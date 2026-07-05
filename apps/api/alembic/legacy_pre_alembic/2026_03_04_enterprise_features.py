"""enterprise AI + notification + activity + webhook + onboarding tables

Revision ID: enterprise_features_001
Revises: voice_gmb_retention_001
Create Date: 2026-03-04
"""

TENANT_SQL = """
-- ── Chatbot Conversations ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chatbot_conversations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL,
    title           TEXT,
    message_count   INTEGER DEFAULT 0,
    last_message_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chatbot_conv_user ON chatbot_conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_chatbot_conv_last ON chatbot_conversations(last_message_at DESC);

-- ── Chatbot Messages ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chatbot_messages (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID NOT NULL REFERENCES chatbot_conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content         TEXT NOT NULL,
    tool_calls      JSONB,
    tokens_used     INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chatbot_msg_conv ON chatbot_messages(conversation_id, created_at);

-- ── Notifications ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS notifications (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL,
    type            TEXT NOT NULL,
    title           TEXT NOT NULL,
    body            TEXT,
    action_url      TEXT,
    metadata        JSONB DEFAULT '{}',
    is_read         BOOLEAN DEFAULT FALSE,
    read_at         TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notif_unread ON notifications(user_id) WHERE is_read = FALSE;

-- ── Activity Log ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS activity_log (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    actor_type      TEXT NOT NULL,
    actor_id        UUID,
    action          TEXT NOT NULL,
    resource_type   TEXT,
    resource_id     UUID,
    description     TEXT,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_activity_actor ON activity_log(actor_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_activity_resource ON activity_log(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_activity_created ON activity_log(created_at DESC);

-- ── Webhook Configs ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS webhook_configs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    url             TEXT NOT NULL,
    secret          TEXT,
    events          TEXT[] NOT NULL DEFAULT '{}',
    is_active       BOOLEAN DEFAULT TRUE,
    created_by      UUID,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Webhook Deliveries ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    webhook_config_id   UUID NOT NULL REFERENCES webhook_configs(id) ON DELETE CASCADE,
    event_type          TEXT NOT NULL,
    payload             JSONB NOT NULL,
    status              TEXT NOT NULL DEFAULT 'pending',
    response_status     INTEGER,
    response_body       TEXT,
    attempt_count       INTEGER DEFAULT 0,
    max_attempts        INTEGER DEFAULT 5,
    next_retry_at       TIMESTAMPTZ,
    last_attempt_at     TIMESTAMPTZ,
    delivered_at        TIMESTAMPTZ,
    error_message       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_wh_del_retry ON webhook_deliveries(status, next_retry_at) WHERE status IN ('pending', 'failed');
CREATE INDEX IF NOT EXISTS idx_wh_del_config ON webhook_deliveries(webhook_config_id, created_at DESC);

-- ── Onboarding Checklist ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS onboarding_checklist (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    step_key        TEXT NOT NULL UNIQUE,
    title           TEXT NOT NULL,
    description     TEXT,
    sort_order      INTEGER DEFAULT 0,
    completed_at    TIMESTAMPTZ,
    completed_by    UUID,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Seed default onboarding steps ────────────────────────────────
INSERT INTO onboarding_checklist (id, step_key, title, description, sort_order) VALUES
    (uuid_generate_v4(), 'create_studio',     'Set up your studio profile',       'Add studio name, address, and contact info', 1),
    (uuid_generate_v4(), 'add_class_type',    'Create your first class type',     'Define a class like Vinyasa Yoga or HIIT', 2),
    (uuid_generate_v4(), 'create_schedule',   'Add a class to the schedule',      'Schedule your first recurring class', 3),
    (uuid_generate_v4(), 'invite_instructor', 'Invite an instructor',             'Add your first instructor to the platform', 4),
    (uuid_generate_v4(), 'add_member',        'Add your first member',            'Import or manually add a member', 5),
    (uuid_generate_v4(), 'setup_payments',    'Connect Stripe payments',          'Enable online payments and POS', 6),
    (uuid_generate_v4(), 'create_membership', 'Create a membership type',         'Set up your pricing plans', 7),
    (uuid_generate_v4(), 'send_first_email',  'Send your first marketing email',  'Reach out to your members', 8),
    (uuid_generate_v4(), 'customize_branding','Customize your branding',          'Upload logo and set colors', 9),
    (uuid_generate_v4(), 'explore_ai',        'Try the AI assistant',             'Ask the AI chatbot a question about AuraFlow', 10)
ON CONFLICT (step_key) DO NOTHING;
"""

GLOBAL_SQL = ""
