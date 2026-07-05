"""Add TOTP / MFA columns to af_global.users

Adds totp_secret, totp_enabled, and backup_codes columns for two-factor
authentication support.

Revision ID: mfa_totp_001
Revises: a9_perf01
Create Date: 2026-03-15
"""
from alembic import op
import sqlalchemy as sa

revision = "mfa_totp_001"
down_revision = "a9_perf01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE af_global.users
        ADD COLUMN IF NOT EXISTS totp_secret     TEXT,
        ADD COLUMN IF NOT EXISTS totp_enabled    BOOLEAN NOT NULL DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS backup_codes    TEXT[]
    """)


def downgrade() -> None:
    op.execute("""
    ALTER TABLE af_global.users
        DROP COLUMN IF EXISTS backup_codes,
        DROP COLUMN IF EXISTS totp_enabled,
        DROP COLUMN IF EXISTS totp_secret
    """)
