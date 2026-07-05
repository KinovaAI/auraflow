"""
AuraFlow -- Discount & Coupon Service

Manages coupon codes, founding rates, and custom pricing for studio tenants.
Integrates with Stripe for coupon/promotion code management.
"""
import asyncio
from datetime import datetime
from typing import Optional

import stripe

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_global_db


def _configure_stripe():
    if settings.STRIPE_SECRET_KEY:
        stripe.api_key = settings.STRIPE_SECRET_KEY


class DiscountService:
    """Manages coupons, discounts, and custom pricing for studio tenants."""

    def __init__(self):
        _configure_stripe()

    async def create_coupon(
        self,
        code: str,
        discount_type: str,
        discount_value: int,
        max_uses: Optional[int] = None,
        expires_at: Optional[datetime] = None,
        description: Optional[str] = None,
    ) -> dict:
        """Create a reusable coupon code.

        Args:
            code: Unique coupon code string (e.g. 'FOUNDING50')
            discount_type: 'percent' or 'fixed'
            discount_value: Percentage (0-100) or amount in cents
            max_uses: Maximum number of times this coupon can be used
            expires_at: When the coupon expires
            description: Human-readable description
        """
        if discount_type not in ("percent", "fixed"):
            raise ValueError("discount_type must be 'percent' or 'fixed'")
        if discount_type == "percent" and not (0 < discount_value <= 100):
            raise ValueError("Percent discount must be between 1 and 100")
        if discount_type == "fixed" and discount_value <= 0:
            raise ValueError("Fixed discount must be a positive amount in cents")

        code = code.upper().strip()

        # Check for duplicate code
        async with get_global_db() as db:
            existing = await db.fetchval(
                "SELECT 1 FROM af_global.coupons WHERE code = $1",
                code,
            )
        if existing:
            raise ValueError(f"Coupon code '{code}' already exists")

        # Create Stripe Coupon
        stripe_coupon_id = None
        try:
            stripe_params = {
                "id": f"auraflow_{code.lower()}",
                "name": description or f"AuraFlow Coupon {code}",
                "metadata": {"auraflow_code": code},
            }
            if discount_type == "percent":
                stripe_params["percent_off"] = discount_value
            else:
                stripe_params["amount_off"] = discount_value
                stripe_params["currency"] = "usd"

            if max_uses:
                stripe_params["max_redemptions"] = max_uses
            if expires_at:
                stripe_params["redeem_by"] = int(expires_at.timestamp())

            stripe_coupon = await asyncio.to_thread(
                lambda: stripe.Coupon.create(**stripe_params)
            )
            stripe_coupon_id = stripe_coupon.id
            logger.info("Stripe coupon created", coupon_id=stripe_coupon_id, code=code)
        except Exception as e:
            logger.warning("Failed to create Stripe coupon", code=code, error=str(e))

        # Store in database
        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                INSERT INTO af_global.coupons
                    (code, discount_type, discount_value, max_uses, uses_count,
                     expires_at, description, stripe_coupon_id, created_at)
                VALUES ($1, $2, $3, $4, 0, $5, $6, $7, NOW())
                RETURNING id, code, discount_type, discount_value, max_uses,
                          uses_count, expires_at, description, stripe_coupon_id,
                          created_at
                """,
                code, discount_type, discount_value, max_uses,
                expires_at, description, stripe_coupon_id,
            )

        logger.info("Coupon created", code=code, discount_type=discount_type, value=discount_value)
        return dict(row)

    async def apply_coupon(self, org_id: str, coupon_code: str) -> dict:
        """Apply a coupon to an org's subscription.

        Validates the coupon exists, is not expired, and has remaining uses.
        Creates a Stripe Promotion Code and applies it to the subscription.
        """
        coupon_code = coupon_code.upper().strip()

        # Look up coupon
        async with get_global_db() as db:
            coupon = await db.fetchrow(
                """
                SELECT id, code, discount_type, discount_value, max_uses,
                       uses_count, expires_at, stripe_coupon_id
                FROM af_global.coupons
                WHERE code = $1
                """,
                coupon_code,
            )

        if not coupon:
            raise ValueError("Invalid coupon code")

        # Check expiration
        if coupon["expires_at"] and coupon["expires_at"] < datetime.utcnow():
            raise ValueError("This coupon has expired")

        # Check uses remaining
        if coupon["max_uses"] and coupon["uses_count"] >= coupon["max_uses"]:
            raise ValueError("This coupon has reached its maximum number of uses")

        # Check if org already has this coupon
        async with get_global_db() as db:
            org = await db.fetchrow(
                """
                SELECT id, discount_coupon_code, stripe_subscription_id,
                       stripe_customer_id
                FROM af_global.organizations
                WHERE id = $1
                """,
                org_id,
            )

        if not org:
            raise ValueError("Organization not found")

        if org["discount_coupon_code"] == coupon_code:
            raise ValueError("This coupon is already applied")

        # Apply Stripe promotion code to subscription if subscription exists
        if org["stripe_subscription_id"] and coupon["stripe_coupon_id"]:
            try:
                await asyncio.to_thread(
                    lambda: stripe.Subscription.modify(
                        org["stripe_subscription_id"],
                        coupon=coupon["stripe_coupon_id"],
                    )
                )
                logger.info(
                    "Stripe coupon applied to subscription",
                    org_id=org_id,
                    coupon=coupon_code,
                )
            except Exception as e:
                logger.error(
                    "Failed to apply Stripe coupon",
                    org_id=org_id,
                    error=str(e),
                )
                raise ValueError(f"Failed to apply coupon to subscription: {str(e)}")

        # Update org record and increment coupon usage
        discount_percent = coupon["discount_value"] if coupon["discount_type"] == "percent" else None

        async with get_global_db() as db:
            await db.execute(
                """
                UPDATE af_global.organizations
                SET discount_coupon_code = $2,
                    discount_percent = $3,
                    updated_at = NOW()
                WHERE id = $1
                """,
                org_id, coupon_code, discount_percent,
            )
            await db.execute(
                """
                UPDATE af_global.coupons
                SET uses_count = uses_count + 1
                WHERE id = $1
                """,
                coupon["id"],
            )

        # Invalidate tenant cache
        from app.core.redis import get_redis
        redis = await get_redis()
        if redis:
            slug = await self._get_org_slug(org_id)
            if slug:
                await redis.delete(f"tenant:{slug}")

        logger.info("Coupon applied", org_id=org_id, coupon=coupon_code)
        return {
            "coupon_code": coupon_code,
            "discount_type": coupon["discount_type"],
            "discount_value": coupon["discount_value"],
            "message": f"Coupon {coupon_code} applied successfully",
        }

    async def remove_coupon(self, org_id: str) -> dict:
        """Remove discount from an org."""
        async with get_global_db() as db:
            org = await db.fetchrow(
                """
                SELECT id, discount_coupon_code, stripe_subscription_id
                FROM af_global.organizations
                WHERE id = $1
                """,
                org_id,
            )

        if not org:
            raise ValueError("Organization not found")

        if not org["discount_coupon_code"]:
            raise ValueError("No coupon is currently applied")

        # Remove from Stripe subscription
        if org["stripe_subscription_id"]:
            try:
                await asyncio.to_thread(
                    lambda: stripe.Subscription.modify(
                        org["stripe_subscription_id"],
                        coupon="",  # empty string removes coupon
                    )
                )
            except Exception as e:
                logger.warning("Failed to remove Stripe coupon", org_id=org_id, error=str(e))

        async with get_global_db() as db:
            await db.execute(
                """
                UPDATE af_global.organizations
                SET discount_coupon_code = NULL,
                    discount_percent = NULL,
                    updated_at = NOW()
                WHERE id = $1
                """,
                org_id,
            )

        logger.info("Coupon removed", org_id=org_id)
        return {"message": "Discount removed"}

    async def list_coupons(self) -> list[dict]:
        """List all coupons (platform admin)."""
        async with get_global_db() as db:
            rows = await db.fetch(
                """
                SELECT id, code, discount_type, discount_value, max_uses,
                       uses_count, expires_at, description, stripe_coupon_id,
                       created_at
                FROM af_global.coupons
                ORDER BY created_at DESC
                """
            )
        return [dict(r) for r in rows]

    async def get_org_discount(self, org_id: str) -> dict:
        """Get current discount for an org."""
        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT discount_coupon_code, discount_percent, custom_price_cents
                FROM af_global.organizations
                WHERE id = $1
                """,
                org_id,
            )

        if not row:
            raise ValueError("Organization not found")

        return {
            "discount_coupon_code": row["discount_coupon_code"],
            "discount_percent": row["discount_percent"],
            "custom_price_cents": row["custom_price_cents"],
            "has_discount": bool(row["discount_coupon_code"] or row["custom_price_cents"]),
        }

    async def set_custom_price(self, org_id: str, custom_price_cents: int) -> dict:
        """Override price for a specific org (founding rate).

        Stores in organizations table. Set to 0 or None to remove.
        """
        if custom_price_cents is not None and custom_price_cents < 0:
            raise ValueError("Custom price cannot be negative")

        async with get_global_db() as db:
            result = await db.execute(
                """
                UPDATE af_global.organizations
                SET custom_price_cents = $2, updated_at = NOW()
                WHERE id = $1
                """,
                org_id,
                custom_price_cents if custom_price_cents else None,
            )

        if result == "UPDATE 0":
            raise ValueError("Organization not found")

        logger.info("Custom price set", org_id=org_id, custom_price_cents=custom_price_cents)
        return {
            "org_id": org_id,
            "custom_price_cents": custom_price_cents,
            "message": f"Custom price set to ${custom_price_cents / 100:.2f}/mo" if custom_price_cents else "Custom price removed",
        }

    async def _get_org_slug(self, org_id: str) -> Optional[str]:
        async with get_global_db() as db:
            return await db.fetchval(
                "SELECT slug FROM af_global.organizations WHERE id = $1",
                org_id,
            )
