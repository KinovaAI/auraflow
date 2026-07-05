"""AuraFlow — AI Office Manager Celery Tasks

Background tasks for the Office Manager:
- process_inbound_office_sms: async handler for inbound SMS (non-blocking webhook)
- check_sub_request_timeout: fires 15 min after a sub request SMS; moves to next if no response
- daily_inventory_check: runs daily at 8am; checks all tenants for low inventory
"""
import asyncio
from datetime import datetime, timezone

from app.core.logging import logger
from app.db.session import get_global_db
from app.workers.celery_app import app


# ── Process Inbound SMS ───────────────────────────────────────────────────────

@app.task(
    name="app.workers.tasks.office_manager.process_inbound_office_sms",
    bind=True,
    max_retries=2,
    default_retry_delay=10,
)
def process_inbound_office_sms(self, schema_name: str, from_number: str, body: str):
    """Handle inbound SMS through the AI Office Manager (async, non-blocking).

    Called by the Twilio webhook to offload processing from the HTTP request.
    """
    try:
        asyncio.run(_process_inbound_office_sms(schema_name, from_number, body))
    except Exception as exc:
        logger.error(
            "Office Manager SMS processing failed",
            schema=schema_name,
            from_number=from_number,
            error=str(exc),
        )
        raise self.retry(exc=exc)


async def _process_inbound_office_sms(schema_name: str, from_number: str, body: str):
    from app.services.ai.office_manager_service import OfficeManagerService
    svc = OfficeManagerService()
    result = await svc.handle_inbound_sms(
        from_number=from_number,
        body=body,
        schema=schema_name,
    )
    logger.info(
        "Office Manager SMS processed",
        schema=schema_name,
        from_number=from_number,
        result_status=result.get("status"),
    )


# ── Sub Request Timeout ──────────────────────────────────────────────────────

@app.task(
    name="app.workers.tasks.office_manager.check_sub_request_timeout",
    bind=True,
    max_retries=1,
    default_retry_delay=30,
)
def check_sub_request_timeout(
    self, schema_name: str, sub_request_id: str, instructor_id: str
):
    """Check if a sub request has timed out (no response in 15 min).

    Scheduled via apply_async(countdown=900) when an SMS is sent to a candidate.
    If the instructor hasn't responded, marks as timed out and contacts the next one.
    """
    try:
        asyncio.run(
            _check_sub_request_timeout(schema_name, sub_request_id, instructor_id)
        )
    except Exception as exc:
        logger.error(
            "Sub request timeout check failed",
            schema=schema_name,
            sub_request_id=sub_request_id,
            error=str(exc),
        )
        raise self.retry(exc=exc)


async def _check_sub_request_timeout(
    schema_name: str, sub_request_id: str, instructor_id: str
):
    from app.services.ai.office_manager_service import OfficeManagerService
    svc = OfficeManagerService()
    result = await svc.handle_sub_timeout(
        schema=schema_name,
        sub_request_id=sub_request_id,
        instructor_id=instructor_id,
    )
    logger.info(
        "Sub request timeout processed",
        schema=schema_name,
        sub_request_id=sub_request_id,
        result=result.get("status"),
    )


# ── Daily Inventory Check ────────────────────────────────────────────────────

@app.task(name="app.workers.tasks.office_manager.daily_inventory_check")
def daily_inventory_check():
    """Run daily at 8am. Iterate all active tenants and check inventory levels."""
    asyncio.run(_daily_inventory_check())


async def _daily_inventory_check():
    async with get_global_db() as db:
        rows = await db.fetch(
            "SELECT schema_name FROM af_global.organizations WHERE status IN ('active', 'trial')"
        )

    checked = 0
    alerts = 0
    for row in rows:
        schema_name = row["schema_name"]
        try:
            from app.services.ai.office_manager_service import OfficeManagerService
            svc = OfficeManagerService()
            result = await svc.check_inventory_levels(schema_name)
            checked += 1
            if result.get("status") == "low_inventory":
                alerts += 1
                logger.info(
                    "Low inventory found",
                    schema=schema_name,
                    items=len(result.get("low_items", [])),
                )
        except Exception as e:
            logger.error(
                "Inventory check failed for tenant",
                schema=schema_name,
                error=str(e),
            )

    logger.info(
        "Daily inventory check complete",
        tenants_checked=checked,
        tenants_with_alerts=alerts,
    )
