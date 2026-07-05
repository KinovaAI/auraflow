"""
AuraFlow — Role-Based Access Control Dependencies

Provides require_role() for gating endpoints by organization role.
Roles follow a hierarchy: owner > admin > instructor > front_desk > member.
A user with a higher role passes checks for lower roles.
"""
from fastapi import Depends, HTTPException, status

from app.api.v1.dependencies.auth import get_current_user
from app.db.session import get_global_db

# Role hierarchy — higher index = more privilege
ROLE_HIERARCHY = ["member", "front_desk", "instructor", "admin", "owner"]


def _role_level(role: str) -> int:
    try:
        return ROLE_HIERARCHY.index(role)
    except ValueError:
        return -1


def require_role(*allowed_roles: str):
    """
    FastAPI dependency that checks the user has one of the allowed roles
    (or a higher role in the hierarchy) in the current organization.

    The org is determined from the JWT token's org_slug claim.

    Usage:
        @router.get("/settings", dependencies=[Depends(require_role("owner", "admin"))])
        async def get_settings(): ...

    Or as a parameter dependency:
        async def endpoint(rbac=Depends(require_role("admin"))):
            # rbac contains {"user_id", "org_slug", "role"}
    """
    min_level = min(_role_level(r) for r in allowed_roles)

    async def check_role(current_user: dict = Depends(get_current_user)):
        user_id = current_user.get("sub")
        org_slug = current_user.get("org_slug")

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )

        # Platform admins bypass role checks
        if current_user.get("is_platform_admin"):
            return {
                "user_id": user_id,
                "org_slug": org_slug,
                "role": "platform_admin",
            }

        if not org_slug:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No organization context. Use /auth/switch-org first.",
            )

        # Fast path: check JWT claim (set at login, avoids DB hit)
        jwt_role = current_user.get("org_role")
        if jwt_role and _role_level(jwt_role) >= min_level:
            return {
                "user_id": user_id,
                "org_slug": org_slug,
                "role": jwt_role,
            }

        # Fallback: verify against DB (covers edge cases like role changes)
        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT ou.role
                FROM af_global.organization_users ou
                JOIN af_global.organizations o ON o.id = ou.organization_id
                WHERE ou.user_id = $1
                  AND o.slug = $2
                  AND ou.is_active = TRUE
                """,
                user_id, org_slug
            )

        if not row:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a member of this organization",
            )

        actual_role = row["role"]
        if _role_level(actual_role) < min_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {', '.join(allowed_roles)}",
            )

        return {
            "user_id": user_id,
            "org_slug": org_slug,
            "role": actual_role,
        }

    return check_role


def require_permission(*permission_keys: str):
    """
    FastAPI dependency that checks the user has a specific permission.

    Accepts one or more keys; the user passes if they have ANY of them
    (OR semantics — useful for endpoints serving both staff and members,
    e.g. `require_permission("private_sessions.book", "private_sessions.book_self")`).

    Returns the same rbac dict shape as require_role ({user_id, org_slug,
    role}) so endpoints that captured `rbac: dict = Depends(require_role(...))`
    can swap to require_permission(...) with no other code change.

    Owner and platform_admin always pass. Everyone else is checked
    against the user_permissions table (Redis-cached).

    Usage:
        @router.put("/courses/{id}", dependencies=[
            Depends(require_permission("workshops.edit")),
        ])

        async def cancel(rbac: dict = Depends(require_permission(
            "private_sessions.cancel_booking",
            "private_sessions.cancel_own",
        ))):
            ...
    """
    async def check_permission(current_user: dict = Depends(get_current_user)):
        user_id = current_user.get("sub")
        org_slug = current_user.get("org_slug")
        role = current_user.get("org_role", "")

        # Returned shape matches require_role so call sites can swap
        # one for the other without changing how they capture user info.
        rbac = {
            "user_id": user_id,
            "org_slug": org_slug,
            "role": role,
        }

        # Platform admin bypass — full access to everything
        if current_user.get("is_platform_admin"):
            rbac["role"] = "platform_admin"
            return rbac

        # Owner bypass — implicit grant on every permission
        if role == "owner":
            return rbac

        if not org_slug:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No organization context.",
            )

        # Resolve org_id from tenant context or DB
        from app.core.tenant_context import get_tenant_context
        ctx = get_tenant_context()
        if ctx:
            org_id = ctx.organization_id
        else:
            async with get_global_db() as db:
                row = await db.fetchrow(
                    "SELECT id FROM af_global.organizations WHERE slug = $1",
                    org_slug,
                )
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Organization not found",
                )
            org_id = str(row["id"])

        from app.services.permissions import permission_service
        for key in permission_keys:
            if await permission_service.has_permission(org_id, user_id, role, key):
                return rbac
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "Permission denied",
                "code": "PERMISSION_DENIED",
                "permission": list(permission_keys),
            },
        )

    return check_permission


def require_platform_admin():
    """FastAPI dependency that requires platform admin access."""
    async def check_admin(current_user: dict = Depends(get_current_user)):
        if not current_user.get("is_platform_admin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Platform admin access required",
            )
        return current_user

    return check_admin
