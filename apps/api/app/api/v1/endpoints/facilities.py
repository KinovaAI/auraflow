"""AuraFlow — Facility Management Endpoints

Enhanced rooms, equipment tracking, maintenance requests,
and recurring cleaning/inspection schedules.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.v1.dependencies.auth import get_current_user
from app.api.v1.dependencies.rbac import require_permission
from app.services.facilities.facility_service import FacilityService

router = APIRouter()
svc = FacilityService()


# ── Schemas ──────────────────────────────────────────────────────────────

class RoomExtendedUpdate(BaseModel):
    description: Optional[str] = None
    room_type: Optional[str] = None
    amenities: Optional[list[str]] = None
    photo_url: Optional[str] = None
    hourly_rate_cents: Optional[int] = None
    max_classes_per_day: Optional[int] = None
    floor_area_sqft: Optional[int] = None
    setup_instructions: Optional[str] = None
    is_bookable: Optional[bool] = None


class EquipmentCreate(BaseModel):
    studio_id: str
    room_id: Optional[str] = None
    name: str
    category: str = "props"
    description: Optional[str] = None
    quantity: int = 1
    purchase_date: Optional[str] = None
    purchase_cost_cents: Optional[int] = None
    condition: str = "good"
    warranty_expiry: Optional[str] = None
    serial_number: Optional[str] = None
    photo_url: Optional[str] = None
    notes: Optional[str] = None


class EquipmentUpdate(BaseModel):
    room_id: Optional[str] = None
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[int] = None
    condition: Optional[str] = None
    warranty_expiry: Optional[str] = None
    serial_number: Optional[str] = None
    photo_url: Optional[str] = None
    notes: Optional[str] = None


class MaintenanceCreate(BaseModel):
    studio_id: str
    room_id: Optional[str] = None
    equipment_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    priority: str = "medium"
    category: str = "repair"
    assigned_to: Optional[str] = None
    estimated_cost_cents: Optional[int] = None
    scheduled_date: Optional[str] = None


class MaintenanceUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    category: Optional[str] = None
    assigned_to: Optional[str] = None
    estimated_cost_cents: Optional[int] = None
    actual_cost_cents: Optional[int] = None
    scheduled_date: Optional[str] = None
    completion_notes: Optional[str] = None


class ScheduleCreate(BaseModel):
    studio_id: str
    room_id: Optional[str] = None
    equipment_id: Optional[str] = None
    schedule_type: str = "cleaning"
    title: str
    description: Optional[str] = None
    rrule: Optional[str] = None
    assigned_to: Optional[str] = None
    next_due_at: Optional[str] = None


class ScheduleUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    rrule: Optional[str] = None
    assigned_to: Optional[str] = None
    next_due_at: Optional[str] = None
    is_active: Optional[bool] = None


class ScheduleCompleteRequest(BaseModel):
    notes: Optional[str] = None
    photos: Optional[list[str]] = None


# ── Enhanced Rooms ───────────────────────────────────────────────────────

@router.get("/rooms/studio/{studio_id}")
async def list_rooms_with_details(
    studio_id: str,
    user=Depends(get_current_user),
):
    """List rooms with equipment count and today's session count."""
    rooms = await svc.list_rooms_with_details(studio_id)
    return {"data": rooms}


@router.get("/rooms/{room_id}/detail")
async def get_room_detail(
    room_id: str,
    user=Depends(get_current_user),
):
    """Get a single room with enriched details."""
    room = await svc.get_room_detail(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return {"data": room}


@router.put("/rooms/{room_id}/extended")
async def update_room_extended(
    room_id: str,
    request: RoomExtendedUpdate,
    _=Depends(require_permission("facilities.edit_rooms")),
):
    """Update extended room fields (description, type, amenities, etc.)."""
    data = request.model_dump(exclude_unset=True)
    room = await svc.update_room_extended(room_id, data)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return {"data": room}


@router.get("/rooms/{room_id}/availability")
async def get_room_availability(
    room_id: str,
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    user=Depends(get_current_user),
):
    """Get class sessions scheduled in a room on a given date."""
    slots = await svc.get_room_availability(room_id, date)
    return {"data": slots}


# ── Equipment ────────────────────────────────────────────────────────────

@router.get("/equipment")
async def list_equipment(
    studio_id: str = Query(...),
    room_id: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    condition: Optional[str] = Query(None),
    _=Depends(require_permission("facilities.view_equipment")),
):
    """List equipment with optional filters."""
    items = await svc.list_equipment(studio_id, room_id, category, condition)
    return {"data": items}


@router.get("/equipment/{equipment_id}")
async def get_equipment(
    equipment_id: str,
    _=Depends(require_permission("facilities.view_equipment")),
):
    """Get a single equipment item."""
    item = await svc.get_equipment(equipment_id)
    if not item:
        raise HTTPException(status_code=404, detail="Equipment not found")
    return {"data": item}


@router.post("/equipment", status_code=201)
async def create_equipment(
    request: EquipmentCreate,
    _=Depends(require_permission("facilities.create_equipment")),
):
    """Create a new equipment item."""
    item = await svc.create_equipment(request.model_dump())
    return {"data": item}


@router.put("/equipment/{equipment_id}")
async def update_equipment(
    equipment_id: str,
    request: EquipmentUpdate,
    _=Depends(require_permission("facilities.edit_equipment")),
):
    """Update an equipment item."""
    item = await svc.update_equipment(
        equipment_id, request.model_dump(exclude_unset=True)
    )
    if not item:
        raise HTTPException(status_code=404, detail="Equipment not found")
    return {"data": item}


@router.delete("/equipment/{equipment_id}", status_code=204)
async def delete_equipment(
    equipment_id: str,
    _=Depends(require_permission("facilities.delete_equipment")),
):
    """Soft-delete an equipment item."""
    deleted = await svc.delete_equipment(equipment_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Equipment not found")


# ── Maintenance Requests ────────────────────────────────────────────────

@router.get("/maintenance")
async def list_maintenance(
    studio_id: str = Query(...),
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    _=Depends(require_permission("facilities.view_maintenance")),
):
    """List maintenance requests with optional filters."""
    items = await svc.list_maintenance_requests(studio_id, status, priority)
    return {"data": items}


@router.get("/maintenance/stats")
async def get_maintenance_stats(
    studio_id: str = Query(...),
    _=Depends(require_permission("facilities.view_maintenance")),
):
    """Get maintenance summary statistics."""
    stats = await svc.get_maintenance_stats(studio_id)
    return {"data": stats}


@router.get("/maintenance/{request_id}")
async def get_maintenance_request(
    request_id: str,
    _=Depends(require_permission("facilities.view_maintenance")),
):
    """Get a single maintenance request."""
    item = await svc.get_maintenance_request(request_id)
    if not item:
        raise HTTPException(status_code=404, detail="Maintenance request not found")
    return {"data": item}


@router.post("/maintenance", status_code=201)
async def create_maintenance(
    request: MaintenanceCreate,
    user=Depends(get_current_user),
    _=Depends(require_permission("facilities.create_maintenance")),
):
    """Create a new maintenance request."""
    data = request.model_dump()
    data["requested_by"] = user.get("user_id")
    item = await svc.create_maintenance_request(data)
    return {"data": item}


@router.put("/maintenance/{request_id}")
async def update_maintenance(
    request_id: str,
    request: MaintenanceUpdate,
    _=Depends(require_permission("facilities.manage_maintenance")),
):
    """Update a maintenance request."""
    item = await svc.update_maintenance_request(
        request_id, request.model_dump(exclude_unset=True)
    )
    if not item:
        raise HTTPException(status_code=404, detail="Maintenance request not found")
    return {"data": item}


# ── Facility Schedules ──────────────────────────────────────────────────

@router.get("/schedules")
async def list_schedules(
    studio_id: str = Query(...),
    type: Optional[str] = Query(None, alias="type"),
    overdue_only: bool = Query(False),
    _=Depends(require_permission("facilities.view_schedules")),
):
    """List facility schedules with optional filters."""
    items = await svc.list_schedules(studio_id, type, overdue_only)
    return {"data": items}


@router.get("/schedules/overdue")
async def get_overdue_tasks(
    studio_id: str = Query(...),
    _=Depends(require_permission("facilities.view_schedules")),
):
    """Get overdue facility schedule tasks."""
    items = await svc.get_overdue_tasks(studio_id)
    return {"data": items}


@router.get("/schedules/{schedule_id}")
async def get_schedule(
    schedule_id: str,
    _=Depends(require_permission("facilities.view_schedules")),
):
    """Get a single facility schedule."""
    item = await svc.get_schedule(schedule_id)
    if not item:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"data": item}


@router.post("/schedules", status_code=201)
async def create_schedule(
    request: ScheduleCreate,
    _=Depends(require_permission("facilities.create_schedule")),
):
    """Create a new facility schedule."""
    item = await svc.create_schedule(request.model_dump())
    return {"data": item}


@router.put("/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: str,
    request: ScheduleUpdate,
    _=Depends(require_permission("facilities.edit_schedule")),
):
    """Update a facility schedule."""
    item = await svc.update_schedule(
        schedule_id, request.model_dump(exclude_unset=True)
    )
    if not item:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"data": item}


@router.delete("/schedules/{schedule_id}", status_code=204)
async def delete_schedule(
    schedule_id: str,
    _=Depends(require_permission("facilities.delete_schedule")),
):
    """Soft-delete a facility schedule."""
    deleted = await svc.delete_schedule(schedule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Schedule not found")


@router.post("/schedules/{schedule_id}/complete")
async def complete_schedule(
    schedule_id: str,
    request: ScheduleCompleteRequest,
    user=Depends(get_current_user),
    _=Depends(require_permission("facilities.complete_schedule")),
):
    """Record a schedule completion and bump next_due_at."""
    item = await svc.complete_schedule(
        schedule_id,
        completed_by=user.get("user_id"),
        notes=request.notes,
        photos=request.photos,
    )
    return {"data": item}


@router.get("/schedules/{schedule_id}/history")
async def get_schedule_history(
    schedule_id: str,
    limit: int = Query(20, le=100),
    _=Depends(require_permission("facilities.view_schedules")),
):
    """Get completion history for a facility schedule."""
    items = await svc.get_schedule_history(schedule_id, limit)
    return {"data": items}
