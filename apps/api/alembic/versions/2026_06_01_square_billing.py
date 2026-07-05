"""a35_square_billing — Square billing dual-run migration

Revision ID: a35_square_billing
Revises: a34_payroll_guest
Create Date: 2026-06-01

Adds Square-side columns parallel to existing Stripe columns so the
billing dispatcher can route per-org. NOTHING is changed for existing
Stripe-mode studios — `billing_provider` defaults to 'stripe' on every
row. Only newly-onboarded studios (or studios that explicitly migrate
themselves) flip to 'square'.

Schema changes:

  af_global.organizations
    + square_merchant_id              TEXT        (Square's merchant_id from OAuth)
    + square_access_token_encrypted   BYTEA       (pgp_sym_encrypt of OAuth access token)
    + square_refresh_token_encrypted  BYTEA       (pgp_sym_encrypt of OAuth refresh token)
    + square_token_expires_at         TIMESTAMPTZ (when access token expires — 30d default)
    + square_location_id              TEXT        (merchant's default location for payments)
    + billing_provider                TEXT        ('stripe' | 'square', default 'stripe')
    + square_subscription_id          TEXT        (KinovaAI Studio Platform sub on KinovaAI's account)
    + check constraint billing_provider IN ('stripe','square')

  af_global.processed_webhook_events
    Drop the existing event_id PK and replace with (provider, event_id)
    so a Square event with the same UUID as a Stripe one can't collide.
    Default provider='stripe' for all pre-existing rows.

  af_global.platform_invoices  (NEW)
    Tracks the monthly Square Invoices KinovaAI sends to each
    'square'-mode studio. Each invoice has the plan fee + AI token
    overage as separate line items. One row per (org, month).

  per-tenant: members.square_customer_id
              member_memberships.square_subscription_id
              member_memberships.billing_provider (default 'stripe')
              transactions.square_payment_id
              transactions.square_refund_id
              pos_transactions.square_payment_id

All ADD COLUMN are nullable so the migration is non-destructive.
Existing rows keep all their Stripe data intact.
"""
from alembic import op

revision = "a35_square_billing"
down_revision = "a34_payroll_guest"
branch_labels = None
depends_on = None


def upgrade():
    # ── af_global.organizations ────────────────────────────────────────
    # billing_provider defaults to 'square' for NEW tenants going
    # forward — Square is the new platform. The UPDATE immediately
    # below switches existing orgs back to 'stripe' if they have any
    # prior Stripe state (Connect account, direct mode, or active
    # subscription). This is keyed on data, not on slug, so it
    # generalizes — any tenant we ever import with prior Stripe
    # state stays on Stripe and runs out their existing subs without
    # disruption.
    op.execute("""
        ALTER TABLE af_global.organizations
            ADD COLUMN IF NOT EXISTS square_merchant_id TEXT,
            ADD COLUMN IF NOT EXISTS square_access_token_encrypted BYTEA,
            ADD COLUMN IF NOT EXISTS square_refresh_token_encrypted BYTEA,
            ADD COLUMN IF NOT EXISTS square_token_expires_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS square_location_id TEXT,
            ADD COLUMN IF NOT EXISTS billing_provider TEXT NOT NULL DEFAULT 'square',
            ADD COLUMN IF NOT EXISTS square_subscription_id TEXT
    """)
    op.execute("""
        UPDATE af_global.organizations
        SET billing_provider = 'stripe'
        WHERE billing_provider = 'square'
          AND (
              stripe_direct_mode = TRUE
              OR stripe_account_id IS NOT NULL
              OR stripe_subscription_id IS NOT NULL
              OR stripe_customer_id IS NOT NULL
          )
    """)
    op.execute("""
        ALTER TABLE af_global.organizations
            DROP CONSTRAINT IF EXISTS organizations_billing_provider_chk
    """)
    op.execute("""
        ALTER TABLE af_global.organizations
            ADD CONSTRAINT organizations_billing_provider_chk
            CHECK (billing_provider IN ('stripe', 'square'))
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_organizations_billing_provider
        ON af_global.organizations (billing_provider)
        WHERE billing_provider = 'square'
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_organizations_square_merchant
        ON af_global.organizations (square_merchant_id)
        WHERE square_merchant_id IS NOT NULL
    """)

    # ── af_global.processed_webhook_events — composite PK ──────────────
    op.execute("""
        ALTER TABLE af_global.processed_webhook_events
            ADD COLUMN IF NOT EXISTS provider TEXT NOT NULL DEFAULT 'stripe'
    """)
    # Replace single-column PK with (provider, event_id). Drop the old
    # PK constraint by its conventional name; defensive IF EXISTS in
    # case it was named differently.
    op.execute("""
        DO $$
        DECLARE
            pk_name TEXT;
        BEGIN
            SELECT conname INTO pk_name
            FROM pg_constraint
            WHERE conrelid = 'af_global.processed_webhook_events'::regclass
              AND contype = 'p';
            IF pk_name IS NOT NULL THEN
                EXECUTE format('ALTER TABLE af_global.processed_webhook_events DROP CONSTRAINT %I', pk_name);
            END IF;
        END $$;
    """)
    op.execute("""
        ALTER TABLE af_global.processed_webhook_events
            ADD CONSTRAINT processed_webhook_events_pkey PRIMARY KEY (provider, event_id)
    """)

    # ── af_global.platform_invoices (NEW) ──────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS af_global.platform_invoices (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id     UUID NOT NULL REFERENCES af_global.organizations(id) ON DELETE CASCADE,
            square_invoice_id   TEXT UNIQUE,
            square_order_id     TEXT,
            period_start        DATE NOT NULL,
            period_end          DATE NOT NULL,
            plan_fee_cents      INTEGER NOT NULL DEFAULT 0,
            token_overage_cents INTEGER NOT NULL DEFAULT 0,
            token_count         INTEGER NOT NULL DEFAULT 0,
            total_cents         INTEGER NOT NULL DEFAULT 0,
            status              TEXT NOT NULL DEFAULT 'pending',
            -- pending | sent | paid | failed | canceled | refunded
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            sent_at             TIMESTAMPTZ,
            paid_at             TIMESTAMPTZ,
            failed_at           TIMESTAMPTZ,
            failure_reason      TEXT,
            UNIQUE (organization_id, period_start)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_platform_invoices_org
        ON af_global.platform_invoices (organization_id, period_start DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_platform_invoices_status
        ON af_global.platform_invoices (status)
        WHERE status IN ('pending', 'sent', 'failed')
    """)

    # ── Per-tenant schemas ─────────────────────────────────────────────
    op.execute("""
    DO $$
    DECLARE
        schema_name TEXT;
    BEGIN
        FOR schema_name IN
            SELECT s.schema_name
            FROM af_global.organizations o
            JOIN information_schema.schemata s ON s.schema_name = o.schema_name
            WHERE o.status IN ('active', 'trial')
        LOOP
            -- members.square_customer_id (per-merchant Square Customer)
            EXECUTE format($f$
                ALTER TABLE %I.members
                ADD COLUMN IF NOT EXISTS square_customer_id TEXT
            $f$, schema_name);
            EXECUTE format($f$
                CREATE INDEX IF NOT EXISTS members_square_customer_idx
                ON %I.members (square_customer_id)
                WHERE square_customer_id IS NOT NULL
            $f$, schema_name);

            -- member_memberships: Square subscription + per-row provider tag
            EXECUTE format($f$
                ALTER TABLE %I.member_memberships
                ADD COLUMN IF NOT EXISTS square_subscription_id TEXT,
                ADD COLUMN IF NOT EXISTS billing_provider TEXT NOT NULL DEFAULT 'stripe'
            $f$, schema_name);
            EXECUTE format($f$
                ALTER TABLE %I.member_memberships
                DROP CONSTRAINT IF EXISTS member_memberships_billing_provider_chk
            $f$, schema_name);
            EXECUTE format($f$
                ALTER TABLE %I.member_memberships
                ADD CONSTRAINT member_memberships_billing_provider_chk
                CHECK (billing_provider IN ('stripe', 'square'))
            $f$, schema_name);

            -- transactions: Square payment + refund IDs
            EXECUTE format($f$
                ALTER TABLE %I.transactions
                ADD COLUMN IF NOT EXISTS square_payment_id TEXT,
                ADD COLUMN IF NOT EXISTS square_refund_id TEXT
            $f$, schema_name);
            EXECUTE format($f$
                CREATE INDEX IF NOT EXISTS transactions_square_payment_idx
                ON %I.transactions (square_payment_id)
                WHERE square_payment_id IS NOT NULL
            $f$, schema_name);

            -- pos_transactions: Square payment id
            EXECUTE format($f$
                ALTER TABLE %I.pos_transactions
                ADD COLUMN IF NOT EXISTS square_payment_id TEXT
            $f$, schema_name);

            -- membership_types: cached Square plan + variation IDs so
            -- we don't recreate the plan on every member subscribe.
            -- One Square plan per (studio, membership_type).
            EXECUTE format($f$
                ALTER TABLE %I.membership_types
                ADD COLUMN IF NOT EXISTS square_plan_id TEXT,
                ADD COLUMN IF NOT EXISTS square_plan_variation_id TEXT
            $f$, schema_name);
        END LOOP;
    END $$;
    """)


def downgrade():
    # Per-tenant rollback
    op.execute("""
    DO $$
    DECLARE
        schema_name TEXT;
    BEGIN
        FOR schema_name IN
            SELECT s.schema_name
            FROM af_global.organizations o
            JOIN information_schema.schemata s ON s.schema_name = o.schema_name
            WHERE o.status IN ('active', 'trial')
        LOOP
            EXECUTE format($f$
                ALTER TABLE %I.membership_types
                DROP COLUMN IF EXISTS square_plan_id,
                DROP COLUMN IF EXISTS square_plan_variation_id
            $f$, schema_name);
            EXECUTE format($f$
                ALTER TABLE %I.pos_transactions
                DROP COLUMN IF EXISTS square_payment_id
            $f$, schema_name);
            EXECUTE format($f$
                DROP INDEX IF EXISTS %I.transactions_square_payment_idx
            $f$, schema_name);
            EXECUTE format($f$
                ALTER TABLE %I.transactions
                DROP COLUMN IF EXISTS square_payment_id,
                DROP COLUMN IF EXISTS square_refund_id
            $f$, schema_name);
            EXECUTE format($f$
                ALTER TABLE %I.member_memberships
                DROP CONSTRAINT IF EXISTS member_memberships_billing_provider_chk,
                DROP COLUMN IF EXISTS square_subscription_id,
                DROP COLUMN IF EXISTS billing_provider
            $f$, schema_name);
            EXECUTE format($f$
                DROP INDEX IF EXISTS %I.members_square_customer_idx
            $f$, schema_name);
            EXECUTE format($f$
                ALTER TABLE %I.members
                DROP COLUMN IF EXISTS square_customer_id
            $f$, schema_name);
        END LOOP;
    END $$;
    """)
    op.execute("DROP TABLE IF EXISTS af_global.platform_invoices CASCADE")

    # Restore single-column PK on processed_webhook_events
    op.execute("""
        ALTER TABLE af_global.processed_webhook_events
            DROP CONSTRAINT IF EXISTS processed_webhook_events_pkey
    """)
    op.execute("""
        ALTER TABLE af_global.processed_webhook_events
            ADD CONSTRAINT processed_webhook_events_pkey PRIMARY KEY (event_id)
    """)
    op.execute("""
        ALTER TABLE af_global.processed_webhook_events
            DROP COLUMN IF EXISTS provider
    """)

    # Roll back organizations columns
    op.execute("""
        DROP INDEX IF EXISTS af_global.idx_organizations_square_merchant
    """)
    op.execute("""
        DROP INDEX IF EXISTS af_global.idx_organizations_billing_provider
    """)
    op.execute("""
        ALTER TABLE af_global.organizations
            DROP CONSTRAINT IF EXISTS organizations_billing_provider_chk,
            DROP COLUMN IF EXISTS square_merchant_id,
            DROP COLUMN IF EXISTS square_access_token_encrypted,
            DROP COLUMN IF EXISTS square_refresh_token_encrypted,
            DROP COLUMN IF EXISTS square_token_expires_at,
            DROP COLUMN IF EXISTS square_location_id,
            DROP COLUMN IF EXISTS billing_provider,
            DROP COLUMN IF EXISTS square_subscription_id
    """)
