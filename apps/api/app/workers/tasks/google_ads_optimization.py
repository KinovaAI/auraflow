"""AuraFlow — Google Ads Optimization Tasks

Celery tasks for:
- Hourly metrics sync from Google Ads → local DB
- AI optimization cycle (4x daily)
- Daily offline conversion uploads
- Budget safety checks (every 4 hours)
"""
import asyncio
from datetime import datetime, timezone, timedelta

from app.core.logging import logger
from app.db.session import get_tenant_db, get_global_db
from app.services.ads.google_ads_service import GoogleAdsService
from app.services.ads.ai_ads_controller import AIAdsController
from app.workers.celery_app import app

_ads = GoogleAdsService()
_ai = AIAdsController()


async def _get_active_google_ads_tenants() -> list[dict]:
    """Get all tenants that have Google Ads connected and active."""
    async with get_global_db() as db:
        rows = await db.fetch(
            """
            SELECT o.id AS org_id, o.schema_name
            FROM af_global.organizations o
            WHERE o.status IN ('active', 'trial')
              AND o.google_ads_customer_id IS NOT NULL
              AND o.google_ads_refresh_token_encrypted IS NOT NULL
            """
        )
    return [{"org_id": str(r["org_id"]), "schema_name": r["schema_name"]} for r in rows]


async def _is_ads_active_for_tenant(schema_name: str) -> bool:
    """Check if google ads config is_active for a tenant."""
    async with get_tenant_db(schema_override=schema_name) as db:
        row = await db.fetchrow("SELECT is_active FROM google_ads_config LIMIT 1")
    return bool(row and row["is_active"])


# ── Task 1: Sync Metrics ─────────────────────────────────────────────────────

async def _sync_metrics_all():
    """Pull yesterday's + today's metrics from Google Ads for all active tenants."""
    tenants = await _get_active_google_ads_tenants()
    now = datetime.now(timezone.utc)
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    today = now.strftime("%Y-%m-%d")
    total_synced = 0

    for tenant in tenants:
        try:
            if not await _is_ads_active_for_tenant(tenant["schema_name"]):
                continue
            # Sync yesterday (final numbers) and today (running totals)
            synced = await _ads.sync_performance_metrics(tenant["org_id"], yesterday)
            synced += await _ads.sync_performance_metrics(tenant["org_id"], today)
            total_synced += synced
        except Exception as e:
            logger.error(
                "Google Ads metrics sync failed",
                org_id=tenant["org_id"],
                schema=tenant["schema_name"],
                error=str(e),
            )
    return total_synced


@app.task(name="app.workers.tasks.google_ads_optimization.sync_google_ads_metrics")
def sync_google_ads_metrics():
    """Celery task: sync Google Ads metrics for all active tenants."""
    loop = asyncio.new_event_loop()
    try:
        total = loop.run_until_complete(_sync_metrics_all())
        if total > 0:
            logger.info("Google Ads metrics synced", total=total)
        return {"synced": total}
    finally:
        loop.close()


# ── Task 2: AI Optimization ──────────────────────────────────────────────────

async def _run_optimization_all():
    """Run AI optimization cycle for all active tenants."""
    tenants = await _get_active_google_ads_tenants()
    results = []

    for tenant in tenants:
        try:
            if not await _is_ads_active_for_tenant(tenant["schema_name"]):
                continue
            result = await _ai.run_optimization_cycle(tenant["org_id"])
            results.append({
                "org_id": tenant["org_id"],
                "actions": len(result.get("actions", [])),
                "completed": result.get("completed", False),
            })
            logger.info(
                "AI optimization complete for tenant",
                org_id=tenant["org_id"],
                actions=len(result.get("actions", [])),
            )
        except Exception as e:
            logger.error(
                "AI optimization failed",
                org_id=tenant["org_id"],
                error=str(e),
            )
            results.append({"org_id": tenant["org_id"], "error": str(e)})

    return results


@app.task(name="app.workers.tasks.google_ads_optimization.run_ai_optimization")
def run_ai_optimization():
    """Celery task: run AI optimization cycle for all active tenants."""
    loop = asyncio.new_event_loop()
    try:
        results = loop.run_until_complete(_run_optimization_all())
        return {"tenants_processed": len(results), "results": results}
    finally:
        loop.close()


# ── Task 3: Upload Conversions ────────────────────────────────────────────────

async def _upload_conversions_all():
    """Upload pending offline conversions to Google Ads for all tenants."""
    tenants = await _get_active_google_ads_tenants()
    total_uploaded = 0

    for tenant in tenants:
        try:
            if not await _is_ads_active_for_tenant(tenant["schema_name"]):
                continue

            async with get_tenant_db(schema_override=tenant["schema_name"]) as db:
                rows = await db.fetch(
                    """
                    SELECT id, gclid, conversion_type, conversion_value_cents, created_at
                    FROM google_ads_conversions
                    WHERE reported_to_google = FALSE
                      AND gclid IS NOT NULL
                    ORDER BY created_at ASC
                    LIMIT 200
                    """
                )

            if not rows:
                continue

            # Build conversion objects
            conversions = []
            for r in rows:
                conv_type = r["conversion_type"]
                # Map to conversion action resource (would be stored in config in production)
                conversions.append({
                    "gclid": r["gclid"],
                    "conversion_action_resource": f"customers/0/conversionActions/{conv_type}",
                    "conversion_datetime": r["created_at"].strftime("%Y-%m-%d %H:%M:%S+00:00"),
                    "conversion_value": r["conversion_value_cents"] / 100 if r["conversion_value_cents"] else 0,
                })

            result = await _ads.upload_offline_conversions(tenant["org_id"], conversions)

            if result.get("uploaded", 0) > 0:
                # Mark as reported
                ids = [str(r["id"]) for r in rows]
                async with get_tenant_db(schema_override=tenant["schema_name"]) as db:
                    await db.execute(
                        f"UPDATE google_ads_conversions SET reported_to_google = TRUE WHERE id = ANY($1::uuid[])",
                        ids,
                    )
                total_uploaded += result["uploaded"]

        except Exception as e:
            logger.error(
                "Conversion upload failed for tenant",
                org_id=tenant["org_id"],
                error=str(e),
            )

    return total_uploaded


@app.task(name="app.workers.tasks.google_ads_optimization.upload_conversions")
def upload_conversions():
    """Celery task: upload offline conversions to Google Ads."""
    loop = asyncio.new_event_loop()
    try:
        total = loop.run_until_complete(_upload_conversions_all())
        if total > 0:
            logger.info("Offline conversions uploaded", total=total)
        return {"uploaded": total}
    finally:
        loop.close()


# ── Task 4: Budget Safety Check ──────────────────────────────────────────────

async def _check_budgets_all():
    """Check monthly budget caps and auto-pause campaigns at 95%."""
    tenants = await _get_active_google_ads_tenants()
    paused = 0

    for tenant in tenants:
        try:
            if not await _is_ads_active_for_tenant(tenant["schema_name"]):
                continue

            budget = await _ads.check_budget_remaining(tenant["org_id"])

            if budget.get("utilization_pct", 0) >= 95:
                count = await _ads.pause_all_campaigns(tenant["org_id"])
                paused += count

                # Log the auto-pause
                await _ads.log_ai_action(
                    action_type="budget_auto_pause",
                    description=f"Auto-paused {count} campaigns — monthly spend at {budget['utilization_pct']}% of cap",
                    reasoning=f"Spent ${budget['spent_cents'] / 100:.2f} of ${budget['max_monthly_cents'] / 100:.2f} monthly cap",
                    changes={"campaigns_paused": count, "budget": budget},
                )

                logger.warning(
                    "Budget cap reached — campaigns auto-paused",
                    org_id=tenant["org_id"],
                    utilization=budget["utilization_pct"],
                    campaigns_paused=count,
                )
        except Exception as e:
            logger.error(
                "Budget check failed",
                org_id=tenant["org_id"],
                error=str(e),
            )

    return paused


@app.task(name="app.workers.tasks.google_ads_optimization.monthly_budget_check")
def monthly_budget_check():
    """Celery task: check budgets and auto-pause at 95%."""
    loop = asyncio.new_event_loop()
    try:
        paused = loop.run_until_complete(_check_budgets_all())
        return {"campaigns_paused": paused}
    finally:
        loop.close()
