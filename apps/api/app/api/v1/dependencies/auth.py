"""AuraFlow — Auth dependencies for FastAPI."""
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.config import settings
from app.core.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # ── Session idle-timeout check ────────────────────────────────
    iat = payload.get("iat")
    if iat is not None:
        issued_at = datetime.fromtimestamp(iat, tz=timezone.utc)
        idle_limit = settings.SESSION_IDLE_TIMEOUT_MINUTES * 60
        elapsed = (datetime.now(timezone.utc) - issued_at).total_seconds()
        if elapsed > idle_limit:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired due to inactivity",
            )

    return payload
