"""Phase 2F — Platform Admin

New global tables: platform_metrics_daily, platform_announcements.

Revision ID: a2pa01
Revises: a2wc01
"""
from alembic import op

revision = "a2pa01"
down_revision = "a2wc01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS af_global.platform_metrics_daily (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            metric_date     DATE NOT NULL UNIQUE,
            total_organizations INTEGER DEFAULT 0,
            active_organizations INTEGER DEFAULT 0,
            total_users     INTEGER DEFAULT 0,
            total_members   INTEGER DEFAULT 0,
            total_revenue_cents BIGINT DEFAULT 0,
            total_bookings  INTEGER DEFAULT 0,
            created_at      TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS af_global.platform_announcements (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            title           VARCHAR(500) NOT NULL,
            body            TEXT,
            type            VARCHAR(20) DEFAULT 'info'
                                CHECK (type IN ('info','warning','maintenance','feature')),
            is_active       BOOLEAN DEFAULT TRUE,
            starts_at       TIMESTAMPTZ,
            ends_at         TIMESTAMPTZ,
            created_by      UUID,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            updated_at      TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_metrics_date ON af_global.platform_metrics_daily(metric_date);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_announcements_active ON af_global.platform_announcements(is_active);")


def downgrade():
    op.execute("DROP TABLE IF EXISTS af_global.platform_announcements;")
    op.execute("DROP TABLE IF EXISTS af_global.platform_metrics_daily;")
