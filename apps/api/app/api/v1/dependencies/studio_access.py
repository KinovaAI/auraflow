"""
AuraFlow — Studio Access Dependency

Validates that the current user has access to a specific studio location.
Extracts studio_id from path parameter, query parameter, or X-Studio-Id header.

Owners and platform admins bypass studio_user_roles checks.
Members are org-wide (always pass). Staff must have a studio_user_roles row.
"""
from fastapi import Depends, HTTPException, Request, status

from app.api.v1.dependencies.auth import get_current_user
from app.db.session import get_tenant_db


def require_studio_access():
    """
    FastAPI dependency that checks studio-level access.

    Resolves studio_id from (in order):
    1. Path parameter `studio_id`
    2. Query parameter `studio_id`
    3. Header `X-Studio-Id`

    Returns dict with user_id, studio_id, studio_role.
    """

    async def check_studio_access(
        request: Request,
        current_user: dict = Depends(get_current_user),
    ):
        user_id = current_user.get("sub")
        org_role = current_user.get("org_role", "")
        is_platform_admin = current_user.get("is_platform_admin", False)

        # Resolve studio_id from path > query > header
        studio_id = request.path_params.get("studio_id")
        if not studio_id:
            studio_id = request.query_params.get("studio_id")
        if not studio_id:
            studio_id = request.headers.get("x-studio-id")

        if not studio_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="studio_id is required (path, query, or X-Studio-Id header)",
            )

        # Owner and platform admin always pass
        if org_role == "owner" or is_platform_admin:
            return {
                "user_id": user_id,
                "studio_id": studio_id,
                "studio_role": "owner",
            }

        # Members are org-wide
        if org_role == "member":
            return {
                "user_id": user_id,
                "studio_id": studio_id,
                "studio_role": "member",
            }

        # Staff: check studio_user_roles
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                SELECT sur.role
                FROM studio_user_roles sur
                JOIN studios s ON s.id = sur.studio_id AND s.is_active = TRUE
                WHERE sur.studio_id = $1 AND sur.user_id = $2
                """,
                studio_id,
                user_id,
            )

        if not row:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this studio location",
            )

        return {
            "user_id": user_id,
            "studio_id": studio_id,
            "studio_role": row["role"],
        }

    return check_studio_access
