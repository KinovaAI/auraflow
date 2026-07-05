"""AuraFlow — Payment Failure Escalation Task

Runs daily via Celery Beat. Checks the failed_payment_attempts table
and escalates based on age:
  - Day 3: send SMS reminder (if sms_opt_in)
  - Day 7: send email + SMS "last chance" warning
  - Day 14: suspend the membership
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


async def _escalate_for_tenant(schema_name: str) -> dict:
    """Process payment failure escalation for a single tenant."""
    now = datetime.now(timezone.utc)
    counts = {"sms_day3": 0, "email_day7": 0, "sms_day7": 0, "suspended": 0, "auto_resolved": 0}

    async with get_tenant_db(schema_override=schema_name) as db:
        # Find unresolved failed payment attempts with member details
        rows = await db.fetch(
            """
            SELECT fp.id AS fp_id, fp.member_id, fp.membership_id,
                   fp.amount_cents, fp.created_at AS failed_at,
                   m.first_name, m.last_name, m.email, m.phone_enc,
                   m.email_opt_in, m.sms_opt_in,
                   mm.status AS membership_status
            FROM failed_payment_attempts fp
            JOIN members m ON m.id = fp.member_id
            LEFT JOIN member_memberships mm ON mm.id = fp.membership_id
            WHERE fp.resolved_at IS NULL
              AND fp.created_at < $1
            ORDER BY fp.created_at ASC
            """,
            now - timedelta(days=3),
        )

        for row in rows:
            member_id = str(row["member_id"])
            fp_id = str(row["fp_id"])
            days_since = (now - row["failed_at"]).days
            name = row["first_name"]
            amount_display = f"${row['amount_cents'] / 100:.2f}"
            member_phone = decrypt_phone(row)

            # Defensive auto-resolve: never dun a member who has actually paid.
            # A failed attempt is stale/recovered if EITHER a completed payment
            # landed at/after the failure (same membership, a subscription
            # payment, or — for membership_id-NULL orphan rows — any payment),
            # OR the member currently holds an active membership paid up into
            # the future. This catches orphaned signup-time declines (e.g. a
            # card that failed several times before the charge succeeded) that
            # otherwise never link to a membership and never clear, and acts as
            # a backstop for any renewal the success-webhook missed.
            recovered = await db.fetchval(
                """
                SELECT 1
                WHERE EXISTS (
                    SELECT 1 FROM transactions t
                    WHERE t.member_id = $1
                      AND t.status = 'completed'
                      AND t.created_at >= $2
                      AND ($3::uuid IS NULL OR t.membership_id = $3 OR t.type = 'subscription')
                )
                OR EXISTS (
                    SELECT 1 FROM member_memberships mm
                    WHERE mm.member_id = $1
                      AND mm.status = 'active'
                      AND COALESCE(mm.current_period_end, mm.ends_at) > $4
                )
                """,
                row["member_id"], row["failed_at"], row["membership_id"], now,
            )
            if recovered:
                await db.execute(
                    "UPDATE failed_payment_attempts SET resolved = TRUE, resolved_at = NOW() WHERE id = $1",
                    fp_id,
                )
                counts["auto_resolved"] += 1
                logger.info(
                    "Auto-resolved recovered failed-payment attempt",
                    member_id=member_id, fp_id=fp_id, schema=schema_name,
                )
                continue

            # Day 14+: suspend membership
            if days_since >= 14 and row.get("membership_id") and row.get("membership_status") not in ("suspended", "cancelled"):
                await db.execute(
                    """
                    UPDATE member_memberships
                    SET status = 'suspended', updated_at = NOW()
                    WHERE id = $1 AND status IN ('active', 'paused', 'frozen')
                    """,
                    row["membership_id"],
                )
                # Mark as resolved
                await db.execute(
                    "UPDATE failed_payment_attempts SET resolved_at = NOW() WHERE id = $1",
                    fp_id,
                )
                counts["suspended"] += 1

                # Send suspension notification email
                if row.get("email_opt_in", True) and row.get("email"):
                    try:
                        await email_svc.send_email(
                            to_email=row["email"],
                            subject="Your membership has been suspended",
                            html_content=f"""
                            <h2>Membership Suspended</h2>
                            <p>Hi {name},</p>
                            <p>Your membership has been suspended due to an outstanding
                            payment of {amount_display} that has remained unpaid for 14 days.</p>
                            <p>Please update your payment method to restore access.</p>
                            <p style="color: #666; font-size: 12px;">— AuraFlow</p>
                            """,
                            member_id=member_id,
                            email_type="payment_suspension",
                        )
                    except Exception as e:
                        logger.warning("Suspension email failed", member_id=member_id, error=str(e))

                continue

            # Day 7+: send email + SMS "last chance"
            if days_since >= 7:
                # Dedup: check if already sent day7 escalation
                existing = await db.fetchval(
                    """
                    SELECT COUNT(*) FROM communication_log
                    WHERE member_id = $1 AND type = 'payment_escalation_day7'
                      AND created_at > $2
                    """,
                    member_id, now - timedelta(hours=24),
                )
                if existing > 0:
                    continue

                # Send email
                if row.get("email_opt_in", True) and row.get("email"):
                    try:
                        await email_svc.send_email(
                            to_email=row["email"],
                            subject="Last chance: update your payment method",
                            html_content=f"""
                            <h2>Payment Past Due — Last Chance</h2>
                            <p>Hi {name},</p>
                            <p>We still haven't been able to process your payment of
                            {amount_display}. Your membership will be <strong>suspended
                            in 7 days</strong> if the payment is not resolved.</p>
                            <p>Please update your payment method now to avoid losing access.</p>
                            <p style="color: #666; font-size: 12px;">— AuraFlow</p>
                            """,
                            member_id=member_id,
                            email_type="payment_escalation_day7",
                        )
                        counts["email_day7"] += 1
                    except Exception as e:
                        logger.warning("Day 7 email failed", member_id=member_id, error=str(e))

                # Send SMS
                if row.get("sms_opt_in", True) and member_phone:
                    try:
                        await sms_svc.send_sms(
                            to_phone=member_phone,
                            body=f"Hi {name}, your payment of {amount_display} is overdue. "
                                 f"Please update your payment method to avoid losing access. "
                                 f"Your membership will be suspended in 7 days.",
                            member_id=member_id,
                            sms_type="payment_escalation",
                        )
                        counts["sms_day7"] += 1
                    except Exception as e:
                        logger.warning("Day 7 SMS failed", member_id=member_id, error=str(e))

                continue

            # Day 3+: send SMS only (if opted in)
            if days_since >= 3:
                # Dedup
                existing = await db.fetchval(
                    """
                    SELECT COUNT(*) FROM communication_log
                    WHERE member_id = $1 AND type = 'payment_escalation_day3'
                      AND created_at > $2
                    """,
                    member_id, now - timedelta(hours=24),
                )
                if existing > 0:
                    continue

                if row.get("sms_opt_in", True) and member_phone:
                    try:
                        await sms_svc.send_sms(
                            to_phone=member_phone,
                            body=f"Hi {name}, we were unable to process your payment of "
                                 f"{amount_display}. Please update your payment method to "
                                 f"keep your membership active.",
                            member_id=member_id,
                            sms_type="payment_escalation",
                        )
                        counts["sms_day3"] += 1
                    except Exception as e:
                        logger.warning("Day 3 SMS failed", member_id=member_id, error=str(e))

    return counts


async def _escalate_all_tenants() -> dict:
    """Run payment escalation across all tenants."""
    totals = {"sms_day3": 0, "email_day7": 0, "sms_day7": 0, "suspended": 0, "auto_resolved": 0}

    async with get_global_db() as db:
        schemas = await db.fetch(
            "SELECT schema_name FROM af_global.organizations WHERE status IN ('active', 'trial')"
        )

    for row in schemas:
        try:
            counts = await _escalate_for_tenant(row["schema_name"])
            for k, v in counts.items():
                totals[k] += v
        except Exception as e:
            logger.error(
                "Payment escalation failed for tenant",
                schema=row["schema_name"],
                error=str(e),
            )

    return totals


@app.task(name="app.workers.tasks.payment_escalation.run_payment_escalation")
def run_payment_escalation():
    """Celery task: escalate failed payments across all tenants."""
    loop = asyncio.new_event_loop()
    try:
        totals = loop.run_until_complete(_escalate_all_tenants())
        logger.info("Payment escalation completed", **totals)
        return totals
    finally:
        loop.close()
