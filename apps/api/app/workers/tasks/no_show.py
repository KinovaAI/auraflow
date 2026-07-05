"""AuraFlow — No-Show Auto-Mark + Follow-Up Tasks

Two tasks:
1. mark_no_shows (every 30 min): Auto-mark bookings as 'no_show' when the
   class has ended and the member was not checked in.
2. send_no_show_followups (daily 9 AM): Send "we missed you" emails to
   members who were marked as no-show for yesterday's classes.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from app.core.logging import logger
from app.db.session import get_tenant_db, get_global_db
from app.services.email.email_service import EmailService
from app.workers.celery_app import app

email_svc = EmailService()


# ── Auto No-Show Marking ──────────────────────────────────────────────────


async def _mark_no_shows_for_tenant(schema_name: str) -> int:
    """Mark confirmed bookings as no_show when the class has already ended."""
    marked = 0
    now = datetime.now(timezone.utc)

    async with get_tenant_db(schema_override=schema_name) as db:
        rows = await db.fetch(
            """
            UPDATE bookings b
            SET status = 'no_show'
            FROM class_sessions cs
            WHERE cs.id = b.class_session_id
              AND b.status = 'confirmed'
              AND cs.ends_at < $1
            RETURNING b.id
            """,
            now,
        )
        marked = len(rows)

    return marked


async def _mark_all_no_shows() -> int:
    """Mark no-shows across all tenants."""
    total = 0
    async with get_global_db() as db:
        schemas = await db.fetch(
            "SELECT schema_name FROM af_global.organizations WHERE status IN ('active', 'trial')"
        )

    for row in schemas:
        try:
            count = await _mark_no_shows_for_tenant(row["schema_name"])
            total += count
        except Exception as e:
            logger.error(
                "No-show marking failed for tenant",
                schema=row["schema_name"],
                error=str(e),
            )

    return total


@app.task(name="app.workers.tasks.no_show.mark_no_shows")
def mark_no_shows():
    """Celery task: auto-mark confirmed bookings as no_show after class ends."""
    loop = asyncio.new_event_loop()
    try:
        total = loop.run_until_complete(_mark_all_no_shows())
        logger.info("Auto no-show marking complete", total_marked=total)
        return {"marked_no_show": total}
    finally:
        loop.close()


# ── No-Show Follow-Up Emails ──────────────────────────────────────────────


async def _send_no_show_for_tenant(schema_name: str) -> int:
    """Send no-show follow-ups for a single tenant."""
    sent_count = 0
    now = datetime.now(timezone.utc)
    yesterday_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0)
    yesterday_end = yesterday_start + timedelta(days=1)

    async with get_tenant_db(schema_override=schema_name) as db:
        rows = await db.fetch(
            """
            SELECT b.id AS booking_id, b.member_id,
                   cs.title AS session_title, cs.starts_at,
                   ct.name AS class_type_name,
                   m.first_name, m.last_name, m.email, m.email_opt_in
            FROM bookings b
            JOIN class_sessions cs ON cs.id = b.class_session_id
            LEFT JOIN class_types ct ON ct.id = cs.class_type_id
            JOIN members m ON m.id = b.member_id
            WHERE b.status = 'no_show'
              AND cs.starts_at BETWEEN $1 AND $2
              AND m.email_opt_in = TRUE
              AND m.email IS NOT NULL
            """,
            yesterday_start, yesterday_end,
        )

        for row in rows:
            member_id = str(row["member_id"])
            booking_id = str(row["booking_id"])

            # Dedup
            existing = await db.fetchval(
                """
                SELECT COUNT(*) FROM communication_log
                WHERE member_id = $1 AND type = 'no_show_followup'
                  AND metadata::text LIKE $2
                """,
                member_id, f'%{booking_id}%',
            )
            if existing > 0:
                continue

            name = f"{row['first_name']} {row['last_name']}"
            class_title = row["session_title"] or row["class_type_name"] or "class"

            try:
                html = f"""
                <h2>We missed you!</h2>
                <p>Hi {name},</p>
                <p>We noticed you weren't able to make it to <strong>{class_title}</strong> yesterday.
                No worries — life happens!</p>
                <p>When you're ready, check the schedule and book your next session.
                We'd love to see you back.</p>
                <p style="color: #666; font-size: 12px;">— AuraFlow</p>
                """
                await email_svc.send_email(
                    to_email=row["email"],
                    subject=f"We missed you at {class_title}",
                    html_content=html,
                    member_id=member_id,
                    email_type="no_show_followup",
                )
                sent_count += 1
            except Exception as e:
                logger.warning(
                    "No-show follow-up failed",
                    member_id=member_id,
                    error=str(e),
                )

    return sent_count


async def _send_all_no_show_followups() -> int:
    """Send no-show follow-ups across all tenants."""
    total = 0
    async with get_global_db() as db:
        schemas = await db.fetch(
            "SELECT schema_name FROM af_global.organizations WHERE status IN ('active', 'trial')"
        )

    for row in schemas:
        try:
            count = await _send_no_show_for_tenant(row["schema_name"])
            total += count
        except Exception as e:
            logger.error(
                "No-show follow-up failed for tenant",
                schema=row["schema_name"],
                error=str(e),
            )

    return total


@app.task(name="app.workers.tasks.no_show.send_no_show_followups")
def send_no_show_followups():
    """Celery task: send no-show follow-up emails for all tenants."""
    loop = asyncio.new_event_loop()
    try:
        total = loop.run_until_complete(_send_all_no_show_followups())
        logger.info("No-show follow-ups sent", total=total)
        return {"followups_sent": total}
    finally:
        loop.close()
