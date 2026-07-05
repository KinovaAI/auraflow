"""AuraFlow — Square OAuth Service

Studio → Square OAuth Code Flow. KinovaAI is the OAuth platform; each
studio connects its own Square merchant account so member-side
payments route through the studio's Square account with a 1% app_fee
deducted to KinovaAI's platform account.

Token lifetimes (Square Code Flow):
  - Access token:  ~30 days
  - Refresh token: no expiry until revoked

CSRF: the `state` parameter on the authorize URL is a random token
stored in Redis with org_id as the value and a 10-minute TTL. The
callback must validate state → org_id matches the current request.

Storage: access + refresh tokens are encrypted with pgp_sym_encrypt
(APP_SECRET passphrase) into BYTEA columns on af_global.organizations.
The plain tokens never hit disk in cleartext.

On successful complete_oauth():
  - Tokens encrypted + stored
  - square_merchant_id + square_location_id captured
  - billing_provider flipped to 'square'
  - Audit log + owner email

On disconnect():
  - Revoke via Square API (best-effort — Square invalidates refresh)
  - Blank the Square columns
  - billing_provider flipped back to 'stripe'
"""
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.core.redis import get_redis
from app.db.session import get_global_db
from app.utils.encryption import encrypt_credential, decrypt_credential


# In-process decrypted-token cache. Square access tokens rotate every
# ~30 days, but on a checkout-heavy minute every payment was decrypting
# the token from DB → tens of redundant pgp_sym_decrypt calls per
# member. 60-second TTL is short enough that a manual disconnect /
# token rotation is picked up quickly, long enough to absorb bursty
# traffic. Single-process inside container; if sharded, each worker
# has its own (acceptable). The cache is busted on refresh + disconnect.
_TOKEN_CACHE_TTL_SECS = 60
_token_cache: dict[str, tuple[str, float]] = {}


def _cache_invalidate(organization_id: str) -> None:
    _token_cache.pop(organization_id, None)


# OAuth round-trip via Square's hosted authorize page should never take
# more than a few seconds, but 10 minutes covers slow networks, a
# distracted user, and a tab-switch back. Longer than ~15 min would let
# a stolen state token sit around too long. One-shot + bound to user_id
# (see start_oauth) is the actual replay protection; TTL is the cleanup.
_CSRF_TTL_SECONDS = 600
# Scopes required for the dual-run migration. Read-side scopes are
# necessary because reconcile + webhooks fetch resources back.
_OAUTH_SCOPES = [
    "PAYMENTS_WRITE",
    "PAYMENTS_READ",
    "PAYMENTS_WRITE_ADDITIONAL_RECIPIENTS",
    "CUSTOMERS_READ",
    "CUSTOMERS_WRITE",
    "SUBSCRIPTIONS_READ",
    "SUBSCRIPTIONS_WRITE",
    "ORDERS_READ",
    "ORDERS_WRITE",
    "INVOICES_READ",
    "INVOICES_WRITE",
    "ITEMS_READ",
    "ITEMS_WRITE",
    "MERCHANT_PROFILE_READ",
    # Required for POS device-code pairing (create_device_code +
    # list/get/delete devices). Without this scope Square returns 403
    # INSUFFICIENT_SCOPES on /v2/devices/codes calls.
    "DEVICE_CREDENTIAL_MANAGEMENT",
]


def _square_base() -> str:
    if (settings.SQUARE_ENVIRONMENT or "sandbox").lower() == "production":
        return "https://connect.squareup.com"
    return "https://connect.squareupsandbox.com"


def _refresh_buffer() -> timedelta:
    """Refresh tokens that expire within 7 days."""
    return timedelta(days=7)


class SquareOAuthService:

    # ── Authorize URL + CSRF ───────────────────────────────────────────

    async def start_oauth(self, organization_id: str, user_id: Optional[str] = None) -> str:
        """Generate the Square authorize URL with a CSRF state token.
        Caller redirects the studio's browser to the returned URL.

        user_id binds the state token to the requesting user — a stolen
        or shoulder-surfed state value cannot be redeemed by a different
        user. complete_oauth() verifies the bound user matches.
        """
        if not settings.SQUARE_OAUTH_APPLICATION_ID:
            raise ValueError("Square OAuth is not configured")
        state = secrets.token_urlsafe(32)
        redis = await get_redis()
        if redis:
            # Store both org_id and user_id; pipe-delimited to keep redis simple
            payload = f"{organization_id}|{user_id or ''}"
            await redis.set(
                f"square_oauth_csrf:{state}",
                payload,
                ex=_CSRF_TTL_SECONDS,
            )

        params = {
            "client_id": settings.SQUARE_OAUTH_APPLICATION_ID,
            "scope": " ".join(_OAUTH_SCOPES),
            "session": "false",  # don't auto-login an existing seller
            "state": state,
        }
        return f"{_square_base()}/oauth2/authorize?{urlencode(params)}"

    async def _consume_state(self, state: str) -> Optional[tuple[str, str]]:
        """Return (org_id, user_id) if the state token is valid, else None.
        One-shot: deleted after read to prevent replay."""
        redis = await get_redis()
        if not redis:
            return None
        val = await redis.get(f"square_oauth_csrf:{state}")
        if not val:
            return None
        await redis.delete(f"square_oauth_csrf:{state}")
        if isinstance(val, bytes):
            val = val.decode()
        # Backward-compat: pre-binding tokens are plain org_id strings
        if "|" in val:
            org_id, user_id = val.split("|", 1)
            return (org_id, user_id)
        return (val, "")

    # ── Code exchange + token storage ──────────────────────────────────

    async def complete_oauth(
        self,
        code: str,
        state: str,
        callback_user_id: Optional[str] = None,
    ) -> dict:
        """Exchange `code` for tokens, store encrypted, flip provider.

        callback_user_id, if provided, must match the user who started
        the flow. Mismatch = abort (the state was stolen / replayed by
        a different session).
        """
        consumed = await self._consume_state(state)
        if not consumed:
            raise ValueError("OAuth state token invalid or expired")
        org_id, bound_user_id = consumed
        if bound_user_id and callback_user_id and bound_user_id != callback_user_id:
            logger.warning(
                "Square OAuth state user mismatch — possible CSRF",
                bound_user_id=bound_user_id,
                callback_user_id=callback_user_id,
                org_id=org_id,
            )
            raise ValueError("OAuth state belongs to a different user")
        if not settings.SQUARE_OAUTH_APPLICATION_SECRET:
            raise ValueError("Square OAuth secret not configured")

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{_square_base()}/oauth2/token",
                json={
                    "client_id": settings.SQUARE_OAUTH_APPLICATION_ID,
                    "client_secret": settings.SQUARE_OAUTH_APPLICATION_SECRET,
                    "code": code,
                    "grant_type": "authorization_code",
                },
                headers={
                    "Square-Version": "2024-11-20",
                    "Content-Type": "application/json",
                },
            )
        data = resp.json()
        if resp.status_code != 200 or "access_token" not in data:
            errors = data.get("errors") or []
            detail = errors[0].get("detail") if errors else "OAuth code exchange failed"
            logger.error(
                "Square OAuth exchange failed",
                org_id=org_id, status=resp.status_code, errors=errors,
            )
            raise ValueError(detail)

        access_token = data["access_token"]
        refresh_token = data.get("refresh_token")
        merchant_id = data.get("merchant_id")
        expires_at_str = data.get("expires_at")  # ISO 8601
        expires_at = (
            datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            if expires_at_str else datetime.now(timezone.utc) + timedelta(days=30)
        )

        # Pick a default location — the first ACTIVE one. Studios can
        # change this later from the connect settings page.
        location_id = await self._pick_default_location(access_token)

        async with get_global_db() as db:
            enc_access = await encrypt_credential(db, access_token)
            enc_refresh = await encrypt_credential(db, refresh_token) if refresh_token else None
            await db.execute(
                """
                UPDATE af_global.organizations
                SET square_merchant_id = $2,
                    square_access_token_encrypted = $3,
                    square_refresh_token_encrypted = $4,
                    square_token_expires_at = $5,
                    square_location_id = $6,
                    billing_provider = 'square',
                    updated_at = NOW()
                WHERE id = $1
                """,
                org_id, merchant_id, enc_access, enc_refresh,
                expires_at, location_id,
            )

        logger.info(
            "Square OAuth completed",
            org_id=org_id, merchant_id=merchant_id, location_id=location_id,
        )
        return {
            "organization_id": org_id,
            "merchant_id": merchant_id,
            "location_id": location_id,
            "billing_provider": "square",
        }

    async def _pick_default_location(self, access_token: str) -> Optional[str]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{_square_base()}/v2/locations",
                    headers={
                        "Square-Version": "2024-11-20",
                        "Authorization": f"Bearer {access_token}",
                    },
                )
            data = resp.json()
            locations = data.get("locations") or []
            for loc in locations:
                if (loc.get("status") or "").upper() == "ACTIVE":
                    return loc["id"]
            return locations[0]["id"] if locations else None
        except Exception:
            logger.exception("Failed to pick default Square location")
            return None

    # ── Refresh / fetch decrypted access token ─────────────────────────

    async def get_merchant_access_token(self, organization_id: str) -> Optional[str]:
        """Return a usable access token for the org, refreshing if it
        expires within the buffer window. Returns None if the org has
        no Square credentials at all (billing_provider != 'square').

        Decrypted-token cache (60s TTL) bypasses pgp_sym_decrypt on the
        hot path; refresh + disconnect both invalidate the cache.
        """
        # Cache hit path
        cached = _token_cache.get(organization_id)
        if cached:
            token, exp_monotonic = cached
            if exp_monotonic > time.monotonic():
                return token
            _token_cache.pop(organization_id, None)

        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT square_access_token_encrypted,
                       square_refresh_token_encrypted,
                       square_token_expires_at
                FROM af_global.organizations
                WHERE id = $1
                """,
                organization_id,
            )
            if not row or not row["square_access_token_encrypted"]:
                return None

            expires_at = row["square_token_expires_at"]
            if expires_at and expires_at <= datetime.now(timezone.utc) + _refresh_buffer():
                # Time to refresh.
                if not row["square_refresh_token_encrypted"]:
                    logger.warning(
                        "Square access token expiring but no refresh token",
                        org_id=organization_id,
                    )
                    return None
                refresh_token = await decrypt_credential(
                    db, row["square_refresh_token_encrypted"],
                )
                new_tokens = await self._refresh_tokens(refresh_token)
                if not new_tokens:
                    return None
                enc_access = await encrypt_credential(db, new_tokens["access_token"])
                enc_refresh = await encrypt_credential(
                    db, new_tokens.get("refresh_token") or refresh_token,
                )
                new_expires = new_tokens["expires_at"]
                await db.execute(
                    """
                    UPDATE af_global.organizations
                    SET square_access_token_encrypted = $2,
                        square_refresh_token_encrypted = $3,
                        square_token_expires_at = $4,
                        updated_at = NOW()
                    WHERE id = $1
                    """,
                    organization_id, enc_access, enc_refresh, new_expires,
                )
                _token_cache[organization_id] = (
                    new_tokens["access_token"],
                    time.monotonic() + _TOKEN_CACHE_TTL_SECS,
                )
                return new_tokens["access_token"]

            decrypted = await decrypt_credential(db, row["square_access_token_encrypted"])
            _token_cache[organization_id] = (
                decrypted, time.monotonic() + _TOKEN_CACHE_TTL_SECS,
            )
            return decrypted

    async def _refresh_tokens(self, refresh_token: str) -> Optional[dict]:
        if not settings.SQUARE_OAUTH_APPLICATION_SECRET:
            return None
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{_square_base()}/oauth2/token",
                json={
                    "client_id": settings.SQUARE_OAUTH_APPLICATION_ID,
                    "client_secret": settings.SQUARE_OAUTH_APPLICATION_SECRET,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                headers={
                    "Square-Version": "2024-11-20",
                    "Content-Type": "application/json",
                },
            )
        data = resp.json()
        if resp.status_code != 200 or "access_token" not in data:
            logger.error(
                "Square OAuth refresh failed",
                status=resp.status_code, errors=data.get("errors"),
            )
            return None
        expires_at = (
            datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
            if data.get("expires_at")
            else datetime.now(timezone.utc) + timedelta(days=30)
        )
        return {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token"),
            "expires_at": expires_at,
        }

    # ── Nightly Celery refresh sweep (Phase 1 of token health) ─────────

    async def refresh_expiring_tokens(self) -> int:
        """Refresh every org whose access token expires within the
        buffer window. Returns the count refreshed. Called from a
        nightly Celery beat task."""
        async with get_global_db() as db:
            rows = await db.fetch(
                """
                SELECT id FROM af_global.organizations
                WHERE billing_provider = 'square'
                  AND square_access_token_encrypted IS NOT NULL
                  AND square_token_expires_at <= NOW() + INTERVAL '7 days'
                """
            )
        refreshed = 0
        for r in rows:
            try:
                token = await self.get_merchant_access_token(str(r["id"]))
                if token:
                    refreshed += 1
            except Exception:
                logger.exception("Token refresh failed", org_id=str(r["id"]))
        return refreshed

    # ── Disconnect / revoke ────────────────────────────────────────────

    async def disconnect(self, organization_id: str) -> dict:
        """Revoke Square access and clear the columns. Flips
        billing_provider back to 'stripe'. Best-effort on Square's
        revoke endpoint — even if Square fails, we clear local state
        because the owner explicitly asked to disconnect."""
        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT square_access_token_encrypted, square_merchant_id
                FROM af_global.organizations WHERE id = $1
                """,
                organization_id,
            )
            access_token = None
            if row and row["square_access_token_encrypted"]:
                access_token = await decrypt_credential(
                    db, row["square_access_token_encrypted"],
                )

        # Best-effort revoke against Square's OAuth API.
        if access_token and settings.SQUARE_OAUTH_APPLICATION_SECRET:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    await client.post(
                        f"{_square_base()}/oauth2/revoke",
                        json={
                            "access_token": access_token,
                            "client_id": settings.SQUARE_OAUTH_APPLICATION_ID,
                        },
                        headers={
                            "Square-Version": "2024-11-20",
                            "Authorization": (
                                f"Client {settings.SQUARE_OAUTH_APPLICATION_SECRET}"
                            ),
                            "Content-Type": "application/json",
                        },
                    )
            except Exception:
                logger.exception("Square revoke call failed (continuing)")

        async with get_global_db() as db:
            await db.execute(
                """
                UPDATE af_global.organizations
                SET square_merchant_id = NULL,
                    square_access_token_encrypted = NULL,
                    square_refresh_token_encrypted = NULL,
                    square_token_expires_at = NULL,
                    square_location_id = NULL,
                    square_subscription_id = NULL,
                    billing_provider = 'stripe',
                    updated_at = NOW()
                WHERE id = $1
                """,
                organization_id,
            )
        _cache_invalidate(organization_id)
        logger.info("Square disconnected", org_id=organization_id)
        return {"organization_id": organization_id, "billing_provider": "stripe"}

    # ── Status (for the connect-settings UI) ───────────────────────────

    async def get_status(self, organization_id: str) -> dict:
        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT square_merchant_id, square_location_id,
                       square_token_expires_at, billing_provider
                FROM af_global.organizations WHERE id = $1
                """,
                organization_id,
            )
        if not row:
            return {"connected": False}
        return {
            "connected": bool(row["square_merchant_id"]),
            "merchant_id": row["square_merchant_id"],
            "location_id": row["square_location_id"],
            "token_expires_at": (
                row["square_token_expires_at"].isoformat()
                if row["square_token_expires_at"] else None
            ),
            "billing_provider": row["billing_provider"],
        }


square_oauth_service = SquareOAuthService()
