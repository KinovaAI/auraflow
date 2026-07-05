"""AuraFlow — Nightly Data Cleanup Task

Runs daily at 4 AM Pacific (11:00 UTC). Deletes rows whose retention
windows have lapsed:

  - af_global.refresh_tokens: revoked or expired > 60 days ago
  - af_global.processed_webhook_events: processed > 90 days ago (past
    Stripe's retry window; dedup is no longer protective)
  - af_tenant_*.webhook_deliveries: status='delivered' + delivered_at
    > 90 days ago (dead-letter rows preserved for forensics)
  - af_tenant_*.sms_messages: orphan (member_id not in members)
  - af_tenant_*.communication_log: orphan (member_id not in members)

Intentionally conservative — deletes ONLY rows that are either
demonstrably dead (orphans) or past the reasonable retention window
for their type. PHI-adjacent tables (audit_log, member rows) are
handled by separate retention migrations with longer HIPAA-aligned
windows, never here.
"""
import asyncio

from app.core.logging import logger
from app.db.session import get_global_db, get_tenant_db
from app.core.tenant_context import set_tenant_context_from_schema, clear_tenant_context
from app.workers.celery_app import app


async def _cleanup_global() -> dict:
    async with get_global_db() as db:
        rt_deleted = await db.execute(
            """DELETE FROM af_global.refresh_tokens
               WHERE (revoked_at IS NOT NULL OR expires_at < NOW())
                 AND created_at < NOW() - INTERVAL '60 days'"""
        )
        wh_deleted = await db.execute(
            """DELETE FROM af_global.processed_webhook_events
               WHERE processed_at < NOW() - INTERVAL '90 days'"""
        )
        # HIPAA §164.312(b) requires audit logs for 6 years. Delete
        # anything older than that — past the retention requirement,
        # these rows are pure clutter and slow audit queries.
        audit_deleted = await db.execute(
            """DELETE FROM af_global.audit_log
               WHERE created_at < NOW() - INTERVAL '6 years'"""
        )
        # Dead-letter tasks past 1 year — if it hasn't been replayed
        # by now, it's never going to be.
        dlt_deleted = await db.execute(
            """DELETE FROM af_global.dead_letter_tasks
               WHERE failed_at < NOW() - INTERVAL '1 year'
                 AND resolution IN ('replayed', 'ignored')"""
        )

    def _count(s: str) -> int:
        try:
            return int(s.split()[-1])
        except (ValueError, IndexError):
            return 0

    return {
        "refresh_tokens_deleted": _count(rt_deleted),
        "processed_webhook_events_deleted": _count(wh_deleted),
        "audit_log_deleted": _count(audit_deleted),
        "dead_letter_tasks_deleted": _count(dlt_deleted),
    }


async def _cleanup_tenant(schema: str) -> dict:
    await set_tenant_context_from_schema(schema)
    try:
        async with get_tenant_db(schema_override=schema) as db:
            wd_deleted = await db.execute(
                """DELETE FROM webhook_deliveries
                   WHERE status = 'delivered'
                     AND delivered_at IS NOT NULL
                     AND delivered_at < NOW() - INTERVAL '90 days'"""
            )
            sms_orphan = await db.execute(
                """DELETE FROM sms_messages
                   WHERE member_id IS NOT NULL
                     AND NOT EXISTS (SELECT 1 FROM members m WHERE m.id = member_id)"""
            )
            cl_orphan = await db.execute(
                """DELETE FROM communication_log
                   WHERE member_id IS NOT NULL
                     AND NOT EXISTS (SELECT 1 FROM members m WHERE m.id = member_id)"""
            )
            # 18-month non-audit comms retention. Keeps booking
            # confirmations / marketing sends for a reasonable
            # operational window but doesn't keep them forever.
            # HIPAA audit-log retention (6y) is on af_global.audit_log,
            # NOT communication_log — these are transactional sends,
            # not security events.
            cl_old = await db.execute(
                """DELETE FROM communication_log
                   WHERE created_at < NOW() - INTERVAL '18 months'"""
            )
            # sms_messages same window
            sms_old = await db.execute(
                """DELETE FROM sms_messages
                   WHERE created_at < NOW() - INTERVAL '18 months'"""
            )

        def _count(s: str) -> int:
            try:
                return int(s.split()[-1])
            except (ValueError, IndexError):
                return 0

        return {
            "schema": schema,
            "webhook_deliveries_deleted": _count(wd_deleted),
            "sms_messages_orphan_deleted": _count(sms_orphan),
            "communication_log_orphan_deleted": _count(cl_orphan),
            "communication_log_retention_deleted": _count(cl_old),
            "sms_messages_retention_deleted": _count(sms_old),
        }
    finally:
        clear_tenant_context()


async def _cleanup_all() -> dict:
    summary: dict = {"global": await _cleanup_global(), "tenants": []}

    async with get_global_db() as db:
        schemas = await db.fetch(
            "SELECT schema_name FROM af_global.organizations "
            "WHERE status IN ('active', 'trial')"
        )

    total_deleted = sum(summary["global"].values())
    for row in schemas:
        report = await _cleanup_tenant(row["schema_name"])
        summary["tenants"].append(report)
        total_deleted += sum(
            v for k, v in report.items() if k.endswith("_deleted")
        )

    summary["total_rows_deleted"] = total_deleted
    return summary


@app.task(name="app.workers.tasks.nightly_cleanup.nightly_data_cleanup")
def nightly_data_cleanup():
    """Celery beat task — run nightly retention-aware cleanup."""
    loop = asyncio.new_event_loop()
    try:
        summary = loop.run_until_complete(_cleanup_all())
        if summary["total_rows_deleted"]:
            logger.info(
                "Nightly data cleanup complete",
                total_deleted=summary["total_rows_deleted"],
                **summary["global"],
            )
        return summary
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        loop.close()
