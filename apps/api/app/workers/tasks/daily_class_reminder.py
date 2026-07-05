"""AuraFlow — Daily Class Reminder Task

Runs daily at 7 AM Pacific via Celery Beat. Sends a single email to each
member who has classes booked today, listing all their classes and times.
Sends 1 email every 2 minutes to avoid blasting SMTP.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from app.core.logging import logger
from app.core.tenant_context import set_tenant_context, clear_tenant_context
from app.db.session import get_tenant_db, get_global_db
from app.services.email.email_service import EmailService
from app.workers.celery_app import app

email_svc = EmailService()

SEND_SPACING_SECONDS = 120  # 2 minutes between emails


async def _send_daily_reminders_for_tenant(org_id: str, org_name: str, schema_name: str) -> int:
    """Send daily class reminders for a single tenant."""
    set_tenant_context(
        organization_id=org_id,
        schema_name=schema_name,
        slug=schema_name.replace("af_tenant_", ""),
    )
    sent = 0

    try:
        from zoneinfo import ZoneInfo
        pacific = ZoneInfo("America/Los_Angeles")
        today_local = datetime.now(pacific).date()

        # Get today's date range in UTC
        day_start = datetime.combine(today_local, datetime.min.time(), tzinfo=pacific).astimezone(timezone.utc)
        day_end = datetime.combine(today_local + timedelta(days=1), datetime.min.time(), tzinfo=pacific).astimezone(timezone.utc)

        async with get_tenant_db(schema_override=schema_name) as db:
            # Get all confirmed bookings for today with member and class info
            rows = await db.fetch(
                """
                SELECT m.id AS member_id, m.first_name, m.email, m.email_opt_in,
                       cs.title, cs.starts_at
                FROM bookings b
                JOIN class_sessions cs ON cs.id = b.class_session_id
                JOIN members m ON m.id = b.member_id
                WHERE b.status = 'confirmed'
                  AND cs.starts_at >= $1 AND cs.starts_at < $2
                  AND cs.status = 'scheduled'
                ORDER BY m.id, cs.starts_at
                """,
                day_start.replace(tzinfo=None), day_end.replace(tzinfo=None),
            )

        if not rows:
            return 0

        # Group by member
        members: dict[str, dict] = {}
        for r in rows:
            mid = str(r["member_id"])
            if mid not in members:
                members[mid] = {
                    "first_name": r["first_name"],
                    "email": r["email"],
                    "email_opt_in": r.get("email_opt_in", True),
                    "classes": [],
                }
            from zoneinfo import ZoneInfo
            starts = r["starts_at"]
            if starts.tzinfo is None:
                starts = starts.replace(tzinfo=timezone.utc)
            local_time = starts.astimezone(pacific)
            members[mid]["classes"].append({
                "title": r["title"],
                "time": local_time.strftime("%-I:%M %p"),
            })

        # Send one email per member
        for mid, info in members.items():
            if not info["email"] or not info.get("email_opt_in", True):
                continue

            class_list = "".join(
                f'<li style="margin: 4px 0;"><strong>{c["title"]}</strong> at {c["time"]}</li>'
                for c in info["classes"]
            )

            html = f"""
            <p>Namaste!</p>
            <p>We'd like to remind you that you are scheduled for the following today at <strong>{org_name}</strong>:</p>
            <ul style="margin: 16px 0; padding-left: 20px;">
              {class_list}
            </ul>
            <p>We look forward to seeing you.</p>
            <p>The {org_name} Team</p>
            """

            try:
                await email_svc.send_email(
                    to_email=info["email"],
                    subject=f"Your classes today at {org_name}",
                    html_content=html,
                    member_id=mid,
                    email_type="daily_reminder",
                )
                sent += 1
            except Exception as e:
                logger.warning("Daily reminder send failed", member_id=mid, error=str(e))

            if sent < len(members):
                await asyncio.sleep(SEND_SPACING_SECONDS)

    finally:
        clear_tenant_context()

    return sent


async def _send_all_daily_reminders() -> int:
    """Send daily reminders across all tenants."""
    total = 0
    async with get_global_db() as db:
        orgs = await db.fetch(
            "SELECT id, name, schema_name FROM af_global.organizations WHERE status IN ('active', 'trial')"
        )

    for org in orgs:
        try:
            count = await _send_daily_reminders_for_tenant(
                str(org["id"]), org["name"], org["schema_name"]
            )
            total += count
            if count:
                logger.info("Daily class reminders sent", schema=org["schema_name"], count=count)
        except Exception as e:
            logger.error("Daily reminder failed for tenant", schema=org["schema_name"], error=str(e))

    return total


@app.task(
    name="app.workers.tasks.daily_class_reminder.send_daily_class_reminders",
    # 120s spacing × N booked members per tenant blows the default 5-min
    # soft limit fast (already truncated 1-of-6 reminders on 2026-04-27).
    # Match churn_scan: 60-min hard / 55-min soft. Spacing rule (no
    # blasting) means runtime is bounded by member count, not retries.
    time_limit=3600,
    soft_time_limit=3300,
)
def send_daily_class_reminders():
    """Celery task: send daily class reminder emails at 7 AM Pacific."""
    loop = asyncio.new_event_loop()
    try:
        total = loop.run_until_complete(_send_all_daily_reminders())
        logger.info("Daily class reminders complete", total=total)
        return {"reminders_sent": total}
    finally:
        loop.close()
