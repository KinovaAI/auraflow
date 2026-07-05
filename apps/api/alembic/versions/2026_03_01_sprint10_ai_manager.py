"""Sprint 10 — AI Manager: sub_finder_requests table

Adds sub_finder_requests table for Sub-Finder 3000 feature, and
adds response_text column to resolution_requests for AI Manager responses.

Revision ID: s10_ai01
Revises: a4c_pay01
"""
from alembic import op
import sqlalchemy as sa


revision = "s10_ai01"
down_revision = "a4c_pay01"
branch_labels = None
depends_on = None


def _tenant_schemas(connection) -> list[str]:
    """Return all tenant schema names."""
    rows = connection.execute(
        sa.text("SELECT schema_name FROM af_global.organizations")
    ).fetchall()
    return [r[0] for r in rows]


def upgrade() -> None:
    conn = op.get_bind()

    for schema in _tenant_schemas(conn):
        # ── sub_finder_requests ────────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".sub_finder_requests (
                id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                class_session_id        UUID NOT NULL REFERENCES "{schema}".class_sessions(id),
                original_instructor_id  UUID NOT NULL REFERENCES "{schema}".instructors(id),
                reason                  TEXT,
                status                  VARCHAR(20) DEFAULT 'searching'
                                        CHECK (status IN (
                                            'searching', 'offered', 'filled',
                                            'unfilled', 'cancelled'
                                        )),
                substitute_instructor_id UUID REFERENCES "{schema}".instructors(id),
                contacted_instructors   JSONB DEFAULT '[]'::jsonb,
                ai_summary              TEXT,
                created_at              TIMESTAMPTZ DEFAULT NOW(),
                updated_at              TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_{schema.replace('-', '_')}_subfinder_session
            ON "{schema}".sub_finder_requests (class_session_id)
        """))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_{schema.replace('-', '_')}_subfinder_status
            ON "{schema}".sub_finder_requests (status) WHERE status IN ('searching', 'offered')
        """))

        # ── Add response_text to resolution_requests ───────────────
        conn.execute(sa.text(f"""
            ALTER TABLE "{schema}".resolution_requests
            ADD COLUMN IF NOT EXISTS response_text TEXT
        """))
        conn.execute(sa.text(f"""
            ALTER TABLE "{schema}".resolution_requests
            ADD COLUMN IF NOT EXISTS intent VARCHAR(50)
        """))
        conn.execute(sa.text(f"""
            ALTER TABLE "{schema}".resolution_requests
            ADD COLUMN IF NOT EXISTS sender_type VARCHAR(20)
        """))
        conn.execute(sa.text(f"""
            ALTER TABLE "{schema}".resolution_requests
            ADD COLUMN IF NOT EXISTS sender_id UUID
        """))
        conn.execute(sa.text(f"""
            ALTER TABLE "{schema}".resolution_requests
            ADD COLUMN IF NOT EXISTS sender_phone VARCHAR(20)
        """))
        conn.execute(sa.text(f"""
            ALTER TABLE "{schema}".resolution_requests
            ADD COLUMN IF NOT EXISTS actions_taken JSONB DEFAULT '[]'::jsonb
        """))

        # ── Expand sms_messages type constraint to include AI types ────
        conn.execute(sa.text(f"""
            ALTER TABLE "{schema}".sms_messages DROP CONSTRAINT IF EXISTS sms_messages_type_check
        """))
        conn.execute(sa.text(f"""
            ALTER TABLE "{schema}".sms_messages ADD CONSTRAINT sms_messages_type_check
            CHECK (type IN (
                'transactional', 'marketing', 'reminder',
                'booking_confirmation', 'booking_cancellation', 'waitlist_promotion',
                'payment_failed', 'sub_request', 'sub_confirmation', 'sub_notification',
                'ai_response'
            ))
        """))


def downgrade() -> None:
    conn = op.get_bind()

    for schema in _tenant_schemas(conn):
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{schema}".sub_finder_requests CASCADE'))
        conn.execute(sa.text(f'ALTER TABLE "{schema}".resolution_requests DROP COLUMN IF EXISTS response_text'))
        conn.execute(sa.text(f'ALTER TABLE "{schema}".resolution_requests DROP COLUMN IF EXISTS intent'))
        conn.execute(sa.text(f'ALTER TABLE "{schema}".resolution_requests DROP COLUMN IF EXISTS sender_type'))
        conn.execute(sa.text(f'ALTER TABLE "{schema}".resolution_requests DROP COLUMN IF EXISTS sender_id'))
        conn.execute(sa.text(f'ALTER TABLE "{schema}".resolution_requests DROP COLUMN IF EXISTS sender_phone'))
        conn.execute(sa.text(f'ALTER TABLE "{schema}".resolution_requests DROP COLUMN IF EXISTS actions_taken'))
