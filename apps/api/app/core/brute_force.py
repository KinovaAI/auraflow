"""
AuraFlow — Brute-Force Login Lockout

Redis-backed fail counter keyed by email address. After 5 failures within
10 minutes, the email is locked for 15 minutes regardless of source IP
(slowapi handles per-IP rate limiting separately).

Separating email-level lockout from IP rate limits means a distributed
attacker spraying one password across many IPs still gets stopped at
the email level, and a legitimate user on a shared network isn't locked
out because one coworker fat-fingered their own password.
"""
from __future__ import annotations

from app.core.logging import logger


FAIL_WINDOW_SECONDS = 600   # 10 min window for counting failures
FAIL_THRESHOLD = 5          # failures within window → trigger lockout
LOCKOUT_SECONDS = 900       # 15 min lockout


async def is_locked(email: str) -> bool:
    """True if the email address is currently locked."""
    try:
        from app.core.redis import get_redis
        redis = await get_redis()
        if not redis:
            # If Redis is down, fail-open: reliability of the login path
            # matters more than this specific defense.
            return False
        key = f"bflock:locked:{email.lower()}"
        return bool(await redis.exists(key))
    except Exception as exc:
        logger.warning("Brute-force lockout check failed", error=str(exc))
        return False


async def register_failure(email: str) -> bool:
    """Record a failed login. Returns True if this failure tripped the
    lockout threshold (caller can log/alert accordingly)."""
    try:
        from app.core.redis import get_redis
        redis = await get_redis()
        if not redis:
            return False
        counter_key = f"bflock:fails:{email.lower()}"
        count = await redis.incr(counter_key)
        # INCR doesn't set TTL on existing key, so only set it on the first
        # failure in a window.
        if count == 1:
            await redis.expire(counter_key, FAIL_WINDOW_SECONDS)
        if count >= FAIL_THRESHOLD:
            lock_key = f"bflock:locked:{email.lower()}"
            await redis.set(lock_key, "1", ex=LOCKOUT_SECONDS)
            # Reset counter so that when lockout expires the next failure
            # starts a fresh window (otherwise 1 more wrong password
            # re-locks immediately).
            await redis.delete(counter_key)
            logger.warning(
                "Brute-force lockout triggered",
                email=email.lower(),
                window_seconds=FAIL_WINDOW_SECONDS,
                threshold=FAIL_THRESHOLD,
                lockout_seconds=LOCKOUT_SECONDS,
            )
            return True
    except Exception as exc:
        logger.warning("Brute-force counter increment failed", error=str(exc))
    return False


async def clear_failures(email: str) -> None:
    """Clear both the failure counter and any active lockout. Call after
    a successful login so legitimate users who mistyped earlier don't
    stay throttled."""
    try:
        from app.core.redis import get_redis
        redis = await get_redis()
        if not redis:
            return
        await redis.delete(
            f"bflock:fails:{email.lower()}",
            f"bflock:locked:{email.lower()}",
        )
    except Exception:
        pass
