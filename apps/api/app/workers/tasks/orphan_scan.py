"""AuraFlow — Orphan Data Scan Task

Runs daily at 5 AM Pacific (12:00 UTC). Cheap integrity check over the
top 6 relationships where orphans have been known to accumulate.

Reports (does NOT delete) any counts > 0 to Sentry so a developer can
decide whether to clean them up. Scheduled cleanup lives in
nightly_cleanup.py — this task's job is just surveillance.

Relationships checked per tenant:
  1. bookings → class_sessions (orphaned if session deleted)
  2. bookings → member_memberships (orphaned if membership deleted)
  3. member_memberships → members (orphaned if member deleted)
  4. transactions → members (orphaned if member deleted)
  5. waiver_signatures → members (orphaned if member deleted)
  6. private_bookings → members (orphaned if member deleted)
"""
import asyncio

from app.core.logging import logger
from app.db.session import get_global_db, get_tenant_db
from app.core.tenant_context import set_tenant_context_from_schema, clear_tenant_context
from app.workers.celery_app import app


ORPHAN_CHECKS = [
    ("bookings", "class_session_id", "class_sessions"),
    ("bookings", "membership_id", "member_memberships"),
    ("member_memberships", "member_id", "members"),
    ("transactions", "member_id", "members"),
    ("waiver_signatures", "member_id", "members"),
    ("private_bookings", "member_id", "members"),
]


async def _scan_schema(schema: str) -> dict:
    summary = {"schema": schema, "orphans": []}
    await set_tenant_context_from_schema(schema)
    try:
        for child_table, fk_col, parent_table in ORPHAN_CHECKS:
            try:
                async with get_tenant_db(schema_override=schema) as db:
                    count = await db.fetchval(
                        f"""
                        SELECT COUNT(*) FROM {child_table} c
                        WHERE c.{fk_col} IS NOT NULL
                          AND NOT EXISTS (
                              SELECT 1 FROM {parent_table} p WHERE p.id = c.{fk_col}
                          )
                        """
                    )
                if count and count > 0:
                    summary["orphans"].append({
                        "child_table": child_table,
                        "fk_column": fk_col,
                        "parent_table": parent_table,
                        "count": count,
                    })
            except Exception as exc:
                # Table might not exist in this tenant schema (future
                # per-tenant features). Skip quietly.
                logger.debug(
                    "Orphan check skipped",
                    schema=schema,
                    child=child_table,
                    error=str(exc),
                )
    finally:
        clear_tenant_context()
    return summary


async def _scan_all() -> dict:
    async with get_global_db() as db:
        schemas = await db.fetch(
            "SELECT schema_name FROM af_global.organizations "
            "WHERE status IN ('active', 'trial')"
        )

    summary = {"tenants": [], "total_orphans": 0}
    for row in schemas:
        report = await _scan_schema(row["schema_name"])
        summary["tenants"].append(report)
        summary["total_orphans"] += sum(o["count"] for o in report["orphans"])

    return summary


@app.task(name="app.workers.tasks.orphan_scan.nightly_orphan_scan")
def nightly_orphan_scan():
    """Celery beat task — surface orphaned rows to Sentry for triage."""
    loop = asyncio.new_event_loop()
    try:
        summary = loop.run_until_complete(_scan_all())
        total = summary["total_orphans"]
        logger.info("Orphan scan complete", total_orphans=total)
        if total > 0:
            try:
                import sentry_sdk
                sentry_sdk.capture_message(
                    f"Orphan rows detected in nightly scan: {total} total across "
                    f"{sum(1 for t in summary['tenants'] if t['orphans'])} tenants",
                    level="warning",
                    extras=summary,
                )
            except Exception:
                pass
        return summary
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        loop.close()
