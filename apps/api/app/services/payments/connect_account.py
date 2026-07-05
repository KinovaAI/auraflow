"""AuraFlow — Stripe Connect account resolution chokepoint.

THE RULE (load-bearing for white-label payment safety):
    The `stripe_account_id` parameter passed to any Stripe API call
    MUST be derived server-side from the authenticated request's
    tenant context (JWT.org_slug or api_key.org_id) by reading
    af_global.organizations.stripe_account_id.

    It MUST NEVER be:
      - read from a request body
      - read from a query parameter
      - read from a header
      - read from a path parameter chosen by the client

This file is the only function the rest of the codebase should call
to obtain a `stripe_account_id`. Direct DB SELECTs for this column
elsewhere are a red flag — replace them with this helper. The pytest
contract in tests/test_stripe_connect_isolation.py pins the rule.

Why this matters: a tenant_A's portal that could specify any
stripe_account_id in a request body could route payments to tenant_B's
connected account. Server-side derivation is the only defense.
"""
from typing import Optional
from uuid import UUID

from app.core.logging import logger
from app.db.session import get_global_db


# In-process cache: org_id → stripe_account_id (or None). 60s TTL.
# Stripe Connect account assignment changes rarely (onboarding event +
# manual updates only); 60s is fine. Webhook handler invalidates on
# account.updated to keep the freshness story honest.
import time as _time
_CACHE: dict[str, tuple[float, Optional[str]]] = {}
_TTL = 60.0


async def resolve_stripe_account_for_org(org_id: str | UUID) -> Optional[str]:
    """Look up the Stripe Connect account_id for a tenant.

    Returns the `acct_*` ID (test or live) configured on
    af_global.organizations.stripe_account_id. Returns None if the
    tenant hasn't completed Connect onboarding yet — callers should
    treat that as "Connect not enabled" and fall back to direct-charge
    mode (the platform takes the funds, no application_fee_amount).

    Most callers will want to also confirm `stripe_charges_enabled`
    is True before initiating any charge — see resolve_connect_status.
    """
    key = str(org_id)
    now = _time.monotonic()
    cached = _CACHE.get(key)
    if cached and (now - cached[0]) < _TTL:
        return cached[1]

    async with get_global_db() as db:
        row = await db.fetchrow(
            "SELECT stripe_account_id FROM af_global.organizations WHERE id = $1",
            key,
        )
    val = row["stripe_account_id"] if row else None
    _CACHE[key] = (now, val)
    return val


async def resolve_connect_status(org_id: str | UUID) -> dict:
    """Fetch full Connect status for a tenant.

    Returns: {
        "stripe_account_id":      str | None,
        "charges_enabled":        bool,
        "payouts_enabled":        bool,
        "ready_for_charges":      bool,   # account_id present AND charges_enabled
    }
    """
    async with get_global_db() as db:
        row = await db.fetchrow(
            """
            SELECT stripe_account_id, stripe_charges_enabled, stripe_payouts_enabled
            FROM af_global.organizations WHERE id = $1
            """,
            str(org_id),
        )
    if not row:
        return {
            "stripe_account_id": None,
            "charges_enabled": False,
            "payouts_enabled": False,
            "ready_for_charges": False,
        }
    acct = row["stripe_account_id"]
    ce = bool(row["stripe_charges_enabled"])
    pe = bool(row["stripe_payouts_enabled"])
    return {
        "stripe_account_id": acct,
        "charges_enabled": ce,
        "payouts_enabled": pe,
        "ready_for_charges": bool(acct) and ce,
    }


def invalidate_cache(org_id: str | UUID) -> None:
    """Drop the cached account-id for one tenant. Called by the webhook
    handler when an account.updated event arrives, so freshly-completed
    onboardings (or revocations) are visible immediately instead of
    waiting for the 60s TTL."""
    _CACHE.pop(str(org_id), None)


def invalidate_all() -> None:
    """Nuke the whole cache. For tests + admin tooling."""
    _CACHE.clear()


# Sanity assert the rule on import — catches a future refactor that tries
# to add a `stripe_account_id` parameter to this module's public API.
def _module_sanity() -> None:
    import inspect
    for name, fn in [
        ("resolve_stripe_account_for_org", resolve_stripe_account_for_org),
        ("resolve_connect_status", resolve_connect_status),
    ]:
        sig = inspect.signature(fn)
        params = list(sig.parameters)
        if params != ["org_id"]:
            raise RuntimeError(
                f"connect_account.{name} signature drift: expected ['org_id'], got {params}. "
                "This module is a security chokepoint — adding parameters here is a red flag."
            )

_module_sanity()
