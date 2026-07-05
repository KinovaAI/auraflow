"""AuraFlow — External Private Sessions Endpoints

API-key-authenticated private session management.
Critical for BioAlignPro integration.
"""
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.v1.dependencies.api_key_auth import get_api_key_context, require_api_scope
from app.services.scheduling.private_session_service import PrivateSessionService
from app.services.external.csv_export import export_csv

router = APIRouter()
_svc = PrivateSessionService()


# ── Schemas ──────────────────────────────────────────────────────────────────

class PrivateSessionCreate(BaseModel):
    member_id: str
    instructor_id: str
    service_id: str
    starts_at: str  # ISO datetime
    ends_at: Optional[str] = None  # Optional; computed from service duration if omitted
    intake_notes: Optional[str] = None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fmt(dt):
    if dt and hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt) if dt else None


def _booking_dict(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "member_id": str(row["member_id"]),
        "instructor_id": str(row["instructor_id"]),
        "private_service_id": str(row.get("private_service_id", "")),
        "service_name": row.get("service_name"),
        "instructor_name": row.get("instructor_name"),
        "member_first_name": row.get("member_first_name"),
        "member_last_name": row.get("member_last_name"),
        "starts_at": _fmt(row.get("starts_at")),
        "ends_at": _fmt(row.get("ends_at")),
        "status": row.get("status"),
        "is_virtual": row.get("is_virtual", False),
        "intake_notes": row.get("intake_notes"),
        "price_cents": row.get("price_cents"),
        "created_at": _fmt(row.get("created_at")),
    }


def _service_dict(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "instructor_id": str(row["instructor_id"]) if row.get("instructor_id") else None,
        "name": row["name"],
        "description": row.get("description"),
        "duration_minutes": row.get("duration_minutes"),
        "price_cents": row.get("price_cents"),
        "is_virtual": row.get("is_virtual", False),
        "visibility": row.get("visibility"),
        "is_active": row.get("is_active", True),
    }


async def _fire_webhook(event: str, payload: dict) -> None:
    try:
        from app.services.webhooks.webhook_delivery_service import WebhookDeliveryService
        await WebhookDeliveryService().fire_event(event, payload)
    except Exception:
        pass


# ── CSV Export ───────────────────────────────────────────────────────────────

_PS_CSV_COLS = [
    ("id", "ID"),
    ("member_first_name", "Member First Name"),
    ("member_last_name", "Member Last Name"),
    ("instructor_name", "Instructor"),
    ("service_name", "Service"),
    ("starts_at", "Starts At"),
    ("ends_at", "Ends At"),
    ("status", "Status"),
    ("price_cents", "Price (cents)"),
]


@router.get(
    "/private-sessions/export.csv",
    dependencies=[Depends(require_api_scope("private_sessions:read"))],
    summary="Export private sessions as CSV",
)
async def export_private_sessions_csv(
    ctx: dict = Depends(get_api_key_context),
    member_id: Optional[str] = Query(None),
    instructor_id: Optional[str] = Query(None),
):
    rows = await _svc.list_bookings(
        instructor_id=instructor_id, member_id=member_id,
    )
    return export_csv([_booking_dict(r) for r in rows], _PS_CSV_COLS, "private_sessions.csv")


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get(
    "/private-session-services",
    dependencies=[Depends(require_api_scope("private_sessions:read"))],
    summary="List private session service types",
)
async def list_service_types(
    ctx: dict = Depends(get_api_key_context),
    instructor_id: Optional[str] = Query(None),
):
    rows = await _svc.list_services(instructor_id=instructor_id, active_only=True)
    return [_service_dict(r) for r in rows]


@router.post(
    "/private-sessions",
    dependencies=[Depends(require_api_scope("private_sessions:write"))],
    status_code=201,
    summary="Book a private session",
)
async def create_private_session(
    body: PrivateSessionCreate,
    ctx: dict = Depends(get_api_key_context),
):
    try:
        row = await _svc.book_session({
            "member_id": body.member_id,
            "instructor_id": body.instructor_id,
            "private_service_id": body.service_id,
            "starts_at": body.starts_at,
            "intake_notes": body.intake_notes,
        })
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    result = _booking_dict(row)
    await _fire_webhook("private_session.created", result)
    return result


@router.get(
    "/private-sessions",
    dependencies=[Depends(require_api_scope("private_sessions:read"))],
    summary="List private sessions",
)
async def list_private_sessions(
    ctx: dict = Depends(get_api_key_context),
    member_id: Optional[str] = Query(None),
    instructor_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    from_date = date.fromisoformat(date_from) if date_from else None
    to_date = date.fromisoformat(date_to) if date_to else None
    rows = await _svc.list_bookings(
        instructor_id=instructor_id,
        member_id=member_id,
        from_date=from_date,
        to_date=to_date,
    )
    return [_booking_dict(r) for r in rows]


@router.get(
    "/private-sessions/{booking_id}",
    dependencies=[Depends(require_api_scope("private_sessions:read"))],
    summary="Get private session by ID",
)
async def get_private_session(
    booking_id: str,
    ctx: dict = Depends(get_api_key_context),
):
    row = await _svc.get_booking(booking_id)
    if not row:
        raise HTTPException(status_code=404, detail="Private session not found")
    return _booking_dict(row)


@router.delete(
    "/private-sessions/{booking_id}",
    dependencies=[Depends(require_api_scope("private_sessions:write"))],
    status_code=204,
    summary="Cancel a private session",
)
async def cancel_private_session(
    booking_id: str,
    ctx: dict = Depends(get_api_key_context),
):
    row = await _svc.cancel_booking(booking_id, reason="Cancelled via API")
    if not row:
        raise HTTPException(status_code=404, detail="Private session not found or already cancelled")
    await _fire_webhook("private_session.cancelled", _booking_dict(row))
