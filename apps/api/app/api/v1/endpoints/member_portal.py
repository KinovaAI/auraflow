"""AuraFlow — Member Portal Endpoints

Self-service endpoints for authenticated members. Every endpoint is
gated by an action-level `require_permission("members.view_own_profile"
/ "schedule.create_booking" / etc.)`. Those keys are seeded into every
member's user_permissions on signup via the member role template, so
any authenticated member passes them. Members can only view/modify
their own data — the service layer scopes every query to rbac.user_id.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.v1.dependencies.rbac import require_permission
from app.services.portal.portal_service import PortalService
from app.services.payments.stripe_service import StripeService
from app.services.payments import billing_dispatcher
from app.services.ai.review_service import ReviewService
from app.core.tenant_context import get_organization_id
from app.db.session import get_tenant_db, get_global_db

router = APIRouter()
svc = PortalService()
stripe_svc = StripeService()
review_svc = ReviewService()


# ── Schemas ──────────────────────────────────────────────────────────────────

class PortalProfileResponse(BaseModel):
    id: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    photo_url: Optional[str] = None
    total_visits: int = 0
    member_number: Optional[str] = None
    email_opt_in: bool = True
    sms_opt_in: bool = True
    payment_setup_required: bool = False
    waiver_required: bool = False
    created_at: Optional[str] = None


class PortalProfileUpdate(BaseModel):
    phone: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    email_opt_in: Optional[bool] = None
    sms_opt_in: Optional[bool] = None


class PortalBookingResponse(BaseModel):
    id: str
    class_session_id: str
    session_title: Optional[str] = None
    class_type_name: Optional[str] = None
    class_category: Optional[str] = None
    instructor_name: Optional[str] = None
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None
    status: str
    booked_at: Optional[str] = None
    waitlist_position: Optional[int] = None
    is_virtual: bool = False
    zoom_join_url: Optional[str] = None
    zoom_password: Optional[str] = None


class PortalSessionResponse(BaseModel):
    id: str
    title: Optional[str] = None
    starts_at: str
    ends_at: Optional[str] = None
    class_type_name: Optional[str] = None
    class_category: Optional[str] = None
    class_description: Optional[str] = None
    level: Optional[str] = None
    instructor_name: Optional[str] = None
    room_name: Optional[str] = None
    spots_remaining: int = 0
    is_full: bool = False
    waitlist_available: bool = False
    is_virtual: bool = False


class BookClassRequest(BaseModel):
    session_id: str
    membership_id: Optional[str] = None


class CancelBookingRequest(BaseModel):
    reason: Optional[str] = None


class PortalMembershipResponse(BaseModel):
    id: str
    type_name: str
    membership_type: Optional[str] = None
    status: str
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None
    classes_remaining: Optional[int] = None
    auto_renew: Optional[bool] = None
    price_cents: Optional[int] = None
    billing_period: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    square_subscription_id: Optional[str] = None
    current_period_end: Optional[str] = None


# ── Workshop / Course Schemas ────────────────────────────────────────────────

class PortalCourseResponse(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    type: str
    instructor_name: Optional[str] = None
    price_cents: int = 0
    early_bird_price_cents: Optional[int] = None
    early_bird_deadline: Optional[str] = None
    is_early_bird_active: bool = False
    capacity: Optional[int] = None
    enrolled_count: int = 0
    spots_remaining: Optional[int] = None
    location: Optional[str] = None
    is_virtual: bool = False
    image_url: Optional[str] = None
    prerequisites: Optional[str] = None
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None


class PortalCourseSessionResponse(BaseModel):
    id: str
    title: Optional[str] = None
    session_number: int = 0
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None
    location: Optional[str] = None
    is_virtual: bool = False


class PortalCourseDetailResponse(PortalCourseResponse):
    sessions: list[PortalCourseSessionResponse] = []


class PortalEnrollmentResponse(BaseModel):
    id: str
    course_id: str
    course_title: Optional[str] = None
    course_type: Optional[str] = None
    status: str
    paid_price_cents: Optional[int] = None
    enrolled_at: Optional[str] = None
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None
    instructor_name: Optional[str] = None
    is_virtual: bool = False


class PortalCourseCheckoutRequest(BaseModel):
    success_url: str
    cancel_url: str


# ── Private Lessons Schemas ──────────────────────────────────────────────────

class PortalInstructorResponse(BaseModel):
    id: str
    display_name: str
    bio: Optional[str] = None
    photo_url: Optional[str] = None
    specialties: list[str] = []
    certifications: list[str] = []


class PortalPrivateServiceResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    duration_minutes: int
    price_cents: int
    is_virtual: bool = False


class PortalTimeSlotResponse(BaseModel):
    start_time: str
    end_time: str
    duration_minutes: int


class PortalBookPrivateRequest(BaseModel):
    instructor_id: str
    private_service_id: str
    starts_at: str
    intake_notes: Optional[str] = None
    success_url: str
    cancel_url: str


class PortalPrivateBookingResponse(BaseModel):
    id: str
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None
    status: str
    is_virtual: bool = False
    zoom_join_url: Optional[str] = None
    service_name: Optional[str] = None
    duration_minutes: Optional[int] = None
    instructor_name: Optional[str] = None
    instructor_photo: Optional[str] = None
    price_cents: Optional[int] = None
    payment_status: Optional[str] = None
    payment_url: Optional[str] = None
    created_at: Optional[str] = None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fmt(dt):
    if dt and hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt) if dt else None


def _profile_response(member: dict) -> PortalProfileResponse:
    dob = member.get("date_of_birth")
    return PortalProfileResponse(
        id=str(member["id"]),
        first_name=member["first_name"],
        last_name=member["last_name"],
        email=member["email"],
        phone=member.get("phone"),
        date_of_birth=str(dob) if dob else None,
        gender=member.get("gender"),
        emergency_contact_name=member.get("emergency_contact_name"),
        emergency_contact_phone=member.get("emergency_contact_phone"),
        photo_url=member.get("photo_url"),
        total_visits=member.get("total_visits", 0),
        member_number=member.get("member_number"),
        email_opt_in=member.get("email_opt_in", True),
        sms_opt_in=member.get("sms_opt_in", True),
        payment_setup_required=member.get("payment_setup_required", False),
        created_at=_fmt(member.get("created_at")),
    )


def _booking_response(b: dict) -> PortalBookingResponse:
    return PortalBookingResponse(
        id=str(b["id"]),
        class_session_id=str(b["class_session_id"]),
        session_title=b.get("session_title"),
        class_type_name=b.get("class_type_name"),
        class_category=b.get("class_category"),
        instructor_name=b.get("instructor_name"),
        starts_at=_fmt(b.get("starts_at")),
        ends_at=_fmt(b.get("ends_at")),
        status=b["status"],
        booked_at=_fmt(b.get("booked_at")),
        waitlist_position=b.get("waitlist_position"),
        is_virtual=b.get("is_virtual", False),
        zoom_join_url=b.get("zoom_join_url"),
        zoom_password=b.get("zoom_password"),
    )


def _session_response(s: dict) -> PortalSessionResponse:
    return PortalSessionResponse(
        id=str(s["id"]),
        title=s.get("title"),
        starts_at=_fmt(s["starts_at"]),
        ends_at=_fmt(s.get("ends_at")),
        class_type_name=s.get("class_type_name"),
        class_category=s.get("class_category"),
        class_description=s.get("class_description"),
        level=s.get("level"),
        instructor_name=s.get("instructor_name"),
        room_name=s.get("room_name"),
        spots_remaining=s.get("spots_remaining", 0),
        is_full=s.get("is_full", False),
        waitlist_available=s.get("waitlist_available", False),
        is_virtual=s.get("is_virtual", False),
    )


def _membership_response(m: dict) -> PortalMembershipResponse:
    return PortalMembershipResponse(
        id=str(m["id"]),
        type_name=m["type_name"],
        membership_type=m.get("membership_type"),
        status=m["status"],
        starts_at=_fmt(m.get("starts_at")),
        ends_at=_fmt(m.get("ends_at")),
        classes_remaining=m.get("classes_remaining"),
        auto_renew=m.get("auto_renew"),
        price_cents=m.get("price_cents"),
        billing_period=m.get("billing_period"),
        stripe_subscription_id=m.get("stripe_subscription_id"),
        square_subscription_id=m.get("square_subscription_id"),
        current_period_end=_fmt(m.get("current_period_end")),
    )


# ── Profile ──────────────────────────────────────────────────────────────────

@router.get("/me", response_model=PortalProfileResponse)
async def get_my_profile(
    rbac: dict = Depends(require_permission("members.view_own_profile")),
):
    """Get the authenticated member's profile."""
    profile = await svc.get_my_profile(rbac["user_id"])
    if not profile:
        raise HTTPException(status_code=404, detail="Member profile not found. Please contact the studio.")
    resp = _profile_response(profile)
    # Check if waiver is needed
    from app.db.session import get_tenant_db
    async with get_tenant_db() as db:
        has_waiver = await db.fetchval(
            "SELECT EXISTS(SELECT 1 FROM waiver_signatures WHERE member_id = $1)",
            str(profile["id"]),
        )
        has_template = await db.fetchval(
            "SELECT EXISTS(SELECT 1 FROM waiver_templates WHERE is_active = TRUE)",
        )
    if has_template and not has_waiver:
        resp.waiver_required = True
    return resp


@router.put("/me", response_model=PortalProfileResponse)
async def update_my_profile(
    request: PortalProfileUpdate,
    rbac: dict = Depends(require_permission("members.edit_own_profile")),
):
    """Update the authenticated member's profile (restricted fields only)."""
    updated = await svc.update_my_profile(
        rbac["user_id"],
        request.model_dump(exclude_unset=True),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Member profile not found")
    return _profile_response(updated)


# ── Schedule ─────────────────────────────────────────────────────────────────

@router.get("/schedule", response_model=list[PortalSessionResponse])
async def browse_schedule(
    start: Optional[str] = Query(None, description="Start date ISO 8601"),
    end: Optional[str] = Query(None, description="End date ISO 8601"),
    class_type_id: Optional[str] = Query(None),
    instructor_id: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    rbac: dict = Depends(require_permission("schedule.view_public")),
):
    """Browse upcoming class sessions with availability info."""
    from datetime import datetime, timezone

    start_dt = datetime.fromisoformat(start) if start else None
    end_dt = datetime.fromisoformat(end) if end else None

    sessions = await svc.get_upcoming_sessions(
        start=start_dt,
        end=end_dt,
        class_type_id=class_type_id,
        instructor_id=instructor_id,
        limit=limit,
    )
    return [_session_response(s) for s in sessions]


# ── Bookings ─────────────────────────────────────────────────────────────────

@router.get("/bookings", response_model=list[PortalBookingResponse])
async def get_my_bookings(
    upcoming_only: bool = Query(False),
    limit: int = Query(50, le=200),
    rbac: dict = Depends(require_permission("schedule.view_own_bookings")),
):
    """Get the authenticated member's bookings."""
    bookings = await svc.get_my_bookings(
        rbac["user_id"],
        upcoming_only=upcoming_only,
        limit=limit,
    )
    return [_booking_response(b) for b in bookings]


@router.post("/bookings", response_model=PortalBookingResponse, status_code=201)
async def book_class(
    request: BookClassRequest,
    rbac: dict = Depends(require_permission("schedule.create_booking")),
):
    """Book the authenticated member into a class session.

    On error, returns ``{"detail": "...", "error_code": "..."}`` where
    ``error_code`` is one of: ``session_not_found``, ``session_cancelled``,
    ``already_booked``, ``no_membership``, ``waiver_required``, ``class_full``.
    """
    from app.services.scheduling.booking_service import BookingError

    try:
        booking = await svc.book_class(
            rbac["user_id"],
            request.session_id,
            membership_id=request.membership_id,
        )
    except BookingError as e:
        raise HTTPException(
            status_code=409 if e.code == "already_booked" else 400,
            detail={"error_code": e.code, "message": str(e)},
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error_code": "booking_error", "message": str(e)})

    return _booking_response(booking)


@router.delete("/bookings/{booking_id}", status_code=204)
async def cancel_my_booking(
    booking_id: str,
    rbac: dict = Depends(require_permission("schedule.cancel_own_booking")),
):
    """Cancel the authenticated member's booking."""
    try:
        result = await svc.cancel_my_booking(rbac["user_id"], booking_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not result:
        raise HTTPException(status_code=404, detail="Booking not found")


# ── Memberships ──────────────────────────────────────────────────────────────

@router.get("/memberships", response_model=list[PortalMembershipResponse])
async def get_my_memberships(
    rbac: dict = Depends(require_permission("memberships.view_own")),
):
    """Get the authenticated member's active memberships."""
    memberships = await svc.get_my_memberships(rbac["user_id"])
    return [_membership_response(m) for m in memberships]


# ── Available Membership Types ─────────────────────────────────────────────────

class PortalMembershipTypeResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    type: str
    class_count: Optional[int] = None
    price_cents: int
    billing_period: Optional[str] = None
    duration_days: Optional[int] = None
    is_founding_rate: bool = False
    trial_days: int = 0
    freeze_allowed: bool = False
    is_public: bool = True


@router.get("/membership-types", response_model=list[PortalMembershipTypeResponse])
async def get_available_membership_types(
    rbac: dict = Depends(require_permission("memberships.view_public")),
):
    """Get publicly available membership types for this studio. Hides free offers already used."""
    user_id = rbac.get("user_id")
    types = await svc.get_available_membership_types(user_id=user_id)
    return [PortalMembershipTypeResponse(**t) for t in types]


# ── Checkout ──────────────────────────────────────────────────────────────────

class PortalCheckoutRequest(BaseModel):
    membership_type_id: str
    success_url: str
    cancel_url: str


@router.post("/checkout")
async def portal_checkout(
    request: PortalCheckoutRequest,
    rbac: dict = Depends(require_permission("memberships.purchase")),
):
    """Create a checkout session for the authenticated member to buy a
    membership.

    Stripe-mode studios get a Stripe Checkout hosted session URL.
    Square-mode studios get a 400 with a directive to use the Web
    Payments SDK + /portal/memberships/purchase-square flow (which
    posts a tokenized nonce + creates either a Square Subscription
    for recurring types or a one-off CreatePayment for packs).
    """
    member = await svc.get_my_profile(rbac["user_id"])
    if not member:
        raise HTTPException(status_code=404, detail="Member profile not found")

    org_id = get_organization_id()
    provider = await billing_dispatcher.get_provider(org_id)
    if provider == "square":
        raise HTTPException(
            status_code=400,
            detail={
                "error": "This studio uses Square — tokenize via Web Payments SDK and call /portal/memberships/purchase-square",
                "code": "WRONG_PROVIDER_FOR_ENDPOINT",
            },
        )

    try:
        result = await stripe_svc.create_checkout_session(
            org_id=org_id,
            member_id=str(member["id"]),
            membership_type_id=request.membership_type_id,
            success_url=request.success_url,
            cancel_url=request.cancel_url,
        )
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Transactions ──────────────────────────────────────────────────────────────

class PortalTransactionResponse(BaseModel):
    id: str
    amount_cents: int
    type: str
    status: str
    description: Optional[str] = None
    created_at: Optional[str] = None


@router.get("/transactions", response_model=list[PortalTransactionResponse])
async def get_my_transactions(
    limit: int = Query(50, le=200),
    rbac: dict = Depends(require_permission("payments.view_own")),
):
    """Get the authenticated member's payment history."""
    transactions = await svc.get_my_transactions(rbac["user_id"], limit)
    return [PortalTransactionResponse(**t) for t in transactions]


# ── Billing Portal ────────────────────────────────────────────────────────────

class PortalBillingRequest(BaseModel):
    return_url: str


class PortalSaveCardSquareRequest(BaseModel):
    source_id: str   # Square Web Payments SDK nonce (cnon:...)
    cardholder_name: Optional[str] = None


@router.post("/payment-methods/save-square")
async def save_card_square(
    request: PortalSaveCardSquareRequest,
    rbac: dict = Depends(require_permission("payments.manage_own")),
):
    """Save a card on file via Square Web Payments SDK nonce.

    Same pattern as `/portal/memberships/purchase-square` — the
    frontend tokenizes the card via Square's Web Payments SDK (in a
    popup on the same page as the studio's portal) and posts the
    resulting nonce here. We ensure the member has a Square Customer
    record (creating one on first save), then call the Square Cards
    API to attach the card to that customer for future charges /
    renewals. No redirect, no external page, no Stripe.
    """
    member = await svc.get_my_profile(rbac["user_id"])
    if not member:
        raise HTTPException(status_code=404, detail="Member profile not found")

    org_id = get_organization_id()

    from app.services.members.phi_helpers import decrypt_phone
    async with get_tenant_db() as db:
        member_row = await db.fetchrow(
            "SELECT id, email, first_name, last_name, phone_enc, square_customer_id FROM members WHERE id = $1",
            str(member["id"]),
        )
    if not member_row:
        raise HTTPException(status_code=404, detail="Member profile not found")

    # Ensure Square Customer (creates one if first save)
    customer = await billing_dispatcher.ensure_customer(
        organization_id=org_id,
        member_id=str(member_row["id"]),
        email=member_row["email"],
        first_name=member_row["first_name"],
        last_name=member_row["last_name"],
        phone=decrypt_phone(member_row),
        existing_square_customer_id=member_row["square_customer_id"],
    )
    customer_id = customer["customer_id"]
    if customer.get("created"):
        async with get_tenant_db() as db:
            await db.execute(
                "UPDATE members SET square_customer_id = $2 WHERE id = $1",
                str(member_row["id"]), customer_id,
            )

    # Save the card to the Square customer
    try:
        card = await billing_dispatcher.save_card_on_file(
            organization_id=org_id,
            customer_id=customer_id,
            source_id=request.source_id,
            cardholder_name=request.cardholder_name,
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not save card: {str(e)}",
        )

    return {
        "data": {
            "saved": True,
            "card_id": card.get("card_id"),
            "card_brand": card.get("card_brand"),
            "last_4": card.get("last_4"),
        }
    }


@router.post("/billing-portal")
async def portal_billing(
    request: PortalBillingRequest,
    rbac: dict = Depends(require_permission("payments.manage_own")),
):
    """Create a Stripe Customer Portal session for the authenticated member."""
    member = await svc.get_my_profile(rbac["user_id"])
    if not member:
        raise HTTPException(status_code=404, detail="Member profile not found")

    org_id = get_organization_id()
    try:
        result = await stripe_svc.create_customer_portal_session(
            org_id=org_id,
            member_id=str(member["id"]),
            return_url=request.return_url,
        )
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Membership Purchase (3A) ──────────────────────────────────────────────

class PortalMembershipPurchaseRequest(BaseModel):
    membership_type_id: str
    success_url: str
    cancel_url: str


@router.post("/memberships/purchase")
async def purchase_membership(
    request: PortalMembershipPurchaseRequest,
    rbac: dict = Depends(require_permission("memberships.purchase")),
):
    """Create a Stripe Checkout session for the authenticated member.

    Stripe-mode only — Square-mode studios use Web Payments SDK +
    /portal/memberships/purchase-square."""
    member = await svc.get_my_profile(rbac["user_id"])
    if not member:
        raise HTTPException(status_code=404, detail="Member profile not found")

    org_id = get_organization_id()
    provider = await billing_dispatcher.get_provider(org_id)
    if provider == "square":
        raise HTTPException(
            status_code=400,
            detail={
                "error": "This studio uses Square — use /portal/memberships/purchase-square",
                "code": "WRONG_PROVIDER_FOR_ENDPOINT",
            },
        )

    try:
        result = await stripe_svc.create_checkout_session(
            org_id=org_id,
            member_id=str(member["id"]),
            membership_type_id=request.membership_type_id,
            success_url=request.success_url,
            cancel_url=request.cancel_url,
        )
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Square Membership Purchase ────────────────────────────────────────
# Square has no hosted Checkout. The frontend tokenizes the card via
# Web Payments SDK (returns a nonce as source_id), then calls this
# endpoint. We:
#   1. Ensure a Square Customer for the member (members.square_customer_id).
#   2. Save the card on file via Cards API (Don's always-save-card rule).
#   3. For unlimited / class_pack / intro_offer membership types, either:
#      - Create a recurring Square Subscription (unlimited monthly /
#        annual), OR
#      - Create a one-off Payment for fixed-duration packs.
#   4. Insert the member_memberships row mirroring what the Stripe
#      webhook would have done.
# All routed through billing_dispatcher so the contract test (no
# cross-provider leaks) keeps holding.


class PortalSquarePurchaseRequest(BaseModel):
    membership_type_id: str
    source_id: str   # Web Payments SDK nonce (cnon:...)
    cardholder_name: Optional[str] = None


@router.post("/memberships/purchase-square")
async def purchase_membership_square(
    request: PortalSquarePurchaseRequest,
    rbac: dict = Depends(require_permission("memberships.purchase")),
):
    """Tokenized-card membership purchase for square-mode studios.

    The frontend ALWAYS saves the card on file before charging (per
    Don's standing rule) and the dispatcher handles either a recurring
    Square Subscription OR a one-off payment based on the membership
    type's recurrence."""
    member = await svc.get_my_profile(rbac["user_id"])
    if not member:
        raise HTTPException(status_code=404, detail="Member profile not found")

    org_id = get_organization_id()
    provider = await billing_dispatcher.get_provider(org_id)
    if provider != "square":
        raise HTTPException(
            status_code=400,
            detail={
                "error": "This studio uses Stripe — use /portal/memberships/purchase",
                "code": "WRONG_PROVIDER_FOR_ENDPOINT",
            },
        )

    # Load membership_type
    from app.db.session import get_tenant_db
    async with get_tenant_db() as db:
        mt = await db.fetchrow(
            """
            SELECT id, name, type, price_cents, billing_period,
                   duration_days, class_count, new_members_only,
                   trial_starts_on_first_class
            FROM membership_types WHERE id = $1 AND is_active = TRUE
            """,
            request.membership_type_id,
        )
        if not mt:
            raise HTTPException(status_code=404, detail="Membership type not found")
        existing_member_row = await db.fetchrow(
            """
            SELECT square_customer_id, first_name, last_name, email, phone_enc
            FROM members WHERE id = $1
            """,
            str(member["id"]),
        )

        # $0 membership (e.g., FREE First Week Unlimited) — provision locally,
        # no Square customer/card/subscription. Square rejects $0 subscriptions
        # ("Amount zero only allowed for free trial phase"), and there's no
        # money to move.
        if int(mt["price_cents"]) == 0:
            if mt["new_members_only"]:
                prior = await db.fetchval(
                    "SELECT COUNT(*) FROM member_memberships WHERE member_id = $1",
                    str(member["id"]),
                )
                if prior and prior > 0:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "error": f"'{mt['name']}' is a new-students-only offer.",
                            "code": "NOT_ELIGIBLE_NEW_MEMBERS_ONLY",
                            "prior_membership_count": int(prior),
                        },
                    )
            # Trial-start-on-first-class types leave ends_at NULL — the
            # check-in handler in booking_service sets it to NOW + duration
            # the first time the member checks into a class.
            ends_at_sql = "NULL"
            if mt["duration_days"] and not mt["trial_starts_on_first_class"]:
                ends_at_sql = f"NOW() + INTERVAL '{int(mt['duration_days'])} days'"
            free_row = await db.fetchrow(
                f"""
                INSERT INTO member_memberships
                    (member_id, membership_type_id, status, starts_at, ends_at,
                     classes_remaining, billing_provider, created_at)
                VALUES ($1, $2, 'active', NOW(), {ends_at_sql}, $3, 'square', NOW())
                RETURNING id
                """,
                str(member["id"]), str(mt["id"]), mt["class_count"],
            )
            return {
                "data": {
                    "membership_id": str(free_row["id"]),
                    "kind": "free",
                }
            }

        # New-members-only gate — refuse BEFORE any Square API call so
        # we don't tokenize / charge for an ineligible purchase.
        if mt["new_members_only"]:
            prior = await db.fetchval(
                "SELECT COUNT(*) FROM member_memberships WHERE member_id = $1",
                str(member["id"]),
            )
            if prior and prior > 0:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": f"'{mt['name']}' is a new-students-only offer.",
                        "code": "NOT_ELIGIBLE_NEW_MEMBERS_ONLY",
                        "prior_membership_count": int(prior),
                    },
                )

    # 1. Ensure Square Customer
    from app.services.members.phi_helpers import decrypt_phone
    customer = await billing_dispatcher.ensure_customer(
        organization_id=org_id,
        member_id=str(member["id"]),
        email=existing_member_row["email"],
        first_name=existing_member_row["first_name"],
        last_name=existing_member_row["last_name"],
        phone=decrypt_phone(existing_member_row),
        existing_square_customer_id=existing_member_row["square_customer_id"],
    )
    customer_id = customer["customer_id"]
    if customer["created"]:
        async with get_tenant_db() as db:
            await db.execute(
                "UPDATE members SET square_customer_id = $2 WHERE id = $1",
                str(member["id"]), customer_id,
            )

    # 2. Save card on file
    card = await billing_dispatcher.save_card_on_file(
        organization_id=org_id,
        customer_id=customer_id,
        source_id=request.source_id,
        cardholder_name=request.cardholder_name,
    )
    card_id = card.get("card_id")
    if not card_id:
        raise HTTPException(status_code=400, detail="Card save failed")

    # 3. Recurring vs one-off
    is_recurring = (mt["type"] == "unlimited" or mt["billing_period"] in (
        "monthly", "annual", "yearly", "weekly",
    ))

    if is_recurring:
        # Charge first period directly via CreatePayment with app_fee_money.
        # Square Subscriptions API does NOT support app_fee_money — using it
        # would forfeit the 1% platform take on every cycle. Instead AuraFlow
        # owns the recurrence: the renewal scheduler in
        # app.workers.tasks.recurring_membership_renewals runs daily and
        # re-charges the saved card via the same path, so 1% lands every cycle.
        payment = await billing_dispatcher.create_payment(
            organization_id=org_id,
            amount_cents=mt["price_cents"],
            source_id=card_id,
            description=f"{mt['name']} — first period",
            member_id=str(member["id"]),
            member_square_customer_id=customer_id,
        )
        period = (mt["billing_period"] or "monthly").lower()
        period_sql = {
            "weekly": "INTERVAL '7 days'",
            "monthly": "INTERVAL '1 month'",
            "annual": "INTERVAL '1 year'",
            "yearly": "INTERVAL '1 year'",
        }.get(period, "INTERVAL '1 month'")
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                f"""
                INSERT INTO member_memberships
                    (member_id, membership_type_id, status, starts_at, ends_at,
                     current_period_end, square_card_id, billing_provider, created_at)
                VALUES ($1, $2, 'active', NOW(), NOW() + {period_sql},
                        NOW() + {period_sql}, $3, 'square', NOW())
                RETURNING id
                """,
                str(member["id"]), str(mt["id"]), card_id,
            )
            await db.execute(
                """
                INSERT INTO transactions
                    (member_id, amount_cents, type, status, description,
                     square_payment_id, fee_cents, net_amount_cents, created_at)
                VALUES ($1, $2, 'subscription', 'completed', $3, $4, $5, $6, NOW())
                """,
                str(member["id"]), mt["price_cents"], mt["name"],
                payment["payment_id"], payment["fee_cents"],
                mt["price_cents"] - payment["fee_cents"],
            )
        return {
            "data": {
                "membership_id": str(row["id"]),
                "payment_id": payment["payment_id"],
                "kind": "recurring",
            }
        }

    # One-off charge (class pack, intro offer, single class)
    payment = await billing_dispatcher.create_payment(
        organization_id=org_id,
        amount_cents=mt["price_cents"],
        source_id=card_id,  # charge the saved card
        description=mt["name"],
        member_id=str(member["id"]),
        member_square_customer_id=customer_id,
    )

    # Compute ends_at from duration_days if set
    ends_at_sql = "NULL"
    if mt["duration_days"]:
        ends_at_sql = f"NOW() + INTERVAL '{int(mt['duration_days'])} days'"
    async with get_tenant_db() as db:
        membership_row = await db.fetchrow(
            f"""
            INSERT INTO member_memberships
                (member_id, membership_type_id, status, starts_at, ends_at,
                 classes_remaining, billing_provider, created_at)
            VALUES ($1, $2, 'active', NOW(), {ends_at_sql}, $3, 'square', NOW())
            RETURNING id
            """,
            str(member["id"]), str(mt["id"]), mt["class_count"],
        )
        # Record the transaction
        await db.execute(
            """
            INSERT INTO transactions
                (member_id, amount_cents, type, status, description,
                 square_payment_id, fee_cents, net_amount_cents, created_at)
            VALUES ($1, $2, 'membership_purchase', 'completed', $3, $4, $5, $6, NOW())
            """,
            str(member["id"]), mt["price_cents"], mt["name"],
            payment["payment_id"], payment["fee_cents"],
            mt["price_cents"] - payment["fee_cents"],
        )
    return {
        "data": {
            "membership_id": str(membership_row["id"]),
            "payment_id": payment["payment_id"],
            "kind": "one_off",
        }
    }


@router.get("/square-config")
async def get_square_config(
    rbac: dict = Depends(require_permission("memberships.view_own")),
):
    """Public-ish Square Web Payments SDK config for THIS studio.

    The portal mounts the SDK with the platform's OAuth application_id
    plus the STUDIO's location_id (so the resulting nonce is bound to
    the studio's Square account, not KinovaAI's). Returns null
    location_id when the studio has not connected Square — UI treats
    that as 'migration unavailable'.
    """
    from app.core.config import settings as _settings
    org_id = get_organization_id()
    async with get_global_db() as db:
        row = await db.fetchrow(
            "SELECT square_location_id FROM af_global.organizations WHERE id = $1",
            org_id,
        )
    return {
        "data": {
            "application_id": _settings.SQUARE_OAUTH_APPLICATION_ID,
            "location_id": (row and row["square_location_id"]) or None,
            "environment": _settings.SQUARE_ENVIRONMENT,
        }
    }


class PortalSwitchToSquareRequest(BaseModel):
    membership_id: str
    source_id: str   # Web Payments SDK nonce (cnon:...)
    cardholder_name: Optional[str] = None


@router.post("/memberships/switch-to-square")
async def switch_membership_to_square(
    request: PortalSwitchToSquareRequest,
    rbac: dict = Depends(require_permission("memberships.purchase")),
):
    """Bridge a member's Stripe-billed membership onto the studio's
    Square account with no break in coverage.

    Used during the Stripe → Square org migration: the studio's
    billing_provider may still be 'stripe' (e.g. Your Studio), but
    individual members can pre-migrate by tokenizing a card with
    Square Web Payments SDK and calling this endpoint.

    Cutover sequence:
      1. Look up the Stripe sub's current_period_end via Stripe.
      2. Save the new card on the studio's Square account.
      3. Create a Square Subscription scheduled to start the day AFTER
         Stripe's period_end → zero overlap, zero gap.
      4. Set Stripe sub to cancel_at_period_end=True so it auto-ends
         exactly when Square begins.
      5. Stamp the row with square_subscription_id; leave
         stripe_subscription_id + billing_provider='stripe' in place
         until the natural period-end. The Stripe
         customer.subscription.deleted webhook then flips
         billing_provider='square' and clears stripe_subscription_id
         (see webhook_handler._handle_subscription_deleted).

    The member never sees a gap. The member sees one charge on
    Stripe (their last period) then one charge on Square (their first
    new period).
    """
    from app.services.payments.square_service import square_service
    from app.services.payments.square_oauth_service import square_oauth_service
    from datetime import datetime, timedelta, timezone

    member = await svc.get_my_profile(rbac["user_id"])
    if not member:
        raise HTTPException(status_code=404, detail="Member profile not found")

    org_id = get_organization_id()

    # 1. Membership row — verify ownership + transition eligibility
    async with get_tenant_db() as db:
        mm = await db.fetchrow(
            """
            SELECT mm.id, mm.member_id, mm.stripe_subscription_id,
                   mm.square_subscription_id, mm.status, mm.membership_type_id,
                   mt.name AS plan_name, mt.price_cents, mt.billing_period,
                   mt.type AS plan_type
            FROM member_memberships mm
            JOIN membership_types mt ON mt.id = mm.membership_type_id
            WHERE mm.id = $1
            """,
            request.membership_id,
        )
    if not mm:
        raise HTTPException(status_code=404, detail="Membership not found")
    if str(mm["member_id"]) != str(member["id"]):
        raise HTTPException(status_code=403, detail="Not your membership")
    if not mm["stripe_subscription_id"]:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "This membership has no Stripe subscription to migrate from",
                "code": "NOT_STRIPE_BACKED",
            },
        )
    if mm["square_subscription_id"]:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "This membership is already migrated to Square",
                "code": "ALREADY_MIGRATED",
            },
        )
    if mm["status"] != "active":
        # past_due explicitly rejected — a member with an overdue Stripe
        # invoice would otherwise migrate to Square and escape the debt.
        # Staff must resolve the past-due balance on Stripe first.
        raise HTTPException(
            status_code=400,
            detail={
                "error": (
                    f"Cannot migrate a {mm['status']} membership. "
                    "Please contact the studio — outstanding balance "
                    "must be resolved before switching providers."
                    if mm["status"] == "past_due"
                    else f"Cannot migrate a {mm['status']} membership"
                ),
                "code": "INVALID_STATUS_FOR_MIGRATION",
                "membership_status": mm["status"],
            },
        )

    # 2. Square credentials — direct read, bypasses the dispatcher's
    # provider gate because this endpoint IS the bridge.
    access_token = await square_oauth_service.get_merchant_access_token(org_id)
    if not access_token:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "This studio is not connected to Square yet. "
                         "Owner must complete Square OAuth in Settings → Billing first.",
                "code": "SQUARE_NOT_CONNECTED",
            },
        )
    async with get_global_db() as db:
        org_row = await db.fetchrow(
            "SELECT square_location_id FROM af_global.organizations WHERE id = $1",
            org_id,
        )
    location_id = org_row and org_row["square_location_id"]
    if not location_id:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Studio's Square location not configured",
                "code": "SQUARE_LOCATION_MISSING",
            },
        )

    # 3. Stripe sub → period_end (honors direct-mode for Your Studio)
    stripe_svc = StripeService()
    try:
        stripe_sub = await stripe_svc.get_subscription_details(
            subscription_id=mm["stripe_subscription_id"],
            org_id=org_id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "error": f"Could not read Stripe subscription: {exc}",
                "code": "STRIPE_LOOKUP_FAILED",
            },
        )
    period_end_ts = stripe_sub.get("current_period_end")
    if not period_end_ts:
        raise HTTPException(
            status_code=502,
            detail={"error": "Stripe sub has no period_end", "code": "STRIPE_NO_PERIOD_END"},
        )
    period_end_dt = datetime.fromtimestamp(period_end_ts, tz=timezone.utc)
    square_start_date = (period_end_dt + timedelta(days=1)).strftime("%Y-%m-%d")

    # 4. Square Customer (idempotent on email)
    from app.services.members.phi_helpers import decrypt_phone
    async with get_tenant_db() as db:
        member_row = await db.fetchrow(
            "SELECT square_customer_id, first_name, last_name, email, phone_enc FROM members WHERE id = $1",
            str(member["id"]),
        )
    customer_id = member_row["square_customer_id"]
    if not customer_id:
        cust = await square_service.create_customer(
            merchant_access_token=access_token,
            email=member_row["email"],
            first_name=member_row["first_name"],
            last_name=member_row["last_name"],
            phone=decrypt_phone(member_row),
            member_id=str(member["id"]),
        )
        customer_id = cust["customer_id"]
        async with get_tenant_db() as db:
            await db.execute(
                "UPDATE members SET square_customer_id = $2 WHERE id = $1",
                str(member["id"]), customer_id,
            )

    # 5. Save card on file
    card = await square_service.create_card(
        merchant_access_token=access_token,
        customer_id=customer_id,
        source_id=request.source_id,
        cardholder_name=request.cardholder_name,
    )
    card_id = card.get("card_id")
    if not card_id:
        raise HTTPException(status_code=400, detail="Card save failed")

    # 6. Resolve (or create + cache) the Square subscription plan for
    # this membership_type — mirrors billing_dispatcher.create_subscription
    async with get_tenant_db() as db:
        mt_row = await db.fetchrow(
            "SELECT square_plan_variation_id FROM membership_types WHERE id = $1",
            str(mm["membership_type_id"]),
        )
    plan_variation_id = mt_row and mt_row["square_plan_variation_id"]
    if not plan_variation_id:
        cadence = billing_dispatcher.resolve_square_cadence(mm["billing_period"])
        plan = await square_service.create_subscription_plan(
            merchant_access_token=access_token,
            name=mm["plan_name"],
            price_cents=mm["price_cents"],
            cadence=cadence,
        )
        plan_variation_id = plan["plan_variation_id"]
        async with get_tenant_db() as db:
            await db.execute(
                """
                UPDATE membership_types
                SET square_plan_id = $1, square_plan_variation_id = $2
                WHERE id = $3
                """,
                plan["plan_id"], plan_variation_id, str(mm["membership_type_id"]),
            )

    # 7. Schedule the Square subscription (starts the day AFTER Stripe ends)
    square_sub = await square_service.create_subscription(
        merchant_access_token=access_token,
        merchant_location_id=location_id,
        plan_variation_id=plan_variation_id,
        customer_id=customer_id,
        card_id=card_id,
        start_date=square_start_date,
        reference_id=str(member["id"]),
    )
    square_sub_id = square_sub["subscription_id"]

    # 8. Tell Stripe to stop after this period (now we know the Square
    # successor exists; if step 7 had failed we'd never have called this).
    #
    # If Stripe cancel fails, AUTO-ROLLBACK the Square sub we just
    # scheduled — leaving the member double-billed is the worst
    # outcome. If rollback also fails, fail loud with both IDs so
    # staff can manually resolve.
    try:
        await stripe_svc.cancel_subscription(
            subscription_id=mm["stripe_subscription_id"],
            at_period_end=True,
            org_id=org_id,
        )
    except Exception as exc:
        logger.error(
            "Stripe cancel failed after Square sub created — rolling back Square sub",
            membership_id=request.membership_id,
            square_sub_id=square_sub_id,
            error=str(exc),
        )
        rollback_ok = False
        try:
            await square_service.cancel_subscription(
                merchant_access_token=access_token,
                subscription_id=square_sub_id,
            )
            rollback_ok = True
            logger.info(
                "Square sub rollback succeeded",
                membership_id=request.membership_id,
                square_sub_id=square_sub_id,
            )
        except Exception as rb_exc:
            logger.error(
                "Square sub rollback FAILED — manual intervention required",
                membership_id=request.membership_id,
                square_sub_id=square_sub_id,
                rollback_error=str(rb_exc),
            )

        if rollback_ok:
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "Could not update your Stripe subscription. "
                             "The Square switch was rolled back — you are "
                             "still on your existing billing. Please try again.",
                    "code": "STRIPE_CANCEL_FAILED_SQUARE_ROLLED_BACK",
                },
            )
        # Rollback failed → double-billing risk; staff must act
        raise HTTPException(
            status_code=502,
            detail={
                "error": "Switch hit a snag — please contact the studio. "
                         "Reference the IDs below; nothing is lost.",
                "code": "STRIPE_CANCEL_FAILED_SQUARE_ROLLBACK_FAILED",
                "square_subscription_id": square_sub_id,
                "stripe_subscription_id": mm["stripe_subscription_id"],
            },
        )

    # 9. Persist the cutover state on the local row. Keep
    # stripe_subscription_id + billing_provider='stripe' so the row
    # continues to behave correctly for the remaining Stripe period.
    # The Stripe subscription.deleted webhook handler flips the
    # provider when the period actually ends.
    async with get_tenant_db() as db:
        await db.execute(
            """
            UPDATE member_memberships
            SET square_subscription_id = $1, updated_at = NOW()
            WHERE id = $2
            """,
            square_sub_id, request.membership_id,
        )

    logger.info(
        "Member migrated Stripe → Square",
        membership_id=request.membership_id,
        stripe_sub_id=mm["stripe_subscription_id"],
        square_sub_id=square_sub_id,
        stripe_ends=period_end_dt.isoformat(),
        square_starts=square_start_date,
    )

    return {
        "data": {
            "membership_id": request.membership_id,
            "square_subscription_id": square_sub_id,
            "stripe_subscription_id": mm["stripe_subscription_id"],
            "stripe_last_charge_date": period_end_dt.date().isoformat(),
            "square_first_charge_date": square_start_date,
            "message": (
                f"Your card is saved with Square. Your last Stripe "
                f"charge will be on {period_end_dt.date().isoformat()}; "
                f"your next charge will be on Square on {square_start_date}. "
                f"No interruption in your membership."
            ),
        }
    }


@router.get("/memberships/available", response_model=list[PortalMembershipTypeResponse])
async def get_available_memberships(
    rbac: dict = Depends(require_permission("memberships.view_public")),
):
    """List active membership types with pricing for the portal.

    Passes user_id so the service can hide:
      - intro offers this member has already used
      - new-students-only types when this member has prior history
    """
    types = await svc.get_available_membership_types(user_id=rbac["user_id"])
    return [PortalMembershipTypeResponse(**t) for t in types]


# ── Subscription Lifecycle (3B) ──────────────────────────────────────────

async def _get_membership_with_subscription(user_id: str, membership_id: str) -> tuple[dict, str, str | None]:
    """Verify the membership belongs to the authenticated member and return it
    along with the stripe_subscription_id and stripe_account_id.
    Raises HTTPException if not found or not authorized.
    """
    member = await svc.get_my_profile(user_id)
    if not member:
        raise HTTPException(status_code=404, detail="Member profile not found")

    member_id = str(member["id"])
    org_id = get_organization_id()

    async with get_tenant_db() as db:
        mm = await db.fetchrow(
            """
            SELECT mm.id, mm.status, mm.stripe_subscription_id, mm.member_id
            FROM member_memberships mm
            WHERE mm.id = $1
            """,
            membership_id,
        )
    if not mm:
        raise HTTPException(status_code=404, detail="Membership not found")
    if str(mm["member_id"]) != member_id:
        raise HTTPException(status_code=403, detail="Not your membership")
    if not mm.get("stripe_subscription_id"):
        raise HTTPException(status_code=400, detail="No active Stripe subscription for this membership")

    # Look up org's Connect account — server-derived from JWT context only.
    # See app/services/payments/connect_account.py for the chokepoint rule.
    from app.services.payments.connect_account import resolve_stripe_account_for_org
    stripe_account_id = await resolve_stripe_account_for_org(org_id)

    return dict(mm), mm["stripe_subscription_id"], stripe_account_id


@router.post("/memberships/{membership_id}/pause")
async def pause_membership(
    membership_id: str,
    rbac: dict = Depends(require_permission("memberships.pause_own")),
):
    """Pause the member's subscription."""
    mm, sub_id, stripe_acct = await _get_membership_with_subscription(rbac["user_id"], membership_id)
    if mm["status"] != "active":
        raise HTTPException(status_code=400, detail="Only active memberships can be paused")

    try:
        result = await stripe_svc.pause_subscription(sub_id, stripe_acct)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Update local status
    async with get_tenant_db() as db:
        await db.execute(
            "UPDATE member_memberships SET status = 'paused', updated_at = NOW() WHERE id = $1",
            membership_id,
        )

    return {"data": result}


@router.post("/memberships/{membership_id}/resume")
async def resume_membership(
    membership_id: str,
    rbac: dict = Depends(require_permission("memberships.resume_own")),
):
    """Resume a paused subscription."""
    mm, sub_id, stripe_acct = await _get_membership_with_subscription(rbac["user_id"], membership_id)
    if mm["status"] != "paused":
        raise HTTPException(status_code=400, detail="Only paused memberships can be resumed")

    try:
        result = await stripe_svc.resume_subscription(sub_id, stripe_acct)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Update local status
    async with get_tenant_db() as db:
        await db.execute(
            "UPDATE member_memberships SET status = 'active', updated_at = NOW() WHERE id = $1",
            membership_id,
        )

    return {"data": result}


@router.post("/memberships/{membership_id}/cancel")
async def cancel_membership(
    membership_id: str,
    rbac: dict = Depends(require_permission("memberships.cancel_own")),
):
    """Cancel the member's subscription at the end of the current billing period."""
    mm, sub_id, stripe_acct = await _get_membership_with_subscription(rbac["user_id"], membership_id)
    if mm["status"] not in ("active", "paused"):
        raise HTTPException(status_code=400, detail="Membership cannot be cancelled in its current state")

    try:
        result = await stripe_svc.cancel_subscription(sub_id, at_period_end=True, stripe_account_id=stripe_acct)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Update local status
    async with get_tenant_db() as db:
        await db.execute(
            """
            UPDATE member_memberships
            SET status = 'cancelled', cancelled_at = NOW(), updated_at = NOW()
            WHERE id = $1
            """,
            membership_id,
        )

    return {"data": result}


# ── Payment Method Management (3C) ───────────────────────────────────────

class PortalPaymentMethodRequest(BaseModel):
    return_url: str


@router.post("/payment-methods/manage")
async def manage_payment_methods(
    request: PortalPaymentMethodRequest,
    rbac: dict = Depends(require_permission("payments.manage_own")),
):
    """Create a Stripe Customer Portal session for managing payment methods."""
    member = await svc.get_my_profile(rbac["user_id"])
    if not member:
        raise HTTPException(status_code=404, detail="Member profile not found")

    org_id = get_organization_id()
    try:
        result = await stripe_svc.create_customer_portal_session(
            org_id=org_id,
            member_id=str(member["id"]),
            return_url=request.return_url,
        )
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Payment History & Invoices (3D) ──────────────────────────────────────

@router.get("/payments", response_model=list[PortalTransactionResponse])
async def get_my_payments(
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    rbac: dict = Depends(require_permission("payments.view_own")),
):
    """Get the authenticated member's payment/transaction history."""
    member = await svc.get_my_profile(rbac["user_id"])
    if not member:
        raise HTTPException(status_code=404, detail="Member profile not found")

    member_id = str(member["id"])
    async with get_tenant_db() as db:
        rows = await db.fetch(
            """
            SELECT id, amount_cents, type, status, description,
                   stripe_invoice_id, created_at
            FROM transactions
            WHERE member_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            member_id, limit, offset,
        )
    return [
        PortalTransactionResponse(
            id=str(r["id"]),
            amount_cents=r["amount_cents"],
            type=r["type"],
            status=r["status"],
            description=r.get("description"),
            created_at=_fmt(r.get("created_at")),
        )
        for r in rows
    ]


@router.get("/invoices/{invoice_id}/pdf")
async def get_invoice_pdf(
    invoice_id: str,
    rbac: dict = Depends(require_permission("payments.view_own")),
):
    """Retrieve invoice PDF URL from Stripe."""
    member = await svc.get_my_profile(rbac["user_id"])
    if not member:
        raise HTTPException(status_code=404, detail="Member profile not found")

    # Verify the invoice belongs to this member by checking local transactions
    member_id = str(member["id"])
    async with get_tenant_db() as db:
        txn = await db.fetchrow(
            """
            SELECT id FROM transactions
            WHERE stripe_invoice_id = $1 AND member_id = $2
            """,
            invoice_id, member_id,
        )
    if not txn:
        raise HTTPException(status_code=404, detail="Invoice not found for this member")

    org_id = get_organization_id()
    async with get_global_db() as db:
        org_row = await db.fetchrow(
            "SELECT stripe_account_id FROM af_global.organizations WHERE id = $1",
            org_id,
        )
    stripe_account_id = org_row["stripe_account_id"] if org_row else None

    try:
        pdf_url = await stripe_svc.get_invoice_pdf_url(invoice_id, stripe_account_id)
        return {"data": {"invoice_id": invoice_id, "pdf_url": pdf_url}}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── AI Suggestions ────────────────────────────────────────────────────────────

class PortalSuggestionResponse(BaseModel):
    session_id: str
    title: str
    starts_at: str
    instructor_name: Optional[str] = None
    reason: str


@router.get("/suggestions", response_model=list[PortalSuggestionResponse])
async def get_suggestions(
    rbac: dict = Depends(require_permission("schedule.view_suggestions")),
):
    """Get AI-powered class suggestions based on the member's history."""
    suggestions = await svc.get_suggestions(rbac["user_id"])
    return [PortalSuggestionResponse(**s) for s in suggestions]


# ── Workshop / Course Helpers ─────────────────────────────────────────────────

def _course_response(c: dict) -> PortalCourseResponse:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    early_bird_deadline = c.get("early_bird_deadline")
    is_early_bird = bool(
        c.get("early_bird_price_cents")
        and early_bird_deadline
        and now < early_bird_deadline
    )
    capacity = c.get("capacity")
    enrolled = c.get("enrolled_count", 0)
    spots = max(0, capacity - enrolled) if capacity else None
    return PortalCourseResponse(
        id=str(c["id"]),
        title=c["title"],
        description=c.get("description"),
        type=c["type"],
        instructor_name=c.get("instructor_name"),
        price_cents=c.get("price_cents", 0),
        early_bird_price_cents=c.get("early_bird_price_cents"),
        early_bird_deadline=_fmt(early_bird_deadline),
        is_early_bird_active=is_early_bird,
        capacity=capacity,
        enrolled_count=enrolled,
        spots_remaining=spots,
        location=c.get("location"),
        is_virtual=c.get("is_virtual", False),
        image_url=c.get("image_url"),
        prerequisites=c.get("prerequisites"),
        starts_at=_fmt(c.get("starts_at")),
        ends_at=_fmt(c.get("ends_at")),
    )


def _course_session_response(s: dict) -> PortalCourseSessionResponse:
    return PortalCourseSessionResponse(
        id=str(s["id"]),
        title=s.get("title"),
        session_number=s.get("session_number", 0),
        starts_at=_fmt(s.get("starts_at")),
        ends_at=_fmt(s.get("ends_at")),
        location=s.get("location"),
        is_virtual=s.get("is_virtual", False),
    )


def _private_booking_response(b: dict) -> PortalPrivateBookingResponse:
    return PortalPrivateBookingResponse(
        id=str(b["id"]),
        starts_at=_fmt(b.get("starts_at")),
        ends_at=_fmt(b.get("ends_at")),
        status=b["status"],
        is_virtual=b.get("is_virtual", False),
        zoom_join_url=b.get("zoom_join_url"),
        service_name=b.get("service_name"),
        duration_minutes=b.get("duration_minutes"),
        instructor_name=b.get("instructor_name"),
        instructor_photo=b.get("instructor_photo"),
        price_cents=b.get("price_cents"),
        payment_status=b.get("payment_status"),
        payment_url=b.get("payment_url"),
        created_at=_fmt(b.get("created_at")),
    )


# ── Workshops & Courses ──────────────────────────────────────────────────────

@router.get("/my-enrollments", response_model=list[PortalEnrollmentResponse])
async def get_my_enrollments(
    rbac: dict = Depends(require_permission("workshops.view_own_enrollments")),
):
    """Get the authenticated member's workshop enrollments."""
    enrollments = await svc.get_my_enrollments(rbac["user_id"])
    return [
        PortalEnrollmentResponse(
            id=str(e["id"]),
            course_id=str(e["course_id"]),
            course_title=e.get("title"),
            course_type=e.get("type"),
            status=e["status"],
            paid_price_cents=e.get("paid_price_cents"),
            enrolled_at=_fmt(e.get("enrolled_at")),
            starts_at=_fmt(e.get("starts_at")),
            ends_at=_fmt(e.get("ends_at")),
            instructor_name=e.get("instructor_name"),
            is_virtual=e.get("is_virtual", False),
        )
        for e in enrollments
    ]


@router.get("/workshops", response_model=list[PortalCourseResponse])
async def browse_workshops(
    type: Optional[str] = Query(None, description="Filter: workshop, course, teacher_training, retreat"),
    rbac: dict = Depends(require_permission("workshops.view_public")),
):
    """Browse published workshops, courses, and trainings."""
    courses = await svc.get_published_courses(course_type=type)
    return [_course_response(c) for c in courses]


@router.get("/workshops/{course_id}", response_model=PortalCourseDetailResponse)
async def get_workshop_detail(
    course_id: str,
    rbac: dict = Depends(require_permission("workshops.view_public")),
):
    """Get workshop detail with session schedule."""
    course = await svc.get_course_detail(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Workshop not found")
    resp = _course_response(course)
    sessions = [_course_session_response(s) for s in course.get("sessions", [])]
    return PortalCourseDetailResponse(**resp.model_dump(), sessions=sessions)


async def _create_square_one_time_payment_link(
    org_id: str,
    item_name: str,
    price_cents: int,
    success_url: str,
    member_email: Optional[str],
    metadata: dict,
) -> dict:
    """Create a Square hosted payment link for a one-off purchase
    (workshop enrollment, private session, etc.). Returns
    {url, session_id} so callers can keep the same response shape
    they had with Stripe one-time checkout."""
    from app.services.payments.square_oauth_service import square_oauth_service
    from app.services.payments.square_service import _client as _sq_client, _idem

    access_token = await square_oauth_service.get_merchant_access_token(org_id)
    if not access_token:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Square not connected. Please ask the studio to finish Square setup.",
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

    pre_populated: dict = {}
    if member_email:
        pre_populated["buyer_email"] = member_email

    client = _sq_client(access_token)
    from app.services.payments.billing_dispatcher import _square_app_fee
    app_fee_cents = _square_app_fee(price_cents)
    try:
        resp = await client.checkout.payment_links.create(
            idempotency_key=_idem(),
            description=item_name[:255],
            order={
                "location_id": location_id,
                "line_items": [{
                    "name": item_name[:255],
                    "quantity": "1",
                    "base_price_money": {"amount": price_cents, "currency": "USD"},
                }],
                "metadata": metadata,
            },
            checkout_options={
                "redirect_url": success_url,
                "app_fee_money": {"amount": app_fee_cents, "currency": "USD"},
            },
            pre_populated_data=pre_populated or None,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Square payment link failed: {e}")
    if getattr(resp, "errors", None):
        raise HTTPException(status_code=502, detail=f"Square error: {resp.errors}")
    pl = resp.payment_link
    return {"url": pl.url, "session_id": pl.id}


@router.post("/workshops/{course_id}/enroll")
async def enroll_in_workshop(
    course_id: str,
    request: PortalCourseCheckoutRequest,
    rbac: dict = Depends(require_permission("workshops.enroll_self")),
):
    """Enroll in a workshop. Free → enroll directly. Paid → Square
    hosted payment link (Square-only; Stripe legacy path retired)."""
    from datetime import datetime, timezone

    course = await svc.get_course_detail(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Workshop not found")

    now = datetime.now(timezone.utc)
    price = course["price_cents"]
    deadline = course.get("early_bird_deadline")
    if course.get("early_bird_price_cents") and deadline and now < deadline:
        price = course["early_bird_price_cents"]

    if price == 0:
        try:
            enrollment = await svc.enroll_in_course(rbac["user_id"], course_id)
            return {"data": {"enrolled": True, "enrollment_id": str(enrollment["id"])}}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    member = await svc.get_my_profile(rbac["user_id"])
    if not member:
        raise HTTPException(status_code=404, detail="Member profile not found")

    from app.core.tenant_context import require_tenant_context
    org_id = get_organization_id()
    ctx = require_tenant_context()
    result = await _create_square_one_time_payment_link(
        org_id=org_id,
        item_name=course["title"],
        price_cents=price,
        success_url=request.success_url,
        member_email=member.get("email"),
        metadata={
            "auraflow_course_id": course_id,
            "auraflow_member_id": str(member["id"]),
            "auraflow_checkout_type": "course_enrollment",
            "auraflow_org_schema": ctx.schema_name,
        },
    )
    return {"data": result}


@router.delete("/workshops/enrollments/{enrollment_id}", status_code=204)
async def withdraw_from_workshop(
    enrollment_id: str,
    rbac: dict = Depends(require_permission("workshops.withdraw_self")),
):
    """Withdraw from a workshop enrollment."""
    try:
        result = await svc.withdraw_my_enrollment(rbac["user_id"], enrollment_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not result:
        raise HTTPException(status_code=404, detail="Enrollment not found")


# ── Private Lessons ──────────────────────────────────────────────────────────

@router.get("/private-lessons/instructors", response_model=list[PortalInstructorResponse])
async def browse_instructors(
    rbac: dict = Depends(require_permission("private_sessions.view_public")),
):
    """Browse instructors who offer private services."""
    instructors = await svc.get_instructors_with_services()
    return [
        PortalInstructorResponse(
            id=str(i["id"]),
            display_name=i["display_name"],
            bio=i.get("bio"),
            photo_url=i.get("photo_url"),
            specialties=i.get("specialties") or [],
            certifications=i.get("certifications") or [],
        )
        for i in instructors
    ]


@router.get(
    "/private-lessons/instructors/{instructor_id}/services",
    response_model=list[PortalPrivateServiceResponse],
)
async def get_instructor_services(
    instructor_id: str,
    rbac: dict = Depends(require_permission("private_sessions.view_public")),
):
    """Get services offered by a specific instructor."""
    services = await svc.get_instructor_services(instructor_id)
    return [
        PortalPrivateServiceResponse(
            id=str(s["id"]),
            name=s["name"],
            description=s.get("description"),
            duration_minutes=s["duration_minutes"],
            price_cents=s["price_cents"],
            is_virtual=s.get("is_virtual", False),
        )
        for s in services
    ]


@router.get("/private-lessons/slots", response_model=list[PortalTimeSlotResponse])
async def get_available_slots(
    instructor_id: str = Query(...),
    service_id: str = Query(...),
    date: str = Query(..., description="YYYY-MM-DD"),
    rbac: dict = Depends(require_permission("private_sessions.view_availability")),
):
    """Get available time slots for a private session on a given date."""
    slots = await svc.get_available_slots(instructor_id, service_id, date)
    return [PortalTimeSlotResponse(**s) for s in slots]


@router.post("/private-lessons/book")
async def book_private_session(
    request: PortalBookPrivateRequest,
    rbac: dict = Depends(require_permission("private_sessions.book_self")),
):
    """Book a private session. Free sessions book directly; paid go to Stripe checkout."""
    service = await svc.get_instructor_services(request.instructor_id)
    matched = next((s for s in service if str(s["id"]) == request.private_service_id), None)
    if not matched:
        raise HTTPException(status_code=404, detail="Service not found")

    price = matched["price_cents"]

    # Create the booking first (pending status) to reserve the slot
    try:
        booking = await svc.book_private_session(rbac["user_id"], {
            "instructor_id": request.instructor_id,
            "private_service_id": request.private_service_id,
            "starts_at": request.starts_at,
            "intake_notes": request.intake_notes,
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if price == 0:
        return {"data": {"booked": True, "booking_id": str(booking["id"])}}

    # Paid: create Square hosted payment link
    member = await svc.get_my_profile(rbac["user_id"])
    from app.core.tenant_context import require_tenant_context
    org_id = get_organization_id()
    ctx = require_tenant_context()
    result = await _create_square_one_time_payment_link(
        org_id=org_id,
        item_name=matched["name"],
        price_cents=price,
        success_url=request.success_url,
        member_email=member.get("email") if member else None,
        metadata={
            "auraflow_booking_id": str(booking["id"]),
            "auraflow_member_id": str(member["id"]) if member else "",
            "auraflow_checkout_type": "private_session",
            "auraflow_org_schema": ctx.schema_name,
        },
    )
    return {"data": result}


@router.get("/private-lessons/my-bookings", response_model=list[PortalPrivateBookingResponse])
async def get_my_private_bookings(
    upcoming_only: bool = Query(False),
    rbac: dict = Depends(require_permission("private_sessions.view_own_bookings")),
):
    """Get the authenticated member's private session bookings."""
    bookings = await svc.get_my_private_bookings(rbac["user_id"], upcoming_only)
    return [_private_booking_response(b) for b in bookings]


@router.delete("/private-lessons/bookings/{booking_id}", status_code=204)
async def cancel_my_private_booking(
    booking_id: str,
    rbac: dict = Depends(require_permission("private_sessions.cancel_own")),
):
    """Cancel a private session booking."""
    try:
        result = await svc.cancel_my_private_booking(rbac["user_id"], booking_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not result:
        raise HTTPException(status_code=404, detail="Booking not found")


# ── Reviews ─────────────────────────────────────────────────────────────────

class SubmitReviewRequest(BaseModel):
    class_session_id: str
    rating: int
    review_text: Optional[str] = None


@router.get("/reviewable-sessions")
async def get_reviewable_sessions(
    rbac: dict = Depends(require_permission("members.view_reviewable")),
):
    """Get sessions the member attended but hasn't reviewed yet."""
    sessions = await review_svc.get_reviewable_sessions(rbac["user_id"])
    return {"data": sessions}


@router.post("/reviews", status_code=201)
async def submit_review(
    body: SubmitReviewRequest,
    rbac: dict = Depends(require_permission("members.create_review")),
):
    """Submit a review for a class the member attended."""
    try:
        review = await review_svc.submit_review(
            rbac["user_id"], body.model_dump(),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": review}


@router.get("/my-reviews")
async def get_my_reviews(
    rbac: dict = Depends(require_permission("members.view_own_reviews")),
):
    """Get all reviews submitted by the authenticated member."""
    reviews = await review_svc.get_member_reviews(rbac["user_id"])
    return {"data": reviews}
