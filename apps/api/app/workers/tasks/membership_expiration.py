"""AuraFlow — Membership Expiration Reminder Task

Runs daily at 8 AM UTC via Celery Beat. Sends reminders to members
whose memberships expire within 7 days or 1 day.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from app.core.logging import logger
from app.db.session import get_tenant_db, get_global_db
from app.services.email.email_service import EmailService
from app.services.marketing.campaign_service import SmsService
from app.services.members.phi_helpers import decrypt_phone
from app.workers.celery_app import app

email_svc = EmailService()
sms_svc = SmsService()


async def _check_expirations_for_tenant(schema_name: str) -> int:
    """Send expiration reminders for a single tenant."""
    sent_count = 0
    now = datetime.now(timezone.utc)

    async with get_tenant_db(schema_override=schema_name) as db:
        # Find memberships expiring within 7 days
        rows = await db.fetch(
            """
            SELECT mm.id AS membership_id, mm.ends_at,
                   mt.name AS type_name,
                   m.id AS member_id, m.first_name, m.last_name,
                   m.email, m.phone_enc, m.email_opt_in, m.sms_opt_in
            FROM member_memberships mm
            JOIN membership_types mt ON mt.id = mm.membership_type_id
            JOIN members m ON m.id = mm.member_id
            WHERE mm.status = 'active'
              AND mm.ends_at IS NOT NULL
              AND mm.ends_at BETWEEN $1 AND $2
            """,
            now, now + timedelta(days=8),
        )

        for row in rows:
            member_id = str(row["member_id"])
            days_left = (row["ends_at"] - now).days
            name = f"{row['first_name']} {row['last_name']}"
            type_name = row["type_name"]

            # Only send at 7-day and 1-day marks
            if days_left not in (1, 7):
                continue

            is_urgent = days_left <= 1
            reminder_type = "membership_expiration_1day" if is_urgent else "membership_expiration_7day"

            # Dedup: check if already sent within 24h
            existing = await db.fetchval(
                """
                SELECT COUNT(*) FROM communication_log
                WHERE member_id = $1 AND type = $2
                  AND created_at > $3
                """,
                member_id, reminder_type, now - timedelta(hours=24),
            )
            if existing > 0:
                continue

            try:
                # Email reminder
                if row.get("email_opt_in", True) and row.get("email"):
                    days_text = "tomorrow" if is_urgent else f"in {days_left} days"
                    subject = f"Your {type_name} membership expires {days_text}"
                    html = f"""
                    <h2>Membership Expiring Soon</h2>
                    <p>Hi {name},</p>
                    <p>Your <strong>{type_name}</strong> membership expires {days_text}.</p>
                    <p>Renew now to keep your access and avoid any interruption.</p>
                    <p>Log in to your member portal to renew.</p>
                    <p style="color: #666; font-size: 12px;">— AuraFlow</p>
                    """
                    await email_svc.send_email(
                        to_email=row["email"],
                        subject=subject,
                        html_content=html,
                        member_id=member_id,
                        email_type=reminder_type,
                    )

                # SMS only for 1-day urgent reminder
                member_phone = decrypt_phone(row)
                if is_urgent and row.get("sms_opt_in", True) and member_phone:
                    await sms_svc.send_sms(
                        to_phone=member_phone,
                        body=f"Hi {row['first_name']}, your {type_name} membership expires tomorrow. Renew now to keep your access!",
                        member_id=member_id,
                        sms_type="reminder",
                    )

                sent_count += 1

            except Exception as e:
                logger.warning(
                    "Expiration reminder failed",
                    member_id=member_id,
                    error=str(e),
                )

    return sent_count


async def _check_all_expirations() -> int:
    """Check membership expirations across all tenants."""
    total = 0
    async with get_global_db() as db:
        schemas = await db.fetch(
            "SELECT schema_name FROM af_global.organizations WHERE status IN ('active', 'trial')"
        )

    for row in schemas:
        try:
            count = await _check_expirations_for_tenant(row["schema_name"])
            total += count
        except Exception as e:
            logger.error(
                "Expiration check failed for tenant",
                schema=row["schema_name"],
                error=str(e),
            )

    return total


@app.task(name="app.workers.tasks.membership_expiration.check_membership_expirations")
def check_membership_expirations():
    """Celery task: send membership expiration reminders for all tenants."""
    loop = asyncio.new_event_loop()
    try:
        total = loop.run_until_complete(_check_all_expirations())
        logger.info("Membership expiration reminders sent", total=total)
        return {"reminders_sent": total}
    finally:
        loop.close()


# ── Auto-Expire Memberships ───────────────────────────────────────────────


async def _expire_memberships_for_tenant(schema_name: str) -> int:
    """Mark expired memberships for a single tenant."""
    now = datetime.now(timezone.utc)

    async with get_tenant_db(schema_override=schema_name) as db:
        rows = await db.fetch(
            """
            UPDATE member_memberships
            SET status = 'expired', updated_at = NOW()
            WHERE status = 'active'
              AND ends_at IS NOT NULL
              AND ends_at < $1
              AND stripe_subscription_id IS NULL
              -- Square memberships (incl. free trials) are lifecycle-managed by
              -- the recurring-renewal scheduler, which charges ~1 day BEFORE
              -- ends_at and rolls the period forward. Never time-expire them out
              -- from under that task — a failed charge moves them to 'past_due'.
              AND billing_provider IS DISTINCT FROM 'square'
            RETURNING id
            """,
            now,
        )
        return len(rows)


async def _expire_all_memberships() -> int:
    """Expire memberships across all tenants."""
    total = 0
    async with get_global_db() as db:
        schemas = await db.fetch(
            "SELECT schema_name FROM af_global.organizations WHERE status IN ('active', 'trial')"
        )

    for row in schemas:
        try:
            count = await _expire_memberships_for_tenant(row["schema_name"])
            total += count
        except Exception as e:
            logger.error(
                "Membership auto-expire failed for tenant",
                schema=row["schema_name"],
                error=str(e),
            )

    return total


@app.task(name="app.workers.tasks.membership_expiration.auto_expire_memberships")
def auto_expire_memberships():
    """Celery task: auto-expire memberships past their end date for all tenants."""
    loop = asyncio.new_event_loop()
    try:
        total = loop.run_until_complete(_expire_all_memberships())
        logger.info("Memberships auto-expired", total=total)
        return {"expired": total}
    finally:
        loop.close()
