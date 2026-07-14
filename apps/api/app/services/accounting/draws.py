"""Apply the owner draw schedule (acct_owner_draws) on every sync.

For each owner, the fixed monthly draw is a distribution (an owner taking money
out — NOT a deductible expense); everything they were paid above it that month is
their variable private/workshop pay = wages. This runs from the configured
schedule so it's consistent and reproducible — never hand-entered.

Idempotent: resets each scheduled owner's bank payouts to wages first, then marks
the monthly draw amount as a distribution. `db` is tenant-scoped.
"""
from app.core.logging import logger


async def apply_draws(db) -> dict:
    sched = await db.fetch(
        "SELECT owner_pattern, monthly_cents, effective_from, effective_to "
        "FROM acct_owner_draws WHERE is_active ORDER BY owner_pattern, effective_from"
    )
    if not sched:
        return {"draws_marked": 0}

    # 1. reset every scheduled owner's bank payouts to wages (idempotent baseline)
    for pat in {r["owner_pattern"] for r in sched}:
        await db.execute(
            "UPDATE acct_transactions SET type = 'expense', category = 'wages', "
            "updated_at = NOW() WHERE source = 'bank' AND description ILIKE $1",
            f"%{pat}%",
        )

    # 2. mark the fixed monthly draw as a distribution, per owner per month
    marked = 0
    for r in sched:
        rows = await db.fetch(
            """
            SELECT id, amount_cents, to_char(txn_date, 'YYYY-MM') AS mo
            FROM acct_transactions
            WHERE source = 'bank' AND description ILIKE $1
              AND txn_date >= $2 AND ($3::date IS NULL OR txn_date <= $3)
            ORDER BY txn_date, amount_cents DESC
            """,
            f"%{r['owner_pattern']}%", r["effective_from"], r["effective_to"],
        )
        by_month: dict = {}
        for x in rows:
            by_month.setdefault(x["mo"], []).append(x)
        for txns in by_month.values():
            acc = 0
            for t in sorted(txns, key=lambda z: -z["amount_cents"]):
                if acc >= r["monthly_cents"]:
                    break
                if acc + t["amount_cents"] <= r["monthly_cents"]:
                    await db.execute(
                        "UPDATE acct_transactions SET type = 'distribution', "
                        "category = 'draw', updated_at = NOW() WHERE id = $1",
                        t["id"],
                    )
                    acc += t["amount_cents"]
                    marked += 1
    logger.info("Accounting owner draws applied", draws_marked=marked)
    return {"draws_marked": marked}
