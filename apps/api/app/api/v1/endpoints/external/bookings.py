"""AuraFlow — External Bookings Endpoints

API-key-authenticated class booking, cancellation, and check-in.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.v1.dependencies.api_key_auth import get_api_key_context, require_api_scope
from app.services.scheduling.booking_service import BookingService, BookingError
from app.db.session import get_tenant_db
from app.services.external.csv_export import export_csv

router = APIRouter()
_svc = BookingService()


# ── Schemas ──────────────────────────────────────────────────────────────────

class BookingCreate(BaseModel):
    member_id: str
    session_id: str
    source: str = "api"
    notes: Optional[str] = None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fmt(dt):
    if dt and hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt) if dt else None


def _booking_dict(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "member_id": str(row["member_id"]),
        "class_session_id": str(row.get("class_session_id", "")),
        "status": row["status"],
        "source": row.get("source"),
        "booked_at": _fmt(row.get("booked_at")),
        "cancelled_at": _fmt(row.get("cancelled_at")),
        "checked_in_at": _fmt(row.get("checked_in_at")),
        "cancellation_reason": row.get("cancellation_reason"),
        "late_cancel": row.get("late_cancel", False),
        "waitlist_position": row.get("waitlist_position"),
        # Joined fields (may not always be present)
        "session_title": row.get("session_title"),
        "starts_at": _fmt(row.get("starts_at")),
        "ends_at": _fmt(row.get("ends_at")),
        "first_name": row.get("first_name"),
        "last_name": row.get("last_name"),
        "member_email": row.get("member_email"),
    }


async def _fire_webhook(event: str, payload: dict) -> None:
    try:
        from app.services.webhooks.webhook_delivery_service import WebhookDeliveryService
        await WebhookDeliveryService().fire_event(event, payload)
    except Exception:
        pass


# ── CSV Export ───────────────────────────────────────────────────────────────

_BOOKING_CSV_COLS = [
    ("id", "ID"),
    ("member_id", "Member ID"),
    ("first_name", "First Name"),
    ("last_name", "Last Name"),
    ("session_title", "Session"),
    ("starts_at", "Session Start"),
    ("status", "Status"),
    ("booked_at", "Booked At"),
    ("checked_in_at", "Checked In At"),
    ("cancelled_at", "Cancelled At"),
]


@router.get(
    "/bookings/export.csv",
    dependencies=[Depends(require_api_scope("bookings:read"))],
    summary="Export bookings as CSV",
)
async def export_bookings_csv(
    ctx: dict = Depends(get_api_key_context),
    member_id: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
):
    rows = await _fetch_bookings(member_id, session_id, status_filter)
    return export_csv(rows, _BOOKING_CSV_COLS, "bookings.csv")


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post(
    "/bookings",
    dependencies=[Depends(require_api_scope("bookings:write"))],
    status_code=201,
    summary="Book a class",
)
async def create_booking(
    body: BookingCreate,
    ctx: dict = Depends(get_api_key_context),
):
    import uuid as _uuid
    try:
        _uuid.UUID(body.member_id)
        _uuid.UUID(body.session_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail="member_id and session_id must be valid UUIDs")
    try:
        row = await _svc.book_class({
            "member_id": body.member_id,
            "class_session_id": body.session_id,
            "source": body.source,
            "notes": body.notes,
        })
    except BookingError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": str(exc)})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    result = _booking_dict(row)
    await _fire_webhook("booking.created", result)
    return result


@router.get(
    "/bookings",
    dependencies=[Depends(require_api_scope("bookings:read"))],
    summary="List bookings",
)
async def list_bookings(
    ctx: dict = Depends(get_api_key_context),
    member_id: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, le=500),
    offset: int = Query(0),
):
    rows = await _fetch_bookings(member_id, session_id, status_filter, limit, offset)
    return [_booking_dict(r) for r in rows]


@router.get(
    "/bookings/{booking_id}",
    dependencies=[Depends(require_api_scope("bookings:read"))],
    summary="Get booking by ID",
)
async def get_booking(
    booking_id: str,
    ctx: dict = Depends(get_api_key_context),
):
    row = await _svc.get_booking(booking_id)
    if not row:
        raise HTTPException(status_code=404, detail="Booking not found")
    return _booking_dict(row)


@router.delete(
    "/bookings/{booking_id}",
    dependencies=[Depends(require_api_scope("bookings:write"))],
    status_code=204,
    summary="Cancel a booking",
)
async def cancel_booking(
    booking_id: str,
    ctx: dict = Depends(get_api_key_context),
):
    row = await _svc.cancel_booking(booking_id, reason="Cancelled via API")
    if not row:
        raise HTTPException(status_code=404, detail="Booking not found or already cancelled")
    await _fire_webhook("booking.cancelled", _booking_dict(row))


@router.post(
    "/bookings/{booking_id}/check-in",
    dependencies=[Depends(require_api_scope("bookings:write"))],
    summary="Check in a booking",
)
async def check_in_booking(
    booking_id: str,
    ctx: dict = Depends(get_api_key_context),
):
    row = await _svc.check_in(booking_id)
    if not row:
        raise HTTPException(status_code=404, detail="Booking not found or not confirmed")
    result = _booking_dict(row)
    await _fire_webhook("booking.checked_in", result)
    return result


# ── Internal ─────────────────────────────────────────────────────────────────

async def _fetch_bookings(
    member_id: str | None = None,
    session_id: str | None = None,
    status_filter: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> list[dict]:
    conditions: list[str] = []
    params: list = []
    idx = 1

    if member_id:
        conditions.append(f"b.member_id = ${idx}")
        params.append(member_id)
        idx += 1
    if session_id:
        conditions.append(f"b.class_session_id = ${idx}")
        params.append(session_id)
        idx += 1
    if status_filter:
        conditions.append(f"b.status = ${idx}")
        params.append(status_filter)
        idx += 1

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    params.extend([limit, offset])
    async with get_tenant_db() as db:
        rows = await db.fetch(
            f"""
            SELECT b.*, cs.title AS session_title, cs.starts_at, cs.ends_at,
                   m.first_name, m.last_name, m.email AS member_email
            FROM bookings b
            JOIN class_sessions cs ON cs.id = b.class_session_id
            JOIN members m ON m.id = b.member_id
            {where}
            ORDER BY b.booked_at DESC
            LIMIT ${idx} OFFSET ${idx + 1}
            """,
            *params,
        )
    return [dict(r) for r in rows]
