"""AuraFlow — Database Monitor Service

DB health checks, performance stats, table sizes, slow queries,
and integrity verification via pg_stat_* views.
"""
from app.core.logging import logger
from app.db.session import get_global_db


class DBMonitorService:

    async def get_health(self) -> dict:
        """Overall DB health: version, uptime, connections."""
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
            max_conns = await db.fetchval("SHOW max_connections")
            db_size = await db.fetchval(
                "SELECT pg_size_pretty(pg_database_size(current_database()))"
            )
            return {
                "version": version,
                "started_at": str(uptime["started_at"]) if uptime else None,
                "uptime": str(uptime["uptime"]) if uptime else None,
                "connections": dict(conns) if conns else {},
                "max_connections": int(max_conns),
                "database_size": db_size,
            }

    async def get_performance(self) -> dict:
        """Cache hit ratio, transaction rates, deadlocks."""
        async with get_global_db() as db:
            cache = await db.fetchrow("""
                SELECT
                    sum(blks_hit) AS hits,
                    sum(blks_read) AS reads,
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
            return {
                "cache_hit_ratio": float(cache["cache_hit_ratio"]) if cache else 0,
                "block_hits": cache["hits"] if cache else 0,
                "block_reads": cache["reads"] if cache else 0,
                "transactions": {
                    "committed": txn["xact_commit"] if txn else 0,
                    "rolled_back": txn["xact_rollback"] if txn else 0,
                    "conflicts": txn["conflicts"] if txn else 0,
                    "deadlocks": txn["deadlocks"] if txn else 0,
                },
                "temp_files": txn["temp_files"] if txn else 0,
                "temp_bytes": txn["temp_bytes"] if txn else 0,
            }

    async def get_table_sizes(self) -> list[dict]:
        """Table sizes across af_global and tenant schemas."""
        async with get_global_db() as db:
            rows = await db.fetch("""
                SELECT schemaname, relname AS tablename,
                       pg_size_pretty(pg_total_relation_size(schemaname || '.' || relname)) AS total_size,
                       pg_total_relation_size(schemaname || '.' || relname) AS total_bytes,
                       n_live_tup AS row_estimate
                FROM pg_stat_user_tables
                ORDER BY pg_total_relation_size(schemaname || '.' || relname) DESC
                LIMIT 50
            """)
            return [dict(r) for r in rows]

    async def get_active_connections(self) -> list[dict]:
        """Active connection details."""
        async with get_global_db() as db:
            rows = await db.fetch("""
                SELECT pid, usename, application_name, client_addr::text,
                       state, query, NOW() - state_change AS duration,
                       wait_event_type, wait_event
                FROM pg_stat_activity
                WHERE backend_type = 'client backend'
                  AND pid != pg_backend_pid()
                ORDER BY state_change DESC
                LIMIT 50
            """)
            return [
                {**dict(r), "duration": str(r["duration"])}
                for r in rows
            ]

    async def get_slow_queries(self) -> list[dict]:
        """Top slow queries from pg_stat_statements (if available)."""
        async with get_global_db() as db:
            # Check if pg_stat_statements is available
            ext = await db.fetchval(
                "SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements'"
            )
            if not ext:
                return []

            rows = await db.fetch("""
                SELECT query,
                       calls,
                       round(total_exec_time::numeric, 2) AS total_time_ms,
                       round(mean_exec_time::numeric, 2) AS avg_time_ms,
                       round(max_exec_time::numeric, 2) AS max_time_ms,
                       rows
                FROM pg_stat_statements
                WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
                ORDER BY mean_exec_time DESC
                LIMIT 20
            """)
            return [dict(r) for r in rows]

    async def run_integrity_check(self) -> dict:
        """Run ANALYZE and basic integrity checks."""
        async with get_global_db() as db:
            # Run ANALYZE on af_global tables
            await db.execute("ANALYZE")

            # Check for bloated tables (dead tuple ratio > 10%)
            bloated = await db.fetch("""
                SELECT schemaname, relname,
                       n_dead_tup, n_live_tup,
                       CASE WHEN n_live_tup = 0 THEN 0
                            ELSE round(n_dead_tup::numeric / n_live_tup * 100, 2)
                       END AS dead_ratio_pct
                FROM pg_stat_user_tables
                WHERE n_dead_tup > 100
                  AND n_live_tup > 0
                  AND (n_dead_tup::float / n_live_tup) > 0.1
                ORDER BY n_dead_tup DESC
                LIMIT 20
            """)

            # Check for invalid indexes
            invalid_idx = await db.fetch("""
                SELECT schemaname, tablename, indexname
                FROM pg_indexes
                WHERE indexdef IS NULL
                LIMIT 20
            """)

            # Sequence health
            seq_health = await db.fetch("""
                SELECT sequencename, last_value, max_value,
                       CASE WHEN max_value > 0
                            THEN round(last_value::numeric / max_value * 100, 2)
                            ELSE 0
                       END AS usage_pct
                FROM pg_sequences
                WHERE last_value IS NOT NULL
                ORDER BY usage_pct DESC
                LIMIT 10
            """)

            logger.info("Database integrity check completed")
            return {
                "analyzed": True,
                "bloated_tables": [dict(r) for r in bloated],
                "invalid_indexes": [dict(r) for r in invalid_idx],
                "sequence_health": [dict(r) for r in seq_health],
            }
