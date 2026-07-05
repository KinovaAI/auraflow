"""AuraFlow — Outgoing Webhook Retry Task

Runs every 2 minutes via Celery Beat. Finds webhook_deliveries rows whose
status is 'failed' and whose next_retry_at has elapsed, re-attempts
delivery, and either marks them 'delivered' or bumps them to the next
retry slot (or 'dead_letter' if retries are exhausted).

Without this task, WebhookDeliveryService.process_retries() was defined
but never called, so outgoing webhook deliveries that failed their first
attempt were never re-tried beyond the inline attempt at fire_event time.
"""
import asyncio

from app.core.logging import logger
from app.db.session import get_global_db
from app.core.tenant_context import set_tenant_context, clear_tenant_context
from app.services.webhooks.webhook_delivery_service import WebhookDeliveryService
from app.workers.celery_app import app


svc = WebhookDeliveryService()


async def _process_all() -> dict:
    """Run process_retries across every active tenant schema."""
    async with get_global_db() as db:
        schemas = await db.fetch(
            "SELECT schema_name FROM af_global.organizations "
            "WHERE status IN ('active', 'trial')"
        )

    total = 0
    per_tenant: list[dict] = []
    for row in schemas:
        schema = row["schema_name"]
        set_tenant_context(
            organization_id="",
            schema_name=schema,
            slug=schema.replace("af_tenant_", ""),
        )
        try:
            count = await svc.process_retries()
            total += count
            per_tenant.append({"schema": schema, "processed": count})
        except Exception as exc:
            logger.warning(
                "Webhook retry failed for tenant",
                schema=schema,
                error=str(exc),
            )
            per_tenant.append({"schema": schema, "error": str(exc)})
        finally:
            clear_tenant_context()

    return {"total_processed": total, "tenants": per_tenant}


@app.task(name="app.workers.tasks.webhook_retries.process_webhook_retries")
def process_webhook_retries():
    """Celery beat task — retry failed outgoing webhook deliveries."""
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_process_all())
        if result["total_processed"]:
            logger.info(
                "Webhook retries processed",
                total=result["total_processed"],
            )
        return result
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        loop.close()
