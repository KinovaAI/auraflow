"""Add verified column to platform_backups

Revision ID: a17_backup_verified
Revises: a16_external_api
Create Date: 2026-03-27
"""

revision = "a17_backup_verified"
down_revision = "a16_external_api"
branch_labels = None
depends_on = None


def upgrade():
    from alembic import op
    op.execute("""
        ALTER TABLE af_global.platform_backups
        ADD COLUMN IF NOT EXISTS verified BOOLEAN DEFAULT NULL;
    """)


def downgrade():
    from alembic import op
    op.execute("""
        ALTER TABLE af_global.platform_backups
        DROP COLUMN IF EXISTS verified;
    """)
