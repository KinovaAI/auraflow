"""Add user_agent_hash + ip_first_seen to refresh_tokens for device binding

Revision ID: a25_refresh_device
Revises: a24_dead_letter
Create Date: 2026-04-24
"""

revision = "a25_refresh_device"
down_revision = "a24_dead_letter"
branch_labels = None
depends_on = None


def upgrade():
    from alembic import op
    op.execute("""
        ALTER TABLE af_global.refresh_tokens
          ADD COLUMN IF NOT EXISTS user_agent_hash  VARCHAR(64),
          ADD COLUMN IF NOT EXISTS ip_first_seen    INET,
          ADD COLUMN IF NOT EXISTS last_refresh_at  TIMESTAMPTZ;
    """)


def downgrade():
    from alembic import op
    op.execute("""
        ALTER TABLE af_global.refresh_tokens
          DROP COLUMN IF EXISTS user_agent_hash,
          DROP COLUMN IF EXISTS ip_first_seen,
          DROP COLUMN IF EXISTS last_refresh_at;
    """)
