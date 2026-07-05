"""
AuraFlow -- Platform Plan Management Service

Handles plan definitions, plan changes (upgrade/downgrade), and Stripe
subscription management for studio tenant subscriptions.
"""
import asyncio
from datetime import datetime
from typing import Optional

import stripe

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_global_db


# ── Plan Definitions ─────────────────────────────────────────────────────────

PLANS = {
    "studio": {
        "id": "studio",
        "name": "Studio",
        "price_cents": 9900,
        "price_display": "$99",
        "interval": "month",
        "tagline": "The full white-label platform for up to 10 locations",
        "popular": True,
        "features": [
            "Up to 10 studio locations",
            "Unlimited classes, members & instructors",
            "Full white-label branding",
            "Full RESTful API for custom integrations",
            "Zoom live-streaming & on-demand video",
            "AI-powered studio management",
            "Private sessions with payment links",
            "POS, gift cards & retail",
            "Email & SMS campaigns",
            "Workshops & teacher training",
            "ClassPass & EMR integrations",
            "Advanced analytics & churn prediction",
            "Priority support",
        ],
        "limits": {
            "members": -1,  # unlimited
            "instructors": -1,  # unlimited
            "locations": 10,
        },
    },
    "enterprise": {
        "id": "enterprise",
        "name": "Enterprise",
        "price_cents": 0,
        "price_display": "Custom",
        "interval": "month",
        "tagline": "For franchise chains and large studio networks",
        "contact_sales": True,
        "features": [
            "Everything in Studio",
            "Unlimited locations",
            "Dedicated account manager",
            "Custom onboarding & migration",
            "SLA guarantee",
            "Advanced security & compliance",
            "Custom feature development",
        ],
        "limits": {
            "members": -1,
            "instructors": -1,
            "locations": -1,
        },
    },
}

# Legacy plan IDs map to studio plan
PLANS["starter"] = PLANS["studio"]
PLANS["growth"] = PLANS["studio"]
PLANS["scale"] = PLANS["studio"]

PLAN_ORDER = ["studio", "enterprise"]


def _configure_stripe():
    if settings.STRIPE_SECRET_KEY:
        stripe.api_key = settings.STRIPE_SECRET_KEY


async def load_plans_from_db() -> dict:
    """Load plans from af_global.platform_plans table. Falls back to PLANS dict."""
    try:
        async with get_global_db() as db:
            rows = await db.fetch(
                "SELECT * FROM af_global.platform_plans WHERE is_active = TRUE ORDER BY sort_order"
            )
        if not rows:
            return PLANS
        result = {}
        for r in rows:
            import json
            features = r["features"] if isinstance(r["features"], list) else json.loads(r["features"]) if r["features"] else []
            limits = r["limits"] if isinstance(r["limits"], dict) else json.loads(r["limits"]) if r["limits"] else {}
            result[r["id"]] = {
                "id": r["id"],
                "name": r["name"],
                "price_cents": r["price_cents"],
                "price_display": r["price_display"],
                "interval": r["interval"],
                "tagline": r["tagline"] or "",
                "features": features,
                "limits": limits,
                "popular": r.get("popular", False),
                "contact_sales": r.get("contact_sales", False),
                "price_note": r.get("price_note"),
                "additional_location_cents": r.get("additional_location_cents"),
            }
        return result
    except Exception as e:
        logger.warning("Failed to load plans from DB, using defaults", error=str(e))
        return PLANS


async def save_plan_to_db(plan_id: str, updates: dict) -> dict:
    """Update a plan in the database."""
    import json
    async with get_global_db() as db:
        features_json = json.dumps(updates["features"]) if "features" in updates else None
        limits_json = json.dumps(updates["limits"]) if "limits" in updates else None

        set_clauses = []
        params = []
        idx = 1
        for key in ["name", "price_cents", "price_display", "interval", "tagline",
                     "price_note", "additional_location_cents", "contact_sales", "popular"]:
            if key in updates:
                set_clauses.append(f"{key} = ${idx}")
                params.append(updates[key])
                idx += 1
        if features_json is not None:
            set_clauses.append(f"features = ${idx}::jsonb")
            params.append(features_json)
            idx += 1
        if limits_json is not None:
            set_clauses.append(f"limits = ${idx}::jsonb")
            params.append(limits_json)
            idx += 1
        set_clauses.append("updated_at = NOW()")
        params.append(plan_id)

        await db.execute(
            f"UPDATE af_global.platform_plans SET {', '.join(set_clauses)} WHERE id = ${idx}",
            *params,
        )

        row = await db.fetchrow("SELECT * FROM af_global.platform_plans WHERE id = $1", plan_id)

    features = row["features"] if isinstance(row["features"], list) else json.loads(row["features"]) if row["features"] else []
    limits = row["limits"] if isinstance(row["limits"], dict) else json.loads(row["limits"]) if row["limits"] else {}
    result = {
        "id": row["id"], "name": row["name"], "price_cents": row["price_cents"],
        "price_display": row["price_display"], "interval": row["interval"],
        "tagline": row["tagline"], "features": features, "limits": limits,
        "popular": row.get("popular", False), "contact_sales": row.get("contact_sales", False),
        "price_note": row.get("price_note"), "additional_location_cents": row.get("additional_location_cents"),
    }

    # Update in-memory cache
    PLANS[plan_id] = result
    return result


class PlanService:
    """Manages platform plan subscriptions for studio tenants."""

    def __init__(self):
        _configure_stripe()

    async def get_available_plans_async(self) -> list[dict]:
        """Return all available plans from database."""
        plans = await load_plans_from_db()
        return [plans[pid] for pid in PLAN_ORDER if pid in plans]

    def get_available_plans(self) -> list[dict]:
        """Return all available plans (sync fallback using in-memory cache)."""
        return [PLANS[pid] for pid in PLAN_ORDER if pid in PLANS]

    def get_plan(self, plan_id: str) -> dict | None:
        """Get a single plan by ID."""
        return PLANS.get(plan_id)

    def classify_change(self, current_plan_id: str, new_plan_id: str) -> str:
        """Return 'upgrade', 'downgrade', or 'same'."""
        if current_plan_id == new_plan_id:
            return "same"
        current_idx = PLAN_ORDER.index(current_plan_id) if current_plan_id in PLAN_ORDER else -1
        new_idx = PLAN_ORDER.index(new_plan_id) if new_plan_id in PLAN_ORDER else -1
        return "upgrade" if new_idx > current_idx else "downgrade"

    async def get_current_billing(self, org_id: str) -> dict:
        """Get the current plan, subscription status, and billing info for an org."""
        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT plan_id, status, stripe_subscription_id,
                       stripe_customer_id, trial_ends_at, created_at
                FROM af_global.organizations
                WHERE id = $1
                """,
                org_id,
            )

        if not row:
            raise ValueError("Organization not found")

        plan_id = row["plan_id"] or "trial"
        plan = PLANS.get(plan_id)
        result = {
            "plan_id": plan_id,
            "plan_name": plan["name"] if plan else plan_id.title(),
            "plan_price_cents": plan["price_cents"] if plan else 0,
            "plan_price_display": plan["price_display"] if plan else "$0",
            "status": row["status"],
            "has_stripe_subscription": bool(row["stripe_subscription_id"]),
            "trial_ends_at": row["trial_ends_at"].isoformat() if row["trial_ends_at"] else None,
        }

        # Fetch Stripe subscription details if one exists
        if row["stripe_subscription_id"]:
            try:
                sub = await asyncio.to_thread(
                    stripe.Subscription.retrieve, row["stripe_subscription_id"]
                )
                result["subscription_status"] = sub.status
                result["current_period_end"] = datetime.fromtimestamp(
                    sub.current_period_end
                ).isoformat()
                result["cancel_at_period_end"] = sub.cancel_at_period_end
            except Exception as e:
                logger.warning(
                    "Failed to fetch Stripe subscription",
                    subscription_id=row["stripe_subscription_id"],
                    error=str(e),
                )

        return result

    async def preview_plan_change(
        self, org_id: str, new_plan_id: str
    ) -> dict:
        """Preview what a plan change would cost (proration info)."""
        if new_plan_id not in PLANS:
            raise ValueError(f"Invalid plan: {new_plan_id}")

        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT plan_id, stripe_subscription_id, stripe_customer_id
                FROM af_global.organizations
                WHERE id = $1
                """,
                org_id,
            )

        if not row:
            raise ValueError("Organization not found")

        current_plan_id = row["plan_id"] or "trial"
        direction = self.classify_change(current_plan_id, new_plan_id)
        new_plan = PLANS[new_plan_id]

        result = {
            "current_plan_id": current_plan_id,
            "new_plan_id": new_plan_id,
            "direction": direction,
            "new_price_cents": new_plan["price_cents"],
            "new_price_display": new_plan["price_display"],
            "proration_amount_cents": None,
            "immediate_charge": direction == "upgrade",
        }

        # If there is an active Stripe subscription, fetch proration preview
        if row["stripe_subscription_id"]:
            try:
                sub = await asyncio.to_thread(
                    stripe.Subscription.retrieve, row["stripe_subscription_id"]
                )
                if sub.status == "active" and sub["items"]["data"]:
                    import time

                    proration_date = int(time.time())
                    invoice = await asyncio.to_thread(
                        lambda: stripe.Invoice.create_preview(
                            customer=row["stripe_customer_id"],
                            subscription=row["stripe_subscription_id"],
                            subscription_items=[
                                {
                                    "id": sub["items"]["data"][0].id,
                                    "price_data": {
                                        "currency": "usd",
                                        "unit_amount": new_plan["price_cents"],
                                        "recurring": {"interval": "month"},
                                        "product_data": {
                                            "name": f"AuraFlow {new_plan['name']} Plan",
                                        },
                                    },
                                }
                            ],
                            subscription_proration_date=proration_date,
                        )
                    )
                    result["proration_amount_cents"] = invoice.total
            except Exception as e:
                logger.warning("Proration preview failed", error=str(e))

        return result

    async def change_plan(self, org_id: str, new_plan_id: str) -> dict:
        """
        Change the organization's subscription plan.

        - If no Stripe subscription exists, creates one.
        - If one exists, modifies the subscription item with proration.
        - Updates the org's plan_id and re-seeds feature flags.
        """
        if new_plan_id not in PLANS:
            raise ValueError(f"Invalid plan: {new_plan_id}")

        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT id, plan_id, status, stripe_subscription_id,
                       stripe_customer_id, slug
                FROM af_global.organizations
                WHERE id = $1
                """,
                org_id,
            )

        if not row:
            raise ValueError("Organization not found")

        current_plan_id = row["plan_id"] or "trial"
        if current_plan_id == new_plan_id:
            raise ValueError("Already on this plan")

        new_plan = PLANS[new_plan_id]
        direction = self.classify_change(current_plan_id, new_plan_id)
        subscription_id = row["stripe_subscription_id"]
        customer_id = row["stripe_customer_id"]

        # ── Handle Stripe subscription ────────────────────────────────────
        if subscription_id:
            # Modify existing subscription
            try:
                sub = await asyncio.to_thread(
                    stripe.Subscription.retrieve, subscription_id
                )
                if sub["items"]["data"]:
                    item_id = sub["items"]["data"][0].id
                    updated_sub = await asyncio.to_thread(
                        lambda: stripe.Subscription.modify(
                            subscription_id,
                            items=[
                                {
                                    "id": item_id,
                                    "price_data": {
                                        "currency": "usd",
                                        "unit_amount": new_plan["price_cents"],
                                        "recurring": {"interval": "month"},
                                        "product_data": {
                                            "name": f"AuraFlow {new_plan['name']} Plan",
                                        },
                                    },
                                }
                            ],
                            proration_behavior="create_prorations",
                            metadata={
                                "auraflow_org_id": org_id,
                                "auraflow_plan": new_plan_id,
                            },
                        )
                    )
                    subscription_id = updated_sub.id
                    logger.info(
                        "Stripe subscription modified",
                        org_id=org_id,
                        direction=direction,
                        new_plan=new_plan_id,
                    )
            except Exception as e:
                logger.error("Failed to modify Stripe subscription", error=str(e))
                raise ValueError(f"Failed to update subscription: {str(e)}")

        elif customer_id:
            # Customer exists but no subscription — create one
            try:
                sub = await asyncio.to_thread(
                    lambda: stripe.Subscription.create(
                        customer=customer_id,
                        items=[
                            {
                                "price_data": {
                                    "currency": "usd",
                                    "unit_amount": new_plan["price_cents"],
                                    "recurring": {"interval": "month"},
                                    "product_data": {
                                        "name": f"AuraFlow {new_plan['name']} Plan",
                                    },
                                },
                            }
                        ],
                        metadata={
                            "auraflow_org_id": org_id,
                            "auraflow_plan": new_plan_id,
                        },
                    )
                )
                subscription_id = sub.id
                logger.info(
                    "Stripe subscription created for plan change",
                    org_id=org_id,
                    subscription_id=sub.id,
                )
            except Exception as e:
                logger.error("Failed to create Stripe subscription", error=str(e))
                raise ValueError(f"Failed to create subscription: {str(e)}")

        # ── Update organization record ────────────────────────────────────
        async with get_global_db() as db:
            await db.execute(
                """
                UPDATE af_global.organizations
                SET plan_id = $1,
                    status = CASE WHEN status = 'trial' THEN 'active' ELSE status END,
                    stripe_subscription_id = COALESCE($2, stripe_subscription_id),
                    updated_at = NOW()
                WHERE id = $3
                """,
                new_plan_id,
                subscription_id,
                org_id,
            )

        # ── Re-seed feature flags for the new plan ────────────────────────
        from app.services.tenant_provisioning import TenantProvisioningService

        provisioner = TenantProvisioningService()
        async with get_global_db() as db:
            await provisioner._seed_feature_flags(db, org_id, new_plan_id)

        # ── Invalidate tenant cache ───────────────────────────────────────
        from app.core.redis import get_redis

        redis = await get_redis()
        if redis and row["slug"]:
            await redis.delete(f"tenant:{row['slug']}")

        logger.info(
            "Plan changed",
            org_id=org_id,
            from_plan=current_plan_id,
            to_plan=new_plan_id,
            direction=direction,
        )

        return {
            "previous_plan_id": current_plan_id,
            "new_plan_id": new_plan_id,
            "direction": direction,
            "new_price_display": new_plan["price_display"],
            "subscription_id": subscription_id,
            "message": f"Plan {'upgraded' if direction == 'upgrade' else 'downgraded'} to {new_plan['name']}",
        }
