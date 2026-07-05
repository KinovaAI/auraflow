"""employer_profile: per-tenant employer/onboarding settings

Revision ID: a41_employer_profile
Revises: a40_hiring
Create Date: 2026-06-22

Per-tenant employer profile so ANY studio on AuraFlow can enter their own
employer info and use the hiring/onboarding system — nothing hardcoded.
Generated onboarding forms (DLSE-NTE wage-theft notice, DE-34 new-hire
report) read from this tenant's row.

One row per tenant (the service upserts a singleton). Created via
af_global.add_employer_profile_to_schema() so it exists for existing AND
newly-provisioned tenants (same pattern as add_api_keys_table).
"""
revision = "a41_employer_profile"
down_revision = "a40_hiring"
branch_labels = None
depends_on = None


def upgrade():
    from alembic import op

    op.execute(r"""
    CREATE OR REPLACE FUNCTION af_global.add_employer_profile_to_schema(p_schema_name TEXT)
    RETURNS VOID
    LANGUAGE plpgsql
    AS $fn$
    BEGIN
        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.employer_profile (
                id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                legal_name           VARCHAR(255),
                dba_name             VARCHAR(255),
                ein                  VARCHAR(20),
                edd_account_number   VARCHAR(40),
                address_line1        VARCHAR(255),
                address_line2        VARCHAR(255),
                city                 VARCHAR(120),
                state                VARCHAR(2) NOT NULL DEFAULT 'CA',
                postal_code          VARCHAR(20),
                phone                VARCHAR(40),
                -- workers' comp (feeds DLSE-NTE + DWC-7)
                wc_carrier_name      VARCHAR(255),
                wc_policy_number     VARCHAR(80),
                wc_carrier_phone     VARCHAR(40),
                wc_policy_effective  DATE,
                -- pay (feeds DLSE-NTE)
                pay_schedule         VARCHAR(20)
                                       CHECK (pay_schedule IS NULL OR pay_schedule IN ('weekly','biweekly','semimonthly','monthly')),
                regular_payday       VARCHAR(120),
                overtime_basis       VARCHAR(120),
                -- policies
                sick_leave_policy    TEXT,
                created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
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
        LOOP PERFORM af_global.add_employer_profile_to_schema(s); END LOOP;
    END $$;
    """)


def downgrade():
    from alembic import op
    op.execute(r"""
    DO $$
    DECLARE s TEXT;
    BEGIN
        FOR s IN SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'af_tenant_%'
        LOOP EXECUTE format($d$ DROP TABLE IF EXISTS %I.employer_profile CASCADE $d$, s); END LOOP;
    END $$;
    """)
    op.execute("DROP FUNCTION IF EXISTS af_global.add_employer_profile_to_schema(TEXT);")
