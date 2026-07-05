-- AuraFlow — AI Engagement Autopilot Schema
-- Run this in each tenant schema to create the engagement campaign tables.
-- These tables track automated AI-driven member re-engagement campaigns.

CREATE TABLE IF NOT EXISTS engagement_campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    member_id UUID NOT NULL,
    engagement_type VARCHAR(30) NOT NULL,
    status VARCHAR(20) DEFAULT 'active'
        CHECK (status IN ('active', 'replied', 'converted', 'completed', 'escalated')),
    priority_score FLOAT DEFAULT 0.0,
    initial_email_sent_at TIMESTAMPTZ,
    last_email_sent_at TIMESTAMPTZ,
    followup_count INTEGER DEFAULT 0,
    reply_count INTEGER DEFAULT 0,
    outcome VARCHAR(30)
        CHECK (outcome IS NULL OR outcome IN (
            'booked', 'purchased_membership', 'visited',
            'opted_out', 'no_response', 'escalated'
        )),
    outcome_at TIMESTAMPTZ,
    escalated_to UUID,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS engagement_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID NOT NULL REFERENCES engagement_campaigns(id) ON DELETE CASCADE,
    direction VARCHAR(10) NOT NULL CHECK (direction IN ('outbound', 'inbound')),
    message_type VARCHAR(20) NOT NULL
        CHECK (message_type IN ('initial', 'followup_1', 'followup_2', 'reply', 'ai_response')),
    subject TEXT,
    body_text TEXT,
    body_html TEXT,
    email_sent_at TIMESTAMPTZ,
    email_message_id VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_engagement_campaigns_member_id
    ON engagement_campaigns(member_id);
CREATE INDEX IF NOT EXISTS idx_engagement_campaigns_status
    ON engagement_campaigns(status);
CREATE INDEX IF NOT EXISTS idx_engagement_campaigns_engagement_type
    ON engagement_campaigns(engagement_type);
CREATE INDEX IF NOT EXISTS idx_engagement_messages_campaign_id
    ON engagement_messages(campaign_id);
