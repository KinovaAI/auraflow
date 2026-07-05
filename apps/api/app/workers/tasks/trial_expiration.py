"""AuraFlow — Trial Expiration Task

Runs daily at 7 AM UTC via Celery Beat. Handles two scenarios:
1. Warning email: orgs on trial with 3 days remaining (created_at + 11 days)
2. Expiration: orgs on trial past 14 days — marks status as 'trial_expired'
   and emails the owner. Does NOT delete data or restrict access.
"""
import asyncio

from app.core.logging import logger
from app.db.session import get_global_db
from app.services.email.email_service import EmailService
from app.workers.celery_app import app
from app.workers.idempotency import acquire_once

email_svc = EmailService()


async def _send_trial_warnings() -> int:
    """Send warning emails to orgs whose trial expires in 3 days."""
    warned = 0

    async with get_global_db() as db:
        rows = await db.fetch(
            """
            SELECT o.id, o.name, o.slug,
                   u.email AS owner_email, u.first_name AS owner_first_name
            FROM af_global.organizations o
            JOIN af_global.organization_users ou
              ON ou.organization_id = o.id AND ou.role = 'owner'
            JOIN af_global.users u ON u.id = ou.user_id
            WHERE o.status = 'trial'
              AND o.created_at >= NOW() - INTERVAL '12 days'
              AND o.created_at < NOW() - INTERVAL '11 days'
            """
        )

        for row in rows:
            org_name = row["name"]
            owner_email = row["owner_email"]
            first_name = row["owner_first_name"] or "there"

            # Idempotency: a task retry or a double-run must not double-warn.
            # 24h TTL covers the natural daily cadence.
            if not await acquire_once(f"trial_warning:{row['id']}", ttl=86400):
                continue

            try:
                subject = f"Your {org_name} trial expires in 3 days"
                html = f"""
                <h2>Your Trial Is Ending Soon</h2>
                <p>Hi {first_name},</p>
                <p>Your free trial of AuraFlow for <strong>{org_name}</strong>
                expires in 3 days.</p>
                <p>Upgrade now to keep all your data, schedules, and member
                information. No disruption to your studio.</p>
                <p>Visit your admin dashboard to choose a plan.</p>
                <p style="color: #666; font-size: 12px;">&mdash; The AuraFlow Team</p>
                """
                await email_svc.send_email(
                    to_email=owner_email,
                    subject=subject,
                    html_content=html,
                )
                warned += 1
                logger.info(
                    "Trial warning email sent",
                    org_id=str(row["id"]),
                    org_name=org_name,
                    owner_email=owner_email,
                )
            except Exception as e:
                logger.warning(
                    "Failed to send trial warning email",
                    org_id=str(row["id"]),
                    error=str(e),
                )

    return warned


async def _expire_trials() -> int:
    """Mark expired trials and notify owners."""
    expired = 0

    async with get_global_db() as db:
        rows = await db.fetch(
            """
            SELECT o.id, o.name, o.slug,
                   u.email AS owner_email, u.first_name AS owner_first_name
            FROM af_global.organizations o
            JOIN af_global.organization_users ou
              ON ou.organization_id = o.id AND ou.role = 'owner'
            JOIN af_global.users u ON u.id = ou.user_id
            WHERE o.status = 'trial'
              AND o.created_at < NOW() - INTERVAL '14 days'
            """
        )

        for row in rows:
            org_id = str(row["id"])
            org_name = row["name"]
            owner_email = row["owner_email"]
            first_name = row["owner_first_name"] or "there"

            try:
                # Mark the org as trial_expired
                await db.execute(
                    """
                    UPDATE af_global.organizations
                    SET status = 'trial_expired', updated_at = NOW()
                    WHERE id = $1
                    """,
                    row["id"],
                )
                logger.info(
                    "Trial expired — status updated",
                    org_id=org_id,
                    org_name=org_name,
                )

                # Notify the owner
                subject = f"Your {org_name} trial has expired"
                html = f"""
                <h2>Your Trial Has Expired</h2>
                <p>Hi {first_name},</p>
                <p>Your 14-day free trial of AuraFlow for
                <strong>{org_name}</strong> has ended.</p>
                <p>Don&rsquo;t worry &mdash; all your data is safe.
                Upgrade to a paid plan to restore full access to scheduling,
                payments, and all the features you&rsquo;ve been using.</p>
                <p>Visit your admin dashboard to choose a plan and pick up
                right where you left off.</p>
                <p style="color: #666; font-size: 12px;">&mdash; The AuraFlow Team</p>
                """
                await email_svc.send_email(
                    to_email=owner_email,
                    subject=subject,
                    html_content=html,
                )
                expired += 1
                logger.info(
                    "Trial expiration email sent",
                    org_id=org_id,
                    owner_email=owner_email,
                )
            except Exception as e:
                logger.error(
                    "Failed to process trial expiration",
                    org_id=org_id,
                    error=str(e),
                )

    return expired


async def _process_trial_expirations() -> dict:
    """Run both warning and expiration flows."""
    warned = await _send_trial_warnings()
    expired = await _expire_trials()
    return {"warnings_sent": warned, "trials_expired": expired}


@app.task(name="app.workers.tasks.trial_expiration.check_trial_expirations")
def check_trial_expirations():
    """Celery task: process trial warnings and expirations for all orgs."""
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_process_trial_expirations())
        logger.info(
            "Trial expiration task complete",
            warnings_sent=result["warnings_sent"],
            trials_expired=result["trials_expired"],
        )
        return result
    finally:
        loop.close()
