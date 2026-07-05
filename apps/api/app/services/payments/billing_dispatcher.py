"""AuraFlow — Billing Dispatcher

Single entry-point for member-side payment operations. Reads
`organizations.billing_provider` once per call and delegates to either
`stripe_service` (legacy path, unchanged) or `square_service`
(OAuth-connected merchant path). Endpoints never branch on the
provider directly — they call into the dispatcher and the dispatcher
does the routing.

Why this is a separate service:
  1. Endpoints stay clean. They don't import stripe_service AND
     square_service; they import the dispatcher.
  2. The contract test (test_billing_dispatcher.py) can pin the rule
     that a stripe-mode org NEVER touches square_service and vice
     versa. One choke point to verify, not 30.
  3. The 1% Square app_fee vs Stripe's STRIPE_PLATFORM_FEE_PERCENT
     live here together — fee math is a billing concern, not an
     endpoint concern.

Per-operation pattern:
  result = await billing_dispatcher.create_payment(
      organization_id=org_id, ...
  )
  result["provider"] tells the caller which path actually ran, so the
  transaction record can carry the right *_payment_id column.

Safety rule (matches test_stripe_connect_isolation.py):
  organization_id is ALWAYS resolved server-side from JWT/tenant
  context. NEVER trust a billing_provider hint from a request body —
  it could be spoofed by a white-label portal trying to bypass the
  org's actual provider. The dispatcher reads provider straight from
  af_global.organizations every call.
"""
from typing import Optional

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_global_db
from app.services.payments.square_oauth_service import square_oauth_service
from app.services.payments.square_service import square_service


# Fee math centralized here. Stripe uses settings.STRIPE_PLATFORM_FEE_PERCENT
# (currently 1.25%); Square is a flat 1% per Don's spec. If you ever
# want to change the Square rate, change SQUARE_PLATFORM_FEE_PERCENT
# on settings — do NOT scatter the math across endpoints.
SQUARE_PLATFORM_FEE_PERCENT = 1.0


def _square_app_fee(amount_cents: int) -> int:
    """1% rounded to nearest cent, floored at 1¢ so $0.99 charges
    still contribute something to KinovaAI's platform account.
    Caps at the Square-enforced 90% / 60% (well above 1%; the floor
    + ceiling guard below is defensive only)."""
    fee = round(amount_cents * SQUARE_PLATFORM_FEE_PERCENT / 100)
    fee = max(1, fee)
    # Square's hard caps: ≥$5 → fee ≤90%; <$5 → fee ≤60%.
    cap = int(amount_cents * (0.60 if amount_cents < 500 else 0.90))
    return min(fee, cap)


# Square accepts these cadence strings on subscription plans. Anything
# not in this set defaults to MONTHLY (most common case + safest).
_SQUARE_CADENCES = {
    "DAILY", "WEEKLY", "EVERY_TWO_WEEKS", "THIRTY_DAYS", "SIXTY_DAYS",
    "NINETY_DAYS", "MONTHLY", "EVERY_TWO_MONTHS", "QUARTERLY",
    "EVERY_FOUR_MONTHS", "EVERY_SIX_MONTHS", "ANNUAL", "EVERY_TWO_YEARS",
}
_BILLING_PERIOD_TO_CADENCE = {
    None: "MONTHLY",
    "": "MONTHLY",
    "monthly": "MONTHLY",
    "weekly": "WEEKLY",
    "annual": "ANNUAL",
    "yearly": "ANNUAL",
    "quarterly": "QUARTERLY",
}


def resolve_square_cadence(billing_period) -> str:
    """Map a membership_types.billing_period value to a valid Square
    cadence string. Defensively handles None, empty string, weird
    types — never raises AttributeError on .upper() of a non-string.
    """
    if not isinstance(billing_period, str):
        return "MONTHLY"
    lower = billing_period.strip().lower()
    if lower in _BILLING_PERIOD_TO_CADENCE:
        return _BILLING_PERIOD_TO_CADENCE[lower]
    upper = lower.upper()
    return upper if upper in _SQUARE_CADENCES else "MONTHLY"


async def _resolve_provider(organization_id: str) -> dict:
    """Read the org's billing_provider + the credentials needed for
    Square-mode calls in one trip. Returns:
        {"provider": "stripe" | "square",
         "merchant_access_token": str | None,
         "merchant_location_id": str | None}
    Treats unset / unknown providers as 'stripe' for backward compat
    so existing Stripe-mode studios keep working unchanged.
    """
    async with get_global_db() as db:
        row = await db.fetchrow(
            """
            SELECT billing_provider, square_location_id
            FROM af_global.organizations WHERE id = $1
            """,
            organization_id,
        )
    if not row:
        return {"provider": "stripe", "merchant_access_token": None, "merchant_location_id": None}
    provider = (row["billing_provider"] or "stripe").lower()
    if provider != "square":
        return {"provider": "stripe", "merchant_access_token": None, "merchant_location_id": None}

    # For Square mode, fetch a usable (refreshed if needed) access token.
    access_token = await square_oauth_service.get_merchant_access_token(organization_id)
    if not access_token:
        # Studio has billing_provider='square' but no usable token —
        # this is a misconfiguration. Surface clearly rather than
        # silently falling back to Stripe (which would be confusing).
        logger.error(
            "Square-mode org has no usable access token",
            org_id=organization_id,
        )
        raise ValueError(
            "This studio is configured for Square but has no Square "
            "connection. Reconnect via Settings → Billing."
        )
    return {
        "provider": "square",
        "merchant_access_token": access_token,
        "merchant_location_id": row["square_location_id"],
    }


# ── Payments ───────────────────────────────────────────────────────────


async def create_payment(
    organization_id: str,
    amount_cents: int,
    source_id: str,
    description: str = "AuraFlow payment",
    member_id: Optional[str] = None,
    member_square_customer_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    # Stripe-only — passed through untouched for that provider
    stripe_account_id: Optional[str] = None,
    stripe_customer_id: Optional[str] = None,
) -> dict:
    """Charge `source_id`. Returns:
        {"provider": "stripe" | "square",
         "payment_id": str,         # provider-native ID
         "amount_cents": int,
         "fee_cents": int,           # platform fee deducted/collected
         "status": str,
         "receipt_url": str | None}

    The caller persists payment_id into the matching transactions
    column (stripe_payment_intent_id OR square_payment_id) by reading
    result["provider"].
    """
    if settings.AURAFLOW_BILLING_MODE == "managed":
        from app.services.payments.broker_client import broker_client
        r = await broker_client.charge(
            customer_id=member_square_customer_id, card_id=source_id,
            amount_cents=amount_cents, description=description,
            member_ref=member_id, idempotency_key=idempotency_key)
        return {"provider": "broker", "payment_id": r.get("payment_id"),
                "amount_cents": r.get("amount_cents", amount_cents),
                "fee_cents": r.get("app_fee_cents", 0), "status": r.get("status"),
                "receipt_url": r.get("receipt_url")}
    ctx = await _resolve_provider(organization_id)
    if ctx["provider"] == "square":
        result = await square_service.create_payment_with_app_fee(
            merchant_access_token=ctx["merchant_access_token"],
            merchant_location_id=ctx["merchant_location_id"],
            source_id=source_id,
            amount_cents=amount_cents,
            description=description,
            member_id=member_id,
            customer_id=member_square_customer_id,
            idempotency_key=idempotency_key,
            app_fee_cents=_square_app_fee(amount_cents),
        )
        return {
            "provider": "square",
            "payment_id": result["payment_id"],
            "amount_cents": result["amount_cents"],
            "fee_cents": result["app_fee_cents"],
            "status": result["status"],
            "receipt_url": result.get("receipt_url"),
        }
    # Stripe path — defer to existing service, no behavior change.
    from app.services.payments.stripe_service import StripeService
    stripe_svc = StripeService()
    # Stripe's create_payment_intent already computes the platform fee
    # from STRIPE_PLATFORM_FEE_PERCENT (default 1.25%). Pass through.
    pi = await stripe_svc.create_payment_intent(
        amount_cents=amount_cents,
        description=description,
        member_id=member_id,
        stripe_account_id=stripe_account_id,
        stripe_customer_id=stripe_customer_id,
        idempotency_key=idempotency_key,
    )
    return {
        "provider": "stripe",
        "payment_id": pi["payment_intent_id"],
        "amount_cents": amount_cents,
        "fee_cents": pi.get("application_fee_amount", 0),
        "status": pi["status"],
        "receipt_url": None,  # Stripe receipt URL arrives via webhook
        "client_secret": pi.get("client_secret"),  # for Stripe.js confirm
    }


async def refund_payment(
    organization_id: str,
    payment_id: str,
    amount_cents: int,
    reason: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    # Stripe-only
    stripe_account_id: Optional[str] = None,
) -> dict:
    """Refund a previously-captured payment. payment_id format depends
    on provider — caller looks it up on the transactions row before
    calling. Returns {"provider", "refund_id", "amount_cents", "status"}."""
    if settings.AURAFLOW_BILLING_MODE == "managed":
        from app.services.payments.broker_client import broker_client
        r = await broker_client.refund(
            payment_id=payment_id, amount_cents=amount_cents,
            reason=reason, idempotency_key=idempotency_key)
        return {"provider": "broker", **r}
    ctx = await _resolve_provider(organization_id)
    if ctx["provider"] == "square":
        result = await square_service.refund_payment(
            merchant_access_token=ctx["merchant_access_token"],
            payment_id=payment_id,
            amount_cents=amount_cents,
            reason=reason,
            idempotency_key=idempotency_key,
        )
        return {"provider": "square", **result}
    from app.services.payments.stripe_service import StripeService
    stripe_svc = StripeService()
    result = await stripe_svc.refund_payment(
        payment_intent_id=payment_id,
        amount_cents=amount_cents,
        reason=reason,
        stripe_account_id=stripe_account_id,
    )
    return {"provider": "stripe", **result}


# ── Customers + cards (save-on-file) ───────────────────────────────────


async def ensure_customer(
    organization_id: str,
    member_id: str,
    email: str,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    phone: Optional[str] = None,
    existing_stripe_customer_id: Optional[str] = None,
    existing_square_customer_id: Optional[str] = None,
) -> dict:
    """Get-or-create the provider-side customer record for a member.
    Returns {"provider", "customer_id"}. The caller persists the ID to
    the matching column on the members row."""
    if settings.AURAFLOW_BILLING_MODE == "managed":
        if existing_square_customer_id:
            return {"provider": "broker", "customer_id": existing_square_customer_id, "created": False}
        from app.services.payments.broker_client import broker_client
        r = await broker_client.ensure_customer(
            email=email, first_name=first_name, last_name=last_name,
            phone=phone, member_ref=member_id)
        return {"provider": "broker", "customer_id": r.get("customer_id"), "created": True}
    ctx = await _resolve_provider(organization_id)
    if ctx["provider"] == "square":
        if existing_square_customer_id:
            return {
                "provider": "square",
                "customer_id": existing_square_customer_id,
                "created": False,
            }
        result = await square_service.create_customer(
            merchant_access_token=ctx["merchant_access_token"],
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            member_id=member_id,
        )
        return {"provider": "square", "customer_id": result["customer_id"], "created": True}
    from app.services.payments.stripe_service import StripeService
    stripe_svc = StripeService()
    if existing_stripe_customer_id:
        return {
            "provider": "stripe",
            "customer_id": existing_stripe_customer_id,
            "created": False,
        }
    customer_id = await stripe_svc.get_or_create_customer(
        email=email, first_name=first_name, last_name=last_name, phone=phone,
        member_id=member_id,
    )
    return {"provider": "stripe", "customer_id": customer_id, "created": True}


async def save_card_on_file(
    organization_id: str,
    customer_id: str,
    source_id: str,
    cardholder_name: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> dict:
    """Save a Web Payments SDK / Stripe.js nonce as a saved card.
    Returns {"provider", "card_id"} or {"provider": "stripe",
    "payment_method_id"} for the Stripe side. Honors Don's standing
    rule (feedback_always_save_card): every first payment saves the
    card."""
    if settings.AURAFLOW_BILLING_MODE == "managed":
        from app.services.payments.broker_client import broker_client
        r = await broker_client.save_card(
            customer_id=customer_id, source_id=source_id, cardholder_name=cardholder_name)
        return {"provider": "broker", "card_id": r.get("card_id"),
                "card_brand": r.get("card_brand"), "last_4": r.get("last_4")}
    ctx = await _resolve_provider(organization_id)
    if ctx["provider"] == "square":
        result = await square_service.create_card(
            merchant_access_token=ctx["merchant_access_token"],
            customer_id=customer_id,
            source_id=source_id,
            cardholder_name=cardholder_name,
            idempotency_key=idempotency_key,
        )
        return {"provider": "square", **result}
    from app.services.payments.stripe_service import StripeService
    stripe_svc = StripeService()
    pm = await stripe_svc.attach_payment_method(
        customer_id=customer_id, payment_method_id=source_id,
    )
    return {"provider": "stripe", "payment_method_id": pm["id"]}


# ── Subscriptions (Phase 6 wiring lives here too) ─────────────────────


async def create_subscription(
    organization_id: str,
    customer_id: str,
    card_id: str,
    membership_type_id: str,
    plan_name: str,
    price_cents: int,
    cadence: str = "MONTHLY",
    start_date: Optional[str] = None,
    member_id: Optional[str] = None,
    # Stripe-only path
    stripe_price_id: Optional[str] = None,
    stripe_account_id: Optional[str] = None,
) -> dict:
    """Create a recurring subscription on the studio's payment account.

    For Square: a plan + variation are created the first time this
    runs for a given (studio, membership_type), and the variation IDs
    are cached on `membership_types.square_plan_id /
    square_plan_variation_id`. Subsequent calls reuse the cached IDs.
    """
    ctx = await _resolve_provider(organization_id)
    if ctx["provider"] == "square":
        # Look up cached plan/variation; create on first use.
        async with get_global_db() as db:
            org_row = await db.fetchrow(
                "SELECT schema_name FROM af_global.organizations WHERE id = $1",
                organization_id,
            )
        if not org_row:
            raise ValueError("Organization not found")
        schema = org_row["schema_name"]
        # Tenant-scoped lookup
        from app.db.session import get_tenant_db
        async with get_tenant_db(schema_override=schema) as tdb:
            mt_row = await tdb.fetchrow(
                """
                SELECT square_plan_id, square_plan_variation_id
                FROM membership_types WHERE id = $1
                """,
                membership_type_id,
            )
        plan_variation_id = mt_row["square_plan_variation_id"] if mt_row else None
        if not plan_variation_id:
            plan = await square_service.create_subscription_plan(
                merchant_access_token=ctx["merchant_access_token"],
                name=plan_name,
                price_cents=price_cents,
                cadence=cadence,
            )
            plan_variation_id = plan["plan_variation_id"]
            async with get_tenant_db(schema_override=schema) as tdb:
                await tdb.execute(
                    """
                    UPDATE membership_types
                    SET square_plan_id = $1, square_plan_variation_id = $2
                    WHERE id = $3
                    """,
                    plan["plan_id"], plan_variation_id, membership_type_id,
                )
        sub = await square_service.create_subscription(
            merchant_access_token=ctx["merchant_access_token"],
            merchant_location_id=ctx["merchant_location_id"],
            plan_variation_id=plan_variation_id,
            customer_id=customer_id,
            card_id=card_id,
            start_date=start_date,
            reference_id=member_id,
        )
        return {"provider": "square", **sub}

    from app.services.payments.stripe_service import StripeService
    stripe_svc = StripeService()
    sub = await stripe_svc.create_subscription(
        customer_id=customer_id,
        price_id=stripe_price_id,
        stripe_account_id=stripe_account_id,
    )
    return {"provider": "stripe", **sub}


async def pause_subscription(
    organization_id: str,
    subscription_id: str,
    stripe_account_id: Optional[str] = None,
) -> dict:
    ctx = await _resolve_provider(organization_id)
    if ctx["provider"] == "square":
        result = await square_service.pause_subscription(
            merchant_access_token=ctx["merchant_access_token"],
            subscription_id=subscription_id,
        )
        return {"provider": "square", **result}
    from app.services.payments.stripe_service import StripeService
    stripe_svc = StripeService()
    result = await stripe_svc.pause_subscription(
        subscription_id=subscription_id, stripe_account_id=stripe_account_id,
    )
    return {"provider": "stripe", **result}


async def resume_subscription(
    organization_id: str,
    subscription_id: str,
    stripe_account_id: Optional[str] = None,
) -> dict:
    ctx = await _resolve_provider(organization_id)
    if ctx["provider"] == "square":
        result = await square_service.resume_subscription(
            merchant_access_token=ctx["merchant_access_token"],
            subscription_id=subscription_id,
        )
        return {"provider": "square", **result}
    from app.services.payments.stripe_service import StripeService
    stripe_svc = StripeService()
    result = await stripe_svc.resume_subscription(
        subscription_id=subscription_id, stripe_account_id=stripe_account_id,
    )
    return {"provider": "stripe", **result}


async def cancel_subscription(
    organization_id: str,
    subscription_id: str,
    at_period_end: bool = True,
    stripe_account_id: Optional[str] = None,
) -> dict:
    ctx = await _resolve_provider(organization_id)
    if ctx["provider"] == "square":
        result = await square_service.cancel_subscription(
            merchant_access_token=ctx["merchant_access_token"],
            subscription_id=subscription_id,
        )
        return {"provider": "square", **result}
    from app.services.payments.stripe_service import StripeService
    stripe_svc = StripeService()
    result = await stripe_svc.cancel_subscription(
        subscription_id=subscription_id,
        at_period_end=at_period_end,
        stripe_account_id=stripe_account_id,
    )
    return {"provider": "stripe", **result}


# ── POS (Terminal API) ────────────────────────────────────────────────
#
# These calls are SQUARE-ONLY. Stripe POS is a different product not in
# scope for AuraFlow — Stripe-mode orgs (Your Studio in direct mode) get
# a clear error pointing them to the in-browser Web Payments SDK flow.
#
# The dispatcher's role here is:
#   1. Refuse to fire if billing_provider != 'square'
#   2. Compute the 1% app_fee centrally (same math as create_payment)
#   3. Resolve a device_id when caller doesn't specify one (default
#      device from organizations.square_pos_default_device_id)
#   4. Hand off to square_pos_service for the actual API call
#
# The endpoint layer creates the pos_terminal_checkouts row + enforces
# the amount-vs-source-of-truth check that prevents staff discounts
# (feedback_no_staff_discounts). The dispatcher trusts the amount it
# receives because the endpoint already validated it.


async def _resolve_pos_device(
    organization_id: str,
    requested_device_id: Optional[str] = None,
) -> Optional[str]:
    """Return the Square device_id to charge against. If
    requested_device_id is given, validate it belongs to this org.
    Otherwise return the org's default. Returns None if nothing
    paired — caller should fall back to deep-link or surface an
    error.
    """
    async with get_global_db() as db:
        if requested_device_id:
            row = await db.fetchrow(
                """
                SELECT device_id FROM af_global.square_pos_devices
                WHERE organization_id = $1 AND id = $2
                """,
                organization_id, requested_device_id,
            )
            return row["device_id"] if row else None
        row = await db.fetchrow(
            """
            SELECT d.device_id
            FROM af_global.organizations o
            JOIN af_global.square_pos_devices d
              ON d.id = o.square_pos_default_device_id
            WHERE o.id = $1
            """,
            organization_id,
        )
        if row:
            return row["device_id"]
        # No default set — pick first paired device deterministically
        row = await db.fetchrow(
            """
            SELECT device_id FROM af_global.square_pos_devices
            WHERE organization_id = $1
            ORDER BY paired_at ASC LIMIT 1
            """,
            organization_id,
        )
        return row["device_id"] if row else None


async def create_pos_charge(
    organization_id: str,
    device_id: str,
    amount_cents: int,
    reference_id: str,
    member_square_customer_id: Optional[str] = None,
    description: Optional[str] = None,
) -> dict:
    """Initiate a Terminal API checkout. Square fires
    terminal.checkout.updated when the customer completes/cancels.

    Returns {"provider": "square", "square_checkout_id", "status",
    "app_fee_cents"}.
    """
    ctx = await _resolve_provider(organization_id)
    if ctx["provider"] != "square":
        raise ValueError(
            "POS terminal charges require Square billing. This studio is "
            "on Stripe — use the in-browser card entry flow instead."
        )
    from app.services.payments.square_pos_service import square_pos_service
    app_fee = _square_app_fee(amount_cents)
    result = await square_pos_service.create_terminal_checkout(
        merchant_access_token=ctx["merchant_access_token"],
        device_id=device_id,
        amount_cents=amount_cents,
        reference_id=reference_id,
        customer_id=member_square_customer_id,
        note=description,
        app_fee_cents=app_fee,
    )
    return {
        "provider": "square",
        "square_checkout_id": result["checkout_id"],
        "status": result["status"],
        "app_fee_cents": app_fee,
    }


async def cancel_pos_charge(
    organization_id: str,
    square_checkout_id: str,
) -> dict:
    ctx = await _resolve_provider(organization_id)
    if ctx["provider"] != "square":
        return {"cancelled": False, "reason": "not a Square-mode org"}
    from app.services.payments.square_pos_service import square_pos_service
    return await square_pos_service.cancel_terminal_checkout(
        merchant_access_token=ctx["merchant_access_token"],
        checkout_id=square_checkout_id,
    )


async def charge_saved_card(
    organization_id: str,
    member_square_customer_id: str,
    card_id: str,
    amount_cents: int,
    description: str,
    member_id: Optional[str] = None,
) -> dict:
    """Charge a previously-saved card without re-tokenization. Used for
    one-off charges (a forgotten drop-in, a tip later, etc.) AND as the
    underlying mechanism for recurring renewals via Square Subscriptions
    (subscriptions auto-charge; this path is for staff-initiated charges
    against the same saved card).
    """
    ctx = await _resolve_provider(organization_id)
    if ctx["provider"] != "square":
        raise ValueError("charge_saved_card is Square-only")
    from app.services.payments.square_service import square_service
    return await square_service.create_payment_with_app_fee(
        merchant_access_token=ctx["merchant_access_token"],
        merchant_location_id=ctx["merchant_location_id"],
        source_id=card_id,
        amount_cents=amount_cents,
        description=description,
        member_id=member_id,
        customer_id=member_square_customer_id,
        app_fee_cents=_square_app_fee(amount_cents),
    )


# ── Helpers exposed for endpoints that need the provider directly ──────


async def get_provider(organization_id: str) -> str:
    """Return 'stripe' or 'square' for the org. Used by endpoints that
    need to render different UI elements (e.g. Stripe.js Elements vs
    Square Web Payments SDK)."""
    async with get_global_db() as db:
        row = await db.fetchrow(
            "SELECT billing_provider FROM af_global.organizations WHERE id = $1",
            organization_id,
        )
    if not row:
        return "stripe"
    return (row["billing_provider"] or "stripe").lower()
