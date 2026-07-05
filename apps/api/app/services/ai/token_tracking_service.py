"""AuraFlow — AI Token Tracking Service

Centralized token usage tracking + Stripe Billing Meter reporting.
Every AI service calls track_ai_usage() after a Claude API response.
Usage is stored locally in af_global.ai_token_usage AND reported to
Stripe Billing Meters for automated invoicing.
"""
import asyncio
from datetime import datetime, timezone
from typing import Optional

from app.core.config import settings
from app.core.logging import logger
from app.core.tenant_context import get_tenant_context
from app.db.session import get_global_db


class TokenTrackingService:

    async def track_ai_usage(
        self,
        service_name: str,
        function_name: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        organization_id: Optional[str] = None,
    ) -> Optional[dict]:
        """Record token usage locally and report to Stripe Billing Meter."""
        org_id = organization_id
        if not org_id:
            ctx = get_tenant_context()
            if ctx:
                org_id = ctx.organization_id
        if not org_id:
            logger.warning("Cannot track AI usage — no organization context")
            return None

        total_tokens = input_tokens + output_tokens

        try:
            async with get_global_db() as db:
                row = await db.fetchrow(
                    """
                    INSERT INTO af_global.ai_token_usage
                        (organization_id, service_name, function_name, model,
                         input_tokens, output_tokens, total_tokens)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    RETURNING id
                    """,
                    org_id, service_name, function_name, model,
                    input_tokens, output_tokens, total_tokens,
                )
            usage_id = str(row["id"]) if row else None
        except Exception as e:
            logger.error("Failed to record AI usage", error=str(e))
            return None

        # Report to Stripe (was fire-and-forget — produced
        # `Task was destroyed but it is pending!` + `aclose(): asynchronous
        # generator is already running` on every Celery `_run_async` tick
        # because the orphan task outlived the per-tick event loop. Now
        # awaited inline; ~200ms added to track_ai_usage but Celery workers
        # don't need micro-latency, and Stripe Billing Meter ingestion no
        # longer silently drops.
        try:
            await self._report_to_stripe_meter(org_id, total_tokens, usage_id)
        except Exception as e:
            logger.error("Stripe meter reporting failed", error=str(e))

        return {"id": usage_id, "total_tokens": total_tokens}

    async def _report_to_stripe_meter(
        self, org_id: str, total_tokens: int, usage_id: Optional[str]
    ) -> None:
        """Report usage to Stripe Billing Meter. Best-effort, non-blocking.

        Square-mode orgs skip this entirely — their token billing is
        handled by the platform billing run, which reads the same
        ai_token_usage rows. Calling Stripe for a square-mode org would
        double-bill, so the very first check below short-circuits.
        """
        try:
            if not settings.STRIPE_SECRET_KEY:
                return

            billing_enabled = await self._get_setting("ai_token_billing_enabled")
            if billing_enabled != "true":
                return

            async with get_global_db() as db:
                row = await db.fetchrow(
                    """
                    SELECT stripe_customer_id, billing_provider
                    FROM af_global.organizations WHERE id = $1
                    """,
                    org_id,
                )
            if not row:
                return
            # Skip Stripe meter for square-mode orgs — their token
            # usage is invoiced via the platform billing run.
            if (row.get("billing_provider") or "stripe").lower() == "square":
                return
            if not row["stripe_customer_id"]:
                return

            meter_id = await self._get_setting("ai_token_stripe_meter_id")
            if not meter_id or meter_id == "null":
                return

            import stripe
            stripe.api_key = settings.STRIPE_SECRET_KEY

            event = await asyncio.to_thread(
                lambda: stripe.billing.MeterEvent.create(
                    event_name="ai_tokens",
                    payload={
                        "value": str(total_tokens),
                        "stripe_customer_id": row["stripe_customer_id"],
                    },
                )
            )

            if usage_id and event:
                async with get_global_db() as db:
                    await db.execute(
                        "UPDATE af_global.ai_token_usage SET stripe_meter_event_id = $1 WHERE id = $2::uuid",
                        getattr(event, "id", str(event)), usage_id,
                    )
        except Exception as e:
            logger.error("Failed to report AI usage to Stripe", org_id=org_id, error=str(e))

    async def _get_setting(self, key: str) -> Optional[str]:
        async with get_global_db() as db:
            row = await db.fetchrow(
                "SELECT value FROM af_global.platform_settings WHERE key = $1", key
            )
        if row:
            val = row["value"]
            if isinstance(val, str):
                return val.strip('"')
            if isinstance(val, bool):
                return "true" if val else "false"
            return str(val)
        return None

    # ── Usage Queries (for dashboard) ───────────────────────────────────

    async def get_org_usage_current_period(self, org_id: str) -> dict:
        """Get token usage for the current billing month."""
        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT
                    COALESCE(SUM(total_tokens), 0)  AS total_tokens,
                    COALESCE(SUM(input_tokens), 0)  AS input_tokens,
                    COALESCE(SUM(output_tokens), 0) AS output_tokens,
                    COUNT(*)                         AS api_call_count
                FROM af_global.ai_token_usage
                WHERE organization_id = $1
                  AND created_at >= date_trunc('month', NOW())
                """,
                org_id,
            )

        total = row["total_tokens"]
        free_tier = int(await self._get_setting("ai_token_free_tier") or 50000)
        rate = float(await self._get_setting("ai_token_rate_cents_per_1k") or 3.0)
        billable = max(0, total - free_tier)
        cost_cents = int((billable * rate) / 1000)

        return {
            "period_start": datetime.now(timezone.utc).replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            ).isoformat(),
            "total_tokens": total,
            "input_tokens": row["input_tokens"],
            "output_tokens": row["output_tokens"],
            "api_call_count": row["api_call_count"],
            "free_tier_limit": free_tier,
            "free_tier_remaining": max(0, free_tier - total),
            "billable_tokens": billable,
            "rate_cents_per_1k": rate,
            "estimated_cost_cents": cost_cents,
            "estimated_cost_display": f"${cost_cents / 100:.2f}",
        }

    async def get_org_usage_by_service(self, org_id: str, days: int = 30) -> list[dict]:
        async with get_global_db() as db:
            rows = await db.fetch(
                """
                SELECT service_name,
                       SUM(total_tokens) AS total_tokens,
                       SUM(input_tokens) AS input_tokens,
                       SUM(output_tokens) AS output_tokens,
                       COUNT(*) AS call_count
                FROM af_global.ai_token_usage
                WHERE organization_id = $1
                  AND created_at >= NOW() - ($2 || ' days')::interval
                GROUP BY service_name
                ORDER BY total_tokens DESC
                """,
                org_id, str(days),
            )
        return [dict(r) for r in rows]

    async def get_org_usage_daily(self, org_id: str, days: int = 30) -> list[dict]:
        async with get_global_db() as db:
            rows = await db.fetch(
                """
                SELECT date_trunc('day', created_at) AS day,
                       SUM(total_tokens) AS total_tokens,
                       COUNT(*) AS call_count
                FROM af_global.ai_token_usage
                WHERE organization_id = $1
                  AND created_at >= NOW() - ($2 || ' days')::interval
                GROUP BY day ORDER BY day ASC
                """,
                org_id, str(days),
            )
        return [
            {"date": r["day"].isoformat() if r["day"] else None,
             "total_tokens": r["total_tokens"],
             "call_count": r["call_count"]}
            for r in rows
        ]

    async def get_all_orgs_usage(self) -> list[dict]:
        async with get_global_db() as db:
            rows = await db.fetch(
                """
                SELECT o.id, o.name, o.slug,
                       COALESCE(SUM(u.total_tokens), 0) AS total_tokens,
                       COUNT(u.id) AS call_count
                FROM af_global.organizations o
                LEFT JOIN af_global.ai_token_usage u
                    ON u.organization_id = o.id
                    AND u.created_at >= date_trunc('month', NOW())
                WHERE o.status IN ('active', 'trial')
                GROUP BY o.id, o.name, o.slug
                ORDER BY total_tokens DESC
                """,
            )
        return [dict(r) for r in rows]

    async def get_billing_settings(self) -> dict:
        async with get_global_db() as db:
            rows = await db.fetch(
                "SELECT key, value, description FROM af_global.platform_settings WHERE key LIKE 'ai_token_%'"
            )
        return {r["key"]: {"value": r["value"], "description": r["description"]} for r in rows}


# Singleton + convenience function
_tracker = TokenTrackingService()


async def track_ai_usage(
    service_name: str,
    function_name: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    organization_id: Optional[str] = None,
) -> Optional[dict]:
    return await _tracker.track_ai_usage(
        service_name=service_name,
        function_name=function_name,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        organization_id=organization_id,
    )
