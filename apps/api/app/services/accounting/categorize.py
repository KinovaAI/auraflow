"""Auto-itemize bank transactions into real Schedule C categories.

Runs after the Mercury import. Two layers, both driven by TENANT DATA — no real
vendor/customer/lender names ever live in this shared code:

  1. Per-tenant vendor rules (acct_vendor_rules): the studio's own map of
     "counterparty contains X → category Y (and optionally re-type it)". This is
     where studio-specific knowledge lives — landlord, lender, card payoffs,
     gift-givers, payment processors, etc. First match by priority wins. A rule
     can re-type a row (e.g. a credit-card payoff or loan proceed → 'transfer' so
     it drops out of the P&L; the underlying itemized purchases/sales carry the
     real amounts).

  2. Payroll by date: bank payouts to people on the instructor roster are booked
     as **owner disbursements** before acct_settings.payroll_w2_start_date and
     **W-2 wages** on/after it (a studio's changeover date). Names come from the
     instructors table (tenant data), matched first-name + surname so partial
     bank names still hit.

Only rewrites rows still in the default buckets ('sales' / 'other_expenses') or
uncategorized — never overrides a category a human set. `db` is tenant-scoped.
"""
from app.core.logging import logger

_DEFAULT_CATS = ("sales", "other_expenses")


def _match_instructor(desc_lower: str, toks: list[str]) -> bool:
    """First name + a surname token (handles 'Jane Smith' vs roster
    'Jane Smith-Doe'); both required so a vendor sharing a first name
    doesn't false-match."""
    if len(toks) == 1:
        return len(toks[0]) >= 6 and toks[0] in desc_lower
    first, rest = toks[0], toks[1:]
    return len(toks) >= 2 and first in desc_lower and any(t in desc_lower for t in rest)


async def categorize_bank(db) -> dict:
    rules = await db.fetch(
        "SELECT pattern, category, txn_type, note FROM acct_vendor_rules "
        "WHERE is_active ORDER BY priority, created_at"
    )
    setting = await db.fetchrow(
        "SELECT payroll_w2_start_date FROM acct_settings WHERE id = 1"
    )
    w2_start = setting["payroll_w2_start_date"] if setting else None

    # category → kind (income/expense/distribution/transfer), so a rule only
    # applies when its category's direction matches the transaction's direction
    # (never an income category on money going out, or vice versa).
    cat_kind = {r["code"]: r["kind"]
                for r in await db.fetch("SELECT code, kind FROM acct_categories")}

    instructors = []
    for r in await db.fetch("SELECT display_name, tax_classification FROM instructors"):
        toks = [t for t in (r["display_name"] or "").lower().replace("-", " ").split()
                if len(t) >= 2]
        if toks:
            instructors.append((toks, (r["tax_classification"] or "1099")))

    rows = await db.fetch(
        """
        SELECT id, description, type, txn_date
        FROM acct_transactions
        WHERE source = 'bank' AND (category IS NULL OR category = ANY($1))
        """,
        list(_DEFAULT_CATS),
    )

    by_rule = payroll = 0
    for r in rows:
        d = (r["description"] or "").lower()
        new_cat = new_type = note = None

        # 1) per-tenant vendor rules
        for rule in rules:
            if (rule["pattern"] or "").lower() in d:
                rtype = rule["txn_type"]  # may be None → keep existing type
                # No explicit type override → the category's direction must match
                # the row's direction, else this rule doesn't apply here.
                if not rtype:
                    k = cat_kind.get(rule["category"])
                    if k and k != r["type"]:
                        continue
                new_cat = rule["category"]
                new_type = rtype
                note = rule["note"]
                by_rule += 1
                break

        # 2) payroll by date (only if no rule already claimed it)
        if not new_cat and r["type"] == "expense":
            for toks, tax in instructors:
                if _match_instructor(d, toks):
                    if w2_start and r["txn_date"] and r["txn_date"] >= w2_start:
                        new_cat, new_type = "wages", "expense"
                    else:
                        new_cat, new_type = "draw", "distribution"
                    payroll += 1
                    break

        if new_cat:
            await db.execute(
                "UPDATE acct_transactions SET category = $1, "
                "type = COALESCE($2, type), notes = COALESCE(notes, $3), "
                "updated_at = NOW() WHERE id = $4",
                new_cat, new_type, note, r["id"],
            )

    result = {"rule_categorized": by_rule, "payroll_categorized": payroll}
    logger.info("Accounting auto-categorize", **result)
    return result
