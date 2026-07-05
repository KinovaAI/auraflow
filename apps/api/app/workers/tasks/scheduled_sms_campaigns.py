"""AuraFlow — Scheduled SMS Campaign Sender Task

Runs every 5 minutes via Celery Beat. Finds SMS campaigns with
status='scheduled' and scheduled_at in the past, then sends them
using SmsCampaignService.
"""
import asyncio
from datetime import datetime, timezone

from app.core.logging import logger
from app.db.session import get_tenant_db, get_global_db
from app.services.marketing.sms_campaign_service import SmsCampaignService
from app.workers.celery_app import app

sms_campaign_svc = SmsCampaignService()


async def _process_sms_campaigns_for_tenant(schema_name: str) -> int:
    """Process scheduled SMS campaigns for a single tenant."""
    sent_count = 0
    now = datetime.now(timezone.utc)

    async with get_tenant_db(schema_override=schema_name) as db:
        rows = await db.fetch(
            """
            SELECT id, name FROM sms_campaigns
            WHERE status = 'scheduled'
              AND scheduled_at IS NOT NULL
              AND scheduled_at <= $1
            """,
            now,
        )

    for row in rows:
        campaign_id = str(row["id"])
        try:
            await sms_campaign_svc.send_campaign(campaign_id)
            sent_count += 1
            logger.info(
                "Scheduled SMS campaign sent",
                campaign_id=campaign_id,
                name=row["name"],
                schema=schema_name,
            )
        except Exception as e:
            logger.error(
                "Scheduled SMS campaign send failed",
                campaign_id=campaign_id,
                schema=schema_name,
                error=str(e),
            )

    return sent_count


async def _process_all_scheduled_sms_campaigns() -> int:
    """Process scheduled SMS campaigns across all tenants."""
    total = 0
    async with get_global_db() as db:
        schemas = await db.fetch(
            "SELECT schema_name FROM af_global.organizations WHERE status IN ('active', 'trial')"
        )

    for row in schemas:
        try:
            count = await _process_sms_campaigns_for_tenant(row["schema_name"])
            total += count
        except Exception as e:
            logger.error(
                "SMS campaign processing failed for tenant",
                schema=row["schema_name"],
                error=str(e),
            )

    return total


@app.task(name="app.workers.tasks.scheduled_sms_campaigns.process_scheduled_sms_campaigns")
def process_scheduled_sms_campaigns():
    """Celery task: process scheduled SMS campaigns for all tenants."""
    total = asyncio.run(_process_all_scheduled_sms_campaigns())
    if total > 0:
        logger.info("Scheduled SMS campaigns processed", total=total)
    return {"sms_campaigns_sent": total}
