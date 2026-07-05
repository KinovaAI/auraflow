"""Add Meta + Google Ads token columns to organizations

Revision ID: a18_ads_tokens
Revises: a17_backup_verified
Create Date: 2026-04-18
"""

revision = "a18_ads_tokens"
down_revision = "a17_backup_verified"
branch_labels = None
depends_on = None


def upgrade():
    from alembic import op
    op.execute("""
        ALTER TABLE af_global.organizations
        ADD COLUMN IF NOT EXISTS meta_access_token_encrypted BYTEA,
        ADD COLUMN IF NOT EXISTS meta_connected_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS google_ads_refresh_token_encrypted BYTEA,
        ADD COLUMN IF NOT EXISTS google_ads_connected_at TIMESTAMPTZ;
    """)


def downgrade():
    from alembic import op
    op.execute("""
        ALTER TABLE af_global.organizations
        DROP COLUMN IF EXISTS meta_access_token_encrypted,
        DROP COLUMN IF EXISTS meta_connected_at,
        DROP COLUMN IF EXISTS google_ads_refresh_token_encrypted,
        DROP COLUMN IF EXISTS google_ads_connected_at;
    """)
