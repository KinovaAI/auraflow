"""AuraFlow — Payment Endpoints

Stripe Connect onboarding, transactions, revenue summary, refunds, and failed payments.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.v1.dependencies.auth import get_current_user
from app.api.v1.dependencies.rbac import require_permission
from app.services.payments.stripe_service import StripeService
from app.services.payments.square_service import SquareService
from app.services.payments.square_oauth_service import square_oauth_service
from app.services.payments import billing_dispatcher
from app.services.email.email_service import EmailService
from app.core.config import settings
from app.core.tenant_context import get_organization_id
from app.db.session import get_tenant_db, get_global_db

router = APIRouter()

stripe_svc = StripeService()
square_svc = SquareService()
email_svc = EmailService()


# ── Schemas ──────────────────────────────────────────────────────────────────

class ConnectOnboardRequest(BaseModel):
    return_url: str
    refresh_url: str

class ConnectOnboardResponse(BaseModel):
    url: str

class CheckoutRequest(BaseModel):
    member_id: str
    membership_type_id: str
    success_url: str
    cancel_url: str

class PortalRequest(BaseModel):
    member_id: str
    return_url: str

class RecordTransactionRequest(BaseModel):
    member_id: str
    amount_cents: int
    type: str = "payment"
    description: Optional[str] = None
    stripe_payment_intent_id: Optional[str] = None
    membership_id: Optional[str] = None
    booking_id: Optional[str] = None

class DropInPaymentRequest(BaseModel):
    member_id: str
    amount_cents: int
    description: str = "Drop-in class"

class DropInRecordRequest(BaseModel):
    member_id: str
    amount_cents: int
    payment_intent_id: str
    description: str = "Drop-in class"

class SquarePaymentRequest(BaseModel):
    member_id: str
    amount_cents: int
    source_id: str  # nonce from Square Web Payments SDK
    description: str = "Drop-in class"

class RefundRequest(BaseModel):
    amount_cents: Optional[int] = None
    reason: str = "requested_by_customer"

class TransactionResponse(BaseModel):
    id: str
    member_id: str
    amount_cents: int
    type: str
    status: str
    description: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class RevenueSummaryResponse(BaseModel):
    total_revenue: int
    total_fees: int
    net_revenue: int
    total_refunds: int
    transaction_count: int


def _txn_response(row: dict) -> dict:
    """Serialize a transaction row."""
    out = {}
    for k, v in row.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        elif v is None:
            out[k] = v
        else:
            out[k] = v
    return out


# ── Stripe Connect ───────────────────────────────────────────────────────────

@router.post("/connect/onboard")
async def start_connect_onboarding(
    body: ConnectOnboardRequest,
    user=Depends(get_current_user),
    rbac=Depends(require_permission("payments.setup_connect")),
):
    """Start Stripe Connect onboarding for the studio owner."""
    org_id = get_organization_id()
    owner_email = user.get("email", "")
    try:
        await stripe_svc.create_connect_account(org_id, email=owner_email)
    except Exception as e:
        # Account may already exist — only log unexpected errors
        error_str = str(e).lower()
        if "already" not in error_str and "exists" not in error_str:
            from app.core.logging import logger
            logger.warning("Stripe Connect account creation failed", org_id=org_id, error=str(e))

    # A new account_id may have been written to organizations.stripe_account_id
    # — drop the connect_account cache for this tenant so the next charge call
    # sees the new value immediately instead of waiting for the 60s TTL.
    from app.services.payments.connect_account import invalidate_cache
    invalidate_cache(org_id)

    try:
        link = await stripe_svc.create_account_link(
            org_id, body.return_url, body.refresh_url
        )
        return link
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/connect/status")
async def get_connect_status(rbac=Depends(require_permission("payments.view_connect_status"))):
    """Check the studio's Stripe Connect status."""
    org_id = get_organization_id()
    return await stripe_svc.get_connect_status(org_id)


# ── Checkout Sessions ────────────────────────────────────────────────

@router.post("/checkout")
async def create_checkout_session(
    body: CheckoutRequest,
    rbac=Depends(require_permission("payments.create_checkout")),
):
    """Create a Stripe Checkout session to purchase a membership.

    Stripe-mode only. Square has no hosted Checkout equivalent — for
    square-mode studios the member portal tokenizes the card via Web
    Payments SDK and calls /square/charge (or the upcoming Square
    Subscriptions API path for recurring memberships).
    """
    org_id = get_organization_id()
    provider = await billing_dispatcher.get_provider(org_id)
    if provider == "square":
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Square-mode studios use Web Payments SDK, not Stripe Checkout",
                "code": "WRONG_PROVIDER_FOR_ENDPOINT",
                "billing_provider": "square",
            },
        )
    try:
        result = await stripe_svc.create_checkout_session(
            org_id=org_id,
            member_id=body.member_id,
            membership_type_id=body.membership_type_id,
            success_url=body.success_url,
            cancel_url=body.cancel_url,
        )
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/checkout/{session_id}/verify")
async def verify_checkout_session(
    session_id: str,
    rbac=Depends(require_permission("payments.verify_checkout")),
):
    """Verify a Stripe Checkout session and recover from a missed webhook.

    Stripe Checkout redirects to success_url with session_id appended. The
    frontend should call this on the success page so we can:
      1. Confirm the session was actually paid (defends against the
         user navigating to a forged success URL).
      2. If the checkout.session.completed webhook never landed (network
         glitch, Stripe outage, retry not yet processed), synthesize the
         same outcome locally — assign the membership row and record the
         transaction. Idempotent via the existing webhook dedup table.

    Without this endpoint, a member can pay through Stripe and end up
    with no local membership while ops scrambles to manually fix it.
    """
    org_id = get_organization_id()
    try:
        result = await stripe_svc.verify_and_recover_checkout(
            org_id=org_id, session_id=session_id,
        )
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/portal")
async def create_portal_session(
    body: PortalRequest,
    rbac=Depends(require_permission("payments.create_portal")),
):
    """Create a Stripe Customer Portal session for payment method management."""
    org_id = get_organization_id()
    try:
        result = await stripe_svc.create_customer_portal_session(
            org_id=org_id,
            member_id=body.member_id,
            return_url=body.return_url,
        )
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Transactions ─────────────────────────────────────────────────────────────

@router.post("/transactions")
async def record_transaction(
    body: RecordTransactionRequest,
    rbac=Depends(require_permission("payments.record_transaction")),
):
    """Record a manual transaction (POS payment, drop-in, etc.)."""
    data = body.model_dump()
    # Calculate fees
    fee = int(data["amount_cents"] * settings.STRIPE_PLATFORM_FEE_PERCENT / 100)
    data["fee_cents"] = fee
    data["net_amount_cents"] = data["amount_cents"] - fee
    data["status"] = "completed"

    txn = await stripe_svc.record_transaction(data)
    return {"data": _txn_response(txn)}


@router.get("/transactions")
async def list_transactions(
    member_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    rbac=Depends(require_permission("payments.view_transactions")),
):
    """List transactions, optionally filtered by member."""
    txns = await stripe_svc.list_transactions(
        member_id=member_id, limit=limit, offset=offset
    )
    return {"data": [_txn_response(t) for t in txns]}


@router.get("/transactions/{txn_id}")
async def get_transaction(
    txn_id: str,
    rbac=Depends(require_permission("payments.view_transactions")),
):
    """Get a single transaction."""
    txn = await stripe_svc.get_transaction(txn_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"data": _txn_response(txn)}


@router.post("/transactions/{txn_id}/refund")
async def refund_transaction(
    txn_id: str,
    body: RefundRequest,
    rbac=Depends(require_permission("payments.refund_transaction")),
):
    """Refund a transaction (full or partial). Routes to Stripe OR
    Square based on which provider ID is on the transactions row —
    NOT on the org's current billing_provider, because a refund of an
    old Stripe charge must still flow through Stripe even if the
    studio has since migrated to Square."""
    txn = await stripe_svc.get_transaction(txn_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if txn.get("status") == "refunded":
        raise HTTPException(status_code=400, detail="Transaction already refunded")

    amount = body.amount_cents or txn["amount_cents"]
    if amount <= 0 or amount > txn["amount_cents"]:
        raise HTTPException(status_code=400, detail="Invalid refund amount")

    # Provider routing: square_payment_id on the row → Square refund.
    # Otherwise (legacy stripe_payment_intent_id or no provider ID) →
    # existing Stripe-side refund flow.
    #
    # Call square_service DIRECTLY (not via dispatcher) so the refund
    # routes to Square even if the org has since switched away from
    # Square — refunds must honor the transaction's original provider,
    # not the org's current provider.
    if txn.get("square_payment_id"):
        org_id = get_organization_id()
        access_token = await square_oauth_service.get_merchant_access_token(org_id)
        if not access_token:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": (
                        "This payment was processed on Square, but the studio's "
                        "Square connection is no longer active. Reconnect Square "
                        "in Settings → Billing before refunding."
                    ),
                    "code": "SQUARE_REFUND_NO_CONNECTION",
                },
            )
        square_result = await square_svc.refund_payment(
            merchant_access_token=access_token,
            payment_id=txn["square_payment_id"],
            amount_cents=amount,
            reason=body.reason,
        )
        result = {"provider": "square", **square_result}
        # Persist the refund on the local row (dispatcher.refund_payment
        # talks to Square; the transactions table is our own ledger).
        async with get_tenant_db() as db:
            updated = await db.fetchrow(
                """
                UPDATE transactions
                SET square_refund_id = $2,
                    refund_amount_cents = COALESCE(refund_amount_cents, 0) + $3,
                    refunded_at = NOW(),
                    refund_reason = $4,
                    status = CASE
                        WHEN COALESCE(refund_amount_cents, 0) + $3 >= amount_cents
                            THEN 'refunded' ELSE 'partially_refunded'
                        END,
                    updated_at = NOW()
                WHERE id = $1
                RETURNING *
                """,
                txn_id, result["refund_id"], amount, body.reason,
            )
        return {"data": _txn_response(dict(updated))}

    # Stripe path (unchanged behavior)
    result = await stripe_svc.refund_transaction(txn_id, amount, body.reason)
    if not result:
        raise HTTPException(status_code=400, detail="Refund failed")
    return {"data": _txn_response(result)}


# ── Drop-in Payment Intent (Real Card Charge) ────────────────────────────────

@router.post("/drop-in-intent")
async def create_drop_in_payment_intent(
    body: DropInPaymentRequest,
    rbac=Depends(require_permission("payments.charge_drop_in")),
):
    """Create a Stripe PaymentIntent for a drop-in class charge.

    Stripe-mode only. Square-mode studios collect the card via Web
    Payments SDK on the frontend and POST directly to /square/charge
    (which already enforces the 1% app_fee through the dispatcher).
    """
    org_id = get_organization_id()

    # Provider guard — Square-mode studios use a different frontend flow.
    provider = await billing_dispatcher.get_provider(org_id)
    if provider == "square":
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Use Square Web Payments SDK + /payments/square/charge",
                "code": "WRONG_PROVIDER_FOR_ENDPOINT",
                "billing_provider": "square",
            },
        )

    # Look up member info
    async with get_tenant_db() as db:
        member = await db.fetchrow(
            "SELECT id, email, first_name, last_name FROM members WHERE id = $1",
            body.member_id,
        )
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    # Get Connect account — server-derived from the JWT's org_id only.
    # See app/services/payments/connect_account.py for the chokepoint rule.
    from app.services.payments.connect_account import resolve_stripe_account_for_org
    stripe_account_id = await resolve_stripe_account_for_org(org_id)

    # Get or create Stripe customer
    customer_id = await stripe_svc.get_or_create_customer(
        member_id=body.member_id,
        email=member["email"],
        name=f"{member['first_name']} {member['last_name']}",
        stripe_account_id=stripe_account_id,
    )

    # Create real PaymentIntent
    result = await stripe_svc.create_payment_intent(
        amount_cents=body.amount_cents,
        customer_id=customer_id,
        description=body.description,
        metadata={"member_id": body.member_id, "type": "drop_in"},
        stripe_account_id=stripe_account_id,
    )

    return {"data": result}


@router.post("/drop-in-intent/record")
async def record_drop_in_payment(
    body: DropInRecordRequest,
    rbac=Depends(require_permission("payments.record_drop_in")),
):
    """Record a completed drop-in payment after Stripe confirms success."""
    fee = int(body.amount_cents * settings.STRIPE_PLATFORM_FEE_PERCENT / 100)
    txn = await stripe_svc.record_transaction({
        "member_id": body.member_id,
        "amount_cents": body.amount_cents,
        "type": "drop_in",
        "status": "completed",
        "description": body.description,
        "stripe_payment_intent_id": body.payment_intent_id,
        "fee_cents": fee,
        "net_amount_cents": body.amount_cents - fee,
    })
    return {"data": _txn_response(txn)}


# ── Square Payments ──────────────────────────────────────────────────────────

@router.post("/square/charge")
async def square_charge(
    body: SquarePaymentRequest,
    rbac=Depends(require_permission("payments.charge_square")),
):
    """Process a card payment via Square Web Payments SDK.

    Routes through billing_dispatcher so:
      - The 1% Square app_fee is applied (was 1.25% Stripe rate via bug)
      - The transaction is recorded under the correct *_payment_id column
        for the provider that actually ran (was always going into
        stripe_payment_intent_id which broke refund routing).
    """
    org_id = get_organization_id()
    try:
        result = await billing_dispatcher.create_payment(
            organization_id=org_id,
            amount_cents=body.amount_cents,
            source_id=body.source_id,
            description=body.description or "Drop-in class",
            member_id=body.member_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Payment provider error: {e}")

    provider = result["provider"]
    fee = result.get("fee_cents", 0)
    record_data: dict = {
        "member_id": body.member_id,
        "amount_cents": body.amount_cents,
        "type": "drop_in",
        "status": "completed",
        "description": body.description,
        "fee_cents": fee,
        "net_amount_cents": body.amount_cents - fee,
    }
    if provider == "square":
        record_data["square_payment_id"] = result["payment_id"]
    else:
        record_data["stripe_payment_intent_id"] = result["payment_id"]

    txn = await stripe_svc.record_transaction(record_data)
    return {"data": {**_txn_response(txn), "provider": provider, "payment_id": result["payment_id"]}}


# ── Revenue Summary ──────────────────────────────────────────────────────────

@router.get("/revenue/summary")
async def revenue_summary(
    days: int = Query(30, ge=1, le=365),
    rbac=Depends(require_permission("payments.view_revenue")),
):
    """Get revenue summary for the last N days."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    summary = await stripe_svc.get_revenue_summary(start, end)
    return {"data": summary}


# ── Failed Payments ──────────────────────────────────────────────────────────

@router.get("/failed-payments")
async def list_failed_payments(
    limit: int = Query(50, ge=1, le=200),
    rbac=Depends(require_permission("payments.view_failed")),
):
    """List recent failed payment attempts."""
    failures = await stripe_svc.get_failed_payments(limit)
    return {"data": [_txn_response(f) for f in failures]}


# ── Communication Log ────────────────────────────────────────────────────────

@router.get("/communications")
async def list_communications(
    member_id: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    rbac=Depends(require_permission("payments.view_log")),
):
    """List communication log entries (emails sent, etc.)."""
    logs = await email_svc.list_communications(
        member_id=member_id, channel=channel, limit=limit
    )
    return {"data": [_txn_response(log) for log in logs]}


# ── Square OAuth ──────────────────────────────────────────────────────
# Studios connect their own Square merchant account via the Code Flow.
# Per Don's hard rule (project_app_secret_encryption.md), tokens are
# encrypted at rest via pgp_sym_encrypt with APP_SECRET. Reuses the
# existing payments.setup_connect permission key so any staff member
# who can set up Stripe Connect can also set up Square — same UX
# location in the studio settings.

@router.post("/square/connect/start")
async def square_connect_start(
    rbac: dict = Depends(require_permission("payments.setup_connect")),
):
    """Owner-only. Returns the Square OAuth authorize URL; the frontend
    redirects the browser to it. State token is stored in Redis with
    a 10-minute TTL keyed to this org_id AND the requesting user_id —
    so a stolen state value can't be redeemed by a different user."""
    org_id = get_organization_id()
    url = await square_oauth_service.start_oauth(org_id, user_id=rbac.get("user_id"))
    return {"data": {"authorize_url": url}}


@router.get("/square/connect/callback")
async def square_connect_callback(
    code: str = Query(...),
    state: str = Query(...),
):
    """Public — Square redirects the browser here after consent.
    Exchanges the code for tokens, stores encrypted, flips
    billing_provider='square'. Redirects to the dashboard settings
    page on success/failure with a query param the UI reads."""
    from fastapi.responses import RedirectResponse
    try:
        result = await square_oauth_service.complete_oauth(code, state)
    except ValueError as e:
        return RedirectResponse(
            url=(
                f"{settings.APP_URL}/dashboard/settings/billing"
                f"?square_error={str(e)}"
            ),
        )
    return RedirectResponse(
        url=(
            f"{settings.APP_URL}/dashboard/settings/billing"
            f"?square_connected=true&merchant_id={result['merchant_id']}"
        ),
    )


@router.get("/square/connect/status")
async def square_connect_status(
    rbac: dict = Depends(require_permission("payments.view_connect_status")),
):
    """Current Square connection state for this org."""
    org_id = get_organization_id()
    status = await square_oauth_service.get_status(org_id)
    return {"data": status}


@router.post("/square/connect/disconnect")
async def square_connect_disconnect(
    rbac: dict = Depends(require_permission("payments.setup_connect")),
):
    """Revoke Square access and revert billing_provider to 'stripe'.
    Owner action only — equivalent permission to setting up Connect."""
    org_id = get_organization_id()
    result = await square_oauth_service.disconnect(org_id)
    return {"data": result}


@router.get("/square/platform/invoices")
async def square_platform_invoices(
    limit: int = Query(12, ge=1, le=60),
    rbac: dict = Depends(require_permission("billing.view_invoices")),
):
    """Last N KinovaAI platform invoices for this studio (the $99/mo +
    AI token overage invoices, not member-side payments)."""
    org_id = get_organization_id()
    async with get_global_db() as db:
        rows = await db.fetch(
            """
            SELECT id, square_invoice_id, period_start, period_end,
                   plan_fee_cents, token_overage_cents, token_count,
                   total_cents, status, created_at, paid_at
            FROM af_global.platform_invoices
            WHERE organization_id = $1
            ORDER BY period_start DESC
            LIMIT $2
            """,
            org_id, limit,
        )
    return {
        "data": [
            {
                "id": str(r["id"]),
                "square_invoice_id": r["square_invoice_id"],
                "period_start": r["period_start"].isoformat(),
                "period_end": r["period_end"].isoformat(),
                "plan_fee_cents": r["plan_fee_cents"],
                "token_overage_cents": r["token_overage_cents"],
                "token_count": r["token_count"],
                "total_cents": r["total_cents"],
                "status": r["status"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "paid_at": r["paid_at"].isoformat() if r["paid_at"] else None,
            }
            for r in rows
        ]
    }


# ── Square POS (Terminal API) ─────────────────────────────────────────
#
# These endpoints drive in-person card capture: paired Square Terminal
# devices, Square POS phone app, Square Register. The flow is always:
#   1. Staff hits POST /pos/charge with member_id + amount + (optional)
#      membership_type_id. Server validates amount matches the source
#      row's price (no staff discounts — feedback_no_staff_discounts).
#   2. Server creates pos_terminal_checkouts row, calls Terminal API,
#      device beeps, customer interacts.
#   3. Webhook terminal.checkout.updated → server saves card on file
#      (no hardware prompt — feedback_always_save_card), records
#      transaction, creates membership row if applicable.
#   4. Frontend polls GET /pos/checkouts/{id} to render success/failure.
#
# All endpoints require billing_provider='square'. Stripe-mode orgs are
# refused with a clear error pointing to the in-browser fallback.

class PairDeviceRequest(BaseModel):
    name: str

class POSChargeRequest(BaseModel):
    member_id: str
    amount_cents: int
    description: Optional[str] = None
    device_id: Optional[str] = None       # null = use default
    flow: Optional[str] = None            # null = "terminal" if device available, else error
    # When charging for a class pack / drop-in / membership, pass the
    # source row id so the endpoint can validate amount_cents matches.
    membership_type_id: Optional[str] = None
    class_session_id: Optional[str] = None
    # Workshop walk-in: server enrolls the member into this course
    # automatically once the deeplink callback (or expiry-sweep
    # reconciliation) confirms payment. Without this, the client-side
    # post-success enroll callback never fires because the deeplink
    # navigates the browser away from the page that initiated the
    # charge (Sat 2026-06-13 Sound Bath: 3 paid via POS, 0 enrolled).
    course_id: Optional[str] = None
    # NO discount, override, or comp fields. Ever. (feedback_no_staff_discounts)

class POSChargeSavedCardRequest(BaseModel):
    member_id: str
    amount_cents: int
    description: str


# Device pairing — owner-only

@router.post("/pos/square/devices/pair")
async def pos_pair_device(
    body: PairDeviceRequest,
    rbac: dict = Depends(require_permission("pos.manage_devices")),
):
    """Generate a one-time pairing code. Studio enters the code on their
    Square POS phone app or Terminal device. Frontend polls the get
    endpoint to detect when pairing completes."""
    from app.services.payments.square_pos_service import square_pos_service
    org_id = get_organization_id()
    access_token = await square_oauth_service.get_merchant_access_token(org_id)
    if not access_token:
        raise HTTPException(
            status_code=400,
            detail={"error": "Connect Square first.", "code": "SQUARE_NOT_CONNECTED"},
        )
    async with get_global_db() as db:
        loc_row = await db.fetchrow(
            "SELECT square_location_id FROM af_global.organizations WHERE id = $1",
            org_id,
        )
    location_id = loc_row and loc_row["square_location_id"]
    result = await square_pos_service.create_device_code(
        merchant_access_token=access_token,
        name=body.name,
        merchant_location_id=location_id,
    )
    return {"data": result}


@router.get("/pos/square/devices/codes/{device_code_id}")
async def pos_get_device_code(
    device_code_id: str,
    rbac: dict = Depends(require_permission("pos.manage_devices")),
):
    """Poll a device code until it transitions to PAIRED with a
    device_id. Frontend uses this during the pair-modal flow."""
    from app.services.payments.square_pos_service import square_pos_service
    org_id = get_organization_id()
    access_token = await square_oauth_service.get_merchant_access_token(org_id)
    if not access_token:
        raise HTTPException(status_code=400, detail="Square not connected")
    result = await square_pos_service.get_device_code(
        merchant_access_token=access_token,
        device_code_id=device_code_id,
    )
    # If newly PAIRED and we don't have a local row yet, insert one
    if result.get("status") == "PAIRED" and result.get("device_id"):
        async with get_global_db() as db:
            await db.execute(
                """
                INSERT INTO af_global.square_pos_devices
                    (organization_id, device_id, name, status, paired_at)
                VALUES ($1, $2, $3, 'paired', NOW())
                ON CONFLICT (organization_id, device_id) DO UPDATE
                    SET name = EXCLUDED.name,
                        status = 'paired',
                        updated_at = NOW()
                """,
                org_id, result["device_id"], result.get("name") or "Square device",
            )
            # If org has no default device yet, make this the default
            await db.execute(
                """
                UPDATE af_global.organizations
                SET square_pos_default_device_id = (
                    SELECT id FROM af_global.square_pos_devices
                    WHERE organization_id = $1 AND device_id = $2
                )
                WHERE id = $1 AND square_pos_default_device_id IS NULL
                """,
                org_id, result["device_id"],
            )
    return {"data": result}


@router.get("/pos/square/devices")
async def pos_list_devices(
    rbac: dict = Depends(require_permission("pos.manage_devices")),
):
    """List devices paired with this org. Status / last_seen come from
    our cache; Square's live state can be requested via the test endpoint."""
    org_id = get_organization_id()
    async with get_global_db() as db:
        rows = await db.fetch(
            """
            SELECT d.id, d.device_id, d.name, d.device_type, d.status,
                   d.paired_at, d.last_seen_at,
                   (o.square_pos_default_device_id = d.id) AS is_default
            FROM af_global.square_pos_devices d
            LEFT JOIN af_global.organizations o ON o.id = d.organization_id
            WHERE d.organization_id = $1
            ORDER BY d.paired_at DESC
            """,
            org_id,
        )
    return {
        "data": [
            {
                "id": str(r["id"]),
                "device_id": r["device_id"],
                "name": r["name"],
                "device_type": r["device_type"],
                "status": r["status"],
                "paired_at": r["paired_at"].isoformat() if r["paired_at"] else None,
                "last_seen_at": r["last_seen_at"].isoformat() if r["last_seen_at"] else None,
                "is_default": r["is_default"],
            }
            for r in rows
        ]
    }


class RenameDeviceRequest(BaseModel):
    name: Optional[str] = None
    set_as_default: Optional[bool] = None

@router.put("/pos/square/devices/{device_pk}")
async def pos_rename_device(
    device_pk: str,
    body: RenameDeviceRequest,
    rbac: dict = Depends(require_permission("pos.manage_devices")),
):
    """Rename a paired device and/or mark it as the org's default."""
    org_id = get_organization_id()
    async with get_global_db() as db:
        exists = await db.fetchval(
            "SELECT 1 FROM af_global.square_pos_devices WHERE id = $1 AND organization_id = $2",
            device_pk, org_id,
        )
        if not exists:
            raise HTTPException(status_code=404, detail="Device not found")
        if body.name is not None:
            await db.execute(
                "UPDATE af_global.square_pos_devices SET name = $1, updated_at = NOW() WHERE id = $2",
                body.name[:100], device_pk,
            )
        if body.set_as_default:
            await db.execute(
                "UPDATE af_global.organizations SET square_pos_default_device_id = $1 WHERE id = $2",
                device_pk, org_id,
            )
    return {"data": {"id": device_pk, "renamed": body.name is not None,
                     "set_as_default": bool(body.set_as_default)}}


@router.delete("/pos/square/devices/{device_pk}")
async def pos_unpair_device(
    device_pk: str,
    rbac: dict = Depends(require_permission("pos.manage_devices")),
):
    """Remove a device from this org. Square-side unpairing happens
    independently on the device itself; this just stops AuraFlow from
    routing charges to it."""
    org_id = get_organization_id()
    async with get_global_db() as db:
        deleted = await db.fetchval(
            """
            DELETE FROM af_global.square_pos_devices
            WHERE id = $1 AND organization_id = $2
            RETURNING device_id
            """,
            device_pk, org_id,
        )
    if not deleted:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"data": {"unpaired": True, "device_id": deleted}}


# POS charge

async def _validate_pos_amount(
    member_id: str,
    amount_cents: int,
    membership_type_id: Optional[str],
    class_session_id: Optional[str],
) -> tuple[Optional[str], int]:
    """Enforce: the requested amount MUST match the source row's price.
    Returns (description, price_cents). Raises 400 on mismatch.

    Don's rule: staff NEVER apply discounts (feedback_no_staff_discounts).
    The amount field on the request is treated as a checksum, not a
    pricing input — if it differs from the source row, reject the call
    rather than silently re-pricing.
    """
    async with get_tenant_db() as db:
        if membership_type_id:
            row = await db.fetchrow(
                "SELECT name, price_cents FROM membership_types WHERE id = $1 AND is_active = TRUE",
                membership_type_id,
            )
            if not row:
                raise HTTPException(status_code=404, detail="Membership type not found")
            if amount_cents != row["price_cents"]:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": (
                            f"Amount mismatch: this plan costs "
                            f"${row['price_cents']/100:.2f}. Staff cannot apply "
                            f"discounts — owner must adjust the plan price."
                        ),
                        "code": "AMOUNT_MISMATCH_NO_DISCOUNT",
                        "expected_cents": row["price_cents"],
                    },
                )
            return (row["name"], row["price_cents"])

        if class_session_id:
            row = await db.fetchrow(
                """
                SELECT cs.drop_in_price_cents, ct.name
                FROM class_sessions cs
                JOIN class_types ct ON ct.id = cs.class_type_id
                WHERE cs.id = $1
                """,
                class_session_id,
            )
            if not row or row["drop_in_price_cents"] is None:
                raise HTTPException(status_code=404, detail="Class session / price not found")
            if amount_cents != row["drop_in_price_cents"]:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": (
                            f"Amount mismatch: this drop-in costs "
                            f"${row['drop_in_price_cents']/100:.2f}. Staff cannot "
                            f"apply discounts."
                        ),
                        "code": "AMOUNT_MISMATCH_NO_DISCOUNT",
                        "expected_cents": row["drop_in_price_cents"],
                    },
                )
            return (f"Drop-in: {row['name']}", row["drop_in_price_cents"])

    # Ad-hoc charge with no source row — staff manually entered the
    # amount. No discount-vs-source check applies; just pass through.
    # (This path exists for tip-after, lost-card-fee, etc.)
    return (None, amount_cents)


@router.post("/pos/charge")
async def pos_charge(
    body: POSChargeRequest,
    rbac: dict = Depends(require_permission("pos.charge")),
):
    """Initiate a POS Terminal checkout for an in-person sale. Returns
    a checkout_id the frontend polls until the device reports
    completion. Card on file is saved automatically post-completion
    (no toggle, no prompt — feedback_always_save_card)."""
    from app.services.payments.square_pos_service import square_pos_service

    org_id = get_organization_id()
    description, validated_amount = await _validate_pos_amount(
        body.member_id, body.amount_cents, body.membership_type_id, body.class_session_id,
    )
    description = body.description or description or "POS sale"

    # Look up the member + ensure their Square Customer record exists.
    # phone is PHI — stored as phone_enc, decrypted via phi_helpers.
    from app.services.members.phi_helpers import decrypt_phone
    async with get_tenant_db() as db:
        member = await db.fetchrow(
            "SELECT id, first_name, last_name, email, phone_enc, square_customer_id FROM members WHERE id = $1",
            body.member_id,
        )
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    member_phone = decrypt_phone(member)

    square_customer_id = member["square_customer_id"]
    if not square_customer_id and member["email"]:
        cust = await billing_dispatcher.ensure_customer(
            organization_id=org_id,
            member_id=body.member_id,
            email=member["email"],
            first_name=member["first_name"],
            last_name=member["last_name"],
            phone=member_phone,
        )
        square_customer_id = cust["customer_id"]
        async with get_tenant_db() as db:
            await db.execute(
                "UPDATE members SET square_customer_id = $2 WHERE id = $1",
                body.member_id, square_customer_id,
            )

    # Resolve device — if none paired, fail with a clear error
    device_id = await billing_dispatcher._resolve_pos_device(
        org_id, body.device_id,
    )
    if not device_id:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "No Square device paired with this studio. "
                         "Pair one in Settings → Square POS.",
                "code": "NO_POS_DEVICE",
            },
        )

    # Insert pos_terminal_checkouts row FIRST so we have a stable
    # reference_id to pass into Square (and a row to update from the
    # webhook even if the Square call hangs).
    async with get_tenant_db() as db:
        checkout_row = await db.fetchrow(
            """
            INSERT INTO pos_terminal_checkouts
                (member_id, amount_cents, app_fee_cents, description,
                 device_id, flow, square_customer_id, membership_type_id,
                 status, initiated_by_user_id)
            VALUES ($1, $2, $3, $4, $5, 'terminal', $6, $7, 'pending', $8)
            RETURNING id
            """,
            body.member_id, validated_amount,
            billing_dispatcher._square_app_fee(validated_amount),
            description, device_id, square_customer_id,
            body.membership_type_id, rbac.get("user_id"),
        )
        local_id = str(checkout_row["id"])

    # O(1) global index for the deeplink return path (so the public
    # callback can find this row's tenant schema without iterating)
    async with get_global_db() as gdb:
        org_schema = await gdb.fetchval(
            "SELECT schema_name FROM af_global.organizations WHERE id=$1", org_id,
        )
        if org_schema:
            await gdb.execute(
                """
                INSERT INTO af_global.pos_checkout_index (checkout_id, schema_name)
                VALUES ($1::uuid, $2)
                ON CONFLICT (checkout_id) DO NOTHING
                """,
                local_id, org_schema,
            )

    # Fire to Square
    try:
        result = await billing_dispatcher.create_pos_charge(
            organization_id=org_id,
            device_id=device_id,
            amount_cents=validated_amount,
            reference_id=local_id,
            member_square_customer_id=square_customer_id,
            description=description,
        )
    except Exception as e:
        async with get_tenant_db() as db:
            await db.execute(
                """
                UPDATE pos_terminal_checkouts
                SET status='failed', failure_reason=$2, completed_at=NOW()
                WHERE id=$1
                """,
                local_id, str(e)[:500],
            )
        raise HTTPException(status_code=502, detail=f"Square error: {e}")

    async with get_tenant_db() as db:
        await db.execute(
            """
            UPDATE pos_terminal_checkouts
            SET square_checkout_id=$2, status='in_progress'
            WHERE id=$1
            """,
            local_id, result["square_checkout_id"],
        )

    return {
        "data": {
            "checkout_id": local_id,
            "square_checkout_id": result["square_checkout_id"],
            "status": "in_progress",
            "flow": "terminal",
            "device_id": device_id,
            "amount_cents": validated_amount,
            "app_fee_cents": result["app_fee_cents"],
        }
    }


@router.get("/pos/checkouts/{checkout_id}")
async def pos_get_checkout(
    checkout_id: str,
    rbac: dict = Depends(require_permission("pos.charge")),
):
    """Poll the state of a POS checkout. Frontend hits this every
    1-2 seconds until status ∈ {completed, cancelled, failed, expired}.

    Side effect: if status is still pending/in_progress AND we have a
    square_checkout_id, we ALSO call Square to grab fresh state — that
    way the UI catches up even if a webhook is delayed."""
    from app.services.payments.square_pos_service import square_pos_service
    org_id = get_organization_id()
    async with get_tenant_db() as db:
        row = await db.fetchrow(
            "SELECT * FROM pos_terminal_checkouts WHERE id = $1",
            checkout_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Checkout not found")

    # Live-refresh if pending/in_progress and we have a square_checkout_id
    if row["status"] in ("pending", "in_progress") and row["square_checkout_id"]:
        try:
            access_token = await square_oauth_service.get_merchant_access_token(org_id)
            if access_token:
                live = await square_pos_service.get_terminal_checkout(
                    merchant_access_token=access_token,
                    checkout_id=row["square_checkout_id"],
                )
                if live["status"] in ("COMPLETED", "CANCELED", "CANCEL_REQUESTED"):
                    # Webhook will reconcile; just surface latest state
                    pass
                row = {**dict(row), "_live_status": live["status"]}
        except Exception:
            pass  # fall back to local state

    return {
        "data": {
            "checkout_id": str(row["id"]),
            "square_checkout_id": row.get("square_checkout_id"),
            "status": row.get("_live_status", "").lower().replace("_requested", "")
                      if row.get("_live_status") else row["status"],
            "amount_cents": row["amount_cents"],
            "device_id": row.get("device_id"),
            "completed_at": row["completed_at"].isoformat() if row.get("completed_at") else None,
            "failure_reason": row.get("failure_reason"),
            "square_payment_id": row.get("square_payment_id"),
            "square_card_id": row.get("square_card_id"),
            "membership_type_id": str(row["membership_type_id"]) if row.get("membership_type_id") else None,
        }
    }


@router.post("/pos/checkouts/{checkout_id}/cancel")
async def pos_cancel_checkout(
    checkout_id: str,
    rbac: dict = Depends(require_permission("pos.charge")),
):
    """Staff aborts an in-flight POS checkout. Best-effort: tells
    Square to cancel, marks our row cancelled. If the customer already
    tapped, Square may return COMPLETED and the webhook will fix the
    state on its own."""
    org_id = get_organization_id()
    async with get_tenant_db() as db:
        row = await db.fetchrow(
            "SELECT square_checkout_id, status FROM pos_terminal_checkouts WHERE id = $1",
            checkout_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Checkout not found")
    if row["status"] not in ("pending", "in_progress"):
        return {"data": {"cancelled": False, "status": row["status"], "reason": "not in-flight"}}

    if row["square_checkout_id"]:
        try:
            await billing_dispatcher.cancel_pos_charge(org_id, row["square_checkout_id"])
        except Exception:
            pass  # local cancel still wins

    async with get_tenant_db() as db:
        await db.execute(
            """
            UPDATE pos_terminal_checkouts
            SET status='cancelled', completed_at=NOW(), failure_reason='cancelled_by_staff'
            WHERE id=$1 AND status IN ('pending','in_progress')
            """,
            checkout_id,
        )
    return {"data": {"cancelled": True}}


@router.post("/pos/charge-saved-card")
async def pos_charge_saved_card(
    body: POSChargeSavedCardRequest,
    rbac: dict = Depends(require_permission("pos.charge_saved_card")),
):
    """Charge a member's saved Square card without hardware. Used for
    "they forgot to pay" scenarios or other ad-hoc staff-initiated
    charges. Routes through billing_dispatcher.charge_saved_card so the
    1% app_fee is applied."""
    org_id = get_organization_id()
    async with get_tenant_db() as db:
        member = await db.fetchrow(
            """
            SELECT id, square_customer_id, square_card_on_file_id,
                   first_name, last_name
            FROM members WHERE id = $1
            """,
            body.member_id,
        )
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    if not member["square_card_on_file_id"] or not member["square_customer_id"]:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "No saved card on file for this member.",
                "code": "NO_CARD_ON_FILE",
            },
        )

    if body.amount_cents <= 0:
        raise HTTPException(status_code=400, detail="amount_cents must be > 0")

    try:
        result = await billing_dispatcher.charge_saved_card(
            organization_id=org_id,
            member_square_customer_id=member["square_customer_id"],
            card_id=member["square_card_on_file_id"],
            amount_cents=body.amount_cents,
            description=body.description,
            member_id=body.member_id,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Square error: {e}")

    # Record transaction (idempotent on square_payment_id)
    txn = await stripe_svc.record_transaction({
        "member_id": body.member_id,
        "amount_cents": body.amount_cents,
        "type": "saved_card_charge",
        "status": "completed",
        "description": body.description,
        "fee_cents": result.get("app_fee_cents", 0),
        "net_amount_cents": body.amount_cents - result.get("app_fee_cents", 0),
        "square_payment_id": result["payment_id"],
    })
    return {"data": {**_txn_response(txn), "payment_id": result["payment_id"]}}


# ── Square POS deep-link (phone Square POS app) ─────────────────────────
#
# This is the alternative to the Terminal API path. Use when the studio
# doesn't have Square hardware paired — the staff opens the Square POS
# app on their phone via the square-commerce-v1:// URL scheme, completes
# the sale there, and Square POS deep-links back to AuraFlow's callback
# URL with the result. No device-code pairing required.

class POSDeeplinkChargeRequest(BaseModel):
    member_id: str
    amount_cents: int
    description: Optional[str] = None
    membership_type_id: Optional[str] = None
    class_session_id: Optional[str] = None


@router.post("/pos/deeplink-charge")
async def pos_deeplink_charge(
    body: POSDeeplinkChargeRequest,
    rbac: dict = Depends(require_permission("pos.charge")),
):
    """Initiate a Square POS deep-link charge. Returns the
    square-commerce-v1:// URL the frontend opens (which launches the
    Square POS app on the same phone). Square POS captures the payment
    and deep-links back to our callback endpoint with the result."""
    from app.services.payments.square_pos_service import square_pos_service
    from app.core.config import settings as _settings

    org_id = get_organization_id()
    description, validated_amount = await _validate_pos_amount(
        body.member_id, body.amount_cents, body.membership_type_id, body.class_session_id,
    )
    description = body.description or description or "POS sale"

    async with get_tenant_db() as db:
        member = await db.fetchrow(
            "SELECT id, first_name, last_name, email, phone_enc, square_customer_id FROM members WHERE id = $1",
            body.member_id,
        )
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    from app.services.members.phi_helpers import decrypt_phone
    member_phone = decrypt_phone(member)

    square_customer_id = member["square_customer_id"]
    if not square_customer_id and member["email"]:
        cust = await billing_dispatcher.ensure_customer(
            organization_id=org_id,
            member_id=body.member_id,
            email=member["email"],
            first_name=member["first_name"],
            last_name=member["last_name"],
            phone=member_phone,
        )
        square_customer_id = cust["customer_id"]
        async with get_tenant_db() as db:
            await db.execute(
                "UPDATE members SET square_customer_id = $2 WHERE id = $1",
                body.member_id, square_customer_id,
            )

    # Insert the in-flight row FIRST so the callback can find it by
    # reference_id (which is our row's UUID).
    async with get_tenant_db() as db:
        checkout_row = await db.fetchrow(
            """
            INSERT INTO pos_terminal_checkouts
                (member_id, amount_cents, app_fee_cents, description,
                 flow, square_customer_id, membership_type_id, course_id,
                 status, initiated_by_user_id)
            VALUES ($1, $2, $3, $4, 'deeplink', $5, $6, $7, 'pending', $8)
            RETURNING id
            """,
            body.member_id, validated_amount,
            billing_dispatcher._square_app_fee(validated_amount),
            description, square_customer_id,
            body.membership_type_id, body.course_id,
            rbac.get("user_id"),
        )
        local_id = str(checkout_row["id"])

    # O(1) global lookup so the public /pos/deeplink-return callback
    # doesn't have to iterate every tenant to find this row.
    async with get_global_db() as gdb:
        org_schema = await gdb.fetchval(
            "SELECT schema_name FROM af_global.organizations WHERE id=$1", org_id,
        )
        if org_schema:
            await gdb.execute(
                """
                INSERT INTO af_global.pos_checkout_index (checkout_id, schema_name)
                VALUES ($1::uuid, $2)
                ON CONFLICT (checkout_id) DO NOTHING
                """,
                local_id, org_schema,
            )

    if not _settings.SQUARE_OAUTH_APPLICATION_ID:
        raise HTTPException(status_code=500, detail="Square application_id not configured")

    # callback_url MUST exactly match the URL registered in Square's
    # Developer Console → Point of Sale API → Web callback URLs. Square
    # rejects any URL with appended query strings. We carry our
    # checkout_id via the `state` field, signed with APP_SECRET so an
    # attacker can't forge a callback for a checkout_id they guessed.
    from app.services.payments.square_pos_service import _sign_checkout_state
    callback_url = f"{_settings.APP_URL}/pos/return"
    signed_state = _sign_checkout_state(local_id)
    ios_url = square_pos_service.build_pos_deeplink(
        amount_cents=validated_amount,
        callback_url=callback_url,
        client_id=_settings.SQUARE_OAUTH_APPLICATION_ID,
        notes=description,
        platform="ios",
        state=signed_state,
    )
    android_url = square_pos_service.build_pos_deeplink(
        amount_cents=validated_amount,
        callback_url=callback_url,
        client_id=_settings.SQUARE_OAUTH_APPLICATION_ID,
        notes=description,
        platform="android",
        state=signed_state,
    )

    return {
        "data": {
            "checkout_id": local_id,
            "flow": "deeplink",
            "status": "pending",
            "amount_cents": validated_amount,
            "ios_url": ios_url,
            "android_url": android_url,
            "callback_url": callback_url,
        }
    }


@router.get("/pos/deeplink-return")
async def pos_deeplink_return(
    data: Optional[str] = Query(None),
    error_code: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
):
    """Public callback hit by Square POS after the phone-side sale
    completes (or is cancelled). Square passes the result as a JSON
    blob in `data`, or an `error_code` on failure. Our checkout_id
    rides inside `data.state` (Square preserves the state param).

    Returns a 302 RedirectResponse to /dashboard/pos so the staff
    phone lands back in AuraFlow instead of staring at a JSON blob.
    """
    import json as _json
    from app.db.session import get_global_db as _gg
    from fastapi.responses import RedirectResponse
    from app.core.config import settings as _settings

    def _redirect(status: str, checkout_id_for_url: str = "", extra: str = "") -> RedirectResponse:
        params = f"pos_status={status}"
        if checkout_id_for_url:
            params += f"&checkout_id={checkout_id_for_url}"
        if extra:
            params += f"&{extra}"
        # Generic dashboard POS landing; the page picks up the params
        # and shows a toast. We don't know which tenant slug this is
        # since the callback is public, so the user lands on the
        # app-root POS page.
        return RedirectResponse(url=f"{_settings.APP_URL}/dashboard/pos?{params}", status_code=302)

    # Parse data first to extract the signed state
    payload = {}
    try:
        if data:
            payload = _json.loads(data)
    except Exception:
        pass
    signed_state = payload.get("state")
    if not signed_state:
        return _redirect("no_state")

    # CRITICAL: verify HMAC signature before trusting the checkout_id.
    # Without this, anyone with a callback URL could forge completions.
    from app.services.payments.square_pos_service import verify_checkout_state
    checkout_id = verify_checkout_state(signed_state)
    if not checkout_id:
        logger.warning(
            "Square POS callback rejected — invalid state signature",
            raw_state_prefix=str(signed_state)[:40],
        )
        return _redirect("invalid_state")

    # O(1) schema lookup via the global index (was: iterate every org)
    async with _gg() as gdb:
        idx = await gdb.fetchrow(
            "SELECT schema_name FROM af_global.pos_checkout_index WHERE checkout_id = $1::uuid",
            checkout_id,
        )
    if not idx:
        return _redirect("checkout_not_found", checkout_id)
    schema = idx["schema_name"]

    async with get_tenant_db(schema_override=schema) as tdb:
        local = await tdb.fetchrow(
            "SELECT * FROM pos_terminal_checkouts WHERE id = $1",
            checkout_id,
        )
    if not local:
        return _redirect("checkout_not_found", checkout_id)

    if error_code:
        async with get_tenant_db(schema_override=schema) as tdb:
            await tdb.execute(
                """
                UPDATE pos_terminal_checkouts
                SET status='failed', completed_at=NOW(),
                    failure_reason=$2
                WHERE id=$1 AND status IN ('pending','in_progress')
                """,
                checkout_id, (error_description or error_code)[:500],
            )
        return _redirect("failed", checkout_id, f"error={error_code}")

    # Success path — payload already parsed up top to extract state.
    # NOTE: Square POS deeplink returns `transaction_id` (the legacy
    # Transactions API ID), NOT a Payments API `payment_id`. Storing it
    # as `square_payment_id` polluted our DB with IDs that don't exist
    # in the Payments API (Sat 2026-06-13 Shoshana Geron: stored
    # `pMDeSGOOIdCVSrPgoGaFZwNuPHTZY` which Square doesn't recognize).
    # We persist it ONLY in `square_pos_transaction_id` for traceability;
    # the real `square_payment_id` is backfilled by
    # pos_checkout_expiry.reconcile_with_square via Payments API search.
    pos_txn_id = payload.get("transaction_id") or payload.get("client_transaction_id")

    # POS deeplink doesn't support app_fee_money — we have no real 1%
    # take here regardless of what app_fee_cents the row claimed.
    actual_fee = 0

    async with get_tenant_db(schema_override=schema) as tdb:
        async with tdb.transaction():
            await tdb.execute(
                """
                UPDATE pos_terminal_checkouts
                SET status='completed', completed_at=NOW()
                WHERE id=$1
                """,
                checkout_id,
            )
            # Idempotent ledger insert — SELECT-then-INSERT keyed off the
            # checkout id stuffed into description (transactions table has
            # no unique on pos_checkout_id, but description carries it).
            existing_txn = await tdb.fetchval(
                """
                SELECT id FROM transactions
                WHERE member_id = $1 AND type = 'pos_sale'
                  AND created_at >= NOW() - INTERVAL '24 hours'
                  AND amount_cents = $2
                  AND description LIKE '%' || $3 || '%'
                """,
                local["member_id"], local["amount_cents"], str(checkout_id)[:8],
            )
            if existing_txn:
                txn_db_id = existing_txn
            else:
                row = await tdb.fetchrow(
                    """
                    INSERT INTO transactions
                        (member_id, amount_cents, type, status, description,
                         fee_cents, net_amount_cents, created_at)
                    VALUES ($1, $2, 'pos_sale', 'completed', $3, $4, $5, NOW())
                    RETURNING id
                    """,
                    local["member_id"], local["amount_cents"],
                    f"{local['description'] or 'POS sale (phone)'} [ck:{str(checkout_id)[:8]}]",
                    actual_fee, local["amount_cents"] - actual_fee,
                )
                txn_db_id = row["id"]

            # Workshop walk-in path: enroll the member in the course
            # idempotently. UNIQUE (course_id, member_id) on
            # course_enrollments stops dup inserts when the
            # expiry-sweep reconciler races with the callback.
            if local.get("course_id"):
                await tdb.execute(
                    """
                    INSERT INTO course_enrollments
                        (course_id, member_id, status, paid_price_cents,
                         transaction_id, enrolled_at)
                    VALUES ($1, $2, 'enrolled', $3, $4, NOW())
                    ON CONFLICT (course_id, member_id) DO NOTHING
                    """,
                    local["course_id"], local["member_id"],
                    local["amount_cents"], txn_db_id,
                )

    logger.info(
        "POS deeplink callback reconciled",
        checkout_id=str(checkout_id), pos_txn_id=pos_txn_id,
        course_id=str(local.get("course_id")) if local.get("course_id") else None,
    )

    return _redirect("completed", checkout_id)
