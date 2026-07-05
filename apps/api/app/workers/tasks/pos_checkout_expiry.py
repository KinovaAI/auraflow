"""AuraFlow — POS Terminal Checkout Expiry + Reconciliation Task

Runs every 5 minutes. Has two jobs:

1. **Reconcile pending/in_progress deeplink checkouts** that may have
   succeeded on Square but never landed our callback. For each, search
   Square Payments API for any COMPLETED payment in the time window with
   the matching amount. If exactly one match → mark our row completed,
   create the transactions ledger row, enroll into the course (for
   workshop walk-ins). This catches the "callback got lost in mobile
   browser hand-off" failure mode that left 3 Sat 2026-06-13 Sound Bath
   walk-ins paid-but-not-on-roster.
2. **Expire genuinely-abandoned rows** that are past their `expires_at`
   and have no matching Square payment. Mark `expired` so the UI knows
   the device is free.

Why this matters:
  - The POS deeplink callback navigates the browser away from the page
    that initiated the charge; mobile browser context loss is common.
    Without server-side reconciliation, every dropped callback = money
    landed in Square but no AuraFlow record.
  - Webhooks don't help here either — POS deeplink payments don't
    carry our `auraflow_*` order metadata (no order is created via API),
    so the square_webhook_handler can't auto-fulfill them.
"""
import asyncio

from app.core.logging import logger
from app.db.session import get_global_db, get_tenant_db
from app.services.payments.square_oauth_service import square_oauth_service
from app.services.payments.square_pos_service import square_pos_service
from app.workers.celery_app import app


async def _find_matching_square_payment(
    access_token: str,
    amount_cents: int,
    initiated_at,
    window_minutes: int = 8,
) -> dict | None:
    """Search Square Payments API for a single COMPLETED payment matching
    amount_cents within window_minutes of initiated_at. Returns the payment
    dict or None if 0 or >1 matches (ambiguous → manual)."""
    from datetime import timedelta
    import httpx
    begin = (initiated_at - timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = (initiated_at + timedelta(minutes=window_minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
    headers = {"Authorization": f"Bearer {access_token}", "Square-Version": "2026-01-22"}
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                "https://connect.squareup.com/v2/payments",
                headers=headers,
                params={"begin_time": begin, "end_time": end, "limit": 100},
            )
        if r.status_code != 200:
            return None
        matches = [
            p for p in (r.json().get("payments") or [])
            if p.get("status") == "COMPLETED"
            and (p.get("amount_money") or {}).get("amount") == amount_cents
        ]
        if len(matches) == 1:
            return matches[0]
        return None
    except Exception as e:
        logger.warning("Square payments search failed", error=str(e))
        return None


async def _reconcile_one(schema: str, row: dict, access_token: str | None) -> str:
    """Try to reconcile a single in-flight checkout with Square. Returns
    one of: 'reconciled', 'expired', 'still_pending', 'no_token'."""
    if not access_token:
        return "no_token"

    match = await _find_matching_square_payment(
        access_token=access_token,
        amount_cents=row["amount_cents"],
        initiated_at=row["initiated_at"],
    )

    if match:
        payment_id = match["id"]
        async with get_tenant_db(schema_override=schema) as db:
            async with db.transaction():
                # Mark the checkout completed + link the REAL Payments
                # API id (not Square POS's legacy transaction_id).
                await db.execute(
                    """
                    UPDATE pos_terminal_checkouts
                    SET status = 'completed',
                        completed_at = COALESCE(completed_at, NOW()),
                        square_payment_id = $2,
                        failure_reason = NULL
                    WHERE id = $1
                    """,
                    row["id"], payment_id,
                )
                # Idempotent ledger insert keyed by checkout-id-in-desc.
                existing_txn = await db.fetchval(
                    """
                    SELECT id FROM transactions
                    WHERE member_id = $1 AND type = 'pos_sale'
                      AND amount_cents = $2
                      AND (description LIKE '%' || $3 || '%'
                           OR square_payment_id = $4)
                      AND created_at >= NOW() - INTERVAL '24 hours'
                    """,
                    row["member_id"], row["amount_cents"],
                    str(row["id"])[:8], payment_id,
                )
                if existing_txn:
                    txn_db_id = existing_txn
                    await db.execute(
                        """
                        UPDATE transactions
                        SET square_payment_id = COALESCE(square_payment_id, $2)
                        WHERE id = $1
                        """,
                        existing_txn, payment_id,
                    )
                else:
                    txn_row = await db.fetchrow(
                        """
                        INSERT INTO transactions
                            (member_id, amount_cents, type, status, description,
                             square_payment_id, fee_cents, net_amount_cents, created_at)
                        VALUES ($1, $2, 'pos_sale', 'completed', $3, $4, 0, $2, $5)
                        RETURNING id
                        """,
                        row["member_id"], row["amount_cents"],
                        f"{row['description'] or 'POS sale (phone)'} [ck:{str(row['id'])[:8]}]",
                        payment_id, row["initiated_at"],
                    )
                    txn_db_id = txn_row["id"]
                # Workshop walk-in enrollment, idempotent on UNIQUE (course_id, member_id).
                if row.get("course_id"):
                    await db.execute(
                        """
                        INSERT INTO course_enrollments
                            (course_id, member_id, status, paid_price_cents,
                             transaction_id, enrolled_at)
                        VALUES ($1, $2, 'enrolled', $3, $4, $5)
                        ON CONFLICT (course_id, member_id) DO NOTHING
                        """,
                        row["course_id"], row["member_id"],
                        row["amount_cents"], txn_db_id, row["initiated_at"],
                    )
        logger.info(
            "POS checkout reconciled from Square Payments search",
            checkout_id=str(row["id"]), payment_id=payment_id,
            amount=row["amount_cents"],
            course_id=str(row["course_id"]) if row.get("course_id") else None,
        )
        return "reconciled"

    # No matching Square payment found.
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    if row["expires_at"] <= now:
        if row.get("square_checkout_id"):
            try:
                await square_pos_service.cancel_terminal_checkout(
                    merchant_access_token=access_token,
                    checkout_id=row["square_checkout_id"],
                )
            except Exception as e:
                logger.warning(
                    "Square cancel during expiry sweep failed (continuing)",
                    checkout_id=row["square_checkout_id"], error=str(e),
                )
        async with get_tenant_db(schema_override=schema) as db:
            await db.execute(
                """
                UPDATE pos_terminal_checkouts
                SET status = 'expired',
                    completed_at = NOW(),
                    failure_reason = COALESCE(failure_reason, 'auto_expired')
                WHERE id = $1 AND status IN ('pending', 'in_progress')
                """,
                row["id"],
            )
        return "expired"
    return "still_pending"


async def _sweep_one_tenant(schema_name: str, org_id: str, access_token: str | None) -> dict:
    """Sweep a single tenant. Returns counts by outcome."""
    counts = {"reconciled": 0, "expired": 0, "still_pending": 0, "no_token": 0}
    async with get_tenant_db(schema_override=schema_name) as db:
        # Two pools to chase:
        #   1) past-expiry rows (the original sweep target)
        #   2) recent in-flight rows where the callback hasn't landed yet —
        #      we try the reconciliation EARLY so paid walk-ins land on
        #      the roster within ~5min instead of waiting for expiry.
        rows = await db.fetch(
            """
            SELECT id, member_id, amount_cents, square_checkout_id,
                   square_customer_id, description, flow, course_id,
                   initiated_at, expires_at
            FROM pos_terminal_checkouts
            WHERE status IN ('pending', 'in_progress')
              AND initiated_at >= NOW() - INTERVAL '2 hours'
            ORDER BY initiated_at
            LIMIT 100
            """,
        )
    for r in rows:
        outcome = await _reconcile_one(schema_name, dict(r), access_token)
        counts[outcome] = counts.get(outcome, 0) + 1
    return counts


async def _sweep_all() -> dict:
    per_tenant: dict[str, dict] = {}
    totals = {"reconciled": 0, "expired": 0, "still_pending": 0, "no_token": 0}
    async with get_global_db() as gdb:
        orgs = await gdb.fetch(
            """
            SELECT id, schema_name
            FROM af_global.organizations
            WHERE billing_provider = 'square' AND status IN ('active', 'trial')
            """,
        )
    for o in orgs:
        org_id = str(o["id"])
        try:
            access_token = await square_oauth_service.get_merchant_access_token(org_id)
        except Exception:
            access_token = None
        counts = await _sweep_one_tenant(o["schema_name"], org_id, access_token)
        if any(v for v in counts.values()):
            per_tenant[o["schema_name"]] = counts
            for k, v in counts.items():
                totals[k] = totals.get(k, 0) + v
    return {"totals": totals, "per_tenant": per_tenant}


@app.task(name="pos.expire_stale_checkouts")
def expire_stale_pos_checkouts():
    """Celery beat entry. Schedule to run every 5 minutes."""
    result = asyncio.run(_sweep_all())
    if any(v for v in result["totals"].values()):
        logger.info("POS checkout reconciliation sweep", **result)
    return result
