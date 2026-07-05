"""AuraFlow — Security Service

Intrusion detection: brute force, rate limit abuse, unusual API patterns,
error spikes. Records security events and sends alerts to platform admins.
"""
import json
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_global_db
from app.core.redis import get_redis


class SecurityService:

    # ── Event Recording ──────────────────────────────────────────────

    async def record_event(
        self,
        event_type: str,
        severity: str = "low",
        source_ip: str | None = None,
        user_agent: str | None = None,
        endpoint: str | None = None,
        details: dict | None = None,
    ) -> dict:
        async with get_global_db() as db:
            row = await db.fetchrow("""
                INSERT INTO af_global.platform_security_events
                    (event_type, severity, source_ip, user_agent, endpoint, details)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                RETURNING *
            """, event_type, severity, source_ip, user_agent, endpoint,
                json.dumps(details or {}))
            return dict(row)

    async def list_events(
        self,
        event_type: str | None = None,
        severity: str | None = None,
        acknowledged: bool | None = None,
        limit: int = 100,
    ) -> list[dict]:
        async with get_global_db() as db:
            conditions = []
            params: list = []
            idx = 1

            if event_type:
                conditions.append(f"event_type = ${idx}")
                params.append(event_type)
                idx += 1
            if severity:
                conditions.append(f"severity = ${idx}")
                params.append(severity)
                idx += 1
            if acknowledged is not None:
                conditions.append(f"acknowledged = ${idx}")
                params.append(acknowledged)
                idx += 1

            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            params.append(limit)

            rows = await db.fetch(f"""
                SELECT * FROM af_global.platform_security_events
                {where}
                ORDER BY created_at DESC
                LIMIT ${idx}
            """, *params)
            return [dict(r) for r in rows]

    async def acknowledge_event(self, event_id: str, admin_id: str) -> dict | None:
        async with get_global_db() as db:
            row = await db.fetchrow("""
                UPDATE af_global.platform_security_events
                SET acknowledged = TRUE, acknowledged_at = NOW(), acknowledged_by = $2
                WHERE id = $1
                RETURNING *
            """, event_id, admin_id)
            return dict(row) if row else None

    async def get_summary(self, hours: int = 24) -> dict:
        """Summary of security events in the last N hours."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        async with get_global_db() as db:
            by_type = await db.fetch("""
                SELECT event_type, count(*) AS count
                FROM af_global.platform_security_events
                WHERE created_at >= $1
                GROUP BY event_type
                ORDER BY count DESC
            """, cutoff)
            by_severity = await db.fetch("""
                SELECT severity, count(*) AS count
                FROM af_global.platform_security_events
                WHERE created_at >= $1
                GROUP BY severity
                ORDER BY count DESC
            """, cutoff)
            unacked = await db.fetchval("""
                SELECT count(*)
                FROM af_global.platform_security_events
                WHERE acknowledged = FALSE AND created_at >= $1
            """, cutoff)
            total = await db.fetchval("""
                SELECT count(*)
                FROM af_global.platform_security_events
                WHERE created_at >= $1
            """, cutoff)

            return {
                "total_events": total,
                "unacknowledged": unacked,
                "by_type": [dict(r) for r in by_type],
                "by_severity": [dict(r) for r in by_severity],
                "period_hours": hours,
            }

    # ── Detection Scans ──────────────────────────────────────────────

    async def detect_brute_force(self) -> list[dict]:
        """Detect IPs with >10 failed logins in last 10 minutes."""
        redis = await get_redis()
        events = []

        # Scan Redis for failed login counters
        keys = []
        async for key in redis.scan_iter(match="failed_login:*"):
            keys.append(key)
        for key in keys:
            key_str = key if isinstance(key, str) else key.decode()
            ip = key_str.split(":", 1)[1] if ":" in key_str else key_str
            count = await redis.get(key)
            count_int = int(count) if count else 0

            if count_int > 10:
                event = await self.record_event(
                    event_type="brute_force",
                    severity="high",
                    source_ip=ip,
                    details={"failed_attempts": count_int, "window_minutes": 10},
                )
                events.append(event)
                logger.warning(f"Brute force detected from {ip}: {count_int} failed logins")

        return events

    async def detect_rate_limit_abuse(self) -> list[dict]:
        """Detect IPs hitting rate limits excessively."""
        redis = await get_redis()
        events = []

        keys = []
        async for key in redis.scan_iter(match="rate_limited:*"):
            keys.append(key)
        for key in keys:
            key_str = key if isinstance(key, str) else key.decode()
            ip = key_str.split(":", 1)[1] if ":" in key_str else key_str
            count = await redis.get(key)
            count_int = int(count) if count else 0

            if count_int > 50:
                event = await self.record_event(
                    event_type="rate_limit",
                    severity="medium",
                    source_ip=ip,
                    details={"rate_limit_hits": count_int},
                )
                events.append(event)

        return events

    async def detect_error_spikes(self) -> list[dict]:
        """Detect if >10% of requests in last 5 min resulted in 5xx errors."""
        events = []
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)

        async with get_global_db() as db:
            row = await db.fetchrow("""
                SELECT
                    SUM(total_requests) AS total,
                    SUM(error_count) AS errors
                FROM af_global.platform_request_metrics
                WHERE period_start >= $1
            """, cutoff)

        if row and row["total"] and row["total"] > 50:
            error_rate = row["errors"] / row["total"]
            if error_rate > 0.10:
                event = await self.record_event(
                    event_type="error_spike",
                    severity="critical",
                    details={
                        "total_requests": row["total"],
                        "error_count": row["errors"],
                        "error_rate": round(error_rate * 100, 2),
                    },
                )
                events.append(event)
                logger.warning(f"Error spike detected: {error_rate*100:.1f}% error rate")

        return events

    async def run_security_scan(self) -> dict:
        """Run all detection checks."""
        brute = await self.detect_brute_force()
        rate = await self.detect_rate_limit_abuse()
        errors = await self.detect_error_spikes()
        total = len(brute) + len(rate) + len(errors)
        if total > 0:
            logger.info(f"Security scan found {total} new events")
        return {
            "brute_force_events": len(brute),
            "rate_limit_events": len(rate),
            "error_spike_events": len(errors),
            "total_new_events": total,
        }

    async def send_alerts(self) -> int:
        """Send email alerts for critical unacknowledged events in the last 15 min."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
        async with get_global_db() as db:
            rows = await db.fetch("""
                SELECT * FROM af_global.platform_security_events
                WHERE severity IN ('high', 'critical')
                  AND acknowledged = FALSE
                  AND created_at >= $1
                ORDER BY created_at DESC
            """, cutoff)

        if not rows:
            return 0

        # Send alert email
        try:
            from app.services.email.email_service import EmailService
            email_svc = EmailService()
            alert_lines = []
            for r in rows:
                alert_lines.append(
                    f"- [{r['severity'].upper()}] {r['event_type']} "
                    f"from {r['source_ip'] or 'unknown'} at {r['created_at']}"
                )

            body = (
                f"AuraFlow Security Alert\n\n"
                f"{len(rows)} security event(s) detected:\n\n"
                + "\n".join(alert_lines)
                + f"\n\nReview at {settings.APP_URL}/dashboard/platform/infrastructure"
            )

            await email_svc.send_email(
                to_email=settings.SENDGRID_FROM_EMAIL,
                subject=f"[AuraFlow Security] {len(rows)} alert(s) detected",
                html_content=body,
            )
            logger.info(f"Sent security alert email with {len(rows)} events")
        except Exception as e:
            logger.error(f"Failed to send security alert: {e}")

        return len(rows)
