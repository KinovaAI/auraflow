"""AuraFlow — External Portal Magic Link

Senior-friendly passwordless login. Caller (your-domain.com etc.)
POSTs an email; we mint a short-lived signed token and return the full
magic-link URL. The caller emails it via their own email service.
User clicks → caller's /auth/verify page → caller exchanges the token
for a real access_token via the verify endpoint.

Endpoints:

  POST /api/v1/external/portal/magic-link
       Auth: Bearer af_live_<tenant-api-key>
       Body: {"email": "member@example.com",
              "return_url": "https://your-domain.com/auth/verify"}
       → {"magic_link": "...?token=<jwt>", "expires_in": 900,
           "user_id": "<uuid>"}

       Tenant-scoped: only emails that belong to members of the
       api_key's org are accepted. Generic 401 on miss — never leaks
       whether the email exists in another tenant.

  POST /api/v1/external/portal/magic-link/verify
       Body: {"token": "<jwt>"}
       (unauthed — token IS the auth)
       → Same TokenResponse shape as /auth/login/json

Magic tokens are 15-min JWTs with `purpose: "auraflow_magic_link"` so
they can't be reused as session tokens. Signed with APP_SECRET like
all other auraflow JWTs.

No email deliverability in auraflow — the CALLER handles email.
"""
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.v1.dependencies.api_key_auth import get_api_key_context
from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_global_db
from app.services.platform.audit_service import audit_service

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

_MAGIC_LINK_PURPOSE = "auraflow_magic_link"
_MAGIC_LINK_TTL_SECONDS = 15 * 60  # 15 min


class MagicLinkRequest(BaseModel):
    email: EmailStr
    return_url: str

    @field_validator("return_url")
    @classmethod
    def _https_only(cls, v: str) -> str:
        if v.startswith("https://"):
            return v
        # Localhost-for-dev — must be a strict prefix; "http://localhost.evil.com" must not pass.
        if v == "http://localhost" or v.startswith("http://localhost/") or v.startswith("http://localhost:"):
            return v
        raise ValueError("return_url must be https:// (localhost allowed for dev only)")


class MagicLinkResponse(BaseModel):
    magic_link: str
    expires_in: int
    user_id: str


class MagicLinkVerifyRequest(BaseModel):
    token: str


# ── Generate ────────────────────────────────────────────────────────────────

@router.post(
    "/portal/magic-link",
    response_model=MagicLinkResponse,
    summary="Mint a magic-link token for a member (caller emails it)",
)
@limiter.limit("5/minute")
async def create_magic_link(
    request: Request,
    body: MagicLinkRequest,
    ctx: Annotated[dict, Depends(get_api_key_context)],
):
    """Mint a 15-minute signed token for a member of the api_key's tenant.
    Returns the full magic-link URL so the caller can email it.

    Generic 401 on all failure modes (email not found, wrong tenant,
    deactivated account, role != member). Never leaks which failure.
    """
    tenant_org_id = ctx["org_id"]
    tenant_org_slug = ctx["org_slug"]
    client_ip = request.client.host if request.client else None

    async with get_global_db() as db:
        user = await db.fetchrow(
            """
            SELECT id, email, is_active
            FROM af_global.users
            WHERE email = $1
            """,
            body.email.lower(),
        )

    if not user or not user["is_active"]:
        await audit_service.log_failed_login(
            email=body.email.lower(), ip_address=client_ip,
            reason=f"magic_link@{tenant_org_slug}:not_found_or_inactive",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email",
        )

    user_id = str(user["id"])

    # Tenant + role gate — same logic as /external/portal/login
    async with get_global_db() as db:
        membership = await db.fetchrow(
            """
            SELECT role
            FROM af_global.organization_users
            WHERE user_id = $1 AND organization_id = $2 AND is_active = TRUE
            """,
            user_id, tenant_org_id,
        )

    if not membership or membership["role"] != "member":
        await audit_service.log_failed_login(
            email=body.email.lower(), ip_address=client_ip,
            reason=f"magic_link@{tenant_org_slug}:not_member",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email",
        )

    # Sign the magic-link JWT
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": user["email"],
        "org_id": str(tenant_org_id),
        "org_slug": tenant_org_slug,
        "purpose": _MAGIC_LINK_PURPOSE,
        "iat": now,
        "exp": now + timedelta(seconds=_MAGIC_LINK_TTL_SECONDS),
    }
    token = jwt.encode(payload, settings.APP_SECRET, algorithm=settings.JWT_ALGORITHM)

    separator = "&" if "?" in body.return_url else "?"
    magic_link = f"{body.return_url}{separator}token={token}"

    logger.info(
        "Magic link minted",
        user_id=user_id, email=user["email"], tenant=tenant_org_slug,
    )

    return MagicLinkResponse(
        magic_link=magic_link,
        expires_in=_MAGIC_LINK_TTL_SECONDS,
        user_id=user_id,
    )


# ── Verify ──────────────────────────────────────────────────────────────────

@router.post(
    "/portal/magic-link/verify",
    summary="Exchange a magic-link token for an access_token",
)
@limiter.limit("10/minute")
async def verify_magic_link(
    request: Request,
    body: MagicLinkVerifyRequest,
):
    """Unauthed (the token IS the auth). Validates signature + expiry +
    purpose + tenant binding, then issues a regular access_token via
    the same _issue_tokens helper the login flow uses."""
    # Local import to avoid pulling auth-router at module load
    from app.api.v1.endpoints.auth import _issue_tokens

    try:
        payload = jwt.decode(
            body.token, settings.APP_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired link",
        )

    if payload.get("purpose") != _MAGIC_LINK_PURPOSE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired link",
        )

    user_id = payload.get("sub")
    tok_org_id = payload.get("org_id")
    tok_org_slug = payload.get("org_slug")
    if not (user_id and tok_org_id and tok_org_slug):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired link",
        )

    # Defensive re-check: the user's membership in the tenant must still
    # be active (in case they were deactivated between mint and click).
    async with get_global_db() as db:
        user = await db.fetchrow(
            """
            SELECT u.id, u.email, u.is_active, u.is_platform_admin,
                   u.force_password_reset, ou.role
            FROM af_global.users u
            JOIN af_global.organization_users ou ON ou.user_id = u.id
            WHERE u.id = $1 AND ou.organization_id = $2
              AND u.is_active = TRUE AND ou.is_active = TRUE
            """,
            user_id, tok_org_id,
        )

    if not user or user["role"] != "member":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired link",
        )

    client_ip = request.client.host if request.client else None
    await audit_service.log_login_success(
        user_id=user_id, email=user["email"], ip_address=client_ip,
    )
    logger.info(
        "Magic link verified",
        user_id=user_id, email=user["email"], tenant=tok_org_slug,
    )

    return await _issue_tokens(
        user_id,
        user["email"],
        is_platform_admin=False,
        org_slug=tok_org_slug,
        org_role="member",
        force_password_reset=bool(user["force_password_reset"]),
    )
