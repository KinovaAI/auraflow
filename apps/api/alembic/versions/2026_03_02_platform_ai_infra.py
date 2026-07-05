"""Platform AI manager and infrastructure tables

Creates all tables for:
- Phase 1: Email inbox monitoring & AI auto-responder
- Phase 2: Social media management
- Phase 3: Ad campaign management
- Phase 4: AI-generated landing pages
- Phase 5: Infrastructure tools (backups, security, traffic, DB monitoring)

Revision ID: a6_plat01
Revises: a5_fac01
Create Date: 2026-03-02
"""

from alembic import op

revision = "a6_plat01"
down_revision = "a5_fac01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Phase 1: Email Inbox & AI Agent Log ──────────────────────────

    op.execute("""
        CREATE TABLE IF NOT EXISTS af_global.platform_email_inbox (
            id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            message_id        VARCHAR(500),
            mailbox           VARCHAR(50) NOT NULL DEFAULT 'support'
                                  CHECK (mailbox IN ('hello','support')),
            from_email        VARCHAR(255) NOT NULL,
            from_name         VARCHAR(255),
            to_email          VARCHAR(255) NOT NULL,
            subject           VARCHAR(1000),
            body_text         TEXT,
            body_html         TEXT,
            ai_status         VARCHAR(20) DEFAULT 'pending'
                                  CHECK (ai_status IN ('pending','processing','resolved','escalated','failed')),
            ai_response       TEXT,
            ai_summary        TEXT,
            ai_actions        JSONB DEFAULT '[]'::JSONB,
            escalated_to      VARCHAR(255),
            escalation_reason TEXT,
            resolved_at       TIMESTAMPTZ,
            created_at        TIMESTAMPTZ DEFAULT NOW(),
            updated_at        TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_email_inbox_status ON af_global.platform_email_inbox(ai_status);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_email_inbox_mailbox ON af_global.platform_email_inbox(mailbox);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_email_inbox_created ON af_global.platform_email_inbox(created_at DESC);")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_email_inbox_message_id ON af_global.platform_email_inbox(message_id) WHERE message_id IS NOT NULL;")

    op.execute("""
        CREATE TABLE IF NOT EXISTS af_global.platform_ai_agent_log (
            id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            agent_type        VARCHAR(50) NOT NULL,
            action            VARCHAR(100) NOT NULL,
            details           JSONB DEFAULT '{}'::JSONB,
            status            VARCHAR(20) DEFAULT 'success'
                                  CHECK (status IN ('success','failure','pending')),
            related_id        UUID,
            created_at        TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_agent_log_type ON af_global.platform_ai_agent_log(agent_type);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_agent_log_created ON af_global.platform_ai_agent_log(created_at DESC);")

    # ── Phase 2: Social Media ────────────────────────────────────────

    op.execute("""
        CREATE TABLE IF NOT EXISTS af_global.platform_social_posts (
            id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            platform          VARCHAR(20) NOT NULL
                                  CHECK (platform IN ('facebook','instagram')),
            platform_post_id  VARCHAR(255),
            content           TEXT NOT NULL,
            media_urls        JSONB DEFAULT '[]'::JSONB,
            post_type         VARCHAR(30) DEFAULT 'post'
                                  CHECK (post_type IN ('post','story','reel','carousel')),
            status            VARCHAR(20) DEFAULT 'draft'
                                  CHECK (status IN ('draft','scheduled','published','failed')),
            scheduled_at      TIMESTAMPTZ,
            published_at      TIMESTAMPTZ,
            engagement        JSONB DEFAULT '{}'::JSONB,
            ai_generated      BOOLEAN DEFAULT FALSE,
            created_at        TIMESTAMPTZ DEFAULT NOW(),
            updated_at        TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_social_posts_platform ON af_global.platform_social_posts(platform);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_social_posts_status ON af_global.platform_social_posts(status);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_social_posts_scheduled ON af_global.platform_social_posts(scheduled_at) WHERE status = 'scheduled';")

    op.execute("""
        CREATE TABLE IF NOT EXISTS af_global.platform_social_messages (
            id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            platform          VARCHAR(20) NOT NULL
                                  CHECK (platform IN ('facebook','instagram')),
            conversation_id   VARCHAR(255),
            sender_id         VARCHAR(255),
            sender_name       VARCHAR(255),
            message_text      TEXT,
            message_type      VARCHAR(20) DEFAULT 'message'
                                  CHECK (message_type IN ('message','comment','mention')),
            post_id           UUID REFERENCES af_global.platform_social_posts(id) ON DELETE SET NULL,
            ai_status         VARCHAR(20) DEFAULT 'pending'
                                  CHECK (ai_status IN ('pending','processing','resolved','ignored')),
            ai_response       TEXT,
            created_at        TIMESTAMPTZ DEFAULT NOW(),
            updated_at        TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_social_messages_status ON af_global.platform_social_messages(ai_status);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_social_messages_platform ON af_global.platform_social_messages(platform);")

    # ── Phase 3: Ad Campaign Config ──────────────────────────────────

    op.execute("""
        CREATE TABLE IF NOT EXISTS af_global.platform_ads_config (
            id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            google_max_monthly_cents BIGINT DEFAULT 0,
            meta_max_monthly_cents   BIGINT DEFAULT 0,
            location_targets        JSONB DEFAULT '[]'::JSONB,
            google_enabled          BOOLEAN DEFAULT FALSE,
            meta_enabled            BOOLEAN DEFAULT FALSE,
            ai_auto_optimize        BOOLEAN DEFAULT FALSE,
            approval_threshold_cents BIGINT DEFAULT 5000,
            created_at              TIMESTAMPTZ DEFAULT NOW(),
            updated_at              TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    # Seed a single config row
    op.execute("""
        INSERT INTO af_global.platform_ads_config (
            google_max_monthly_cents, meta_max_monthly_cents, location_targets,
            google_enabled, meta_enabled, ai_auto_optimize, approval_threshold_cents
        )
        SELECT 0, 0, '[]'::JSONB, FALSE, FALSE, FALSE, 5000
        WHERE NOT EXISTS (SELECT 1 FROM af_global.platform_ads_config);
    """)

    # ── Phase 4: Landing Pages ───────────────────────────────────────

    op.execute("""
        CREATE TABLE IF NOT EXISTS af_global.platform_landing_pages (
            id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            slug              VARCHAR(200) UNIQUE NOT NULL,
            title             VARCHAR(500) NOT NULL,
            campaign_source   VARCHAR(50),
            campaign_id       VARCHAR(255),
            hero_headline     TEXT,
            hero_subheadline  TEXT,
            hero_cta_text     VARCHAR(100) DEFAULT 'Get Started',
            hero_cta_url      VARCHAR(500),
            features_json     JSONB DEFAULT '[]'::JSONB,
            testimonials_json JSONB DEFAULT '[]'::JSONB,
            custom_sections_json JSONB DEFAULT '[]'::JSONB,
            meta_title        VARCHAR(200),
            meta_description  VARCHAR(500),
            utm_source        VARCHAR(100),
            utm_medium        VARCHAR(100),
            utm_campaign      VARCHAR(200),
            views             INTEGER DEFAULT 0,
            conversions       INTEGER DEFAULT 0,
            status            VARCHAR(20) DEFAULT 'draft'
                                  CHECK (status IN ('draft','active','paused')),
            created_at        TIMESTAMPTZ DEFAULT NOW(),
            updated_at        TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_landing_pages_slug ON af_global.platform_landing_pages(slug);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_landing_pages_status ON af_global.platform_landing_pages(status);")

    # ── Phase 5: Infrastructure — Backups ────────────────────────────

    op.execute("""
        CREATE TABLE IF NOT EXISTS af_global.platform_backups (
            id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            backup_type       VARCHAR(20) NOT NULL
                                  CHECK (backup_type IN ('database','files')),
            status            VARCHAR(20) DEFAULT 'pending'
                                  CHECK (status IN ('pending','running','completed','failed')),
            file_name         VARCHAR(500),
            file_size_bytes   BIGINT,
            b2_file_id        VARCHAR(255),
            b2_bucket         VARCHAR(100),
            duration_seconds  INTEGER,
            error_message     TEXT,
            triggered_by      VARCHAR(20) DEFAULT 'manual'
                                  CHECK (triggered_by IN ('manual','scheduled')),
            created_at        TIMESTAMPTZ DEFAULT NOW(),
            updated_at        TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_backups_type ON af_global.platform_backups(backup_type);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_backups_status ON af_global.platform_backups(status);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_backups_created ON af_global.platform_backups(created_at DESC);")

    op.execute("""
        CREATE TABLE IF NOT EXISTS af_global.platform_backup_schedule (
            id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            backup_type       VARCHAR(20) NOT NULL
                                  CHECK (backup_type IN ('database','files')),
            cron_expression   VARCHAR(100) NOT NULL DEFAULT '0 3 * * *',
            retention_days    INTEGER DEFAULT 30,
            is_active         BOOLEAN DEFAULT TRUE,
            last_run_at       TIMESTAMPTZ,
            next_run_at       TIMESTAMPTZ,
            created_at        TIMESTAMPTZ DEFAULT NOW(),
            updated_at        TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    # Seed default schedules
    op.execute("""
        INSERT INTO af_global.platform_backup_schedule (backup_type, cron_expression, retention_days, is_active)
        SELECT 'database', '0 3 * * *', 30, TRUE
        WHERE NOT EXISTS (SELECT 1 FROM af_global.platform_backup_schedule WHERE backup_type = 'database');
    """)
    op.execute("""
        INSERT INTO af_global.platform_backup_schedule (backup_type, cron_expression, retention_days, is_active)
        SELECT 'files', '0 4 * * 0', 60, TRUE
        WHERE NOT EXISTS (SELECT 1 FROM af_global.platform_backup_schedule WHERE backup_type = 'files');
    """)

    # ── Phase 5: Infrastructure — Security Events ────────────────────

    op.execute("""
        CREATE TABLE IF NOT EXISTS af_global.platform_security_events (
            id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            event_type        VARCHAR(50) NOT NULL
                                  CHECK (event_type IN (
                                      'failed_login','rate_limit','brute_force',
                                      'unusual_api','suspicious_ip','error_spike'
                                  )),
            severity          VARCHAR(10) DEFAULT 'low'
                                  CHECK (severity IN ('low','medium','high','critical')),
            source_ip         VARCHAR(45),
            user_agent        TEXT,
            endpoint          VARCHAR(500),
            details           JSONB DEFAULT '{}'::JSONB,
            acknowledged      BOOLEAN DEFAULT FALSE,
            acknowledged_at   TIMESTAMPTZ,
            acknowledged_by   UUID,
            created_at        TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_security_events_type ON af_global.platform_security_events(event_type);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_security_events_severity ON af_global.platform_security_events(severity);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_security_events_created ON af_global.platform_security_events(created_at DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_security_events_unacked ON af_global.platform_security_events(acknowledged) WHERE acknowledged = FALSE;")

    # ── Phase 5: Infrastructure — Request Metrics ────────────────────

    op.execute("""
        CREATE TABLE IF NOT EXISTS af_global.platform_request_metrics (
            id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            period_start      TIMESTAMPTZ NOT NULL,
            total_requests    INTEGER DEFAULT 0,
            avg_response_ms   NUMERIC(10,2) DEFAULT 0,
            p95_response_ms   NUMERIC(10,2) DEFAULT 0,
            p99_response_ms   NUMERIC(10,2) DEFAULT 0,
            error_count       INTEGER DEFAULT 0,
            unique_ips        INTEGER DEFAULT 0,
            top_endpoints     JSONB DEFAULT '[]'::JSONB,
            status_codes      JSONB DEFAULT '{}'::JSONB,
            geo_data          JSONB DEFAULT '{}'::JSONB,
            created_at        TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_request_metrics_period ON af_global.platform_request_metrics(period_start);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_request_metrics_created ON af_global.platform_request_metrics(created_at DESC);")

    # ── Triggers for updated_at ──────────────────────────────────────

    for table in [
        "platform_email_inbox",
        "platform_social_posts",
        "platform_social_messages",
        "platform_ads_config",
        "platform_landing_pages",
        "platform_backups",
        "platform_backup_schedule",
    ]:
        op.execute(f"""
            CREATE OR REPLACE TRIGGER trg_{table}_updated_at
                BEFORE UPDATE ON af_global.{table}
                FOR EACH ROW
                EXECUTE FUNCTION af_global.update_updated_at();
        """)


def downgrade() -> None:
    tables = [
        "platform_request_metrics",
        "platform_security_events",
        "platform_backup_schedule",
        "platform_backups",
        "platform_landing_pages",
        "platform_ads_config",
        "platform_social_messages",
        "platform_social_posts",
        "platform_ai_agent_log",
        "platform_email_inbox",
    ]
    for table in tables:
        op.execute(f"DROP TABLE IF EXISTS af_global.{table} CASCADE;")
