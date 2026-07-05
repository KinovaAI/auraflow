"""AuraFlow — Mailchimp Sync Celery Tasks

Handles asynchronous outbound sync from AuraFlow to Mailchimp.
- sync_member_to_mailchimp: fired after member creation/update
- mailchimp_bulk_sync: triggered manually via admin endpoint
"""
import asyncio

from app.core.logging import logger
from app.workers.celery_app import app


@app.task(
    name="app.workers.tasks.mailchimp_sync.sync_member_to_mailchimp",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def sync_member_to_mailchimp(self, schema_name: str, member_id: str):
    """Push new/updated member to Mailchimp audience."""
    try:
        from app.services.integrations.mailchimp_service import mailchimp_service
        result = asyncio.run(
            mailchimp_service.sync_member(schema_name, member_id)
        )
        if result:
            logger.info("Mailchimp member sync complete", member_id=member_id, subscriber_hash=result)
        return result
    except Exception as exc:
        logger.error("Mailchimp member sync task failed", member_id=member_id, error=str(exc))
        raise self.retry(exc=exc)


@app.task(
    name="app.workers.tasks.mailchimp_sync.mailchimp_bulk_sync",
    bind=True,
    max_retries=1,
    default_retry_delay=300,
)
def mailchimp_bulk_sync(self, schema_name: str):
    """Bulk sync all active members to Mailchimp. Triggered manually."""
    try:
        from app.services.integrations.mailchimp_service import mailchimp_service
        result = asyncio.run(
            mailchimp_service.sync_all_members(schema_name)
        )
        logger.info("Mailchimp bulk sync complete", schema=schema_name, result=result)
        return result
    except Exception as exc:
        logger.error("Mailchimp bulk sync task failed", schema=schema_name, error=str(exc))
        raise self.retry(exc=exc)
