"""AuraFlow — Backup Service

Database and files backup to Backblaze B2 via boto3 (S3-compatible).
Supports on-demand and scheduled backups, restore with confirmation token,
and automatic cleanup of expired backups.
"""
import asyncio
import os
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import boto3
from botocore.config import Config as BotoConfig
from cryptography.fernet import Fernet

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_global_db
from app.core.redis import get_redis


def _b2_client():
    """Create an S3-compatible Backblaze B2 client."""
    return boto3.client(
        "s3",
        endpoint_url=settings.B2_ENDPOINT,
        aws_access_key_id=settings.B2_ACCOUNT_ID,
        aws_secret_access_key=settings.B2_APPLICATION_KEY,
        config=BotoConfig(signature_version="s3v4"),
    )


def _parse_db_url() -> dict:
    """Parse DATABASE_URL into components."""
    parsed = urlparse(settings.DATABASE_URL)
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "user": parsed.username or "auraflow",
        "password": parsed.password or "",
        "dbname": parsed.path.lstrip("/") or "auraflow",
    }


class BackupService:

    async def _verify_backup(self, backup_id: str, file_size: int, b2_key: str) -> bool:
        """Verify a completed backup: check file size > 0 and B2 object exists.

        Updates the backup record with verified = true/false.
        Sends alert email if verification fails.
        """
        verified = True
        failure_reason = None

        # Check 1: file size > 0
        if file_size <= 0:
            verified = False
            failure_reason = f"Backup file size is {file_size} bytes (empty)"

        # Check 2: verify B2 object exists
        if verified:
            try:
                s3 = _b2_client()
                response = await asyncio.to_thread(
                    lambda: s3.head_object(Bucket=settings.B2_BUCKET_BACKUPS, Key=b2_key)
                )
                remote_size = response.get("ContentLength", 0)
                if remote_size <= 0:
                    verified = False
                    failure_reason = f"B2 object exists but has size {remote_size}"
            except Exception as e:
                verified = False
                failure_reason = f"B2 object verification failed: {str(e)[:200]}"

        # Update backup record
        async with get_global_db() as db:
            await db.execute(
                """
                UPDATE af_global.platform_backups
                SET verified = $2
                WHERE id = $1
                """,
                backup_id, verified,
            )

        # Send alert if verification failed
        if not verified:
            logger.error(f"Backup verification FAILED: {failure_reason}", backup_id=backup_id)
            try:
                from app.services.email.email_service import EmailService
                from app.core.config import settings as cfg
                email_svc = EmailService()
                await email_svc.send_email(
                    to_email=cfg.PLATFORM_ADMIN_ALERT_EMAIL,
                    subject=f"ALERT: Backup verification failed — {backup_id[:8]}",
                    html_content=f"""
                    <h2 style="color: #E53E3E;">Backup Verification Failed</h2>
                    <p><strong>Backup ID:</strong> {backup_id}</p>
                    <p><strong>B2 Key:</strong> {b2_key}</p>
                    <p><strong>Reason:</strong> {failure_reason}</p>
                    <p>Please investigate immediately.</p>
                    <p style="color: #666; font-size: 12px;">— AuraFlow Platform</p>
                    """,
                    email_type="platform_alert",
                )
            except Exception as e:
                logger.error(f"Failed to send backup alert email: {e}")
        else:
            logger.info(f"Backup verified successfully", backup_id=backup_id)

        return verified

    @staticmethod
    def _encrypt_file(path: str) -> None:
        """Encrypt a file in-place using Fernet symmetric encryption."""
        f = Fernet(settings.BACKUP_ENCRYPTION_KEY.encode())
        with open(path, "rb") as fh:
            data = fh.read()
        encrypted = f.encrypt(data)
        with open(path, "wb") as fh:
            fh.write(encrypted)

    @staticmethod
    def _decrypt_file(path: str) -> None:
        """Decrypt a Fernet-encrypted file in-place."""
        f = Fernet(settings.BACKUP_ENCRYPTION_KEY.encode())
        with open(path, "rb") as fh:
            data = fh.read()
        decrypted = f.decrypt(data)
        with open(path, "wb") as fh:
            fh.write(decrypted)

    async def list_backups(self, backup_type: str | None = None, limit: int = 50) -> list[dict]:
        async with get_global_db() as db:
            if backup_type:
                rows = await db.fetch("""
                    SELECT * FROM af_global.platform_backups
                    WHERE backup_type = $1
                    ORDER BY created_at DESC LIMIT $2
                """, backup_type, limit)
            else:
                rows = await db.fetch("""
                    SELECT * FROM af_global.platform_backups
                    ORDER BY created_at DESC LIMIT $1
                """, limit)
            return [dict(r) for r in rows]

    async def trigger_database_backup(self, triggered_by: str = "manual") -> dict:
        """Perform pg_dump and upload to B2."""
        backup_id = str(uuid.uuid4())

        # Insert pending record
        async with get_global_db() as db:
            await db.execute("""
                INSERT INTO af_global.platform_backups (id, backup_type, status, triggered_by)
                VALUES ($1, 'database', 'running', $2)
            """, backup_id, triggered_by)

        start = time.time()
        try:
            db_info = _parse_db_url()
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            file_name = f"db_backup_{timestamp}.sql.gz"

            with tempfile.NamedTemporaryFile(suffix=".sql.gz", delete=False) as tmp:
                tmp_path = tmp.name

            env = os.environ.copy()
            env["PGPASSWORD"] = db_info["password"]
            cmd = [
                "pg_dump",
                "-h", db_info["host"],
                "-p", db_info["port"],
                "-U", db_info["user"],
                "-d", db_info["dbname"],
                "--no-owner",
                "--no-privileges",
                "-Z", "9",
                "-f", tmp_path,
            ]
            result = await asyncio.to_thread(
                lambda: subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=settings.BACKUP_TIMEOUT_SECONDS)
            )
            if result.returncode != 0:
                raise RuntimeError(f"pg_dump failed: {result.stderr[:500]}")

            # Encrypt before upload if key is configured
            if settings.BACKUP_ENCRYPTION_KEY:
                await asyncio.to_thread(self._encrypt_file, tmp_path)

            file_size = os.path.getsize(tmp_path)

            # Upload to B2
            s3 = _b2_client()
            b2_key = f"backups/database/{file_name}"
            await asyncio.to_thread(s3.upload_file, tmp_path, settings.B2_BUCKET_BACKUPS, b2_key)

            # Get B2 file ID
            response = await asyncio.to_thread(
                lambda: s3.head_object(Bucket=settings.B2_BUCKET_BACKUPS, Key=b2_key)
            )
            b2_file_id = response.get("VersionId", b2_key)

            duration = int(time.time() - start)

            async with get_global_db() as db:
                row = await db.fetchrow("""
                    UPDATE af_global.platform_backups
                    SET status = 'completed', file_name = $2, file_size_bytes = $3,
                        b2_file_id = $4, b2_bucket = $5, duration_seconds = $6
                    WHERE id = $1
                    RETURNING *
                """, backup_id, file_name, file_size, b2_file_id,
                    settings.B2_BUCKET_BACKUPS, duration)

            logger.info(f"Database backup completed: {file_name} ({file_size} bytes)")

            # Verify the backup
            await self._verify_backup(backup_id, file_size, b2_key)

            return dict(row)

        except Exception as e:
            duration = int(time.time() - start)
            async with get_global_db() as db:
                await db.execute("""
                    UPDATE af_global.platform_backups
                    SET status = 'failed', error_message = $2, duration_seconds = $3
                    WHERE id = $1
                """, backup_id, str(e)[:2000], duration)
            logger.error(f"Database backup failed: {e}")
            raise
        finally:
            if "tmp_path" in locals() and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    async def trigger_files_backup(self, triggered_by: str = "manual") -> dict:
        """Tar the application code/config and upload to B2."""
        backup_id = str(uuid.uuid4())

        async with get_global_db() as db:
            await db.execute("""
                INSERT INTO af_global.platform_backups (id, backup_type, status, triggered_by)
                VALUES ($1, 'files', 'running', $2)
            """, backup_id, triggered_by)

        start = time.time()
        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            file_name = f"files_backup_{timestamp}.tar.gz"

            with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
                tmp_path = tmp.name

            # Tar the app directory excluding regeneratable contents.
            # The container's /app/venv is ~400 MB of pip packages that
            # are already baked into the Docker image — excluding it
            # drops every backup from ~94 MB to ~3-5 MB. (The old
            # `.venv` exclude missed our `venv` dir — no leading dot.)
            cmd = [
                "tar", "-czf", tmp_path,
                "--exclude=__pycache__",
                "--exclude=.git",
                "--exclude=node_modules",
                "--exclude=.next",
                "--exclude=*.pyc",
                "--exclude=.venv",
                "--exclude=venv",
                "--exclude=.pytest_cache",
                "--exclude=.mypy_cache",
                "--exclude=celerybeat-schedule",
                "-C", "/app",
                ".",
            ]
            result = await asyncio.to_thread(
                lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=settings.BACKUP_TIMEOUT_SECONDS)
            )
            if result.returncode != 0:
                raise RuntimeError(f"tar failed: {result.stderr[:500]}")

            # Encrypt before upload if key is configured
            if settings.BACKUP_ENCRYPTION_KEY:
                await asyncio.to_thread(self._encrypt_file, tmp_path)

            file_size = os.path.getsize(tmp_path)

            s3 = _b2_client()
            b2_key = f"backups/files/{file_name}"
            await asyncio.to_thread(s3.upload_file, tmp_path, settings.B2_BUCKET_BACKUPS, b2_key)

            response = await asyncio.to_thread(
                lambda: s3.head_object(Bucket=settings.B2_BUCKET_BACKUPS, Key=b2_key)
            )
            b2_file_id = response.get("VersionId", b2_key)

            duration = int(time.time() - start)

            async with get_global_db() as db:
                row = await db.fetchrow("""
                    UPDATE af_global.platform_backups
                    SET status = 'completed', file_name = $2, file_size_bytes = $3,
                        b2_file_id = $4, b2_bucket = $5, duration_seconds = $6
                    WHERE id = $1
                    RETURNING *
                """, backup_id, file_name, file_size, b2_file_id,
                    settings.B2_BUCKET_BACKUPS, duration)

            logger.info(f"Files backup completed: {file_name} ({file_size} bytes)")

            # Verify the backup
            await self._verify_backup(backup_id, file_size, b2_key)

            return dict(row)

        except Exception as e:
            duration = int(time.time() - start)
            async with get_global_db() as db:
                await db.execute("""
                    UPDATE af_global.platform_backups
                    SET status = 'failed', error_message = $2, duration_seconds = $3
                    WHERE id = $1
                """, backup_id, str(e)[:2000], duration)
            logger.error(f"Files backup failed: {e}")
            raise
        finally:
            if "tmp_path" in locals() and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    async def get_download_url(self, backup_id: str) -> str | None:
        """Generate a presigned download URL for a backup."""
        async with get_global_db() as db:
            row = await db.fetchrow(
                "SELECT * FROM af_global.platform_backups WHERE id = $1 AND status = 'completed'",
                backup_id,
            )
        if not row:
            return None

        s3 = _b2_client()
        b2_key = f"backups/{'database' if row['backup_type'] == 'database' else 'files'}/{row['file_name']}"
        url = await asyncio.to_thread(
            lambda: s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": row["b2_bucket"], "Key": b2_key},
                ExpiresIn=3600,
            )
        )
        return url

    async def request_restore(self, backup_id: str) -> str:
        """Create a time-limited restore confirmation token (5 min TTL in Redis)."""
        token = str(uuid.uuid4())
        redis = await get_redis()
        await redis.set(f"restore:{token}", backup_id, ex=300)
        return token

    async def confirm_restore(self, token: str) -> dict:
        """Execute restore after confirmation. Currently supports DB restore."""
        redis = await get_redis()
        backup_id = await redis.get(f"restore:{token}")
        if not backup_id:
            raise ValueError("Restore token expired or invalid")

        await redis.delete(f"restore:{token}")

        async with get_global_db() as db:
            row = await db.fetchrow(
                "SELECT * FROM af_global.platform_backups WHERE id = $1 AND status = 'completed'",
                backup_id if isinstance(backup_id, str) else backup_id.decode(),
            )
        if not row:
            raise ValueError("Backup not found or not completed")

        if row["backup_type"] != "database":
            raise ValueError("Only database backups can be restored")

        # Download from B2
        s3 = _b2_client()
        b2_key = f"backups/database/{row['file_name']}"

        with tempfile.NamedTemporaryFile(suffix=".sql.gz", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            await asyncio.to_thread(s3.download_file, row["b2_bucket"], b2_key, tmp_path)

            # Decrypt after download if key is configured
            if settings.BACKUP_ENCRYPTION_KEY:
                await asyncio.to_thread(self._decrypt_file, tmp_path)

            db_info = _parse_db_url()
            env = os.environ.copy()
            env["PGPASSWORD"] = db_info["password"]

            def _restore():
                gunzip = subprocess.Popen(
                    ["gunzip", "-c", str(tmp_path)], stdout=subprocess.PIPE
                )
                result = subprocess.run(
                    ["psql", "-h", db_info['host'], "-p", str(db_info['port']),
                     "-U", db_info['user'], "-d", db_info['dbname']],
                    stdin=gunzip.stdout, env=env,
                    capture_output=True, text=True, timeout=settings.BACKUP_TIMEOUT_SECONDS,
                )
                gunzip.wait()
                return result

            result = await asyncio.to_thread(_restore)

            logger.info(f"Database restore completed from backup {backup_id}")
            return {"restored": True, "backup_id": str(row["id"]), "file_name": row["file_name"]}

        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    async def get_status(self) -> dict:
        """Return backup status overview: last backup, next scheduled, B2 health, total size."""
        async with get_global_db() as db:
            last_backup = await db.fetchrow("""
                SELECT * FROM af_global.platform_backups
                WHERE status = 'completed'
                ORDER BY created_at DESC LIMIT 1
            """)
            running = await db.fetchval("""
                SELECT COUNT(*) FROM af_global.platform_backups WHERE status = 'running'
            """)
            total_size = await db.fetchval("""
                SELECT COALESCE(SUM(file_size_bytes), 0) FROM af_global.platform_backups
                WHERE status = 'completed'
            """)
            total_count = await db.fetchval("""
                SELECT COUNT(*) FROM af_global.platform_backups WHERE status = 'completed'
            """)
            next_schedule = await db.fetchrow("""
                SELECT * FROM af_global.platform_backup_schedule
                WHERE is_active = TRUE
                ORDER BY next_run_at ASC NULLS LAST LIMIT 1
            """)

        # Check B2 connection
        b2_connected = False
        try:
            if settings.B2_ACCOUNT_ID and settings.B2_APPLICATION_KEY:
                s3 = _b2_client()
                await asyncio.to_thread(
                    lambda: s3.head_bucket(Bucket=settings.B2_BUCKET_BACKUPS)
                )
                b2_connected = True
        except Exception:
            pass

        return {
            "last_backup": dict(last_backup) if last_backup else None,
            "running_count": running,
            "total_size_bytes": total_size,
            "total_count": total_count,
            "next_scheduled": dict(next_schedule) if next_schedule else None,
            "b2_connected": b2_connected,
            "b2_bucket": settings.B2_BUCKET_BACKUPS,
            "encryption_enabled": bool(settings.BACKUP_ENCRYPTION_KEY),
        }

    async def delete_backup(self, backup_id: str) -> bool:
        """Delete a specific backup from B2 and the database."""
        async with get_global_db() as db:
            row = await db.fetchrow(
                "SELECT * FROM af_global.platform_backups WHERE id = $1",
                backup_id,
            )
        if not row:
            return False

        # Delete from B2 if the file exists
        if row["status"] == "completed" and row["file_name"] and row["b2_bucket"]:
            try:
                s3 = _b2_client()
                b2_key = f"backups/{row['backup_type']}/{row['file_name']}"
                await asyncio.to_thread(
                    lambda: s3.delete_object(Bucket=row["b2_bucket"], Key=b2_key)
                )
            except Exception as e:
                logger.warning(f"Failed to delete B2 object for backup {backup_id}: {e}")

        async with get_global_db() as db:
            await db.execute(
                "DELETE FROM af_global.platform_backups WHERE id = $1",
                backup_id,
            )
        logger.info(f"Deleted backup {backup_id}")
        return True

    # ── Schedules ──────────────────────────────────────────────────────

    async def list_schedules(self) -> list[dict]:
        async with get_global_db() as db:
            rows = await db.fetch(
                "SELECT * FROM af_global.platform_backup_schedule ORDER BY backup_type"
            )
            return [dict(r) for r in rows]

    async def update_schedule(self, schedule_id: str, cron: str | None = None,
                              retention_days: int | None = None,
                              is_active: bool | None = None) -> dict | None:
        async with get_global_db() as db:
            parts = []
            params = [schedule_id]
            idx = 2
            if cron is not None:
                parts.append(f"cron_expression = ${idx}")
                params.append(cron)
                idx += 1
            if retention_days is not None:
                parts.append(f"retention_days = ${idx}")
                params.append(retention_days)
                idx += 1
            if is_active is not None:
                parts.append(f"is_active = ${idx}")
                params.append(is_active)
                idx += 1

            if not parts:
                return None

            row = await db.fetchrow(f"""
                UPDATE af_global.platform_backup_schedule
                SET {', '.join(parts)}
                WHERE id = $1
                RETURNING *
            """, *params)
            return dict(row) if row else None

    async def cleanup_expired_backups(self) -> int:
        """Delete backups older than retention_days. Includes BOTH
        completed and failed rows — failed backups previously
        accumulated forever (rows + any partial multi-part upload
        chunks they left in B2).

        For completed rows: delete the B2 object then the DB row.
        For failed rows: the file_name may be NULL (upload never
        finished), so we skip the B2 delete and just clean up the DB
        side. Orphaned multipart-upload chunks must be aborted by the
        bucket's lifecycle policy (recommended: "abort incomplete
        after 1 day") OR by abort_orphan_multipart_uploads().
        """
        deleted_count = 0
        async with get_global_db() as db:
            schedules = await db.fetch(
                "SELECT backup_type, retention_days FROM af_global.platform_backup_schedule"
            )
            for sched in schedules:
                cutoff = datetime.now(timezone.utc) - timedelta(days=sched["retention_days"])
                expired = await db.fetch("""
                    SELECT id, file_name, b2_bucket, backup_type, status
                    FROM af_global.platform_backups
                    WHERE backup_type = $1
                      AND status IN ('completed', 'failed')
                      AND created_at < $2
                """, sched["backup_type"], cutoff)

                s3 = _b2_client()
                for backup in expired:
                    if backup["status"] == "completed" and backup.get("file_name"):
                        try:
                            b2_key = f"backups/{backup['backup_type']}/{backup['file_name']}"
                            await asyncio.to_thread(
                                lambda: s3.delete_object(Bucket=backup["b2_bucket"], Key=b2_key)
                            )
                        except Exception as e:
                            logger.warning(
                                f"Failed to delete B2 object for backup {backup['id']}: {e}"
                            )

                    await db.execute(
                        "DELETE FROM af_global.platform_backups WHERE id = $1",
                        backup["id"],
                    )
                    deleted_count += 1

        logger.info(f"Cleaned up {deleted_count} expired backups")
        return deleted_count

    async def abort_orphan_multipart_uploads(self) -> int:
        """One-shot: cancel all incomplete multipart uploads in the
        backups bucket. The 50+ failed cap-exceeded uploads left
        partial chunks behind that count toward B2 storage cost
        despite never showing up in object listings. Long-term defense
        is a B2 bucket lifecycle rule that auto-aborts after 24h —
        configure in B2 console; this method is the cleanup-now path.
        """
        s3 = _b2_client()
        bucket = settings.B2_BUCKET_BACKUPS
        aborted = 0
        next_kwargs: dict = {}
        while True:
            resp = await asyncio.to_thread(
                lambda: s3.list_multipart_uploads(Bucket=bucket, **next_kwargs)
            )
            uploads = resp.get("Uploads") or []
            for u in uploads:
                try:
                    await asyncio.to_thread(
                        lambda u=u: s3.abort_multipart_upload(
                            Bucket=bucket, Key=u["Key"], UploadId=u["UploadId"],
                        )
                    )
                    aborted += 1
                except Exception as e:
                    logger.warning(
                        "Failed to abort multipart upload",
                        key=u.get("Key"), upload_id=u.get("UploadId"), error=str(e),
                    )
            if not resp.get("IsTruncated"):
                break
            next_kwargs = {
                "KeyMarker": resp.get("NextKeyMarker"),
                "UploadIdMarker": resp.get("NextUploadIdMarker"),
            }
        logger.info(f"Aborted {aborted} orphan multipart uploads")
        return aborted
