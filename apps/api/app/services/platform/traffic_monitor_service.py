"""AuraFlow — Traffic Monitor Service

Aggregates Redis request counters into platform_request_metrics,
provides traffic overview, active users, top endpoints, and geo data.
"""
import json
from datetime import datetime, timedelta

from app.core.logging import logger
from app.db.session import get_global_db
from app.core.redis import get_redis


class TrafficMonitorService:

    async def aggregate_metrics(self) -> dict | None:
        """Flush Redis counters for the current 5-minute bucket into DB."""
        redis = await get_redis()
        now = datetime.utcnow()
        # Round down to 5-min bucket
        bucket_min = (now.minute // 5) * 5
        period_start = now.replace(minute=bucket_min, second=0, microsecond=0)
        bucket_key = f"traffic:{period_start.strftime('%Y%m%d%H%M')}"

        data = await redis.hgetall(bucket_key)
        if not data:
            return None

        # Decode Redis hash values
        decoded = {}
        for k, v in data.items():
            key = k if isinstance(k, str) else k.decode()
            val = v if isinstance(v, str) else v.decode()
            decoded[key] = val

        total_requests = int(decoded.get("total", 0))
        error_count = int(decoded.get("errors", 0))
        unique_ips = int(decoded.get("unique_ips", 0))

        # Parse response times for percentiles
        times_raw = decoded.get("response_times", "[]")
        try:
            times = json.loads(times_raw)
        except (json.JSONDecodeError, TypeError):
            times = []

        if times:
            times.sort()
            avg_ms = round(sum(times) / len(times), 2)
            p95_ms = round(times[int(len(times) * 0.95)] if len(times) > 1 else times[0], 2)
            p99_ms = round(times[int(len(times) * 0.99)] if len(times) > 1 else times[0], 2)
        else:
            avg_ms = p95_ms = p99_ms = 0

        top_endpoints_raw = decoded.get("top_endpoints", "{}")
        status_codes_raw = decoded.get("status_codes", "{}")
        geo_data_raw = decoded.get("geo_data", "{}")

        try:
            top_endpoints = json.loads(top_endpoints_raw)
        except (json.JSONDecodeError, TypeError):
            top_endpoints = {}

        try:
            status_codes = json.loads(status_codes_raw)
        except (json.JSONDecodeError, TypeError):
            status_codes = {}

        try:
            geo_data = json.loads(geo_data_raw)
        except (json.JSONDecodeError, TypeError):
            geo_data = {}

        async with get_global_db() as db:
            row = await db.fetchrow("""
                INSERT INTO af_global.platform_request_metrics
                    (period_start, total_requests, avg_response_ms, p95_response_ms,
                     p99_response_ms, error_count, unique_ips, top_endpoints,
                     status_codes, geo_data)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10::jsonb)
                ON CONFLICT (period_start) DO UPDATE SET
                    total_requests = EXCLUDED.total_requests,
                    avg_response_ms = EXCLUDED.avg_response_ms,
                    p95_response_ms = EXCLUDED.p95_response_ms,
                    p99_response_ms = EXCLUDED.p99_response_ms,
                    error_count = EXCLUDED.error_count,
                    unique_ips = EXCLUDED.unique_ips,
                    top_endpoints = EXCLUDED.top_endpoints,
                    status_codes = EXCLUDED.status_codes,
                    geo_data = EXCLUDED.geo_data
                RETURNING *
            """, period_start, total_requests, avg_ms, p95_ms, p99_ms,
                error_count, unique_ips,
                json.dumps(top_endpoints), json.dumps(status_codes), json.dumps(geo_data))

        # Expire old Redis key
        await redis.expire(bucket_key, 600)
        logger.debug(f"Aggregated traffic metrics for {period_start}")
        return dict(row) if row else None

    async def get_traffic_overview(self, hours: int = 24) -> list[dict]:
        """Time-series traffic data for the last N hours."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        async with get_global_db() as db:
            rows = await db.fetch("""
                SELECT period_start, total_requests, avg_response_ms,
                       p95_response_ms, error_count, unique_ips
                FROM af_global.platform_request_metrics
                WHERE period_start >= $1
                ORDER BY period_start ASC
            """, cutoff)
            return [dict(r) for r in rows]

    async def get_active_users(self) -> dict:
        """Count active users from Redis session keys."""
        redis = await get_redis()
        # Count keys matching active session pattern
        keys_5m = await redis.keys("active_user:5m:*")
        keys_1h = await redis.keys("active_user:1h:*")
        keys_24h = await redis.keys("active_user:24h:*")
        return {
            "last_5_minutes": len(keys_5m),
            "last_1_hour": len(keys_1h),
            "last_24_hours": len(keys_24h),
        }

    async def get_top_endpoints(self, hours: int = 24) -> list[dict]:
        """Aggregate top endpoints across recent metrics."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        async with get_global_db() as db:
            rows = await db.fetch("""
                SELECT top_endpoints
                FROM af_global.platform_request_metrics
                WHERE period_start >= $1
            """, cutoff)

        # Aggregate across all periods
        endpoint_counts: dict[str, int] = {}
        for row in rows:
            eps = row["top_endpoints"]
            if isinstance(eps, str):
                try:
                    eps = json.loads(eps)
                except (json.JSONDecodeError, TypeError):
                    continue
            if isinstance(eps, dict):
                for ep, count in eps.items():
                    endpoint_counts[ep] = endpoint_counts.get(ep, 0) + int(count)

        sorted_eps = sorted(endpoint_counts.items(), key=lambda x: x[1], reverse=True)[:20]
        return [{"endpoint": ep, "requests": count} for ep, count in sorted_eps]

    async def get_geo_breakdown(self, hours: int = 24) -> list[dict]:
        """Aggregate geo data across recent metrics."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        async with get_global_db() as db:
            rows = await db.fetch("""
                SELECT geo_data
                FROM af_global.platform_request_metrics
                WHERE period_start >= $1
            """, cutoff)

        geo_counts: dict[str, int] = {}
        for row in rows:
            geo = row["geo_data"]
            if isinstance(geo, str):
                try:
                    geo = json.loads(geo)
                except (json.JSONDecodeError, TypeError):
                    continue
            if isinstance(geo, dict):
                for region, count in geo.items():
                    geo_counts[region] = geo_counts.get(region, 0) + int(count)

        sorted_geo = sorted(geo_counts.items(), key=lambda x: x[1], reverse=True)[:30]
        return [{"region": region, "requests": count} for region, count in sorted_geo]
