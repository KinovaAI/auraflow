"""AuraFlow — Subscription Reconciliation Task

Compares local member_memberships.status against Stripe's source-of-truth
subscription status. Webhook delivery isn't 100% — outages, dropped events,
and partial failures cause local state to drift away from Stripe over time.

Without this task, members like Melodee Morse, Holly Maddox, Joan Claassen,
and Anna Marie Gonzalez get stranded: Stripe is happily charging them but
their local membership shows expired/cancelled, blocking bookings.

Scope: only memberships with a stripe_subscription_id. One-time pack
purchases are unaffected by this drift class.

Cadence: hourly. Most drift gets caught in the first hour after a webhook
miss; running more often is overkill, less often risks a member being
locked out longer than they should be.
"""
import asyncio
from typing import Optional

import stripe

from app.core.logging import logger
from app.db.session import get_global_db, get_tenant_db
from app.core.tenant_context import set_tenant_context_from_schema, clear_tenant_context
from app.workers.celery_app import app


# Map Stripe subscription status -> local membership status
_STRIPE_TO_LOCAL_STATUS = {
    "active": "active",
    "trialing": "active",
    "past_due": "past_due",
    "canceled": "cancelled",
    "incomplete": "past_due",
    "incomplete_expired": "expired",
    "unpaid": "past_due",
    "paused": "frozen",
}


async def _get_stripe_key(org_id: str) -> tuple[str, Optional[str]]:
    """Resolve (api_key, stripe_account_id) for an org. Direct-mode orgs
    use their own key with no Connect account; Connect orgs use the
    platform key with stripe_account header.
    """
    from app.services.payments.stripe_service import _get_org_stripe_key
    from app.core.config import settings

    direct_key = await _get_org_stripe_key(org_id)
    if direct_key:
        return direct_key, None

    async with get_global_db() as db:
        row = await db.fetchrow(
            "SELECT stripe_account_id FROM af_global.organizations WHERE id = $1",
            org_id,
        )
    return settings.STRIPE_SECRET_KEY, (row["stripe_account_id"] if row else None)


async def _reconcile_one(
    schema: str,
    org_id: str,
    api_key: str,
    stripe_account_id: Optional[str],
    membership_id: str,
    sub_id: str,
    local_status: str,
) -> Optional[dict]:
    """Fetch one Stripe subscription and update the local row if status
    drifted. Returns a drift record on change, None on no-op.
    """
    kwargs: dict = {}
    if stripe_account_id:
        kwargs["stripe_account"] = stripe_account_id
    try:
        sub = await asyncio.to_thread(
            lambda: stripe.Subscription.retrieve(sub_id, api_key=api_key, **kwargs)
        )
    except stripe.error.InvalidRequestError as e:
        # Subscription no longer exists on Stripe — treat as cancelled.
        if "No such subscription" in str(e):
            mapped = "cancelled"
        else:
            logger.warning("Stripe sub fetch failed", sub_id=sub_id, error=str(e))
            return None
    except Exception as e:
        logger.warning("Stripe sub fetch failed", sub_id=sub_id, error=str(e))
        return None
    else:
        # Stripe reports status='active' even when pause_collection is
        # set — the sub still exists, billing is just suppressed. If we
        # naively map that to local 'active' we undo a member freeze.
        # Detect pause_collection and treat as 'frozen' so a manually
        # paused sub stays paused locally too. Without this the
        # reconcile worker flipped Anna Marie's row back to active
        # after her 5/07 freeze and she got billed again on 5/10.
        if getattr(sub, "pause_collection", None):
            mapped = "frozen"
        else:
            mapped = _STRIPE_TO_LOCAL_STATUS.get(sub.status)
        if not mapped:
            logger.warning("Unknown Stripe subscription status",
                           sub_id=sub_id, stripe_status=sub.status)
            return None

    if mapped == local_status:
        return None

    # Never auto-unfreeze. Freezes are an intentional staff action; if
    # Stripe somehow reports active for a row marked frozen locally we
    # leave the local row alone and surface a warning so ops can
    # investigate (e.g. someone removed pause_collection by hand in the
    # Stripe Dashboard). The unfreeze flow is the only path that should
    # flip frozen → active.
    if local_status == "frozen" and mapped == "active":
        logger.warning(
            "Subscription reconciliation: Stripe is active for a locally-frozen membership — not auto-unfreezing",
            schema=schema, membership_id=membership_id, sub_id=sub_id,
        )
        return None

    async with get_tenant_db(schema_override=schema) as db:
        await db.execute(
            """
            UPDATE member_memberships
            SET status = $1,
                updated_at = NOW()
            WHERE id = $2
            """,
            mapped, membership_id,
        )
    logger.info(
        "Subscription reconciliation: status drift fixed",
        schema=schema, membership_id=membership_id, sub_id=sub_id,
        from_status=local_status, to_status=mapped,
    )
    return {
        "membership_id": membership_id,
        "sub_id": sub_id,
        "from": local_status,
        "to": mapped,
    }


async def _reconcile_one_square(
    schema: str,
    merchant_access_token: str,
    membership_id: str,
    sub_id: str,
    local_status: str,
) -> Optional[dict]:
    """Square equivalent of _reconcile_one. Pulls the subscription from
    Square via the merchant's OAuth token and reconciles drift.

    Square subscription statuses:
      ACTIVE | PAUSED | DEACTIVATED | CANCELED | PENDING

    Honors feedback_freeze_one_way: never auto-unfreeze. If Square
    reports ACTIVE for a locally-frozen membership we log + skip.
    """
    from app.services.payments.square_service import square_service
    try:
        sub = await square_service.get_subscription(
            merchant_access_token=merchant_access_token,
            subscription_id=sub_id,
        )
    except Exception as e:
        logger.warning("Square sub fetch failed", sub_id=sub_id, error=str(e))
        return None

    if sub is None:
        # Subscription no longer exists on Square — treat as cancelled.
        mapped = "cancelled"
    else:
        status = (sub.get("status") or "").upper()
        mapped = {
            "ACTIVE": "active",
            "PENDING": "active",
            "PAUSED": "frozen",
            "DEACTIVATED": "cancelled",
            "CANCELED": "cancelled",
        }.get(status)
        if not mapped:
            logger.warning("Unknown Square subscription status",
                           sub_id=sub_id, square_status=status)
            return None

    if mapped == local_status:
        return None

    # Same freeze-one-way safeguard as the Stripe path.
    if local_status == "frozen" and mapped == "active":
        logger.warning(
            "Subscription reconciliation: Square is active for a locally-frozen membership — not auto-unfreezing",
            schema=schema, membership_id=membership_id, sub_id=sub_id,
        )
        return None

    async with get_tenant_db(schema_override=schema) as db:
        await db.execute(
            """
            UPDATE member_memberships
            SET status = $1, updated_at = NOW()
            WHERE id = $2
            """,
            mapped, membership_id,
        )
    logger.info(
        "Subscription reconciliation (Square): status drift fixed",
        schema=schema, membership_id=membership_id, sub_id=sub_id,
        from_status=local_status, to_status=mapped,
    )
    return {
        "membership_id": membership_id,
        "sub_id": sub_id,
        "from": local_status,
        "to": mapped,
        "provider": "square",
    }


async def _reconcile_schema(schema: str) -> dict:
    summary = {"schema": schema, "checked": 0, "drift": []}
    await set_tenant_context_from_schema(schema)
    try:
        from app.core.tenant_context import get_tenant_context
        ctx = get_tenant_context()
        org_id = ctx.organization_id

        # ── Stripe-tracked memberships ────────────────────────────────
        api_key, stripe_account_id = await _get_stripe_key(org_id)
        async with get_tenant_db(schema_override=schema) as db:
            stripe_rows = await db.fetch(
                """
                SELECT id, stripe_subscription_id, status
                FROM member_memberships
                WHERE stripe_subscription_id IS NOT NULL
                  AND status IN ('active', 'past_due', 'frozen', 'expired')
                """
            )
        for r in stripe_rows:
            summary["checked"] += 1
            drift = await _reconcile_one(
                schema, org_id, api_key, stripe_account_id,
                str(r["id"]), r["stripe_subscription_id"], r["status"],
            )
            if drift:
                drift["provider"] = "stripe"
                summary["drift"].append(drift)

        # ── Square-tracked memberships ────────────────────────────────
        # Only fetches a Square access token if the org has any
        # square_subscription_id rows — keeps the OAuth-decrypt cost
        # off Stripe-only studios.
        async with get_tenant_db(schema_override=schema) as db:
            square_rows = await db.fetch(
                """
                SELECT id, square_subscription_id, status
                FROM member_memberships
                WHERE square_subscription_id IS NOT NULL
                  AND status IN ('active', 'past_due', 'frozen', 'expired')
                """
            )
        if square_rows:
            from app.services.payments.square_oauth_service import (
                square_oauth_service,
            )
            merchant_token = await square_oauth_service.get_merchant_access_token(
                org_id,
            )
            if not merchant_token:
                logger.warning(
                    "Skipping Square reconciliation — no usable access token",
                    schema=schema, sub_count=len(square_rows),
                )
            else:
                for r in square_rows:
                    summary["checked"] += 1
                    drift = await _reconcile_one_square(
                        schema, merchant_token,
                        str(r["id"]), r["square_subscription_id"], r["status"],
                    )
                    if drift:
                        summary["drift"].append(drift)
    finally:
        clear_tenant_context()
    return summary


async def _reconcile_all() -> dict:
    async with get_global_db() as db:
        schemas = await db.fetch(
            "SELECT schema_name FROM af_global.organizations "
            "WHERE status IN ('active', 'trial')"
        )

    overall = {"tenants": [], "total_drift": 0}
    for s in schemas:
        try:
            result = await _reconcile_schema(s["schema_name"])
            overall["tenants"].append(result)
            overall["total_drift"] += len(result["drift"])
        except Exception as e:
            logger.warning(
                "Subscription reconciliation: tenant failed",
                schema=s["schema_name"], error=str(e),
            )
    return overall


@app.task(name="app.workers.tasks.subscription_reconcile.reconcile_subscriptions")
def reconcile_subscriptions():
    """Hourly task: sync local membership status with Stripe."""
    return asyncio.run(_reconcile_all())
