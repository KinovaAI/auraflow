"""Phase 3B — YouTube OAuth for uploads

Adds youtube_refresh_token_encrypted to af_global.organizations
and youtube_upload_authorized to connection status.

Revision ID: a2yt01
Revises: a2zm01
"""
from alembic import op
import sqlalchemy as sa


revision = "a2yt01"
down_revision = "a2zm01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE af_global.organizations
        ADD COLUMN IF NOT EXISTS youtube_refresh_token_encrypted BYTEA
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE af_global.organizations
        DROP COLUMN IF EXISTS youtube_refresh_token_encrypted
    """)
