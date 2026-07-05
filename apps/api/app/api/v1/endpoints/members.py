"""AuraFlow — Member Endpoints

Member profiles, search, notes, and health data management.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.v1.dependencies.auth import get_current_user
from app.api.v1.dependencies.rbac import require_permission
from app.services.members.member_service import MemberService

router = APIRouter()

svc = MemberService()


# ── Schemas ──────────────────────────────────────────────────────────────────

class MemberCreate(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    address_line1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[list[str]] = None
    source: str = "manual"
    referral_source: Optional[str] = None


class MemberUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    address_line1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[list[str]] = None
    email_opt_in: Optional[bool] = None
    sms_opt_in: Optional[bool] = None


class MemberResponse(BaseModel):
    id: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    address_line1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[list[str]] = None
    photo_url: Optional[str] = None
    source: Optional[str] = None
    referral_source: Optional[str] = None
    total_visits: int = 0
    lifetime_revenue_cents: int = 0
    is_active: bool = True
    member_number: Optional[str] = None
    email_opt_in: bool = True
    sms_opt_in: bool = True
    stripe_coupon_id: Optional[str] = None
    churn_risk_flagged_at: Optional[str] = None
    # Square saved card-on-file pointer (no PAN, just brand/last4/exp)
    square_customer_id: Optional[str] = None
    square_card_on_file_id: Optional[str] = None
    square_card_on_file_brand: Optional[str] = None
    square_card_on_file_last4: Optional[str] = None
    square_card_on_file_exp_month: Optional[int] = None
    square_card_on_file_exp_year: Optional[int] = None
    square_card_on_file_saved_at: Optional[str] = None


class NoteCreate(BaseModel):
    note: str
    is_pinned: bool = False


class NoteResponse(BaseModel):
    id: str
    member_id: str
    author_id: str
    note: str
    is_pinned: bool
    created_at: str


class HealthDataUpdate(BaseModel):
    health_data: Optional[str] = None
    injuries: Optional[str] = None
    conditions: Optional[str] = None
    medications: Optional[str] = None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _member_response(row) -> MemberResponse:
    dob = row.get("date_of_birth")
    return MemberResponse(
        id=str(row["id"]),
        first_name=row["first_name"],
        last_name=row["last_name"],
        email=row["email"],
        phone=row.get("phone"),
        date_of_birth=str(dob) if dob else None,
        gender=row.get("gender"),
        address_line1=row.get("address_line1"),
        city=row.get("city"),
        state=row.get("state"),
        postal_code=row.get("postal_code"),
        emergency_contact_name=row.get("emergency_contact_name"),
        emergency_contact_phone=row.get("emergency_contact_phone"),
        notes=row.get("notes"),
        tags=row.get("tags") or [],
        photo_url=row.get("photo_url"),
        source=row.get("source"),
        referral_source=row.get("referral_source"),
        total_visits=row.get("total_visits", 0),
        lifetime_revenue_cents=row.get("lifetime_revenue_cents", 0),
        is_active=row["is_active"],
        member_number=row.get("member_number"),
        email_opt_in=row.get("email_opt_in", True),
        sms_opt_in=row.get("sms_opt_in", True),
        stripe_coupon_id=row.get("stripe_coupon_id"),
        churn_risk_flagged_at=row["churn_risk_flagged_at"].isoformat() if row.get("churn_risk_flagged_at") else None,
        square_customer_id=row.get("square_customer_id"),
        square_card_on_file_id=row.get("square_card_on_file_id"),
        square_card_on_file_brand=row.get("square_card_on_file_brand"),
        square_card_on_file_last4=row.get("square_card_on_file_last4"),
        square_card_on_file_exp_month=row.get("square_card_on_file_exp_month"),
        square_card_on_file_exp_year=row.get("square_card_on_file_exp_year"),
        square_card_on_file_saved_at=(
            row["square_card_on_file_saved_at"].isoformat()
            if row.get("square_card_on_file_saved_at") else None
        ),
    )


def _note_response(row) -> NoteResponse:
    return NoteResponse(
        id=str(row["id"]),
        member_id=str(row["member_id"]),
        author_id=str(row["author_id"]),
        note=row["note"],
        is_pinned=row["is_pinned"],
        created_at=row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else str(row["created_at"]),
    )


# ── Member CRUD ──────────────────────────────────────────────────────────────

@router.post("", response_model=MemberResponse, status_code=201)
async def create_member(
    request: MemberCreate,
    rbac: dict = Depends(require_permission("members.create")),
):
    member = await svc.create_member(request.model_dump())
    return _member_response(member)


@router.get("", response_model=list[MemberResponse])
async def list_members(
    search: Optional[str] = Query(None, description="Search by name, email, or phone"),
    active_only: bool = Query(True),
    membership_status: Optional[str] = Query(None, description="active|frozen|cancelled|expired|none"),
    has_failed_payments: Optional[bool] = Query(None),
    churn_risk: Optional[bool] = Query(None),
    min_visits: Optional[int] = Query(None, ge=0),
    max_visits: Optional[int] = Query(None, ge=0),
    inactive_weeks: Optional[int] = Query(None, ge=1),
    joined_after: Optional[str] = Query(None),
    joined_before: Optional[str] = Query(None),
    min_revenue: Optional[int] = Query(None, ge=0),
    has_coupon: Optional[bool] = Query(None, description="Filter members with/without coupons"),
    sort_by: Optional[str] = Query(None),
    sort_dir: Optional[str] = Query("desc"),
    limit: int = Query(200, le=500),
    offset: int = Query(0),
    rbac: dict = Depends(require_permission("members.view_all")),
):
    members = await svc.list_members(
        search=search, active_only=active_only,
        membership_status=membership_status,
        has_failed_payments=has_failed_payments,
        churn_risk=churn_risk,
        min_visits=min_visits, max_visits=max_visits,
        inactive_weeks=inactive_weeks,
        joined_after=joined_after, joined_before=joined_before,
        min_revenue=min_revenue,
        has_coupon=has_coupon,
        sort_by=sort_by, sort_dir=sort_dir,
        limit=limit, offset=offset,
    )
    return [_member_response(m) for m in members]


@router.get("/{member_id}", response_model=MemberResponse)
async def get_member(
    member_id: str,
    rbac: dict = Depends(require_permission("members.view")),
):
    member = await svc.get_member(member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return _member_response(member)


@router.put("/{member_id}", response_model=MemberResponse)
async def update_member(
    member_id: str,
    request: MemberUpdate,
    rbac: dict = Depends(require_permission("members.edit")),
):
    member = await svc.update_member(member_id, request.model_dump(exclude_unset=True))
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return _member_response(member)


@router.delete("/{member_id}", status_code=204)
async def deactivate_member(
    member_id: str,
    rbac: dict = Depends(require_permission("members.delete")),
):
    result = await svc.deactivate_member(member_id)
    if not result:
        raise HTTPException(status_code=404, detail="Member not found")


# ── Notes ────────────────────────────────────────────────────────────────────

@router.post("/{member_id}/notes", response_model=NoteResponse, status_code=201)
async def add_note(
    member_id: str,
    request: NoteCreate,
    rbac: dict = Depends(require_permission("members.create_note")),
):
    note = await svc.add_note(member_id, rbac["user_id"], request.note, request.is_pinned)
    return _note_response(note)


@router.get("/{member_id}/notes", response_model=list[NoteResponse])
async def list_notes(
    member_id: str,
    rbac: dict = Depends(require_permission("members.view_notes")),
):
    notes = await svc.list_notes(member_id)
    return [_note_response(n) for n in notes]


@router.delete("/{member_id}/notes/{note_id}", status_code=204)
async def delete_note(
    member_id: str,
    note_id: str,
    rbac: dict = Depends(require_permission("members.delete_note")),
):
    result = await svc.delete_note(note_id)
    if not result:
        raise HTTPException(status_code=404, detail="Note not found")


# ── Health Data ──────────────────────────────────────────────────────────────

@router.put("/{member_id}/health-data", status_code=200)
async def set_health_data(
    member_id: str,
    request: HealthDataUpdate,
    rbac: dict = Depends(require_permission("members.edit_health")),
):
    data = {}
    if request.health_data is not None:
        data["health_data"] = request.health_data.encode("utf-8")
    if request.injuries is not None:
        data["injuries"] = request.injuries.encode("utf-8")
    if request.conditions is not None:
        data["conditions"] = request.conditions.encode("utf-8")
    if request.medications is not None:
        data["medications"] = request.medications.encode("utf-8")
    await svc.set_health_data(member_id, data)
    return {"status": "saved"}


@router.get("/{member_id}/health-data")
async def get_health_data(
    member_id: str,
    rbac: dict = Depends(require_permission("members.view_health")),
):
    hd = await svc.get_health_data(member_id)
    if not hd:
        return {"health_data": None, "injuries": None, "conditions": None, "medications": None}
    return {
        "health_data": hd["health_data_encrypted"].decode("utf-8") if hd.get("health_data_encrypted") else None,
        "injuries": hd["injuries_encrypted"].decode("utf-8") if hd.get("injuries_encrypted") else None,
        "conditions": hd["conditions_encrypted"].decode("utf-8") if hd.get("conditions_encrypted") else None,
        "medications": hd["medications_encrypted"].decode("utf-8") if hd.get("medications_encrypted") else None,
    }


# ── Booking History ──────────────────────────────────────────────────────────

@router.get("/{member_id}/bookings")
async def get_booking_history(
    member_id: str,
    limit: int = Query(100, le=500),
    rbac: dict = Depends(require_permission("members.view_bookings")),
):
    bookings = await svc.get_booking_history(member_id, limit)

    def _fmt(dt):
        if dt and hasattr(dt, "isoformat"):
            return dt.isoformat()
        return str(dt) if dt else None

    return [
        {
            "id": str(b["id"]),
            "class_session_id": str(b["class_session_id"]),
            "session_title": b.get("session_title"),
            "class_type_name": b.get("class_type_name"),
            "class_category": b.get("class_category"),
            "starts_at": _fmt(b.get("starts_at")),
            "ends_at": _fmt(b.get("ends_at")),
            "status": b["status"],
            "booked_at": _fmt(b.get("booked_at")),
            "cancelled_at": _fmt(b.get("cancelled_at")),
            "checked_in_at": _fmt(b.get("checked_in_at")),
            "cancellation_reason": b.get("cancellation_reason"),
            "late_cancel": b.get("late_cancel", False),
        }
        for b in bookings
    ]


# ── Member-detail dashboard endpoints ────────────────────────────────────────
# These power the tabbed member-detail page in the staff dashboard. Each is
# a focused read of one slice of the member's history. All require staff role.


def _fmt_dt(dt):
    if dt and hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt) if dt else None


class CreditGrantRequest(BaseModel):
    amount_cents: int
    source: str  # 'courtesy', 'manual_grant', 'refund_to_credit', 'gift'
    service_filter: Optional[str] = "private_session"
    expiry_days: Optional[int] = 180
    notes: Optional[str] = None


@router.get("/{member_id}/credits")
async def list_member_credits(
    member_id: str,
    include_used: bool = Query(False, description="Include used + expired credits in the history"),
    rbac: dict = Depends(require_permission("members.view_credits")),
):
    """Return available credits (default) or full credit history."""
    from app.services.members.member_credit_service import MemberCreditService
    svc_c = MemberCreditService()
    if include_used:
        rows = await svc_c.list_all_credits(member_id)
    else:
        rows = await svc_c.list_available_credits(member_id)
    return [
        {
            "id": str(c["id"]),
            "source": c["source"],
            "source_ref_id": str(c["source_ref_id"]) if c.get("source_ref_id") else None,
            "service_filter": c.get("service_filter"),
            "amount_cents": c["amount_cents"],
            "expires_at": _fmt_dt(c.get("expires_at")),
            "used_at": _fmt_dt(c.get("used_at")),
            "used_booking_id": str(c["used_booking_id"]) if c.get("used_booking_id") else None,
            "used_booking_table": c.get("used_booking_table"),
            "notes": c.get("notes"),
            "granted_by_user_id": str(c["granted_by_user_id"]) if c.get("granted_by_user_id") else None,
            "created_at": _fmt_dt(c.get("created_at")),
        }
        for c in rows
    ]


@router.post("/{member_id}/credits", status_code=201)
async def grant_member_credit(
    member_id: str,
    body: CreditGrantRequest,
    rbac: dict = Depends(require_permission("members.grant_credits")),
):
    """Staff manually grants a credit (courtesy, refund-to-credit, etc.).
    Owner/admin only — front desk can't issue arbitrary credits."""
    from app.services.members.member_credit_service import MemberCreditService
    try:
        credit = await MemberCreditService().grant_credit(
            member_id=member_id,
            amount_cents=body.amount_cents,
            source=body.source,
            service_filter=body.service_filter,
            expiry_days=body.expiry_days,
            notes=body.notes,
            granted_by_user_id=rbac["user_id"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "id": str(credit["id"]),
        "source": credit["source"],
        "amount_cents": credit["amount_cents"],
        "expires_at": _fmt_dt(credit.get("expires_at")),
        "notes": credit.get("notes"),
    }


@router.post("/{member_id}/credits/{credit_id}/revoke", status_code=200)
async def revoke_member_credit(
    member_id: str,
    credit_id: str,
    reason: Optional[str] = Query(None),
    rbac: dict = Depends(require_permission("members.revoke_credits")),
):
    """Soft-revoke an unused credit (issued in error). Preserves audit
    trail by setting used_at with a revoked sentinel booking_id."""
    from app.services.members.member_credit_service import MemberCreditService
    ok = await MemberCreditService().revoke_credit(credit_id, reason=reason)
    if not ok:
        raise HTTPException(status_code=404, detail="Credit not found or already used")
    return {"status": "revoked"}


@router.get("/{member_id}/payments")
async def list_member_payments(
    member_id: str,
    limit: int = Query(100, le=500),
    rbac: dict = Depends(require_permission("members.view_payments")),
):
    """Transaction history (payments + refunds) for the member."""
    from app.db.session import get_tenant_db
    async with get_tenant_db() as db:
        rows = await db.fetch(
            """
            SELECT t.id, t.type, t.amount_cents, t.fee_cents, t.net_amount_cents,
                   t.status, t.description,
                   t.stripe_payment_intent_id, t.stripe_charge_id,
                   t.membership_id, t.created_at,
                   mt.name AS membership_type_name
            FROM transactions t
            LEFT JOIN member_memberships mm ON mm.id = t.membership_id
            LEFT JOIN membership_types mt ON mt.id = mm.membership_type_id
            WHERE t.member_id = $1
            ORDER BY t.created_at DESC
            LIMIT $2
            """,
            member_id, limit,
        )
    return [
        {
            "id": str(r["id"]),
            "type": r.get("type"),
            "amount_cents": r.get("amount_cents"),
            "fee_cents": r.get("fee_cents"),
            "net_amount_cents": r.get("net_amount_cents"),
            "status": r.get("status"),
            "description": r.get("description"),
            "stripe_payment_intent_id": r.get("stripe_payment_intent_id"),
            "stripe_charge_id": r.get("stripe_charge_id"),
            "membership_type_name": r.get("membership_type_name"),
            "created_at": _fmt_dt(r.get("created_at")),
        }
        for r in rows
    ]


@router.get("/{member_id}/private-sessions")
async def list_member_private_sessions(
    member_id: str,
    limit: int = Query(100, le=500),
    rbac: dict = Depends(require_permission("members.view_private_sessions")),
):
    """Private session history for the member, joined with service + instructor."""
    from app.db.session import get_tenant_db
    async with get_tenant_db() as db:
        rows = await db.fetch(
            """
            SELECT pb.id, pb.starts_at, pb.ends_at, pb.status, pb.is_virtual,
                   pb.price_cents, pb.payment_status, pb.cancelled_at,
                   pb.cancellation_reason, pb.cancelled_by_role,
                   pb.created_at, pb.transaction_id,
                   ps.name AS service_name, ps.duration_minutes,
                   i.display_name AS instructor_name
            FROM private_bookings pb
            JOIN private_services ps ON ps.id = pb.private_service_id
            JOIN instructors i ON i.id = pb.instructor_id
            WHERE pb.member_id = $1
            ORDER BY pb.starts_at DESC
            LIMIT $2
            """,
            member_id, limit,
        )
    return [
        {
            "id": str(r["id"]),
            "service_name": r.get("service_name"),
            "duration_minutes": r.get("duration_minutes"),
            "instructor_name": r.get("instructor_name"),
            "starts_at": _fmt_dt(r.get("starts_at")),
            "ends_at": _fmt_dt(r.get("ends_at")),
            "status": r.get("status"),
            "is_virtual": r.get("is_virtual"),
            "price_cents": r.get("price_cents"),
            "payment_status": r.get("payment_status"),
            "cancelled_at": _fmt_dt(r.get("cancelled_at")),
            "cancellation_reason": r.get("cancellation_reason"),
            "cancelled_by_role": r.get("cancelled_by_role"),
            "transaction_id": str(r["transaction_id"]) if r.get("transaction_id") else None,
            "created_at": _fmt_dt(r.get("created_at")),
        }
        for r in rows
    ]


@router.get("/{member_id}/memberships")
async def list_member_memberships(
    member_id: str,
    rbac: dict = Depends(require_permission("members.view_memberships")),
):
    """All memberships (active + past) with credits remaining, expiry, etc."""
    from app.db.session import get_tenant_db
    async with get_tenant_db() as db:
        rows = await db.fetch(
            """
            SELECT mm.id, mm.status, mm.starts_at, mm.ends_at, mm.classes_remaining,
                   mm.cancelled_at, mm.frozen_at, mm.created_at,
                   mt.name AS type_name, mt.type AS type_category,
                   mt.price_cents AS type_price_cents,
                   mm.stripe_subscription_id
            FROM member_memberships mm
            JOIN membership_types mt ON mt.id = mm.membership_type_id
            WHERE mm.member_id = $1
            ORDER BY
              CASE mm.status WHEN 'active' THEN 0 WHEN 'frozen' THEN 1 ELSE 2 END,
              mm.created_at DESC
            """,
            member_id,
        )
    return [
        {
            "id": str(r["id"]),
            "type_name": r.get("type_name"),
            "type_category": r.get("type_category"),
            "type_price_cents": r.get("type_price_cents"),
            "status": r.get("status"),
            "classes_remaining": r.get("classes_remaining"),
            "starts_at": _fmt_dt(r.get("starts_at")),
            "ends_at": _fmt_dt(r.get("ends_at")),
            "cancelled_at": _fmt_dt(r.get("cancelled_at")),
            "frozen_at": _fmt_dt(r.get("frozen_at")),
            "stripe_subscription_id": r.get("stripe_subscription_id"),
            "created_at": _fmt_dt(r.get("created_at")),
        }
        for r in rows
    ]
