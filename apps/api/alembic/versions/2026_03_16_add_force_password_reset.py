"""Add force_password_reset column to af_global.users

Used by member/instructor import to require imported users to set their
own password on first login.

Revision ID: a12_force_pw_reset
Revises: a11_webhook_dedup
Create Date: 2026-03-16
"""
from alembic import op

revision = "a12_force_pw_reset"
down_revision = "a11_webhook_dedup"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE af_global.users
        ADD COLUMN IF NOT EXISTS force_password_reset BOOLEAN NOT NULL DEFAULT FALSE
    """)


def downgrade():
    op.execute("""
    ALTER TABLE af_global.users
        DROP COLUMN IF EXISTS force_password_reset
    """)
