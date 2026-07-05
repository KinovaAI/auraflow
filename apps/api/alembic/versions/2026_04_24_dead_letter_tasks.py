"""Add af_global.dead_letter_tasks for Celery task failures past retry limit

Revision ID: a24_dead_letter
Revises: a23_merge_heads
Create Date: 2026-04-24
"""

revision = "a24_dead_letter"
down_revision = "a23_merge_heads"
branch_labels = None
depends_on = None


def upgrade():
    from alembic import op
    op.execute("""
        CREATE TABLE IF NOT EXISTS af_global.dead_letter_tasks (
            id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            task_name     VARCHAR(255) NOT NULL,
            task_id       VARCHAR(255) UNIQUE,
            args          JSONB,
            kwargs        JSONB,
            exception     TEXT,
            traceback     TEXT,
            retries       INTEGER DEFAULT 0,
            failed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            replayed_at   TIMESTAMPTZ,
            replayed_by   UUID,
            resolution    VARCHAR(30) DEFAULT 'pending'
        );
        CREATE INDEX IF NOT EXISTS idx_dlt_task_name ON af_global.dead_letter_tasks(task_name);
        CREATE INDEX IF NOT EXISTS idx_dlt_failed_at ON af_global.dead_letter_tasks(failed_at DESC);
        CREATE INDEX IF NOT EXISTS idx_dlt_resolution ON af_global.dead_letter_tasks(resolution);
        ALTER TABLE af_global.dead_letter_tasks
          ADD CONSTRAINT dlt_resolution_check
          CHECK (resolution IN ('pending', 'replayed', 'ignored', 'investigating'));
    """)


def downgrade():
    from alembic import op
    op.execute("DROP TABLE IF EXISTS af_global.dead_letter_tasks")
