"""AuraFlow — JWT Security utilities."""
import hashlib, secrets, uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from jwt.exceptions import PyJWTError

from app.core.config import settings

# Re-export for use in dependencies/auth.py
JWTError = PyJWTError


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(data: dict) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {**data, "exp": expire, "iat": now},
        settings.APP_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.APP_SECRET, algorithms=[settings.JWT_ALGORITHM])

def _hash_user_agent(user_agent: str | None) -> str | None:
    """Stable fingerprint of a User-Agent string. SHA-256 hex[:40] — shorter
    than a full hash so joining across many tokens is cheap but still
    collision-resistant enough for device-binding purposes."""
    if not user_agent:
        return None
    return hashlib.sha256(user_agent.strip().encode()).hexdigest()[:40]


async def create_refresh_token(
    user_id: str,
    user_agent: str | None = None,
    ip: str | None = None,
) -> str:
    """Mint a refresh token. Records device fingerprint (UA hash + IP) at
    creation time so subsequent refreshes can detect token theft: if a
    refresh shows up from a completely different device, reject it and
    revoke the token.

    user_agent and ip are optional so existing call sites that don't pass
    them still work; binding simply won't be enforced for tokens minted
    without the fingerprint.
    """
    token = secrets.token_urlsafe(64)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    ua_hash = _hash_user_agent(user_agent)
    from app.db.session import get_global_db
    async with get_global_db() as db:
        await db.execute(
            """INSERT INTO af_global.refresh_tokens
                 (user_id, token_hash, expires_at, user_agent_hash, ip_first_seen, last_refresh_at)
               VALUES ($1, $2, $3, $4, $5::inet, NOW())""",
            user_id, token_hash, expire, ua_hash, ip,
        )
        # Clean up revoked and expired tokens for this user
        await db.execute(
            """DELETE FROM af_global.refresh_tokens
               WHERE user_id = $1 AND (revoked_at IS NOT NULL OR expires_at < NOW())""",
            user_id,
        )
    return token
