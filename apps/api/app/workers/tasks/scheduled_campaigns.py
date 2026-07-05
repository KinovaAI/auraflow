"""AuraFlow — Scheduled Campaign Sender Task

Runs every 5 minutes via Celery Beat. Finds email campaigns with
status='scheduled' and scheduled_at in the past, then sends them
using the existing CampaignService.
"""
import asyncio
from datetime import datetime, timezone

from app.core.logging import logger
from app.db.session import get_tenant_db, get_global_db
from app.services.marketing.campaign_service import CampaignService
from app.workers.celery_app import app

campaign_svc = CampaignService()


async def _process_campaigns_for_tenant(schema_name: str) -> int:
    """Process scheduled campaigns for a single tenant.

    Atomic claim pattern guards against double-send when the 5-min beat
    double-fires or when two workers race on the same campaign row:
    each campaign's status is flipped from 'scheduled' → 'sending' via
    UPDATE ... RETURNING id. Only the row that returns a non-empty result
    is actually sent by this worker; the other gets skipped cleanly.
    """
    sent_count = 0
    now = datetime.now(timezone.utc)

    async with get_tenant_db(schema_override=schema_name) as db:
        rows = await db.fetch(
            """
            SELECT id, name FROM email_campaigns
            WHERE status = 'scheduled'
              AND scheduled_at IS NOT NULL
              AND scheduled_at <= $1
            """,
            now,
        )

    for row in rows:
        campaign_id = str(row["id"])
        # Atomic claim: flip status 'scheduled' → 'sending' ONLY if still
        # scheduled. If another worker got there first we get no row back
        # and skip quietly.
        async with get_tenant_db(schema_override=schema_name) as db:
            claimed = await db.fetchval(
                """
                UPDATE email_campaigns
                SET status = 'sending', updated_at = NOW()
                WHERE id = $1 AND status = 'scheduled'
                RETURNING id
                """,
                row["id"],
            )
        if not claimed:
            logger.info(
                "Scheduled campaign already claimed by another worker — skipping",
                campaign_id=campaign_id,
                schema=schema_name,
            )
            continue

        try:
            await campaign_svc.send_campaign(campaign_id)
            sent_count += 1
            logger.info(
                "Scheduled campaign sent",
                campaign_id=campaign_id,
                name=row["name"],
                schema=schema_name,
            )
        except Exception as e:
            # Put the row back so a future beat can retry, instead of
            # leaving it stranded in 'sending' forever.
            try:
                async with get_tenant_db(schema_override=schema_name) as db:
                    await db.execute(
                        "UPDATE email_campaigns SET status = 'scheduled', updated_at = NOW() "
                        "WHERE id = $1 AND status = 'sending'",
                        row["id"],
                    )
            except Exception:
                pass
            logger.error(
                "Scheduled campaign send failed — reset to scheduled for retry",
                campaign_id=campaign_id,
                schema=schema_name,
                error=str(e),
            )

    return sent_count


async def _process_all_scheduled_campaigns() -> int:
    """Process scheduled campaigns across all tenants."""
    total = 0
    async with get_global_db() as db:
        schemas = await db.fetch(
            "SELECT schema_name FROM af_global.organizations WHERE status IN ('active', 'trial')"
        )

    for row in schemas:
        try:
            count = await _process_campaigns_for_tenant(row["schema_name"])
            total += count
        except Exception as e:
            logger.error(
                "Campaign processing failed for tenant",
                schema=row["schema_name"],
                error=str(e),
            )

    return total


@app.task(name="app.workers.tasks.scheduled_campaigns.process_scheduled_campaigns")
def process_scheduled_campaigns():
    """Celery task: process scheduled campaigns for all tenants."""
    loop = asyncio.new_event_loop()
    try:
        total = loop.run_until_complete(_process_all_scheduled_campaigns())
        if total > 0:
            logger.info("Scheduled campaigns processed", total=total)
        return {"campaigns_sent": total}
    finally:
        loop.close()
