"""Financial reports for the Accounting module.

Faithful port of a standalone single-tenant LLC accounting app's reports:
  - summary()          — P&L: income / expense / distribution by category + net.
  - schedule_c()       — the same ledger mapped onto IRS Schedule C lines (via
                         acct_categories.schedule_c_line / txf_ref), for the tax
                         export + accountant PDF.
  - member_allocation()— K-1: each partner's pro-rata share of income / expenses /
                         net + their actual distributions (server.js:963-1017).

All figures are in **cents** (BIGINT); the caller formats. `type='transfer'` is
excluded from the P&L (internal money movement), matching the standalone app.
`db` is a tenant-scoped asyncpg connection.
"""


_RETURNS = "returns_allowances"  # contra-revenue (Schedule C Line 2)


def _year_clause(year, params: list) -> str:
    """Append a year filter on txn_date; returns the SQL fragment."""
    if not year:
        return ""
    params.append(int(year))
    return f" AND EXTRACT(YEAR FROM txn_date) = ${len(params)}"


async def _by_category(db, txn_type: str, year) -> tuple[dict, int]:
    params: list = [txn_type]
    clause = _year_clause(year, params)
    rows = await db.fetch(
        f"""
        SELECT category, COALESCE(SUM(amount_cents), 0) AS total
        FROM acct_transactions
        WHERE type = $1{clause}
        GROUP BY category
        ORDER BY total DESC
        """,
        *params,
    )
    by_cat, total = {}, 0
    for r in rows:
        by_cat[r["category"] or "uncategorized"] = r["total"]
        total += r["total"]
    return by_cat, total


async def summary(db, year=None) -> dict:
    """P&L. income/expense/distribution grouped by category + net profit.

    Returns & Allowances (refunds) are a contra-revenue: they reduce gross
    receipts rather than counting as positive income. `total_income_cents` is
    net of returns so net profit is correct. `type='transfer'` rows (processor /
    cash settlements) are excluded entirely — they're not income or expense.
    """
    income, gross = await _by_category(db, "income", year)
    expense, total_expenses = await _by_category(db, "expense", year)
    distribution, total_distributions = await _by_category(db, "distribution", year)
    # Returns/refunds are NOT income — take them out of the income list and
    # subtract them from gross receipts (Schedule C Line 1 − Line 2).
    returns_cents = income.pop(_RETURNS, 0)
    net_income = (gross - returns_cents) - returns_cents
    return {
        "year": int(year) if year else None,
        "income": income,
        "expense": expense,
        "distribution": distribution,
        "returns_cents": returns_cents,
        "total_income_cents": net_income,
        "total_expenses_cents": total_expenses,
        "total_distributions_cents": total_distributions,
        "net_profit_cents": net_income - total_expenses,
    }


async def schedule_c(db, year=None) -> dict:
    """Ledger mapped onto Schedule C lines. Returns per-line detail (with the TXF
    ref code for the tax export) for income (Part I) and expenses (Part II), plus
    the headline totals. Categories without a schedule_c_line still surface under
    an 'Unmapped' bucket so nothing is silently dropped."""
    params: list = []
    clause = _year_clause(year, params)
    rows = await db.fetch(
        f"""
        SELECT
            t.type,
            COALESCE(c.schedule_c_line, 'Unmapped') AS line,
            c.txf_ref,
            COALESCE(c.label, INITCAP(REPLACE(t.category, '_', ' ')), 'Uncategorized') AS label,
            t.category AS code,
            COALESCE(SUM(t.amount_cents), 0) AS total
        FROM acct_transactions t
        LEFT JOIN acct_categories c ON c.code = t.category
        WHERE t.type IN ('income', 'expense'){clause}
        GROUP BY t.type, c.schedule_c_line, c.txf_ref, c.label, t.category
        ORDER BY t.type, line
        """,
        *params,
    )
    income_lines, expense_lines = [], []
    gross_receipts = total_expenses = 0
    for r in rows:
        item = {
            "line": r["line"],
            "label": r["label"],
            "code": r["code"],
            "txf_ref": r["txf_ref"],
            "amount_cents": r["total"],
        }
        if r["type"] == "income":
            income_lines.append(item)
            # Line 2 (returns & allowances) subtracts from gross receipts
            gross_receipts += -r["total"] if r["code"] == _RETURNS else r["total"]
        else:
            expense_lines.append(item)
            total_expenses += r["total"]
    return {
        "year": int(year) if year else None,
        "income_lines": income_lines,
        "expense_lines": expense_lines,
        "gross_receipts_cents": gross_receipts,
        "total_expenses_cents": total_expenses,
        "net_profit_cents": gross_receipts - total_expenses,
    }


async def member_allocation(db, year=None) -> dict:
    """K-1 pro-rata allocation. Each partner gets ownership_pct of income /
    expenses / net; distributions are their actual draws (server.js:963-1017)."""
    income_by_cat, gross = await _by_category(db, "income", year)
    _, total_expenses = await _by_category(db, "expense", year)
    _, total_distributions = await _by_category(db, "distribution", year)
    # Postgres SUM(bigint) comes back as Decimal — cast to int so the per-owner
    # fraction math (int * float) doesn't blow up.
    gross = int(gross)
    total_expenses = int(total_expenses)
    total_distributions = int(total_distributions)
    total_income = gross - 2 * int(income_by_cat.get(_RETURNS, 0))  # net of returns
    net_profit = total_income - total_expenses

    dist_params: list = []
    dist_clause = _year_clause(year, dist_params)
    dist_rows = await db.fetch(
        f"""
        SELECT member_id, COALESCE(SUM(amount_cents), 0) AS total
        FROM acct_transactions
        WHERE type = 'distribution' AND member_id IS NOT NULL{dist_clause}
        GROUP BY member_id
        """,
        *dist_params,
    )
    dist_by_member = {str(r["member_id"]): int(r["total"]) for r in dist_rows}

    members = await db.fetch(
        "SELECT id, name, email, ownership_pct, capital_cents FROM acct_members "
        "ORDER BY name ASC"
    )
    allocations = []
    for m in members:
        frac = float(m["ownership_pct"] or 0) / 100.0
        allocations.append({
            "id": str(m["id"]),
            "name": m["name"],
            "email": m["email"],
            "ownership_pct": float(m["ownership_pct"] or 0),
            "capital_cents": m["capital_cents"],
            "share_income_cents": round(total_income * frac),
            "share_expenses_cents": round(total_expenses * frac),
            "net_allocation_cents": round(net_profit * frac),
            "distributions_cents": dist_by_member.get(str(m["id"]), 0),
        })
    return {
        "year": int(year) if year else None,
        "total_income_cents": total_income,
        "total_expenses_cents": total_expenses,
        "total_distributions_cents": total_distributions,
        "net_profit_cents": net_profit,
        "allocations": allocations,
    }
