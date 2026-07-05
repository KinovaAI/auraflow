"""AuraFlow — AI Engagement Autopilot Tasks

Celery tasks for automated member re-engagement:
- Daily scan for disengaged members (10am UTC)
- Follow-up processing (2pm UTC)
- Outcome checking (6pm UTC)
- Inbound reply handling (async, on-demand)
"""
import asyncio

from app.core.logging import logger
from app.db.session import get_global_db
from app.services.ai.engagement_autopilot import (
    EngagementAutopilot,
    MAX_CAMPAIGNS_PER_TENANT_PER_DAY,
)
from app.workers.celery_app import app

autopilot = EngagementAutopilot()


# ── Daily Engagement Scan (10am UTC) ──────────────────────────────────────

async def _scan_all_tenants() -> dict:
    """Scan all tenants for disengaged members and create campaigns."""
    total_campaigns = 0
    total_targets = 0

    async with get_global_db() as db:
        schemas = await db.fetch(
            "SELECT schema_name FROM af_global.organizations WHERE status IN ('active', 'trial')"
        )

    for row in schemas:
        schema = row["schema_name"]
        try:
            targets = await autopilot.scan_for_engagement_targets(schema)
            total_targets += len(targets)

            # Create campaigns for top targets (capped per tenant per day)
            created = 0
            for target in targets[:MAX_CAMPAIGNS_PER_TENANT_PER_DAY]:
                try:
                    campaign_id = await autopilot.create_campaign(
                        schema=schema,
                        member_id=target["member_id"],
                        engagement_type=target["engagement_type"],
                        member_data=target["member_data"],
                    )
                    if campaign_id:
                        created += 1
                except Exception as e:
                    logger.error(
                        "Failed to create engagement campaign",
                        schema=schema,
                        member_id=target["member_id"],
                        error=str(e),
                    )

            total_campaigns += created
            if created:
                logger.info(
                    "Engagement campaigns created for tenant",
                    schema=schema,
                    targets_found=len(targets),
                    campaigns_created=created,
                )
        except Exception as e:
            logger.error(
                "Engagement scan failed for tenant",
                schema=schema,
                error=str(e),
            )

    return {
        "total_targets": total_targets,
        "total_campaigns": total_campaigns,
    }


@app.task(name="app.workers.tasks.engagement_autopilot.daily_engagement_scan")
def daily_engagement_scan():
    """Celery task: daily scan for disengaged members across all tenants."""
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_scan_all_tenants())
        logger.info(
            "Daily engagement scan complete",
            targets=result["total_targets"],
            campaigns=result["total_campaigns"],
        )
        return result
    finally:
        loop.close()


# ── Follow-up Processing (2pm UTC) ────────────────────────────────────────

async def _process_all_followups() -> dict:
    """Process follow-ups for all tenants."""
    total_sent = 0

    async with get_global_db() as db:
        schemas = await db.fetch(
            "SELECT schema_name FROM af_global.organizations WHERE status IN ('active', 'trial')"
        )

    for row in schemas:
        try:
            sent = await autopilot.process_followups(row["schema_name"])
            total_sent += sent
        except Exception as e:
            logger.error(
                "Engagement follow-up failed for tenant",
                schema=row["schema_name"],
                error=str(e),
            )

    return {"total_followups_sent": total_sent}


@app.task(name="app.workers.tasks.engagement_autopilot.process_engagement_followups")
def process_engagement_followups():
    """Celery task: process follow-ups for active engagement campaigns."""
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_process_all_followups())
        logger.info(
            "Engagement follow-ups complete",
            sent=result["total_followups_sent"],
        )
        return result
    finally:
        loop.close()


# ── Outcome Checking (6pm UTC) ────────────────────────────────────────────

async def _check_all_outcomes() -> dict:
    """Check campaign outcomes for all tenants."""
    total_converted = 0
    total_checked = 0

    async with get_global_db() as db:
        schemas = await db.fetch(
            "SELECT schema_name FROM af_global.organizations WHERE status IN ('active', 'trial')"
        )

    for row in schemas:
        try:
            result = await autopilot.check_campaign_outcomes(row["schema_name"])
            total_checked += result["checked"]
            total_converted += result["converted"]
        except Exception as e:
            logger.error(
                "Engagement outcome check failed for tenant",
                schema=row["schema_name"],
                error=str(e),
            )

    return {"total_checked": total_checked, "total_converted": total_converted}


@app.task(name="app.workers.tasks.engagement_autopilot.check_engagement_outcomes")
def check_engagement_outcomes():
    """Celery task: check if campaigned members have engaged."""
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_check_all_outcomes())
        logger.info(
            "Engagement outcome check complete",
            checked=result["total_checked"],
            converted=result["total_converted"],
        )
        return result
    finally:
        loop.close()


# ── Inbound Reply Handling (on-demand) ────────────────────────────────────

async def _handle_reply(schema_name: str, campaign_id: str, reply_text: str) -> dict:
    """Handle an inbound reply for a specific campaign."""
    return await autopilot.handle_reply(schema_name, campaign_id, reply_text)


@app.task(name="app.workers.tasks.engagement_autopilot.handle_engagement_reply")
def handle_engagement_reply(schema_name: str, campaign_id: str, reply_text: str):
    """Celery task: handle an inbound reply to an engagement campaign email."""
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_handle_reply(schema_name, campaign_id, reply_text))
        logger.info(
            "Engagement reply handled",
            schema=schema_name,
            campaign_id=campaign_id,
            action=result.get("action"),
        )
        return result
    finally:
        loop.close()
