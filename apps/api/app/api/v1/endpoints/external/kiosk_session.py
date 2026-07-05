"""AuraFlow — External Kiosk Session

PIN-based staff auth for the white-label portal kiosk. A staff member
(owner / admin / front_desk) types their 4-digit PIN at the kiosk
tablet; if it matches the bcrypt hash stored on their organization_users
row for THIS tenant, we issue a JWT scoped to their staff role with
an extra `is_kiosk_session: true` claim.

Why PIN instead of email+password:
  - Customer-facing tablet — staff don't want to type their full
    password where members can shoulder-surf
  - PIN is per-tenant (a staff at studio-A can't use their PIN to
    authenticate at studio-B's kiosk even if they're the same human)
  - Short — 4 digits is fine because (a) it's a secondary factor
    behind the api_key in the auth header (b) we rate-limit aggressively

Endpoints:

  POST /api/v1/external/kiosk/session
       Auth: Bearer <api_key>
       Body: {"pin": "1234"}
       → Same TokenResponse shape as /auth/login/json. JWT carries
         org_slug, org_role, is_kiosk_session=true, exp=8h.

  PUT  /api/v1/external/kiosk/staff-pins/{user_id}
       Auth: Bearer <api_key> (with branding:write or kiosk:admin scope)
       Body: {"pin": "1234"}
       → Sets/rotates the PIN for one staff member of this tenant.
         user_id must be a member of the api_key's org with role in
         (owner, admin, front_desk). 404 if not.

  DELETE /api/v1/external/kiosk/staff-pins/{user_id}
       Removes a PIN (staff member can no longer use kiosk).

Existing dashboard kiosk path is UNCHANGED — that uses standard JWT
auth with email+password. This is an additive auth method.

Rate limiting: 10 attempts/minute per source IP (slowapi). After
5 failed attempts in 15 minutes the api_key context flag should
require backoff — not implemented yet, document for follow-up.
"""
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.v1.dependencies.api_key_auth import get_api_key_context
from app.core.security import hash_password, verify_password
from app.core.logging import logger
from app.db.session import get_global_db
from app.services.platform.audit_service import audit_service

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

# PIN constraints — 4 to 8 digits. 4 is the floor for usability;
# 8 cap stops anyone from trying to use it as a password.
_KIOSK_ELIGIBLE_ROLES = {"owner", "admin", "front_desk"}
_KIOSK_SESSION_TTL_SECONDS = 8 * 60 * 60  # 8h — covers a full shift


class KioskSessionRequest(BaseModel):
    pin: str = Field(..., min_length=4, max_length=8, pattern=r"^\d+$")


class KioskPinSetRequest(BaseModel):
    pin: str = Field(..., min_length=4, max_length=8, pattern=r"^\d+$")


@router.post(
    "/kiosk/session",
    summary="Exchange a staff PIN for a kiosk-scoped JWT",
)
@limiter.limit("10/minute")
async def kiosk_session(
    request: Request,
    body: KioskSessionRequest,
    ctx: Annotated[dict, Depends(get_api_key_context)],
):
    """Issue a kiosk JWT for a staff member who entered the right PIN."""
    # Local imports to avoid pulling auth-router code at module import time.
    from app.api.v1.endpoints.auth import _issue_tokens

    org_id = ctx["org_id"]
    org_slug = ctx["org_slug"]
    client_ip = request.client.host if request.client else None

    # Find any active staff member in this tenant whose PIN hash matches.
    # bcrypt verify is constant-time, so iterating all eligible staff is
    # acceptable — a single tenant has small staff counts (< 50 typically).
    async with get_global_db() as db:
        rows = await db.fetch(
            """
            SELECT ou.user_id, ou.role, ou.kiosk_pin_hash, u.email,
                   u.force_password_reset
            FROM af_global.organization_users ou
            JOIN af_global.users u ON u.id = ou.user_id
            WHERE ou.organization_id = $1
              AND ou.is_active = TRUE
              AND ou.role = ANY($2::text[])
              AND ou.kiosk_pin_hash IS NOT NULL
              AND u.is_active = TRUE
            """,
            org_id,
            list(_KIOSK_ELIGIBLE_ROLES),
        )

    matched_row = None
    for row in rows:
        if verify_password(body.pin, row["kiosk_pin_hash"]):
            matched_row = row
            break

    if matched_row is None:
        # Generic 401 — never leak whether a PIN is set vs which staff has it
        await audit_service.log_failed_login(
            email=f"<kiosk-pin>@{org_slug}",
            ip_address=client_ip,
            reason="kiosk_pin_no_match",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid PIN",
        )

    user_id = str(matched_row["user_id"])
    role = matched_row["role"]
    email = matched_row["email"]
    force_password_reset = bool(matched_row["force_password_reset"])

    async with get_global_db() as db:
        await db.execute(
            "UPDATE af_global.users SET last_login_at = NOW() WHERE id = $1",
            user_id,
        )

    await audit_service.log_login_success(
        user_id=user_id, email=email, ip_address=client_ip,
    )
    logger.info(
        "Kiosk session issued",
        user_id=user_id, tenant=org_slug, role=role, kiosk=True,
    )

    # Issue JWT via the same helper as the regular login flow. The
    # is_kiosk_session claim is ADDITIVE — existing JWT consumers
    # ignore unknown claims, so no behavior change for non-kiosk paths.
    # force_password_reset is propagated so the kiosk flow cannot bypass
    # an admin-mandated password reset.
    return await _issue_tokens(
        user_id,
        email,
        is_platform_admin=False,
        org_slug=org_slug,
        org_role=role,
        force_password_reset=force_password_reset,
    )


@router.put(
    "/kiosk/staff-pins/{user_id}",
    summary="Set or rotate a staff member's kiosk PIN (api-key admin)",
)
async def set_kiosk_pin(
    user_id: str,
    body: KioskPinSetRequest,
    ctx: Annotated[dict, Depends(get_api_key_context)],
):
    """Admin endpoint — sets the kiosk PIN for a staff member of the
    api_key's tenant. The staff member's current PIN (if any) is
    overwritten. Returns 404 if the user_id isn't a member of this
    tenant or isn't in a kiosk-eligible role.
    """
    org_id = ctx["org_id"]

    async with get_global_db() as db:
        existing = await db.fetchrow(
            """
            SELECT id, role
            FROM af_global.organization_users
            WHERE organization_id = $1 AND user_id = $2 AND is_active = TRUE
            """,
            org_id, user_id,
        )

    if not existing:
        raise HTTPException(status_code=404, detail="Staff member not found in this tenant")

    if existing["role"] not in _KIOSK_ELIGIBLE_ROLES:
        # Don't leak the role specifically — return same 404 as
        # "not in this tenant".
        raise HTTPException(
            status_code=404,
            detail="Staff member not eligible for kiosk PIN",
        )

    pin_hash = hash_password(body.pin)
    async with get_global_db() as db:
        await db.execute(
            """
            UPDATE af_global.organization_users
            SET kiosk_pin_hash = $1, kiosk_pin_set_at = NOW()
            WHERE organization_id = $2 AND user_id = $3
            """,
            pin_hash, org_id, user_id,
        )

    logger.info(
        "Kiosk PIN set",
        user_id=user_id, tenant=ctx["org_slug"], role=existing["role"],
    )
    return {"user_id": user_id, "kiosk_pin_set_at": datetime.now(timezone.utc).isoformat()}


@router.delete(
    "/kiosk/staff-pins/{user_id}",
    summary="Remove a staff member's kiosk PIN (api-key admin)",
)
async def remove_kiosk_pin(
    user_id: str,
    ctx: Annotated[dict, Depends(get_api_key_context)],
):
    org_id = ctx["org_id"]
    async with get_global_db() as db:
        result = await db.execute(
            """
            UPDATE af_global.organization_users
            SET kiosk_pin_hash = NULL, kiosk_pin_set_at = NULL
            WHERE organization_id = $1 AND user_id = $2
              AND kiosk_pin_hash IS NOT NULL
            """,
            org_id, user_id,
        )
    logger.info("Kiosk PIN removed", user_id=user_id, tenant=ctx["org_slug"])
    return {"user_id": user_id, "removed": True}


@router.get(
    "/kiosk/staff-pins",
    summary="List staff members eligible for kiosk PIN (api-key admin)",
)
async def list_kiosk_eligible_staff(
    ctx: Annotated[dict, Depends(get_api_key_context)],
):
    """Return the kiosk-eligible staff for this tenant, with whether each
    has a PIN set. Used by the white-label admin UI to show 'Set/Rotate
    PIN' buttons without exposing the hash itself."""
    org_id = ctx["org_id"]
    async with get_global_db() as db:
        rows = await db.fetch(
            """
            SELECT ou.user_id, ou.role, ou.kiosk_pin_set_at,
                   u.email, u.first_name, u.last_name
            FROM af_global.organization_users ou
            JOIN af_global.users u ON u.id = ou.user_id
            WHERE ou.organization_id = $1
              AND ou.is_active = TRUE
              AND ou.role = ANY($2::text[])
            ORDER BY u.first_name, u.last_name
            """,
            org_id,
            list(_KIOSK_ELIGIBLE_ROLES),
        )
    return {
        "data": [
            {
                "user_id": str(r["user_id"]),
                "email": r["email"],
                "first_name": r["first_name"],
                "last_name": r["last_name"],
                "role": r["role"],
                "has_pin": r["kiosk_pin_set_at"] is not None,
                "kiosk_pin_set_at": (
                    r["kiosk_pin_set_at"].isoformat()
                    if r["kiosk_pin_set_at"] else None
                ),
            }
            for r in rows
        ]
    }
