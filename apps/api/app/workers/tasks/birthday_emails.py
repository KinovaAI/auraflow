"""AuraFlow — Birthday Email Task

Runs daily at 7:30 AM UTC via Celery Beat. Sends a birthday greeting
to members whose date_of_birth matches today's month and day.
"""
import asyncio
from datetime import datetime, timezone

from app.core.logging import logger
from app.db.session import get_tenant_db, get_global_db
from app.services.email.email_service import EmailService
from app.workers.celery_app import app

email_svc = EmailService()


async def _get_studio_name(schema_name: str) -> str:
    """Get the org display name from the global organizations table."""
    async with get_global_db() as db:
        name = await db.fetchval(
            "SELECT name FROM af_global.organizations WHERE schema_name = $1",
            schema_name,
        )
    return name or schema_name.replace("af_tenant_", "").replace("_", " ").title()


async def _send_birthdays_for_tenant(schema_name: str) -> int:
    """Send birthday emails for a single tenant."""
    sent_count = 0
    now = datetime.now(timezone.utc)
    today_month = now.month
    today_day = now.day

    studio_name = await _get_studio_name(schema_name)

    async with get_tenant_db(schema_override=schema_name) as db:

        # HIPAA 2C Phase C: filter on plaintext-derived month+day
        # cols. Full date_of_birth stays encrypted in date_of_birth_enc.
        # Month+day alone are not PHI under §164.514 Safe Harbor.
        rows = await db.fetch(
            """
            SELECT m.id AS member_id, m.first_name, m.last_name,
                   m.email, m.email_opt_in
            FROM members m
            WHERE m.birthday_month = $1
              AND m.birthday_day = $2
              AND m.email IS NOT NULL
              AND m.email_opt_in = TRUE
              AND m.status = 'active'
            """,
            today_month, today_day,
        )

        for row in rows:
            member_id = str(row["member_id"])
            name = row["first_name"]

            # Dedup: check if birthday email already sent today
            existing = await db.fetchval(
                """
                SELECT COUNT(*) FROM communication_log
                WHERE member_id = $1 AND type = 'birthday'
                  AND created_at::date = $2
                """,
                member_id, now.date(),
            )
            if existing > 0:
                continue

            try:
                html = f"""
                <h2 style="color: #6B46C1;">🎂 Happy Birthday, {name}!</h2>
                <p>Hi {name},</p>
                <p>Everyone at <strong>{studio_name}</strong> wants to wish you the happiest of birthdays!</p>
                <p>We're so grateful to have you as part of our community.
                Here's to another wonderful year of wellness and growth.</p>
                <p>Enjoy your special day!</p>
                <p style="color: #666; font-size: 12px;">— {studio_name}</p>
                """
                await email_svc.send_email(
                    to_email=row["email"],
                    subject=f"Happy Birthday from {studio_name}! 🎂",
                    html_content=html,
                    member_id=member_id,
                    email_type="birthday",
                )
                sent_count += 1
            except Exception as e:
                logger.warning(
                    "Birthday email failed",
                    member_id=member_id,
                    error=str(e),
                )

    return sent_count


async def _send_all_birthday_emails() -> int:
    """Send birthday emails across all tenants."""
    total = 0
    async with get_global_db() as db:
        schemas = await db.fetch(
            "SELECT schema_name FROM af_global.organizations WHERE status IN ('active', 'trial')"
        )

    for row in schemas:
        try:
            count = await _send_birthdays_for_tenant(row["schema_name"])
            total += count
        except Exception as e:
            logger.error(
                "Birthday emails failed for tenant",
                schema=row["schema_name"],
                error=str(e),
            )

    return total


@app.task(name="app.workers.tasks.birthday_emails.send_birthday_emails")
def send_birthday_emails():
    """Celery task: send birthday greeting emails for all tenants."""
    loop = asyncio.new_event_loop()
    try:
        total = loop.run_until_complete(_send_all_birthday_emails())
        logger.info("Birthday emails sent", total=total)
        return {"birthday_emails_sent": total}
    finally:
        loop.close()
