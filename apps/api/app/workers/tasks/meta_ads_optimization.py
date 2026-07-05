"""AuraFlow — Meta/Facebook Ads Optimization Tasks

Celery tasks for:
- Hourly metrics sync from Meta Insights → local DB
- AI optimization cycle (4x daily)
- Daily CAPI conversion uploads
- Budget safety checks (every 4 hours)

Schedules are offset from Google Ads tasks to avoid overlap.
"""
import asyncio
import json
from datetime import datetime, timezone, timedelta

from app.core.logging import logger
from app.db.session import get_tenant_db, get_global_db
from app.services.ads.meta_ads_service import MetaAdsService
from app.services.ads.ai_meta_ads_controller import AIMetaAdsController
from app.workers.celery_app import app

_meta = MetaAdsService()
_ai = AIMetaAdsController()


async def _get_active_meta_ads_tenants() -> list[dict]:
    """Get all tenants that have Meta Ads connected and active."""
    async with get_global_db() as db:
        rows = await db.fetch(
            """
            SELECT o.id AS org_id, o.schema_name
            FROM af_global.organizations o
            WHERE o.status IN ('active', 'trial')
              AND o.meta_ad_account_id IS NOT NULL
              AND o.meta_access_token_encrypted IS NOT NULL
            """
        )
    return [{"org_id": str(r["org_id"]), "schema_name": r["schema_name"]} for r in rows]


async def _is_meta_ads_active_for_tenant(schema_name: str) -> bool:
    """Check if meta ads config is_active for a tenant."""
    async with get_tenant_db(schema_override=schema_name) as db:
        row = await db.fetchrow("SELECT is_active FROM meta_ads_config LIMIT 1")
    return bool(row and row["is_active"])


# ── Task 1: Sync Metrics ─────────────────────────────────────────────────────

async def _sync_metrics_all():
    """Pull yesterday's + today's metrics from Meta Insights for all active tenants."""
    tenants = await _get_active_meta_ads_tenants()
    now = datetime.now(timezone.utc)
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    today = now.strftime("%Y-%m-%d")
    total_synced = 0

    for tenant in tenants:
        try:
            if not await _is_meta_ads_active_for_tenant(tenant["schema_name"]):
                continue
            synced = await _meta.sync_performance_metrics(tenant["org_id"], yesterday)
            synced += await _meta.sync_performance_metrics(tenant["org_id"], today)
            total_synced += synced
        except Exception as e:
            logger.error(
                "Meta Ads metrics sync failed",
                org_id=tenant["org_id"],
                schema=tenant["schema_name"],
                error=str(e),
            )
    return total_synced


@app.task(name="app.workers.tasks.meta_ads_optimization.sync_meta_ads_metrics")
def sync_meta_ads_metrics():
    """Celery task: sync Meta Ads metrics for all active tenants."""
    loop = asyncio.new_event_loop()
    try:
        total = loop.run_until_complete(_sync_metrics_all())
        if total > 0:
            logger.info("Meta Ads metrics synced", total=total)
        return {"synced": total}
    finally:
        loop.close()


# ── Task 2: AI Optimization ──────────────────────────────────────────────────

async def _run_optimization_all():
    """Run AI optimization cycle for all active tenants."""
    tenants = await _get_active_meta_ads_tenants()
    results = []

    for tenant in tenants:
        try:
            if not await _is_meta_ads_active_for_tenant(tenant["schema_name"]):
                continue
            result = await _ai.run_optimization_cycle(tenant["org_id"])
            results.append({
                "org_id": tenant["org_id"],
                "actions": len(result.get("actions", [])),
                "completed": result.get("completed", False),
            })
            logger.info(
                "AI Meta optimization complete for tenant",
                org_id=tenant["org_id"],
                actions=len(result.get("actions", [])),
            )
        except Exception as e:
            logger.error(
                "AI Meta optimization failed",
                org_id=tenant["org_id"],
                error=str(e),
            )
            results.append({"org_id": tenant["org_id"], "error": str(e)})

    return results


@app.task(name="app.workers.tasks.meta_ads_optimization.run_meta_ai_optimization")
def run_meta_ai_optimization():
    """Celery task: run AI optimization cycle for all active tenants."""
    loop = asyncio.new_event_loop()
    try:
        results = loop.run_until_complete(_run_optimization_all())
        return {"tenants_processed": len(results), "results": results}
    finally:
        loop.close()


# ── Task 3: Upload Conversions via CAPI ──────────────────────────────────────

async def _upload_conversions_all():
    """Upload pending conversions via Meta Conversions API for all tenants."""
    tenants = await _get_active_meta_ads_tenants()
    total_uploaded = 0

    for tenant in tenants:
        try:
            if not await _is_meta_ads_active_for_tenant(tenant["schema_name"]):
                continue

            # Get pixel ID from config
            async with get_tenant_db(schema_override=tenant["schema_name"]) as db:
                config = await db.fetchrow("SELECT meta_pixel_id FROM meta_ads_config LIMIT 1")
                if not config or not config["meta_pixel_id"]:
                    continue
                pixel_id = config["meta_pixel_id"]

                rows = await db.fetch(
                    """
                    SELECT id, conversion_type, event_name, fbclid, fbc, fbp,
                           email_hash, phone_hash, conversion_value_cents,
                           event_id, created_at
                    FROM meta_ads_conversions
                    WHERE reported_to_meta = FALSE
                    ORDER BY created_at ASC
                    LIMIT 200
                    """
                )

            if not rows:
                continue

            # Build CAPI events
            events = []
            for r in rows:
                user_data = {}
                if r["email_hash"]:
                    user_data["em"] = [r["email_hash"]]
                if r["phone_hash"]:
                    user_data["ph"] = [r["phone_hash"]]
                if r["fbc"]:
                    user_data["fbc"] = r["fbc"]
                if r["fbp"]:
                    user_data["fbp"] = r["fbp"]
                if r["fbclid"]:
                    user_data["fbclid"] = r["fbclid"]

                event = {
                    "event_name": r["event_name"],
                    "event_time": int(r["created_at"].timestamp()),
                    "event_id": r["event_id"],
                    "action_source": "website",
                    "user_data": user_data,
                }
                if r["conversion_value_cents"]:
                    event["custom_data"] = {
                        "value": r["conversion_value_cents"] / 100,
                        "currency": "USD",
                    }
                events.append(event)

            result = await _meta.send_conversion_events(tenant["org_id"], pixel_id, events)

            if result.get("uploaded", 0) > 0:
                ids = [str(r["id"]) for r in rows]
                async with get_tenant_db(schema_override=tenant["schema_name"]) as db:
                    await db.execute(
                        "UPDATE meta_ads_conversions SET reported_to_meta = TRUE, reported_at = NOW() WHERE id = ANY($1::uuid[])",
                        ids,
                    )
                total_uploaded += result["uploaded"]

        except Exception as e:
            logger.error(
                "Meta CAPI upload failed for tenant",
                org_id=tenant["org_id"],
                error=str(e),
            )

    return total_uploaded


@app.task(name="app.workers.tasks.meta_ads_optimization.upload_meta_conversions")
def upload_meta_conversions():
    """Celery task: upload conversions via Meta Conversions API."""
    loop = asyncio.new_event_loop()
    try:
        total = loop.run_until_complete(_upload_conversions_all())
        if total > 0:
            logger.info("Meta CAPI conversions uploaded", total=total)
        return {"uploaded": total}
    finally:
        loop.close()


# ── Task 4: Budget Safety Check ──────────────────────────────────────────────

async def _check_budgets_all():
    """Check monthly budget caps and auto-pause campaigns at 95%."""
    tenants = await _get_active_meta_ads_tenants()
    paused = 0

    for tenant in tenants:
        try:
            if not await _is_meta_ads_active_for_tenant(tenant["schema_name"]):
                continue

            budget = await _meta.check_budget_remaining(tenant["org_id"])

            if budget.get("utilization_pct", 0) >= 95:
                count = await _meta.pause_all_campaigns(tenant["org_id"])
                paused += count

                await _meta.log_ai_action(
                    action_type="budget_auto_pause",
                    description=f"Auto-paused {count} campaigns — monthly spend at {budget['utilization_pct']}% of cap",
                    reasoning=f"Spent ${budget['spent_cents'] / 100:.2f} of ${budget['max_monthly_cents'] / 100:.2f} monthly cap",
                    changes={"campaigns_paused": count, "budget": budget},
                )

                logger.warning(
                    "Meta budget cap reached — campaigns auto-paused",
                    org_id=tenant["org_id"],
                    utilization=budget["utilization_pct"],
                    campaigns_paused=count,
                )
        except Exception as e:
            logger.error(
                "Meta budget check failed",
                org_id=tenant["org_id"],
                error=str(e),
            )

    return paused


@app.task(name="app.workers.tasks.meta_ads_optimization.meta_monthly_budget_check")
def meta_monthly_budget_check():
    """Celery task: check Meta Ads budgets and auto-pause at 95%."""
    loop = asyncio.new_event_loop()
    try:
        paused = loop.run_until_complete(_check_budgets_all())
        return {"campaigns_paused": paused}
    finally:
        loop.close()
