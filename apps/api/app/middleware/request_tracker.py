"""AuraFlow — Request Tracker Middleware (Pure ASGI)

Increments Redis counters per request for traffic monitoring:
- Total request count per 5-min bucket
- Error count (5xx)
- Per-endpoint counts
- Status code distribution
- Response time tracking
- Failed auth tracking for brute force detection
"""
import json
import time
from datetime import datetime

from app.core.redis import get_redis


class RequestTrackerMiddleware:
    """Pure ASGI middleware for request metrics collection."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        start = time.time()
        status_code = 200
        original_send = send

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 200)
            await original_send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.time() - start) * 1000, 2)
            path = scope.get("path", "/")
            client = scope.get("client")
            ip = client[0] if client else "unknown"

            try:
                await self._record(path, status_code, duration_ms, ip)
            except Exception:
                pass  # Never let tracking break requests

    async def _record(self, path: str, status_code: int, duration_ms: float, ip: str):
        redis = await get_redis()

        now = datetime.utcnow()
        bucket_min = (now.minute // 5) * 5
        bucket = now.replace(minute=bucket_min, second=0, microsecond=0)
        bucket_key = f"traffic:{bucket.strftime('%Y%m%d%H%M')}"

        pipe = redis.pipeline()

        # Total requests
        pipe.hincrby(bucket_key, "total", 1)

        # Error count
        if status_code >= 500:
            pipe.hincrby(bucket_key, "errors", 1)

        # Status codes
        sc_key = f"{bucket_key}:status"
        pipe.hincrby(sc_key, str(status_code), 1)

        # Top endpoints (strip query string, normalize)
        ep = path.split("?")[0]
        ep_key = f"{bucket_key}:endpoints"
        pipe.hincrby(ep_key, ep, 1)

        # Track unique IPs
        ip_key = f"{bucket_key}:ips"
        pipe.sadd(ip_key, ip)

        # Response time (append to list, capped)
        rt_key = f"{bucket_key}:rt"
        pipe.rpush(rt_key, str(duration_ms))

        # Set TTL on all keys (10 min)
        for k in [bucket_key, sc_key, ep_key, ip_key, rt_key]:
            pipe.expire(k, 600)

        # Track failed auth for brute force detection
        if status_code == 401 and ("/login" in path or "/token" in path):
            pipe.incr(f"failed_login:{ip}")
            pipe.expire(f"failed_login:{ip}", 600)

        # Rate limit tracking
        if status_code == 429:
            pipe.incr(f"rate_limited:{ip}")
            pipe.expire(f"rate_limited:{ip}", 600)

        # Active user tracking (by IP as proxy)
        pipe.set(f"active_user:5m:{ip}", "1", ex=300)
        pipe.set(f"active_user:1h:{ip}", "1", ex=3600)
        pipe.set(f"active_user:24h:{ip}", "1", ex=86400)

        await pipe.execute()

        # Finalize aggregated JSON fields (done separately to keep pipeline clean)
        # Status codes
        status_data = await redis.hgetall(sc_key)
        status_dict = {}
        for k, v in status_data.items():
            key = k if isinstance(k, str) else k.decode()
            status_dict[key] = int(v if isinstance(v, str) else v.decode())
        await redis.hset(bucket_key, "status_codes", json.dumps(status_dict))

        # Endpoints
        ep_data = await redis.hgetall(ep_key)
        ep_dict = {}
        for k, v in ep_data.items():
            key = k if isinstance(k, str) else k.decode()
            ep_dict[key] = int(v if isinstance(v, str) else v.decode())
        # Keep only top 20
        top_20 = dict(sorted(ep_dict.items(), key=lambda x: x[1], reverse=True)[:20])
        await redis.hset(bucket_key, "top_endpoints", json.dumps(top_20))

        # Unique IPs count
        unique_ip_count = await redis.scard(ip_key)
        await redis.hset(bucket_key, "unique_ips", str(unique_ip_count))

        # Response times list
        rt_data = await redis.lrange(rt_key, 0, -1)
        rt_list = [float(v if isinstance(v, str) else v.decode()) for v in rt_data]
        await redis.hset(bucket_key, "response_times", json.dumps(rt_list[-500:]))
