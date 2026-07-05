"""AuraFlow — Redis-based sliding-window rate limiter for external API keys.

Uses a simple INCR + EXPIRE pattern with a 60-second window.
Each API key gets its own Redis counter keyed by api_key_id.
"""
import time

from app.core.redis import get_redis
from app.core.logging import logger


WINDOW_SECONDS = 60


async def check_rate_limit(
    api_key_id: str,
    limit_rpm: int,
) -> tuple[bool, int, int]:
    """Check whether the given API key is within its rate limit.

    Args:
        api_key_id: Unique identifier for the API key.
        limit_rpm:  Maximum requests allowed per minute.

    Returns:
        (allowed, remaining, reset_at)
        - allowed:   True if the request should proceed.
        - remaining: How many requests are left in the current window.
        - reset_at:  Unix timestamp when the window resets.
    """
    redis = await get_redis()
    if redis is None:
        # If Redis is unavailable, fail open (allow the request)
        logger.warning("rate_limiter_redis_unavailable", api_key_id=api_key_id)
        return True, limit_rpm, int(time.time()) + WINDOW_SECONDS

    cache_key = f"ratelimit:apikey:{api_key_id}"

    # Atomic increment
    current = await redis.incr(cache_key)

    if current == 1:
        # First request in window — set expiry
        await redis.expire(cache_key, WINDOW_SECONDS)

    # Determine TTL for reset_at
    ttl = await redis.ttl(cache_key)
    if ttl < 0:
        # Key exists without expiry (edge case) — fix it
        await redis.expire(cache_key, WINDOW_SECONDS)
        ttl = WINDOW_SECONDS

    reset_at = int(time.time()) + ttl
    remaining = max(0, limit_rpm - current)
    allowed = current <= limit_rpm

    if not allowed:
        logger.warning(
            "rate_limit_exceeded",
            api_key_id=api_key_id,
            current=current,
            limit=limit_rpm,
        )

    return allowed, remaining, reset_at
