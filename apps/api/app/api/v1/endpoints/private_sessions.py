"""AuraFlow — Private Session Endpoints

Private 1-on-1 sessions: service catalog, instructor availability,
slot computation, and booking lifecycle.
"""
from datetime import date, time, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.v1.dependencies.auth import get_current_user
from app.api.v1.dependencies.rbac import require_permission
from app.core.config import settings
from app.core.logging import logger
from app.services.scheduling.private_session_service import PrivateSessionService
from app.services.payments.stripe_service import StripeService
from app.services.email.email_service import EmailService

router = APIRouter()

# Keep stub routers for webhook module compatibility
stripe_router = APIRouter()
mux_router = APIRouter()

svc = PrivateSessionService()
stripe_svc = StripeService()
email_svc = EmailService()


# ── Schemas ──────────────────────────────────────────────────────────────────

class ServiceCreate(BaseModel):
    instructor_id: str
    name: str
    description: Optional[str] = None
    duration_minutes: int = 60
    price_cents: int
    buffer_before_minutes: int = 0
    buffer_after_minutes: int = 15
    max_per_day: Optional[int] = None
    visibility: str = "members_only"
    required_membership_type_id: Optional[str] = None
    is_virtual: bool = False


class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = None
    price_cents: Optional[int] = None
    buffer_before_minutes: Optional[int] = None
    buffer_after_minutes: Optional[int] = None
    max_per_day: Optional[int] = None
    visibility: Optional[str] = None
    is_virtual: Optional[bool] = None


class AvailabilitySlot(BaseModel):
    day_of_week: int  # 0=Monday..6=Sunday
    start_time: str   # HH:MM
    end_time: str      # HH:MM


class SetAvailability(BaseModel):
    slots: list[AvailabilitySlot]


class BlockTime(BaseModel):
    date: str       # YYYY-MM-DD
    start_time: str  # HH:MM
    end_time: str    # HH:MM


class BookSession(BaseModel):
    member_id: str
    instructor_id: str
    private_service_id: str
    starts_at: str  # ISO datetime
    intake_notes: Optional[str] = None
    as_package: bool = False  # Book as a package deal (creates credits + payment link)
    apply_credit_id: Optional[str] = None  # member_credits.id to consume


class CancelBooking(BaseModel):
    reason: Optional[str] = None
    cancelled_by_role: Optional[str] = None  # 'instructor' | 'member' | 'staff'


class CompleteBooking(BaseModel):
    instructor_notes: Optional[str] = None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _ts(val) -> str | None:
    if val is None:
        return None
    return val.isoformat() if hasattr(val, "isoformat") else str(val)


def _serialize(row: dict) -> dict:
    """Convert datetime/time/date fields to strings."""
    out = {}
    for k, v in row.items():
        if isinstance(v, (datetime, date, time)):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


# ── Private Services CRUD ───────────────────────────────────────────────────

@router.post("/services", status_code=201)
async def create_service(
    request: ServiceCreate,
    rbac: dict = Depends(require_permission("private_sessions.create_service")),
):
    service = await svc.create_service(request.model_dump())
    return {"data": _serialize(service)}


@router.get("/services")
async def list_services(
    instructor_id: Optional[str] = Query(None),
    active_only: bool = Query(True),
    current_user: dict = Depends(get_current_user),
):
    services = await svc.list_services(instructor_id, active_only)
    return {"data": [_serialize(s) for s in services]}


@router.get("/services/{service_id}")
async def get_service(
    service_id: str,
    current_user: dict = Depends(get_current_user),
):
    service = await svc.get_service(service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return {"data": _serialize(service)}


@router.put("/services/{service_id}")
async def update_service(
    service_id: str,
    request: ServiceUpdate,
    rbac: dict = Depends(require_permission("private_sessions.edit_service")),
):
    service = await svc.update_service(service_id, request.model_dump(exclude_unset=True))
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return {"data": _serialize(service)}


@router.delete("/services/{service_id}", status_code=200)
async def deactivate_service(
    service_id: str,
    rbac: dict = Depends(require_permission("private_sessions.delete_service")),
):
    result = await svc.deactivate_service(service_id)
    if not result:
        raise HTTPException(status_code=404, detail="Service not found")
    return {"data": {"deactivated": True}}


# ── Instructor Availability ────────────────────────────────────────────────

@router.get("/availability/{instructor_id}")
async def get_availability(
    instructor_id: str,
    current_user: dict = Depends(get_current_user),
):
    avail = await svc.get_availability(instructor_id)
    return {"data": [_serialize(a) for a in avail]}


@router.post("/availability/{instructor_id}")
async def set_availability(
    instructor_id: str,
    request: SetAvailability,
    rbac: dict = Depends(require_permission("private_sessions.set_availability")),
):
    slots = []
    for s in request.slots:
        slots.append({
            "day_of_week": s.day_of_week,
            "start_time": time.fromisoformat(s.start_time),
            "end_time": time.fromisoformat(s.end_time),
        })
    created = await svc.set_availability(instructor_id, slots)
    return {"data": [_serialize(a) for a in created]}


@router.post("/availability/{instructor_id}/block")
async def block_time(
    instructor_id: str,
    request: BlockTime,
    rbac: dict = Depends(require_permission("private_sessions.block_time")),
):
    blocked = await svc.add_blocked_time(
        instructor_id,
        date.fromisoformat(request.date),
        time.fromisoformat(request.start_time),
        time.fromisoformat(request.end_time),
    )
    return {"data": _serialize(blocked)}


# ── Available Slots ─────────────────────────────────────────────────────────

@router.get("/slots")
async def get_slots(
    instructor_id: str = Query(...),
    service_id: str = Query(...),
    date: str = Query(...),  # YYYY-MM-DD
    current_user: dict = Depends(get_current_user),
):
    from datetime import date as date_type
    target = date_type.fromisoformat(date)
    slots = await svc.get_available_slots(instructor_id, service_id, target)
    return {"data": slots}


# ── Bookings ────────────────────────────────────────────────────────────────

@router.post("/bookings", status_code=201)
async def book_session(
    request: BookSession,
    rbac: dict = Depends(require_permission("private_sessions.book", "private_sessions.book_self")),
):
    booking_data = request.model_dump()

    # If booking as a package, override price with package price
    if request.as_package:
        from app.db.session import get_tenant_db as _get_tdb
        async with _get_tdb() as db:
            pkg_svc = await db.fetchrow(
                "SELECT package_sessions, package_price_cents FROM private_services WHERE id = $1",
                request.private_service_id,
            )
        if not pkg_svc or not pkg_svc["package_sessions"]:
            raise HTTPException(status_code=400, detail="This service does not have a package option")
        # Store package info for after booking
        booking_data["_package_sessions"] = pkg_svc["package_sessions"]
        booking_data["_package_price"] = pkg_svc["package_price_cents"]

    try:
        booking = await svc.book_session(booking_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # If package booking, override the price to the package price
    if request.as_package and booking_data.get("_package_price"):
        from app.db.session import get_tenant_db as _get_tdb
        async with _get_tdb() as db:
            await db.execute(
                "UPDATE private_bookings SET price_cents = $1, updated_at = NOW() WHERE id = $2",
                booking_data["_package_price"], str(booking["id"]),
            )
        booking["price_cents"] = booking_data["_package_price"]

    full = await svc.get_booking(str(booking["id"]))

    # Auto-send payment link if staff booked a paid session for a member
    role = rbac.get("role")
    charge_amount = booking["price_cents"]
    if role in ("owner", "admin", "front_desk", "instructor") and charge_amount > 0:
        try:
            from app.core.tenant_context import require_tenant_context, get_organization_id
            from app.db.session import get_tenant_db

            async with get_tenant_db() as db:
                member = await db.fetchrow(
                    "SELECT id, first_name, last_name, email, stripe_customer_id FROM members WHERE id = $1",
                    booking["member_id"],
                )
            if member:
                org_id = get_organization_id()
                ctx = require_tenant_context()
                portal_base = f"{settings.APP_URL}/{ctx.slug}/portal"

                # Add package info to booking for Stripe metadata
                if request.as_package and booking_data.get("_package_sessions"):
                    full["_package_sessions"] = booking_data["_package_sessions"]
                    full["_package_service_id"] = request.private_service_id

                result = await stripe_svc.create_booking_payment_link(
                    org_id=org_id,
                    booking=full,
                    member=dict(member),
                    success_url=f"{portal_base}/private-lessons?booked=1",
                    cancel_url=f"{portal_base}/private-lessons?cancelled=1",
                )
                full["payment_url"] = result["url"]

                # Send payment email
                from zoneinfo import ZoneInfo
                starts = booking["starts_at"]
                if hasattr(starts, 'tzinfo') and starts.tzinfo is None:
                    starts = starts.replace(tzinfo=ZoneInfo("UTC"))
                local_time = starts.astimezone(ZoneInfo("America/Los_Angeles"))
                session_date = local_time.strftime("%A, %B %d, %Y")
                session_time = local_time.strftime("%-I:%M %p")
                price_display = f"${booking['price_cents'] / 100:.2f}"

                from app.db.session import get_global_db
                async with get_global_db() as db:
                    org = await db.fetchrow("SELECT name FROM af_global.organizations WHERE id = $1", org_id)
                studio_name = org["name"] if org else "the studio"

                html = f"""
                <h2>Complete Payment for Your Private Session</h2>
                <p>Hi {member['first_name']},</p>
                <p>A private session has been booked for you at <strong>{studio_name}</strong>:</p>
                <table style="margin: 16px 0; border-collapse: collapse;">
                  <tr><td style="padding: 6px 12px; color: #666;">Service</td><td style="padding: 6px 12px; font-weight: 600;">{full.get('service_name', 'Private Session')}</td></tr>
                  <tr><td style="padding: 6px 12px; color: #666;">Date</td><td style="padding: 6px 12px; font-weight: 600;">{session_date}</td></tr>
                  <tr><td style="padding: 6px 12px; color: #666;">Time</td><td style="padding: 6px 12px; font-weight: 600;">{session_time}</td></tr>
                  <tr><td style="padding: 6px 12px; color: #666;">Amount</td><td style="padding: 6px 12px; font-weight: 600;">{price_display}</td></tr>
                </table>
                <p>Please complete your payment to confirm the booking:</p>
                <p style="margin: 24px 0;">
                  <a href="{result['url']}" style="background-color: #4f46e5; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: 600;">
                    Pay {price_display}
                  </a>
                </p>
                <p style="color: #666; font-size: 13px;">If the button doesn't work, copy and paste this link:<br/>
                <a href="{result['url']}">{result['url']}</a></p>
                """
                await email_svc.send_email(
                    to_email=member["email"],
                    subject=f"Payment Required: {full.get('service_name', 'Private Session')} on {session_date}",
                    html_content=html,
                    member_id=str(member["id"]),
                    email_type="payment_request",
                )
                logger.info("Auto-sent payment link for staff booking", booking_id=str(booking["id"]))
        except Exception as e:
            logger.warning("Failed to auto-send payment link", error=str(e), booking_id=str(booking["id"]))

    return {"data": _serialize(full)}


@router.get("/bookings")
async def list_bookings(
    instructor_id: Optional[str] = Query(None),
    member_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    payment_status: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    bookings = await svc.list_bookings(
        instructor_id=instructor_id,
        member_id=member_id,
        status=status,
        payment_status=payment_status,
    )
    return {"data": [_serialize(b) for b in bookings]}


@router.get("/bookings/{booking_id}")
async def get_booking(
    booking_id: str,
    current_user: dict = Depends(get_current_user),
):
    booking = await svc.get_booking(booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return {"data": _serialize(booking)}


@router.post("/bookings/{booking_id}/confirm")
async def confirm_booking(
    booking_id: str,
    rbac: dict = Depends(require_permission("private_sessions.confirm_booking")),
):
    result = await svc.confirm_booking(booking_id)
    if not result:
        raise HTTPException(status_code=400, detail="Booking not found or not pending")
    full = await svc.get_booking(booking_id)
    return {"data": _serialize(full)}


@router.post("/bookings/{booking_id}/cancel")
async def cancel_booking(
    booking_id: str,
    request: CancelBooking,
    rbac: dict = Depends(require_permission("private_sessions.cancel_booking", "private_sessions.cancel_own")),
):
    try:
        result = await svc.cancel_booking(
            booking_id,
            reason=request.reason,
            cancelled_by_role=request.cancelled_by_role,
            cancelled_by_user_id=rbac["user_id"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not result:
        raise HTTPException(status_code=400, detail="Booking not found or already cancelled/completed")
    full = await svc.get_booking(booking_id)
    out = {"data": _serialize(full)}
    if result.get("granted_credit_id"):
        out["granted_credit"] = {
            "id": result["granted_credit_id"],
            "amount_cents": result["granted_credit_amount_cents"],
        }
    return out


@router.post("/bookings/{booking_id}/complete")
async def complete_booking(
    booking_id: str,
    request: CompleteBooking,
    rbac: dict = Depends(require_permission("private_sessions.complete_booking")),
):
    result = await svc.complete_booking(booking_id, request.instructor_notes)
    if not result:
        raise HTTPException(status_code=400, detail="Booking not found or already cancelled/completed")
    full = await svc.get_booking(booking_id)
    return {"data": _serialize(full)}


@router.post("/bookings/{booking_id}/send-payment-link")
async def send_payment_link(
    booking_id: str,
    rbac: dict = Depends(require_permission("private_sessions.send_payment_link")),
):
    """Generate a Square hosted payment link for a pending booking and
    email it to the member. Square only — no Stripe."""
    from app.core.tenant_context import require_tenant_context, get_organization_id
    from app.db.session import get_tenant_db, get_global_db
    from app.services.payments.square_oauth_service import square_oauth_service
    from app.services.payments.square_service import _client as _sq_client, _idem

    booking = await svc.get_booking(booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking["status"] not in ("pending", "confirmed"):
        raise HTTPException(status_code=400, detail="Booking is not pending or confirmed")
    if booking["price_cents"] <= 0:
        raise HTTPException(status_code=400, detail="Booking has no charge — payment not required")

    # Get the member
    async with get_tenant_db() as db:
        member = await db.fetchrow(
            "SELECT id, first_name, last_name, email FROM members WHERE id = $1",
            booking["member_id"],
        )
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    org_id = get_organization_id()
    ctx = require_tenant_context()
    portal_base = f"{settings.APP_URL}/{ctx.slug}/portal"

    # ── Build a Square Checkout Payment Link ──
    access_token = await square_oauth_service.get_merchant_access_token(org_id)
    if not access_token:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Square not connected. Connect Square in Settings → Billing.",
                "code": "SQUARE_NOT_CONNECTED",
            },
        )
    async with get_global_db() as gdb:
        loc_row = await gdb.fetchrow(
            "SELECT square_location_id FROM af_global.organizations WHERE id=$1",
            org_id,
        )
    location_id = loc_row and loc_row["square_location_id"]
    if not location_id:
        raise HTTPException(status_code=400, detail="Square location not configured")

    service_name = booking.get("service_name") or "Private Session"
    sq_client = _sq_client(access_token)
    pre_populated: dict = {}
    if member["email"]:
        pre_populated["buyer_email"] = member["email"]
    from app.services.payments.billing_dispatcher import _square_app_fee
    app_fee_cents = _square_app_fee(booking["price_cents"])
    try:
        sq_resp = await sq_client.checkout.payment_links.create(
            idempotency_key=_idem(),
            description=f"{service_name} (booking {str(booking['id'])[:8]})",
            order={
                "location_id": location_id,
                "line_items": [{
                    "name": service_name[:255],
                    "quantity": "1",
                    "base_price_money": {"amount": booking["price_cents"], "currency": "USD"},
                }],
                "reference_id": str(booking["id"])[:40],
                "metadata": {
                    "auraflow_booking_id": str(booking["id"]),
                    "auraflow_org_schema": ctx.schema_name,
                    "auraflow_checkout_type": "private_session",
                },
            },
            checkout_options={
                "redirect_url": f"{portal_base}/private-lessons?booked=1",
                "app_fee_money": {"amount": app_fee_cents, "currency": "USD"},
            },
            pre_populated_data=pre_populated or None,
        )
        if getattr(sq_resp, "errors", None):
            raise RuntimeError(f"Square error: {sq_resp.errors}")
        pl = sq_resp.payment_link
        # Mirror the prior helper's return shape
        result = {"url": pl.url, "id": pl.id}
        # Persist the link on the booking row so /resend works
        async with get_tenant_db() as db:
            await db.execute(
                "UPDATE private_bookings SET payment_url=$2, payment_status='unpaid', updated_at=NOW() WHERE id=$1",
                str(booking["id"]), pl.url,
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Square payment link failed: {e}")

    # Format session date/time for email
    from zoneinfo import ZoneInfo
    starts = booking["starts_at"]
    if starts.tzinfo is None:
        starts = starts.replace(tzinfo=ZoneInfo("UTC"))
    local_time = starts.astimezone(ZoneInfo("America/Los_Angeles"))
    session_date = local_time.strftime("%A, %B %d, %Y")
    session_time = local_time.strftime("%-I:%M %p")
    price_display = f"${booking['price_cents'] / 100:.2f}"

    # Get org name
    from app.db.session import get_global_db
    async with get_global_db() as db:
        org = await db.fetchrow("SELECT name FROM af_global.organizations WHERE id = $1", org_id)
    studio_name = org["name"] if org else "the studio"

    # Send payment link email
    html = f"""
    <h2>Complete Payment for Your Private Session</h2>
    <p>Hi {member['first_name']},</p>
    <p>A private session has been booked for you at <strong>{studio_name}</strong>:</p>
    <table style="margin: 16px 0; border-collapse: collapse;">
      <tr><td style="padding: 6px 12px; color: #666;">Service</td><td style="padding: 6px 12px; font-weight: 600;">{booking.get('service_name', 'Private Session')}</td></tr>
      <tr><td style="padding: 6px 12px; color: #666;">Date</td><td style="padding: 6px 12px; font-weight: 600;">{session_date}</td></tr>
      <tr><td style="padding: 6px 12px; color: #666;">Time</td><td style="padding: 6px 12px; font-weight: 600;">{session_time}</td></tr>
      <tr><td style="padding: 6px 12px; color: #666;">Amount</td><td style="padding: 6px 12px; font-weight: 600;">{price_display}</td></tr>
    </table>
    <p>Please complete your payment to confirm the booking:</p>
    <p style="margin: 24px 0;">
      <a href="{result['url']}" style="background-color: #4f46e5; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: 600;">
        Pay {price_display}
      </a>
    </p>
    <p style="color: #666; font-size: 13px;">If the button doesn't work, copy and paste this link into your browser:<br/>
    <a href="{result['url']}">{result['url']}</a></p>
    """

    await email_svc.send_email(
        to_email=member["email"],
        subject=f"Payment Required: {booking.get('service_name', 'Private Session')} on {session_date}",
        html_content=html,
        member_id=str(member["id"]),
        email_type="payment_request",
    )

    return {"data": {"payment_url": result["url"], "emailed": True}}
