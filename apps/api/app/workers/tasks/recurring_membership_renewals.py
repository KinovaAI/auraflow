"""
Recurring membership renewal scheduler — Square-mode studios.

AuraFlow owns the recurrence (NOT Square Subscriptions, which don't
support `app_fee_money` and would forfeit the 1% platform fee). Every
24 hours this task:

1. Scans every Square-mode tenant for member_memberships rows whose
   `current_period_end` falls within the next 24h and status='active'.
2. Charges the saved card (`square_card_id`) for `membership_type.price_cents`
   via Square `CreatePayment` with `app_fee_money=1%`.
3. On success: extends `current_period_end` and `ends_at` by one billing
   period; records the transaction with the 1% fee.
4. On failure: flips status to 'past_due' and logs.

The same path is used by `purchase_membership_square` for the FIRST
charge — so first-cycle and renewal cycles both deposit 1% to KinovaAI.
"""
import asyncio

from app.core.logging import logger
from app.db.session import get_global_db, get_tenant_db
from app.core.tenant_context import set_tenant_context_from_schema, clear_tenant_context
from app.services.payments import billing_dispatcher
from app.services.email.email_service import EmailService
from app.workers.celery_app import app

_email_svc = EmailService()


_PERIOD_SQL = {
    "weekly": "INTERVAL '7 days'",
    "monthly": "INTERVAL '1 month'",
    "annual": "INTERVAL '1 year'",
    "yearly": "INTERVAL '1 year'",
}


async def _renew_one(schema: str, org_id: str, row: dict) -> dict:
    period_sql = _PERIOD_SQL.get((row["billing_period"] or "monthly").lower(), "INTERVAL '1 month'")
    member_id = str(row["member_id"])
    mt_id = str(row["membership_type_id"])
    membership_id = str(row["id"])
    price = int(row["price_cents"])
    card_id = row["square_card_id"]
    customer_id = row["square_customer_id"]
    # A free trial converts on its first charge: trial_period_end is set and the
    # period hasn't been rolled past it yet. This is the SAME charge path as a
    # renewal (one charger, no double-charge) — we just notify the member that
    # their trial has converted (or failed) instead of staying silent.
    is_trial_conversion = (
        row.get("trial_period_end") is not None
        and row.get("current_period_end") is not None
        and row["current_period_end"] <= row["trial_period_end"]
    )
    amount_display = f"${price / 100:.2f}"
    member_email = row.get("email")
    member_first = row.get("first_name") or "there"
    if not card_id:
        logger.error("Renewal skipped — no card on file", membership_id=membership_id, member_id=member_id)
        async with get_tenant_db(schema_override=schema) as db:
            await db.execute(
                "UPDATE member_memberships SET status='past_due', updated_at=NOW() WHERE id=$1",
                membership_id,
            )
        return {"membership_id": membership_id, "outcome": "skipped_no_card"}
    try:
        payment = await billing_dispatcher.create_payment(
            organization_id=org_id,
            amount_cents=price,
            source_id=card_id,
            description=f"{row['name']} — renewal",
            member_id=member_id,
            member_square_customer_id=customer_id,
            idempotency_key=f"renew:{membership_id}:{row['current_period_end'].isoformat()}",
        )
    except Exception as e:
        logger.error("Renewal charge failed", membership_id=membership_id, error=str(e))
        async with get_tenant_db(schema_override=schema) as db:
            await db.execute(
                "UPDATE member_memberships SET status='past_due', updated_at=NOW() WHERE id=$1",
                membership_id,
            )
        # Tell trial members their first charge failed (regular renewals already
        # have the dunning/escalation flow; a failed trial conversion otherwise
        # goes silent). Best-effort — never let email break the renewal sweep.
        if is_trial_conversion and member_email:
            try:
                await _email_svc.send_payment_failed(
                    member_id=member_id, to_email=member_email,
                    member_name=member_first, membership_name=row["name"],
                    amount_display=amount_display,
                )
            except Exception as ee:
                logger.warning("Trial payment-failed email failed", membership_id=membership_id, error=str(ee))
        return {"membership_id": membership_id, "outcome": "charge_failed", "error": str(e)}

    async with get_tenant_db(schema_override=schema) as db:
        await db.execute(
            f"""
            UPDATE member_memberships
            SET current_period_end = current_period_end + {period_sql},
                ends_at = COALESCE(ends_at, current_period_end) + {period_sql},
                updated_at = NOW()
            WHERE id = $1
            """,
            membership_id,
        )
        await db.execute(
            """
            INSERT INTO transactions
                (member_id, amount_cents, type, status, description,
                 square_payment_id, fee_cents, net_amount_cents, created_at)
            VALUES ($1, $2, 'subscription', 'completed', $3, $4, $5, $6, NOW())
            """,
            member_id, price, f"{row['name']} renewal",
            payment["payment_id"], payment["fee_cents"],
            price - payment["fee_cents"],
        )
    # Trial just converted to paid — send the first receipt so the member knows
    # the free period ended and they're now an active paying member.
    if is_trial_conversion and member_email:
        try:
            await _email_svc.send_payment_receipt(
                member_id=member_id, to_email=member_email,
                member_name=member_first, amount_display=amount_display,
                description=f"{row['name']} — first payment (trial ended)",
            )
        except Exception as ee:
            logger.warning("Trial conversion receipt failed", membership_id=membership_id, error=str(ee))

    logger.info(
        "Membership renewed",
        membership_id=membership_id, member_id=member_id,
        amount_cents=price, fee_cents=payment["fee_cents"],
        trial_conversion=is_trial_conversion,
    )
    return {
        "membership_id": membership_id,
        "outcome": "renewed",
        "payment_id": payment["payment_id"],
        "trial_conversion": is_trial_conversion,
    }


async def _renew_tenant(schema: str, org_id: str) -> list[dict]:
    await set_tenant_context_from_schema(schema)
    try:
        async with get_tenant_db(schema_override=schema) as db:
            due = await db.fetch(
                """
                SELECT mm.id, mm.member_id, mm.membership_type_id, mm.square_card_id,
                       mm.current_period_end, mm.trial_period_end,
                       mt.name, mt.price_cents, mt.billing_period,
                       m.square_customer_id, m.email, m.first_name
                FROM member_memberships mm
                JOIN membership_types mt ON mt.id = mm.membership_type_id
                JOIN members m ON m.id = mm.member_id
                WHERE mm.billing_provider = 'square'
                  AND mm.status = 'active'
                  AND mm.current_period_end IS NOT NULL
                  AND mm.current_period_end <= NOW() + INTERVAL '1 day'
                  AND mt.price_cents > 0
                """
            )
        results = []
        for r in due:
            results.append(await _renew_one(schema, org_id, dict(r)))
        return results
    finally:
        clear_tenant_context()


async def _renew_all() -> dict:
    async with get_global_db() as db:
        orgs = await db.fetch(
            "SELECT id, schema_name, name FROM af_global.organizations WHERE billing_provider='square'"
        )
    by_tenant = {}
    total_renewed = 0
    total_failed = 0
    for org in orgs:
        results = await _renew_tenant(org["schema_name"], str(org["id"]))
        by_tenant[org["name"]] = results
        for r in results:
            if r["outcome"] == "renewed":
                total_renewed += 1
            elif r["outcome"] in ("charge_failed", "skipped_no_card"):
                total_failed += 1
    return {"total_renewed": total_renewed, "total_failed": total_failed, "by_tenant": by_tenant}


@app.task(name="app.workers.tasks.recurring_membership_renewals.run_renewals")
def run_renewals():
    loop = asyncio.new_event_loop()
    try:
        summary = loop.run_until_complete(_renew_all())
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        loop.close()
    logger.info("Membership renewals run", **summary)
    return summary
