"""AuraFlow — External Portal Login

API-key-scoped member auth for white-label portal deploys.

Why this exists:
  /auth/login/json (the existing login) resolves the user's *default*
  org. That works fine for app.auraflow.fit where users sign in to
  whatever org they belong to. It does NOT work for a white-label
  portal: customer X's portal must only be able to log in customer X's
  members, never another tenant's members who happen to share an email.

Contract:
    POST /api/v1/external/portal/login
    Authorization: Bearer af_live_<tenant-api-key>
    Content-Type: application/json
    {"email": "member@example.com", "password": "..."}

The api_key identifies the tenant. The user must:
  - exist in af_global.users
  - have a password (not OAuth-only)
  - have an active organization_users row for THIS tenant
  - have role == 'member' (owners/admins/instructors use the dashboard,
    not the portal — separation of audience)

On success: same TokenResponse shape as /auth/login/json. The JWT's
org_slug is forced to the api_key's tenant — never the user's default.
This is the cross-tenant isolation guarantee. A unit test in
tests/test_portal_login_isolation.py pins the rule.

MFA / forced-password-reset / inactive-account handling mirrors the
existing flow exactly.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.v1.dependencies.api_key_auth import get_api_key_context
from app.core.security import verify_password
from app.core.logging import logger
from app.db.session import get_global_db
from app.services.platform.audit_service import audit_service

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


class PortalLoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/portal/login", summary="Member login scoped to this tenant's portal")
@limiter.limit("5/minute")
async def portal_login(
    request: Request,
    body: PortalLoginRequest,
    ctx: Annotated[dict, Depends(get_api_key_context)],
):
    """Authenticate a member through the white-label portal channel.

    Returns the same TokenResponse shape as POST /auth/login/json,
    but the JWT's `org_slug` is locked to the api_key's tenant — even
    if the user belongs to multiple orgs, the portal session is
    pinned to this one.
    """
    # Local import to avoid pulling auth-router code at module import time.
    from app.api.v1.endpoints.auth import _issue_tokens, _create_mfa_token

    tenant_org_slug = ctx["org_slug"]
    tenant_org_id = ctx["org_id"]
    client_ip = request.client.host if request.client else None

    async with get_global_db() as db:
        user = await db.fetchrow(
            """
            SELECT id, email, password_hash, is_active, is_platform_admin,
                   force_password_reset, totp_enabled
            FROM af_global.users
            WHERE email = $1
            """,
            body.email.lower(),
        )

    # Generic 401 — never leak whether the email exists vs the password is wrong
    # vs the user belongs to a different tenant. All three look identical.
    if (
        not user
        or not user["password_hash"]
        or not verify_password(body.password, user["password_hash"])
    ):
        await audit_service.log_failed_login(
            email=body.email.lower(), ip_address=client_ip,
            reason=f"portal_login@{tenant_org_slug}",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if not user["is_active"]:
        await audit_service.log_failed_login(
            email=body.email.lower(), ip_address=client_ip,
            reason=f"portal_login@{tenant_org_slug}:account_deactivated",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,  # 401 not 403 — same generic
            detail="Incorrect email or password",
        )

    user_id = str(user["id"])

    # Cross-tenant guard: user must have an active membership in THIS tenant
    # specifically. Any other org_role they have elsewhere is irrelevant.
    async with get_global_db() as db:
        membership = await db.fetchrow(
            """
            SELECT role
            FROM af_global.organization_users
            WHERE user_id = $1 AND organization_id = $2 AND is_active = TRUE
            """,
            user_id,
            tenant_org_id,
        )

    if not membership:
        # Same generic 401 — don't leak the tenant boundary
        await audit_service.log_failed_login(
            email=body.email.lower(), ip_address=client_ip,
            reason=f"portal_login@{tenant_org_slug}:not_a_member_of_this_tenant",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if membership["role"] != "member":
        # Owners / admins / instructors have to use app.auraflow.fit, not a
        # member portal. Generic 401 again so the response shape doesn't
        # leak the role info to a probing client.
        await audit_service.log_failed_login(
            email=body.email.lower(), ip_address=client_ip,
            reason=f"portal_login@{tenant_org_slug}:role_not_member({membership['role']})",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    # MFA branch — short-lived mfa_token; mfa-verify completes the login.
    if user.get("totp_enabled"):
        mfa_token = _create_mfa_token(user_id, user["email"])
        logger.info(
            "MFA required for portal login",
            user_id=user_id, email=user["email"], tenant=tenant_org_slug,
        )
        return {"requires_mfa": True, "mfa_token": mfa_token}

    async with get_global_db() as db:
        await db.execute(
            "UPDATE af_global.users SET last_login_at = NOW() WHERE id = $1", user_id,
        )

    await audit_service.log_login_success(
        user_id=user_id, email=user["email"], ip_address=client_ip,
    )
    logger.info(
        "Portal member login",
        user_id=user_id, email=user["email"], tenant=tenant_org_slug,
    )
    # JWT org_slug is pinned to the api_key's tenant — single source of truth.
    return await _issue_tokens(
        user_id,
        user["email"],
        is_platform_admin=False,  # platform admins never log in via portals
        org_slug=tenant_org_slug,
        org_role="member",
        force_password_reset=bool(user.get("force_password_reset")),
    )
