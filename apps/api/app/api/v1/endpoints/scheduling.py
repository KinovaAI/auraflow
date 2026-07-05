"""AuraFlow — Group Class Scheduling Endpoints

Class types, recurring series (RRULE), and individual session management.
"""
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.v1.dependencies.auth import get_current_user
from app.core.tenant_context import get_organization_id
from app.api.v1.dependencies.rbac import require_permission
from app.services.scheduling.scheduling_service import SchedulingService
from app.services.scheduling.booking_service import BookingService

router = APIRouter()

# Keep stub routers for webhook module compatibility
stripe_router = APIRouter()
mux_router = APIRouter()

svc = SchedulingService()
booking_svc = BookingService()


# ── Schemas ──────────────────────────────────────────────────────────────────

class ClassTypeCreate(BaseModel):
    studio_id: str
    name: str
    description: Optional[str] = None
    duration_minutes: int = 60
    color: str = "#4F46E5"
    capacity: int = 20
    level: str = "all_levels"
    tags: list[str] = []
    category: Optional[str] = None
    image_url: Optional[str] = None


class ClassTypeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = None
    color: Optional[str] = None
    capacity: Optional[int] = None
    level: Optional[str] = None
    tags: Optional[list[str]] = None
    category: Optional[str] = None
    image_url: Optional[str] = None


class ClassTypeResponse(BaseModel):
    id: str
    studio_id: str
    name: str
    description: Optional[str] = None
    duration_minutes: int
    color: str
    capacity: int
    level: str
    tags: list[str]
    category: Optional[str] = None
    image_url: Optional[str] = None
    is_active: bool


class SeriesCreate(BaseModel):
    studio_id: str
    class_type_id: str
    instructor_id: Optional[str] = None
    room_id: Optional[str] = None
    title: str
    rrule: str
    start_time: str  # HH:MM
    duration_minutes: int
    capacity: Optional[int] = None
    waitlist_capacity: int = 10
    effective_from: str  # YYYY-MM-DD
    effective_until: Optional[str] = None
    timezone: str = "America/Los_Angeles"
    expand_weeks: int = 4  # auto-expand this many weeks on creation
    is_virtual: bool = False
    auto_record: bool = False


class SeriesUpdate(BaseModel):
    instructor_id: Optional[str] = None
    room_id: Optional[str] = None
    title: Optional[str] = None
    rrule: Optional[str] = None
    start_time: Optional[str] = None
    duration_minutes: Optional[int] = None
    capacity: Optional[int] = None
    waitlist_capacity: Optional[int] = None
    effective_until: Optional[str] = None
    is_virtual: Optional[bool] = None
    auto_record: Optional[bool] = None


class SeriesResponse(BaseModel):
    id: str
    studio_id: str
    class_type_id: str
    instructor_id: Optional[str] = None
    room_id: Optional[str] = None
    title: str
    rrule: str
    start_time: str
    duration_minutes: int
    capacity: Optional[int] = None
    waitlist_capacity: int
    effective_from: str
    effective_until: Optional[str] = None
    timezone: str
    is_virtual: bool = False
    auto_record: bool = False
    is_active: bool


class SessionCreate(BaseModel):
    studio_id: str
    class_type_id: str
    instructor_id: Optional[str] = None
    room_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    starts_at: str  # ISO 8601
    ends_at: str
    timezone: str = "America/Los_Angeles"
    capacity: int = 20
    waitlist_capacity: int = 10
    notes: Optional[str] = None
    is_virtual: bool = False
    is_community: bool = False
    auto_record: bool = False
    # Defaults to in_studio. Setting virtual/hybrid implies is_virtual=True.
    modality: Optional[str] = None


class SessionUpdate(BaseModel):
    instructor_id: Optional[str] = None
    room_id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None
    capacity: Optional[int] = None
    notes: Optional[str] = None
    is_virtual: Optional[bool] = None
    is_community: Optional[bool] = None
    auto_record: Optional[bool] = None
    # in_studio | virtual | hybrid — drives eligibility gating per
    # member access_scope. is_virtual still governs Zoom-meeting
    # creation; setting modality='virtual' or 'hybrid' implies
    # is_virtual=True at the service layer.
    modality: Optional[str] = None


class SessionResponse(BaseModel):
    id: str
    studio_id: str
    class_type_id: str
    class_type_name: Optional[str] = None
    instructor_id: Optional[str] = None
    instructor_name: Optional[str] = None
    room_id: Optional[str] = None
    room_name: Optional[str] = None
    title: str
    description: Optional[str] = None
    starts_at: str
    ends_at: str
    timezone: str
    capacity: int
    booked_count: int = 0
    waitlist_count: int = 0
    status: str
    color: Optional[str] = None
    notes: Optional[str] = None
    series_id: Optional[str] = None
    is_virtual: bool = False
    is_community: bool = False
    modality: str = "in_studio"
    zoom_join_url: Optional[str] = None
    zoom_password: Optional[str] = None
    auto_record: bool = False
    recording_status: Optional[str] = None
    video_id: Optional[str] = None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _class_type_response(row) -> ClassTypeResponse:
    return ClassTypeResponse(
        id=str(row["id"]),
        studio_id=str(row["studio_id"]),
        name=row["name"],
        description=row.get("description"),
        duration_minutes=row["duration_minutes"],
        color=row["color"],
        capacity=row["capacity"],
        level=row.get("level", "all_levels"),
        tags=row.get("tags") or [],
        category=row.get("category"),
        image_url=row.get("image_url"),
        is_active=row["is_active"],
    )


def _series_response(row) -> SeriesResponse:
    return SeriesResponse(
        id=str(row["id"]),
        studio_id=str(row["studio_id"]),
        class_type_id=str(row["class_type_id"]),
        instructor_id=str(row["instructor_id"]) if row.get("instructor_id") else None,
        room_id=str(row["room_id"]) if row.get("room_id") else None,
        title=row["title"],
        rrule=row["rrule"],
        start_time=str(row["start_time"]),
        duration_minutes=row["duration_minutes"],
        capacity=row.get("capacity"),
        waitlist_capacity=row["waitlist_capacity"],
        effective_from=str(row["effective_from"]),
        effective_until=str(row["effective_until"]) if row.get("effective_until") else None,
        timezone=row["timezone"],
        is_virtual=row.get("is_virtual", False),
        auto_record=row.get("auto_record", False),
        is_active=row["is_active"],
    )


def _session_response(row) -> SessionResponse:
    starts = row["starts_at"]
    ends = row["ends_at"]
    return SessionResponse(
        id=str(row["id"]),
        studio_id=str(row["studio_id"]),
        class_type_id=str(row["class_type_id"]),
        class_type_name=row.get("class_type_name"),
        instructor_id=str(row["instructor_id"]) if row.get("instructor_id") else None,
        instructor_name=row.get("instructor_name"),
        room_id=str(row["room_id"]) if row.get("room_id") else None,
        room_name=row.get("room_name"),
        title=row["title"],
        description=row.get("description"),
        starts_at=starts.isoformat() if hasattr(starts, "isoformat") else str(starts),
        ends_at=ends.isoformat() if hasattr(ends, "isoformat") else str(ends),
        timezone=row["timezone"],
        capacity=row["capacity"],
        booked_count=row.get("booked_count", 0),
        waitlist_count=row.get("waitlist_count", 0),
        status=row["status"],
        color=row.get("color"),
        notes=row.get("notes"),
        series_id=str(row["series_id"]) if row.get("series_id") else None,
        is_virtual=row.get("is_virtual", False),
        is_community=row.get("is_community", False),
        modality=row.get("modality") or "in_studio",
        zoom_join_url=row.get("zoom_join_url"),
        zoom_password=row.get("zoom_password"),
        auto_record=row.get("auto_record", False),
        recording_status=row.get("recording_status"),
        video_id=str(row["video_id"]) if row.get("video_id") else None,
    )


# ── Class Type Endpoints ────────────────────────────────────────────────────

@router.post("/class-types", response_model=ClassTypeResponse, status_code=201)
async def create_class_type(
    request: ClassTypeCreate,
    rbac: dict = Depends(require_permission("schedule.create_class_type")),
):
    ct = await svc.create_class_type(request.studio_id, request.model_dump())
    return _class_type_response(ct)


@router.get("/class-types", response_model=list[ClassTypeResponse])
async def list_class_types(
    studio_id: str = Query(...),
    active_only: bool = Query(True),
    current_user: dict = Depends(get_current_user),
):
    types = await svc.list_class_types(studio_id, active_only)
    return [_class_type_response(ct) for ct in types]


@router.get("/class-types/{class_type_id}", response_model=ClassTypeResponse)
async def get_class_type(
    class_type_id: str,
    current_user: dict = Depends(get_current_user),
):
    ct = await svc.get_class_type(class_type_id)
    if not ct:
        raise HTTPException(status_code=404, detail="Class type not found")
    return _class_type_response(ct)


@router.put("/class-types/{class_type_id}", response_model=ClassTypeResponse)
async def update_class_type(
    class_type_id: str,
    request: ClassTypeUpdate,
    rbac: dict = Depends(require_permission("schedule.edit_class_type")),
):
    ct = await svc.update_class_type(class_type_id, request.model_dump(exclude_unset=True))
    if not ct:
        raise HTTPException(status_code=404, detail="Class type not found")
    return _class_type_response(ct)


@router.delete("/class-types/{class_type_id}", status_code=204)
async def deactivate_class_type(
    class_type_id: str,
    rbac: dict = Depends(require_permission("schedule.delete_class_type")),
):
    await svc.deactivate_class_type(class_type_id)


# ── Series Endpoints ────────────────────────────────────────────────────────

@router.post("/series", response_model=dict, status_code=201)
async def create_series(
    request: SeriesCreate,
    rbac: dict = Depends(require_permission("schedule.create_series")),
):
    org_id = get_organization_id()
    series = await svc.create_series(request.model_dump())
    # Auto-expand sessions
    until = date.fromisoformat(request.effective_from) + __import__("datetime").timedelta(
        weeks=request.expand_weeks
    )
    if request.effective_until:
        eu = date.fromisoformat(request.effective_until)
        until = min(until, eu)
    sessions = await svc.expand_series(str(series["id"]), until, org_id=org_id)
    return {
        "series": _series_response(series).model_dump(),
        "sessions_created": len(sessions),
    }


@router.get("/series", response_model=list[SeriesResponse])
async def list_series(
    studio_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    items = await svc.list_series(studio_id)
    return [_series_response(s) for s in items]


@router.get("/series/{series_id}", response_model=SeriesResponse)
async def get_series(
    series_id: str,
    current_user: dict = Depends(get_current_user),
):
    s = await svc.get_series(series_id)
    if not s:
        raise HTTPException(status_code=404, detail="Series not found")
    return _series_response(s)


@router.put("/series/{series_id}", response_model=SeriesResponse)
async def update_series(
    series_id: str,
    request: SeriesUpdate,
    rbac: dict = Depends(require_permission("schedule.edit_series")),
):
    s = await svc.update_series(series_id, request.model_dump(exclude_unset=True))
    if not s:
        raise HTTPException(status_code=404, detail="Series not found")
    return _series_response(s)


@router.delete("/series/{series_id}", status_code=204)
async def delete_series(
    series_id: str,
    delete_future_sessions: bool = Query(True),
    rbac: dict = Depends(require_permission("schedule.delete_series")),
):
    org_id = get_organization_id()
    await svc.delete_series(series_id, delete_future_sessions, org_id=org_id)


@router.post("/series/{series_id}/expand")
async def expand_series(
    series_id: str,
    weeks: int = Query(4, ge=1, le=52),
    rbac: dict = Depends(require_permission("schedule.manage_series")),
):
    org_id = get_organization_id()
    until = date.today() + __import__("datetime").timedelta(weeks=weeks)
    sessions = await svc.expand_series(series_id, until, org_id=org_id)
    return {"sessions_created": len(sessions), "sessions": sessions}


# ── Session Endpoints ────────────────────────────────────────────────────────

@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    studio_id: str = Query(...),
    start: str = Query(..., description="ISO date/datetime"),
    end: str = Query(..., description="ISO date/datetime"),
    instructor_id: Optional[str] = Query(None),
    room_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    from datetime import timedelta
    start_dt = datetime.fromisoformat(start) - timedelta(hours=12)
    end_dt = datetime.fromisoformat(end) + timedelta(hours=12)
    sessions = await svc.list_sessions(studio_id, start_dt, end_dt, instructor_id, room_id)
    return [_session_response(s) for s in sessions]


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    s = await svc.get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    return _session_response(s)


@router.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session(
    request: SessionCreate,
    rbac: dict = Depends(require_permission("schedule.create_session")),
):
    org_id = get_organization_id()
    s = await svc.create_session(request.model_dump(), org_id=org_id)
    full = await svc.get_session(str(s["id"]))
    return _session_response(full)


@router.put("/sessions/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: str,
    request: SessionUpdate,
    rbac: dict = Depends(require_permission("schedule.edit_session")),
):
    org_id = get_organization_id()
    s = await svc.update_session(session_id, request.model_dump(exclude_unset=True), org_id=org_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    full = await svc.get_session(session_id)
    return _session_response(full)


@router.delete("/sessions/{session_id}", status_code=204)
async def cancel_session(
    session_id: str,
    reason: Optional[str] = Query(None),
    rbac: dict = Depends(require_permission("schedule.delete_session")),
):
    org_id = get_organization_id()
    result = await svc.cancel_session(session_id, reason, org_id=org_id)
    if not result:
        raise HTTPException(status_code=404, detail="Session not found")


# ── Booking Schemas ──────────────────────────────────────────────────────────

class BookingCreate(BaseModel):
    member_id: str
    class_session_id: str
    source: str = "web"
    membership_id: Optional[str] = None
    notes: Optional[str] = None
    guest_name: Optional[str] = None
    guest_email: Optional[str] = None


class BookingResponse(BaseModel):
    id: str
    member_id: str
    class_session_id: str
    status: str
    source: str
    booked_at: Optional[str] = None
    cancelled_at: Optional[str] = None
    checked_in_at: Optional[str] = None
    cancellation_reason: Optional[str] = None
    late_cancel: bool = False
    waitlist_position: Optional[int] = None
    membership_id: Optional[str] = None
    notes: Optional[str] = None
    guest_name: Optional[str] = None
    guest_email: Optional[str] = None
    # Enriched fields (from joins)
    session_title: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    member_email: Optional[str] = None


def _booking_response(row) -> BookingResponse:
    def _ts(v):
        if v is None:
            return None
        return v.isoformat() if hasattr(v, "isoformat") else str(v)

    return BookingResponse(
        id=str(row["id"]),
        member_id=str(row["member_id"]),
        class_session_id=str(row["class_session_id"]),
        status=row["status"],
        source=row.get("source", "web"),
        booked_at=_ts(row.get("booked_at")),
        cancelled_at=_ts(row.get("cancelled_at")),
        checked_in_at=_ts(row.get("checked_in_at")),
        cancellation_reason=row.get("cancellation_reason"),
        late_cancel=row.get("late_cancel", False),
        waitlist_position=row.get("waitlist_position"),
        membership_id=str(row["membership_id"]) if row.get("membership_id") else None,
        notes=row.get("notes"),
        guest_name=row.get("guest_name"),
        guest_email=row.get("guest_email"),
        session_title=row.get("session_title"),
        first_name=row.get("first_name"),
        last_name=row.get("last_name"),
        member_email=row.get("member_email"),
    )


# ── Booking Endpoints ────────────────────────────────────────────────────────

@router.post("/bookings", response_model=BookingResponse, status_code=201)
async def book_class(
    request: BookingCreate,
    rbac: dict = Depends(require_permission("schedule.create_admin_booking")),
):
    try:
        booking = await booking_svc.book_class(request.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _booking_response(booking)


@router.get("/bookings/{booking_id}", response_model=BookingResponse)
async def get_booking(
    booking_id: str,
    current_user: dict = Depends(get_current_user),
):
    booking = await booking_svc.get_booking(booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return _booking_response(booking)


@router.delete("/bookings/{booking_id}", response_model=BookingResponse)
async def cancel_booking(
    booking_id: str,
    reason: Optional[str] = Query(None),
    late_cancel: bool = Query(False),
    rbac: dict = Depends(require_permission("schedule.cancel_booking")),
):
    result = await booking_svc.cancel_booking(booking_id, reason, late_cancel)
    if not result:
        raise HTTPException(status_code=404, detail="Booking not found")
    return _booking_response(result)


@router.post("/bookings/{booking_id}/check-in", response_model=BookingResponse)
async def check_in(
    booking_id: str,
    rbac: dict = Depends(require_permission("schedule.check_in")),
):
    booking = await booking_svc.check_in(booking_id)
    if not booking:
        raise HTTPException(status_code=400, detail="Cannot check in — booking not confirmed")
    return _booking_response(booking)


@router.post("/bookings/{booking_id}/no-show", response_model=BookingResponse)
async def mark_no_show(
    booking_id: str,
    rbac: dict = Depends(require_permission("schedule.no_show")),
):
    booking = await booking_svc.mark_no_show(booking_id)
    if not booking:
        raise HTTPException(status_code=400, detail="Cannot mark no-show — booking not confirmed")
    return _booking_response(booking)


@router.get("/sessions/{session_id}/roster", response_model=list[BookingResponse])
async def get_session_roster(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    roster = await booking_svc.get_session_roster(session_id)
    return [_booking_response(r) for r in roster]
