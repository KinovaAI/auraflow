"""AuraFlow — Membership Endpoints

Membership types, assignment, freeze, cancel, and eligibility.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.v1.dependencies.auth import get_current_user
from app.api.v1.dependencies.rbac import require_permission
from app.services.memberships.membership_service import MembershipService

router = APIRouter()

# Keep stub routers for webhook module compatibility
stripe_router = APIRouter()
mux_router = APIRouter()

svc = MembershipService()


# ── Schemas ──────────────────────────────────────────────────────────────────

class MembershipTypeCreate(BaseModel):
    studio_id: str
    name: str
    description: Optional[str] = None
    type: str  # unlimited, class_pack, intro_offer, day_pass, single_class
    access_scope: str = "in_studio"  # in_studio, online, all_access
    class_count: Optional[int] = None
    price_cents: int
    billing_period: Optional[str] = "monthly"
    duration_days: Optional[int] = None
    is_founding_rate: bool = False
    max_enrollments: Optional[int] = None
    auto_renew: bool = True
    trial_days: int = 0
    freeze_allowed: bool = False
    max_freeze_days: int = 30
    cancellation_notice_days: int = 0
    class_types_allowed: Optional[list[str]] = None
    is_public: bool = True
    sort_order: int = 0


class MembershipTypeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    access_scope: Optional[str] = None
    price_cents: Optional[int] = None
    class_count: Optional[int] = None
    billing_period: Optional[str] = None
    duration_days: Optional[int] = None
    is_founding_rate: Optional[bool] = None
    max_enrollments: Optional[int] = None
    auto_renew: Optional[bool] = None
    trial_days: Optional[int] = None
    freeze_allowed: Optional[bool] = None
    max_freeze_days: Optional[int] = None
    cancellation_notice_days: Optional[int] = None
    is_public: Optional[bool] = None
    sort_order: Optional[int] = None


class MembershipTypeResponse(BaseModel):
    id: str
    studio_id: str
    name: str
    description: Optional[str] = None
    type: str
    access_scope: str = "in_studio"
    class_count: Optional[int] = None
    price_cents: int
    billing_period: Optional[str] = None
    duration_days: Optional[int] = None
    is_founding_rate: bool = False
    max_enrollments: Optional[int] = None
    auto_renew: bool = True
    trial_days: int = 0
    freeze_allowed: bool = False
    max_freeze_days: int = 30
    cancellation_notice_days: int = 0
    is_template: bool = False
    template_key: Optional[str] = None
    is_active: bool = True
    is_public: bool = True
    sort_order: int = 0


class AssignMembership(BaseModel):
    member_id: str
    membership_type_id: str
    starts_at: Optional[str] = None


class PurchaseWithGiftCard(BaseModel):
    member_id: str
    membership_type_id: str
    gift_card_code: str


class MemberMembershipResponse(BaseModel):
    id: str
    member_id: str
    membership_type_id: str
    type_name: Optional[str] = None
    membership_type: Optional[str] = None
    access_scope: Optional[str] = None
    member_first_name: Optional[str] = None
    member_last_name: Optional[str] = None
    status: str
    starts_at: str
    ends_at: Optional[str] = None
    classes_remaining: Optional[int] = None
    total_classes: Optional[int] = None
    price_cents: Optional[int] = None
    frozen_at: Optional[str] = None
    frozen_until: Optional[str] = None
    cancelled_at: Optional[str] = None
    cancellation_reason: Optional[str] = None


class FreezeMembership(BaseModel):
    until: Optional[str] = None


class CancelMembership(BaseModel):
    reason: Optional[str] = None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _type_response(row) -> MembershipTypeResponse:
    return MembershipTypeResponse(
        id=str(row["id"]),
        studio_id=str(row["studio_id"]),
        name=row["name"],
        description=row.get("description"),
        type=row["type"],
        access_scope=row.get("access_scope", "in_studio"),
        class_count=row.get("class_count"),
        price_cents=row["price_cents"],
        billing_period=row.get("billing_period"),
        duration_days=row.get("duration_days"),
        is_founding_rate=row.get("is_founding_rate", False),
        max_enrollments=row.get("max_enrollments"),
        auto_renew=row.get("auto_renew", True),
        trial_days=row.get("trial_days", 0),
        freeze_allowed=row.get("freeze_allowed", False),
        max_freeze_days=row.get("max_freeze_days", 30),
        cancellation_notice_days=row.get("cancellation_notice_days", 0),
        is_template=row.get("is_template", False),
        template_key=row.get("template_key"),
        is_active=row["is_active"],
        is_public=row.get("is_public", True),
        sort_order=row.get("sort_order", 0),
    )


def _ts(val) -> str | None:
    if val is None:
        return None
    return val.isoformat() if hasattr(val, "isoformat") else str(val)


def _mm_response(row) -> MemberMembershipResponse:
    return MemberMembershipResponse(
        id=str(row["id"]),
        member_id=str(row["member_id"]),
        membership_type_id=str(row["membership_type_id"]),
        type_name=row.get("type_name"),
        membership_type=row.get("membership_type"),
        access_scope=row.get("access_scope"),
        member_first_name=row.get("member_first_name"),
        member_last_name=row.get("member_last_name"),
        status=row["status"],
        starts_at=_ts(row["starts_at"]) or "",
        ends_at=_ts(row.get("ends_at")),
        classes_remaining=row.get("classes_remaining"),
        total_classes=row.get("total_classes"),
        price_cents=row.get("price_cents"),
        frozen_at=_ts(row.get("frozen_at")),
        frozen_until=_ts(row.get("frozen_until")),
        cancelled_at=_ts(row.get("cancelled_at")),
        cancellation_reason=row.get("cancellation_reason"),
    )


# ── Membership Type CRUD ────────────────────────────────────────────────────

@router.post("/types", response_model=MembershipTypeResponse, status_code=201)
async def create_type(
    request: MembershipTypeCreate,
    rbac: dict = Depends(require_permission("memberships.create_type")),
):
    data = request.model_dump()
    # For free memberships, billing_period can be None
    if data.get("price_cents", 0) == 0 and not data.get("billing_period"):
        data["billing_period"] = None
    try:
        mt = await svc.create_type(data)
    except Exception as e:
        error_msg = str(e)
        if "billing_period_check" in error_msg:
            raise HTTPException(status_code=400, detail="Invalid billing period. Use: monthly, yearly, quarterly, semi_annual, one_time, or leave empty for free memberships.")
        raise HTTPException(status_code=400, detail=f"Failed to create membership type: {error_msg}")
    return _type_response(mt)


@router.get("/types", response_model=list[MembershipTypeResponse])
async def list_types(
    studio_id: str = Query(...),
    active_only: bool = Query(True),
    current_user: dict = Depends(get_current_user),
):
    types = await svc.list_types(studio_id, active_only)
    return [_type_response(t) for t in types]


@router.get("/types/{type_id}", response_model=MembershipTypeResponse)
async def get_type(
    type_id: str,
    current_user: dict = Depends(get_current_user),
):
    mt = await svc.get_type(type_id)
    if not mt:
        raise HTTPException(status_code=404, detail="Membership type not found")
    return _type_response(mt)


@router.put("/types/{type_id}", response_model=MembershipTypeResponse)
async def update_type(
    type_id: str,
    request: MembershipTypeUpdate,
    rbac: dict = Depends(require_permission("memberships.edit_type")),
):
    mt = await svc.update_type(type_id, request.model_dump(exclude_unset=True))
    if not mt:
        raise HTTPException(status_code=404, detail="Membership type not found")
    return _type_response(mt)


@router.delete("/types/{type_id}", status_code=204)
async def deactivate_type(
    type_id: str,
    rbac: dict = Depends(require_permission("memberships.delete_type")),
):
    result = await svc.deactivate_type(type_id)
    if not result:
        raise HTTPException(status_code=404, detail="Membership type not found")


# ── Assignment ───────────────────────────────────────────────────────────────

@router.post("/assign", response_model=MemberMembershipResponse, status_code=201)
async def assign_membership(
    request: AssignMembership,
    rbac: dict = Depends(require_permission("memberships.assign")),
):
    try:
        mm = await svc.assign_membership(request.model_dump())
    except ValueError as e:
        msg = str(e)
        # Return 409 with a distinct error code for the waiver gate so
        # the frontend can render a shouty red banner instead of a
        # generic "bad request".
        if msg.startswith("WAIVER NOT COMPLETED"):
            raise HTTPException(
                status_code=409,
                detail={"code": "waiver_required", "message": msg},
            )
        raise HTTPException(status_code=400, detail=msg)
    full = await svc.get_membership(str(mm["id"]))
    return _mm_response(full)


@router.post("/purchase-with-gift-card", response_model=MemberMembershipResponse, status_code=201)
async def purchase_with_gift_card(
    request: PurchaseWithGiftCard,
    rbac: dict = Depends(require_permission("memberships.purchase_with_gift_card")),
):
    """Purchase a class pack / membership using a gift card balance.

    Atomic flow: validate the card has sufficient balance, debit the card,
    assign the membership, record the transaction. All or nothing — if any
    step fails, none of them persist. Allowed for staff (selling at the
    counter) and members (self-service via the portal).
    """
    try:
        result = await svc.purchase_membership_with_gift_card(request.model_dump())
    except ValueError as e:
        msg = str(e)
        if msg.startswith("WAIVER NOT COMPLETED"):
            raise HTTPException(
                status_code=409,
                detail={"code": "waiver_required", "message": msg},
            )
        raise HTTPException(status_code=400, detail=msg)
    full = await svc.get_membership(str(result["id"]))
    return _mm_response(full)


@router.get("/active", response_model=list[MemberMembershipResponse])
async def list_active_memberships(
    active_only: bool = Query(True),
    limit: int = Query(200, le=500),
    current_user: dict = Depends(get_current_user),
    _=Depends(require_permission("memberships.view_active")),
):
    memberships = await svc.list_all_memberships(active_only, limit)
    return [_mm_response(mm) for mm in memberships]


@router.get("/member/{member_id}", response_model=list[MemberMembershipResponse])
async def get_member_memberships(
    member_id: str,
    active_only: bool = Query(True),
    current_user: dict = Depends(get_current_user),
):
    memberships = await svc.get_member_memberships(member_id, active_only)
    return [_mm_response(mm) for mm in memberships]


# ── Eligibility ──────────────────────────────────────────────────────────────

@router.get("/eligibility/{member_id}")
async def check_eligibility(
    member_id: str,
    class_type_id: Optional[str] = Query(None),
    is_virtual: bool = Query(False),
    current_user: dict = Depends(get_current_user),
):
    return await svc.check_eligibility(member_id, class_type_id, is_virtual)


# ── Templates ───────────────────────────────────────────────────────────────

@router.get("/templates")
async def list_templates(
    rbac: dict = Depends(require_permission("memberships.view_templates")),
):
    """List global membership templates for reference."""
    templates = await svc.list_templates()
    return {"data": [dict(t) for t in templates]}


@router.post("/types/seed-defaults")
async def seed_defaults(
    studio_id: str = Query(...),
    rbac: dict = Depends(require_permission("memberships.seed_defaults")),
):
    """Seed the studio with default membership types from platform templates."""
    created = await svc.seed_from_templates(studio_id)
    return {"data": {"seeded": len(created), "types": [_type_response(t) for t in created]}}


# ── Single Membership (must come AFTER fixed paths) ─────────────────────────

@router.get("/{membership_id}", response_model=MemberMembershipResponse)
async def get_membership(
    membership_id: str,
    current_user: dict = Depends(get_current_user),
):
    mm = await svc.get_membership(membership_id)
    if not mm:
        raise HTTPException(status_code=404, detail="Membership not found")
    return _mm_response(mm)


# ── Freeze / Unfreeze ────────────────────────────────────────────────────────

@router.post("/{membership_id}/freeze", response_model=MemberMembershipResponse)
async def freeze_membership(
    membership_id: str,
    request: FreezeMembership,
    rbac: dict = Depends(require_permission("memberships.freeze")),
):
    from datetime import datetime
    until = datetime.fromisoformat(request.until) if request.until else None
    try:
        mm = await svc.freeze_membership(membership_id, until)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not mm:
        raise HTTPException(status_code=404, detail="Membership not found")
    full = await svc.get_membership(membership_id)
    return _mm_response(full)


@router.post("/{membership_id}/unfreeze", response_model=MemberMembershipResponse)
async def unfreeze_membership(
    membership_id: str,
    rbac: dict = Depends(require_permission("memberships.unfreeze")),
):
    mm = await svc.unfreeze_membership(membership_id)
    if not mm:
        raise HTTPException(status_code=404, detail="Membership not found or not frozen")
    full = await svc.get_membership(membership_id)
    return _mm_response(full)


# ── Cancel ───────────────────────────────────────────────────────────────────

@router.post("/{membership_id}/cancel", response_model=MemberMembershipResponse)
async def cancel_membership(
    membership_id: str,
    request: CancelMembership,
    rbac: dict = Depends(require_permission("memberships.cancel")),
):
    mm = await svc.cancel_membership(membership_id, request.reason)
    if not mm:
        raise HTTPException(status_code=404, detail="Membership not found or already cancelled")
    full = await svc.get_membership(membership_id)
    return _mm_response(full)
