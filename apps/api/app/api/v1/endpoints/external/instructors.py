"""AuraFlow — External Instructors Endpoints

Read-only instructor listing for third-party integrations.
"""
from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.dependencies.api_key_auth import get_api_key_context, require_api_scope
from app.services.scheduling.instructor_service import InstructorService
from app.services.external.csv_export import export_csv

router = APIRouter()
_svc = InstructorService()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fmt(dt):
    if dt and hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt) if dt else None


def _instructor_dict(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "display_name": row.get("display_name"),
        "bio": row.get("bio"),
        "photo_url": row.get("photo_url"),
        "specialties": row.get("specialties") or [],
        "certifications": row.get("certifications") or [],
        "email": row.get("email"),
        "phone": row.get("phone"),
        "color": row.get("color"),
        "is_active": row.get("is_active", True),
    }


# ── CSV Export ───────────────────────────────────────────────────────────────

_INSTRUCTOR_CSV_COLS = [
    ("id", "ID"),
    ("display_name", "Name"),
    ("email", "Email"),
    ("phone", "Phone"),
    ("specialties", "Specialties"),
    ("certifications", "Certifications"),
    ("is_active", "Active"),
]


@router.get(
    "/instructors/export.csv",
    dependencies=[Depends(require_api_scope("instructors:read"))],
    summary="Export instructors as CSV",
)
async def export_instructors_csv(
    ctx: dict = Depends(get_api_key_context),
):
    rows = await _svc.list_instructors(active_only=False)
    return export_csv([_instructor_dict(r) for r in rows], _INSTRUCTOR_CSV_COLS, "instructors.csv")


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get(
    "/instructors",
    dependencies=[Depends(require_api_scope("instructors:read"))],
    summary="List instructors",
)
async def list_instructors(
    ctx: dict = Depends(get_api_key_context),
):
    rows = await _svc.list_instructors(active_only=True)
    return [_instructor_dict(r) for r in rows]


@router.get(
    "/instructors/{instructor_id}",
    dependencies=[Depends(require_api_scope("instructors:read"))],
    summary="Get instructor by ID",
)
async def get_instructor(
    instructor_id: str,
    ctx: dict = Depends(get_api_key_context),
):
    row = await _svc.get_instructor(instructor_id)
    if not row:
        raise HTTPException(status_code=404, detail="Instructor not found")
    return _instructor_dict(row)
