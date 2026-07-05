"""de34_filings: track CA DE-34 new-hire report filings

Revision ID: a43_de34_filings
Revises: a42_onboarding_packets
Create Date: 2026-06-22

California requires a DE-34 (Report of New Employee(s)) filed with the EDD
within 20 days of a new hire's start date. This per-tenant table records when
each hire's DE-34 has been filed so the dashboard can surface what's still due.
Created via af_global.add_de34_filings_to_schema() (existing + future tenants).
"""
revision = "a43_de34_filings"
down_revision = "a42_onboarding_packets"
branch_labels = None
depends_on = None


def upgrade():
    from alembic import op
    op.execute(r"""
    CREATE OR REPLACE FUNCTION af_global.add_de34_filings_to_schema(p_schema_name TEXT)
    RETURNS VOID
    LANGUAGE plpgsql
    AS $fn$
    BEGIN
        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.de34_filings (
                id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id    UUID NOT NULL UNIQUE,
                filed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                filed_by   UUID,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        $ddl$, p_schema_name);
    END;
    $fn$;
    """)
    op.execute(r"""
    DO $$
    DECLARE s TEXT;
    BEGIN
        FOR s IN SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'af_tenant_%'
        LOOP PERFORM af_global.add_de34_filings_to_schema(s); END LOOP;
    END $$;
    """)


def downgrade():
    from alembic import op
    op.execute(r"""
    DO $$
    DECLARE s TEXT;
    BEGIN
        FOR s IN SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'af_tenant_%'
        LOOP EXECUTE format($d$ DROP TABLE IF EXISTS %I.de34_filings CASCADE $d$, s); END LOOP;
    END $$;
    """)
    op.execute("DROP FUNCTION IF EXISTS af_global.add_de34_filings_to_schema(TEXT);")
