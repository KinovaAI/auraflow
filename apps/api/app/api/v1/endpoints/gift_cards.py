"""AuraFlow — Gift Card Endpoints

Purchase, redeem, manage, and check balance on gift cards.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.v1.dependencies.auth import get_current_user
from app.api.v1.dependencies.rbac import require_permission
from app.services.payments.gift_card_service import GiftCardService

router = APIRouter()
gift_card_svc = GiftCardService()


# ── Schemas ──────────────────────────────────────────────────────────────────

class CreateGiftCardRequest(BaseModel):
    amount_cents: int = Field(..., gt=0, description="Gift card value in cents")
    purchaser_member_id: Optional[str] = None
    recipient_email: Optional[str] = None
    recipient_name: Optional[str] = None
    message: Optional[str] = None
    purchased_by_name: Optional[str] = None
    expires_at: Optional[datetime] = None
    # Payment method is required for new flows. Stripe-based methods
    # (card / stripe / send_payment_link) return a checkout URL and
    # defer the gift-card row creation to the webhook. Non-Stripe
    # methods (cash / check / comp / venmo) create the card row
    # immediately and record a transaction.
    payment_method: Optional[str] = Field(
        None,
        description="card / stripe / send_payment_link / cash / check / comp / venmo",
    )
    success_url: Optional[str] = None  # required for Stripe payment_methods
    cancel_url: Optional[str] = None   # required for Stripe payment_methods


class GiftCardResponse(BaseModel):
    id: str
    code: str
    amount_cents: int
    # Legacy alias used by the portal/staff frontend — same value as
    # amount_cents, kept on the response so existing UI keeps working.
    initial_amount_cents: Optional[int] = None
    balance_cents: int
    status: str
    purchaser_member_id: Optional[str] = None
    purchased_by_name: Optional[str] = None
    recipient_email: Optional[str] = None
    recipient_name: Optional[str] = None
    message: Optional[str] = None
    expires_at: Optional[datetime] = None
    voided_at: Optional[datetime] = None
    void_reason: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # Optional, only populated by /gift-cards/my — tells the portal
    # whether the calling member bought this card, received it, or both.
    relationship: Optional[str] = None

    class Config:
        from_attributes = True


class GiftCardDetailResponse(GiftCardResponse):
    redemptions: list[dict] = []


class CreateGiftCardResponse(BaseModel):
    """POST /gift-cards returns either the created card (immediate payment
    methods) OR a Stripe checkout URL (deferred until webhook fires)."""
    gift_card: Optional[GiftCardResponse] = None
    checkout_url: Optional[str] = None
    checkout_session_id: Optional[str] = None
    payment_method: str


class CheckBalanceRequest(BaseModel):
    code: str


class CheckBalanceResponse(BaseModel):
    id: str
    code: str
    amount_cents: int
    balance_cents: int
    status: str
    recipient_name: Optional[str] = None
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class RedeemRequest(BaseModel):
    code: str
    amount_cents: Optional[int] = Field(None, gt=0, description="Amount to redeem; null = full balance")


class RedeemResponse(BaseModel):
    id: str
    gift_card_id: str
    member_id: str
    amount_cents: int
    transaction_id: Optional[str] = None
    created_at: Optional[datetime] = None


class VoidRequest(BaseModel):
    reason: Optional[str] = None


class AdjustRequest(BaseModel):
    amount_cents: int = Field(..., description="Positive to add, negative to subtract")
    reason: str


class ApplyToTransactionRequest(BaseModel):
    code: str
    transaction_amount_cents: int = Field(..., gt=0)


class ApplyToTransactionResponse(BaseModel):
    discount_cents: int
    remaining_balance: int
    gift_card_id: str


# ── Public / Member Endpoints (registered first to avoid path-param capture) ─

@router.post("/check-balance", response_model=CheckBalanceResponse)
async def check_balance(body: CheckBalanceRequest):
    """Check gift card balance by code (no auth required)."""
    try:
        result = await gift_card_svc.check_balance(body.code)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/redeem", response_model=RedeemResponse)
async def redeem_gift_card(
    body: RedeemRequest,
    user=Depends(get_current_user),
):
    """Redeem a gift card onto the authenticated member's account."""
    try:
        result = await gift_card_svc.redeem_gift_card(
            code=body.code,
            member_id=user["id"],
            amount_cents=body.amount_cents,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/apply", response_model=ApplyToTransactionResponse)
async def apply_to_transaction(
    body: ApplyToTransactionRequest,
    user=Depends(get_current_user),
):
    """Apply a gift card during checkout."""
    try:
        result = await gift_card_svc.apply_to_transaction(
            code=body.code,
            transaction_amount_cents=body.transaction_amount_cents,
            member_id=user["id"],
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Admin Endpoints ──────────────────────────────────────────────────────────

@router.post("", response_model=CreateGiftCardResponse)
async def create_gift_card(
    body: CreateGiftCardRequest,
    user=Depends(require_permission("gift_cards.purchase")),
):
    """Purchase a gift card.

    - Stripe payment methods (`card`, `stripe`, `send_payment_link`):
      returns a checkout URL. The card row is created by the Stripe
      webhook handler when payment confirms — no row is inserted now.
    - Cash / check / comp / venmo: creates the card immediately and
      records a transaction with the chosen payment method.

    A gift card can no longer be created without specifying a payment
    method (the legacy "free" path is gone — that allowed members to
    self-issue $1000 cards for nothing).
    """
    if not body.payment_method:
        raise HTTPException(
            status_code=400,
            detail="payment_method is required (card / stripe / send_payment_link / cash / check / comp / venmo)",
        )
    if not body.recipient_email or not body.recipient_email.strip():
        raise HTTPException(
            status_code=400,
            detail="recipient_email is required — the gift card code is emailed there",
        )
    try:
        result = await gift_card_svc.purchase_gift_card(
            amount_cents=body.amount_cents,
            payment_method=body.payment_method,
            purchaser_member_id=body.purchaser_member_id,
            recipient_email=body.recipient_email,
            recipient_name=body.recipient_name,
            message=body.message,
            purchased_by_name=body.purchased_by_name,
            expires_at=body.expires_at,
            success_url=body.success_url,
            cancel_url=body.cancel_url,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return CreateGiftCardResponse(
        gift_card=_to_response(result["gift_card"]) if result.get("gift_card") else None,
        checkout_url=result.get("checkout_url"),
        checkout_session_id=result.get("checkout_session_id"),
        payment_method=result["payment_method"],
    )


@router.get("/my", response_model=list[GiftCardResponse])
async def list_my_gift_cards(
    rbac: dict = Depends(require_permission("gift_cards.view_own")),
):
    """Gift cards relevant to the calling user — both cards they
    purchased AND cards where they are the recipient (matched by
    email). Used by the member-portal "My Gift Cards" view so a buyer
    sees codes for cards they purchased and a recipient sees codes
    for cards sent to them.

    Each row is annotated with `relationship` ∈ {"purchased",
    "received", "purchased_and_received"} via the GiftCardResponse
    `metadata` payload so the UI can label them."""
    from app.db.session import get_tenant_db
    user_id = rbac.get("user_id")
    if not user_id:
        return []
    async with get_tenant_db() as db:
        member = await db.fetchrow(
            "SELECT id, email FROM members WHERE user_id = $1",
            user_id,
        )
    if not member:
        return []
    rows = await gift_card_svc.list_cards_for_member(
        member_id=str(member["id"]),
        member_email=member["email"],
    )
    return [_to_response(r) for r in rows]


@router.get("", response_model=list[GiftCardResponse])
async def list_gift_cards(
    status: Optional[str] = Query(None, description="Filter: active, fully_redeemed, voided, expired"),
    search: Optional[str] = Query(None, description="Search code, email, or name"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user=Depends(require_permission("gift_cards.view")),
):
    """List all gift cards with optional filters."""
    rows = await gift_card_svc.list_gift_cards(
        status=status, search=search, limit=limit, offset=offset,
    )
    return [_to_response(r) for r in rows]


@router.get("/stats")
async def get_gift_card_stats(
    user=Depends(require_permission("gift_cards.view_stats")),
):
    """Get gift card summary stats."""
    from app.db.session import get_tenant_db
    async with get_tenant_db() as db:
        row = await db.fetchrow("""
            SELECT
                COUNT(*) AS total_issued,
                COALESCE(SUM(amount_cents), 0) AS total_amount,
                COALESCE(SUM(amount_cents - balance_cents), 0) AS total_redeemed,
                COALESCE(SUM(CASE WHEN status = 'active' THEN balance_cents ELSE 0 END), 0) AS outstanding_balance,
                COUNT(*) FILTER (WHERE status = 'active') AS active_count,
                COUNT(*) FILTER (WHERE status = 'fully_redeemed') AS redeemed_count,
                COUNT(*) FILTER (WHERE status = 'voided') AS voided_count
            FROM gift_cards
        """)
    return {
        "total_issued": row["total_issued"],
        # Frontend reads total_count (count of cards) and
        # total_issued_cents (sum of dollar amounts). Aliases avoid a
        # coordinated rename.
        "total_count": row["total_issued"],
        "total_amount_cents": row["total_amount"],
        "total_issued_cents": row["total_amount"],
        "total_redeemed_cents": row["total_redeemed"],
        "outstanding_balance_cents": row["outstanding_balance"],
        "active_count": row["active_count"],
        "redeemed_count": row["redeemed_count"],
        "voided_count": row["voided_count"],
    }


@router.get("/{gift_card_id}", response_model=GiftCardDetailResponse)
async def get_gift_card(
    gift_card_id: str,
    user=Depends(require_permission("gift_cards.view")),
):
    """Get gift card detail with redemption history."""
    result = await gift_card_svc.get_gift_card(gift_card_id)
    if not result:
        raise HTTPException(status_code=404, detail="Gift card not found")
    return result


@router.post("/{gift_card_id}/void", response_model=GiftCardResponse)
async def void_gift_card(
    gift_card_id: str,
    body: VoidRequest,
    user=Depends(require_permission("gift_cards.manage")),
):
    """Void a gift card (sets balance to 0, marks as voided)."""
    try:
        result = await gift_card_svc.void_gift_card(gift_card_id, reason=body.reason)
        return _to_response(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{gift_card_id}/adjust", response_model=GiftCardResponse)
async def adjust_balance(
    gift_card_id: str,
    body: AdjustRequest,
    user=Depends(require_permission("gift_cards.manage")),
):
    """Adjust gift card balance (admin action)."""
    try:
        result = await gift_card_svc.adjust_balance(
            gift_card_id, body.amount_cents, body.reason
        )
        return _to_response(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{gift_card_id}/resend")
async def resend_email(
    gift_card_id: str,
    user=Depends(require_permission("gift_cards.manage")),
):
    """Resend gift card email to recipient."""
    try:
        await gift_card_svc.resend_gift_card_email(gift_card_id)
        return {"detail": "Gift card email resent successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Helpers ──────────────────────────────────────────────────────────────────

def _to_response(row: dict) -> dict:
    """Convert DB row to response-friendly dict with string UUIDs.

    Mirrors `amount_cents` to `initial_amount_cents` for legacy frontend
    code that hasn't been migrated yet — both keys are populated so
    either reads correctly.
    """
    result = {}
    for k, v in row.items():
        if hasattr(v, "hex") and hasattr(v, "int"):  # UUID
            result[k] = str(v)
        else:
            result[k] = v
    if "amount_cents" in result and "initial_amount_cents" not in result:
        result["initial_amount_cents"] = result["amount_cents"]
    return result
