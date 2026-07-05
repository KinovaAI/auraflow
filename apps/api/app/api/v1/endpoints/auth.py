"""
AuraFlow — Authentication Endpoints
JWT-based auth with refresh tokens.
"""
import asyncio
import uuid
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings
from app.core.security import (
    verify_password, create_access_token, create_refresh_token,
    decode_token, hash_password
)
from app.core.logging import logger
from app.db.session import get_global_db
from app.api.v1.dependencies.auth import get_current_user
from app.services.platform.audit_service import audit_service
from app.schemas.auth import (
    TokenResponse, LoginRequest, RefreshRequest,
    ForgotPasswordRequest, ResetPasswordRequest, RegisterRequest,
    MemberRegisterRequest,
    MFASetupResponse, MFAVerifySetupRequest, MFAVerifySetupResponse,
    MFADisableRequest, MFALoginPendingResponse, MFAVerifyRequest,
)

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


# ── Helpers ──────────────────────────────────────────────────────────────────
async def _get_default_org(user_id: str) -> tuple[str | None, str | None]:
    """Fetch the user's default (first active) organization."""
    async with get_global_db() as db:
        org = await db.fetchrow(
            """
            SELECT o.slug, ou.role
            FROM af_global.organization_users ou
            JOIN af_global.organizations o ON o.id = ou.organization_id
            WHERE ou.user_id = $1 AND ou.is_active = TRUE AND o.status != 'cancelled'
            ORDER BY ou.joined_at ASC NULLS LAST
            LIMIT 1
            """,
            user_id
        )
    if org:
        return org["slug"], org["role"]
    return None, None


async def _issue_tokens(
    user_id: str,
    email: str,
    is_platform_admin: bool,
    org_slug: str | None = None,
    org_role: str | None = None,
    force_password_reset: bool = False,
    force_password_change: bool = False,
    user_agent: str | None = None,
    ip: str | None = None,
) -> TokenResponse:
    token_data = {
        "sub": user_id,
        "email": email,
        "is_platform_admin": is_platform_admin,
    }
    if org_slug:
        token_data["org_slug"] = org_slug
    if org_role:
        token_data["org_role"] = org_role
    access_token = create_access_token(data=token_data)
    # Capture device fingerprint for theft detection on subsequent refresh.
    refresh_token = await create_refresh_token(
        user_id=user_id, user_agent=user_agent, ip=ip,
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        force_password_reset=force_password_reset,
        force_password_change=force_password_change,
    )


async def _send_reset_email(to_email: str, first_name: str, reset_url: str) -> None:
    """Send password reset email — STUDIO SMTP ONLY, NO FALLBACK.

    Same rule as `_send_verification_email`: NEVER use SendGrid; NEVER
    use platform-level SMTP credentials for a recipient who is attached
    to a studio. Resolves user → studio via the
    af_global.users.id ↔ af_tenant_*.members.user_id link, sets tenant
    context, and goes through EmailService which picks the studio's
    SMTP from `studio_email_accounts`. If no studio match (i.e. a
    platform-admin user), falls through to platform SMTP (Purelymail
    `settings.SMTP_*`) — never SendGrid.
    """
    from app.db.session import get_global_db, get_tenant_db
    from app.core.tenant_context import set_tenant_context, clear_tenant_context
    from app.services.email.email_service import EmailService

    html = f"""
    <p>Hey {first_name},</p>
    <p>We received a request to reset your AuraFlow password.
    Click the link below to set a new one:</p>
    <p><a href="{reset_url}" style="
        display: inline-block; padding: 12px 24px;
        background-color: #4F46E5; color: #ffffff;
        text-decoration: none; border-radius: 6px;
        font-weight: 600;">Reset Password</a></p>
    <p>This link expires in 1 hour. If you didn't request this, you can safely ignore it.</p>
    """
    subject = "Reset your AuraFlow password"

    # Resolve user → tenant
    studio_org_id = None
    studio_schema = None
    member_id_in_tenant = None
    try:
        async with get_global_db() as db:
            user_row = await db.fetchrow(
                "SELECT id FROM af_global.users WHERE LOWER(email) = LOWER($1)",
                to_email,
            )
            if user_row:
                schemas = await db.fetch(
                    "SELECT id::text AS org_id, schema_name FROM af_global.organizations "
                    "WHERE schema_name LIKE 'af_tenant_%' AND status IN ('active','trial')"
                )
                for s in schemas:
                    async with get_tenant_db(schema_override=s["schema_name"]) as tdb:
                        row = await tdb.fetchrow(
                            "SELECT id FROM members WHERE user_id = $1",
                            user_row["id"],
                        )
                        if row:
                            studio_org_id = s["org_id"]
                            studio_schema = s["schema_name"]
                            member_id_in_tenant = str(row["id"])
                            break
    except Exception as e:
        logger.warning("Reset email tenant resolution failed", error=str(e), email=to_email)

    if studio_org_id and studio_schema:
        # Studio member — send via studio SMTP (NO platform fallback).
        set_tenant_context(
            organization_id=studio_org_id,
            schema_name=studio_schema,
            slug=studio_schema.replace("af_tenant_", ""),
        )
        try:
            svc = EmailService()
            await svc.send_email(
                to_email=to_email,
                subject=subject,
                html_content=html,
                member_id=member_id_in_tenant,
                email_type="password_reset",
            )
        finally:
            clear_tenant_context()
        return

    # Platform-admin user (no tenant). Use platform Purelymail SMTP.
    from app.services.email.smtp_sender import is_smtp_configured, send_smtp_email
    if not is_smtp_configured():
        logger.error("SMTP not configured — password reset NOT sent", email=to_email)
        return
    await send_smtp_email(to_email=to_email, subject=subject, html_content=html)


async def _create_verification_token(user_id: str) -> str:
    """Create an email verification token stored in Redis (24h TTL)."""
    import hashlib, secrets
    from app.core.redis import get_redis

    raw_token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    redis = await get_redis()
    if redis:
        await redis.setex(f"email_verify:{token_hash}", 86400, user_id)  # 24 hours

    return raw_token


async def _send_verification_email(to_email: str, first_name: str, verify_url: str) -> None:
    """Send email verification email — STUDIO SMTP ONLY, NO FALLBACK.

    Don's absolute rule: AuraFlow platform credentials (SendGrid,
    platform Purelymail, any settings.SENDGRID_*/SMTP_* env vars)
    must NEVER be used to send mail to a studio recipient, and the
    code must NEVER fall back to platform credentials when studio
    SMTP fails. If the studio's SMTP is broken or the user is not
    attached to a studio, the email does not go. Period.

    Resolves the user → tenant via
    af_global.users.id ↔ af_tenant_*.members.user_id, sets tenant
    context, and calls EmailService.send_email which picks the
    studio's SMTP from studio_email_accounts and writes a
    communication_log row. If no studio match: no email is sent.
    """
    from app.db.session import get_global_db, get_tenant_db
    from app.core.tenant_context import set_tenant_context, clear_tenant_context
    from app.services.email.email_service import EmailService

    html = f"""
    <p>Hey {first_name},</p>
    <p>Please verify your email address by clicking the button below:</p>
    <p><a href="{verify_url}" style="
        display: inline-block; padding: 12px 24px;
        background-color: #4F46E5; color: #ffffff;
        text-decoration: none; border-radius: 6px;
        font-weight: 600;">Verify Email</a></p>
    <p>This link expires in 24 hours.</p>
    """

    # Resolve user → tenant via the af_global.users.id ↔ af_tenant_*.members.user_id link
    studio_org_id = None
    studio_schema = None
    member_id_in_tenant = None
    try:
        async with get_global_db() as db:
            user_row = await db.fetchrow(
                "SELECT id FROM af_global.users WHERE LOWER(email) = LOWER($1)",
                to_email,
            )
            if user_row:
                schemas = await db.fetch(
                    "SELECT id::text AS org_id, schema_name FROM af_global.organizations "
                    "WHERE schema_name LIKE 'af_tenant_%' AND status IN ('active','trial')"
                )
                for s in schemas:
                    try:
                        async with get_tenant_db(schema_override=s["schema_name"]) as tdb:
                            m = await tdb.fetchrow(
                                "SELECT id FROM members WHERE user_id = $1",
                                user_row["id"],
                            )
                            if m:
                                studio_org_id = s["org_id"]
                                studio_schema = s["schema_name"]
                                member_id_in_tenant = str(m["id"])
                                break
                    except Exception:
                        continue
    except Exception as e:
        logger.warning("Verification email tenant lookup failed", email=to_email, error=str(e))

    if not studio_schema:
        # No studio attachment → no email. Platform credentials are
        # not allowed as a fallback; if a platform-only user genuinely
        # needs verification, that's a separate code path that does
        # not exist (and intentionally so).
        logger.warning(
            "Verification email NOT sent — recipient has no studio attachment "
            "and platform credentials are forbidden",
            email=to_email,
        )
        return

    set_tenant_context(
        organization_id=studio_org_id or "verify",
        schema_name=studio_schema,
        slug=studio_schema.replace("af_tenant_", ""),
    )
    try:
        svc = EmailService()
        result = await svc.send_email(
            to_email=to_email,
            subject="Verify your email",
            html_content=html,
            member_id=member_id_in_tenant,
            email_type="email_verification",
        )
        if result.get("status") == "failed":
            # Studio SMTP failed — that's the studio's problem to fix.
            # We do NOT retry with platform creds. The verification
            # email simply does not go.
            logger.warning(
                "Verification email failed (studio SMTP) — no fallback attempted",
                email=to_email, schema=studio_schema,
            )
        else:
            logger.info(
                "Verification email sent via studio SMTP",
                email=to_email, schema=studio_schema,
            )
    finally:
        clear_tenant_context()


# ── Login (OAuth2 form for Swagger) ─────────────────────────────────────────
@router.post("/login")
@limiter.limit("5/minute")
async def login(request: Request, form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    """OAuth2-compatible login. Returns JWT access + refresh tokens."""
    from app.core.brute_force import is_locked, register_failure, clear_failures

    email_lower = form_data.username.lower()

    if await is_locked(email_lower):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts — try again in a few minutes.",
        )

    async with get_global_db() as db:
        user = await db.fetchrow(
            """
            SELECT id, email, password_hash, first_name, last_name,
                   is_active, is_platform_admin, force_password_reset,
                   force_password_change, totp_enabled
            FROM af_global.users
            WHERE email = $1
            """,
            email_lower,
        )

    if not user or not verify_password(form_data.password, user["password_hash"]):
        await register_failure(email_lower)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    await clear_failures(email_lower)

    if not user["is_active"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account deactivated")

    user_id = str(user["id"])

    # Check if MFA is enabled — return short-lived mfa_token instead of full tokens
    if user.get("totp_enabled"):
        mfa_token = _create_mfa_token(user_id, user["email"])
        logger.info("MFA required for login", user_id=user_id, email=user["email"])
        return MFALoginPendingResponse(mfa_token=mfa_token)

    async with get_global_db() as db:
        await db.execute(
            "UPDATE af_global.users SET last_login_at = NOW() WHERE id = $1",
            user_id
        )

    org_slug, org_role = await _get_default_org(user_id)
    logger.info("User logged in", user_id=user_id, email=user["email"], org=org_slug)
    client_ip = request.client.host if request.client else None
    return await _issue_tokens(
        user_id, user["email"], user["is_platform_admin"], org_slug, org_role,
        force_password_reset=bool(user.get("force_password_reset")),
        force_password_change=bool(user.get("force_password_change")),
        user_agent=request.headers.get("user-agent"),
        ip=client_ip,
    )


# ── Login (JSON body for frontend) ──────────────────────────────────────────
@router.post("/login/json")
@limiter.limit("5/minute")
async def login_json(request: Request, body: LoginRequest):
    """JSON-body login for frontend apps."""
    from app.core.brute_force import is_locked, register_failure, clear_failures

    email_lower = body.email.lower()
    client_ip = request.client.host if request.client else None

    if await is_locked(email_lower):
        await audit_service.log_failed_login(
            email=email_lower, ip_address=client_ip, reason="brute_force_locked",
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts — try again in a few minutes.",
        )

    async with get_global_db() as db:
        user = await db.fetchrow(
            """
            SELECT id, email, password_hash, first_name, last_name,
                   is_active, is_platform_admin, force_password_reset,
                   force_password_change, totp_enabled
            FROM af_global.users
            WHERE email = $1
            """,
            email_lower,
        )

    if not user or not user["password_hash"] or not verify_password(body.password, user["password_hash"]):
        await register_failure(email_lower)
        await audit_service.log_failed_login(
            email=email_lower, ip_address=client_ip,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    await clear_failures(email_lower)

    if not user["is_active"]:
        await audit_service.log_failed_login(
            email=body.email.lower(), ip_address=client_ip, reason="account_deactivated",
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account deactivated")

    user_id = str(user["id"])

    # Check if MFA is enabled — return short-lived mfa_token instead of full tokens
    if user.get("totp_enabled"):
        mfa_token = _create_mfa_token(user_id, user["email"])
        logger.info("MFA required for login", user_id=user_id, email=user["email"])
        return MFALoginPendingResponse(mfa_token=mfa_token)

    async with get_global_db() as db:
        await db.execute(
            "UPDATE af_global.users SET last_login_at = NOW() WHERE id = $1",
            user_id
        )

    await audit_service.log_login_success(
        user_id=user_id, email=user["email"], ip_address=client_ip,
    )
    org_slug, org_role = await _get_default_org(user_id)
    logger.info("User logged in", user_id=user_id, email=user["email"], org=org_slug)
    client_ip = request.client.host if request.client else None
    return await _issue_tokens(
        user_id, user["email"], user["is_platform_admin"], org_slug, org_role,
        force_password_reset=bool(user.get("force_password_reset")),
        force_password_change=bool(user.get("force_password_change")),
        user_agent=request.headers.get("user-agent"),
        ip=client_ip,
    )


# ── Register ─────────────────────────────────────────────────────────────────
@router.post("/register", response_model=TokenResponse, status_code=201)
@limiter.limit("3/minute")
async def register(request: Request, body: RegisterRequest):
    """Register a new user, optionally provisioning a studio organization."""
    # Check email uniqueness
    async with get_global_db() as db:
        existing = await db.fetchrow(
            "SELECT id FROM af_global.users WHERE email = $1",
            body.email.lower()
        )
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    password_hash = hash_password(body.password)

    try:
        if body.organization_name and body.organization_slug:
            # Studio owner signup - provision org + schema
            from app.services.tenant_provisioning import TenantProvisioningService
            provisioner = TenantProvisioningService()
            result = await provisioner.provision(
                organization_name=body.organization_name,
                slug=body.organization_slug,
                owner_email=body.email.lower(),
                owner_first_name=body.first_name,
                owner_last_name=body.last_name,
            )
            user_id = result["user_id"]
            # Provisioner creates user without password - set it now
            async with get_global_db() as db:
                await db.execute(
                    "UPDATE af_global.users SET password_hash = $1 WHERE id = $2",
                    password_hash, user_id
                )
        else:
            # User-only signup (joins an org later via invite)
            user_id = str(uuid.uuid4())
            async with get_global_db() as db:
                await db.execute(
                    """
                    INSERT INTO af_global.users
                        (id, email, password_hash, first_name, last_name)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    user_id, body.email.lower(), password_hash,
                    body.first_name, body.last_name
                )
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="Email already registered")

    # Handle invite token — auto-join the invited org
    org_slug = body.organization_slug
    org_role = "owner" if org_slug else None

    if body.invite_token and not org_slug:
        import hashlib
        from app.core.redis import get_redis
        redis = await get_redis()
        if redis:
            import json
            token_hash = hashlib.sha256(body.invite_token.encode()).hexdigest()
            invite_data_raw = await redis.get(f"invite:{token_hash}")
            if invite_data_raw:
                invite_data = json.loads(invite_data_raw.decode() if isinstance(invite_data_raw, bytes) else invite_data_raw)
                invite_org_slug = invite_data.get("org_slug")
                invite_role = invite_data.get("role", "member")

                # Link user to the org
                async with get_global_db() as db:
                    org = await db.fetchrow(
                        "SELECT id FROM af_global.organizations WHERE slug = $1",
                        invite_org_slug,
                    )
                    if org:
                        await db.execute(
                            """
                            INSERT INTO af_global.organization_users
                                (id, user_id, organization_id, role, joined_at, is_active)
                            VALUES ($1, $2, $3, $4, NOW(), TRUE)
                            ON CONFLICT (organization_id, user_id)
                            DO UPDATE SET role = EXCLUDED.role, is_active = TRUE, joined_at = NOW()
                            """,
                            str(uuid.uuid4()), user_id, str(org["id"]), invite_role,
                        )
                        # Initialize permissions
                        from app.services.permissions import permission_service
                        await permission_service.initialize_default_permissions(
                            str(org["id"]), user_id, invite_role,
                        )
                        org_slug = invite_org_slug
                        org_role = invite_role

                await redis.delete(f"invite:{token_hash}")

    # Send verification email
    try:
        raw_token = await _create_verification_token(user_id)
        verify_url = f"{settings.APP_URL}/verify-email?token={raw_token}"
        await _send_verification_email(body.email.lower(), body.first_name, verify_url)
    except Exception as e:
        logger.error("Failed to send verification email on register", error=str(e))

    # Store UTM attribution data
    if any([body.utm_source, body.utm_medium, body.utm_campaign, body.gclid, body.fbclid]):
        async with get_global_db() as db:
            await db.execute(
                """
                UPDATE af_global.users
                SET utm_source = $2, utm_medium = $3, utm_campaign = $4,
                    gclid = $5, fbclid = $6
                WHERE id = $1
                """,
                user_id, body.utm_source, body.utm_medium, body.utm_campaign,
                body.gclid, body.fbclid,
            )

    logger.info("User registered", user_id=user_id, email=body.email, org=org_slug)
    return await _issue_tokens(user_id, body.email.lower(), False, org_slug, org_role)


# ── Refresh ──────────────────────────────────────────────────────────────────
@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: Request, body: RefreshRequest):
    """Exchange a refresh token for new access + refresh tokens.

    Server-side idle-timeout enforcement (HIPAA §164.312(a)(2)(iii) "automatic
    logoff"): because refresh tokens rotate on every refresh, the `created_at`
    timestamp of the presented token is effectively the "last activity"
    timestamp. If it's older than SESSION_IDLE_TIMEOUT_MINUTES, the session
    is considered idle-expired.

    Device binding: if the refresh token was minted with a user_agent_hash
    at login, a refresh attempt from a completely different UA is treated
    as token theft → revoke the token, force re-login.
    """
    import hashlib
    from datetime import datetime, timezone, timedelta
    from app.core.config import settings
    from app.core.security import _hash_user_agent

    token_hash = hashlib.sha256(body.refresh_token.encode()).hexdigest()
    presented_ua = _hash_user_agent(request.headers.get("user-agent"))

    async with get_global_db() as db:
        stored = await db.fetchrow(
            """
            SELECT rt.user_id, rt.expires_at, rt.revoked_at, rt.created_at,
                   rt.user_agent_hash, rt.ip_first_seen,
                   u.email, u.is_active, u.is_platform_admin
            FROM af_global.refresh_tokens rt
            JOIN af_global.users u ON u.id = rt.user_id
            WHERE rt.token_hash = $1
            """,
            token_hash
        )

    if not stored:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if stored["revoked_at"]:
        raise HTTPException(status_code=401, detail="Refresh token revoked")
    if stored["expires_at"] < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Refresh token expired")
    if not stored["is_active"]:
        raise HTTPException(status_code=403, detail="Account deactivated")

    # Idle-session enforcement. Refresh tokens rotate on each successful
    # refresh so `created_at` effectively marks last activity.
    idle_minutes = settings.SESSION_IDLE_TIMEOUT_MINUTES or 0
    if idle_minutes > 0:
        idle_cutoff = datetime.now(timezone.utc) - timedelta(minutes=idle_minutes)
        if stored["created_at"] < idle_cutoff:
            async with get_global_db() as db:
                await db.execute(
                    "UPDATE af_global.refresh_tokens SET revoked_at = NOW() WHERE token_hash = $1",
                    token_hash,
                )
            raise HTTPException(
                status_code=401,
                detail="Session expired due to inactivity — please log in again.",
            )

    # Device-binding check: if the token was minted with a UA fingerprint
    # and the presented UA doesn't match, treat as theft — revoke + reject.
    if stored["user_agent_hash"] and presented_ua and stored["user_agent_hash"] != presented_ua:
        async with get_global_db() as db:
            await db.execute(
                "UPDATE af_global.refresh_tokens SET revoked_at = NOW() WHERE token_hash = $1",
                token_hash,
            )
        raise HTTPException(
            status_code=401,
            detail="Refresh token was used from a different device — session terminated.",
        )

    user_id = str(stored["user_id"])

    # Rotate: revoke old, issue new
    async with get_global_db() as db:
        await db.execute(
            "UPDATE af_global.refresh_tokens SET revoked_at = NOW() WHERE token_hash = $1",
            token_hash
        )

    org_slug, org_role = await _get_default_org(user_id)
    client_ip = request.client.host if request.client else None
    return await _issue_tokens(
        user_id, stored["email"], stored["is_platform_admin"], org_slug, org_role,
        user_agent=request.headers.get("user-agent"), ip=client_ip,
    )


# ── Session management (list + logout-all) ──────────────────────────────────
@router.get("/sessions")
async def list_sessions(current_user: dict = Depends(get_current_user)):
    """List a user's active refresh tokens (one row per logged-in device)."""
    user_id = current_user.get("sub")
    async with get_global_db() as db:
        rows = await db.fetch(
            """
            SELECT id, user_agent_hash, ip_first_seen, created_at,
                   last_refresh_at, expires_at
            FROM af_global.refresh_tokens
            WHERE user_id = $1
              AND revoked_at IS NULL
              AND expires_at > NOW()
            ORDER BY COALESCE(last_refresh_at, created_at) DESC
            """,
            user_id,
        )
    return {"data": [
        {
            "id": str(r["id"]),
            "user_agent_hash": r["user_agent_hash"],
            "ip_first_seen": str(r["ip_first_seen"]) if r["ip_first_seen"] else None,
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "last_refresh_at": r["last_refresh_at"].isoformat() if r["last_refresh_at"] else None,
            "expires_at": r["expires_at"].isoformat() if r["expires_at"] else None,
        }
        for r in rows
    ]}


@router.post("/logout-all", status_code=204)
async def logout_all_sessions(current_user: dict = Depends(get_current_user)):
    """Revoke every active refresh token for the user. Log them out of
    every device they're currently signed in on."""
    user_id = current_user.get("sub")
    async with get_global_db() as db:
        await db.execute(
            "UPDATE af_global.refresh_tokens SET revoked_at = NOW() "
            "WHERE user_id = $1 AND revoked_at IS NULL",
            user_id,
        )
    logger.info("All sessions revoked", user_id=user_id)


# ── Logout ───────────────────────────────────────────────────────────────────
@router.post("/logout", status_code=204)
async def logout(request: RefreshRequest):
    """Revoke a refresh token."""
    import hashlib
    token_hash = hashlib.sha256(request.refresh_token.encode()).hexdigest()

    async with get_global_db() as db:
        await db.execute(
            "UPDATE af_global.refresh_tokens SET revoked_at = NOW() WHERE token_hash = $1",
            token_hash
        )


# ── Switch Organization ─────────────────────────────────────────────────────
@router.post("/switch-org", response_model=TokenResponse)
async def switch_organization(
    org_slug: str,
    current_user: dict = Depends(get_current_user),
):
    """Switch the active organization context. Returns new tokens with the target org."""
    user_id = current_user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    async with get_global_db() as db:
        membership = await db.fetchrow(
            """
            SELECT ou.role, o.slug, o.status
            FROM af_global.organization_users ou
            JOIN af_global.organizations o ON o.id = ou.organization_id
            WHERE ou.user_id = $1 AND o.slug = $2 AND ou.is_active = TRUE
            """,
            user_id, org_slug
        )

    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this organization")
    if membership["status"] in ("suspended", "cancelled"):
        raise HTTPException(status_code=403, detail="Organization is not active")

    return await _issue_tokens(
        user_id,
        current_user.get("email"),
        current_user.get("is_platform_admin", False),
        membership["slug"],
        membership["role"],
    )


# ── Forgot Password ─────────────────────────────────────────────────────────
@router.post("/forgot-password", status_code=202)
@limiter.limit("3/15minutes")
async def forgot_password(request: Request, body: ForgotPasswordRequest):
    """
    Request a password reset email.
    Always returns 202 regardless of whether email exists (prevents enumeration).
    """
    async with get_global_db() as db:
        user = await db.fetchrow(
            "SELECT id, first_name FROM af_global.users WHERE email = $1",
            body.email.lower()
        )

    import asyncio, random
    from app.core.redis import get_redis

    redis = await get_redis()
    if not redis:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    import time as _time
    start = _time.monotonic()

    if user:
        import hashlib, secrets

        # Generate a secure reset token
        raw_token = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        # Store token_hash → user_id in Redis with 1-hour TTL
        await redis.setex(
            f"password_reset:{token_hash}",
            3600,  # 1 hour
            str(user["id"]),
        )

        # Build reset link
        reset_url = f"{settings.APP_URL}/reset-password?token={raw_token}"

        # Send via SendGrid (graceful fallback if not configured)
        await _send_reset_email(
            to_email=body.email.lower(),
            first_name=user["first_name"] or "there",
            reset_url=reset_url,
        )

        logger.info("Password reset requested", email=body.email)

    # Constant-time response to prevent email enumeration via timing
    # Always wait at least 0.3s regardless of whether email was found
    elapsed = _time.monotonic() - start
    if elapsed < 0.3:
        await asyncio.sleep(0.3 - elapsed + random.uniform(0.0, 0.1))

    return {"message": "If that email exists, you will receive reset instructions"}


# ── Reset Password ───────────────────────────────────────────────────────────
@router.post("/reset-password")
@limiter.limit("5/minute")
async def reset_password(request: Request, body: ResetPasswordRequest):
    """Reset password using a valid token from the reset email."""
    import hashlib

    token_hash = hashlib.sha256(body.token.encode()).hexdigest()

    redis = None
    try:
        from app.core.redis import get_redis
        redis = await get_redis()
    except Exception:
        pass

    if not redis:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    user_id_raw = await redis.get(f"password_reset:{token_hash}")
    if not user_id_raw:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user_id = user_id_raw.decode() if isinstance(user_id_raw, bytes) else user_id_raw

    # Delete token (single-use)
    await redis.delete(f"password_reset:{token_hash}")

    new_hash = hash_password(body.new_password)

    async with get_global_db() as db:
        await db.execute(
            "UPDATE af_global.users SET password_hash = $1, "
            "force_password_reset = FALSE, force_password_change = FALSE "
            "WHERE id = $2",
            new_hash, user_id
        )
        # Revoke all refresh tokens for security
        await db.execute(
            "UPDATE af_global.refresh_tokens SET revoked_at = NOW() WHERE user_id = $1 AND revoked_at IS NULL",
            user_id
        )

    await audit_service.log(
        user_id=user_id, action="user.password_reset",
        resource_type="user", resource_id=user_id,
        ip_address=request.client.host if request.client else None,
    )
    logger.info("Password reset completed", user_id=user_id)
    return {"message": "Password reset successfully"}


# ── Change Password (authenticated, for force_password_reset) ────────────────
from pydantic import BaseModel as _BaseModel, field_validator as _field_validator


class ChangePasswordRequest(_BaseModel):
    current_password: str | None = None
    new_password: str

    @_field_validator("new_password")
    @classmethod
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


@router.post("/change-password")
async def change_password(body: ChangePasswordRequest, current_user: dict = Depends(get_current_user)):
    """Change password for authenticated user. Clears force_password_reset flag.
    Requires current_password unless user has force_password_reset set."""
    user_id = current_user["sub"]

    async with get_global_db() as db:
        user = await db.fetchrow(
            "SELECT password_hash, force_password_reset FROM af_global.users WHERE id = $1",
            user_id,
        )
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Require current password unless force_password_reset is set
        if not user["force_password_reset"]:
            if not body.current_password:
                raise HTTPException(status_code=400, detail="Current password is required")
            if not verify_password(body.current_password, user["password_hash"]):
                raise HTTPException(status_code=400, detail="Current password is incorrect")

        new_hash = hash_password(body.new_password)
        await db.execute(
            "UPDATE af_global.users SET password_hash = $1, "
            "force_password_reset = FALSE, force_password_change = FALSE "
            "WHERE id = $2",
            new_hash, user_id,
        )

    await audit_service.log(
        user_id=user_id, action="user.password_change",
        resource_type="user", resource_id=user_id,
    )
    logger.info("Password changed", user_id=user_id)
    return {"message": "Password changed successfully"}


# ── Member Registration ─────────────────────────────────────────────────────
@router.post("/member-register", response_model=TokenResponse, status_code=201)
@limiter.limit("3/minute")
async def member_register(request: Request, body: MemberRegisterRequest):
    """
    Register as a member of a specific studio.
    Creates user account, links to org with member role, and links or creates
    a member record in the tenant schema.
    """
    email = body.email.lower()

    # 1. Look up the organization
    async with get_global_db() as db:
        org = await db.fetchrow(
            "SELECT id, slug, schema_name, status FROM af_global.organizations WHERE slug = $1",
            body.org_slug,
        )
    if not org:
        raise HTTPException(status_code=404, detail="Studio not found")
    if org["status"] in ("suspended", "cancelled"):
        raise HTTPException(status_code=403, detail="Studio is not accepting registrations")

    org_id = str(org["id"])
    schema_name = org["schema_name"]

    # 2. Check if user already exists
    async with get_global_db() as db:
        existing_user = await db.fetchrow(
            "SELECT id, email, password_hash, is_platform_admin FROM af_global.users WHERE email = $1",
            email,
        )

    if existing_user:
        # Require password verification when linking existing user to prevent account hijacking
        if not existing_user["password_hash"] or not verify_password(body.password, existing_user["password_hash"]):
            raise HTTPException(status_code=401, detail="Incorrect email or password")

        user_id = str(existing_user["id"])
        is_platform_admin = existing_user["is_platform_admin"]

        # Check if already linked to this org
        async with get_global_db() as db:
            org_link = await db.fetchrow(
                """
                SELECT id FROM af_global.organization_users
                WHERE user_id = $1 AND organization_id = $2
                """,
                user_id, org_id,
            )

        if org_link:
            raise HTTPException(status_code=409, detail="Already registered with this studio")

        # Link existing user to this org with member role
        async with get_global_db() as db:
            await db.execute(
                """
                INSERT INTO af_global.organization_users (id, user_id, organization_id, role)
                VALUES ($1, $2, $3, 'member')
                """,
                str(uuid.uuid4()), user_id, org_id,
            )
    else:
        # 3. Create new user
        user_id = str(uuid.uuid4())
        password_hash = hash_password(body.password)
        is_platform_admin = False

        async with get_global_db() as db:
            await db.execute(
                """
                INSERT INTO af_global.users (id, email, password_hash, first_name, last_name)
                VALUES ($1, $2, $3, $4, $5)
                """,
                user_id, email, password_hash, body.first_name, body.last_name,
            )
            await db.execute(
                """
                INSERT INTO af_global.organization_users (id, user_id, organization_id, role)
                VALUES ($1, $2, $3, 'member')
                """,
                str(uuid.uuid4()), user_id, org_id,
            )

    # 4. Link or create member record in tenant schema
    # Use get_tenant_db with schema_override for proper cleanup (avoids leaking search_path)
    from app.db.session import get_tenant_db
    async with get_tenant_db(schema_override=schema_name) as db:
        # Check if member record exists with matching email
        member = await db.fetchrow(
            "SELECT id, user_id FROM members WHERE email = $1",
            email,
        )

        if member and str(member["user_id"]) != user_id:
            # Link existing member record to user account (overwrite placeholder user_id)
            await db.execute(
                "UPDATE members SET user_id = $1, updated_at = NOW() WHERE id = $2",
                user_id, str(member["id"]),
            )
            logger.info("Linked existing member to user", member_id=str(member["id"]), user_id=user_id)
        elif member:
            pass  # Already linked
        else:
            # Create new member record
            member_id = str(uuid.uuid4())
            await db.execute(
                """
                INSERT INTO members (id, user_id, first_name, last_name, email, source)
                VALUES ($1, $2, $3, $4, $5, 'member_portal')
                """,
                member_id, user_id, body.first_name, body.last_name, email,
            )
            logger.info("Created member record", member_id=member_id, user_id=user_id)

    # Seed the member's default portal permissions. The RBAC system gates
    # every /portal/* endpoint on per-user rows in af_global.user_permissions;
    # without this seed a freshly-registered member gets 403 on every portal
    # call (profile, schedule, memberships, waiver), silently breaking the
    # new-member provisioning flow (waiver + billing) and the portal itself.
    try:
        from app.services.permissions import permission_service
        await permission_service.initialize_default_permissions(org_id, user_id, "member")
    except Exception as e:
        logger.warning("Failed to seed member permissions on register", user_id=user_id, error=str(e))

    logger.info("Member registered", user_id=user_id, email=email, org=body.org_slug)
    return await _issue_tokens(user_id, email, is_platform_admin, body.org_slug, "member")


# ── Email Verification ─────────────────────────────────────────────────────
@router.get("/verify-email")
async def verify_email(token: str):
    """Verify a user's email using the token from the verification email."""
    import hashlib
    from app.core.redis import get_redis

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    redis = await get_redis()
    if not redis:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    user_id_raw = await redis.get(f"email_verify:{token_hash}")
    if not user_id_raw:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    user_id = user_id_raw.decode() if isinstance(user_id_raw, bytes) else user_id_raw

    async with get_global_db() as db:
        await db.execute(
            "UPDATE af_global.users SET email_verified = TRUE, updated_at = NOW() WHERE id = $1",
            user_id,
        )

    await redis.delete(f"email_verify:{token_hash}")
    logger.info("Email verified", user_id=user_id)
    return {"message": "Email verified successfully"}


@router.post("/resend-verification", status_code=202)
@limiter.limit("3/15minutes")
async def resend_verification(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Resend the email verification email."""
    user_id = current_user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    async with get_global_db() as db:
        user = await db.fetchrow(
            "SELECT email, first_name, email_verified FROM af_global.users WHERE id = $1",
            user_id,
        )

    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user["email_verified"]:
        return {"message": "Email is already verified"}

    raw_token = await _create_verification_token(user_id)
    verify_url = f"{settings.APP_URL}/verify-email?token={raw_token}"
    await _send_verification_email(user["email"], user["first_name"] or "there", verify_url)

    return {"message": "Verification email sent"}


# ── Invite Token Validation ────────────────────────────────────────────────
@router.get("/validate-invite")
async def validate_invite(token: str):
    """Validate a staff invite token and return the invitation details."""
    import hashlib, json
    from app.core.redis import get_redis

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    redis = await get_redis()
    if not redis:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    invite_raw = await redis.get(f"invite:{token_hash}")
    if not invite_raw:
        raise HTTPException(status_code=400, detail="Invalid or expired invite token")

    invite_data = json.loads(invite_raw.decode() if isinstance(invite_raw, bytes) else invite_raw)
    return {
        "org_slug": invite_data.get("org_slug"),
        "org_name": invite_data.get("org_name", ""),
        "role": invite_data.get("role", "member"),
        "email": invite_data.get("email", ""),
    }


# ── MFA / TOTP Helpers ────────────────────────────────────────────────────
from datetime import datetime, timedelta, timezone as _tz

MFA_TOKEN_EXPIRE_MINUTES = 5  # short-lived


def _create_mfa_token(user_id: str, email: str) -> str:
    """Create a short-lived JWT that only authorizes an MFA verification step."""
    import jwt as _jwt
    now = datetime.now(_tz.utc)
    expire = now + timedelta(minutes=MFA_TOKEN_EXPIRE_MINUTES)
    return _jwt.encode(
        {"sub": user_id, "email": email, "purpose": "mfa", "exp": expire, "iat": now},
        settings.APP_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


def _decode_mfa_token(token: str) -> dict:
    """Decode an MFA-purpose JWT. Raises HTTPException on failure."""
    import jwt as _jwt
    try:
        payload = _jwt.decode(token, settings.APP_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except _jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired MFA token")
    if payload.get("purpose") != "mfa":
        raise HTTPException(status_code=401, detail="Invalid MFA token")
    return payload


# ── MFA Setup ─────────────────────────────────────────────────────────────
@router.post("/mfa/setup", response_model=MFASetupResponse)
async def mfa_setup(current_user: dict = Depends(get_current_user)):
    """Generate a TOTP secret and provisioning URI for QR code display.

    The secret is stored on the user row but MFA is NOT enabled until the
    user verifies with a valid TOTP code via ``/mfa/verify-setup``.
    """
    from app.services.auth.totp_service import generate_secret, generate_provisioning_uri

    user_id = current_user["sub"]
    email = current_user["email"]

    secret = generate_secret()
    uri = generate_provisioning_uri(email, secret)

    # Persist the secret (but keep totp_enabled = FALSE)
    async with get_global_db() as db:
        await db.execute(
            "UPDATE af_global.users SET totp_secret = $1 WHERE id = $2",
            secret, user_id,
        )

    logger.info("MFA setup initiated", user_id=user_id)
    return MFASetupResponse(provisioning_uri=uri, secret=secret)


# ── MFA Verify Setup ─────────────────────────────────────────────────────
@router.post("/mfa/verify-setup", response_model=MFAVerifySetupResponse)
async def mfa_verify_setup(
    body: MFAVerifySetupRequest,
    current_user: dict = Depends(get_current_user),
):
    """Verify that the user's authenticator app is producing valid codes.

    On success: enables TOTP, generates backup codes, and returns them.
    """
    from app.services.auth.totp_service import (
        verify_totp, generate_backup_codes, hash_backup_codes,
    )

    user_id = current_user["sub"]

    async with get_global_db() as db:
        user = await db.fetchrow(
            "SELECT totp_secret, totp_enabled FROM af_global.users WHERE id = $1",
            user_id,
        )

    if not user or not user["totp_secret"]:
        raise HTTPException(status_code=400, detail="MFA setup not initiated — call /mfa/setup first")

    if user["totp_enabled"]:
        raise HTTPException(status_code=400, detail="MFA is already enabled")

    if not verify_totp(user["totp_secret"], body.code):
        raise HTTPException(status_code=400, detail="Invalid TOTP code")

    # Generate backup codes
    raw_codes = generate_backup_codes()
    hashed = hash_backup_codes(raw_codes)

    async with get_global_db() as db:
        await db.execute(
            """
            UPDATE af_global.users
            SET totp_enabled = TRUE, backup_codes = $1
            WHERE id = $2
            """,
            hashed, user_id,
        )

    await audit_service.log(
        user_id=user_id, action="user.mfa_enable",
        resource_type="user", resource_id=user_id,
    )
    logger.info("MFA enabled", user_id=user_id)
    return MFAVerifySetupResponse(backup_codes=raw_codes)


# ── MFA Disable ───────────────────────────────────────────────────────────
@router.post("/mfa/disable")
async def mfa_disable(
    body: MFADisableRequest,
    current_user: dict = Depends(get_current_user),
):
    """Disable MFA. Requires the user's password and a valid TOTP code."""
    from app.services.auth.totp_service import verify_totp

    user_id = current_user["sub"]

    async with get_global_db() as db:
        user = await db.fetchrow(
            "SELECT password_hash, totp_secret, totp_enabled FROM af_global.users WHERE id = $1",
            user_id,
        )

    if not user or not user["totp_enabled"]:
        raise HTTPException(status_code=400, detail="MFA is not enabled")

    if not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Incorrect password")

    if not verify_totp(user["totp_secret"], body.code):
        raise HTTPException(status_code=400, detail="Invalid TOTP code")

    async with get_global_db() as db:
        await db.execute(
            """
            UPDATE af_global.users
            SET totp_enabled = FALSE, totp_secret = NULL, backup_codes = NULL
            WHERE id = $1
            """,
            user_id,
        )

    await audit_service.log(
        user_id=user_id, action="user.mfa_disable",
        resource_type="user", resource_id=user_id,
    )
    logger.info("MFA disabled", user_id=user_id)
    return {"message": "MFA disabled successfully"}


# ── MFA Verify (login second step) ───────────────────────────────────────
@router.post("/mfa/verify", response_model=TokenResponse)
@limiter.limit("5/minute")
async def mfa_verify(request: Request, body: MFAVerifyRequest):
    """Complete login by verifying a TOTP or backup code.

    Accepts the short-lived ``mfa_token`` issued during login plus a TOTP
    code *or* a backup code.  Returns full access/refresh tokens on success.
    """
    from app.services.auth.totp_service import verify_totp, verify_backup_code

    payload = _decode_mfa_token(body.mfa_token)
    user_id = payload["sub"]

    async with get_global_db() as db:
        user = await db.fetchrow(
            """
            SELECT email, is_platform_admin, totp_secret, totp_enabled,
                   backup_codes, force_password_reset, force_password_change
            FROM af_global.users
            WHERE id = $1
            """,
            user_id,
        )

    if not user or not user["totp_enabled"]:
        raise HTTPException(status_code=400, detail="MFA is not enabled for this account")

    # Try TOTP first
    if verify_totp(user["totp_secret"], body.code):
        pass  # success
    else:
        # Try backup code
        hashed_codes = list(user["backup_codes"]) if user["backup_codes"] else []
        matched, remaining = verify_backup_code(body.code, hashed_codes)
        if not matched:
            raise HTTPException(status_code=401, detail="Invalid TOTP or backup code")
        # Persist remaining backup codes
        async with get_global_db() as db:
            await db.execute(
                "UPDATE af_global.users SET backup_codes = $1 WHERE id = $2",
                remaining, user_id,
            )

    # MFA verified — update last_login and issue full tokens
    async with get_global_db() as db:
        await db.execute(
            "UPDATE af_global.users SET last_login_at = NOW() WHERE id = $1",
            user_id,
        )

    await audit_service.log_login_success(
        user_id=user_id, email=user["email"],
        ip_address=request.client.host if request.client else None,
        mfa_used=True,
    )
    org_slug, org_role = await _get_default_org(user_id)
    logger.info("User logged in (MFA verified)", user_id=user_id, email=user["email"])
    return await _issue_tokens(
        user_id, user["email"], user["is_platform_admin"], org_slug, org_role,
        force_password_reset=bool(user.get("force_password_reset")),
        force_password_change=bool(user.get("force_password_change")),
    )
