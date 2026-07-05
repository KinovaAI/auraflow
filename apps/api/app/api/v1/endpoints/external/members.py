"""AuraFlow — External Members CRUD Endpoints

API-key-authenticated member management for third-party integrations.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.v1.dependencies.api_key_auth import get_api_key_context, require_api_scope
from app.services.members.member_service import MemberService
from app.services.external.csv_export import export_csv

router = APIRouter()
_svc = MemberService()


# ── Schemas ──────────────────────────────────────────────────────────────────

class ExternalMemberCreate(BaseModel):
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
    source: str = "api"
    referral_source: Optional[str] = None


class ExternalMemberUpdate(BaseModel):
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


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fmt(dt):
    if dt and hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt) if dt else None


def _member_dict(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "first_name": row["first_name"],
        "last_name": row["last_name"],
        "email": row["email"],
        "phone": row.get("phone"),
        "date_of_birth": str(row["date_of_birth"]) if row.get("date_of_birth") else None,
        "gender": row.get("gender"),
        "address_line1": row.get("address_line1"),
        "city": row.get("city"),
        "state": row.get("state"),
        "postal_code": row.get("postal_code"),
        "source": row.get("source"),
        "total_visits": row.get("total_visits", 0),
        "lifetime_revenue_cents": row.get("lifetime_revenue_cents", 0),
        "is_active": row.get("is_active", True),
        "member_number": row.get("member_number"),
        "joined_at": _fmt(row.get("joined_at")),
        "last_visit_at": _fmt(row.get("last_visit_at")),
    }


async def _fire_webhook(event: str, payload: dict) -> None:
    try:
        from app.services.webhooks.webhook_delivery_service import WebhookDeliveryService
        await WebhookDeliveryService().fire_event(event, payload)
    except Exception:
        pass  # Non-fatal


# ── CSV Export (must be before /{member_id} to avoid route conflict) ─────────

_MEMBER_CSV_COLS = [
    ("id", "ID"),
    ("first_name", "First Name"),
    ("last_name", "Last Name"),
    ("email", "Email"),
    ("phone", "Phone"),
    ("date_of_birth", "Date of Birth"),
    ("gender", "Gender"),
    ("is_active", "Active"),
    ("total_visits", "Total Visits"),
    ("lifetime_revenue_cents", "Lifetime Revenue (cents)"),
    ("joined_at", "Joined At"),
    ("last_visit_at", "Last Visit At"),
]


@router.get(
    "/members/export.csv",
    dependencies=[Depends(require_api_scope("members:read"))],
    summary="Export members as CSV",
)
async def export_members_csv(
    ctx: dict = Depends(get_api_key_context),
    search: Optional[str] = Query(None),
    active_only: bool = Query(True),
):
    rows = await _svc.list_members(search=search, active_only=active_only, limit=10000)
    return export_csv(rows, _MEMBER_CSV_COLS, "members.csv")


# ── CRUD Endpoints ───────────────────────────────────────────────────────────

@router.get(
    "/members",
    dependencies=[Depends(require_api_scope("members:read"))],
    summary="List members",
)
async def list_members(
    ctx: dict = Depends(get_api_key_context),
    search: Optional[str] = Query(None),
    active_only: bool = Query(True),
    limit: int = Query(50, le=500),
    offset: int = Query(0),
):
    rows = await _svc.list_members(
        search=search, active_only=active_only, limit=limit, offset=offset,
    )
    return [_member_dict(r) for r in rows]


@router.get(
    "/members/{member_id}",
    dependencies=[Depends(require_api_scope("members:read"))],
    summary="Get member by ID",
)
async def get_member(
    member_id: str,
    ctx: dict = Depends(get_api_key_context),
):
    row = await _svc.get_member(member_id)
    if not row:
        raise HTTPException(status_code=404, detail="Member not found")
    return _member_dict(row)


@router.post(
    "/members",
    dependencies=[Depends(require_api_scope("members:write"))],
    status_code=201,
    summary="Create a member",
)
async def create_member(
    body: ExternalMemberCreate,
    ctx: dict = Depends(get_api_key_context),
):
    row = await _svc.create_member(body.model_dump())
    result = _member_dict(row)
    await _fire_webhook("member.created", result)
    return result


@router.put(
    "/members/{member_id}",
    dependencies=[Depends(require_api_scope("members:write"))],
    summary="Update a member",
)
async def update_member(
    member_id: str,
    body: ExternalMemberUpdate,
    ctx: dict = Depends(get_api_key_context),
):
    row = await _svc.update_member(member_id, body.model_dump(exclude_unset=True))
    if not row:
        raise HTTPException(status_code=404, detail="Member not found")
    result = _member_dict(row)
    await _fire_webhook("member.updated", result)
    return result


@router.delete(
    "/members/{member_id}",
    dependencies=[Depends(require_api_scope("members:write"))],
    status_code=204,
    summary="Deactivate a member (soft delete)",
)
async def deactivate_member(
    member_id: str,
    ctx: dict = Depends(get_api_key_context),
):
    ok = await _svc.deactivate_member(member_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Member not found")
    await _fire_webhook("member.deactivated", {"id": member_id})


# ── Waiver Endpoints ────────────────────────────────────────────────────────

class WaiverSignRequest(BaseModel):
    signature_text: str  # Member's typed full name
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


@router.get(
    "/members/{member_id}/waiver",
    dependencies=[Depends(require_api_scope("members:read"))],
    summary="Check waiver status for a member",
)
async def get_waiver_status(
    member_id: str,
    ctx: dict = Depends(get_api_key_context),
):
    """Check if a member has signed the current waiver. Returns waiver text if unsigned."""
    from app.services.waivers.waiver_service import WaiverService
    waiver_svc = WaiverService()
    status = await waiver_svc.check_waiver_status(member_id)
    result = {
        "signed": status["signed"],
        "expired": status.get("expired", False),
        "needs_resign": status.get("needs_resign", False),
    }
    # If not signed, include waiver template for display
    if not status["signed"] or status.get("expired") or status.get("needs_resign"):
        from app.db.session import get_tenant_db
        async with get_tenant_db() as db:
            tpl = await db.fetchrow(
                "SELECT id, title, content, version FROM waiver_templates WHERE is_active = TRUE ORDER BY version DESC LIMIT 1"
            )
        if tpl:
            result["template"] = {
                "id": str(tpl["id"]),
                "title": tpl["title"],
                "content": tpl["content"],
                "version": tpl["version"],
            }
    return result


@router.post(
    "/members/{member_id}/waiver/sign",
    dependencies=[Depends(require_api_scope("members:write"))],
    summary="DISABLED — waivers must be signed by the member directly",
    status_code=410,
    deprecated=True,
)
async def sign_waiver_disabled(
    member_id: str,
    body: WaiverSignRequest,
    ctx: dict = Depends(get_api_key_context),
):
    """Back-door waiver signing is permanently disabled.

    Waivers MUST be signed by the member themselves, logged into their
    own portal account with a verified email address, on their own
    device. Signing on behalf of a member (even with a valid API key)
    undermines the legal validity of the waiver. Any integration that
    needs to collect a waiver should redirect the member to
    /portal/waiver instead.
    """
    raise HTTPException(
        status_code=410,
        detail={
            "code": "waiver_self_sign_only",
            "message": (
                "Waiver signing via API key is disabled. Members must "
                "sign their own waiver from the member portal while "
                "logged into their own account with a verified email."
            ),
        },
    )


# ── Kiosk: Create Account + Book Class ──────────────────────────────────────

class KioskDropInRequest(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    session_id: str
    signature_text: Optional[str] = None  # Waiver signature (typed name)


@router.post(
    "/members/kiosk-drop-in",
    dependencies=[Depends(require_api_scope("members:write", "bookings:write"))],
    summary="Kiosk: create member + sign waiver + book class in one call",
    status_code=201,
)
async def kiosk_drop_in(
    member_id_or_new: KioskDropInRequest,
    ctx: dict = Depends(get_api_key_context),
):
    """One-call endpoint for kiosk drop-ins: creates member if needed, signs waiver, books class."""
    body = member_id_or_new
    from app.db.session import get_tenant_db
    from app.services.waivers.waiver_service import WaiverService
    from app.services.scheduling.booking_service import BookingService, BookingError
    import uuid as _uuid

    # 1. Find or create member
    async with get_tenant_db() as db:
        existing = await db.fetchrow(
            "SELECT id FROM members WHERE LOWER(email) = $1",
            body.email.strip().lower(),
        )

    if existing:
        member_id = str(existing["id"])
        is_new = False
    else:
        # Create new member
        result = await _svc.create_member({
            "first_name": body.first_name,
            "last_name": body.last_name,
            "email": body.email.strip().lower(),
            "phone": body.phone,
            "source": "kiosk",
        })
        member_id = str(result["id"])
        is_new = True

    # 2. Waiver handling — the kiosk does NOT sign for the member.
    # signature_text is intentionally ignored. Legally, the member must
    # sign their own waiver while logged into their own portal account
    # with a verified email. The booking call below will fail cleanly
    # with WAIVER_REQUIRED if they haven't; the kiosk UI should then
    # direct them to /portal/waiver on their own device.
    waiver_svc = WaiverService()
    existing_waiver = await waiver_svc.check_waiver_status(member_id)
    waiver_signed = bool(existing_waiver.get("signed"))

    # 3. Book the class
    booking_svc = BookingService()
    try:
        booking = await booking_svc.book_class({
            "member_id": member_id,
            "class_session_id": body.session_id,
            "source": "kiosk",
        })
        booking_id = str(booking["id"])
    except BookingError as exc:
        return {
            "member_id": member_id,
            "is_new_member": is_new,
            "waiver_signed": waiver_signed,
            "booked": False,
            "error": {"code": exc.code, "message": str(exc)},
        }

    # 4. Check them in
    try:
        await booking_svc.check_in(booking_id)
    except Exception:
        pass  # Booked but not checked in is fine

    return {
        "member_id": member_id,
        "is_new_member": is_new,
        "waiver_signed": waiver_signed,
        "booked": True,
        "booking_id": booking_id,
        "checked_in": True,
    }
