"""a46_accounting — per-tenant Accounting module tables

Adds the per-tenant bookkeeping ledger that brings a standalone single-tenant
LLC accounting app into AuraFlow as an Accounting module.
Each studio's books live in its own tenant schema (hard-isolated).

Tenant tables (created for every tenant via
af_global.add_accounting_tables_to_schema(), so they exist for BOTH existing
tenants (backfill loop below) and newly provisioned ones (called from
tenant_provisioning.py)):

  - <schema>.acct_categories    — Schedule C taxonomy (code, label, kind,
                                  schedule_c_line, txf_ref). Seeded by the app.
  - <schema>.acct_settings      — single-row: LLC identity + encrypted Mercury
                                  API key + accounts + last_sync_at.
  - <schema>.acct_members       — K-1 partners (ownership %, capital, encrypted TIN).
  - <schema>.acct_transactions  — the ledger: bank-imported + auraflow-derived +
                                  manual entries. amount_cents is POSITIVE; the
                                  `type` column carries the sign (income vs expense),
                                  mirroring the standalone app. Deduped on
                                  (source, external_id). `auraflow_txn_id` links a
                                  reconciled bank deposit to the AuraFlow payment(s)
                                  it settles; `payout_id` links it to the processor
                                  payout (acct_payouts) that batch of payments settled as.
  - <schema>.acct_payouts       — one row per Stripe/Square payout (a batch of many
                                  member payments that lands in the bank as ONE
                                  deposit, net of fees). Reconciliation matches each
                                  payout to its bank deposit so AuraFlow ties to the
                                  bank statement (the authoritative record).
  - <schema>.acct_payout_items  — the payments composing each payout (charge/payment
                                  id + fee), each linked to the AuraFlow `transactions`
                                  row it came from — the per-sale detail + Schedule C
                                  categorization behind a payout's single bank deposit.

Additive only — touches no existing table and never the payment path.
"""
from alembic import op

revision = "a46_accounting"
down_revision = "a44_online_membership_trials"
branch_labels = None
depends_on = None


def upgrade():
    # ── Provisioning helper (single source of truth for the tenant DDL) ──────
    op.execute(r"""
    CREATE OR REPLACE FUNCTION af_global.add_accounting_tables_to_schema(p_schema_name TEXT)
    RETURNS VOID
    LANGUAGE plpgsql
    AS $fn$
    BEGIN
        -- Schedule C category taxonomy (seeded by the app on first use)
        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.acct_categories (
                code            TEXT PRIMARY KEY,
                label           TEXT NOT NULL,
                kind            TEXT NOT NULL
                                  CHECK (kind IN ('income','expense','distribution','transfer')),
                schedule_c_line TEXT,
                txf_ref         TEXT,
                sort_order      INT NOT NULL DEFAULT 0,
                is_custom       BOOLEAN NOT NULL DEFAULT FALSE,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        $ddl$, p_schema_name);

        -- Single-row per-studio settings: LLC identity + encrypted Mercury key
        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.acct_settings (
                id                  INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
                llc_name            TEXT,
                llc_ein             TEXT,
                llc_state           TEXT,
                llc_tax_class       TEXT,
                mercury_api_key_enc BYTEA,
                mercury_accounts    JSONB,
                last_sync_at        TIMESTAMPTZ,
                created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        $ddl$, p_schema_name);

        -- K-1 partners / LLC members
        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.acct_members (
                id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name           TEXT NOT NULL,
                email          TEXT,
                ownership_pct  NUMERIC(6,3) NOT NULL DEFAULT 0
                                 CHECK (ownership_pct >= 0 AND ownership_pct <= 100),
                capital_cents  BIGINT NOT NULL DEFAULT 0 CHECK (capital_cents >= 0),
                tin_encrypted  BYTEA,
                created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        $ddl$, p_schema_name);

        -- The ledger. amount_cents POSITIVE; sign implied by `type`.
        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.acct_transactions (
                id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                txn_date        DATE NOT NULL,
                description     TEXT NOT NULL,
                type            TEXT NOT NULL
                                  CHECK (type IN ('income','expense','distribution','transfer')),
                category        TEXT,
                amount_cents    BIGINT NOT NULL CHECK (amount_cents >= 0),
                source          TEXT NOT NULL DEFAULT 'manual'
                                  CHECK (source IN ('bank','auraflow','manual')),
                external_id     TEXT,
                auraflow_txn_id UUID,
                payout_id       UUID,
                member_id       UUID,
                status          TEXT NOT NULL DEFAULT 'pending'
                                  CHECK (status IN ('pending','reconciled')),
                notes           TEXT,
                created_by      UUID,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        $ddl$, p_schema_name);

        -- dedup key for bank / auraflow imports (manual rows have NULL external_id)
        EXECUTE format($ddl$
            CREATE UNIQUE INDEX IF NOT EXISTS acct_transactions_source_extid_idx
                ON %I.acct_transactions (source, external_id)
                WHERE external_id IS NOT NULL
        $ddl$, p_schema_name);
        EXECUTE format($ddl$
            CREATE INDEX IF NOT EXISTS acct_transactions_date_idx
                ON %I.acct_transactions (txn_date)
        $ddl$, p_schema_name);
        EXECUTE format($ddl$
            CREATE INDEX IF NOT EXISTS acct_transactions_type_idx
                ON %I.acct_transactions (type, status)
        $ddl$, p_schema_name);
        EXECUTE format($ddl$
            CREATE INDEX IF NOT EXISTS acct_transactions_auraflow_idx
                ON %I.acct_transactions (auraflow_txn_id)
                WHERE auraflow_txn_id IS NOT NULL
        $ddl$, p_schema_name);
        EXECUTE format($ddl$
            CREATE INDEX IF NOT EXISTS acct_transactions_payout_idx
                ON %I.acct_transactions (payout_id)
                WHERE payout_id IS NOT NULL
        $ddl$, p_schema_name);

        -- One row per Stripe/Square payout. A payout is a batch of member
        -- payments that lands in the bank as ONE deposit, net of fees.
        -- net_cents is what actually hits the bank (== the bank deposit amount);
        -- gross_cents − fee_cents == net_cents. bank_txn_id links to the matched
        -- acct_transactions bank deposit once reconciled.
        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.acct_payouts (
                id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                provider           TEXT NOT NULL CHECK (provider IN ('stripe','square')),
                provider_payout_id TEXT NOT NULL,
                payout_date        DATE,
                gross_cents        BIGINT NOT NULL DEFAULT 0,
                fee_cents          BIGINT NOT NULL DEFAULT 0,
                net_cents          BIGINT NOT NULL DEFAULT 0,
                status             TEXT,
                bank_txn_id        UUID,
                reconciled         BOOLEAN NOT NULL DEFAULT FALSE,
                discrepancy_cents  BIGINT NOT NULL DEFAULT 0,
                created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        $ddl$, p_schema_name);
        EXECUTE format($ddl$
            CREATE UNIQUE INDEX IF NOT EXISTS acct_payouts_provider_id_idx
                ON %I.acct_payouts (provider, provider_payout_id)
        $ddl$, p_schema_name);
        EXECUTE format($ddl$
            CREATE INDEX IF NOT EXISTS acct_payouts_date_idx
                ON %I.acct_payouts (payout_date)
        $ddl$, p_schema_name);
        EXECUTE format($ddl$
            CREATE INDEX IF NOT EXISTS acct_payouts_unreconciled_idx
                ON %I.acct_payouts (reconciled) WHERE reconciled = FALSE
        $ddl$, p_schema_name);

        -- The individual payments composing each payout. provider_payment_id is
        -- the Stripe charge id / Square payment id; auraflow_txn_id links to the
        -- AuraFlow `transactions` row it came from (per-sale detail + category).
        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.acct_payout_items (
                id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                payout_id           UUID NOT NULL
                                      REFERENCES %I.acct_payouts (id) ON DELETE CASCADE,
                provider_payment_id TEXT NOT NULL,
                auraflow_txn_id     UUID,
                member_id           UUID,
                category            TEXT,
                gross_cents         BIGINT NOT NULL DEFAULT 0,
                fee_cents           BIGINT NOT NULL DEFAULT 0,
                net_cents           BIGINT NOT NULL DEFAULT 0,
                created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        $ddl$, p_schema_name, p_schema_name);
        EXECUTE format($ddl$
            CREATE UNIQUE INDEX IF NOT EXISTS acct_payout_items_uniq_idx
                ON %I.acct_payout_items (payout_id, provider_payment_id)
        $ddl$, p_schema_name);
        EXECUTE format($ddl$
            CREATE INDEX IF NOT EXISTS acct_payout_items_auraflow_idx
                ON %I.acct_payout_items (auraflow_txn_id)
                WHERE auraflow_txn_id IS NOT NULL
        $ddl$, p_schema_name);
    END;
    $fn$;
    """)

    # ── Backfill every existing active/trial tenant ──────────────────────────
    op.execute("""
    DO $$
    DECLARE s TEXT;
    BEGIN
        FOR s IN
            SELECT sch.schema_name
            FROM af_global.organizations o
            JOIN information_schema.schemata sch ON sch.schema_name = o.schema_name
            WHERE o.status IN ('active', 'trial')
        LOOP
            PERFORM af_global.add_accounting_tables_to_schema(s);
        END LOOP;
    END $$;
    """)


def downgrade():
    op.execute("""
    DO $$
    DECLARE s TEXT;
    BEGIN
        FOR s IN
            SELECT sch.schema_name
            FROM af_global.organizations o
            JOIN information_schema.schemata sch ON sch.schema_name = o.schema_name
        LOOP
            EXECUTE format('DROP TABLE IF EXISTS %I.acct_payout_items', s);
            EXECUTE format('DROP TABLE IF EXISTS %I.acct_payouts', s);
            EXECUTE format('DROP TABLE IF EXISTS %I.acct_transactions', s);
            EXECUTE format('DROP TABLE IF EXISTS %I.acct_members', s);
            EXECUTE format('DROP TABLE IF EXISTS %I.acct_settings', s);
            EXECUTE format('DROP TABLE IF EXISTS %I.acct_categories', s);
        END LOOP;
    END $$;
    """)
    op.execute("DROP FUNCTION IF EXISTS af_global.add_accounting_tables_to_schema(TEXT);")
