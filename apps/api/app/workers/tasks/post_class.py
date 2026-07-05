"""AuraFlow — Post-Class Follow-Up Task

Runs hourly at :30 via Celery Beat. Sends a "thanks for coming" email
to members who attended a class ~24 hours ago.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from app.core.logging import logger
from app.db.session import get_tenant_db, get_global_db
from app.services.email.email_service import EmailService
from app.workers.celery_app import app

email_svc = EmailService()


async def _send_followups_for_tenant(schema_name: str) -> int:
    """Send post-class follow-ups for a single tenant."""
    from app.core.tenant_context import set_tenant_context, clear_tenant_context

    # Set tenant context so email service finds studio SMTP
    org_id = None
    studio_name = "the studio"
    async with get_global_db() as db:
        org_row = await db.fetchrow(
            "SELECT id, name FROM af_global.organizations WHERE schema_name = $1", schema_name
        )
        if org_row:
            org_id = str(org_row["id"])
            studio_name = org_row["name"]
    set_tenant_context(
        organization_id=org_id or "post_class",
        schema_name=schema_name,
        slug=schema_name.replace("af_tenant_", ""),
    )

    sent_count = 0
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=28)
    window_end = now - timedelta(hours=20)

    try:
      async with get_tenant_db(schema_override=schema_name) as db:
        rows = await db.fetch(
            """
            SELECT b.id AS booking_id, b.member_id, b.checked_in_at,
                   cs.title AS session_title,
                   ct.name AS class_type_name,
                   i.display_name AS instructor_name,
                   m.first_name, m.last_name, m.email, m.email_opt_in
            FROM bookings b
            JOIN class_sessions cs ON cs.id = b.class_session_id
            LEFT JOIN class_types ct ON ct.id = cs.class_type_id
            LEFT JOIN instructors i ON i.id = cs.instructor_id
            JOIN members m ON m.id = b.member_id
            WHERE b.status = 'attended'
              AND b.checked_in_at BETWEEN $1 AND $2
              AND b.post_class_followup_sent_at IS NULL
              AND m.email_opt_in = TRUE
              AND m.email IS NOT NULL
            """,
            window_start, window_end,
        )

        for row in rows:
            member_id = str(row["member_id"])
            booking_id = str(row["booking_id"])

            # Atomic claim: flip post_class_followup_sent_at NULL → NOW()
            # only if it's still NULL. Returns the row only for the worker
            # that wins the claim. Prevents duplicate sends across the
            # 8-hour sliding window the hourly task scans, and across
            # any concurrent task run.
            claimed = await db.fetchval(
                """
                UPDATE bookings
                SET post_class_followup_sent_at = NOW()
                WHERE id = $1 AND post_class_followup_sent_at IS NULL
                RETURNING id
                """,
                booking_id,
            )
            if not claimed:
                continue

            name = f"{row['first_name']} {row['last_name']}"
            class_title = row["session_title"] or row["class_type_name"] or "class"
            instructor = row.get("instructor_name")

            try:
                instructor_line = f" with {instructor}" if instructor else ""
                html = f"""
                <h2>Thanks for coming!</h2>
                <p>Hi {name},</p>
                <p>We hope you enjoyed <strong>{class_title}</strong>{instructor_line}.</p>
                <p>Ready for your next session? Check the schedule in your member portal
                and book your next class.</p>
                <p style="color: #666; font-size: 12px;">— {studio_name}</p>
                """
                await email_svc.send_email(
                    to_email=row["email"],
                    subject=f"Thanks for attending {class_title}!",
                    html_content=html,
                    member_id=member_id,
                    email_type="post_class_followup",
                )
                sent_count += 1
            except Exception as e:
                # Reset the claim so a future run can retry. Without this,
                # a transient SMTP failure permanently silences the email.
                await db.execute(
                    "UPDATE bookings SET post_class_followup_sent_at = NULL WHERE id = $1",
                    booking_id,
                )
                logger.warning(
                    "Post-class follow-up failed",
                    member_id=member_id,
                    error=str(e),
                )

    finally:
        clear_tenant_context()

    return sent_count


async def _send_all_followups() -> int:
    """Send post-class follow-ups across all tenants."""
    total = 0
    async with get_global_db() as db:
        schemas = await db.fetch(
            "SELECT schema_name FROM af_global.organizations WHERE status IN ('active', 'trial')"
        )

    for row in schemas:
        try:
            count = await _send_followups_for_tenant(row["schema_name"])
            total += count
        except Exception as e:
            logger.error(
                "Post-class follow-up failed for tenant",
                schema=row["schema_name"],
                error=str(e),
            )

    return total


@app.task(name="app.workers.tasks.post_class.send_post_class_followups")
def send_post_class_followups():
    """Celery task: send post-class follow-up emails for all tenants."""
    loop = asyncio.new_event_loop()
    try:
        total = loop.run_until_complete(_send_all_followups())
        logger.info("Post-class follow-ups sent", total=total)
        return {"followups_sent": total}
    finally:
        loop.close()
