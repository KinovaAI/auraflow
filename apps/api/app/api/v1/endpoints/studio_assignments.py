"""AuraFlow — Studio Staff Assignment Endpoints

CRUD for assigning staff to studio locations with per-location roles.
Owners/admins can manage who has access to which location.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.v1.dependencies.rbac import require_permission
from app.db.session import get_tenant_db, get_global_db
from app.core.tenant_context import get_organization_id

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────

class AssignStaffRequest(BaseModel):
    user_id: str
    role: str  # admin, instructor, front_desk

class UpdateAssignmentRequest(BaseModel):
    role: str  # admin, instructor, front_desk


VALID_STUDIO_ROLES = {"admin", "instructor", "front_desk"}


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/{studio_id}/staff")
async def list_studio_staff(
    studio_id: str,
    rbac: dict = Depends(require_permission("staff.view_assignments")),
):
    """List all staff assigned to a studio location."""
    org_id = get_organization_id()

    async with get_tenant_db() as db:
        rows = await db.fetch(
            """
            SELECT sur.user_id, sur.role, sur.is_primary, sur.created_at
            FROM studio_user_roles sur
            WHERE sur.studio_id = $1
            ORDER BY sur.role, sur.created_at
            """,
            studio_id,
        )

    if not rows:
        return {"data": []}

    # Enrich with user info from global DB
    user_ids = [r["user_id"] for r in rows]
    async with get_global_db() as gdb:
        users = await gdb.fetch(
            """
            SELECT id, email, first_name, last_name
            FROM af_global.users
            WHERE id = ANY($1::uuid[])
            """,
            user_ids,
        )
    user_map = {str(u["id"]): u for u in users}

    data = []
    for r in rows:
        uid = str(r["user_id"])
        u = user_map.get(uid, {})
        data.append({
            "user_id": uid,
            "email": u.get("email", ""),
            "first_name": u.get("first_name", ""),
            "last_name": u.get("last_name", ""),
            "role": r["role"],
            "is_primary": r["is_primary"],
        })

    return {"data": data}


@router.post("/{studio_id}/staff")
async def assign_staff_to_studio(
    studio_id: str,
    body: AssignStaffRequest,
    rbac: dict = Depends(require_permission("staff.create_assignment")),
):
    """Assign a staff member to a studio location with a role."""
    if body.role not in VALID_STUDIO_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role. Must be one of: {', '.join(VALID_STUDIO_ROLES)}",
        )

    # Verify studio exists
    async with get_tenant_db() as db:
        studio = await db.fetchval(
            "SELECT id FROM studios WHERE id = $1 AND is_active = TRUE",
            studio_id,
        )
    if not studio:
        raise HTTPException(status_code=404, detail="Studio not found")

    # Verify user belongs to this org
    org_id = get_organization_id()
    async with get_global_db() as gdb:
        org_user = await gdb.fetchrow(
            """
            SELECT role FROM af_global.organization_users
            WHERE organization_id = $1 AND user_id = $2 AND is_active = TRUE
            """,
            org_id, body.user_id,
        )
    if not org_user:
        raise HTTPException(status_code=404, detail="User not found in this organization")
    if org_user["role"] == "owner":
        raise HTTPException(status_code=400, detail="Owners have access to all locations by default")
    if org_user["role"] == "member":
        raise HTTPException(status_code=400, detail="Members have org-wide access and don't need location assignments")

    # Check if this is the first assignment for the user (make it primary)
    async with get_tenant_db() as db:
        existing_count = await db.fetchval(
            "SELECT count(*) FROM studio_user_roles WHERE user_id = $1",
            body.user_id,
        )
        is_primary = existing_count == 0

        await db.execute(
            """
            INSERT INTO studio_user_roles (studio_id, user_id, role, is_primary)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (studio_id, user_id)
            DO UPDATE SET role = EXCLUDED.role, updated_at = NOW()
            """,
            studio_id, body.user_id, body.role, is_primary,
        )

    return {"data": {"assigned": True, "studio_id": studio_id, "user_id": body.user_id, "role": body.role}}


@router.put("/{studio_id}/staff/{user_id}")
async def update_studio_staff_role(
    studio_id: str,
    user_id: str,
    body: UpdateAssignmentRequest,
    rbac: dict = Depends(require_permission("staff.edit_assignment")),
):
    """Update a staff member's role at a studio location."""
    if body.role not in VALID_STUDIO_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role. Must be one of: {', '.join(VALID_STUDIO_ROLES)}",
        )

    async with get_tenant_db() as db:
        result = await db.execute(
            """
            UPDATE studio_user_roles
            SET role = $1, updated_at = NOW()
            WHERE studio_id = $2 AND user_id = $3
            """,
            body.role, studio_id, user_id,
        )

    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Staff assignment not found")

    return {"data": {"updated": True, "studio_id": studio_id, "user_id": user_id, "role": body.role}}


@router.delete("/{studio_id}/staff/{user_id}")
async def remove_staff_from_studio(
    studio_id: str,
    user_id: str,
    rbac: dict = Depends(require_permission("staff.delete_assignment")),
):
    """Remove a staff member's access to a studio location."""
    async with get_tenant_db() as db:
        result = await db.execute(
            "DELETE FROM studio_user_roles WHERE studio_id = $1 AND user_id = $2",
            studio_id, user_id,
        )

    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Staff assignment not found")

    return {"data": {"removed": True, "studio_id": studio_id, "user_id": user_id}}
