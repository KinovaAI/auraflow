"""AuraFlow — Studio & Room Endpoints

CRUD for studio locations and rooms within a tenant.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.v1.dependencies.auth import get_current_user
from app.api.v1.dependencies.rbac import require_permission
from app.core.logging import logger
from app.core.tenant_context import get_organization_id
from app.db.session import get_tenant_db, get_global_db

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────

class StudioCreate(BaseModel):
    name: str
    slug: str
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    timezone: str = "America/Los_Angeles"
    is_virtual: bool = False


class StudioUpdate(BaseModel):
    name: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    timezone: Optional[str] = None
    cancellation_policy_hours: Optional[int] = None
    late_cancel_fee_cents: Optional[int] = None
    booking_window_days: Optional[int] = None
    allow_guest_booking: Optional[bool] = None


class StudioResponse(BaseModel):
    id: str
    name: str
    slug: str
    address_line1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    timezone: str
    is_virtual: bool
    is_active: bool
    cancellation_policy_hours: Optional[int] = None
    late_cancel_fee_cents: Optional[int] = None
    booking_window_days: Optional[int] = None
    allow_guest_booking: Optional[bool] = None


class RoomCreate(BaseModel):
    name: str
    capacity: Optional[int] = None
    color: str = "#6366F1"
    sort_order: int = 0


class RoomUpdate(BaseModel):
    name: Optional[str] = None
    capacity: Optional[int] = None
    color: Optional[str] = None
    sort_order: Optional[int] = None


class RoomResponse(BaseModel):
    id: str
    studio_id: str
    name: str
    capacity: Optional[int] = None
    color: str
    sort_order: int
    is_active: bool


# ── Helpers ──────────────────────────────────────────────────────────────────

def _studio_response(row) -> StudioResponse:
    return StudioResponse(
        id=str(row["id"]),
        name=row["name"],
        slug=row["slug"],
        address_line1=row.get("address_line1"),
        city=row.get("city"),
        state=row.get("state"),
        postal_code=row.get("postal_code"),
        phone=row.get("phone"),
        email=row.get("email"),
        timezone=row["timezone"],
        is_virtual=row["is_virtual"],
        is_active=row["is_active"],
        cancellation_policy_hours=row.get("cancellation_policy_hours"),
        late_cancel_fee_cents=row.get("late_cancel_fee_cents"),
        booking_window_days=row.get("booking_window_days"),
        allow_guest_booking=row.get("allow_guest_booking"),
    )


def _room_response(row) -> RoomResponse:
    return RoomResponse(
        id=str(row["id"]),
        studio_id=str(row["studio_id"]),
        name=row["name"],
        capacity=row.get("capacity"),
        color=row["color"],
        sort_order=row["sort_order"],
        is_active=row["is_active"],
    )


# ── Studio Endpoints ────────────────────────────────────────────────────────

@router.get("", response_model=list[StudioResponse])
async def list_studios(current_user: dict = Depends(get_current_user)):
    async with get_tenant_db() as db:
        rows = await db.fetch(
            "SELECT * FROM studios WHERE is_active = TRUE ORDER BY name"
        )
    return [_studio_response(r) for r in rows]


@router.get("/me")
async def get_my_studios(current_user: dict = Depends(get_current_user)):
    """Return studios the current user has access to, with per-studio role."""
    user_id = current_user.get("sub")
    role = current_user.get("org_role", "")
    is_platform_admin = current_user.get("is_platform_admin", False)

    async with get_tenant_db() as db:
        if role == "owner" or is_platform_admin:
            rows = await db.fetch(
                "SELECT id, name, slug FROM studios WHERE is_active = TRUE ORDER BY name"
            )
            return {
                "data": [
                    {
                        "studio_id": str(r["id"]),
                        "studio_name": r["name"],
                        "studio_slug": r["slug"] or "",
                        "role": "owner",
                        "is_primary": i == 0,
                    }
                    for i, r in enumerate(rows)
                ]
            }
        else:
            rows = await db.fetch(
                """
                SELECT s.id, s.name, s.slug, sur.role, sur.is_primary
                FROM studio_user_roles sur
                JOIN studios s ON s.id = sur.studio_id AND s.is_active = TRUE
                WHERE sur.user_id = $1
                ORDER BY sur.is_primary DESC, s.name
                """,
                user_id,
            )
            return {
                "data": [
                    {
                        "studio_id": str(r["id"]),
                        "studio_name": r["name"],
                        "studio_slug": r["slug"] or "",
                        "role": r["role"],
                        "is_primary": r["is_primary"],
                    }
                    for r in rows
                ]
            }


@router.get("/{studio_id}", response_model=StudioResponse)
async def get_studio(studio_id: str, current_user: dict = Depends(get_current_user)):
    async with get_tenant_db() as db:
        row = await db.fetchrow("SELECT * FROM studios WHERE id = $1", studio_id)
    if not row:
        raise HTTPException(status_code=404, detail="Studio not found")
    return _studio_response(row)


@router.post("", response_model=StudioResponse, status_code=201)
async def create_studio(
    request: StudioCreate,
    rbac: dict = Depends(require_permission("studios.edit")),
):
    studio_id = str(uuid.uuid4())
    org_id = get_organization_id()

    # Feature flag gate: check if multi_location is enabled before creating a second studio
    async with get_tenant_db() as db:
        studio_count = await db.fetchval("SELECT count(*) FROM studios WHERE is_active = TRUE")
    if studio_count >= 1:
        async with get_global_db() as gdb:
            flag = await gdb.fetchval(
                """
                SELECT is_enabled FROM af_global.feature_flags
                WHERE organization_id = $1 AND flag_key = 'multi_location'
                """,
                org_id,
            )
        if not flag:
            raise HTTPException(
                status_code=403,
                detail="Multi-location is available on the Scale plan. Upgrade to add more studios.",
            )

    async with get_tenant_db() as db:
        await db.execute(
            """
            INSERT INTO studios
                (id, organization_id, name, slug, address_line1, address_line2,
                 city, state, postal_code, phone, email, timezone, is_virtual)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            """,
            studio_id, org_id, request.name, request.slug,
            request.address_line1, request.address_line2,
            request.city, request.state, request.postal_code,
            request.phone, request.email, request.timezone, request.is_virtual,
        )
        row = await db.fetchrow("SELECT * FROM studios WHERE id = $1", studio_id)

    logger.info("Studio created", studio_id=studio_id, name=request.name)
    return _studio_response(row)


@router.put("/{studio_id}", response_model=StudioResponse)
async def update_studio(
    studio_id: str,
    request: StudioUpdate,
    rbac: dict = Depends(require_permission("studios.edit")),
):
    _STUDIO_UPDATE_COLS = {
        "name", "address_line1", "address_line2", "city", "state",
        "postal_code", "phone", "email", "timezone", "cancellation_policy_hours",
    }
    updates = {k: v for k, v in request.model_dump().items() if v is not None and k in _STUDIO_UPDATE_COLS}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clauses = []
    params = []
    for i, (col, val) in enumerate(updates.items(), start=1):
        set_clauses.append(f"{col} = ${i}")
        params.append(val)
    params.append(studio_id)

    async with get_tenant_db() as db:
        result = await db.execute(
            f"UPDATE studios SET {', '.join(set_clauses)}, updated_at = NOW() WHERE id = ${len(params)}",
            *params,
        )
        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail="Studio not found")
        row = await db.fetchrow("SELECT * FROM studios WHERE id = $1", studio_id)

    return _studio_response(row)


@router.delete("/{studio_id}", status_code=204)
async def deactivate_studio(
    studio_id: str,
    rbac: dict = Depends(require_permission("studios.delete")),
):
    async with get_tenant_db() as db:
        result = await db.execute(
            "UPDATE studios SET is_active = FALSE, updated_at = NOW() WHERE id = $1",
            studio_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Studio not found")


# ── Room Endpoints ──────────────────────────────────────────────────────────

@router.get("/{studio_id}/rooms", response_model=list[RoomResponse])
async def list_rooms(studio_id: str, current_user: dict = Depends(get_current_user)):
    async with get_tenant_db() as db:
        rows = await db.fetch(
            "SELECT * FROM rooms WHERE studio_id = $1 AND is_active = TRUE ORDER BY sort_order, name",
            studio_id,
        )
    return [_room_response(r) for r in rows]


@router.post("/{studio_id}/rooms", response_model=RoomResponse, status_code=201)
async def create_room(
    studio_id: str,
    request: RoomCreate,
    rbac: dict = Depends(require_permission("studios.create_room")),
):
    from app.services.scheduling.scheduling_service import SchedulingService

    svc = SchedulingService()
    room = await svc.create_room(studio_id, request.model_dump())
    return _room_response(room)


@router.put("/{studio_id}/rooms/{room_id}", response_model=RoomResponse)
async def update_room(
    studio_id: str,
    room_id: str,
    request: RoomUpdate,
    rbac: dict = Depends(require_permission("studios.edit_room")),
):
    from app.services.scheduling.scheduling_service import SchedulingService

    svc = SchedulingService()
    room = await svc.update_room(room_id, request.model_dump(exclude_unset=True))
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return _room_response(room)


@router.delete("/{studio_id}/rooms/{room_id}", status_code=204)
async def delete_room(
    studio_id: str,
    room_id: str,
    rbac: dict = Depends(require_permission("studios.delete_room")),
):
    from app.services.scheduling.scheduling_service import SchedulingService

    svc = SchedulingService()
    await svc.delete_room(room_id)
