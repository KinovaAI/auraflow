"""Performance index audit — add missing indexes on hot query paths

Adds CREATE INDEX IF NOT EXISTS for frequently queried columns across
tenant schemas: bookings, transactions, class_sessions, member_memberships,
communication_log, and members.

Revision ID: a9_perf01
Revises: a8_ai_ph4
Create Date: 2026-03-15
"""
from alembic import op
import sqlalchemy as sa

revision = "a9_perf01"
down_revision = "a8_ai_ph4"
branch_labels = None
depends_on = None


# Indexes for performance optimization on hot query paths
# (index_name_suffix, table, columns)
_INDEXES = [
    # Bookings
    ("bookings_member_id", "bookings", "member_id"),
    ("bookings_class_session_id", "bookings", "class_session_id"),
    ("bookings_status", "bookings", "status"),
    ("bookings_reminder_sent", "bookings", "reminder_sent_at"),

    # Transactions
    ("transactions_created_at", "transactions", "created_at"),
    ("transactions_stripe_pi", "transactions", "stripe_payment_intent_id"),

    # Class Sessions
    ("class_sessions_starts_at", "class_sessions", "starts_at"),
    ("class_sessions_series_id", "class_sessions", "series_id"),
    ("class_sessions_studio_id", "class_sessions", "studio_id"),

    # Member Memberships — composite index for common member+status filter
    ("member_memberships_member_status", "member_memberships", "member_id, status"),

    # Communication Log — composite index for type+date range queries
    ("communication_log_type_created", "communication_log", "type, created_at"),

    # Members
    ("members_stripe_customer", "members", "stripe_customer_id"),
]


def _apply_to_tenant(schema: str) -> None:
    """Create performance indexes in a single tenant schema."""
    safe = schema.replace("-", "_")
    for idx_suffix, table, columns in _INDEXES:
        idx_name = f"idx_{safe}_{idx_suffix}"
        op.execute(
            f'CREATE INDEX IF NOT EXISTS {idx_name} ON "{schema}".{table}({columns})'
        )


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT schema_name FROM af_global.organizations "
            "WHERE status != 'cancelled'"
        )
    ).fetchall()
    for row in rows:
        _apply_to_tenant(row[0])


def downgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT schema_name FROM af_global.organizations "
            "WHERE status != 'cancelled'"
        )
    ).fetchall()
    for row in rows:
        safe = row[0].replace("-", "_")
        for idx_suffix, _table, _columns in _INDEXES:
            idx_name = f"idx_{safe}_{idx_suffix}"
            op.execute(f"DROP INDEX IF EXISTS \"{row[0]}\".{idx_name}")
