"""AuraFlow — Guest Instructor REST endpoints

CRUD for 1099-contractor instructors who teach workshops only. Lives
under `/api/v1/guest-instructors`. Owner/admin only — these records
hold tax ID and contact info.

Per Don's rule, these are NEVER mixed with the staff `instructors`
endpoints — different tables, different access surface, different
purpose.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.v1.dependencies.rbac import require_permission
from app.services.scheduling.guest_instructor_service import GuestInstructorService

router = APIRouter()
svc = GuestInstructorService()


class GuestInstructorCreate(BaseModel):
    studio_id: Optional[str] = None
    name: str
    bio: Optional[str] = None
    photo_url: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address_line1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    tax_id: Optional[str] = None  # SSN/EIN — encrypted at rest
    revenue_share_percent_to_guest: int = 60
    notes: Optional[str] = None


class GuestInstructorUpdate(BaseModel):
    name: Optional[str] = None
    bio: Optional[str] = None
    photo_url: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address_line1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    tax_id: Optional[str] = None
    revenue_share_percent_to_guest: Optional[int] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class GuestInstructorResponse(BaseModel):
    id: str
    studio_id: Optional[str] = None
    name: str
    bio: Optional[str] = None
    photo_url: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address_line1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    tax_id: Optional[str] = None
    revenue_share_percent_to_guest: int
    notes: Optional[str] = None
    is_active: bool


def _photo_url_from_row(row: dict) -> Optional[str]:
    """Prefer photo_url (hosted/external), else build a base64 data URL
    from photo_data + photo_mime (set when the guest uploaded a photo
    on the contract sign page). Returns None if neither."""
    url = row.get("photo_url")
    if url:
        return url
    blob = row.get("photo_data")
    if blob:
        import base64
        mime = row.get("photo_mime") or "image/jpeg"
        return f"data:{mime};base64,{base64.b64encode(blob).decode('ascii')}"
    return None


def _to_response(row: dict) -> GuestInstructorResponse:
    return GuestInstructorResponse(
        id=str(row["id"]),
        studio_id=str(row["studio_id"]) if row.get("studio_id") else None,
        name=row["name"],
        bio=row.get("bio"),
        photo_url=_photo_url_from_row(row),
        email=row.get("email"),
        phone=row.get("phone"),
        address_line1=row.get("address_line1"),
        city=row.get("city"),
        state=row.get("state"),
        postal_code=row.get("postal_code"),
        tax_id=row.get("tax_id"),
        revenue_share_percent_to_guest=row["revenue_share_percent_to_guest"],
        notes=row.get("notes"),
        is_active=row["is_active"],
    )


@router.get("", response_model=list[GuestInstructorResponse])
async def list_guests(
    active_only: bool = True,
    studio_id: Optional[str] = None,
    rbac: dict = Depends(require_permission("instructors.view_guest")),
):
    rows = await svc.list_guests(studio_id=studio_id, active_only=active_only)
    return [_to_response(r) for r in rows]


@router.post("", response_model=GuestInstructorResponse, status_code=201)
async def create_guest(
    body: GuestInstructorCreate,
    rbac: dict = Depends(require_permission("instructors.edit_guest")),
):
    row = await svc.create_guest(body.model_dump(exclude_unset=True))
    return _to_response(row)


@router.get("/{guest_id}", response_model=GuestInstructorResponse)
async def get_guest(
    guest_id: str,
    rbac: dict = Depends(require_permission("instructors.view_guest")),
):
    row = await svc.get_guest(guest_id)
    if not row:
        raise HTTPException(status_code=404, detail="Guest instructor not found")
    return _to_response(row)


@router.patch("/{guest_id}", response_model=GuestInstructorResponse)
async def update_guest(
    guest_id: str,
    body: GuestInstructorUpdate,
    rbac: dict = Depends(require_permission("instructors.edit_guest")),
):
    row = await svc.update_guest(guest_id, body.model_dump(exclude_unset=True))
    if not row:
        raise HTTPException(status_code=404, detail="Guest instructor not found")
    return _to_response(row)


@router.delete("/{guest_id}", status_code=204)
async def archive_guest(
    guest_id: str,
    rbac: dict = Depends(require_permission("instructors.delete_guest")),
):
    """Soft-archive: flips is_active=false so they don't show in pickers,
    but the row stays so prior workshops keep their tax attribution."""
    archived = await svc.archive_guest(guest_id)
    if not archived:
        raise HTTPException(status_code=404, detail="Guest instructor not found")
