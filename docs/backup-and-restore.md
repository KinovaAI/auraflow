# AuraFlow Backup and Restore

## Overview

AuraFlow uses a two-tier backup strategy:

1. **Shell-based backups** (`infra/scripts/backup.sh`) -- cron-driven `pg_dumpall` uploaded to Backblaze B2 via `rclone`.
2. **Application-level backups** (`app.services.platform.backup_service.BackupService`) -- triggered on-demand or by Celery Beat, using `pg_dump` and boto3 (S3-compatible) uploads to B2.

Both tiers store compressed SQL dumps in the same Backblaze B2 bucket (`$B2_BUCKET_BACKUPS`, default `auraflow-backups`).

---

## Backup Schedule

### Automated (Celery Beat)

| Task | Schedule | Description |
|------|----------|-------------|
| `platform.check_backup_schedules` | Every 5 minutes | Checks `af_global.platform_backup_schedule` for due backups and triggers them |
| `platform.cleanup_expired_backups` | Daily at 03:00 UTC | Deletes backups older than the configured retention period |

Backup schedules are stored in the `af_global.platform_backup_schedule` table with configurable cron expressions, retention days, and active/inactive status.

### Automated (Cron -- infra/scripts/backup.sh)

| Cron | Description |
|------|-------------|
| `0 2 * * *` | Nightly full `pg_dumpall` at 02:00 local time |

Add to crontab:
```bash
0 2 * * * /opt/auraflow/infra/scripts/backup.sh
```

---

## Retention Policy

| Tier | Retention | Cleanup |
|------|-----------|---------|
| Shell script (local) | 3 days | `find -mtime +3 -delete` in backup.sh |
| Shell script (B2) | 90 days | `rclone delete --min-age 90d` in backup.sh |
| App-level (B2) | Configurable per schedule | `platform.cleanup_expired_backups` Celery task (daily at 03:00 UTC) |

App-level retention is configured per backup type in `af_global.platform_backup_schedule.retention_days`.

---

## Storage

All backups are stored in Backblaze B2 using S3-compatible API.

| Setting | Environment Variable | Default |
|---------|---------------------|---------|
| Bucket | `B2_BUCKET_BACKUPS` | `auraflow-backups` |
| Endpoint | `B2_ENDPOINT` | `https://s3.us-west-002.backblazeb2.com` |
| Account ID | `B2_ACCOUNT_ID` | (required) |
| App Key | `B2_APPLICATION_KEY` | (required) |

B2 directory structure:
```
auraflow-backups/
  backups/
    database/
      db_backup_20260315_020000.sql.gz
    files/
      files_backup_20260315_020000.tar.gz
  postgres/          # Shell-script backups (rclone)
    postgres-2026-03-15-0200.sql.gz
```

---

## Manual Backup

### Via API (application-level)

Trigger a database backup through the platform admin API:

```bash
# Trigger database backup
curl -X POST https://api.auraflow.fit/api/v1/platform/backups/trigger \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"backup_type": "database"}'

# Trigger files backup
curl -X POST https://api.auraflow.fit/api/v1/platform/backups/trigger \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"backup_type": "files"}'

# List backups
curl https://api.auraflow.fit/api/v1/platform/backups \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

### Via shell script

```bash
# Run the backup script directly
sudo /opt/auraflow/infra/scripts/backup.sh

# Or manually with pg_dump
PGPASSWORD="$DB_PASSWORD" pg_dump \
  -h localhost -U auraflow -d auraflow \
  --no-owner --no-privileges -Z 9 \
  -f /tmp/auraflow-manual-backup.sql.gz
```

---

## Restore Procedure

### Via API (two-step confirmation)

The API uses a confirmation token to prevent accidental restores:

```bash
# Step 1: Request a restore token (valid for 5 minutes)
curl -X POST https://api.auraflow.fit/api/v1/platform/backups/{backup_id}/restore \
  -H "Authorization: Bearer $ADMIN_TOKEN"
# Returns: {"token": "abc-123-..."}

# Step 2: Confirm the restore
curl -X POST https://api.auraflow.fit/api/v1/platform/backups/restore/confirm \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"token": "abc-123-..."}'
```

### Manual restore from B2

```bash
# 1. Download the backup from B2
rclone copy "b2:auraflow-backups/backups/database/db_backup_20260315_020000.sql.gz" /tmp/

# 2. Stop the application to prevent writes
sudo systemctl stop auraflow-api auraflow-worker

# 3. Restore the database
gunzip -c /tmp/db_backup_20260315_020000.sql.gz | \
  PGPASSWORD="$DB_PASSWORD" psql -h localhost -U auraflow -d auraflow

# 4. Restart the application
sudo systemctl start auraflow-api auraflow-worker
```

### Manual restore from shell-script backups

```bash
# 1. Download from B2
rclone copy "b2:auraflow-backups/postgres/postgres-2026-03-15-0200.sql.gz" /tmp/

# 2. Stop the application
sudo systemctl stop auraflow-api auraflow-worker

# 3. Restore (pg_dumpall output -- uses psql)
gunzip -c /tmp/postgres-2026-03-15-0200.sql.gz | \
  PGPASSWORD="$DB_PASSWORD" psql -h localhost -U auraflow -d postgres

# 4. Restart the application
sudo systemctl start auraflow-api auraflow-worker
```

---

## Automated Restore Testing

Use the restore test script to verify backup integrity:

```bash
sudo /opt/auraflow/infra/scripts/restore-test.sh
```

This script downloads the latest backup, restores it to a temporary database, runs verification queries, and cleans up. See `infra/scripts/restore-test.sh` for details.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Backup task not running | Check Celery Beat is running: `celery -A app.workers.celery_app inspect active` |
| B2 upload fails | Verify `B2_ACCOUNT_ID` and `B2_APPLICATION_KEY` env vars are set |
| Restore token expired | Tokens are valid for 5 minutes -- request a new one |
| `pg_dump` fails | Ensure the database user has sufficient privileges and `pg_dump` version matches the server |
| Backup log location | Shell script: `/var/log/auraflow-backup.log`; App-level: check `af_global.platform_backups` table |
