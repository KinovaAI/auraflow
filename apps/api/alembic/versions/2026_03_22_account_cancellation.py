"""Add cancelling status and cancellation tracking columns to organizations

Revision ID: a14_account_cancel
Revises: a13_merge_heads
Create Date: 2026-03-22
"""
from alembic import op

revision = "a14_account_cancel"
down_revision = "a13_merge_heads"
branch_labels = None
depends_on = None


def upgrade():
    # Expand the status CHECK constraint to include 'cancelling'
    op.execute("""
        ALTER TABLE af_global.organizations
        DROP CONSTRAINT IF EXISTS organizations_status_check
    """)
    op.execute("""
        ALTER TABLE af_global.organizations
        ADD CONSTRAINT organizations_status_check
        CHECK (status IN ('trial', 'active', 'suspended', 'cancelling', 'cancelled'))
    """)

    # Add cancellation tracking columns
    op.execute("""
        ALTER TABLE af_global.organizations
        ADD COLUMN IF NOT EXISTS cancellation_reason VARCHAR(100),
        ADD COLUMN IF NOT EXISTS cancellation_feedback TEXT,
        ADD COLUMN IF NOT EXISTS cancellation_requested_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS cancellation_effective_at TIMESTAMPTZ
    """)


def downgrade():
    op.execute("""
        ALTER TABLE af_global.organizations
        DROP COLUMN IF EXISTS cancellation_reason,
        DROP COLUMN IF EXISTS cancellation_feedback,
        DROP COLUMN IF EXISTS cancellation_requested_at,
        DROP COLUMN IF EXISTS cancellation_effective_at
    """)
    op.execute("""
        ALTER TABLE af_global.organizations
        DROP CONSTRAINT IF EXISTS organizations_status_check
    """)
    op.execute("""
        ALTER TABLE af_global.organizations
        ADD CONSTRAINT organizations_status_check
        CHECK (status IN ('trial', 'active', 'suspended', 'cancelled'))
    """)
