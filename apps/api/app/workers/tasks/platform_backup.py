"""AuraFlow — Platform Backup Celery Tasks

Scheduled backup tasks: check cron schedules, run backups, cleanup expired.
"""
import asyncio
from datetime import datetime

from croniter import croniter

from app.core.logging import logger
from app.workers.celery_app import app as celery_app


def _run_async(coro):
    """Run an async coroutine from sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="platform.check_backup_schedules", bind=True, max_retries=2)
def check_backup_schedules(self):
    """Check if any backup schedules are due and trigger them."""
    try:
        _run_async(_check_schedules())
    except Exception as e:
        logger.error(f"check_backup_schedules failed: {e}")
        raise self.retry(exc=e, countdown=60)


async def _check_schedules():
    from app.services.platform.backup_service import BackupService
    from app.db.session import get_global_db

    svc = BackupService()
    now = datetime.utcnow()

    async with get_global_db() as db:
        schedules = await db.fetch("""
            SELECT * FROM af_global.platform_backup_schedule
            WHERE is_active = TRUE
        """)

        for sched in schedules:
            cron = croniter(sched["cron_expression"], sched["last_run_at"] or now)
            next_run = cron.get_next(datetime)

            if next_run <= now:
                logger.info(f"Triggering scheduled {sched['backup_type']} backup")
                try:
                    if sched["backup_type"] == "database":
                        await svc.trigger_database_backup("scheduled")
                    else:
                        await svc.trigger_files_backup("scheduled")

                    await db.execute("""
                        UPDATE af_global.platform_backup_schedule
                        SET last_run_at = $2, next_run_at = $3
                        WHERE id = $1
                    """, sched["id"], now, cron.get_next(datetime))
                except Exception as e:
                    logger.error(f"Scheduled {sched['backup_type']} backup failed: {e}")


@celery_app.task(name="platform.scheduled_db_backup", bind=True, max_retries=2)
def scheduled_db_backup(self):
    """Direct database backup task."""
    try:
        from app.services.platform.backup_service import BackupService
        result = _run_async(BackupService().trigger_database_backup("scheduled"))
        logger.info(f"Scheduled DB backup completed: {result.get('file_name')}")
    except Exception as e:
        logger.error(f"scheduled_db_backup failed: {e}")
        raise self.retry(exc=e, countdown=120)


@celery_app.task(name="platform.scheduled_files_backup", bind=True, max_retries=2)
def scheduled_files_backup(self):
    """Direct files backup task."""
    try:
        from app.services.platform.backup_service import BackupService
        result = _run_async(BackupService().trigger_files_backup("scheduled"))
        logger.info(f"Scheduled files backup completed: {result.get('file_name')}")
    except Exception as e:
        logger.error(f"scheduled_files_backup failed: {e}")
        raise self.retry(exc=e, countdown=120)


@celery_app.task(name="platform.cleanup_expired_backups")
def cleanup_expired_backups():
    """Remove backups older than retention_days."""
    try:
        from app.services.platform.backup_service import BackupService
        deleted = _run_async(BackupService().cleanup_expired_backups())
        logger.info(f"Cleaned up {deleted} expired backups")
    except Exception as e:
        logger.error(f"cleanup_expired_backups failed: {e}")
