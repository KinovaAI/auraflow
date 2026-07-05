"""GDPR deletion requests table and custom domain columns

Adds gdpr_deletion_requests table to each tenant schema.
Adds custom_domain_status and custom_domain_verified_at columns
to af_global.organizations for custom domain management.

Revision ID: a10_gdpr_cd01
Revises: a9_perf01
Create Date: 2026-03-15
"""
import sqlalchemy as sa
from alembic import op

revision = "a10_gdpr_cd01"
down_revision = "a9_perf01"
branch_labels = None
depends_on = None


def _apply_to_tenant(schema: str) -> None:
    """Apply GDPR deletion requests table to a single tenant schema."""

    op.execute(f"""
    CREATE TABLE IF NOT EXISTS {schema}.gdpr_deletion_requests (
        id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        member_id               UUID NOT NULL,
        requested_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        scheduled_deletion_at   TIMESTAMPTZ NOT NULL,
        status                  VARCHAR(20) NOT NULL DEFAULT 'pending',
        completed_at            TIMESTAMPTZ,
        cancelled_at            TIMESTAMPTZ
    )
    """)

    safe = schema.replace("-", "_")
    op.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{safe}_gdpr_del_member "
        f"ON {schema}.gdpr_deletion_requests(member_id)"
    )
    op.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{safe}_gdpr_del_status "
        f"ON {schema}.gdpr_deletion_requests(status) WHERE status = 'pending'"
    )
    op.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{safe}_gdpr_del_scheduled "
        f"ON {schema}.gdpr_deletion_requests(scheduled_deletion_at) WHERE status = 'pending'"
    )


def upgrade():
    # 1. Apply GDPR deletion requests table to all existing tenant schemas
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT schema_name FROM af_global.organizations WHERE status != 'cancelled'")
    ).fetchall()

    for row in rows:
        _apply_to_tenant(row[0])

    # 2. Add custom domain columns to af_global.organizations
    # custom_domain column already exists; add status and verified_at
    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'af_global'
              AND table_name = 'organizations'
              AND column_name = 'custom_domain_status'
        ) THEN
            ALTER TABLE af_global.organizations
            ADD COLUMN custom_domain_status VARCHAR(20);
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'af_global'
              AND table_name = 'organizations'
              AND column_name = 'custom_domain_verified_at'
        ) THEN
            ALTER TABLE af_global.organizations
            ADD COLUMN custom_domain_verified_at TIMESTAMPTZ;
        END IF;
    END
    $$;
    """)


def downgrade():
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT schema_name FROM af_global.organizations WHERE status != 'cancelled'")
    ).fetchall()
    for row in rows:
        schema = row[0]
        op.execute(f"DROP TABLE IF EXISTS {schema}.gdpr_deletion_requests CASCADE")

    # Remove custom domain columns
    op.execute("ALTER TABLE af_global.organizations DROP COLUMN IF EXISTS custom_domain_status")
    op.execute("ALTER TABLE af_global.organizations DROP COLUMN IF EXISTS custom_domain_verified_at")
