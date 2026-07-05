"""AuraFlow — Instructor Endpoints

Instructor profiles, availability, and schedule management.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.v1.dependencies.auth import get_current_user
from app.api.v1.dependencies.rbac import require_permission
from app.services.scheduling.instructor_service import InstructorService

router = APIRouter()

svc = InstructorService()


# ── Schemas ──────────────────────────────────────────────────────────────────

class InstructorCreate(BaseModel):
    user_id: Optional[str] = None
    display_name: str
    bio: Optional[str] = None
    photo_url: Optional[str] = None
    specialties: list[str] = []
    certifications: list[str] = []
    email: Optional[str] = None
    phone: Optional[str] = None
    pay_rate_cents: Optional[int] = None
    pay_type: str = "per_class"
    salary_cents: int = 0
    tax_classification: str = "1099"
    workshop_pay_percent: int = 60
    private_session_pay_percent: int = 70
    training_pay_percent: int = 50
    color: str = "#4F46E5"
    sort_order: int = 0


class InstructorUpdate(BaseModel):
    display_name: Optional[str] = None
    bio: Optional[str] = None
    photo_url: Optional[str] = None
    specialties: Optional[list[str]] = None
    certifications: Optional[list[str]] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    pay_rate_cents: Optional[int] = None
    pay_type: Optional[str] = None
    salary_cents: Optional[int] = None
    tax_classification: Optional[str] = None
    workshop_pay_percent: Optional[int] = None
    private_session_pay_percent: Optional[int] = None
    training_pay_percent: Optional[int] = None
    color: Optional[str] = None
    sort_order: Optional[int] = None


class InstructorResponse(BaseModel):
    id: str
    user_id: Optional[str] = None
    display_name: str
    bio: Optional[str] = None
    photo_url: Optional[str] = None
    specialties: list[str]
    certifications: list[str]
    email: Optional[str] = None
    phone: Optional[str] = None
    pay_rate_cents: Optional[int] = None
    pay_type: str
    salary_cents: int = 0
    tax_classification: str
    workshop_pay_percent: int
    private_session_pay_percent: int
    training_pay_percent: int
    color: str
    sort_order: int
    is_active: bool


class AvailabilitySlot(BaseModel):
    day_of_week: int  # 0=Monday, 6=Sunday
    start_time: str   # HH:MM
    end_time: str     # HH:MM
    is_recurring: bool = True
    specific_date: Optional[str] = None
    is_blocked: bool = False


class AvailabilityResponse(BaseModel):
    id: str
    instructor_id: str
    day_of_week: Optional[int] = None
    start_time: str
    end_time: str
    is_recurring: bool
    specific_date: Optional[str] = None
    is_blocked: bool


# ── Helpers ──────────────────────────────────────────────────────────────────

def _instructor_response(row) -> InstructorResponse:
    return InstructorResponse(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        display_name=row["display_name"],
        bio=row.get("bio"),
        photo_url=row.get("photo_url"),
        specialties=row.get("specialties") or [],
        certifications=row.get("certifications") or [],
        email=row.get("email"),
        phone=row.get("phone"),
        pay_rate_cents=row.get("pay_rate_cents"),
        pay_type=row.get("pay_type", "per_class"),
        salary_cents=row.get("salary_cents", 0),
        tax_classification=row.get("tax_classification", "1099"),
        workshop_pay_percent=row.get("workshop_pay_percent", 60),
        private_session_pay_percent=row.get("private_session_pay_percent", 70),
        training_pay_percent=row.get("training_pay_percent", 50),
        color=row.get("color", "#4F46E5"),
        sort_order=row.get("sort_order", 0),
        is_active=row["is_active"],
    )


def _availability_response(row) -> AvailabilityResponse:
    return AvailabilityResponse(
        id=str(row["id"]),
        instructor_id=str(row["instructor_id"]),
        day_of_week=row.get("day_of_week"),
        start_time=str(row["start_time"]),
        end_time=str(row["end_time"]),
        is_recurring=row["is_recurring"],
        specific_date=str(row["specific_date"]) if row.get("specific_date") else None,
        is_blocked=row["is_blocked"],
    )


# ── Instructor CRUD ─────────────────────────────────────────────────────────

@router.post("", response_model=InstructorResponse, status_code=201)
async def create_instructor(
    request: InstructorCreate,
    rbac: dict = Depends(require_permission("staff.invite")),
):
    instructor = await svc.create_instructor(
        request.model_dump(), org_slug=rbac.get("org_slug"),
    )
    return _instructor_response(instructor)


@router.get("", response_model=list[InstructorResponse])
async def list_instructors(
    active_only: bool = Query(True),
    current_user: dict = Depends(get_current_user),
):
    instructors = await svc.list_instructors(active_only)
    return [_instructor_response(i) for i in instructors]


@router.get("/{instructor_id}", response_model=InstructorResponse)
async def get_instructor(
    instructor_id: str,
    current_user: dict = Depends(get_current_user),
):
    instructor = await svc.get_instructor(instructor_id)
    if not instructor:
        raise HTTPException(status_code=404, detail="Instructor not found")
    return _instructor_response(instructor)


@router.put("/{instructor_id}", response_model=InstructorResponse)
async def update_instructor(
    instructor_id: str,
    request: InstructorUpdate,
    rbac: dict = Depends(require_permission("instructors.edit")),
):
    instructor = await svc.update_instructor(
        instructor_id, request.model_dump(exclude_unset=True)
    )
    if not instructor:
        raise HTTPException(status_code=404, detail="Instructor not found")
    return _instructor_response(instructor)


@router.delete("/{instructor_id}", status_code=204)
async def deactivate_instructor(
    instructor_id: str,
    rbac: dict = Depends(require_permission("instructors.delete")),
):
    await svc.deactivate_instructor(instructor_id)


# ── Availability ────────────────────────────────────────────────────────────

@router.get("/{instructor_id}/availability", response_model=list[AvailabilityResponse])
async def get_availability(
    instructor_id: str,
    current_user: dict = Depends(get_current_user),
):
    slots = await svc.get_availability(instructor_id)
    return [_availability_response(s) for s in slots]


@router.put("/{instructor_id}/availability", response_model=list[AvailabilityResponse])
async def set_availability(
    instructor_id: str,
    slots: list[AvailabilitySlot],
    rbac: dict = Depends(require_permission("instructors.manage_availability")),
):
    created = await svc.set_availability(
        instructor_id, [s.model_dump() for s in slots]
    )
    # Re-fetch to get full records
    all_slots = await svc.get_availability(instructor_id)
    return [_availability_response(s) for s in all_slots]


# ── Schedule ────────────────────────────────────────────────────────────────

@router.get("/{instructor_id}/schedule")
async def get_instructor_schedule(
    instructor_id: str,
    start: str = Query(..., description="ISO date"),
    end: str = Query(..., description="ISO date"),
    rbac: dict = Depends(require_permission("instructors.view_schedule")),
):
    sessions = await svc.get_instructor_schedule(instructor_id, start, end)
    return sessions
