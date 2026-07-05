"""
AuraFlow — Staff Management & Permission Endpoints

Provides CRUD for staff members and granular permission management.
Owners can toggle individual function access per staff member.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.dependencies.auth import get_current_user
from app.api.v1.dependencies.rbac import require_permission
from app.core.logging import logger
from app.db.session import get_global_db
from app.schemas.staff import (
    StaffMemberResponse,
    UpdateStaffProfileRequest,
    UpdateRoleRequest,
    UpdatePermissionsRequest,
    UserPermissionsResponse,
)
from app.services.permissions import (
    permission_service,
    ALL_PERMISSIONS,
    DEFAULT_ROLE_PERMISSIONS,
)

router = APIRouter()


# ── Helper ───────────────────────────────────────────────────────────────────

async def _get_org_id_from_slug(org_slug: str) -> str:
    """Resolve organization ID from slug."""
    async with get_global_db() as db:
        row = await db.fetchrow(
            "SELECT id FROM af_global.organizations WHERE slug = $1",
            org_slug,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Organization not found")
    return str(row["id"])


async def _build_staff_response(
    row: dict, org_id: str, role: str,
) -> StaffMemberResponse:
    """Build StaffMemberResponse with permissions from service."""
    perms = await permission_service.get_user_permissions(
        org_id, str(row["user_id"]), role,
    )
    return StaffMemberResponse(
        user_id=str(row["user_id"]),
        email=row["email"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        role=row["role"],
        title=row.get("title"),
        department=row.get("department"),
        hire_date=row.get("hire_date"),
        is_active=row["is_active"],
        permissions=perms,
    )


# ── Get Current User's Permissions ──────────────────────────────────────────

@router.get(
    "/me/permissions",
    response_model=UserPermissionsResponse,
)
async def get_my_permissions(
    current_user: dict = Depends(get_current_user),
):
    """Get the current user's permissions for their active organization."""
    user_id = current_user.get("sub")
    org_slug = current_user.get("org_slug")
    role = current_user.get("org_role", "")

    if not org_slug:
        return UserPermissionsResponse(role=role, permissions=[])

    # Platform admin gets all permissions
    if current_user.get("is_platform_admin"):
        return UserPermissionsResponse(
            role="platform_admin", permissions=list(ALL_PERMISSIONS),
        )

    org_id = await _get_org_id_from_slug(org_slug)
    perms = await permission_service.get_user_permissions(org_id, user_id, role)
    return UserPermissionsResponse(role=role, permissions=perms)


# ── Get Default Permission Sets ─────────────────────────────────────────────

@router.get(
    "/permissions/defaults",
    dependencies=[Depends(require_permission("staff.view"))],
)
async def get_permission_defaults():
    """Get default permission sets per role. Used by the UI for reference."""
    return {
        "all_permissions": ALL_PERMISSIONS,
        "defaults": DEFAULT_ROLE_PERMISSIONS,
    }


# ── List Staff ──────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=list[StaffMemberResponse],
)
async def list_staff(
    rbac: dict = Depends(require_permission("staff.view")),
):
    """List all staff members (non-member users) in the organization."""
    org_slug = rbac["org_slug"]
    org_id = await _get_org_id_from_slug(org_slug)

    async with get_global_db() as db:
        rows = await db.fetch(
            """
            SELECT u.id as user_id, u.email, u.first_name, u.last_name,
                   ou.role, ou.is_active, ou.title, ou.department, ou.hire_date
            FROM af_global.organization_users ou
            JOIN af_global.users u ON u.id = ou.user_id
            JOIN af_global.organizations o ON o.id = ou.organization_id
            WHERE o.slug = $1 AND ou.role != 'member'
            ORDER BY
                CASE ou.role
                    WHEN 'owner' THEN 0
                    WHEN 'admin' THEN 1
                    WHEN 'instructor' THEN 2
                    WHEN 'front_desk' THEN 3
                END,
                u.last_name, u.first_name
            """,
            org_slug,
        )

    result = []
    for row in rows:
        staff = await _build_staff_response(dict(row), org_id, row["role"])
        result.append(staff)
    return result


# ── Get Staff Member Detail ─────────────────────────────────────────────────

@router.get(
    "/{user_id}",
    response_model=StaffMemberResponse,
)
async def get_staff_member(
    user_id: str,
    rbac: dict = Depends(require_permission("staff.view")),
):
    """Get a single staff member's details including permissions."""
    org_slug = rbac["org_slug"]
    org_id = await _get_org_id_from_slug(org_slug)

    async with get_global_db() as db:
        row = await db.fetchrow(
            """
            SELECT u.id as user_id, u.email, u.first_name, u.last_name,
                   ou.role, ou.is_active, ou.title, ou.department,
                   ou.hire_date, ou.notes
            FROM af_global.organization_users ou
            JOIN af_global.users u ON u.id = ou.user_id
            JOIN af_global.organizations o ON o.id = ou.organization_id
            WHERE o.slug = $1 AND u.id = $2
            """,
            org_slug, user_id,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Staff member not found")

    return await _build_staff_response(dict(row), org_id, row["role"])


# ── Update Staff Profile ────────────────────────────────────────────────────

@router.put(
    "/{user_id}",
    response_model=StaffMemberResponse,
)
async def update_staff_profile(
    user_id: str,
    request: UpdateStaffProfileRequest,
    rbac: dict = Depends(require_permission("staff.edit_profile")),
):
    """Update a staff member's profile (title, department, etc.)."""
    org_slug = rbac["org_slug"]
    org_id = await _get_org_id_from_slug(org_slug)

    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clauses = []
    params = []
    for i, (col, val) in enumerate(updates.items(), start=1):
        set_clauses.append(f"{col} = ${i}")
        params.append(val)

    params.extend([org_slug, user_id])
    query = f"""
        UPDATE af_global.organization_users ou
        SET {', '.join(set_clauses)}
        FROM af_global.organizations o
        WHERE o.id = ou.organization_id
          AND o.slug = ${len(params) - 1}
          AND ou.user_id = ${len(params)}
    """

    async with get_global_db() as db:
        result = await db.execute(query, *params)

    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Staff member not found")

    logger.info(
        "Staff profile updated",
        org=org_slug, user_id=user_id,
        fields=list(updates.keys()),
    )
    return await get_staff_member(user_id, rbac)


# ── Update Staff Role ───────────────────────────────────────────────────────

@router.put(
    "/{user_id}/role",
    response_model=StaffMemberResponse,
)
async def update_staff_role(
    user_id: str,
    request: UpdateRoleRequest,
    rbac: dict = Depends(require_permission("staff.set_role")),
):
    """Change a staff member's role. Owner only."""
    org_slug = rbac["org_slug"]
    org_id = await _get_org_id_from_slug(org_slug)

    # Prevent changing own role
    if user_id == rbac["user_id"]:
        raise HTTPException(status_code=400, detail="Cannot change your own role")

    async with get_global_db() as db:
        result = await db.execute(
            """
            UPDATE af_global.organization_users ou
            SET role = $1
            FROM af_global.organizations o
            WHERE o.id = ou.organization_id
              AND o.slug = $2
              AND ou.user_id = $3
            """,
            request.role, org_slug, user_id,
        )

    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Staff member not found")

    logger.info(
        "Staff role changed",
        org=org_slug, user_id=user_id,
        new_role=request.role, changed_by=rbac["user_id"],
    )
    return await get_staff_member(user_id, rbac)


# ── Update Staff Permissions ────────────────────────────────────────────────

@router.put(
    "/{user_id}/permissions",
    response_model=StaffMemberResponse,
)
async def update_staff_permissions(
    user_id: str,
    request: UpdatePermissionsRequest,
    rbac: dict = Depends(require_permission("staff.set_permissions")),
):
    """Update a staff member's granular permissions. Owner only."""
    org_slug = rbac["org_slug"]
    org_id = await _get_org_id_from_slug(org_slug)

    # Verify the user exists in this org
    async with get_global_db() as db:
        exists = await db.fetchval(
            """
            SELECT 1 FROM af_global.organization_users ou
            JOIN af_global.organizations o ON o.id = ou.organization_id
            WHERE o.slug = $1 AND ou.user_id = $2
            """,
            org_slug, user_id,
        )

    if not exists:
        raise HTTPException(status_code=404, detail="Staff member not found")

    await permission_service.set_user_permissions(
        org_id, user_id, request.permissions, rbac["user_id"],
    )

    logger.info(
        "Staff permissions updated",
        org=org_slug, user_id=user_id,
        changed_by=rbac["user_id"],
    )
    return await get_staff_member(user_id, rbac)
