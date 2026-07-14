"""Schedule C category taxonomy for the Accounting module.

Ported from a standalone single-tenant LLC accounting app's category config,
with each expense category mapped to its IRS Schedule C line AND its TXF reference
code (for direct TurboTax `.txf` export — verified against the TXF v042 spec).

Seeded per tenant into `<schema>.acct_categories` on first use (idempotent).
`txf_ref` may be None for lines TXF doesn't carry (e.g. contract labor,
depreciation) — those still appear on the P&L / Schedule C summary, just not in
the TXF file.
"""

# (code, label, kind, schedule_c_line, txf_ref)
SEED_CATEGORIES: list[tuple[str, str, str, str | None, str | None]] = [
    # ── Income (Schedule C Part I) ────────────────────────────────────────
    ("sales", "Sales", "income", "Line 1", "293"),
    ("service_income", "Service Income", "income", "Line 1", "293"),
    ("class_revenue", "Class Revenue", "income", "Line 1", "293"),
    ("subscriptions", "Subscriptions / Memberships", "income", "Line 1", "293"),
    ("workshops", "Workshops", "income", "Line 1", "293"),
    ("group_workshops", "Group / Guest-Instructor Workshops", "income", "Line 1", "293"),
    ("private_sessions", "Private Sessions", "income", "Line 1", "293"),
    ("tshirt_sales", "T-Shirt / Retail Sales", "income", "Line 1", "293"),
    ("card_sales", "Card Sales", "income", "Line 1", "293"),
    ("classpass_revenue", "ClassPass Revenue", "income", "Line 1", "293"),
    ("consulting", "Consulting", "income", "Line 1", "293"),
    ("returns_allowances", "Returns & Allowances", "income", "Line 2", "296"),
    ("gifts", "Gifts Received", "income", "Line 6", "303"),
    ("other_income", "Other Income", "income", "Line 6", "303"),
    ("interest_income", "Interest Income", "income", "Line 6", "303"),

    # ── Cost of goods sold (Part III) ─────────────────────────────────────
    ("cost_of_goods_sold", "Cost of Goods Sold", "expense", "Line 4", "295"),

    # ── Expenses (Part II) ────────────────────────────────────────────────
    ("advertising", "Advertising", "expense", "Line 8", "304"),
    ("car_truck", "Car & Truck Expenses", "expense", "Line 9", "306"),
    ("commissions_fees", "Commissions & Fees", "expense", "Line 10", "307"),
    ("contract_labor", "Contract Labor", "expense", "Line 11", None),
    ("depletion", "Depletion", "expense", "Line 12", None),
    ("depreciation", "Depreciation", "expense", "Line 13", None),
    ("employee_benefits", "Employee Benefit Programs", "expense", "Line 14", "308"),
    ("insurance", "Insurance (not health)", "expense", "Line 15", "310"),
    ("interest_mortgage", "Interest — Mortgage", "expense", "Line 16a", "311"),
    ("interest_other", "Interest — Other", "expense", "Line 16b", "312"),
    ("legal_professional", "Legal & Professional Services", "expense", "Line 17", "298"),
    ("office_expense", "Office Expense", "expense", "Line 18", "313"),
    ("pension_profit_sharing", "Pension & Profit-Sharing Plans", "expense", "Line 19", "314"),
    ("rent_lease_vehicles", "Rent/Lease — Vehicles, Machinery, Equip.", "expense", "Line 20a", "299"),
    ("rent_lease_other", "Rent/Lease — Other Business Property", "expense", "Line 20b", "300"),
    ("repairs_maintenance", "Repairs & Maintenance", "expense", "Line 21", "315"),
    ("supplies", "Supplies", "expense", "Line 22", "301"),
    ("taxes_licenses", "Taxes & Licenses", "expense", "Line 23", "316"),
    ("travel", "Travel", "expense", "Line 24a", "317"),
    ("meals", "Meals", "expense", "Line 24b", "294"),
    ("utilities", "Utilities", "expense", "Line 25", "318"),
    ("wages", "Wages", "expense", "Line 26", "297"),
    ("startup_expenses", "Startup Costs", "expense", "Line 27a", None),
    ("other_expenses", "Other Expenses", "expense", "Line 27a", None),

    # ── Distributions (not Schedule C — K-1 / owner draws) ────────────────
    ("partner_distribution", "Partner Distribution", "distribution", None, None),
    ("guaranteed_payment", "Guaranteed Payment", "distribution", None, None),
    ("draw", "Owner Draw", "distribution", None, None),

    # ── Transfers / non-P&L money movement (excluded from income & expense) ─
    ("bank_transfer", "Bank-to-Bank Transfer", "transfer", None, None),
    ("internal_transfer", "Internal Transfer", "transfer", None, None),
    ("card_settlement", "Credit-Card Payment (settlement)", "transfer", None, None),
    ("business_loan", "Business Loan Proceeds", "transfer", None, None),
    ("transfer_other", "Other Transfer", "transfer", None, None),
]

# Default income category applied to auto-imported income before a human
# confirms it; default expense category for bank withdrawals.
DEFAULT_INCOME_CATEGORY = "sales"
DEFAULT_EXPENSE_CATEGORY = "other_expenses"


async def seed_categories(db, schema: str) -> int:
    """Insert any missing SEED_CATEGORIES into <schema>.acct_categories.

    Idempotent — ON CONFLICT DO NOTHING so a studio's custom edits are kept.
    `db` is a tenant-scoped asyncpg connection (search_path already set to the
    tenant schema by get_tenant_db). Returns the number seeded on this run.
    """
    inserted = 0
    for i, (code, label, kind, line, txf) in enumerate(SEED_CATEGORIES):
        status = await db.execute(
            """
            INSERT INTO acct_categories
                (code, label, kind, schedule_c_line, txf_ref, sort_order, is_custom)
            VALUES ($1, $2, $3, $4, $5, $6, FALSE)
            ON CONFLICT (code) DO NOTHING
            """,
            code, label, kind, line, txf, i,
        )
        if status and status.endswith("1"):
            inserted += 1
    return inserted
