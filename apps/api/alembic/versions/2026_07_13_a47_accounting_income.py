"""a47_accounting_income — link AuraFlow sales into the books

Adds one column so the Accounting module can post EVERY AuraFlow sale (POS
card/cash, memberships, classes, private sessions, workshops, …) into the ledger
as an itemized, auto-categorized income row (source='auraflow') and reconcile the
card ones to their processor payout → bank deposit:

  acct_transactions.processor_payment_id  — the Stripe charge / Square payment id
      behind a source='auraflow' income row, so reconciliation can match it to the
      payout (acct_payout_items.provider_payment_id) that settled it. NULL for cash
      sales (no processor id) and for bank/manual rows.

Additive only. Chains off a46_accounting.
"""
from alembic import op

revision = "a47_accounting_income"
down_revision = "a46_accounting"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(r"""
    CREATE OR REPLACE FUNCTION af_global.add_accounting_income_link_to_schema(p_schema_name TEXT)
    RETURNS VOID
    LANGUAGE plpgsql
    AS $fn$
    BEGIN
        EXECUTE format($ddl$
            ALTER TABLE %I.acct_transactions
                ADD COLUMN IF NOT EXISTS processor_payment_id TEXT
        $ddl$, p_schema_name);
        EXECUTE format($ddl$
            CREATE INDEX IF NOT EXISTS acct_transactions_processor_pid_idx
                ON %I.acct_transactions (processor_payment_id)
                WHERE processor_payment_id IS NOT NULL
        $ddl$, p_schema_name);
    END;
    $fn$;
    """)
    op.execute("""
    DO $$
    DECLARE s TEXT;
    BEGIN
        FOR s IN
            SELECT sch.schema_name
            FROM af_global.organizations o
            JOIN information_schema.schemata sch ON sch.schema_name = o.schema_name
            WHERE o.status IN ('active', 'trial')
        LOOP
            PERFORM af_global.add_accounting_income_link_to_schema(s);
        END LOOP;
    END $$;
    """)


def downgrade():
    op.execute("""
    DO $$
    DECLARE s TEXT;
    BEGIN
        FOR s IN
            SELECT sch.schema_name
            FROM af_global.organizations o
            JOIN information_schema.schemata sch ON sch.schema_name = o.schema_name
        LOOP
            EXECUTE format('DROP INDEX IF EXISTS %I.acct_transactions_processor_pid_idx', s);
            EXECUTE format('ALTER TABLE %I.acct_transactions DROP COLUMN IF EXISTS processor_payment_id', s);
        END LOOP;
    END $$;
    """)
    op.execute("DROP FUNCTION IF EXISTS af_global.add_accounting_income_link_to_schema(TEXT);")
