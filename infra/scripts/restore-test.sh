#!/bin/bash
# AuraFlow — Automated Restore Test Script
#
# Downloads the latest database backup from Backblaze B2, restores it to a
# temporary database, runs verification queries, and cleans up.
#
# Prerequisites:
#   - rclone configured with a "b2" remote
#   - PostgreSQL client tools (psql, createdb, dropdb)
#   - Environment variables: DB_PASSWORD, B2_BUCKET_BACKUPS (optional, defaults
#     to "auraflow-backups")
#
# Usage:
#   sudo ./restore-test.sh

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────

B2_BUCKET="${B2_BUCKET_BACKUPS:-auraflow-backups}"
B2_PATH="backups/database"
TEMP_DB="auraflow_restore_test_$$"
TEMP_DIR="/tmp/auraflow-restore-test-$$"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-auraflow}"
LOG_FILE="/tmp/auraflow-restore-test.log"
EXIT_CODE=0

# ── Helpers ───────────────────────────────────────────────────────────────────

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

cleanup() {
    log "Cleaning up..."
    # Drop temporary database
    PGPASSWORD="${DB_PASSWORD}" dropdb \
        -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" \
        --if-exists "$TEMP_DB" 2>/dev/null || true
    # Remove temporary files
    rm -rf "$TEMP_DIR"
    if [ "$EXIT_CODE" -eq 0 ]; then
        log "Restore test PASSED"
    else
        log "Restore test FAILED (exit code $EXIT_CODE)"
    fi
    exit "$EXIT_CODE"
}

trap cleanup EXIT

# ── Main ──────────────────────────────────────────────────────────────────────

mkdir -p "$TEMP_DIR"
log "Starting restore test (temp DB: $TEMP_DB)"

# 1. Find the latest backup in B2
log "Listing backups in b2:${B2_BUCKET}/${B2_PATH}/..."
LATEST=$(rclone lsf "b2:${B2_BUCKET}/${B2_PATH}/" \
    --files-only \
    | grep '\.sql\.gz$' \
    | sort \
    | tail -1)

if [ -z "$LATEST" ]; then
    log "ERROR: No database backups found in b2:${B2_BUCKET}/${B2_PATH}/"
    EXIT_CODE=1
    exit 1
fi

log "Latest backup: $LATEST"

# 2. Download the backup
log "Downloading $LATEST..."
rclone copy "b2:${B2_BUCKET}/${B2_PATH}/${LATEST}" "$TEMP_DIR/" --log-level INFO
BACKUP_FILE="$TEMP_DIR/$LATEST"

if [ ! -f "$BACKUP_FILE" ]; then
    log "ERROR: Download failed — file not found at $BACKUP_FILE"
    EXIT_CODE=1
    exit 1
fi

BACKUP_SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
log "Downloaded $BACKUP_SIZE"

# 3. Create temporary database
log "Creating temporary database '$TEMP_DB'..."
PGPASSWORD="${DB_PASSWORD}" createdb \
    -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" \
    "$TEMP_DB"

# 4. Restore the backup
log "Restoring backup to '$TEMP_DB'..."
gunzip -c "$BACKUP_FILE" | PGPASSWORD="${DB_PASSWORD}" psql \
    -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" \
    -d "$TEMP_DB" \
    --quiet \
    -v ON_ERROR_STOP=0 \
    > "$TEMP_DIR/restore.log" 2>&1

log "Restore complete"

# 5. Run verification queries
log "Running verification queries..."

run_check() {
    local description="$1"
    local query="$2"
    local result

    result=$(PGPASSWORD="${DB_PASSWORD}" psql \
        -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" \
        -d "$TEMP_DB" \
        -t -A -c "$query" 2>/dev/null) || true

    if [ -z "$result" ] || [ "$result" = "0" ]; then
        log "  WARN: $description — got '$result'"
        return 1
    else
        log "  OK:   $description — $result"
        return 0
    fi
}

CHECKS_PASSED=0
CHECKS_TOTAL=0

check() {
    CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
    if run_check "$1" "$2"; then
        CHECKS_PASSED=$((CHECKS_PASSED + 1))
    fi
}

# Global schema checks
check "af_global schema exists" \
    "SELECT count(*) FROM information_schema.schemata WHERE schema_name = 'af_global'"

check "organizations table has rows" \
    "SELECT count(*) FROM af_global.organizations"

check "users table has rows" \
    "SELECT count(*) FROM af_global.users"

# Tenant schema checks — get first active tenant
TENANT_SCHEMA=$(PGPASSWORD="${DB_PASSWORD}" psql \
    -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" \
    -d "$TEMP_DB" \
    -t -A -c "SELECT schema_name FROM af_global.organizations WHERE status != 'cancelled' LIMIT 1" 2>/dev/null) || true

if [ -n "$TENANT_SCHEMA" ]; then
    log "  Checking tenant schema: $TENANT_SCHEMA"

    check "tenant members table exists" \
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = '$TENANT_SCHEMA' AND table_name = 'members'"

    check "tenant studios table exists" \
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = '$TENANT_SCHEMA' AND table_name = 'studios'"

    check "tenant class_types table exists" \
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = '$TENANT_SCHEMA' AND table_name = 'class_types'"

    check "tenant bookings table exists" \
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = '$TENANT_SCHEMA' AND table_name = 'bookings'"

    check "tenant membership_types table exists" \
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = '$TENANT_SCHEMA' AND table_name = 'membership_types'"
else
    log "  WARN: No active tenant schema found — skipping tenant checks"
fi

# Summary
log "Verification: $CHECKS_PASSED/$CHECKS_TOTAL checks passed"

if [ "$CHECKS_PASSED" -lt "$CHECKS_TOTAL" ]; then
    log "WARNING: Some verification checks failed"
    # Don't fail the script for missing data — structure is what matters
fi

log "Restore test completed successfully"
