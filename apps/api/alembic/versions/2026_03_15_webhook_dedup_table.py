"""Add processed_webhook_events table for Stripe idempotency

Revision ID: a11_webhook_dedup
Revises: mfa_totp_001
Create Date: 2026-03-15
"""
from alembic import op

revision = "a11_webhook_dedup"
down_revision = "mfa_totp_001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE IF NOT EXISTS af_global.processed_webhook_events (
        event_id    TEXT PRIMARY KEY,
        event_type  TEXT,
        processed_at TIMESTAMPTZ DEFAULT NOW()
    )
    """)
    # Auto-cleanup: events older than 90 days are safe to remove
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_webhook_events_processed_at
    ON af_global.processed_webhook_events(processed_at)
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS af_global.processed_webhook_events")
