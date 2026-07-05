"""AuraFlow — System Health Service

Aggregates DB, server (OS), and Redis health into a single snapshot.
"""
import os
import platform as plat
from datetime import datetime, timezone

import psutil

from app.core.logging import logger
from app.core.redis import get_redis
from app.db.session import get_global_db


class SystemHealthService:

    async def get_system_health(self) -> dict:
        db_health = await self._db_health()
        server = self._server_health()
        redis = await self._redis_health()

        services = {
            "api": "healthy",
            "database": "healthy" if db_health.get("version") else "unhealthy",
            "redis": "healthy" if redis.get("connected") else "unhealthy",
            "celery": await self._celery_health(),
        }

        return {
            "database": db_health,
            "server": server,
            "redis": redis,
            "services": services,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }

    async def get_active_queries(self) -> list[dict]:
        async with get_global_db() as db:
            rows = await db.fetch("""
                SELECT pid, usename, application_name, client_addr::text,
                       state, query,
                       NOW() - state_change AS duration,
                       EXTRACT(EPOCH FROM (NOW() - state_change)) AS duration_secs,
                       wait_event_type, wait_event
                FROM pg_stat_activity
                WHERE backend_type = 'client backend'
                  AND pid != pg_backend_pid()
                ORDER BY state_change DESC
                LIMIT 50
            """)
            results = []
            for r in rows:
                secs = float(r["duration_secs"] or 0)
                if secs > 10:
                    severity = "critical"
                elif secs > 1:
                    severity = "warning"
                else:
                    severity = "healthy"
                results.append({
                    **dict(r),
                    "duration": str(r["duration"]),
                    "duration_secs": round(secs, 2),
                    "severity": severity,
                })
            return results

    # ── Private helpers ───────────────────────────────────────────────

    async def _db_health(self) -> dict:
        try:
            async with get_global_db() as db:
                version = await db.fetchval("SELECT version()")
                uptime = await db.fetchrow("""
                    SELECT pg_postmaster_start_time() AS started_at,
                           NOW() - pg_postmaster_start_time() AS uptime
                """)
                conns = await db.fetchrow("""
                    SELECT count(*) AS total,
                           count(*) FILTER (WHERE state = 'active') AS active,
                           count(*) FILTER (WHERE state = 'idle') AS idle,
                           count(*) FILTER (WHERE state = 'idle in transaction') AS idle_in_tx
                    FROM pg_stat_activity
                    WHERE backend_type = 'client backend'
                """)
                max_conns = int(await db.fetchval("SHOW max_connections"))
                db_size = await db.fetchval(
                    "SELECT pg_size_pretty(pg_database_size(current_database()))"
                )
                db_size_bytes = await db.fetchval(
                    "SELECT pg_database_size(current_database())"
                )
                cache = await db.fetchrow("""
                    SELECT
                        CASE WHEN sum(blks_hit) + sum(blks_read) = 0 THEN 0
                             ELSE round(sum(blks_hit)::numeric / (sum(blks_hit) + sum(blks_read)) * 100, 2)
                        END AS cache_hit_ratio
                    FROM pg_stat_database
                    WHERE datname = current_database()
                """)
                txn = await db.fetchrow("""
                    SELECT xact_commit, xact_rollback, conflicts, deadlocks,
                           temp_files, temp_bytes
                    FROM pg_stat_database
                    WHERE datname = current_database()
                """)
                repl = await db.fetch("""
                    SELECT client_addr::text, state, sent_lsn::text, write_lsn::text
                    FROM pg_stat_replication
                """)

                total_conns = conns["total"] if conns else 0
                return {
                    "version": version,
                    "started_at": str(uptime["started_at"]) if uptime else None,
                    "uptime": str(uptime["uptime"]) if uptime else None,
                    "connections": dict(conns) if conns else {},
                    "max_connections": max_conns,
                    "connection_utilization_pct": round(total_conns / max(max_conns, 1) * 100, 1),
                    "database_size": db_size,
                    "database_size_bytes": db_size_bytes,
                    "cache_hit_ratio": float(cache["cache_hit_ratio"]) if cache else 0,
                    "transactions": {
                        "committed": txn["xact_commit"] if txn else 0,
                        "rolled_back": txn["xact_rollback"] if txn else 0,
                        "conflicts": txn["conflicts"] if txn else 0,
                        "deadlocks": txn["deadlocks"] if txn else 0,
                    } if txn else {},
                    "temp_files": txn["temp_files"] if txn else 0,
                    "replication": [dict(r) for r in repl] if repl else [],
                }
        except Exception as e:
            logger.error(f"DB health check failed: {e}")
            return {"error": str(e)}

    def _server_health(self) -> dict:
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        proc = psutil.Process()

        uptime_secs = (datetime.now() - datetime.fromtimestamp(proc.create_time())).total_seconds()
        hours = int(uptime_secs // 3600)
        minutes = int((uptime_secs % 3600) // 60)

        return {
            "hostname": plat.node(),
            "platform": f"{plat.system()} {plat.release()}",
            "python_version": plat.python_version(),
            "cpu_count": psutil.cpu_count(),
            "cpu_usage_pct": psutil.cpu_percent(interval=0.1),
            "memory": {
                "total_gb": round(mem.total / (1024**3), 2),
                "used_gb": round(mem.used / (1024**3), 2),
                "available_gb": round(mem.available / (1024**3), 2),
                "usage_pct": mem.percent,
            },
            "disk": {
                "total_gb": round(disk.total / (1024**3), 2),
                "used_gb": round(disk.used / (1024**3), 2),
                "free_gb": round(disk.free / (1024**3), 2),
                "usage_pct": disk.percent,
            },
            "load_average": list(os.getloadavg()),
            "process_uptime": f"{hours}h {minutes}m",
            "process_uptime_seconds": round(uptime_secs),
        }

    async def _redis_health(self) -> dict:
        try:
            r = await get_redis()
            info = await r.info()
            return {
                "connected": True,
                "version": info.get("redis_version"),
                "memory_used_mb": round(info.get("used_memory", 0) / (1024**2), 1),
                "memory_max_mb": round(info.get("maxmemory", 0) / (1024**2), 1) if info.get("maxmemory") else None,
                "connected_clients": info.get("connected_clients"),
                "uptime_seconds": info.get("uptime_in_seconds"),
            }
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return {"connected": False, "error": str(e)}

    async def _celery_health(self) -> str:
        try:
            from app.workers.celery_app import app as celery_app
            inspector = celery_app.control.inspect(timeout=2)
            ping = inspector.ping()
            return "healthy" if ping else "unknown"
        except Exception:
            return "unknown"
