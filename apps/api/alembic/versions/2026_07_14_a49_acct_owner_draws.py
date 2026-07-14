"""a49_acct_owner_draws — per-tenant owner draw schedule

Owner disbursements are a business fact the studio configures, not something to
hand-enter on the books: each owner takes a fixed monthly draw (a distribution,
not a deductible expense) that can change over time. This stores that schedule
so the sync splits owner payouts consistently — the fixed monthly amount →
Distributions, everything above it → their variable (private/workshop) wages.

  <schema>.acct_owner_draws
    - owner_pattern  : case-insensitive match against the payout's description
    - monthly_cents  : the fixed monthly draw amount
    - effective_from / effective_to : the window this amount applies (inclusive)

Additive only. Chains off a48.
"""
from alembic import op

revision = "a49_acct_owner_draws"
down_revision = "a48_acct_vendor_rules"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(r"""
    CREATE OR REPLACE FUNCTION af_global.add_acct_owner_draws_to_schema(p_schema_name TEXT)
    RETURNS VOID LANGUAGE plpgsql AS $fn$
    BEGIN
        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.acct_owner_draws (
                id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                owner_pattern  TEXT NOT NULL,
                monthly_cents  BIGINT NOT NULL,
                effective_from DATE NOT NULL,
                effective_to   DATE,
                is_active      BOOLEAN NOT NULL DEFAULT TRUE,
                created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        $ddl$, p_schema_name);
    END;
    $fn$;
    """)
    op.execute("""
    DO $$ DECLARE s TEXT;
    BEGIN
        FOR s IN SELECT sch.schema_name FROM af_global.organizations o
            JOIN information_schema.schemata sch ON sch.schema_name = o.schema_name
            WHERE o.status IN ('active','trial')
        LOOP PERFORM af_global.add_acct_owner_draws_to_schema(s); END LOOP;
    END $$;
    """)


def downgrade():
    op.execute("""
    DO $$ DECLARE s TEXT;
    BEGIN
        FOR s IN SELECT sch.schema_name FROM af_global.organizations o
            JOIN information_schema.schemata sch ON sch.schema_name = o.schema_name
        LOOP EXECUTE format('DROP TABLE IF EXISTS %I.acct_owner_draws', s); END LOOP;
    END $$;
    """)
    op.execute("DROP FUNCTION IF EXISTS af_global.add_acct_owner_draws_to_schema(TEXT);")
