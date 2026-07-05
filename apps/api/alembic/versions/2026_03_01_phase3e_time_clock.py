"""Phase 3E — Time Clock & Payroll: entries, payroll runs, line items

Adds time_entries, payroll_runs, and payroll_line_items tables
to each tenant schema for instructor time tracking and payroll.

Revision ID: a2tc01
Revises: a2cm01
"""
from alembic import op
import sqlalchemy as sa


revision = "a2tc01"
down_revision = "a2cm01"
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
        # ── time_entries ──────────────────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".time_entries (
                id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                instructor_id     UUID NOT NULL REFERENCES "{schema}".instructors(id),
                clock_in          TIMESTAMPTZ NOT NULL,
                clock_out         TIMESTAMPTZ,
                break_minutes     INTEGER DEFAULT 0,
                shift_type        VARCHAR(20) DEFAULT 'regular',
                notes             TEXT,
                status            VARCHAR(20) DEFAULT 'pending',
                approved_by       UUID,
                approved_at       TIMESTAMPTZ,
                total_minutes     INTEGER,
                overtime_minutes  INTEGER DEFAULT 0,
                created_at        TIMESTAMPTZ DEFAULT NOW(),
                updated_at        TIMESTAMPTZ DEFAULT NOW(),
                CONSTRAINT time_entries_shift_type_check
                    CHECK (shift_type IN ('regular', 'training', 'admin', 'event')),
                CONSTRAINT time_entries_status_check
                    CHECK (status IN ('pending', 'approved', 'rejected'))
            )
        """))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_time_entries_instructor_clock
            ON "{schema}".time_entries (instructor_id, clock_in)
        """))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_time_entries_pending
            ON "{schema}".time_entries (status) WHERE status = 'pending'
        """))

        # ── payroll_runs ──────────────────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".payroll_runs (
                id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                period_start      DATE NOT NULL,
                period_end        DATE NOT NULL,
                status            VARCHAR(20) DEFAULT 'draft',
                total_gross_cents INTEGER DEFAULT 0,
                total_hours       NUMERIC(8,2) DEFAULT 0,
                created_by        UUID,
                finalized_at      TIMESTAMPTZ,
                created_at        TIMESTAMPTZ DEFAULT NOW(),
                updated_at        TIMESTAMPTZ DEFAULT NOW(),
                CONSTRAINT payroll_runs_status_check
                    CHECK (status IN ('draft', 'finalized', 'exported')),
                CONSTRAINT payroll_runs_period_unique
                    UNIQUE (period_start, period_end)
            )
        """))

        # ── payroll_line_items ────────────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".payroll_line_items (
                id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                payroll_run_id    UUID NOT NULL REFERENCES "{schema}".payroll_runs(id) ON DELETE CASCADE,
                instructor_id     UUID NOT NULL REFERENCES "{schema}".instructors(id),
                hours_worked      NUMERIC(8,2) DEFAULT 0,
                overtime_hours    NUMERIC(8,2) DEFAULT 0,
                classes_taught    INTEGER DEFAULT 0,
                class_pay_cents   INTEGER DEFAULT 0,
                hourly_pay_cents  INTEGER DEFAULT 0,
                overtime_pay_cents INTEGER DEFAULT 0,
                total_gross_cents INTEGER DEFAULT 0,
                created_at        TIMESTAMPTZ DEFAULT NOW(),
                CONSTRAINT payroll_line_items_unique
                    UNIQUE (payroll_run_id, instructor_id)
            )
        """))


def downgrade() -> None:
    conn = op.get_bind()

    for schema in _tenant_schemas(conn):
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{schema}".payroll_line_items CASCADE'))
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{schema}".payroll_runs CASCADE'))
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{schema}".time_entries CASCADE'))
