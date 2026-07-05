"""AI token usage tracking and platform settings tables

Revision ID: ai_token_billing_001
Revises: enterprise_features_001
Create Date: 2026-03-05
"""
from alembic import op

revision = "ai_token_billing_001"
down_revision = "enterprise_features_001"
branch_labels = None
depends_on = None

GLOBAL_SQL = """
-- ── AI Token Usage Tracking ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS af_global.ai_token_usage (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id         UUID NOT NULL REFERENCES af_global.organizations(id) ON DELETE CASCADE,
    service_name            VARCHAR(100) NOT NULL,
    function_name           VARCHAR(200) NOT NULL,
    model                   VARCHAR(100) NOT NULL,
    input_tokens            INTEGER NOT NULL DEFAULT 0,
    output_tokens           INTEGER NOT NULL DEFAULT 0,
    total_tokens            INTEGER NOT NULL DEFAULT 0,
    stripe_meter_event_id   VARCHAR(100),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_usage_org
    ON af_global.ai_token_usage(organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_usage_org_month
    ON af_global.ai_token_usage(organization_id, date_trunc('month', created_at));
CREATE INDEX IF NOT EXISTS idx_ai_usage_service
    ON af_global.ai_token_usage(service_name, created_at DESC);

-- ── Platform Settings (key-value with JSONB) ────────────────────────
CREATE TABLE IF NOT EXISTS af_global.platform_settings (
    key                     VARCHAR(100) PRIMARY KEY,
    value                   JSONB NOT NULL,
    description             TEXT,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by              UUID
);

-- Seed default AI billing configuration
INSERT INTO af_global.platform_settings (key, value, description) VALUES
    ('ai_token_rate_cents_per_1k', '3.0', 'Cost per 1,000 AI tokens in cents (after free tier)'),
    ('ai_token_free_tier', '50000', 'Free tokens per organization per month'),
    ('ai_token_billing_enabled', '"true"', 'Whether AI token billing is active'),
    ('ai_token_stripe_meter_id', 'null', 'Stripe Billing Meter ID for ai_tokens'),
    ('ai_token_stripe_price_id', 'null', 'Stripe Price ID for metered AI usage')
ON CONFLICT (key) DO NOTHING;
"""


def upgrade():
    op.execute(GLOBAL_SQL)


def downgrade():
    op.execute("DROP TABLE IF EXISTS af_global.ai_token_usage CASCADE;")
    op.execute("DROP TABLE IF EXISTS af_global.platform_settings CASCADE;")
