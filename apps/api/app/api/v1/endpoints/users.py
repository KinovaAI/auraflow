"""AuraFlow — User profile endpoints."""
from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.dependencies.auth import get_current_user
from app.db.session import get_global_db, get_tenant_db
from app.schemas.auth import UserProfile, UserOrganization, UserStudioRole, UpdateProfileRequest

router = APIRouter()


@router.get("/me", response_model=UserProfile)
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get the current user's profile with their organizations."""
    user_id = current_user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    async with get_global_db() as db:
        user = await db.fetchrow(
            """
            SELECT id, email, first_name, last_name, phone,
                   avatar_url, is_platform_admin, email_verified
            FROM af_global.users
            WHERE id = $1
            """,
            user_id
        )

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    async with get_global_db() as db:
        orgs = await db.fetch(
            """
            SELECT o.id, o.slug, o.name, ou.role, o.status,
                   o.created_at + INTERVAL '14 days' AS trial_ends_at
            FROM af_global.organization_users ou
            JOIN af_global.organizations o ON o.id = ou.organization_id
            WHERE ou.user_id = $1 AND ou.is_active = TRUE
            """,
            user_id
        )

    # Load permissions for the current org context
    permissions = []
    current_org_slug = current_user.get("org_slug")
    current_role = current_user.get("org_role", "")
    if current_user.get("is_platform_admin"):
        from app.services.permissions import ALL_PERMISSIONS
        permissions = list(ALL_PERMISSIONS)
    elif current_org_slug:
        for org in orgs:
            if org["slug"] == current_org_slug:
                from app.services.permissions import permission_service
                permissions = await permission_service.get_user_permissions(
                    str(org["id"]), str(user["id"]), current_role,
                )
                break

    # Determine active org role from the JWT context
    active_org_role = current_role
    if not active_org_role and current_org_slug:
        for org in orgs:
            if org["slug"] == current_org_slug:
                active_org_role = org["role"]
                break

    # Check video access: staff/owner/admin always have access,
    # members need an active membership with online or all_access scope
    has_video_access = False
    if active_org_role in ("owner", "admin", "instructor", "front_desk") or user["is_platform_admin"]:
        has_video_access = True
    elif active_org_role == "member":
        try:
            async with get_tenant_db() as tdb:
                row = await tdb.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM member_memberships mm
                        JOIN membership_types mt ON mt.id = mm.membership_type_id
                        JOIN members m ON m.id = mm.member_id
                        WHERE m.user_id = $1
                          AND mm.status = 'active'
                          AND mt.access_scope IN ('online', 'all_access')
                    )
                    """,
                    user_id,
                )
                has_video_access = bool(row)
        except Exception:
            has_video_access = False

    # Load studio assignments for the current org
    studios = []
    if current_org_slug:
        try:
            async with get_tenant_db() as tdb:
                if active_org_role == "owner" or user["is_platform_admin"]:
                    # Owners/admins see all active studios
                    studio_rows = await tdb.fetch(
                        """
                        SELECT id, name, slug FROM studios
                        WHERE is_active = TRUE ORDER BY name
                        """
                    )
                    studios = [
                        UserStudioRole(
                            studio_id=str(r["id"]),
                            studio_name=r["name"],
                            studio_slug=r["slug"] or "",
                            role="owner",
                            is_primary=i == 0,
                        )
                        for i, r in enumerate(studio_rows)
                    ]
                elif active_org_role in ("admin", "instructor", "front_desk"):
                    studio_rows = await tdb.fetch(
                        """
                        SELECT s.id, s.name, s.slug, sur.role, sur.is_primary
                        FROM studio_user_roles sur
                        JOIN studios s ON s.id = sur.studio_id AND s.is_active = TRUE
                        WHERE sur.user_id = $1
                        ORDER BY sur.is_primary DESC, s.name
                        """,
                        user_id,
                    )
                    studios = [
                        UserStudioRole(
                            studio_id=str(r["id"]),
                            studio_name=r["name"],
                            studio_slug=r["slug"] or "",
                            role=r["role"],
                            is_primary=r["is_primary"],
                        )
                        for r in studio_rows
                    ]
        except Exception:
            studios = []

    return UserProfile(
        id=str(user["id"]),
        email=user["email"],
        first_name=user["first_name"],
        last_name=user["last_name"],
        phone=user.get("phone"),
        avatar_url=user.get("avatar_url"),
        is_platform_admin=user["is_platform_admin"],
        email_verified=user["email_verified"],
        organizations=[
            UserOrganization(
                id=str(org["id"]),
                slug=org["slug"],
                name=org["name"],
                role=org["role"],
                status=org["status"],
                trial_ends_at=org["trial_ends_at"].isoformat() if org["trial_ends_at"] else None,
            )
            for org in orgs
        ],
        permissions=permissions,
        active_org_slug=current_org_slug,
        active_org_role=active_org_role,
        has_video_access=has_video_access,
        studios=studios,
    )


@router.put("/me", response_model=UserProfile)
async def update_me(
    update: UpdateProfileRequest,
    current_user: dict = Depends(get_current_user),
):
    """Update the current user's profile."""
    user_id = current_user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Build SET clause from provided fields only
    updates = {}
    if update.first_name is not None:
        updates["first_name"] = update.first_name
    if update.last_name is not None:
        updates["last_name"] = update.last_name
    if update.phone is not None:
        updates["phone"] = update.phone

    _USER_UPDATE_COLS = {"first_name", "last_name", "phone"}
    updates = {k: v for k, v in updates.items() if k in _USER_UPDATE_COLS}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clauses = []
    params = []
    for i, (col, val) in enumerate(updates.items(), start=1):
        set_clauses.append(f"{col} = ${i}")
        params.append(val)

    params.append(user_id)
    query = f"UPDATE af_global.users SET {', '.join(set_clauses)}, updated_at = NOW() WHERE id = ${len(params)}"

    async with get_global_db() as db:
        await db.execute(query, *params)

    # Return updated profile
    return await get_me(current_user)
