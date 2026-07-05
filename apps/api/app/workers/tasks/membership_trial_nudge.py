"""AuraFlow — Online-membership free-trial ending nudge.

Runs daily via Celery Beat. Emails members whose free trial converts to its
first paid charge in 1–2 days, so they get a heads-up BEFORE the
recurring-renewal scheduler charges the card (that sweep fires ~1 day before
the trial end). Organization-independent: runs across every active tenant and
reads each plan's own price/period.

"Still in trial" = trial_period_end set AND current_period_end <= trial_period_end
(the renewal sweep rolls current_period_end past trial_period_end on the first
charge, which is exactly the conversion).
"""
import asyncio
from datetime import datetime, timezone

from app.core.logging import logger
from app.db.session import get_global_db, get_tenant_db
from app.core.tenant_context import set_tenant_context_from_schema, clear_tenant_context
from app.services.email.email_service import EmailService
from app.workers.celery_app import app
from app.workers.idempotency import acquire_once

email_svc = EmailService()

_PERIOD_LABEL = {"weekly": "week", "monthly": "month", "annual": "year", "yearly": "year"}


async def _nudge_tenant(schema_name: str, org_id: str, tz_name: str) -> int:
    sent = 0
    await set_tenant_context_from_schema(schema_name)
    try:
        async with get_tenant_db(schema_override=schema_name) as db:
            rows = await db.fetch(
                """
                SELECT mm.id AS membership_id, mm.member_id, mm.trial_period_end,
                       mt.name, mt.price_cents, mt.billing_period,
                       m.email, m.first_name, m.email_opt_in
                FROM member_memberships mm
                JOIN membership_types mt ON mt.id = mm.membership_type_id
                JOIN members m ON m.id = mm.member_id
                WHERE mm.status = 'active'
                  AND mm.trial_period_end IS NOT NULL
                  AND mm.current_period_end IS NOT NULL
                  AND mm.current_period_end <= mm.trial_period_end
                  AND mm.trial_period_end BETWEEN NOW() + INTERVAL '1 day'
                                              AND NOW() + INTERVAL '2 days'
                  AND mt.price_cents > 0
                """
            )

        for row in rows:
            if not row.get("email") or not row.get("email_opt_in", True):
                continue
            membership_id = str(row["membership_id"])
            trial_end = row["trial_period_end"]
            # One nudge per trial, even across retries / double runs.
            if not await acquire_once(
                f"trial_nudge:{membership_id}:{trial_end.date()}", ttl=172800
            ):
                continue

            price_label = _PERIOD_LABEL.get((row["billing_period"] or "monthly").lower(), "month")
            amount_display = f"${row['price_cents'] / 100:.2f}/{price_label}"
            try:
                from zoneinfo import ZoneInfo
                end_disp = trial_end.astimezone(ZoneInfo(tz_name or "America/Los_Angeles")).strftime(
                    "%B %d, %Y"
                ).replace(" 0", " ")
            except Exception:
                end_disp = trial_end.strftime("%B %d, %Y")

            name = row["first_name"] or "there"
            subject = "Your free trial ends soon"
            html = f"""
            <h2>Your free trial is ending</h2>
            <p>Hi {name},</p>
            <p>Your free trial of <strong>{row['name']}</strong> ends on
            <strong>{end_disp}</strong>. At that point your card on file will be
            automatically charged <strong>{amount_display}</strong> and your
            membership continues with no interruption.</p>
            <p>Nothing to do if you'd like to keep going. If you'd prefer not to
            continue, just cancel in your member portal before then and you won't
            be charged.</p>
            <p style="color:#666;font-size:12px;">— {row['name']}</p>
            """
            try:
                await email_svc.send_email(
                    to_email=row["email"], subject=subject, html_content=html,
                    member_id=str(row["member_id"]), email_type="trial_ending",
                )
                sent += 1
            except Exception as e:
                logger.warning("Trial-ending nudge failed", membership_id=membership_id, error=str(e))
    finally:
        clear_tenant_context()
    return sent


async def _nudge_all() -> dict:
    total = 0
    async with get_global_db() as db:
        orgs = await db.fetch(
            "SELECT id, schema_name, timezone FROM af_global.organizations "
            "WHERE status IN ('active', 'trial')"
        )
    for org in orgs:
        try:
            total += await _nudge_tenant(org["schema_name"], str(org["id"]), org["timezone"])
        except Exception as e:
            logger.error("Trial nudge failed for tenant", schema=org["schema_name"], error=str(e))
    return {"nudges_sent": total}


@app.task(name="app.workers.tasks.membership_trial_nudge.send_trial_nudges")
def send_trial_nudges():
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_nudge_all())
        logger.info("Trial-ending nudges sent", **result)
        return result
    finally:
        loop.close()
