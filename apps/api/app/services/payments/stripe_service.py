"""AuraFlow — Stripe Service

Stripe Connect integration: customer management, subscriptions, one-off charges,
refunds, and Stripe Connect account onboarding for studio owners.
"""
import asyncio
import json
import uuid
from datetime import datetime
from typing import Optional

import stripe

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_tenant_db, get_global_db


def _configure_stripe():
    """Set the Stripe API key from settings."""
    if settings.STRIPE_SECRET_KEY:
        stripe.api_key = settings.STRIPE_SECRET_KEY


def _stripe_key_for_org(direct_key: str | None) -> str:
    """Return the correct Stripe API key — org's direct key or platform key.

    Use this instead of mutating stripe.api_key to avoid race conditions
    between concurrent requests.
    """
    return direct_key if direct_key else settings.STRIPE_SECRET_KEY


async def _get_org_stripe_key(org_id: str) -> str | None:
    """Get the org's direct Stripe key if in direct mode, else return None (use platform key)."""
    async with get_global_db() as db:
        row = await db.fetchrow(
            "SELECT stripe_direct_mode, stripe_secret_key_encrypted FROM af_global.organizations WHERE id = $1",
            org_id,
        )
    if row and row.get("stripe_direct_mode") and row.get("stripe_secret_key_encrypted"):
        from app.utils.encryption import decrypt_credential
        async with get_global_db() as db:
            return await decrypt_credential(db, row["stripe_secret_key_encrypted"])
    return None


async def _get_org_publishable_key(org_id: str) -> str | None:
    """Get the org's publishable key if in direct mode."""
    async with get_global_db() as db:
        row = await db.fetchrow(
            "SELECT stripe_direct_mode, stripe_publishable_key FROM af_global.organizations WHERE id = $1",
            org_id,
        )
    if row and row.get("stripe_direct_mode") and row.get("stripe_publishable_key"):
        return row["stripe_publishable_key"]
    return None


class StripeService:

    def __init__(self):
        _configure_stripe()

    # ── Stripe Connect (studio owner onboarding) ─────────────────────────────

    async def create_connect_account(self, org_id: str, email: str) -> dict:
        """Create a Stripe Connect Express account for the studio."""
        _configure_stripe()
        account = await asyncio.to_thread(
            lambda: stripe.Account.create(
                type="express",
                email=email,
                capabilities={
                    "card_payments": {"requested": True},
                    "transfers": {"requested": True},
                },
                metadata={"auraflow_org_id": org_id},
            )
        )
        # Store the connected account ID on the org
        async with get_global_db() as db:
            await db.execute(
                """
                UPDATE af_global.organizations
                SET stripe_account_id = $1, updated_at = NOW()
                WHERE id = $2
                """,
                account.id, org_id,
            )
        logger.info("Stripe Connect account created", org_id=org_id, account_id=account.id)
        return {"account_id": account.id}

    async def create_account_link(self, org_id: str, return_url: str, refresh_url: str) -> dict:
        """Create an onboarding link for a Connect account."""
        _configure_stripe()
        async with get_global_db() as db:
            row = await db.fetchrow(
                "SELECT stripe_account_id FROM af_global.organizations WHERE id = $1",
                org_id,
            )
        if not row or not row["stripe_account_id"]:
            raise ValueError("No Stripe Connect account found for this organization")

        link = await asyncio.to_thread(
            lambda: stripe.AccountLink.create(
                account=row["stripe_account_id"],
                type="account_onboarding",
                return_url=return_url,
                refresh_url=refresh_url,
            )
        )
        return {"url": link.url}

    async def get_connect_status(self, org_id: str) -> dict:
        """Get the status of a Stripe Connect account."""
        _configure_stripe()
        async with get_global_db() as db:
            row = await db.fetchrow(
                "SELECT stripe_account_id FROM af_global.organizations WHERE id = $1",
                org_id,
            )
        if not row or not row["stripe_account_id"]:
            return {"connected": False, "charges_enabled": False, "payouts_enabled": False}

        account = await asyncio.to_thread(stripe.Account.retrieve, row["stripe_account_id"])
        return {
            "connected": True,
            "account_id": account.id,
            "charges_enabled": account.charges_enabled,
            "payouts_enabled": account.payouts_enabled,
            "details_submitted": account.details_submitted,
        }

    # ── Customer Management ───────────────────────────────────────────────────

    async def get_or_create_customer(
        self,
        member_id: str,
        email: str,
        name: str,
        stripe_account_id: Optional[str] = None,
        org_id: Optional[str] = None,
    ) -> str:
        """Get existing Stripe customer or create one. Returns customer ID.

        Supports direct mode via org_id — creates customer on org's own Stripe
        account instead of the platform account.
        """
        _configure_stripe()

        # Determine the correct API key (org direct key or platform)
        api_key = settings.STRIPE_SECRET_KEY
        if org_id:
            direct_key = await _get_org_stripe_key(org_id)
            if direct_key:
                api_key = direct_key
                stripe_account_id = None  # Direct mode, no Connect

        async with get_tenant_db() as db:
            row = await db.fetchrow(
                "SELECT stripe_customer_id FROM members WHERE id = $1",
                member_id,
            )
            if row and row.get("stripe_customer_id"):
                return row["stripe_customer_id"]

            # Create in Stripe
            params = {
                "api_key": api_key,
                "email": email,
                "name": name,
                "metadata": {"auraflow_member_id": member_id},
            }
            if stripe_account_id:
                customer = await asyncio.to_thread(
                    lambda: stripe.Customer.create(
                        stripe_account=stripe_account_id,
                        **params,
                    )
                )
            else:
                customer = await asyncio.to_thread(
                    lambda: stripe.Customer.create(**params)
                )

            # Store back
            await db.execute(
                "UPDATE members SET stripe_customer_id = $1, updated_at = NOW() WHERE id = $2",
                customer.id, member_id,
            )
            logger.info("Stripe customer created", member_id=member_id, customer_id=customer.id)
            return customer.id

    # ── One-off Charges / Payment Intents ─────────────────────────────────────

    async def create_payment_intent(
        self,
        amount_cents: int,
        customer_id: str,
        description: str,
        metadata: Optional[dict] = None,
        stripe_account_id: Optional[str] = None,
    ) -> dict:
        """Create a Stripe PaymentIntent."""
        _configure_stripe()
        params = {
            "amount": amount_cents,
            "currency": "usd",
            "customer": customer_id,
            "description": description,
            "metadata": metadata or {},
            # ALWAYS save the card on the customer for future off-session
            # charges. Without this, Stripe charges the card once and
            # forgets it — the customer ends up with zero PaymentMethods
            # on file even after paying us hundreds of dollars.
            "setup_future_usage": "off_session",
        }
        if stripe_account_id:
            # Platform fee
            fee = int(amount_cents * settings.STRIPE_PLATFORM_FEE_PERCENT / 100)
            params["application_fee_amount"] = fee
            intent = await asyncio.to_thread(
                lambda: stripe.PaymentIntent.create(
                    stripe_account=stripe_account_id,
                    **params,
                )
            )
        else:
            intent = await asyncio.to_thread(
                lambda: stripe.PaymentIntent.create(**params)
            )

        return {
            "payment_intent_id": intent.id,
            "client_secret": intent.client_secret,
            "status": intent.status,
        }

    # ── Subscriptions ─────────────────────────────────────────────────────────

    async def create_subscription(
        self,
        customer_id: str,
        price_cents: int,
        interval: str = "month",
        metadata: Optional[dict] = None,
        stripe_account_id: Optional[str] = None,
        trial_days: int = 0,
    ) -> dict:
        """Create a Stripe subscription with an inline price."""
        _configure_stripe()
        params = {
            "customer": customer_id,
            "items": [{
                "price_data": {
                    "currency": "usd",
                    "unit_amount": price_cents,
                    "recurring": {"interval": interval},
                    "product_data": {"name": metadata.get("type_name", "Membership")},
                },
            }],
            "metadata": metadata or {},
        }
        if trial_days > 0:
            params["trial_period_days"] = trial_days
        if stripe_account_id:
            fee = int(price_cents * settings.STRIPE_PLATFORM_FEE_PERCENT / 100)
            params["application_fee_percent"] = settings.STRIPE_PLATFORM_FEE_PERCENT
            sub = await asyncio.to_thread(
                lambda: stripe.Subscription.create(
                    stripe_account=stripe_account_id,
                    **params,
                )
            )
        else:
            sub = await asyncio.to_thread(
                lambda: stripe.Subscription.create(**params)
            )

        logger.info("Stripe subscription created", subscription_id=sub.id, customer_id=customer_id)
        return {
            "subscription_id": sub.id,
            "status": sub.status,
            "current_period_end": sub.current_period_end,
        }

    async def cancel_subscription(
        self,
        subscription_id: str,
        at_period_end: bool = True,
        stripe_account_id: Optional[str] = None,
        org_id: Optional[str] = None,
    ) -> dict:
        """Cancel a Stripe subscription. Honors direct-mode when org_id given."""
        _configure_stripe()
        api_key = settings.STRIPE_SECRET_KEY
        kwargs: dict = {}
        if org_id:
            direct_key = await _get_org_stripe_key(org_id)
            if direct_key:
                api_key = direct_key
            else:
                async with get_global_db() as db:
                    row = await db.fetchrow(
                        "SELECT stripe_account_id FROM af_global.organizations WHERE id = $1",
                        org_id,
                    )
                if row and row.get("stripe_account_id"):
                    kwargs["stripe_account"] = row["stripe_account_id"]
        elif stripe_account_id:
            kwargs["stripe_account"] = stripe_account_id
        if at_period_end:
            sub = await asyncio.to_thread(
                lambda: stripe.Subscription.modify(
                    subscription_id,
                    cancel_at_period_end=True,
                    api_key=api_key,
                    **kwargs,
                )
            )
        else:
            sub = await asyncio.to_thread(
                lambda: stripe.Subscription.delete(
                    subscription_id, api_key=api_key, **kwargs
                )
            )
        logger.info("Stripe subscription cancelled", subscription_id=subscription_id)
        return {
            "subscription_id": sub.id,
            "status": sub.status,
            "current_period_end": getattr(sub, "current_period_end", None),
            "cancel_at_period_end": getattr(sub, "cancel_at_period_end", False),
        }

    # ── Checkout Sessions ────────────────────────────────────────────────

    async def create_checkout_session(
        self,
        org_id: str,
        member_id: str,
        membership_type_id: str,
        success_url: str,
        cancel_url: str,
    ) -> dict:
        """Create a Stripe Checkout session for membership purchase."""
        _configure_stripe()

        # Check if org uses direct Stripe (own key) vs Connect
        direct_key = await _get_org_stripe_key(org_id)
        api_key = _stripe_key_for_org(direct_key)
        if direct_key:
            stripe_account_id = None  # No Connect, direct mode
        else:
            # Get Connect account
            async with get_global_db() as db:
                org_row = await db.fetchrow(
                    "SELECT stripe_account_id FROM af_global.organizations WHERE id = $1",
                    org_id,
                )
            stripe_account_id = org_row["stripe_account_id"] if org_row else None

        # Get membership type pricing
        async with get_tenant_db() as db:
            mt = await db.fetchrow(
                "SELECT * FROM membership_types WHERE id = $1", membership_type_id
            )
            if not mt:
                raise ValueError("Membership type not found")

            member = await db.fetchrow(
                "SELECT id, email, first_name, last_name, stripe_customer_id FROM members WHERE id = $1",
                member_id,
            )
            if not member:
                raise ValueError("Member not found")

        # Get or create Stripe customer
        customer_id = await self.get_or_create_customer(
            member_id=member_id,
            email=member["email"],
            name=f"{member['first_name']} {member['last_name']}",
            stripe_account_id=stripe_account_id,
            org_id=org_id,
        )

        price_cents = mt["price_cents"]
        is_recurring = mt["billing_period"] in ("monthly", "yearly", "weekly")
        interval_map = {"monthly": "month", "yearly": "year", "weekly": "week"}

        # Include org schema so webhooks can resolve the tenant
        from app.core.tenant_context import require_tenant_context
        ctx = require_tenant_context()

        metadata = {
            "auraflow_member_id": member_id,
            "auraflow_membership_type_id": membership_type_id,
            "auraflow_org_schema": ctx.schema_name,
            "type_name": mt["name"],
        }

        line_item = {
            "price_data": {
                "currency": "usd",
                "unit_amount": price_cents,
                "product_data": {"name": mt["name"]},
            },
            "quantity": 1,
        }
        if is_recurring:
            line_item["price_data"]["recurring"] = {
                "interval": interval_map.get(mt["billing_period"], "month"),
            }

        params = {
            "mode": "subscription" if is_recurring else "payment",
            "customer": customer_id,
            "line_items": [line_item],
            "success_url": success_url + "?session_id={CHECKOUT_SESSION_ID}",
            "cancel_url": cancel_url,
            "metadata": metadata,
            # Always save the card on the customer for future off-session
            # charges (drop-ins, refilled packs, etc). Subscription mode
            # saves automatically; payment mode needs the explicit
            # setup_future_usage flag. Without this Stripe charges the
            # card once and forgets it, leaving the customer with zero
            # PaymentMethods on file. This was the bug behind Mira Dick
            # having no card to charge for a drop-in after she'd paid
            # $180 for a gift card a week earlier.
        }

        if is_recurring:
            params["subscription_data"] = {"metadata": metadata}
        else:
            params["payment_intent_data"] = {
                "setup_future_usage": "off_session",
            }

        # Circuit-breaker guard: if Stripe is degraded, fail fast instead of
        # stacking requests that all time out.
        from app.core.circuit_breakers import stripe_breaker

        if stripe_account_id:
            fee_percent = settings.STRIPE_PLATFORM_FEE_PERCENT
            if is_recurring:
                params["subscription_data"]["application_fee_percent"] = fee_percent
            else:
                fee = int(price_cents * fee_percent / 100)
                params["payment_intent_data"]["application_fee_amount"] = fee

            async def _create_connect_session():
                return await asyncio.to_thread(
                    lambda: stripe.checkout.Session.create(
                        api_key=api_key, stripe_account=stripe_account_id, **params
                    )
                )
            session = await stripe_breaker.call_async(_create_connect_session)
        else:
            async def _create_direct_session():
                return await asyncio.to_thread(
                    lambda: stripe.checkout.Session.create(api_key=api_key, **params)
                )
            session = await stripe_breaker.call_async(_create_direct_session)

        logger.info(
            "Checkout session created",
            session_id=session.id,
            member_id=member_id,
            membership_type=mt["name"],
        )
        return {
            "session_id": session.id,
            "url": session.url,
        }

    async def verify_and_recover_checkout(self, org_id: str, session_id: str) -> dict:
        """Confirm a checkout session was paid and ensure the local
        membership row exists. Use as a fallback for missed webhooks.

        Returns:
          {
            "session_id": str,
            "paid": bool,
            "recovered": bool,   # true if we had to synthesize the row
            "membership_id": str | None,
          }
        """
        _configure_stripe()
        # Resolve direct vs Connect mode just like create_checkout_session
        direct_key = await _get_org_stripe_key(org_id)
        api_key = _stripe_key_for_org(direct_key)
        kwargs: dict = {}
        if not direct_key:
            async with get_global_db() as db:
                row = await db.fetchrow(
                    "SELECT stripe_account_id FROM af_global.organizations WHERE id = $1",
                    org_id,
                )
            if row and row.get("stripe_account_id"):
                kwargs["stripe_account"] = row["stripe_account_id"]

        try:
            session = await asyncio.to_thread(
                lambda: stripe.checkout.Session.retrieve(
                    session_id, api_key=api_key, **kwargs,
                )
            )
        except Exception as e:
            raise ValueError(f"Could not retrieve checkout session: {e}")

        paid = session.payment_status == "paid" and session.status == "complete"
        if not paid:
            return {
                "session_id": session_id,
                "paid": False,
                "recovered": False,
                "membership_id": None,
            }

        # If the webhook already ran, the membership row exists — return it.
        metadata = session.metadata or {}
        member_id = metadata.get("auraflow_member_id")
        membership_type_id = metadata.get("auraflow_membership_type_id")
        schema = metadata.get("auraflow_org_schema")
        if not (member_id and membership_type_id and schema):
            raise ValueError(
                "Checkout session is missing AuraFlow metadata — cannot recover. "
                "Open a Stripe Dashboard → AuraFlow refund and recreate the purchase."
            )

        async with get_tenant_db(schema_override=schema) as db:
            existing = await db.fetchrow(
                """
                SELECT id FROM member_memberships
                WHERE member_id = $1 AND membership_type_id = $2 AND status = 'active'
                """,
                member_id, membership_type_id,
            )
        if existing:
            return {
                "session_id": session_id,
                "paid": True,
                "recovered": False,
                "membership_id": str(existing["id"]),
            }

        # Webhook hasn't landed and the row isn't there — replay the
        # webhook handler manually with this event's data.
        logger.warning(
            "Checkout recovery: synthesizing missed webhook",
            session_id=session_id, member_id=member_id, schema=schema,
        )
        from app.services.payments.webhook_handler import StripeWebhookHandler
        handler = StripeWebhookHandler()
        synthetic_event = {"id": f"recover_{session_id}", "type": "checkout.session.completed"}
        # Set tenant context so the handler can write to the right schema
        from app.core.tenant_context import set_tenant_context, clear_tenant_context
        set_tenant_context(
            organization_id=org_id, schema_name=schema,
            slug=schema.replace("af_tenant_", ""),
        )
        try:
            await handler._handle_checkout_completed(session, schema=schema)
        finally:
            clear_tenant_context()

        async with get_tenant_db(schema_override=schema) as db:
            new_row = await db.fetchrow(
                """
                SELECT id FROM member_memberships
                WHERE member_id = $1 AND membership_type_id = $2 AND status = 'active'
                ORDER BY created_at DESC LIMIT 1
                """,
                member_id, membership_type_id,
            )
        return {
            "session_id": session_id,
            "paid": True,
            "recovered": True,
            "membership_id": str(new_row["id"]) if new_row else None,
        }

    async def create_one_time_checkout_session(
        self,
        org_id: str,
        member_id: str,
        item_name: str,
        price_cents: int,
        success_url: str,
        cancel_url: str,
        metadata: dict | None = None,
    ) -> dict:
        """Create a Stripe Checkout session for a generic one-time payment.

        Used for workshop/course enrollment and private session bookings.
        """
        _configure_stripe()

        # Check if org uses direct Stripe (own key) vs Connect
        direct_key = await _get_org_stripe_key(org_id)
        api_key = _stripe_key_for_org(direct_key)
        if direct_key:
            stripe_account_id = None
        else:
            async with get_global_db() as db:
                org_row = await db.fetchrow(
                    "SELECT stripe_account_id FROM af_global.organizations WHERE id = $1",
                    org_id,
                )
            stripe_account_id = org_row["stripe_account_id"] if org_row else None

        async with get_tenant_db() as db:
            member = await db.fetchrow(
                "SELECT id, email, first_name, last_name, stripe_customer_id FROM members WHERE id = $1",
                member_id,
            )
            if not member:
                raise ValueError("Member not found")

        customer_id = await self.get_or_create_customer(
            member_id=member_id,
            email=member["email"],
            name=f"{member['first_name']} {member['last_name']}",
            stripe_account_id=stripe_account_id,
            org_id=org_id,
        )

        from app.core.tenant_context import require_tenant_context
        ctx = require_tenant_context()

        base_metadata = {
            "auraflow_member_id": member_id,
            "auraflow_org_schema": ctx.schema_name,
            "item_name": item_name,
        }
        if metadata:
            base_metadata.update(metadata)

        line_item = {
            "price_data": {
                "currency": "usd",
                "unit_amount": price_cents,
                "product_data": {"name": item_name},
            },
            "quantity": 1,
        }

        params = {
            "mode": "payment",
            "customer": customer_id,
            "line_items": [line_item],
            "success_url": success_url + "?session_id={CHECKOUT_SESSION_ID}",
            "cancel_url": cancel_url,
            "metadata": base_metadata,
            # Always save the card on the customer for future off-session
            # charges. See create_checkout_session for the rationale —
            # without setup_future_usage Stripe forgets the card after
            # the one-time charge.
            "payment_intent_data": {
                "setup_future_usage": "off_session",
                "metadata": base_metadata,
            },
        }

        if stripe_account_id:
            fee = int(price_cents * settings.STRIPE_PLATFORM_FEE_PERCENT / 100)
            params["payment_intent_data"]["application_fee_amount"] = fee
            session = await asyncio.to_thread(
                lambda: stripe.checkout.Session.create(
                    api_key=api_key, stripe_account=stripe_account_id, **params
                )
            )
        else:
            session = await asyncio.to_thread(
                lambda: stripe.checkout.Session.create(api_key=api_key, **params)
            )

        logger.info(
            "One-time checkout session created",
            session_id=session.id,
            member_id=member_id,
            item=item_name,
        )
        return {
            "session_id": session.id,
            "url": session.url,
        }

    async def create_customer_portal_session(
        self,
        org_id: str,
        member_id: str,
        return_url: str,
    ) -> dict:
        """Create a Stripe Customer Portal session for payment method management."""
        _configure_stripe()

        # Check for direct mode — use per-request api_key to avoid race conditions
        direct_key = await _get_org_stripe_key(org_id)
        api_key = _stripe_key_for_org(direct_key)
        if direct_key:
            stripe_account_id = None
        else:
            async with get_global_db() as db:
                org_row = await db.fetchrow(
                    "SELECT stripe_account_id FROM af_global.organizations WHERE id = $1",
                    org_id,
                )
            stripe_account_id = org_row["stripe_account_id"] if org_row else None

        async with get_tenant_db() as db:
            member = await db.fetchrow(
                "SELECT stripe_customer_id, email, first_name, last_name, stripe_coupon_id FROM members WHERE id = $1", member_id
            )
        if not member:
            raise ValueError("Member not found")

        # Auto-create Stripe customer if none exists
        customer_id = member.get("stripe_customer_id")
        if not customer_id:
            # Check if customer already exists in Stripe by email
            existing = await asyncio.to_thread(
                lambda: stripe.Customer.list(api_key=api_key, email=member["email"], limit=1)
            )
            if existing.data:
                customer_id = existing.data[0].id
            else:
                customer = await asyncio.to_thread(
                    lambda: stripe.Customer.create(
                        api_key=api_key,
                        email=member["email"],
                        name=f"{member['first_name']} {member['last_name']}",
                        metadata={"auraflow_member_id": member_id},
                    )
                )
                customer_id = customer.id
            # Save to member record
            async with get_tenant_db() as db:
                await db.execute(
                    "UPDATE members SET stripe_customer_id = $1, updated_at = NOW() WHERE id = $2",
                    customer_id, member_id,
                )

        # Check if member has active recurring membership without subscription
        async with get_tenant_db() as db:
            recurring = await db.fetchrow(
                """
                SELECT mm.id, mt.name, mt.price_cents, mt.billing_period, mm.current_period_end
                FROM member_memberships mm
                JOIN membership_types mt ON mt.id = mm.membership_type_id
                WHERE mm.member_id = $1 AND mm.status IN ('active', 'frozen')
                  AND mt.billing_period IN ('monthly', 'yearly')
                  AND mt.price_cents > 0
                  AND mm.stripe_subscription_id IS NULL
                LIMIT 1
                """,
                member_id,
            )

        if recurring:
            # Create a Checkout Session with trial until their current billing period ends
            # so they are NOT charged until their next billing date
            interval = "month" if recurring["billing_period"] == "monthly" else "year"
            from app.core.tenant_context import require_tenant_context
            ctx = require_tenant_context()

            # Calculate trial days until their next billing date
            trial_days = None
            if recurring.get("current_period_end"):
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc)
                period_end = recurring["current_period_end"]
                if hasattr(period_end, 'tzinfo') and period_end.tzinfo is None:
                    from zoneinfo import ZoneInfo
                    period_end = period_end.replace(tzinfo=ZoneInfo("UTC"))
                days_remaining = (period_end - now).days
                if days_remaining > 0:
                    trial_days = days_remaining

            # Session-level metadata so webhook handler can find the member
            session_metadata = {
                "auraflow_member_id": member_id,
                "auraflow_membership_id": str(recurring["id"]),
                "auraflow_org_schema": ctx.schema_name,
            }

            checkout_params = {
                "mode": "subscription",
                "customer": customer_id,
                "line_items": [{
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": recurring["price_cents"],
                        "product_data": {"name": recurring["name"]},
                        "recurring": {"interval": interval},
                    },
                    "quantity": 1,
                }],
                "success_url": return_url + "?payment=success",
                "cancel_url": return_url + "?payment=cancelled",
                "metadata": session_metadata,
                "subscription_data": {
                    "metadata": session_metadata,
                },
            }

            # Add trial period so they aren't charged until their next billing date
            if trial_days and trial_days > 0:
                checkout_params["subscription_data"]["trial_period_days"] = trial_days
                logger.info("Subscription with trial", member_id=member_id, trial_days=trial_days,
                           first_charge=str(recurring["current_period_end"]))

            # Apply founding member coupon if member has one
            if member.get("stripe_coupon_id"):
                checkout_params["discounts"] = [{"coupon": member["stripe_coupon_id"]}]
                logger.info("Founding member coupon applied", member_id=member_id, coupon=member["stripe_coupon_id"])
            session = await asyncio.to_thread(
                lambda: stripe.checkout.Session.create(api_key=api_key, **checkout_params)
            )
            return {"url": session.url}
        else:
            # No recurring membership — just open billing portal for card management
            params = {
                "customer": customer_id,
                "return_url": return_url,
            }
            if stripe_account_id:
                session = await asyncio.to_thread(
                    lambda: stripe.billing_portal.Session.create(
                        api_key=api_key, stripe_account=stripe_account_id, **params
                    )
                )
            else:
                session = await asyncio.to_thread(
                    lambda: stripe.billing_portal.Session.create(api_key=api_key, **params)
                )
            return {"url": session.url}

    # ── Payment Links (for staff-booked private sessions) ──────────────────

    async def create_booking_payment_link(
        self,
        org_id: str,
        booking: dict,
        member: dict,
        success_url: str,
        cancel_url: str,
    ) -> dict:
        """Create a Stripe Checkout session for a private session booking.

        Used when staff books on behalf of a member — generates a payment URL
        that can be emailed to the member.
        """
        _configure_stripe()
        direct_key = await _get_org_stripe_key(org_id)
        api_key = _stripe_key_for_org(direct_key)
        stripe_account_id = None
        if not direct_key:
            async with get_global_db() as db:
                org_row = await db.fetchrow(
                    "SELECT stripe_account_id FROM af_global.organizations WHERE id = $1",
                    org_id,
                )
            stripe_account_id = org_row["stripe_account_id"] if org_row else None

        # Get or create Stripe customer
        member_id = str(member["id"])
        customer_id = member.get("stripe_customer_id")
        if not customer_id:
            existing = await asyncio.to_thread(
                lambda: stripe.Customer.list(api_key=api_key, email=member["email"], limit=1)
            )
            if existing.data:
                customer_id = existing.data[0].id
            else:
                customer = await asyncio.to_thread(
                    lambda: stripe.Customer.create(
                        api_key=api_key,
                        email=member["email"],
                        name=f"{member['first_name']} {member['last_name']}",
                        metadata={"auraflow_member_id": member_id},
                    )
                )
                customer_id = customer.id
            async with get_tenant_db() as db:
                await db.execute(
                    "UPDATE members SET stripe_customer_id = $1, updated_at = NOW() WHERE id = $2",
                    customer_id, member_id,
                )

        from app.core.tenant_context import require_tenant_context
        ctx = require_tenant_context()

        metadata = {
            "auraflow_member_id": member_id,
            "auraflow_booking_id": str(booking["id"]),
            "auraflow_checkout_type": "private_session",
            "auraflow_org_schema": ctx.schema_name,
            "item_name": booking.get("service_name", "Private Session"),
        }
        # Add package info if this is a package booking
        if booking.get("_package_sessions"):
            metadata["auraflow_package_sessions"] = str(booking["_package_sessions"])
            metadata["auraflow_package_service_id"] = str(booking.get("_package_service_id", ""))

        params = {
            "mode": "payment",
            "customer": customer_id,
            "line_items": [{
                "price_data": {
                    "currency": "usd",
                    "unit_amount": booking["price_cents"],
                    "product_data": {"name": booking.get("service_name", "Private Session")},
                },
                "quantity": 1,
            }],
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": metadata,
            # Always save the card on the customer for future off-session
            # charges. See create_checkout_session for the rationale.
            "payment_intent_data": {
                "setup_future_usage": "off_session",
                "metadata": metadata,
            },
        }

        if stripe_account_id:
            fee = int(booking["price_cents"] * settings.STRIPE_PLATFORM_FEE_PERCENT / 100)
            params["payment_intent_data"]["application_fee_amount"] = fee
            session = await asyncio.to_thread(
                lambda: stripe.checkout.Session.create(
                    api_key=api_key, stripe_account=stripe_account_id, **params
                )
            )
        else:
            session = await asyncio.to_thread(
                lambda: stripe.checkout.Session.create(api_key=api_key, **params)
            )

        # Store payment link URL on the booking
        async with get_tenant_db() as db:
            await db.execute(
                "UPDATE private_bookings SET payment_url = $1, updated_at = NOW() WHERE id = $2",
                session.url, str(booking["id"]),
            )

        logger.info(
            "Booking payment link created",
            booking_id=str(booking["id"]),
            member_id=member_id,
            session_id=session.id,
        )
        return {"session_id": session.id, "url": session.url}

    # ── Refunds ───────────────────────────────────────────────────────────────

    async def refund_payment(
        self,
        payment_intent_id: str,
        amount_cents: Optional[int] = None,
        reason: str = "requested_by_customer",
        stripe_account_id: Optional[str] = None,
    ) -> dict:
        """Issue a full or partial refund."""
        _configure_stripe()
        params = {
            "payment_intent": payment_intent_id,
            "reason": reason,
        }
        if amount_cents:
            params["amount"] = amount_cents
        if stripe_account_id:
            refund = await asyncio.to_thread(
                lambda: stripe.Refund.create(stripe_account=stripe_account_id, **params)
            )
        else:
            refund = await asyncio.to_thread(
                lambda: stripe.Refund.create(**params)
            )

        logger.info("Refund issued", refund_id=refund.id, amount=refund.amount)
        return {
            "refund_id": refund.id,
            "amount": refund.amount,
            "status": refund.status,
        }

    # ── Transactions (local DB) ───────────────────────────────────────────────

    async def record_transaction(self, data: dict) -> dict:
        """Record a transaction in the local DB.

        Idempotent on:
          - stripe_payment_intent_id (Stripe-originated)
          - square_payment_id (Square-originated)
          - metadata->>'external_reference' (api-key-originated, e.g. wellness-emr
            / bioalign integrations)
        Whichever dedup key is present, the existing row is returned so retries
        don't create duplicates. Square payments MUST use square_payment_id; do
        not stuff Square IDs into stripe_payment_intent_id (corrupts refund
        routing in refund_payment endpoint).
        """
        txn_id = str(uuid.uuid4())
        metadata = data.get("metadata") or {}
        external_ref = metadata.get("external_reference") if isinstance(metadata, dict) else None
        async with get_tenant_db() as db:
            if data.get("stripe_payment_intent_id"):
                existing = await db.fetchrow(
                    "SELECT * FROM transactions WHERE stripe_payment_intent_id = $1",
                    data["stripe_payment_intent_id"],
                )
                if existing:
                    return dict(existing)
            if data.get("square_payment_id"):
                existing = await db.fetchrow(
                    "SELECT * FROM transactions WHERE square_payment_id = $1",
                    data["square_payment_id"],
                )
                if existing:
                    return dict(existing)
            if external_ref:
                existing = await db.fetchrow(
                    "SELECT * FROM transactions WHERE metadata->>'external_reference' = $1",
                    external_ref,
                )
                if existing:
                    return dict(existing)

            row = await db.fetchrow(
                """
                INSERT INTO transactions
                    (id, member_id, amount_cents, type, status, description,
                     stripe_payment_intent_id, stripe_invoice_id,
                     square_payment_id,
                     membership_id, booking_id,
                     fee_cents, net_amount_cents, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14::jsonb)
                RETURNING *
                """,
                txn_id, data["member_id"], data["amount_cents"],
                data.get("type", "payment"), data.get("status", "completed"),
                data.get("description"), data.get("stripe_payment_intent_id"),
                data.get("stripe_invoice_id"),
                data.get("square_payment_id"),
                data.get("membership_id"),
                data.get("booking_id"), data.get("fee_cents", 0),
                data.get("net_amount_cents", data["amount_cents"]),
                json.dumps(metadata) if metadata else None,
            )
            # Update member lifetime revenue
            await db.execute(
                """
                UPDATE members
                SET lifetime_revenue_cents = lifetime_revenue_cents + $1, updated_at = NOW()
                WHERE id = $2
                """,
                data["amount_cents"], data["member_id"],
            )
            logger.info("Transaction recorded", txn_id=txn_id, amount=data["amount_cents"])
            return dict(row)

    async def list_transactions(
        self,
        member_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """List transactions, optionally filtered by member."""
        async with get_tenant_db() as db:
            if member_id:
                rows = await db.fetch(
                    """
                    SELECT t.*, m.first_name, m.last_name, m.email AS member_email
                    FROM transactions t
                    JOIN members m ON m.id = t.member_id
                    WHERE t.member_id = $1
                    ORDER BY t.created_at DESC
                    LIMIT $2 OFFSET $3
                    """,
                    member_id, limit, offset,
                )
            else:
                rows = await db.fetch(
                    """
                    SELECT t.*, m.first_name, m.last_name, m.email AS member_email
                    FROM transactions t
                    JOIN members m ON m.id = t.member_id
                    ORDER BY t.created_at DESC
                    LIMIT $1 OFFSET $2
                    """,
                    limit, offset,
                )
            return [dict(r) for r in rows]

    async def get_transaction(self, txn_id: str) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                SELECT t.*, m.first_name, m.last_name, m.email AS member_email
                FROM transactions t
                JOIN members m ON m.id = t.member_id
                WHERE t.id = $1
                """,
                txn_id,
            )
            return dict(row) if row else None

    async def refund_transaction(self, txn_id: str, amount_cents: int, reason: str) -> dict | None:
        """Mark a transaction as refunded in local DB."""
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                UPDATE transactions
                SET refund_amount_cents = $2, refund_reason = $3, refunded_at = NOW(),
                    status = CASE WHEN $2 >= amount_cents THEN 'refunded' ELSE 'partially_refunded' END,
                    updated_at = NOW()
                WHERE id = $1
                RETURNING *
                """,
                txn_id, amount_cents, reason,
            )
            if row:
                # Adjust member lifetime revenue
                await db.execute(
                    """
                    UPDATE members
                    SET lifetime_revenue_cents = lifetime_revenue_cents - $1, updated_at = NOW()
                    WHERE id = $2
                    """,
                    amount_cents, str(row["member_id"]),
                )
            return dict(row) if row else None

    # ── Revenue Queries ───────────────────────────────────────────────────────

    async def get_revenue_summary(self, start_date: datetime, end_date: datetime) -> dict:
        """Get revenue summary for a date range.

        Treats refund-type rows (amount_cents negative, type='refund') as
        a separate ledger flow: gross revenue counts the inbound payments,
        refunds counts the outbound, net = gross_net - refunds.

        Includes status='refunded' so fully-refunded transactions still
        contribute to gross revenue — the money DID come in, it just left
        again as a refund. The previous query excluded 'refunded' rows
        AND ignored type='refund' rows entirely, so the Refunds tile
        always read $0 once a refund finalized.
        """
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN type != 'refund' THEN amount_cents ELSE 0 END), 0) AS total_revenue,
                    COALESCE(SUM(CASE WHEN type != 'refund' THEN fee_cents ELSE 0 END), 0) AS total_fees,
                    COALESCE(SUM(CASE WHEN type != 'refund' THEN net_amount_cents ELSE 0 END), 0)
                      + COALESCE(SUM(CASE WHEN type  = 'refund' THEN amount_cents ELSE 0 END), 0)
                      AS net_revenue,
                    COALESCE(SUM(CASE WHEN type  = 'refund' THEN -amount_cents ELSE 0 END), 0) AS total_refunds,
                    COUNT(*) FILTER (WHERE type != 'refund') AS transaction_count
                FROM transactions
                WHERE status IN ('completed', 'partially_refunded', 'refunded')
                  AND created_at >= $1 AND created_at < $2
                """,
                start_date, end_date,
            )
            return dict(row) if row else {}

    async def get_failed_payments(self, limit: int = 50) -> list[dict]:
        """Get recent failed payment attempts."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT fp.*, m.first_name, m.last_name, m.email AS member_email
                FROM failed_payment_attempts fp
                JOIN members m ON m.id = fp.member_id
                ORDER BY fp.created_at DESC
                LIMIT $1
                """,
                limit,
            )
            return [dict(r) for r in rows]

    async def record_failed_payment(self, data: dict) -> dict:
        """Record a failed payment attempt."""
        fp_id = str(uuid.uuid4())
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                INSERT INTO failed_payment_attempts
                    (id, member_id, membership_id, stripe_payment_intent_id,
                     stripe_invoice_id, amount_cents, failure_reason, attempt_number)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING *
                """,
                fp_id, data["member_id"], data.get("membership_id"),
                data.get("stripe_payment_intent_id"), data.get("stripe_invoice_id"),
                data["amount_cents"], data["failure_reason"],
                data.get("attempt_number", 1),
            )
            return dict(row)

    # ── Subscription Lifecycle ─────────────────────────────────────────────────

    async def pause_subscription(
        self,
        subscription_id: str,
        org_id: Optional[str] = None,
        stripe_account_id: Optional[str] = None,
    ) -> dict:
        """Pause a Stripe subscription by setting pause_collection.

        If `org_id` is provided, resolves the correct API key/account
        automatically (direct-mode orgs use their own key; Connect-mode
        orgs use the platform key + stripe_account). If `org_id` is
        missing, falls back to the explicit stripe_account_id arg
        (legacy callers).
        """
        _configure_stripe()
        api_key = settings.STRIPE_SECRET_KEY
        kwargs: dict = {}
        if org_id:
            direct_key = await _get_org_stripe_key(org_id)
            if direct_key:
                api_key = direct_key
            else:
                async with get_global_db() as db:
                    row = await db.fetchrow(
                        "SELECT stripe_account_id FROM af_global.organizations WHERE id = $1",
                        org_id,
                    )
                if row and row.get("stripe_account_id"):
                    kwargs["stripe_account"] = row["stripe_account_id"]
        elif stripe_account_id:
            kwargs["stripe_account"] = stripe_account_id

        sub = await asyncio.to_thread(
            lambda: stripe.Subscription.modify(
                subscription_id,
                pause_collection={"behavior": "void"},
                api_key=api_key,
                **kwargs,
            )
        )
        logger.info("Stripe subscription paused", subscription_id=subscription_id)
        return {"subscription_id": sub.id, "status": sub.status, "paused": True}

    async def resume_subscription(
        self,
        subscription_id: str,
        org_id: Optional[str] = None,
        stripe_account_id: Optional[str] = None,
    ) -> dict:
        """Resume a paused Stripe subscription by removing pause_collection.

        See pause_subscription for the org_id resolution semantics.
        """
        _configure_stripe()
        api_key = settings.STRIPE_SECRET_KEY
        kwargs: dict = {}
        if org_id:
            direct_key = await _get_org_stripe_key(org_id)
            if direct_key:
                api_key = direct_key
            else:
                async with get_global_db() as db:
                    row = await db.fetchrow(
                        "SELECT stripe_account_id FROM af_global.organizations WHERE id = $1",
                        org_id,
                    )
                if row and row.get("stripe_account_id"):
                    kwargs["stripe_account"] = row["stripe_account_id"]
        elif stripe_account_id:
            kwargs["stripe_account"] = stripe_account_id

        sub = await asyncio.to_thread(
            lambda: stripe.Subscription.modify(
                subscription_id,
                pause_collection="",
                api_key=api_key,
                **kwargs,
            )
        )
        logger.info("Stripe subscription resumed", subscription_id=subscription_id)
        return {"subscription_id": sub.id, "status": sub.status, "paused": False}

    async def get_subscription_details(
        self,
        subscription_id: str,
        stripe_account_id: Optional[str] = None,
        org_id: Optional[str] = None,
    ) -> dict:
        """Retrieve subscription info from Stripe. Honors direct-mode when org_id given."""
        _configure_stripe()
        api_key = settings.STRIPE_SECRET_KEY
        kwargs: dict = {}
        if org_id:
            direct_key = await _get_org_stripe_key(org_id)
            if direct_key:
                api_key = direct_key
            else:
                async with get_global_db() as db:
                    row = await db.fetchrow(
                        "SELECT stripe_account_id FROM af_global.organizations WHERE id = $1",
                        org_id,
                    )
                if row and row.get("stripe_account_id"):
                    kwargs["stripe_account"] = row["stripe_account_id"]
        elif stripe_account_id:
            kwargs["stripe_account"] = stripe_account_id
        sub = await asyncio.to_thread(
            lambda: stripe.Subscription.retrieve(
                subscription_id, api_key=api_key, **kwargs
            )
        )
        return {
            "subscription_id": sub.id,
            "status": sub.status,
            "current_period_start": sub.current_period_start,
            "current_period_end": sub.current_period_end,
            "cancel_at_period_end": sub.cancel_at_period_end,
            "pause_collection": dict(sub.pause_collection) if sub.pause_collection else None,
        }

    # ── Invoice PDF ──────────────────────────────────────────────────────────

    async def get_invoice_pdf_url(
        self,
        invoice_id: str,
        stripe_account_id: Optional[str] = None,
    ) -> str:
        """Retrieve the invoice PDF URL from Stripe."""
        _configure_stripe()
        kwargs = {}
        if stripe_account_id:
            kwargs["stripe_account"] = stripe_account_id
        invoice = await asyncio.to_thread(
            lambda: stripe.Invoice.retrieve(invoice_id, **kwargs)
        )
        if not invoice.invoice_pdf:
            raise ValueError("Invoice PDF not available")
        return invoice.invoice_pdf

    # ── Platform Invoices (org billing history) ────────────────────────────────

    async def list_org_invoices(
        self,
        org_id: str,
        limit: int = 24,
    ) -> list[dict]:
        """List Stripe invoices for an organization's platform subscription.

        Uses the org's stripe_customer_id (not the Connect stripe_account_id)
        to fetch invoices that represent what the studio pays AuraFlow.
        """
        _configure_stripe()

        async with get_global_db() as db:
            row = await db.fetchrow(
                "SELECT stripe_customer_id FROM af_global.organizations WHERE id = $1",
                org_id,
            )
        if not row or not row.get("stripe_customer_id"):
            return []

        invoices = await asyncio.to_thread(
            lambda: stripe.Invoice.list(
                customer=row["stripe_customer_id"],
                limit=limit,
            )
        )

        results = []
        for inv in invoices.data:
            results.append({
                "id": inv.id,
                "number": inv.number,
                "created": inv.created,
                "amount_due": inv.amount_due,
                "amount_paid": inv.amount_paid,
                "currency": inv.currency,
                "status": inv.status,  # draft, open, paid, void, uncollectible
                "invoice_pdf": inv.invoice_pdf,
                "hosted_invoice_url": inv.hosted_invoice_url,
                "period_start": inv.period_start,
                "period_end": inv.period_end,
                "description": inv.description,
            })

        return results

    # ── AI Token Billing (Stripe Billing Meters) ──────────────────────────────

    async def setup_ai_token_meter(self) -> dict:
        """One-time setup: create Stripe Meter, Product, and graduated Price.

        Stores the resulting IDs in af_global.platform_settings for future use.
        """
        _configure_stripe()

        # Check if already set up
        async with get_global_db() as db:
            existing = await db.fetchrow(
                "SELECT value FROM af_global.platform_settings WHERE key = 'ai_token_stripe_meter_id'"
            )
            if existing and existing["value"]:
                import json as _json
                meter_id = _json.loads(existing["value"]) if isinstance(existing["value"], str) else existing["value"]
                if meter_id:
                    return {"status": "already_configured", "meter_id": meter_id}

        # 1. Create the Billing Meter
        meter = await asyncio.to_thread(
            lambda: stripe.billing.Meter.create(
                display_name="AI Tokens",
                event_name="ai_tokens",
                default_aggregation={"formula": "sum"},
                customer_mapping={
                    "type": "by_id",
                    "event_payload_key": "stripe_customer_id",
                },
            )
        )

        # 2. Create a Product
        product = await asyncio.to_thread(
            lambda: stripe.Product.create(
                name="AI Token Usage",
                description="AI-powered features token consumption",
                metadata={"auraflow_type": "ai_token_usage"},
            )
        )

        # 3. Load current rate settings
        async with get_global_db() as db:
            rate_row = await db.fetchrow(
                "SELECT value FROM af_global.platform_settings WHERE key = 'ai_token_rate_cents_per_1k'"
            )
            free_row = await db.fetchrow(
                "SELECT value FROM af_global.platform_settings WHERE key = 'ai_token_free_tier'"
            )

        import json as _json
        rate = float(_json.loads(rate_row["value"])) if rate_row else 3.0
        free_tier = int(_json.loads(free_row["value"])) if free_row else 50000

        # 4. Create graduated tiered Price (per 1K tokens)
        # Stripe tiers use unit_amount_decimal in cents
        price = await asyncio.to_thread(
            lambda: stripe.Price.create(
                product=product.id,
                currency="usd",
                billing_scheme="tiered",
                tiers_mode="graduated",
                tiers=[
                    {
                        "up_to": free_tier,
                        "unit_amount_decimal": "0",
                    },
                    {
                        "up_to": "inf",
                        "unit_amount_decimal": str(rate),
                    },
                ],
                recurring={"interval": "month", "usage_type": "metered"},
                meter=meter.id,
                metadata={"auraflow_type": "ai_token_price"},
            )
        )

        # 5. Store IDs in platform_settings
        async with get_global_db() as db:
            for key, value in [
                ("ai_token_stripe_meter_id", meter.id),
                ("ai_token_stripe_product_id", product.id),
                ("ai_token_stripe_price_id", price.id),
            ]:
                await db.execute(
                    """
                    UPDATE af_global.platform_settings
                    SET value = to_jsonb($2::text), updated_at = NOW()
                    WHERE key = $1
                    """,
                    key, value,
                )

        logger.info(
            "AI token billing meter set up",
            meter_id=meter.id,
            product_id=product.id,
            price_id=price.id,
        )
        return {
            "status": "created",
            "meter_id": meter.id,
            "product_id": product.id,
            "price_id": price.id,
        }

    async def report_ai_meter_event(
        self,
        stripe_customer_id: str,
        token_count: int,
    ) -> Optional[str]:
        """Report AI token usage to Stripe Billing Meter.

        Returns the meter event ID or None if billing is not configured.
        """
        _configure_stripe()

        async with get_global_db() as db:
            row = await db.fetchrow(
                "SELECT value FROM af_global.platform_settings WHERE key = 'ai_token_stripe_meter_id'"
            )
            enabled_row = await db.fetchrow(
                "SELECT value FROM af_global.platform_settings WHERE key = 'ai_token_billing_enabled'"
            )

        if not row or not row["value"]:
            return None

        import json as _json
        enabled = _json.loads(enabled_row["value"]) if enabled_row else True
        if not enabled:
            return None

        try:
            import time
            event = await asyncio.to_thread(
                lambda: stripe.billing.MeterEvent.create(
                    event_name="ai_tokens",
                    payload={
                        "stripe_customer_id": stripe_customer_id,
                        "value": str(token_count),
                    },
                    timestamp=int(time.time()),
                )
            )
            return event.identifier if hasattr(event, "identifier") else "reported"
        except Exception as e:
            logger.warning("Stripe meter event failed", error=str(e))
            return None

    async def add_ai_usage_to_subscription(self, org_id: str) -> dict:
        """Add AI token metered billing to an organization's subscription.

        Looks up the org's Stripe customer, finds their active subscription,
        and adds the AI token price as a metered subscription item.
        """
        _configure_stripe()

        # Get the AI token price ID
        async with get_global_db() as db:
            price_row = await db.fetchrow(
                "SELECT value FROM af_global.platform_settings WHERE key = 'ai_token_stripe_price_id'"
            )
            if not price_row or not price_row["value"]:
                raise ValueError("AI token billing not set up. Run setup_ai_token_meter first.")

            org_row = await db.fetchrow(
                "SELECT stripe_account_id, stripe_customer_id FROM af_global.organizations WHERE id = $1",
                org_id,
            )
            if not org_row:
                raise ValueError("Organization not found")

        import json as _json
        price_id = _json.loads(price_row["value"]) if isinstance(price_row["value"], str) else price_row["value"]

        customer_id = org_row.get("stripe_customer_id")
        if not customer_id:
            raise ValueError("Organization has no Stripe customer ID")

        # Find the org's active subscription
        subs = await asyncio.to_thread(
            lambda: stripe.Subscription.list(customer=customer_id, status="active", limit=1)
        )
        if not subs.data:
            raise ValueError("Organization has no active subscription")

        subscription = subs.data[0]

        # Check if AI token item already exists
        for item in subscription["items"]["data"]:
            if item.get("price", {}).get("id") == price_id:
                return {"status": "already_added", "subscription_id": subscription.id}

        # Add the metered price as a new subscription item
        await asyncio.to_thread(
            lambda: stripe.SubscriptionItem.create(
                subscription=subscription.id,
                price=price_id,
                metadata={"auraflow_type": "ai_token_usage"},
            )
        )

        logger.info("AI token billing added to subscription", org_id=org_id, subscription_id=subscription.id)
        return {"status": "added", "subscription_id": subscription.id}

    async def update_ai_token_rate(
        self,
        rate_cents_per_1k: float,
        free_tier: int = 50000,
    ) -> dict:
        """Update the AI token billing rate.

        Creates a new Stripe Price with updated tiers, archives the old one,
        and updates platform_settings.
        """
        _configure_stripe()

        async with get_global_db() as db:
            product_row = await db.fetchrow(
                "SELECT value FROM af_global.platform_settings WHERE key = 'ai_token_stripe_product_id'"
            )
            old_price_row = await db.fetchrow(
                "SELECT value FROM af_global.platform_settings WHERE key = 'ai_token_stripe_price_id'"
            )
            meter_row = await db.fetchrow(
                "SELECT value FROM af_global.platform_settings WHERE key = 'ai_token_stripe_meter_id'"
            )

        if not product_row or not product_row["value"]:
            raise ValueError("AI token billing not set up. Run setup_ai_token_meter first.")

        import json as _json
        product_id = _json.loads(product_row["value"]) if isinstance(product_row["value"], str) else product_row["value"]
        meter_id = _json.loads(meter_row["value"]) if meter_row and meter_row["value"] else None

        # Create new Price with updated tiers
        new_price = await asyncio.to_thread(
            lambda: stripe.Price.create(
                product=product_id,
                currency="usd",
                billing_scheme="tiered",
                tiers_mode="graduated",
                tiers=[
                    {
                        "up_to": free_tier,
                        "unit_amount_decimal": "0",
                    },
                    {
                        "up_to": "inf",
                        "unit_amount_decimal": str(rate_cents_per_1k),
                    },
                ],
                recurring={"interval": "month", "usage_type": "metered"},
                meter=meter_id,
                metadata={"auraflow_type": "ai_token_price"},
            )
        )

        # Archive old price
        if old_price_row and old_price_row["value"]:
            old_price_id = _json.loads(old_price_row["value"]) if isinstance(old_price_row["value"], str) else old_price_row["value"]
            try:
                await asyncio.to_thread(
                    lambda: stripe.Price.modify(old_price_id, active=False)
                )
            except Exception as e:
                logger.warning("Failed to archive old price", error=str(e))

        # Update platform_settings
        async with get_global_db() as db:
            await db.execute(
                """
                UPDATE af_global.platform_settings
                SET value = to_jsonb($2::text), updated_at = NOW()
                WHERE key = $1
                """,
                "ai_token_stripe_price_id", new_price.id,
            )
            await db.execute(
                """
                UPDATE af_global.platform_settings
                SET value = to_jsonb($2::numeric), updated_at = NOW()
                WHERE key = $1
                """,
                "ai_token_rate_cents_per_1k", rate_cents_per_1k,
            )
            await db.execute(
                """
                UPDATE af_global.platform_settings
                SET value = to_jsonb($2::integer), updated_at = NOW()
                WHERE key = $1
                """,
                "ai_token_free_tier", free_tier,
            )

        logger.info(
            "AI token rate updated",
            rate=rate_cents_per_1k,
            free_tier=free_tier,
            new_price_id=new_price.id,
        )
        return {
            "status": "updated",
            "rate_cents_per_1k": rate_cents_per_1k,
            "free_tier": free_tier,
            "new_price_id": new_price.id,
        }
