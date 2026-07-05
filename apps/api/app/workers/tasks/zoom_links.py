"""AuraFlow — Zoom Link Sender Task

Runs every 15 minutes via Celery Beat. Finds confirmed bookings for virtual
class sessions starting within the next hour that haven't been sent a Zoom
link yet, and emails the join link to the member.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from app.core.logging import logger
from app.db.session import get_tenant_db, get_global_db
from app.core.tenant_context import set_tenant_context, clear_tenant_context
from app.services.email.email_service import EmailService
from app.workers.celery_app import app

email_svc = EmailService()


async def _send_zoom_links_for_tenant(schema_name: str, org_id: str, org_name: str) -> int:
    """Send Zoom join links for virtual classes starting within 1 hour."""
    sent_count = 0
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(hours=1)

    set_tenant_context(organization_id=org_id, schema_name=schema_name, slug=schema_name.replace("af_tenant_", ""))

    try:
        async with get_tenant_db(schema_override=schema_name) as db:
            rows = await db.fetch(
                """
                SELECT b.id AS booking_id, b.member_id,
                       cs.title AS session_title, cs.starts_at,
                       cs.zoom_join_url, cs.zoom_password, cs.zoom_meeting_id,
                       m.first_name, m.last_name, m.email, m.email_opt_in
                FROM bookings b
                JOIN class_sessions cs ON cs.id = b.class_session_id
                JOIN members m ON m.id = b.member_id
                WHERE b.status = 'confirmed'
                  -- Class must HAVE a Zoom side. Pure in_studio classes
                  -- get no Zoom link regardless of member scope.
                  AND cs.modality IN ('virtual', 'hybrid')
                  AND cs.zoom_join_url IS NOT NULL
                  AND b.zoom_link_sent_at IS NULL
                  AND cs.starts_at BETWEEN $1 AND $2
                  AND cs.status = 'scheduled'
                  AND EXISTS (
                      SELECT 1 FROM member_memberships mm
                      JOIN membership_types mt ON mt.id = mm.membership_type_id
                      WHERE mm.member_id = b.member_id
                        AND mm.status = 'active'
                        AND (mm.ends_at IS NULL OR mm.ends_at > NOW())
                        -- Only members paying for digital access get
                        -- the link. in_studio plans on a hybrid class
                        -- attend in person without the join URL.
                        AND mt.access_scope IN ('online', 'all_access')
                        AND (mt.type <> 'single_class' OR mm.classes_remaining > 0)
                        AND (mt.type <> 'class_pack' OR mm.classes_remaining > 0)
                  )
                """,
                now, window_end,
            )

            for row in rows:
                if not row.get("email") or not row.get("email_opt_in", True):
                    continue

                member_id = str(row["member_id"])
                name = row["first_name"]
                title = row["session_title"]
                dt = row["starts_at"]
                from zoneinfo import ZoneInfo
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                local_time = dt.astimezone(ZoneInfo("America/Los_Angeles"))
                time_str = local_time.strftime("%-I:%M %p")
                date_str = local_time.strftime("%A, %B %d")

                zoom_url = row["zoom_join_url"]
                zoom_password = row["zoom_password"] or ""
                zoom_id = row["zoom_meeting_id"] or ""

                html = f"""
                <h2>Your Zoom Link for {title}</h2>
                <p>Hi {name},</p>
                <p>Your class is starting soon! Here's your Zoom link for <strong>{title}</strong> at <strong>{org_name}</strong>:</p>
                <table style="margin: 16px 0; border-collapse: collapse;">
                  <tr><td style="padding: 6px 12px; color: #666;">Date</td><td style="padding: 6px 12px; font-weight: 600;">{date_str}</td></tr>
                  <tr><td style="padding: 6px 12px; color: #666;">Time</td><td style="padding: 6px 12px; font-weight: 600;">{time_str}</td></tr>
                  <tr><td style="padding: 6px 12px; color: #666;">Meeting ID</td><td style="padding: 6px 12px; font-weight: 600;">{zoom_id}</td></tr>
                  {"<tr><td style='padding: 6px 12px; color: #666;'>Password</td><td style='padding: 6px 12px; font-weight: 600;'>" + zoom_password + "</td></tr>" if zoom_password else ""}
                </table>
                <p style="margin: 24px 0;">
                  <a href="{zoom_url}" style="background-color: #2D8CFF; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: 600;">
                    Join Zoom Class
                  </a>
                </p>
                <p style="color: #666; font-size: 13px;">If the button doesn't work, copy and paste this link:<br/>
                <a href="{zoom_url}">{zoom_url}</a></p>
                <p>See you on the mat!</p>
                <p>— {org_name}</p>
                """

                try:
                    await email_svc.send_email(
                        to_email=row["email"],
                        subject=f"Zoom Link: {title} — Today at {time_str}",
                        html_content=html,
                        member_id=member_id,
                        email_type="zoom_link",
                    )

                    await db.execute(
                        "UPDATE bookings SET zoom_link_sent_at = NOW() WHERE id = $1",
                        str(row["booking_id"]),
                    )
                    sent_count += 1
                    logger.info("Zoom link sent", member=row["email"], session=title)

                except Exception as e:
                    logger.warning("Zoom link send failed", booking_id=str(row["booking_id"]), error=str(e))
    finally:
        clear_tenant_context()

    return sent_count


async def _send_all_zoom_links() -> int:
    """Send Zoom links across all tenant schemas."""
    total = 0
    async with get_global_db() as db:
        orgs = await db.fetch(
            "SELECT id, name, schema_name FROM af_global.organizations WHERE status IN ('active', 'trial')"
        )

    for org in orgs:
        try:
            count = await _send_zoom_links_for_tenant(org["schema_name"], str(org["id"]), org["name"])
            total += count
        except Exception as e:
            logger.error("Zoom link task failed for tenant", schema=org["schema_name"], error=str(e))

    return total


@app.task(name="app.workers.tasks.zoom_links.send_zoom_links")
def send_zoom_links():
    """Celery task: send Zoom join links 1 hour before virtual classes."""
    loop = asyncio.new_event_loop()
    try:
        total = loop.run_until_complete(_send_all_zoom_links())
        if total:
            logger.info("Zoom links sent", total=total)
        return {"zoom_links_sent": total}
    finally:
        loop.close()
