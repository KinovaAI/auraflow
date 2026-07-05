"""Platform configuration table for email, Google Ads, and Meta credentials

Single-row config table with encrypted sensitive fields (BYTEA via pgcrypto).
Services fall back to environment variables when DB values are NULL.

Revision ID: a7_plat02
Revises: a6_plat01
Create Date: 2026-03-03
"""

from alembic import op

revision = "a7_plat02"
down_revision = "a6_plat01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS af_global.platform_config (
            id                                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

            -- Email / SendGrid
            sendgrid_api_key_enc                BYTEA,
            sendgrid_from_email                 VARCHAR(255) DEFAULT 'hello@example.com',
            sendgrid_from_name                  VARCHAR(100) DEFAULT 'AuraFlow',
            sendgrid_inbound_webhook_secret_enc BYTEA,
            platform_admin_alert_email          VARCHAR(255) DEFAULT 'alerts@example.com',
            support_escalation_email            VARCHAR(255) DEFAULT 'alerts@example.com',

            -- Google Ads (platform-level)
            google_ads_developer_token_enc      BYTEA,
            google_ads_login_customer_id        VARCHAR(100),
            google_client_id                    VARCHAR(255),
            google_client_secret_enc            BYTEA,

            -- Meta / Facebook (platform-level)
            meta_app_id                         VARCHAR(255),
            meta_app_secret_enc                 BYTEA,
            meta_page_access_token_enc          BYTEA,
            meta_page_id                        VARCHAR(255),
            instagram_business_account_id       VARCHAR(255),

            -- Timestamps
            created_at                          TIMESTAMPTZ DEFAULT NOW(),
            updated_at                          TIMESTAMPTZ DEFAULT NOW()
        );

        -- Seed single config row
        INSERT INTO af_global.platform_config (sendgrid_from_email, sendgrid_from_name)
        SELECT 'hello@example.com', 'AuraFlow'
        WHERE NOT EXISTS (SELECT 1 FROM af_global.platform_config);

        -- Updated-at trigger
        CREATE OR REPLACE TRIGGER trg_platform_config_updated_at
            BEFORE UPDATE ON af_global.platform_config
            FOR EACH ROW
            EXECUTE FUNCTION af_global.update_updated_at();
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS af_global.platform_config CASCADE;")
