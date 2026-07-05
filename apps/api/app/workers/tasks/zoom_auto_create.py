"""AuraFlow — Zoom Auto-Create Task

Runs daily via Celery Beat. Creates Zoom meetings for virtual class sessions
happening in the next 3 days that don't have a Zoom meeting yet.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from app.core.logging import logger
from app.core.tenant_context import set_tenant_context, clear_tenant_context
from app.db.session import get_tenant_db, get_global_db
from app.services.integrations.zoom_service import ZoomService
from app.workers.celery_app import app

zoom_svc = ZoomService()


async def _create_zoom_for_tenant(org_id: str, org_name: str, schema_name: str) -> int:
    """Create Zoom meetings for virtual sessions in the next 3 days."""
    set_tenant_context(organization_id=org_id, schema_name=schema_name, slug=schema_name.replace("af_tenant_", ""))
    created = 0

    try:
        now = datetime.now(timezone.utc)
        window_end = now + timedelta(days=3)

        async with get_tenant_db(schema_override=schema_name) as db:
            sessions = await db.fetch(
                """
                SELECT id, title, starts_at, ends_at
                FROM class_sessions
                WHERE is_virtual = TRUE
                  AND zoom_meeting_id IS NULL
                  AND starts_at BETWEEN $1 AND $2
                  AND status = 'scheduled'
                ORDER BY starts_at
                """,
                now, window_end,
            )

        for s in sessions:
            starts = s["starts_at"]
            if starts.tzinfo is None:
                starts = starts.replace(tzinfo=timezone.utc)
            from zoneinfo import ZoneInfo
            local = starts.astimezone(ZoneInfo("America/Los_Angeles"))

            duration = 60
            if s.get("ends_at"):
                ends = s["ends_at"]
                if ends.tzinfo is None:
                    ends = ends.replace(tzinfo=timezone.utc)
                duration = int((ends - starts).total_seconds() / 60)

            try:
                meeting = await zoom_svc.create_meeting(
                    org_id=org_id,
                    topic=f"{s['title']} - {org_name}",
                    start_time=local.isoformat(),
                    duration_minutes=duration,
                )

                async with get_tenant_db(schema_override=schema_name) as db:
                    await db.execute(
                        """
                        UPDATE class_sessions
                        SET zoom_meeting_id = $1, zoom_join_url = $2, zoom_password = $3, updated_at = NOW()
                        WHERE id = $4
                        """,
                        str(meeting["meeting_id"]), meeting["join_url"], meeting.get("password", ""), str(s["id"]),
                    )

                created += 1
                logger.info("Zoom meeting auto-created", session=s["title"], date=local.strftime("%m/%d"), meeting_id=meeting["meeting_id"])
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.warning("Zoom auto-create failed", session_id=str(s["id"]), title=s["title"], error=str(e))
    finally:
        clear_tenant_context()

    return created


async def _auto_create_all() -> int:
    total = 0
    async with get_global_db() as db:
        orgs = await db.fetch(
            "SELECT id, name, schema_name FROM af_global.organizations WHERE status IN ('active', 'trial')"
        )

    for org in orgs:
        try:
            count = await _create_zoom_for_tenant(str(org["id"]), org["name"], org["schema_name"])
            total += count
        except Exception as e:
            logger.error("Zoom auto-create failed for tenant", schema=org["schema_name"], error=str(e))

    return total


@app.task(name="app.workers.tasks.zoom_auto_create.auto_create_zoom_meetings")
def auto_create_zoom_meetings():
    """Celery task: auto-create Zoom meetings for virtual classes in the next 3 days."""
    loop = asyncio.new_event_loop()
    try:
        total = loop.run_until_complete(_auto_create_all())
        if total:
            logger.info("Zoom meetings auto-created", total=total)
        return {"zoom_meetings_created": total}
    finally:
        loop.close()
