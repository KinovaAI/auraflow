"""Phase 4 AI — Waitlist Triage, Dynamic Pricing, Reviews

Adds waitlist_mode to studios, drop-in/dynamic pricing columns to
class_sessions, pricing_rules + price_adjustments_log tables, and
reviews table to each tenant schema.

Revision ID: a8_ai_ph4
Revises: a7_plat02
"""
from alembic import op
import sqlalchemy as sa


revision = "a8_ai_ph4"
down_revision = "a7_plat02"
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
        safe = schema.replace("-", "_")

        # ── Waitlist mode on studios ───────────────────────────────
        conn.execute(sa.text(f"""
            ALTER TABLE "{schema}".studios
            ADD COLUMN IF NOT EXISTS waitlist_mode VARCHAR(20) DEFAULT 'fifo';
        """))
        # Add check constraint only if it doesn't exist
        conn.execute(sa.text(f"""
            DO $$ BEGIN
                ALTER TABLE "{schema}".studios
                ADD CONSTRAINT chk_waitlist_mode
                CHECK (waitlist_mode IN ('fifo', 'ai_priority'));
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """))

        # ── Dynamic pricing columns on class_sessions ──────────────
        conn.execute(sa.text(f"""
            ALTER TABLE "{schema}".class_sessions
            ADD COLUMN IF NOT EXISTS drop_in_price_cents INTEGER;
        """))
        conn.execute(sa.text(f"""
            ALTER TABLE "{schema}".class_sessions
            ADD COLUMN IF NOT EXISTS dynamic_price_cents INTEGER;
        """))

        # ── pricing_rules ──────────────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".pricing_rules (
                id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                studio_id   UUID NOT NULL REFERENCES "{schema}".studios(id) ON DELETE CASCADE,
                name        VARCHAR(255) NOT NULL,
                rule_type   VARCHAR(50) NOT NULL
                    CHECK (rule_type IN ('peak_hour', 'fill_rate', 'day_of_week', 'seasonal', 'last_minute')),
                config      JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                is_active   BOOLEAN DEFAULT TRUE,
                created_at  TIMESTAMPTZ DEFAULT NOW(),
                updated_at  TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_{safe}_pricing_rules_studio
            ON "{schema}".pricing_rules (studio_id)
        """))

        # ── price_adjustments_log ──────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".price_adjustments_log (
                id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                class_session_id        UUID NOT NULL REFERENCES "{schema}".class_sessions(id) ON DELETE CASCADE,
                original_price_cents    INTEGER NOT NULL,
                adjusted_price_cents    INTEGER NOT NULL,
                reason                  TEXT,
                rules_applied           JSONB DEFAULT '[]'::jsonb,
                ai_explanation          TEXT,
                applied_by              VARCHAR(50) DEFAULT 'ai'
                    CHECK (applied_by IN ('ai', 'manual')),
                status                  VARCHAR(20) DEFAULT 'suggested'
                    CHECK (status IN ('suggested', 'approved', 'rejected', 'applied')),
                created_at              TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_{safe}_price_adj_session
            ON "{schema}".price_adjustments_log (class_session_id)
        """))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_{safe}_price_adj_created
            ON "{schema}".price_adjustments_log (created_at DESC)
        """))

        # ── reviews ────────────────────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".reviews (
                id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                member_id           UUID NOT NULL REFERENCES "{schema}".members(id) ON DELETE CASCADE,
                class_session_id    UUID NOT NULL REFERENCES "{schema}".class_sessions(id) ON DELETE CASCADE,
                rating              INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
                review_text         TEXT,
                sentiment           VARCHAR(20)
                    CHECK (sentiment IN ('positive', 'neutral', 'negative')),
                sentiment_score     DECIMAL(4,3),
                ai_analysis         TEXT,
                response_text       TEXT,
                response_draft      TEXT,
                responded_by        UUID,
                responded_at        TIMESTAMPTZ,
                is_published        BOOLEAN DEFAULT TRUE,
                is_flagged          BOOLEAN DEFAULT FALSE,
                flag_reason         TEXT,
                created_at          TIMESTAMPTZ DEFAULT NOW(),
                updated_at          TIMESTAMPTZ DEFAULT NOW(),
                CONSTRAINT review_unique UNIQUE (member_id, class_session_id)
            )
        """))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_{safe}_reviews_member
            ON "{schema}".reviews (member_id)
        """))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_{safe}_reviews_session
            ON "{schema}".reviews (class_session_id)
        """))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_{safe}_reviews_sentiment
            ON "{schema}".reviews (sentiment)
        """))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_{safe}_reviews_created
            ON "{schema}".reviews (created_at DESC)
        """))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_{safe}_reviews_rating
            ON "{schema}".reviews (rating)
        """))


def downgrade() -> None:
    conn = op.get_bind()

    for schema in _tenant_schemas(conn):
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{schema}".reviews CASCADE'))
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{schema}".price_adjustments_log CASCADE'))
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{schema}".pricing_rules CASCADE'))
        conn.execute(sa.text(f"""
            ALTER TABLE "{schema}".class_sessions
            DROP COLUMN IF EXISTS dynamic_price_cents;
        """))
        conn.execute(sa.text(f"""
            ALTER TABLE "{schema}".class_sessions
            DROP COLUMN IF EXISTS drop_in_price_cents;
        """))
        conn.execute(sa.text(f"""
            ALTER TABLE "{schema}".studios
            DROP COLUMN IF EXISTS waitlist_mode;
        """))
