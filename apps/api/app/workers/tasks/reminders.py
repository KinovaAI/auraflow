"""AuraFlow — Class Reminder Task

Runs every 15 minutes via Celery Beat. Finds bookings for classes starting
within the next 2 hours that haven't been sent a reminder yet, and sends
email + SMS reminders.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from app.core.logging import logger
from app.db.session import get_tenant_db, get_global_db
from app.services.email.email_service import EmailService
from app.services.marketing.campaign_service import SmsService
from app.workers.celery_app import app

email_svc = EmailService()
sms_svc = SmsService()


async def _send_reminders_for_tenant(schema_name: str) -> int:
    """Send class reminders for a single tenant schema."""
    from app.core.tenant_context import set_tenant_context, clear_tenant_context

    # Set tenant context so email service can find studio SMTP credentials
    org_id = None
    async with get_global_db() as db:
        org_row = await db.fetchrow(
            "SELECT id FROM af_global.organizations WHERE schema_name = $1", schema_name
        )
        if org_row:
            org_id = str(org_row["id"])
    set_tenant_context(
        organization_id=org_id or "reminder",
        schema_name=schema_name,
        slug=schema_name.replace("af_tenant_", ""),
    )

    sent_count = 0
    now = datetime.now(timezone.utc)
    reminder_window_start = now
    reminder_window_end = now + timedelta(hours=2)

    try:
        # Get studio name
        studio_name = "the studio"
        async with get_global_db() as gdb:
            name_row = await gdb.fetchrow(
                "SELECT name FROM af_global.organizations WHERE schema_name = $1", schema_name
            )
            if name_row:
                studio_name = name_row["name"]

        async with get_tenant_db(schema_override=schema_name) as db:
            # HIPAA 2C Phase C: read phone_enc and decrypt in Python
            # rather than the plaintext column (which will go away).
            rows = await db.fetch(
                """
                SELECT b.id AS booking_id, b.member_id,
                       cs.title AS session_title, cs.starts_at,
                       m.first_name, m.last_name, m.email,
                       m.phone_enc,
                       m.email_opt_in, m.sms_opt_in
                FROM bookings b
                JOIN class_sessions cs ON cs.id = b.class_session_id
                JOIN members m ON m.id = b.member_id
                WHERE b.status = 'confirmed'
                  AND b.reminder_sent_at IS NULL
                  AND cs.starts_at BETWEEN $1 AND $2
                  AND cs.status = 'scheduled'
                """,
                reminder_window_start, reminder_window_end,
            )

            for row in rows:
                member_id = str(row["member_id"])
                name = f"{row['first_name']} {row['last_name']}"
                title = row["session_title"]
                dt = row["starts_at"]
                # Convert UTC to Pacific
                if dt:
                    from zoneinfo import ZoneInfo
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
                    dt = dt.astimezone(ZoneInfo("America/Los_Angeles"))
                time_str = dt.strftime("%-I:%M %p") if dt else ""

                # Atomic claim BEFORE send. Prevents the race where two
                # concurrent task runs (15-min beat overlapping a long
                # iteration) each see reminder_sent_at IS NULL and both
                # send. Only the worker that wins the UPDATE proceeds.
                claimed = await db.fetchval(
                    "UPDATE bookings SET reminder_sent_at = NOW() "
                    "WHERE id = $1 AND reminder_sent_at IS NULL RETURNING id",
                    str(row["booking_id"]),
                )
                if not claimed:
                    continue

                try:
                    if row.get("email_opt_in", True) and row.get("email"):
                        date_str = dt.strftime("%b %d, %Y") if dt else ""
                        await email_svc.send_email(
                            to_email=row["email"],
                            subject=f"Reminder: {title} today at {time_str}",
                            html_content=f"""
                            <h2>Class Reminder</h2>
                            <p>Hi {name},</p>
                            <p>Just a reminder that <strong>{title}</strong> starts at
                            {time_str} today.</p>
                            <p>See you soon!</p>
                            <p style="color: #666; font-size: 12px;">— {studio_name}</p>
                            """,
                            member_id=member_id,
                            email_type="class_reminder",
                        )

                    from app.services.members.phi_helpers import decrypt_phone
                    member_phone = decrypt_phone(row)
                    if row.get("sms_opt_in", True) and member_phone:
                        await sms_svc.send_class_reminder(
                            member_id=member_id,
                            to_phone=member_phone,
                            member_name=name,
                            class_title=title,
                            session_time=time_str,
                        )

                    sent_count += 1

                except Exception as e:
                    # Reset the claim so a future run can retry.
                    await db.execute(
                        "UPDATE bookings SET reminder_sent_at = NULL WHERE id = $1",
                        str(row["booking_id"]),
                    )
                    logger.warning(
                        "Reminder send failed",
                        booking_id=str(row["booking_id"]),
                        error=str(e),
                    )
    finally:
        clear_tenant_context()

    return sent_count


async def _send_all_reminders() -> int:
    """Send reminders across all tenant schemas."""
    total = 0
    async with get_global_db() as db:
        schemas = await db.fetch(
            "SELECT schema_name FROM af_global.organizations WHERE status IN ('active', 'trial')"
        )

    for row in schemas:
        try:
            count = await _send_reminders_for_tenant(row["schema_name"])
            total += count
        except Exception as e:
            logger.error(
                "Reminder task failed for tenant",
                schema=row["schema_name"],
                error=str(e),
            )

    return total


@app.task(name="app.workers.tasks.reminders.send_class_reminders")
def send_class_reminders():
    """Celery task: send class reminders for all tenants."""
    loop = asyncio.new_event_loop()
    try:
        total = loop.run_until_complete(_send_all_reminders())
        logger.info("Class reminders sent", total=total)
        return {"reminders_sent": total}
    finally:
        loop.close()
