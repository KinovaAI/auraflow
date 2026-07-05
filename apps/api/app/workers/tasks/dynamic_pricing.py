"""AuraFlow — Nightly Dynamic Pricing Task

Runs nightly via Celery Beat. Generates AI price suggestions for
upcoming drop-in classes across all tenant schemas.
"""
import asyncio

from app.core.logging import logger
from app.db.session import get_global_db
from app.services.ai.dynamic_pricing_service import DynamicPricingService
from app.workers.celery_app import app

pricing_svc = DynamicPricingService()


async def _price_all_tenants() -> dict:
    """Run dynamic pricing across all active tenants."""
    total_suggestions = 0

    async with get_global_db() as db:
        schemas = await db.fetch(
            "SELECT schema_name FROM af_global.organizations WHERE status = 'active'"
        )

    for row in schemas:
        try:
            suggestions = await pricing_svc.ai_suggest_prices(
                studio_id="all",
                schema_override=row["schema_name"],
            )
            total_suggestions += len(suggestions)
        except Exception as e:
            logger.error(
                "Dynamic pricing failed for tenant",
                schema=row["schema_name"],
                error=str(e),
            )

    return {"total_suggestions": total_suggestions}


@app.task(name="app.workers.tasks.dynamic_pricing.nightly_dynamic_pricing")
def nightly_dynamic_pricing():
    """Celery task: nightly AI pricing suggestions for all tenants."""
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_price_all_tenants())
        logger.info(
            "Nightly pricing complete",
            suggestions=result["total_suggestions"],
        )
        return result
    finally:
        loop.close()
