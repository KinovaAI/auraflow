"""AuraFlow sales → books, automatically.

The whole point of the module: every dollar AuraFlow takes in must land in the
books, itemized and categorized, with no separation. This posts EVERY AuraFlow
sale into acct_transactions as a source='auraflow' income row:

  - `transactions`      — memberships, subscriptions, classes, drop-ins, private
                          sessions, course enrollments, POS-via-payments, etc.
  - `pos_transactions`  — the retail POS module (card + cash).

Sales are booked at **gross** (Schedule C Line 1 gross receipts). Processing fees
and the settlement of these sales against the bank are handled in
reconciliation.py, so gross sales − fees == the net bank deposit and nothing is
double-counted. Refunds are booked as a Returns & Allowances contra (Line 2).

Every income row carries `processor_payment_id` (Stripe charge / Square payment
id) so reconciliation can tie it to the payout that settled it. Cash sales have
no processor id and settle against cash bank deposits instead.

Deduped on (source, external_id): 'txn:<id>' / 'pos:<id>' / 'ret:<id>'. Re-running
is idempotent and refreshes amounts/categories. `db` is tenant-scoped.
"""
from app.core.logging import logger

# AuraFlow transactions.type → itemized income category (by PRODUCT, not rail).
_TXN_CATEGORY = {
    "subscription": "subscriptions",
    "membership_purchase": "subscriptions",
    "payment": "class_revenue",
    "drop_in": "class_revenue",
    "course_enrollment": "workshops",
    "workshop": "workshops",
    "private_session": "private_sessions",
    "pos_sale": "tshirt_sales",
    "gift_card": "tshirt_sales",
}
_DEFAULT_INCOME = "class_revenue"
_RETURNS = "returns_allowances"

# Revenue-bearing transaction statuses (a refunded payment still happened; its
# reversal is booked separately as a 'refund' row).
_INCOME_STATUSES = ("completed", "refunded")


def _processor_id(r) -> str | None:
    return (
        r.get("stripe_charge_id")
        or r.get("stripe_payment_intent_id")
        or r.get("square_payment_id")
    )


# courses.type → income category
_COURSE_CATEGORY = {
    "workshop": "workshops",
    "course": "workshops",
    "retreat": "workshops",
    "teacher_training": "workshops",
}


async def _product_map(db) -> dict:
    """transaction_id → income category, resolved from the REAL product records
    (the same source payroll uses), not from a guess at transactions.type.

      course_enrollments → Workshops (by courses.type)
      private_bookings   → Private Sessions
    """
    pmap: dict[str, str] = {}
    for r in await db.fetch(
        """
        SELECT ce.transaction_id, c.type
        FROM course_enrollments ce
        JOIN courses c ON c.id = ce.course_id
        WHERE ce.transaction_id IS NOT NULL AND ce.status <> 'withdrawn'
        """
    ):
        pmap[str(r["transaction_id"])] = _COURSE_CATEGORY.get(r["type"], "workshops")
    for r in await db.fetch(
        "SELECT transaction_id FROM private_bookings "
        "WHERE transaction_id IS NOT NULL AND status NOT IN ('cancelled', 'no_show')"
    ):
        pmap[str(r["transaction_id"])] = "private_sessions"
    return pmap


async def _upsert(db, *, external_id, txn_date, description, ttype, category,
                  amount_cents, member_id, processor_payment_id):
    await db.execute(
        """
        INSERT INTO acct_transactions
            (txn_date, description, type, category, amount_cents, source,
             external_id, member_id, processor_payment_id, status)
        VALUES ($1,$2,$3,$4,$5,'auraflow',$6,$7,$8,'pending')
        ON CONFLICT (source, external_id) WHERE external_id IS NOT NULL
        DO UPDATE SET
            amount_cents = EXCLUDED.amount_cents,
            category = CASE
                WHEN acct_transactions.status = 'reconciled' THEN acct_transactions.category
                ELSE EXCLUDED.category END,
            description = EXCLUDED.description,
            processor_payment_id = EXCLUDED.processor_payment_id,
            updated_at = NOW()
        """,
        txn_date, description, ttype, category, abs(amount_cents),
        external_id, member_id, processor_payment_id,
    )


async def sync_income(db) -> dict:
    """Post every AuraFlow sale into the books. Returns counts."""
    booked = returns = pos = 0

    ws = pv = 0
    covered: set[str] = set()  # transaction ids booked via a product record (dedup)

    # 1a. Workshops — booked from course_enrollments, exactly like payroll
    #     (revenue = SUM(paid_price_cents) per course, dated by the course).
    for c in await db.fetch(
        """
        SELECT c.id, c.type, c.title, c.starts_at,
               COALESCE(SUM(ce.paid_price_cents), 0) AS revenue,
               array_remove(array_agg(ce.transaction_id), NULL) AS txn_ids
        FROM courses c
        LEFT JOIN course_enrollments ce ON ce.course_id = c.id
            AND ce.status IN ('enrolled', 'completed')
        WHERE c.status IN ('published', 'completed')
        GROUP BY c.id, c.type, c.title, c.starts_at
        HAVING COALESCE(SUM(ce.paid_price_cents), 0) > 0
        """
    ):
        d = c["starts_at"].date() if c["starts_at"] else None
        if not d:
            continue
        await _upsert(
            db, external_id=f"course:{c['id']}", txn_date=d,
            description=c["title"] or "Workshop", ttype="income",
            category=_COURSE_CATEGORY.get(c["type"], "workshops"),
            amount_cents=c["revenue"], member_id=None, processor_payment_id=None,
        )
        for t in (c["txn_ids"] or []):
            covered.add(str(t))
        ws += 1

    # 1b. Private sessions — booked from private_bookings, exactly like payroll.
    for pb in await db.fetch(
        """
        SELECT pb.id, pb.starts_at, pb.member_id, pb.transaction_id,
               COALESCE(NULLIF(pb.price_cents, 0),
                   CASE WHEN COALESCE(ps.package_sessions, 0) > 0
                        THEN ps.package_price_cents / ps.package_sessions
                        ELSE NULLIF(ps.price_cents, 0) END, 0) AS revenue
        FROM private_bookings pb
        LEFT JOIN private_services ps ON ps.id = pb.private_service_id
        WHERE pb.status = 'completed'
        """
    ):
        if not pb["revenue"]:
            continue
        d = pb["starts_at"].date() if pb["starts_at"] else None
        if not d:
            continue
        await _upsert(
            db, external_id=f"priv:{pb['id']}", txn_date=d,
            description="Private session", ttype="income",
            category="private_sessions", amount_cents=pb["revenue"],
            member_id=pb["member_id"], processor_payment_id=None,
        )
        if pb["transaction_id"]:
            covered.add(str(pb["transaction_id"]))
        pv += 1

    # 1c. Everything else from transactions (subscriptions, class payments),
    #     skipping any payment already booked as a workshop/private above.
    txns = await db.fetch(
        """
        SELECT id, member_id, amount_cents, type, status, description,
               stripe_charge_id, stripe_payment_intent_id, square_payment_id,
               created_at
        FROM transactions
        WHERE status = ANY($1) AND amount_cents <> 0
        """,
        list(_INCOME_STATUSES),
    )
    for r in txns:
        r = dict(r)
        if str(r["id"]) in covered:
            continue
        date = r["created_at"].date() if r["created_at"] else None
        if not date:
            continue
        is_refund = r["type"] == "refund" or (r["amount_cents"] or 0) < 0
        if is_refund:
            await _upsert(
                db, external_id=f"ret:{r['id']}", txn_date=date,
                description=r["description"] or "Refund",
                ttype="income", category=_RETURNS,
                amount_cents=r["amount_cents"], member_id=r["member_id"],
                processor_payment_id=None,
            )
            returns += 1
        else:
            await _upsert(
                db, external_id=f"txn:{r['id']}", txn_date=date,
                description=r["description"] or (r["type"] or "Sale").replace("_", " ").title(),
                ttype="income", category=_TXN_CATEGORY.get(r["type"], _DEFAULT_INCOME),
                amount_cents=r["amount_cents"], member_id=r["member_id"],
                processor_payment_id=_processor_id(r),
            )
            booked += 1

    # 2. pos_transactions (retail POS — card + cash)
    pos_rows = await db.fetch(
        """
        SELECT id, member_id, total_cents, payment_method, stripe_payment_id,
               notes, created_at
        FROM pos_transactions
        WHERE status = 'completed' AND total_cents > 0
        """
    )
    for p in pos_rows:
        p = dict(p)
        date = p["created_at"].date() if p["created_at"] else None
        if not date:
            continue
        method = p["payment_method"] or "card"
        desc = "POS sale" + (f" — {p['notes']}" if p.get("notes") else "")
        await _upsert(
            db, external_id=f"pos:{p['id']}", txn_date=date, description=desc,
            ttype="income", category="tshirt_sales", amount_cents=p["total_cents"],
            member_id=p["member_id"],
            # cash/comp POS sales have no processor id → settle against cash deposits
            processor_payment_id=p["stripe_payment_id"],
        )
        pos += 1

    result = {"income_booked": booked, "workshops_booked": ws,
              "privates_booked": pv, "returns_booked": returns, "pos_booked": pos}
    logger.info("Accounting income sync", **result)
    return result
