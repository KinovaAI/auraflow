"""AuraFlow — External Courses Endpoints

API-key-authenticated courses, workshops, teacher trainings, and retreats.
Critical for MyYogi Academy integration.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.v1.dependencies.api_key_auth import get_api_key_context, require_api_scope
from app.services.scheduling.course_service import CourseService
from app.services.external.csv_export import export_csv

router = APIRouter()
_svc = CourseService()


# ── Schemas ──────────────────────────────────────────────────────────────────

class CourseSessionIn(BaseModel):
    starts_at: str  # ISO 8601
    ends_at: str
    location: Optional[str] = None
    is_virtual: bool = False
    title: Optional[str] = None


class CourseCreate(BaseModel):
    title: str
    description: Optional[str] = None
    type: str = "workshop"  # workshop, teacher_training, retreat, course
    instructor_id: Optional[str] = None
    price_cents: int = 0
    early_bird_price_cents: Optional[int] = None
    early_bird_deadline: Optional[str] = None
    capacity: Optional[int] = None
    min_enrollment: Optional[int] = None
    location: Optional[str] = None
    is_virtual: bool = False
    image_url: Optional[str] = None
    prerequisites: Optional[str] = None
    registration_opens: Optional[str] = None
    registration_closes: Optional[str] = None
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None
    studio_id: Optional[str] = None
    # Multi-session support: pass one entry per session. If omitted but
    # starts_at + ends_at are set, the service creates a single implicit
    # session at the course level.
    sessions: Optional[list[CourseSessionIn]] = None


class EnrollmentCreate(BaseModel):
    member_id: str


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fmt(dt):
    if dt and hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt) if dt else None


def _course_dict(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "title": row["title"],
        "description": row.get("description"),
        "type": row.get("type"),
        "instructor_id": str(row["instructor_id"]) if row.get("instructor_id") else None,
        "instructor_name": row.get("instructor_name"),
        "price_cents": row.get("price_cents"),
        "early_bird_price_cents": row.get("early_bird_price_cents"),
        "early_bird_deadline": _fmt(row.get("early_bird_deadline")),
        "capacity": row.get("capacity"),
        "min_enrollment": row.get("min_enrollment"),
        "location": row.get("location"),
        "is_virtual": row.get("is_virtual", False),
        "image_url": row.get("image_url"),
        "prerequisites": row.get("prerequisites"),
        "registration_opens": _fmt(row.get("registration_opens")),
        "registration_closes": _fmt(row.get("registration_closes")),
        "starts_at": _fmt(row.get("starts_at")),
        "ends_at": _fmt(row.get("ends_at")),
        "status": row.get("status"),
        "enrolled_count": row.get("enrolled_count", 0),
        "created_at": _fmt(row.get("created_at")),
    }


def _enrollment_dict(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "course_id": str(row["course_id"]),
        "member_id": str(row["member_id"]),
        "first_name": row.get("first_name"),
        "last_name": row.get("last_name"),
        "email": row.get("email"),
        "status": row.get("status"),
        "paid_price_cents": row.get("paid_price_cents"),
        "enrolled_at": _fmt(row.get("enrolled_at")),
        "withdrawn_at": _fmt(row.get("withdrawn_at")),
        "completed_at": _fmt(row.get("completed_at")),
    }


async def _fire_webhook(event: str, payload: dict) -> None:
    try:
        from app.services.webhooks.webhook_delivery_service import WebhookDeliveryService
        await WebhookDeliveryService().fire_event(event, payload)
    except Exception:
        pass


# ── CSV Export ───────────────────────────────────────────────────────────────

_COURSE_CSV_COLS = [
    ("id", "ID"),
    ("title", "Title"),
    ("type", "Type"),
    ("instructor_name", "Instructor"),
    ("price_cents", "Price (cents)"),
    ("capacity", "Capacity"),
    ("enrolled_count", "Enrolled"),
    ("starts_at", "Starts At"),
    ("ends_at", "Ends At"),
    ("status", "Status"),
]


@router.get(
    "/courses/export.csv",
    dependencies=[Depends(require_api_scope("courses:read"))],
    summary="Export courses as CSV",
)
async def export_courses_csv(
    ctx: dict = Depends(get_api_key_context),
    type_filter: Optional[str] = Query(None, alias="type"),
):
    rows = await _svc.list_courses(course_type=type_filter)
    return export_csv([_course_dict(r) for r in rows], _COURSE_CSV_COLS, "courses.csv")


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get(
    "/courses",
    dependencies=[Depends(require_api_scope("courses:read"))],
    summary="List courses",
)
async def list_courses(
    ctx: dict = Depends(get_api_key_context),
    type_filter: Optional[str] = Query(None, alias="type"),
):
    rows = await _svc.list_courses(course_type=type_filter)
    return [_course_dict(r) for r in rows]


@router.get(
    "/courses/{course_id}",
    dependencies=[Depends(require_api_scope("courses:read"))],
    summary="Get course detail with sessions and enrollment count",
)
async def get_course(
    course_id: str,
    ctx: dict = Depends(get_api_key_context),
):
    row = await _svc.get_course(course_id)
    if not row:
        raise HTTPException(status_code=404, detail="Course not found")
    result = _course_dict(row)
    # Include sessions
    sessions = await _svc.list_sessions(course_id)
    result["sessions"] = [
        {
            "id": str(s["id"]),
            "title": s.get("title"),
            "session_number": s.get("session_number"),
            "starts_at": _fmt(s.get("starts_at")),
            "ends_at": _fmt(s.get("ends_at")),
            "location": s.get("location"),
            "is_virtual": s.get("is_virtual", False),
        }
        for s in sessions
    ]
    return result


@router.post(
    "/courses",
    dependencies=[Depends(require_api_scope("courses:write"))],
    status_code=201,
    summary="Create a course",
)
async def create_course(
    body: CourseCreate,
    ctx: dict = Depends(get_api_key_context),
):
    payload = body.model_dump()
    sessions = payload.pop("sessions", None) or []
    # If sessions[] provided, derive course-level starts_at/ends_at from
    # the span of the series so list/list-by-time queries still work.
    if sessions:
        sorted_s = sorted(sessions, key=lambda s: s["starts_at"])
        payload["starts_at"] = payload.get("starts_at") or sorted_s[0]["starts_at"]
        payload["ends_at"]   = payload.get("ends_at")   or sorted_s[-1]["ends_at"]
    row = await _svc.create_course(payload)
    course_id = str(row["id"])
    for s in sessions:
        await _svc.add_session(course_id, s)
    result = _course_dict(row)
    if sessions:
        result["sessions"] = [
            {
                "starts_at": _fmt(s["starts_at"]),
                "ends_at":   _fmt(s["ends_at"]),
                "location":  s.get("location"),
                "is_virtual": s.get("is_virtual", False),
                "title":     s.get("title"),
            }
            for s in sessions
        ]
    await _fire_webhook("course.created", result)
    return result


@router.post(
    "/courses/{course_id}/enroll",
    dependencies=[Depends(require_api_scope("courses:write"))],
    status_code=201,
    summary="Enroll a member in a course",
)
async def enroll_member(
    course_id: str,
    body: EnrollmentCreate,
    ctx: dict = Depends(get_api_key_context),
):
    try:
        row = await _svc.enroll_member(course_id, body.member_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    result = _enrollment_dict(row)
    await _fire_webhook("course.enrollment.created", result)
    return result


@router.delete(
    "/courses/{course_id}/enrollments/{enrollment_id}",
    dependencies=[Depends(require_api_scope("courses:write"))],
    status_code=204,
    summary="Cancel an enrollment",
)
async def cancel_enrollment(
    course_id: str,
    enrollment_id: str,
    ctx: dict = Depends(get_api_key_context),
):
    row = await _svc.withdraw_member(enrollment_id)
    if not row:
        raise HTTPException(status_code=404, detail="Enrollment not found or already withdrawn")
    await _fire_webhook("course.enrollment.cancelled", _enrollment_dict(row))
