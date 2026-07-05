"""Index transactions.metadata->>'external_reference' for idempotency lookups

The /api/v1/external/transactions endpoint dedups on
metadata->>'external_reference' for cross-system idempotency. Without
an index, every external POST runs a full table scan to look for an
existing row. At a few hundred transactions this is fine; at a few
million it becomes a measurable per-request hit.

Adds a partial expression index applied to all tenant schemas. Partial
because most rows don't have an external_reference (POS sales, Stripe
webhooks, etc.) and we only need to find the ones that do.

Revision ID: a20_external_ref_index
Revises: a19_merge_emr_main
Create Date: 2026-04-19
"""
from alembic import op


revision = "a20_external_ref_index"
down_revision = "a19_merge_emr_main"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Apply the index to every tenant schema. New tenants pick it up
    # via init.sql; this migration backfills existing ones.
    op.execute("""
        DO $$
        DECLARE
            tenant_schema TEXT;
        BEGIN
            FOR tenant_schema IN
                SELECT schema_name FROM information_schema.schemata
                WHERE schema_name LIKE 'af_tenant_%'
            LOOP
                EXECUTE format(
                    'CREATE INDEX IF NOT EXISTS idx_transactions_external_reference '
                    'ON %I.transactions ((metadata->>''external_reference'')) '
                    'WHERE metadata->>''external_reference'' IS NOT NULL',
                    tenant_schema
                );
            END LOOP;
        END$$;
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        DECLARE
            tenant_schema TEXT;
        BEGIN
            FOR tenant_schema IN
                SELECT schema_name FROM information_schema.schemata
                WHERE schema_name LIKE 'af_tenant_%'
            LOOP
                EXECUTE format(
                    'DROP INDEX IF EXISTS %I.idx_transactions_external_reference',
                    tenant_schema
                );
            END LOOP;
        END$$;
    """)
