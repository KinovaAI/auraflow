"""AuraFlow — AI Token Overage Computation

Pure computation: sums tokens from af_global.ai_token_usage for a
date range, applies the free tier + rate from platform_settings, and
returns the overage in cents.

This is the "self-managed token counter" that replaces Stripe Billing
Meters for square-mode orgs (Don's spec). The numbers it returns get
written as a line item on the monthly Square Invoice (Phase 8 runner).

No external API calls. No mutation. Safe to call from dashboards as
many times as you like — the per-period math is cheap.
"""
import json
from datetime import date
from typing import Optional

from app.core.logging import logger
from app.db.session import get_global_db


_DEFAULT_FREE_TIER = 50000
_DEFAULT_RATE_CENTS_PER_1K = 3.0


async def _get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    """Read a platform_settings JSONB value as a plain string. Falls
    back to `default` if missing."""
    async with get_global_db() as db:
        row = await db.fetchrow(
            "SELECT value FROM af_global.platform_settings WHERE key = $1", key,
        )
    if not row:
        return default
    val = row["value"]
    if isinstance(val, str):
        s = val.strip('"')
        return s if s and s.lower() != "null" else default
    if val is None:
        return default
    return json.dumps(val) if not isinstance(val, str) else val


async def _free_tier() -> int:
    raw = await _get_setting("ai_token_free_tier", str(_DEFAULT_FREE_TIER))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_FREE_TIER


async def _rate_cents_per_1k() -> float:
    raw = await _get_setting(
        "ai_token_rate_cents_per_1k", str(_DEFAULT_RATE_CENTS_PER_1K),
    )
    try:
        return float(raw)
    except (TypeError, ValueError):
        return _DEFAULT_RATE_CENTS_PER_1K


async def compute_period_overage(
    organization_id: str,
    period_start: date,
    period_end: date,
) -> dict:
    """Sum tokens for an org in [period_start, period_end) and apply
    free_tier + rate. Returns:

      {
        "total_tokens": int,
        "billable_tokens": int,   # max(0, total - free_tier)
        "free_tier": int,
        "rate_cents_per_1k": float,
        "overage_cents": int,     # round(billable * rate / 1000)
      }
    """
    async with get_global_db() as db:
        row = await db.fetchrow(
            """
            SELECT COALESCE(SUM(total_tokens), 0)::bigint AS tokens
            FROM af_global.ai_token_usage
            WHERE organization_id = $1
              AND created_at >= $2::date
              AND created_at <  $3::date
            """,
            organization_id, period_start, period_end,
        )
    total = int(row["tokens"]) if row else 0
    free_tier = await _free_tier()
    rate = await _rate_cents_per_1k()
    billable = max(0, total - free_tier)
    overage_cents = int(round((billable * rate) / 1000))
    return {
        "total_tokens": total,
        "billable_tokens": billable,
        "free_tier": free_tier,
        "rate_cents_per_1k": rate,
        "overage_cents": overage_cents,
    }
