"""AuraFlow — Square Platform Billing Service

KinovaAI's side of the billing — what the studio pays *to* the
platform every month. Distinct from square_service.py (which is the
per-merchant SDK wrapper) and square_oauth_service.py (which is the
studio's OAuth to its own Square account).

Every studio with `billing_provider='square'` is a Customer on
KinovaAI's own Square account, with a Card on File and a recurring
Subscription. The monthly invoice (Phase 8) is built against this
customer + card.

Three pieces of state on `af_global.organizations` matter here:
  square_subscription_id  — KinovaAI's recurring sub for this studio
  square_customer_id      — already used per-tenant for members, but
                            we ALSO need a separate Square Customer
                            on KinovaAI's account; we store that on
                            a new column (TODO if not yet added) or
                            map it on the platform_invoices table.

For this initial pass, the KinovaAI-side Square Customer ID is kept
on a lightweight `kinovaai_platform_billing` JSONB column attached to
the migration scratch (we add it via a follow-up if it's missing).
For now the methods accept and return the IDs explicitly.

API surface:

  create_platform_customer(org_id, email, business_name)
    Creates a Square Customer on KinovaAI's account keyed on the
    studio's email + name. Returns the Square Customer ID.

  save_platform_card(org_id, customer_id, source_id)
    Saves a Web Payments SDK nonce as a Card on file on KinovaAI's
    account. Returns the card_id. ALWAYS save the card (Don's rule).

  start_platform_subscription(org_id, customer_id, card_id, plan_cents)
    Creates KinovaAI's Square Subscription Plan + Variation for the
    "Studio Platform" tier (cached after first creation) and enrolls
    this studio with the given card. Stores
    organizations.square_subscription_id. Default plan_cents = $99
    per Don's existing PLANS["studio"] price.

  get_status(org_id) — view of platform billing state for this studio.

Plan creation is one-shot at the platform level. The plan ID lives in
af_global.platform_settings under 'square_platform_plan_id' /
'square_platform_plan_variation_id'. First studio that subscribes
creates the plan; subsequent studios reuse it.
"""
from datetime import date
from typing import Optional

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_global_db
from app.services.payments.square_service import square_service


_PLATFORM_PLAN_SETTING_KEY = "square_platform_plan_id"
_PLATFORM_VARIATION_SETTING_KEY = "square_platform_plan_variation_id"
_PLATFORM_PRICE_SETTING_KEY = "square_platform_plan_price_cents"


def _platform_token() -> str:
    """KinovaAI's own access token. Distinct from any merchant token."""
    token = (
        settings.SQUARE_PLATFORM_ACCESS_TOKEN
        or settings.SQUARE_ACCESS_TOKEN  # legacy fallback
    )
    if not token:
        raise ValueError(
            "KinovaAI's Square platform account is not configured "
            "(SQUARE_PLATFORM_ACCESS_TOKEN)"
        )
    return token


def _platform_location_id() -> str:
    loc = (
        settings.SQUARE_PLATFORM_LOCATION_ID
        or settings.SQUARE_LOCATION_ID
    )
    if not loc:
        raise ValueError(
            "KinovaAI's Square platform location is not configured "
            "(SQUARE_PLATFORM_LOCATION_ID)"
        )
    return loc


async def _get_setting(key: str) -> Optional[str]:
    async with get_global_db() as db:
        row = await db.fetchrow(
            "SELECT value FROM af_global.platform_settings WHERE key = $1", key,
        )
    if not row:
        return None
    val = row["value"]
    # platform_settings.value is JSONB. Could be a JSON string OR a
    # plain string depending on how it was seeded historically.
    if isinstance(val, str):
        return val.strip('"') or None
    return str(val) if val is not None else None


async def _set_setting(key: str, value: str) -> None:
    import json
    async with get_global_db() as db:
        await db.execute(
            """
            INSERT INTO af_global.platform_settings (key, value, updated_at)
            VALUES ($1, $2::jsonb, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
            """,
            key, json.dumps(value),
        )


class SquarePlatformBillingService:

    async def create_platform_customer(
        self,
        organization_id: str,
        email: str,
        business_name: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> dict:
        """Get-or-create a Square Customer on KinovaAI's account.
        Returns {"customer_id", "created"}. The caller persists the ID
        wherever it tracks platform billing identity for the org."""
        result = await square_service.create_customer(
            merchant_access_token=_platform_token(),
            email=email,
            first_name=first_name or business_name,
            last_name=last_name,
            phone=phone,
            member_id=organization_id,  # reference_id ties back to AuraFlow org
        )
        logger.info(
            "Square platform customer created",
            org_id=organization_id, customer_id=result["customer_id"],
        )
        return {"customer_id": result["customer_id"], "created": True}

    async def save_platform_card(
        self,
        organization_id: str,
        customer_id: str,
        source_id: str,
        cardholder_name: Optional[str] = None,
    ) -> dict:
        """Save a card on KinovaAI's Square account for billing the
        studio. Returns {"card_id", "card_brand", "last_4", ...}."""
        card = await square_service.create_card(
            merchant_access_token=_platform_token(),
            customer_id=customer_id,
            source_id=source_id,
            cardholder_name=cardholder_name,
        )
        logger.info(
            "Square platform card saved",
            org_id=organization_id, customer_id=customer_id,
            card_id=card["card_id"], last_4=card.get("last_4"),
        )
        return card

    async def _ensure_platform_plan(
        self,
        price_cents: int,
    ) -> str:
        """Lazy-create KinovaAI's 'Studio Platform' Subscription Plan +
        Variation on first use. Cached in platform_settings so we never
        recreate it. Returns the plan_variation_id."""
        variation_id = await _get_setting(_PLATFORM_VARIATION_SETTING_KEY)
        if variation_id:
            return variation_id

        result = await square_service.create_subscription_plan(
            merchant_access_token=_platform_token(),
            name="AuraFlow Studio Platform",
            price_cents=price_cents,
            cadence="MONTHLY",
        )
        await _set_setting(_PLATFORM_PLAN_SETTING_KEY, result["plan_id"])
        await _set_setting(
            _PLATFORM_VARIATION_SETTING_KEY, result["plan_variation_id"],
        )
        await _set_setting(_PLATFORM_PRICE_SETTING_KEY, str(price_cents))
        logger.info(
            "Square platform plan created",
            plan_id=result["plan_id"],
            variation_id=result["plan_variation_id"],
            price_cents=price_cents,
        )
        return result["plan_variation_id"]

    async def start_platform_subscription(
        self,
        organization_id: str,
        customer_id: str,
        card_id: str,
        plan_cents: int = 9900,
        start_date: Optional[str] = None,
    ) -> dict:
        """Enroll a studio in KinovaAI's $99/mo Studio Platform plan
        with the given card on file. Stores
        organizations.square_subscription_id. Returns the subscription
        row."""
        plan_variation_id = await self._ensure_platform_plan(plan_cents)
        sub = await square_service.create_subscription(
            merchant_access_token=_platform_token(),
            merchant_location_id=_platform_location_id(),
            plan_variation_id=plan_variation_id,
            customer_id=customer_id,
            card_id=card_id,
            start_date=start_date or date.today().isoformat(),
            reference_id=organization_id,
        )
        async with get_global_db() as db:
            await db.execute(
                """
                UPDATE af_global.organizations
                SET square_subscription_id = $2, updated_at = NOW()
                WHERE id = $1
                """,
                organization_id, sub["subscription_id"],
            )
        logger.info(
            "Square platform subscription started",
            org_id=organization_id, sub_id=sub["subscription_id"],
            plan_cents=plan_cents,
        )
        return sub

    async def get_status(self, organization_id: str) -> dict:
        """Snapshot of platform billing state for an org. Surface this
        on /dashboard/settings/billing so the studio knows their card
        is on file and their subscription is active."""
        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT square_subscription_id, billing_provider, status
                FROM af_global.organizations WHERE id = $1
                """,
                organization_id,
            )
        if not row:
            return {"connected": False}
        sub_status = None
        if row["square_subscription_id"]:
            sub = await square_service.get_subscription(
                merchant_access_token=_platform_token(),
                subscription_id=row["square_subscription_id"],
            )
            sub_status = sub.get("status") if sub else None
        return {
            "connected": bool(row["square_subscription_id"]),
            "subscription_id": row["square_subscription_id"],
            "subscription_status": sub_status,
            "billing_provider": row["billing_provider"],
        }


square_platform_billing_service = SquarePlatformBillingService()
