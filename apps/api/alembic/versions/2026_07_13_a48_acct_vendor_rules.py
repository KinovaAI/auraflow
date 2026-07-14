"""a48_acct_vendor_rules — per-tenant categorization rules

The bank feed can only be itemized correctly with knowledge that's specific to
each studio: which counterparty is their landlord, their lender, their card
payoff, their gift-givers, etc. That knowledge is TENANT DATA (it contains real
people/vendor names), so it lives in a per-tenant table — never in shared code.

  <schema>.acct_vendor_rules
    - pattern    : case-insensitive substring matched against a bank line's
                   description/counterparty
    - category   : the acct_categories code to assign on match
    - txn_type   : optional type override (income|expense|distribution|transfer);
                   e.g. a credit-card payoff or loan proceed → 'transfer' so it's
                   excluded from the P&L
    - note       : optional note stamped on matched rows
    - priority   : lower runs first (first match wins)

Also adds acct_settings.payroll_w2_start_date — the date a studio switched its
instructor payouts from owner disbursements to W-2 wages (e.g. when a
departing owner-instructor's pay moves to W-2). Payouts before it are
distributions; on/after are wages.

Additive only. Chains off a47.
"""
from alembic import op

revision = "a48_acct_vendor_rules"
down_revision = "a47_accounting_income"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(r"""
    CREATE OR REPLACE FUNCTION af_global.add_acct_vendor_rules_to_schema(p_schema_name TEXT)
    RETURNS VOID
    LANGUAGE plpgsql
    AS $fn$
    BEGIN
        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.acct_vendor_rules (
                id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                pattern     TEXT NOT NULL,
                category    TEXT NOT NULL,
                txn_type    TEXT
                              CHECK (txn_type IN ('income','expense','distribution','transfer')),
                note        TEXT,
                priority    INT NOT NULL DEFAULT 100,
                is_active   BOOLEAN NOT NULL DEFAULT TRUE,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        $ddl$, p_schema_name);
        EXECUTE format($ddl$
            CREATE INDEX IF NOT EXISTS acct_vendor_rules_active_idx
                ON %I.acct_vendor_rules (priority) WHERE is_active
        $ddl$, p_schema_name);
        EXECUTE format($ddl$
            ALTER TABLE %I.acct_settings
                ADD COLUMN IF NOT EXISTS payroll_w2_start_date DATE
        $ddl$, p_schema_name);
    END;
    $fn$;
    """)
    op.execute("""
    DO $$
    DECLARE s TEXT;
    BEGIN
        FOR s IN
            SELECT sch.schema_name FROM af_global.organizations o
            JOIN information_schema.schemata sch ON sch.schema_name = o.schema_name
            WHERE o.status IN ('active', 'trial')
        LOOP
            PERFORM af_global.add_acct_vendor_rules_to_schema(s);
        END LOOP;
    END $$;
    """)


def downgrade():
    op.execute("""
    DO $$
    DECLARE s TEXT;
    BEGIN
        FOR s IN
            SELECT sch.schema_name FROM af_global.organizations o
            JOIN information_schema.schemata sch ON sch.schema_name = o.schema_name
        LOOP
            EXECUTE format('DROP TABLE IF EXISTS %I.acct_vendor_rules', s);
            EXECUTE format('ALTER TABLE %I.acct_settings DROP COLUMN IF EXISTS payroll_w2_start_date', s);
        END LOOP;
    END $$;
    """)
    op.execute("DROP FUNCTION IF EXISTS af_global.add_acct_vendor_rules_to_schema(TEXT);")
