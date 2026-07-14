"""Reconciliation engine — tie AuraFlow's booked income to the bank statement.

Income is booked per-sale from AuraFlow (income_sync.py). This engine ties those
sales to the bank so the books balance to the statement (the authoritative record)
without double-counting:

  1. Match each processor payout (acct_payouts) to its Mercury bank deposit
     (amount == payout net, within a date window).
  2. On match: reclassify that bank deposit from income → **transfer** (it's the
     settlement of already-booked sales, not new income); post the payout's
     processing **fee** as an expense (so gross sales − fees == the net deposit);
     and mark the payout's constituent AuraFlow income rows reconciled.
  3. Match cash bank deposits to unsettled cash AuraFlow sales (greedy exact sum),
     reclassifying matched deposits as settlement too.
  4. Flag whatever doesn't tie out for review.

Net effect: P&L income = gross AuraFlow sales − returns; expenses = bank
withdrawals + processing fees; every bank deposit is either a settlement (transfer)
or genuine external income. Ties to the bank. `db` is tenant-scoped.
"""
from app.core.logging import logger

MATCH_WINDOW_DAYS = 8


async def _settle_payouts(db) -> int:
    """Match each unreconciled payout to its bank deposit, then settle:
    reclassify the deposit, post the fee expense, and reconcile the sales."""
    payouts = await db.fetch(
        """
        SELECT id, provider, provider_payout_id, net_cents, fee_cents, payout_date
        FROM acct_payouts
        WHERE reconciled = FALSE AND payout_date IS NOT NULL
        ORDER BY payout_date
        """
    )
    matched = 0
    for po in payouts:
        deposit = await db.fetchrow(
            """
            SELECT id FROM acct_transactions
            WHERE source = 'bank' AND type = 'income' AND payout_id IS NULL
              AND amount_cents = $1
              AND txn_date BETWEEN $2::date - $3 AND $2::date + $3
            ORDER BY abs(txn_date - $2::date)
            LIMIT 1
            """,
            po["net_cents"], po["payout_date"], MATCH_WINDOW_DAYS,
        )
        if not deposit:
            continue

        # Are this payout's sales booked as AuraFlow income? (They are for the
        # AuraFlow era, Apr 2026+. For Oct 2025–Mar 2026 there's no AuraFlow data,
        # so the bank deposit itself IS the income — don't zero it out.)
        booked = await db.fetchrow(
            """
            SELECT count(*) AS n
            FROM acct_transactions a
            WHERE a.source = 'auraflow' AND a.type = 'income' AND a.payout_id IS NULL
              AND a.processor_payment_id IN (
                  SELECT provider_payment_id FROM acct_payout_items WHERE payout_id = $1
              )
            """,
            po["id"],
        )
        await db.execute(
            "UPDATE acct_payouts SET bank_txn_id = $1, reconciled = TRUE, "
            "discrepancy_cents = 0, updated_at = NOW() WHERE id = $2",
            deposit["id"], po["id"],
        )

        if not (booked and booked["n"]):
            # No AuraFlow sales behind this payout → the bank deposit is the
            # income (net). Just link + mark reconciled; keep type='income',
            # and don't post a fee (it's already netted into the deposit).
            await db.execute(
                "UPDATE acct_transactions SET payout_id = $1, status = 'reconciled', "
                "updated_at = NOW() WHERE id = $2",
                po["id"], deposit["id"],
            )
            matched += 1
            continue

        # a) the bank deposit is the settlement of booked sales, not new income
        await db.execute(
            "UPDATE acct_transactions SET payout_id = $1, type = 'transfer', "
            "status = 'reconciled', notes = $2, updated_at = NOW() WHERE id = $3",
            po["id"],
            f"Settlement — {po['provider']} payout {po['provider_payout_id']}",
            deposit["id"],
        )

        # b) processing fees for this payout → expense (so gross − fee == deposit)
        if po["fee_cents"]:
            await db.execute(
                """
                INSERT INTO acct_transactions
                    (txn_date, description, type, category, amount_cents, source,
                     external_id, payout_id, status)
                VALUES ($1,$2,'expense','commissions_fees',$3,'auraflow',$4,$5,'reconciled')
                ON CONFLICT (source, external_id) WHERE external_id IS NOT NULL
                DO UPDATE SET amount_cents = EXCLUDED.amount_cents, updated_at = NOW()
                """,
                po["payout_date"],
                f"Processing fees — {po['provider']} payout {po['provider_payout_id']}",
                po["fee_cents"], f"payoutfee:{po['id']}", po["id"],
            )

        # c) reconcile the AuraFlow income rows this payout settled
        await db.execute(
            """
            UPDATE acct_transactions a
            SET payout_id = $1, status = 'reconciled', updated_at = NOW()
            WHERE a.source = 'auraflow' AND a.type = 'income' AND a.payout_id IS NULL
              AND a.processor_payment_id IN (
                  SELECT provider_payment_id FROM acct_payout_items WHERE payout_id = $1
              )
            """,
            po["id"],
        )
        matched += 1
    return matched


async def _settle_cash(db) -> int:
    """Match cash bank deposits to unsettled cash AuraFlow sales (greedy exact
    sum, oldest first). Only settles on an exact tie-out; otherwise leaves the
    deposit for review (it may be genuine external income)."""
    deposits = await db.fetch(
        """
        SELECT id, amount_cents, txn_date FROM acct_transactions
        WHERE source = 'bank' AND type = 'income' AND payout_id IS NULL
        ORDER BY txn_date
        """
    )
    settled = 0
    for dep in deposits:
        # unsettled cash sales (no processor id) up to this deposit's date
        cash = await db.fetch(
            """
            SELECT id, amount_cents FROM acct_transactions
            WHERE source = 'auraflow' AND type = 'income' AND status <> 'reconciled'
              AND processor_payment_id IS NULL AND txn_date <= $1
            ORDER BY txn_date, created_at
            """,
            dep["txn_date"],
        )
        acc, ids = 0, []
        for c in cash:
            acc += c["amount_cents"]
            ids.append(c["id"])
            if acc == dep["amount_cents"]:
                break
        if acc == dep["amount_cents"] and ids:
            await db.execute(
                "UPDATE acct_transactions SET type='transfer', status='reconciled', "
                "notes='Settlement — cash deposit', updated_at=NOW() WHERE id=$1",
                dep["id"],
            )
            await db.execute(
                "UPDATE acct_transactions SET status='reconciled', updated_at=NOW() "
                "WHERE id = ANY($1::uuid[])", ids,
            )
            settled += 1
    return settled


async def _flags(db) -> dict:
    unmatched_payouts = await db.fetch(
        "SELECT id, provider, provider_payout_id, payout_date, net_cents "
        "FROM acct_payouts WHERE reconciled = FALSE ORDER BY payout_date DESC NULLS LAST"
    )
    # bank income deposits that never settled to a payout or cash — need a human call
    unmatched_deposits = await db.fetch(
        """
        SELECT id, txn_date, description, amount_cents
        FROM acct_transactions
        WHERE source = 'bank' AND type = 'income' AND payout_id IS NULL
        ORDER BY txn_date DESC
        """
    )
    # AuraFlow card sales booked but not yet tied to a payout (pending settlement)
    unsettled = await db.fetchrow(
        """
        SELECT count(*) AS n, COALESCE(sum(amount_cents),0) AS cents
        FROM acct_transactions
        WHERE source = 'auraflow' AND type = 'income' AND status <> 'reconciled'
          AND processor_payment_id IS NOT NULL
        """
    )
    return {
        "unmatched_payouts": [dict(r) for r in unmatched_payouts],
        "unmatched_deposits": [dict(r) for r in unmatched_deposits],
        "unsettled_card_sales_count": unsettled["n"],
        "unsettled_card_sales_cents": unsettled["cents"],
    }


async def reconcile(db) -> dict:
    """Bank-authoritative tie-out report (non-mutating).

    Income and expenses come from the bank feed (the authoritative record);
    AuraFlow sales are itemized detail excluded from the P&L. So this pass does
    NOT reclassify any bank rows — it only reports the picture: what the bank
    shows vs. the AuraFlow sales sitting behind the card deposits.

    (The payout-driven settlement matcher — _settle_payouts / _settle_cash — is
    kept for a future mode where AuraFlow sales are counted directly; it needs
    Stripe/Square payout access, which Square currently blocks. Not called here
    because reclassifying a bank deposit would drop real income.)
    """
    row = await db.fetchrow(
        """
        SELECT
          count(*) FILTER (WHERE source='bank' AND type='income')   AS bank_income_n,
          COALESCE(sum(amount_cents) FILTER (WHERE source='bank' AND type='income'),0)   AS bank_income_c,
          count(*) FILTER (WHERE source='bank' AND type='expense')  AS bank_expense_n,
          count(*) FILTER (WHERE source='bank' AND type='transfer') AS bank_transfer_n,
          count(*) FILTER (WHERE source='auraflow' AND type='income') AS auraflow_sales_n,
          COALESCE(sum(amount_cents) FILTER (WHERE source='auraflow' AND type='income'),0) AS auraflow_sales_c
        FROM acct_transactions
        """
    )
    summary = {
        "bank_income_count": row["bank_income_n"],
        "bank_income_cents": row["bank_income_c"],
        "bank_expense_count": row["bank_expense_n"],
        "bank_transfer_count": row["bank_transfer_n"],
        "auraflow_sales_count": row["auraflow_sales_n"],
        "auraflow_sales_cents": row["auraflow_sales_c"],
        # kept for API/UI back-compat
        "newly_matched": 0,
        "cash_settled": 0,
        "unmatched_payout_count": 0,
        "unmatched_deposit_count": 0,
        "unsettled_card_sales_count": 0,
    }
    logger.info("Accounting tie-out (bank-authoritative)",
                bank_income=row["bank_income_n"], bank_expense=row["bank_expense_n"],
                bank_transfer=row["bank_transfer_n"], auraflow_sales=row["auraflow_sales_n"])
    return summary
