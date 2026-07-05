"""Platform email accounts for IMAP/SMTP integration (Purelymail)

Stores per-account IMAP and SMTP credentials so the AI email agent
can fetch mail via IMAP and send replies via SMTP using the correct
From/Reply-To address.

Also adds account_id FK to platform_email_inbox so each email is
linked to the account it was fetched from.

Revision ID: a8_plat03
Revises: a7_plat02
Create Date: 2026-03-03
"""

from alembic import op

revision = "a8_plat03"
down_revision = "a7_plat02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS af_global.platform_email_accounts (
            id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            email_address       VARCHAR(255) NOT NULL UNIQUE,
            display_name        VARCHAR(255) DEFAULT 'AuraFlow',

            -- IMAP settings
            imap_host           VARCHAR(255) NOT NULL DEFAULT 'imap.purelymail.com',
            imap_port           INT NOT NULL DEFAULT 993,
            imap_use_tls        BOOLEAN NOT NULL DEFAULT TRUE,

            -- SMTP settings
            smtp_host           VARCHAR(255) NOT NULL DEFAULT 'smtp.purelymail.com',
            smtp_port           INT NOT NULL DEFAULT 465,
            smtp_use_tls        BOOLEAN NOT NULL DEFAULT TRUE,

            -- Credentials (shared for IMAP and SMTP on most providers)
            username            VARCHAR(255) NOT NULL,
            password_enc        BYTEA NOT NULL,

            -- State
            is_active           BOOLEAN NOT NULL DEFAULT TRUE,
            last_checked_at     TIMESTAMPTZ,
            last_uid            INT DEFAULT 0,

            -- Timestamps
            created_at          TIMESTAMPTZ DEFAULT NOW(),
            updated_at          TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE OR REPLACE TRIGGER trg_platform_email_accounts_updated_at
            BEFORE UPDATE ON af_global.platform_email_accounts
            FOR EACH ROW
            EXECUTE FUNCTION af_global.update_updated_at();

        -- Link emails to the account they were fetched from
        ALTER TABLE af_global.platform_email_inbox
            ADD COLUMN IF NOT EXISTS account_id UUID
            REFERENCES af_global.platform_email_accounts(id) ON DELETE SET NULL;

        CREATE INDEX IF NOT EXISTS idx_email_inbox_account
            ON af_global.platform_email_inbox(account_id);
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE af_global.platform_email_inbox DROP COLUMN IF EXISTS account_id;
        DROP TABLE IF EXISTS af_global.platform_email_accounts CASCADE;
    """)
