"""AuraFlow — EMR Sync Celery Tasks

Handles asynchronous outbound sync from AuraFlow to EMR systems.
- sync_member_to_emr: fired after member creation
- sync_attendance_to_emr: fired after class check-in
- emr_periodic_retry: retries failed syncs every 15 minutes
"""
import asyncio

from app.core.logging import logger
from app.db.session import get_global_db
from app.workers.celery_app import app


@app.task(
    name="app.workers.tasks.emr_sync.sync_member_to_emr",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def sync_member_to_emr(self, schema_name: str, member_id: str):
    """Push new/updated member to EMR as a Patient."""
    try:
        from app.services.integrations.emr import emr_service
        result = asyncio.run(
            emr_service.sync_member_to_emr(schema_name, member_id)
        )
        if result:
            logger.info("EMR member sync complete", member_id=member_id, emr_patient_id=result)
        return result
    except Exception as exc:
        logger.error("EMR member sync task failed", member_id=member_id, error=str(exc))
        raise self.retry(exc=exc)


@app.task(
    name="app.workers.tasks.emr_sync.sync_attendance_to_emr",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def sync_attendance_to_emr(self, schema_name: str, booking_id: str):
    """Push class check-in to EMR as an Encounter."""
    try:
        from app.services.integrations.emr import emr_service
        result = asyncio.run(
            emr_service.sync_attendance_to_emr(schema_name, booking_id)
        )
        if result:
            logger.info("EMR attendance sync complete", booking_id=booking_id, emr_encounter_id=result)
        return result
    except Exception as exc:
        logger.error("EMR attendance sync task failed", booking_id=booking_id, error=str(exc))
        raise self.retry(exc=exc)


@app.task(name="app.workers.tasks.emr_sync.emr_periodic_retry")
def emr_periodic_retry():
    """Retry failed EMR syncs for all tenants. Runs every 15 minutes via Beat."""
    async def _retry_all():
        from app.services.integrations.emr import emr_service
        async with get_global_db() as db:
            orgs = await db.fetch(
                """
                SELECT slug FROM af_global.organizations
                WHERE status IN ('active', 'trial') AND emr_sync_enabled = TRUE
                """
            )

        total_retried = 0
        for org in orgs:
            schema = f"af_tenant_{org['slug']}"
            try:
                retried = await emr_service.retry_failed_syncs(schema)
                total_retried += retried
            except Exception as e:
                logger.error("EMR retry failed for tenant", schema=schema, error=str(e))

        if total_retried > 0:
            logger.info("EMR periodic retry complete", total_retried=total_retried)

    asyncio.run(_retry_all())
