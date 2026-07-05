"""AuraFlow — Redis connection."""
import asyncio
from typing import Optional
import redis.asyncio as aioredis
from app.core.config import settings

_redis = None
_redis_loop = None


async def get_redis() -> Optional[aioredis.Redis]:
    global _redis, _redis_loop
    current_loop = asyncio.get_running_loop()
    if _redis is not None and _redis_loop is not current_loop:
        try:
            await _redis.aclose()
        except Exception:
            pass
        _redis = None
    if _redis is None:
        try:
            _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=False)
            _redis_loop = current_loop
        except Exception:
            return None
    return _redis


async def get_redis_status() -> bool:
    r = await get_redis()
    if not r:
        return False
    try:
        await r.ping()
        return True
    except Exception:
        return False
