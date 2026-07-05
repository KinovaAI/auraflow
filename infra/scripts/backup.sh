#!/bin/bash
# AuraFlow Automated Backup Script
# Add to crontab: 0 2 * * * /opt/auraflow/infra/scripts/backup.sh

set -euo pipefail

DATE=$(date +%Y-%m-%d-%H%M)
BACKUP_DIR="/tmp/auraflow-backups"
LOG_FILE="/var/log/auraflow-backup.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

mkdir -p "$BACKUP_DIR"
log "Starting backup $DATE"

# Database backup
log "Backing up PostgreSQL..."
PGPASSWORD="${DB_PASSWORD}" pg_dumpall \
    -h localhost \
    -U auraflow \
    --clean \
    --if-exists \
    | gzip > "$BACKUP_DIR/postgres-$DATE.sql.gz"

log "PostgreSQL backup complete: $(du -sh "$BACKUP_DIR/postgres-$DATE.sql.gz" | cut -f1)"

# Upload to Backblaze B2
log "Uploading to Backblaze B2..."
rclone copy "$BACKUP_DIR/postgres-$DATE.sql.gz" \
    "b2:${B2_BUCKET_BACKUPS}/postgres/" \
    --log-level INFO

log "Upload complete"

# Clean up local backup files older than 3 days
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +3 -delete

# Clean up B2 backups older than 90 days
rclone delete "b2:${B2_BUCKET_BACKUPS}/postgres/" \
    --min-age 90d \
    --log-level INFO

log "Backup complete for $DATE"
