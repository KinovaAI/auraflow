"""AuraFlow — Workshop & Course Endpoints

Multi-session programs: workshops, courses, teacher trainings, retreats.
Enrollment, sessions, attendance tracking.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.v1.dependencies.auth import get_current_user
from app.api.v1.dependencies.rbac import require_permission
from app.services.scheduling.course_service import CourseService

router = APIRouter()

# Keep stub routers for webhook module compatibility
stripe_router = APIRouter()
mux_router = APIRouter()

svc = CourseService()


# ── Schemas ──────────────────────────────────────────────────────────────────

class CourseCreate(BaseModel):
    studio_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    type: str = "workshop"
    instructor_id: Optional[str] = None
    # Workshops may be taught by a 1099 guest instructor instead of a
    # staff instructor. Mutually exclusive with instructor_id at the
    # service layer; DB CHECK constraint forbids guest_instructor_id
    # on any non-workshop course type (CA labor law).
    guest_instructor_id: Optional[str] = None
    price_cents: int = 0
    early_bird_price_cents: Optional[int] = None
    early_bird_deadline: Optional[str] = None
    capacity: Optional[int] = None
    min_enrollment: Optional[int] = None
    location: Optional[str] = None
    is_virtual: bool = False
    image_url: Optional[str] = None
    flyer_data_url: Optional[str] = None  # data:image/...;base64,...
    prerequisites: Optional[str] = None
    registration_opens: Optional[str] = None
    registration_closes: Optional[str] = None
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None


class CourseUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None
    instructor_id: Optional[str] = None
    guest_instructor_id: Optional[str] = None
    price_cents: Optional[int] = None
    early_bird_price_cents: Optional[int] = None
    early_bird_deadline: Optional[str] = None
    capacity: Optional[int] = None
    min_enrollment: Optional[int] = None
    location: Optional[str] = None
    is_virtual: Optional[bool] = None
    image_url: Optional[str] = None
    flyer_data_url: Optional[str] = None  # data:image/...;base64,... (set to "" to clear)
    prerequisites: Optional[str] = None
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None


class SessionCreate(BaseModel):
    title: Optional[str] = None
    starts_at: str
    ends_at: str
    location: Optional[str] = None
    is_virtual: bool = False


class SessionUpdate(BaseModel):
    title: Optional[str] = None
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None
    location: Optional[str] = None
    is_virtual: Optional[bool] = None


class EnrollMember(BaseModel):
    member_id: str


class AttendanceRecord(BaseModel):
    member_id: str
    status: str = "attended"


# ── Course CRUD ──────────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def create_course(
    body: CourseCreate,
    user=Depends(get_current_user),
    _=Depends(require_permission("workshops.create")),
):
    data = body.model_dump(exclude_none=True)
    # Convert string datetimes
    for field in ("early_bird_deadline", "registration_opens", "registration_closes", "starts_at", "ends_at"):
        if field in data and isinstance(data[field], str):
            from datetime import datetime
            data[field] = datetime.fromisoformat(data[field])
    try:
        course = await svc.create_course(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": course}


@router.get("")
async def list_courses(
    status: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    user=Depends(get_current_user),
):
    courses = await svc.list_courses(status=status, course_type=type)
    return {"data": courses}


# ── Course lifecycle (must come before /{course_id}) ─────────────────────────

@router.get("/{course_id}")
async def get_course(
    course_id: str,
    user=Depends(get_current_user),
):
    course = await svc.get_course(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return {"data": course}


@router.put("/{course_id}")
async def update_course(
    course_id: str,
    body: CourseUpdate,
    user=Depends(get_current_user),
    _=Depends(require_permission("workshops.edit")),
):
    data = body.model_dump(exclude_none=True)
    for field in ("early_bird_deadline", "starts_at", "ends_at"):
        if field in data and isinstance(data[field], str):
            from datetime import datetime
            data[field] = datetime.fromisoformat(data[field])
    try:
        course = await svc.update_course(course_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return {"data": course}


@router.post("/{course_id}/publish")
async def publish_course(
    course_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("workshops.publish")),
):
    course = await svc.publish_course(course_id)
    if not course:
        raise HTTPException(status_code=400, detail="Course not found or not in draft status")
    return {"data": course}


@router.post("/{course_id}/cancel")
async def cancel_course(
    course_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("workshops.cancel")),
):
    course = await svc.cancel_course(course_id)
    if not course:
        raise HTTPException(status_code=400, detail="Course not found or cannot be cancelled")
    return {"data": course}


@router.post("/{course_id}/complete")
async def complete_course(
    course_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("workshops.complete")),
):
    course = await svc.complete_course(course_id)
    if not course:
        raise HTTPException(status_code=400, detail="Course not found or not in active status")
    return {"data": course}


@router.delete("/{course_id}")
async def delete_course(
    course_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("workshops.delete")),
):
    """Permanently delete a course and all associated data."""
    deleted = await svc.delete_course(course_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Course not found")
    return {"data": {"deleted": True}}


# ── Sessions ─────────────────────────────────────────────────────────────────

@router.post("/{course_id}/sessions", status_code=201)
async def add_session(
    course_id: str,
    body: SessionCreate,
    user=Depends(get_current_user),
    _=Depends(require_permission("workshops.manage_sessions")),
):
    data = body.model_dump(exclude_none=True)
    for field in ("starts_at", "ends_at"):
        if field in data and isinstance(data[field], str):
            from datetime import datetime
            data[field] = datetime.fromisoformat(data[field])
    session = await svc.add_session(course_id, data)
    return {"data": session}


@router.get("/sessions/upcoming")
async def list_upcoming_sessions(
    days: int = 30,
    user=Depends(get_current_user),
):
    """All upcoming course_sessions across published courses, with the
    course title joined in. Used by the schedule page calendar to render
    each workshop session as its own time block — previously the calendar
    consumed course-level starts_at/ends_at which span the entire series
    and rendered as 'all day every day' across multi-week workshops.
    """
    from app.db.session import get_tenant_db
    async with get_tenant_db() as db:
        rows = await db.fetch(
            """
            SELECT cs.id, cs.course_id, cs.title, cs.starts_at, cs.ends_at,
                   cs.location, cs.is_virtual,
                   c.title AS course_title, c.type AS course_type,
                   c.status AS course_status, c.instructor_id
            FROM course_sessions cs
            JOIN courses c ON c.id = cs.course_id
            WHERE c.status = 'published'
              AND cs.starts_at >= NOW()
              AND cs.starts_at < NOW() + ($1::int || ' days')::interval
            ORDER BY cs.starts_at
            """,
            days,
        )
        out = []
        for r in rows:
            d = dict(r)
            for k in ("id", "course_id", "instructor_id"):
                if d.get(k):
                    d[k] = str(d[k])
            for k in ("starts_at", "ends_at"):
                if d.get(k):
                    d[k] = d[k].isoformat()
            out.append(d)
    return {"data": out}


@router.get("/{course_id}/sessions")
async def list_sessions(
    course_id: str,
    user=Depends(get_current_user),
):
    sessions = await svc.list_sessions(course_id)
    return {"data": sessions}


@router.put("/sessions/{session_id}")
async def update_session(
    session_id: str,
    body: SessionUpdate,
    user=Depends(get_current_user),
    _=Depends(require_permission("workshops.manage_sessions")),
):
    data = body.model_dump(exclude_none=True)
    for field in ("starts_at", "ends_at"):
        if field in data and isinstance(data[field], str):
            from datetime import datetime
            data[field] = datetime.fromisoformat(data[field])
    session = await svc.update_session(session_id, data)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"data": session}


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("workshops.manage_sessions")),
):
    deleted = await svc.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"data": {"deleted": True}}


# ── Enrollment ───────────────────────────────────────────────────────────────

@router.post("/{course_id}/enroll", status_code=201)
async def enroll_member(
    course_id: str,
    body: EnrollMember,
    user=Depends(get_current_user),
    _=Depends(require_permission("workshops.enroll_member")),
):
    try:
        enrollment = await svc.enroll_member(course_id, body.member_id)
        return {"data": enrollment}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{course_id}/enrollments")
async def list_enrollments(
    course_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("workshops.view_enrollments")),
):
    enrollments = await svc.list_enrollments(course_id)
    return {"data": enrollments}


@router.post("/enrollments/{enrollment_id}/withdraw")
async def withdraw_enrollment(
    enrollment_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("workshops.withdraw_member")),
):
    enrollment = await svc.withdraw_member(enrollment_id)
    if not enrollment:
        raise HTTPException(status_code=400, detail="Enrollment not found or already withdrawn")
    return {"data": enrollment}


# ── Attendance ───────────────────────────────────────────────────────────────

@router.post("/sessions/{session_id}/attendance", status_code=201)
async def record_attendance(
    session_id: str,
    body: AttendanceRecord,
    user=Depends(get_current_user),
    _=Depends(require_permission("workshops.record_attendance")),
):
    record = await svc.record_attendance(session_id, body.member_id, body.status)
    return {"data": record}


@router.get("/sessions/{session_id}/attendance")
async def get_attendance(
    session_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("workshops.view_attendance")),
):
    attendance = await svc.get_session_attendance(session_id)
    return {"data": attendance}
