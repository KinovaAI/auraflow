"""Phase 3H — AI Features: churn detection, milestones, marketing drafts

Adds churn_risk_flagged_at column to members, member_milestones table,
and marketing_drafts table to each tenant schema.

Revision ID: a3h_ai01
Revises: a4b_pos01
"""
from alembic import op
import sqlalchemy as sa


revision = "a3h_ai01"
down_revision = "a4b_pos01"
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
        # ── Add churn_risk_flagged_at to members ─────────────────
        conn.execute(sa.text(f"""
            ALTER TABLE "{schema}".members
            ADD COLUMN IF NOT EXISTS churn_risk_flagged_at TIMESTAMPTZ
        """))

        # ── member_milestones ────────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".member_milestones (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                member_id       UUID NOT NULL REFERENCES "{schema}".members(id) ON DELETE CASCADE,
                milestone_type  VARCHAR(50) NOT NULL,
                achieved_at     TIMESTAMPTZ DEFAULT NOW(),
                notified_at     TIMESTAMPTZ,
                CONSTRAINT member_milestone_unique UNIQUE (member_id, milestone_type)
            )
        """))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_milestones_member
            ON "{schema}".member_milestones (member_id)
        """))

        # ── marketing_drafts ─────────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".marketing_drafts (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                prompt_context  TEXT NOT NULL,
                draft_type      VARCHAR(50) NOT NULL DEFAULT 'email',
                subject         TEXT,
                body            TEXT NOT NULL,
                status          VARCHAR(20) NOT NULL DEFAULT 'draft',
                created_by      UUID,
                reviewed_by     UUID,
                reviewed_at     TIMESTAMPTZ,
                campaign_id     UUID,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW(),
                CONSTRAINT draft_type_check
                    CHECK (draft_type IN ('email', 'social', 'sms', 'class_description')),
                CONSTRAINT draft_status_check
                    CHECK (status IN ('draft', 'approved', 'rejected', 'sent'))
            )
        """))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_drafts_status
            ON "{schema}".marketing_drafts (status)
        """))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_drafts_created
            ON "{schema}".marketing_drafts (created_at DESC)
        """))


def downgrade() -> None:
    conn = op.get_bind()

    for schema in _tenant_schemas(conn):
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{schema}".marketing_drafts CASCADE'))
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{schema}".member_milestones CASCADE'))
        conn.execute(sa.text(f"""
            ALTER TABLE "{schema}".members
            DROP COLUMN IF EXISTS churn_risk_flagged_at
        """))
