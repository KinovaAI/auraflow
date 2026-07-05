"""AuraFlow — Daily Churn Scan Task

Runs daily via Celery Beat. Scans all tenant schemas for members
at risk of churning and automatically sends personalized winback
outreach (email) to newly flagged members. Tracks outreach via
churn_outreach_sent_at to prevent duplicate sends.
"""
import asyncio

from app.core.logging import logger
from app.db.session import get_global_db, get_tenant_db
from app.services.ai.churn_service import ChurnService
from app.services.email.email_service import EmailService
from app.workers.celery_app import app

churn_svc = ChurnService()
email_svc = EmailService()

# Max winback emails per tenant per scan (prevent blasting)
MAX_WINBACK_PER_TENANT = 50
# Minimum seconds between sends (spread them out)
SEND_SPACING_SECONDS = 30


async def _send_winback_for_member(
    schema: str, member: dict, studio_name: str,
) -> bool:
    """Send a personalized winback email to a single flagged member.

    Returns True if sent successfully, False otherwise.
    """
    member_id = member["id"]
    first_name = member.get("first_name", "there")
    email = member.get("email")

    if not email:
        return False

    # Calculate days since last visit for personalization
    days_text = ""
    async with get_tenant_db(schema_override=schema) as db:
        row = await db.fetchrow(
            "SELECT last_visit_at FROM members WHERE id = $1", member_id,
        )
        if row and row["last_visit_at"]:
            from datetime import datetime, timezone
            days = (datetime.now(timezone.utc) - row["last_visit_at"]).days
            days_text = f"It's been {days} days since your last visit. "

    html_content = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 560px; margin: 0 auto;">
      <h2 style="color: #1a1a2e;">We miss you, {first_name}!</h2>
      <p>Hi {first_name},</p>
      <p>{days_text}We'd love to welcome you back to {studio_name}.</p>
      <p>Whether life got busy or you're looking for something different,
      we're here for you. We have classes every week and would love to
      see your face again.</p>
      <p>Just reply to this email if you have any questions, want a
      class recommendation, or need help getting back on the schedule.</p>
      <p style="margin-top: 24px;">Warmly,<br/>{studio_name} Team</p>
    </div>
    """

    try:
        # Atomic claim BEFORE send. Flip churn_outreach_sent_at from
        # "either NULL or older than 7 days" → NOW() in a single UPDATE,
        # and only proceed if we won the claim. Without this, two
        # parallel runs (or a stuck task that re-fires) both see the
        # member as eligible, both call send_email, and the member
        # receives two identical winback emails seconds apart — exactly
        # the bug Don reported on 2026-04-28 where every flagged member
        # was getting a pair of "We miss you at Your Studio…"
        # emails.
        async with get_tenant_db(schema_override=schema) as db:
            claimed = await db.fetchval(
                """
                UPDATE members
                SET churn_outreach_sent_at = NOW(), updated_at = NOW()
                WHERE id = $1
                  AND (churn_outreach_sent_at IS NULL
                       OR churn_outreach_sent_at < NOW() - INTERVAL '7 days')
                RETURNING id
                """,
                member_id,
            )
        if not claimed:
            logger.info(
                "Winback skipped — already claimed by another run",
                schema=schema, member_id=str(member_id),
            )
            return False

        # Send via studio's own email service (SMTP/SendGrid) — never AuraFlow's
        from app.core.tenant_context import set_tenant_context, clear_tenant_context
        from app.services.email.email_service import EmailService

        # Set tenant context so email service finds studio credentials
        org_id = None
        async with get_global_db() as gdb:
            org_row = await gdb.fetchrow(
                "SELECT id FROM af_global.organizations WHERE schema_name = $1", schema
            )
            if org_row:
                org_id = str(org_row["id"])
        set_tenant_context(
            organization_id=org_id or "churn",
            schema_name=schema,
            slug=schema.replace("af_tenant_", ""),
        )
        send_failed = False
        try:
            email_svc = EmailService()
            result = await email_svc.send_email(
                to_email=email,
                subject=f"We miss you at {studio_name}, {first_name}!",
                html_content=html_content,
                member_id=str(member_id),
                email_type="winback",
            )
            if result.get("status") == "failed":
                send_failed = True
                logger.warning("Winback email failed — studio email unavailable", schema=schema, email=email)
        finally:
            clear_tenant_context()

        if send_failed:
            # Reset the claim so a future run can retry. Without this,
            # one transient SMTP blip silences a flagged member for the
            # full 7-day re-eligibility window.
            async with get_tenant_db(schema_override=schema) as db:
                await db.execute(
                    "UPDATE members SET churn_outreach_sent_at = NULL WHERE id = $1",
                    member_id,
                )
            return False

        logger.info("Winback email sent", schema=schema, member_id=str(member_id), email=email)
        return True
    except Exception as e:
        # Same recovery on unexpected failure.
        try:
            async with get_tenant_db(schema_override=schema) as db:
                await db.execute(
                    "UPDATE members SET churn_outreach_sent_at = NULL WHERE id = $1",
                    member_id,
                )
        except Exception:
            pass
        logger.warning("Winback email failed", schema=schema, member_id=str(member_id), error=str(e))
        return False


async def _scan_all_tenants() -> dict:
    """Run churn scan across all active tenant schemas and auto-send winback."""
    import asyncio as _asyncio

    total_flagged = 0
    total_cleared = 0
    total_outreach_sent = 0

    async with get_global_db() as db:
        schemas = await db.fetch(
            "SELECT schema_name FROM af_global.organizations WHERE status IN ('active', 'trial')"
        )

    for row in schemas:
        schema = row["schema_name"]
        try:
            result = await churn_svc.scan_tenant_churn(schema_override=schema)
            total_flagged += result["newly_flagged"]
            total_cleared += result["cleared"]

            # Auto-send winback to ALL flagged members who haven't been contacted
            async with get_tenant_db(schema_override=schema) as db:
                flagged_members = await db.fetch(
                    """
                    SELECT id, first_name, last_name, email
                    FROM members
                    WHERE churn_risk_flagged_at IS NOT NULL
                      AND is_active = TRUE
                      AND email IS NOT NULL
                      AND (churn_outreach_sent_at IS NULL OR churn_outreach_sent_at < NOW() - INTERVAL '7 days')
                      AND (email_opt_in IS NULL OR email_opt_in = TRUE)
                    ORDER BY churn_risk_flagged_at ASC
                    """
                )
                flagged_members = [dict(r) for r in flagged_members]
            if not flagged_members:
                continue

            # Fetch studio name for email personalization
            studio_name = "our studio"
            try:
                async with get_tenant_db(schema_override=schema) as db:
                    studio_row = await db.fetchrow(
                        "SELECT name FROM studios WHERE is_active = TRUE LIMIT 1"
                    )
                    if studio_row:
                        studio_name = studio_row["name"]
            except Exception:
                pass

            # Send winback emails with spacing — query already filtered eligible members
            sent = 0
            for m in flagged_members[:MAX_WINBACK_PER_TENANT]:
                success = await _send_winback_for_member(schema, m, studio_name)
                if success:
                    sent += 1
                # Space out sends
                if sent < len(flagged_members[:MAX_WINBACK_PER_TENANT]):
                    await _asyncio.sleep(SEND_SPACING_SECONDS)

            total_outreach_sent += sent
            if sent:
                logger.info(
                    "Auto winback outreach complete for tenant",
                    schema=schema,
                    sent=sent,
                    eligible=len(flagged_members[:MAX_WINBACK_PER_TENANT]),
                )

        except Exception as e:
            logger.error(
                "Churn scan failed for tenant",
                schema=row["schema_name"],
                error=str(e),
            )

    return {
        "total_flagged": total_flagged,
        "total_cleared": total_cleared,
        "total_outreach_sent": total_outreach_sent,
    }


@app.task(
    name="app.workers.tasks.churn_scan.daily_churn_scan",
    time_limit=3600,        # 60 min hard — email spacing can push runtime past default 10 min
    soft_time_limit=3300,   # 55 min soft
)
def daily_churn_scan():
    """Celery task: daily churn risk scan + automatic winback outreach for all tenants."""
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_scan_all_tenants())
        logger.info(
            "Daily churn scan complete",
            flagged=result["total_flagged"],
            cleared=result["total_cleared"],
            outreach_sent=result["total_outreach_sent"],
        )
        return result
    finally:
        loop.close()
