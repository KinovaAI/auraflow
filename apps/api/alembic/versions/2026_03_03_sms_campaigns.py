"""SMS Campaigns & Templates

New tenant tables: sms_campaigns, sms_campaign_sends, sms_templates.
Adds 'ai_response' to sms_messages type check constraint.

Revision ID: a9_sms01
Revises: a8_plat03
"""
from alembic import op

revision = "a9_sms01"
down_revision = "a8_plat03"
branch_labels = None
depends_on = None


def _get_tenant_schemas():
    conn = op.get_bind()
    rows = conn.execute(
        __import__("sqlalchemy").text(
            "SELECT slug FROM af_global.organizations WHERE status != 'suspended'"
        )
    ).fetchall()
    return [f"af_tenant_{r[0].replace('-', '_')}" for r in rows]


def _apply_to_tenant(schema: str):
    safe = schema.replace("-", "_")

    # ── SMS Templates ─────────────────────────────────────────────────────
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS {schema}.sms_templates (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name            VARCHAR(255) NOT NULL,
            slug            VARCHAR(100) NOT NULL UNIQUE,
            body            TEXT NOT NULL,
            description     TEXT,
            variables       TEXT[] DEFAULT ARRAY[]::TEXT[],
            category        VARCHAR(50) DEFAULT 'general'
                                CHECK (category IN (
                                    'general','booking','reminder','cancellation',
                                    'waitlist','payment','winback','milestone',
                                    'marketing','welcome'
                                )),
            is_active       BOOLEAN DEFAULT TRUE,
            created_by      UUID,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            updated_at      TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # ── SMS Campaigns ─────────────────────────────────────────────────────
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS {schema}.sms_campaigns (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name            VARCHAR(255) NOT NULL,
            body            TEXT NOT NULL,
            template_id     UUID REFERENCES {schema}.sms_templates(id) ON DELETE SET NULL,
            status          VARCHAR(20) DEFAULT 'draft'
                                CHECK (status IN ('draft','scheduled','sending','sent','cancelled')),
            audience_filter JSONB DEFAULT '{{}}'::jsonb,
            scheduled_at    TIMESTAMPTZ,
            sent_at         TIMESTAMPTZ,
            recipients      INTEGER DEFAULT 0,
            delivered       INTEGER DEFAULT 0,
            failed          INTEGER DEFAULT 0,
            opt_outs        INTEGER DEFAULT 0,
            created_by      UUID,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            updated_at      TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # ── SMS Campaign Sends ────────────────────────────────────────────────
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS {schema}.sms_campaign_sends (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            campaign_id     UUID NOT NULL REFERENCES {schema}.sms_campaigns(id) ON DELETE CASCADE,
            member_id       UUID NOT NULL,
            to_phone        VARCHAR(20) NOT NULL,
            status          VARCHAR(20) DEFAULT 'queued'
                                CHECK (status IN ('queued','sent','delivered','failed','opted_out')),
            twilio_sid      VARCHAR(100),
            error_message   TEXT,
            created_at      TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # ── Update sms_messages type constraint to include campaign type ──────
    op.execute(f"""
        ALTER TABLE {schema}.sms_messages
        DROP CONSTRAINT IF EXISTS sms_messages_type_check;
    """)
    op.execute(f"""
        ALTER TABLE {schema}.sms_messages
        ADD CONSTRAINT sms_messages_type_check
        CHECK (type IN (
            'transactional','marketing','reminder','ai_response',
            'booking_confirmation','booking_cancellation','waitlist_promotion',
            'payment_failed','campaign','winback','milestone','opt_out','opt_in'
        ));
    """)

    # ── Indexes ───────────────────────────────────────────────────────────
    op.execute(f"CREATE INDEX IF NOT EXISTS idx_{safe}_smscampaigns_status ON {schema}.sms_campaigns(status);")
    op.execute(f"CREATE INDEX IF NOT EXISTS idx_{safe}_smscampaigns_scheduled ON {schema}.sms_campaigns(scheduled_at) WHERE status = 'scheduled';")
    op.execute(f"CREATE INDEX IF NOT EXISTS idx_{safe}_smssends_campaign ON {schema}.sms_campaign_sends(campaign_id);")
    op.execute(f"CREATE INDEX IF NOT EXISTS idx_{safe}_smstemplates_slug ON {schema}.sms_templates(slug);")
    op.execute(f"CREATE INDEX IF NOT EXISTS idx_{safe}_smstemplates_category ON {schema}.sms_templates(category);")

    # ── Seed default SMS templates ────────────────────────────────────────
    op.execute(f"""
        INSERT INTO {schema}.sms_templates (name, slug, body, description, variables, category)
        VALUES
            ('Booking Confirmation', 'booking_confirmation',
             'Hi {{{{member_name}}}}! You''re booked for {{{{class_title}}}} on {{{{session_date}}}} at {{{{session_time}}}}. See you there!',
             'Sent when a member books a class',
             ARRAY['member_name', 'class_title', 'session_date', 'session_time'],
             'booking'),
            ('Booking Cancellation', 'booking_cancellation',
             'Hi {{{{member_name}}}}, your booking for {{{{class_title}}}} on {{{{session_date}}}} has been cancelled.',
             'Sent when a booking is cancelled',
             ARRAY['member_name', 'class_title', 'session_date'],
             'cancellation'),
            ('Class Reminder', 'class_reminder',
             'Reminder: {{{{member_name}}}}, your {{{{class_title}}}} class starts at {{{{session_time}}}} today. See you soon!',
             'Sent 2 hours before class',
             ARRAY['member_name', 'class_title', 'session_time'],
             'reminder'),
            ('Waitlist Promotion', 'waitlist_promotion',
             'Great news {{{{member_name}}}}! A spot opened up in {{{{class_title}}}} on {{{{session_date}}}} at {{{{session_time}}}}. You''re confirmed!',
             'Sent when promoted from waitlist',
             ARRAY['member_name', 'class_title', 'session_date', 'session_time'],
             'waitlist'),
            ('Payment Failed', 'payment_failed',
             'Hi {{{{member_name}}}}, your payment of {{{{amount}}}} could not be processed. Please update your payment method.',
             'Sent on failed payment',
             ARRAY['member_name', 'amount'],
             'payment'),
            ('Welcome', 'welcome',
             'Welcome to {{{{studio_name}}}}, {{{{member_name}}}}! We''re excited to have you. Book your first class today!',
             'Sent to new members',
             ARRAY['member_name', 'studio_name'],
             'welcome'),
            ('Winback', 'winback',
             'We miss you, {{{{member_name}}}}! It''s been a while since your last visit. Come back and try a class this week!',
             'Sent to members at risk of churning',
             ARRAY['member_name'],
             'winback'),
            ('Milestone Celebration', 'milestone',
             'Congratulations {{{{member_name}}}}! You just hit {{{{milestone}}}} classes! Keep up the amazing work!',
             'Sent when a member reaches a class milestone',
             ARRAY['member_name', 'milestone'],
             'milestone')
        ON CONFLICT (slug) DO NOTHING;
    """)


def upgrade():
    for schema in _get_tenant_schemas():
        _apply_to_tenant(schema)


def downgrade():
    for schema in _get_tenant_schemas():
        op.execute(f"DROP TABLE IF EXISTS {schema}.sms_campaign_sends CASCADE;")
        op.execute(f"DROP TABLE IF EXISTS {schema}.sms_campaigns CASCADE;")
        op.execute(f"DROP TABLE IF EXISTS {schema}.sms_templates CASCADE;")
