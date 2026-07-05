"""voice_calls, gmb columns, retention columns

Revision ID: voice_gmb_retention_001
Revises: sms_campaigns_001
Create Date: 2026-03-03
"""

# SQL to run in each tenant schema
TENANT_SQL = """
-- ── Voice Calls table ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS voice_calls (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    member_id       UUID REFERENCES members(id),
    call_type       TEXT NOT NULL,   -- 'waitlist', 'payment_recovery'
    twilio_sid      TEXT,
    to_phone        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'initiated',  -- initiated, ringing, in_progress, completed, failed, no_answer, busy, cancelled
    reference_id    TEXT,            -- booking_id or transaction_id
    reference_type  TEXT,            -- 'booking' or 'transaction'
    error_message   TEXT,
    digits_pressed  TEXT,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_voice_calls_member ON voice_calls(member_id);
CREATE INDEX IF NOT EXISTS idx_voice_calls_twilio_sid ON voice_calls(twilio_sid);
CREATE INDEX IF NOT EXISTS idx_voice_calls_reference ON voice_calls(reference_type, reference_id);

-- ── Reviews: add GMB sync columns ──────────────────────────────────
ALTER TABLE reviews ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'internal';
ALTER TABLE reviews ADD COLUMN IF NOT EXISTS gmb_review_id TEXT;
ALTER TABLE reviews ADD COLUMN IF NOT EXISTS gmb_metadata JSONB;
CREATE INDEX IF NOT EXISTS idx_reviews_gmb_id ON reviews(gmb_review_id) WHERE gmb_review_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_reviews_source ON reviews(source);

-- ── Member Milestones: add video generation columns ────────────────
ALTER TABLE member_milestones ADD COLUMN IF NOT EXISTS video_url TEXT;
ALTER TABLE member_milestones ADD COLUMN IF NOT EXISTS video_provider TEXT;
ALTER TABLE member_milestones ADD COLUMN IF NOT EXISTS video_id TEXT;
ALTER TABLE member_milestones ADD COLUMN IF NOT EXISTS video_status TEXT;

-- ── Members: add ML retention columns ──────────────────────────────
ALTER TABLE members ADD COLUMN IF NOT EXISTS churn_probability FLOAT;
ALTER TABLE members ADD COLUMN IF NOT EXISTS churn_risk_level TEXT;
ALTER TABLE members ADD COLUMN IF NOT EXISTS churn_scored_at TIMESTAMPTZ;
"""

# SQL for global schema (organization_integrations)
GLOBAL_SQL = """
-- ── Organization Integrations table (for GMB, future integrations) ─
CREATE TABLE IF NOT EXISTS af_global.organization_integrations (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id     UUID NOT NULL REFERENCES af_global.organizations(id),
    integration_type    TEXT NOT NULL,  -- 'gmb', 'google_ads', 'meta_ads', etc.
    access_token        TEXT,
    refresh_token       TEXT,
    token_expires_at    TIMESTAMPTZ,
    metadata            JSONB DEFAULT '{}',
    connected_at        TIMESTAMPTZ DEFAULT NOW(),
    disconnected_at     TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(organization_id, integration_type)
);

CREATE INDEX IF NOT EXISTS idx_org_integrations_org ON af_global.organization_integrations(organization_id);
CREATE INDEX IF NOT EXISTS idx_org_integrations_type ON af_global.organization_integrations(integration_type);
"""
