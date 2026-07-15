-- ============================================================================
-- AuraFlow (open core (AGPLv3, public)) — SINGLE-FILE database build. No migrations.
-- The Postgres entrypoint runs this once; it builds the ENTIRE schema from scratch:
--   * af_global platform tables + functions
--   * a COMPLETE provision_tenant_schema() that creates ALL tenant tables
--   * config seed rows
--   * a working demo tenant  (login: owner@demo.example.com / demo1234)
-- Regenerated 2026-07-15 from the live production schema. Recreate a dead server:
--   docker compose up -d   (this file builds the DB; restore data from a backup if needed)
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gin;
CREATE SCHEMA IF NOT EXISTS af_global;


-- ── af_global functions ─────────────────────────────────────────────
CREATE FUNCTION af_global.add_accounting_income_link_to_schema(p_schema_name text) RETURNS void
    LANGUAGE plpgsql
    AS $_$
    BEGIN
        EXECUTE format($ddl$
            ALTER TABLE %I.acct_transactions
                ADD COLUMN IF NOT EXISTS processor_payment_id TEXT
        $ddl$, p_schema_name);
        EXECUTE format($ddl$
            CREATE INDEX IF NOT EXISTS acct_transactions_processor_pid_idx
                ON %I.acct_transactions (processor_payment_id)
                WHERE processor_payment_id IS NOT NULL
        $ddl$, p_schema_name);
    END;
    $_$;

CREATE FUNCTION af_global.add_accounting_tables_to_schema(p_schema_name text) RETURNS void
    LANGUAGE plpgsql
    AS $_$
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
    $_$;

CREATE FUNCTION af_global.add_acct_owner_draws_to_schema(p_schema_name text) RETURNS void
    LANGUAGE plpgsql
    AS $_$
    BEGIN
        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.acct_owner_draws (
                id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                owner_pattern  TEXT NOT NULL,
                monthly_cents  BIGINT NOT NULL,
                effective_from DATE NOT NULL,
                effective_to   DATE,
                is_active      BOOLEAN NOT NULL DEFAULT TRUE,
                created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        $ddl$, p_schema_name);
    END;
    $_$;

CREATE FUNCTION af_global.add_acct_vendor_rules_to_schema(p_schema_name text) RETURNS void
    LANGUAGE plpgsql
    AS $_$
    BEGIN
        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.acct_vendor_rules (
                id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                pattern     TEXT NOT NULL,
                category    TEXT NOT NULL,
                txn_type    TEXT
                              CHECK (txn_type IN ('income','expense','distribution','transfer')),
                note        TEXT,
                priority    INT NOT NULL DEFAULT 100,
                is_active   BOOLEAN NOT NULL DEFAULT TRUE,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        $ddl$, p_schema_name);
        EXECUTE format($ddl$
            CREATE INDEX IF NOT EXISTS acct_vendor_rules_active_idx
                ON %I.acct_vendor_rules (priority) WHERE is_active
        $ddl$, p_schema_name);
        EXECUTE format($ddl$
            ALTER TABLE %I.acct_settings
                ADD COLUMN IF NOT EXISTS payroll_w2_start_date DATE
        $ddl$, p_schema_name);
    END;
    $_$;

CREATE FUNCTION af_global.add_api_keys_table(p_schema_name text) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.api_keys (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            key_hash TEXT NOT NULL UNIQUE,
            key_prefix TEXT NOT NULL,
            scopes TEXT[] NOT NULL DEFAULT ''{}'',
            rate_limit_rpm INTEGER NOT NULL DEFAULT 60,
            is_active BOOLEAN DEFAULT TRUE,
            last_used_at TIMESTAMPTZ,
            expires_at TIMESTAMPTZ,
            created_by UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            revoked_at TIMESTAMPTZ
        )', p_schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON %I.api_keys(key_hash) WHERE is_active = TRUE', p_schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_api_keys_prefix ON %I.api_keys(key_prefix)', p_schema_name);
END;
$$;

CREATE FUNCTION af_global.add_de34_filings_to_schema(p_schema_name text) RETURNS void
    LANGUAGE plpgsql
    AS $_$
    BEGIN
        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.de34_filings (
                id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id    UUID NOT NULL UNIQUE,
                filed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                filed_by   UUID,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        $ddl$, p_schema_name);
    END;
    $_$;

CREATE FUNCTION af_global.add_employer_profile_to_schema(p_schema_name text) RETURNS void
    LANGUAGE plpgsql
    AS $_$
    BEGIN
        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.employer_profile (
                id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                legal_name           VARCHAR(255),
                dba_name             VARCHAR(255),
                ein                  VARCHAR(20),
                edd_account_number   VARCHAR(40),
                address_line1        VARCHAR(255),
                address_line2        VARCHAR(255),
                city                 VARCHAR(120),
                state                VARCHAR(2) NOT NULL DEFAULT 'CA',
                postal_code          VARCHAR(20),
                phone                VARCHAR(40),
                -- workers' comp (feeds DLSE-NTE + DWC-7)
                wc_carrier_name      VARCHAR(255),
                wc_policy_number     VARCHAR(80),
                wc_carrier_phone     VARCHAR(40),
                wc_policy_effective  DATE,
                -- pay (feeds DLSE-NTE)
                pay_schedule         VARCHAR(20)
                                       CHECK (pay_schedule IS NULL OR pay_schedule IN ('weekly','biweekly','semimonthly','monthly')),
                regular_payday       VARCHAR(120),
                overtime_basis       VARCHAR(120),
                -- policies
                sick_leave_policy    TEXT,
                created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        $ddl$, p_schema_name);
    END;
    $_$;

CREATE FUNCTION af_global.add_gift_card_tables(p_schema_name text) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.gift_cards (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            code VARCHAR(19) UNIQUE NOT NULL,
            amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
            balance_cents INTEGER NOT NULL CHECK (balance_cents >= 0),
            status VARCHAR(20) NOT NULL DEFAULT ''active'' CHECK (status IN (''active'',''fully_redeemed'',''voided'',''expired'')),
            purchaser_member_id UUID, purchased_by_name VARCHAR(255),
            recipient_email VARCHAR(255), recipient_name VARCHAR(255), message TEXT,
            expires_at TIMESTAMPTZ, voided_at TIMESTAMPTZ, void_reason TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )', p_schema_name);
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.gift_card_redemptions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            gift_card_id UUID NOT NULL REFERENCES %I.gift_cards(id) ON DELETE CASCADE,
            member_id UUID NOT NULL, amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
            transaction_id UUID, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )', p_schema_name, p_schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_gift_cards_code ON %I.gift_cards (code)', p_schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_gift_cards_status ON %I.gift_cards (status)', p_schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_gc_redemptions_gc ON %I.gift_card_redemptions (gift_card_id)', p_schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_gc_redemptions_member ON %I.gift_card_redemptions (member_id)', p_schema_name);
END;
$$;

CREATE FUNCTION af_global.add_hiring_tables_to_schema(p_schema_name text) RETURNS void
    LANGUAGE plpgsql
    AS $_$
    BEGIN
        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.job_applications (
                id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                first_name           VARCHAR(120) NOT NULL,
                last_name            VARCHAR(120) NOT NULL,
                email                VARCHAR(255) NOT NULL,
                phone                VARCHAR(40),
                address_line1        VARCHAR(255),
                address_line2        VARCHAR(255),
                city                 VARCHAR(120),
                state                VARCHAR(60),
                postal_code          VARCHAR(20),
                position_type        VARCHAR(30) NOT NULL DEFAULT 'instructor'
                                       CHECK (position_type IN ('instructor','front_desk','admin','other')),
                position_title       VARCHAR(160),
                employment_type      VARCHAR(20)
                                       CHECK (employment_type IS NULL OR employment_type IN ('full_time','part_time','contract')),
                availability         TEXT,
                earliest_start_date  DATE,
                desired_pay_text     VARCHAR(160),
                authorized_to_work   BOOLEAN NOT NULL DEFAULT FALSE,
                over_18              BOOLEAN NOT NULL DEFAULT FALSE,
                years_experience     INTEGER,
                experience_seniors   TEXT,
                experience_injuries  TEXT,
                experience_pain      TEXT,
                specialties          TEXT[] NOT NULL DEFAULT '{}',
                work_history         JSONB NOT NULL DEFAULT '[]',
                certifications       JSONB NOT NULL DEFAULT '[]',
                yoga_alliance_number VARCHAR(60),
                yoga_alliance_level  VARCHAR(40),
                cpr_first_aid        BOOLEAN NOT NULL DEFAULT FALSE,
                liability_insurance  BOOLEAN NOT NULL DEFAULT FALSE,
                "references"         JSONB NOT NULL DEFAULT '[]',
                cover_letter         TEXT,
                hear_about_us        VARCHAR(160),
                attestation          BOOLEAN NOT NULL DEFAULT FALSE,
                status               VARCHAR(20) NOT NULL DEFAULT 'new'
                                       CHECK (status IN ('new','reviewed','shortlisted','interviewed','offer','hired','rejected')),
                rating               SMALLINT CHECK (rating IS NULL OR (rating >= 0 AND rating <= 5)),
                assigned_reviewer_id UUID,
                reviewed_by          UUID,
                reviewed_at          TIMESTAMPTZ,
                rejection_reason     TEXT,
                hired_user_id        UUID,
                hired_studio_id      UUID,
                hired_role           VARCHAR(30),
                hired_at             TIMESTAMPTZ,
                created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        $ddl$, p_schema_name);

        EXECUTE format($ddl$
            CREATE INDEX IF NOT EXISTS idx_job_apps_status
                ON %I.job_applications (status, created_at DESC)
        $ddl$, p_schema_name);
        EXECUTE format($ddl$
            CREATE INDEX IF NOT EXISTS idx_job_apps_email
                ON %I.job_applications (lower(email))
        $ddl$, p_schema_name);

        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.job_application_documents (
                id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                application_id   UUID NOT NULL REFERENCES %I.job_applications(id) ON DELETE CASCADE,
                doc_type         VARCHAR(30) NOT NULL DEFAULT 'other'
                                   CHECK (doc_type IN ('resume','certification','insurance','yoga_alliance','other')),
                filename         VARCHAR(255) NOT NULL,
                content_type     VARCHAR(120) NOT NULL,
                file_data        BYTEA NOT NULL,
                size_bytes       INTEGER NOT NULL,
                uploaded_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        $ddl$, p_schema_name, p_schema_name);
        EXECUTE format($ddl$
            CREATE INDEX IF NOT EXISTS idx_job_app_docs_app
                ON %I.job_application_documents (application_id)
        $ddl$, p_schema_name);

        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.job_application_events (
                id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                application_id   UUID NOT NULL REFERENCES %I.job_applications(id) ON DELETE CASCADE,
                event_type       VARCHAR(30) NOT NULL
                                   CHECK (event_type IN ('created','status_changed','note','rated','document_uploaded','hired')),
                from_status      VARCHAR(20),
                to_status        VARCHAR(20),
                note             TEXT,
                actor_user_id    UUID,
                created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        $ddl$, p_schema_name, p_schema_name);
        EXECUTE format($ddl$
            CREATE INDEX IF NOT EXISTS idx_job_app_events_app
                ON %I.job_application_events (application_id, created_at)
        $ddl$, p_schema_name);

        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.employee_w4_forms (
                id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                application_id          UUID REFERENCES %I.job_applications(id) ON DELETE SET NULL,
                user_id                 UUID NOT NULL,
                first_name              VARCHAR(120) NOT NULL,
                middle_initial          VARCHAR(4),
                last_name               VARCHAR(120) NOT NULL,
                address_line1           VARCHAR(255),
                address_line2           VARCHAR(255),
                city                    VARCHAR(120),
                state                   VARCHAR(60),
                postal_code             VARCHAR(20),
                ssn_encrypted           BYTEA,
                filing_status           VARCHAR(24)
                                          CHECK (filing_status IS NULL OR filing_status IN ('single','married_jointly','head_of_household')),
                multiple_jobs           BOOLEAN NOT NULL DEFAULT FALSE,
                dependents_amount_cents INTEGER NOT NULL DEFAULT 0,
                other_income_cents      INTEGER NOT NULL DEFAULT 0,
                deductions_cents        INTEGER NOT NULL DEFAULT 0,
                extra_withholding_cents INTEGER NOT NULL DEFAULT 0,
                exempt                  BOOLEAN NOT NULL DEFAULT FALSE,
                signing_token           CHAR(64),
                signing_token_expires_at TIMESTAMPTZ,
                signature_text          VARCHAR(255),
                signed_at               TIMESTAMPTZ,
                signed_ip               VARCHAR(64),
                status                  VARCHAR(16) NOT NULL DEFAULT 'pending'
                                          CHECK (status IN ('pending','completed')),
                signed_pdf              BYTEA,
                created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        $ddl$, p_schema_name, p_schema_name);
        EXECUTE format($ddl$
            CREATE UNIQUE INDEX IF NOT EXISTS idx_w4_token
                ON %I.employee_w4_forms (signing_token)
                WHERE signing_token IS NOT NULL
        $ddl$, p_schema_name);
        EXECUTE format($ddl$
            CREATE INDEX IF NOT EXISTS idx_w4_user
                ON %I.employee_w4_forms (user_id)
        $ddl$, p_schema_name);
    END;
    $_$;

CREATE FUNCTION af_global.add_onboarding_tables_to_schema(p_schema_name text) RETURNS void
    LANGUAGE plpgsql
    AS $_$
    BEGIN
        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.onboarding_packets (
                id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id                  UUID NOT NULL,
                application_id           UUID,
                first_name               VARCHAR(120),
                last_name                VARCHAR(120),
                email                    VARCHAR(255),
                signing_token            CHAR(64),
                signing_token_expires_at TIMESTAMPTZ,
                status                   VARCHAR(16) NOT NULL DEFAULT 'pending'
                                           CHECK (status IN ('pending','completed')),
                created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        $ddl$, p_schema_name);
        EXECUTE format($ddl$
            CREATE UNIQUE INDEX IF NOT EXISTS idx_onboarding_packet_token
                ON %I.onboarding_packets (signing_token) WHERE signing_token IS NOT NULL
        $ddl$, p_schema_name);
        EXECUTE format($ddl$
            CREATE INDEX IF NOT EXISTS idx_onboarding_packet_user
                ON %I.onboarding_packets (user_id)
        $ddl$, p_schema_name);

        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.onboarding_documents (
                id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                packet_id       UUID NOT NULL REFERENCES %I.onboarding_packets(id) ON DELETE CASCADE,
                user_id         UUID NOT NULL,
                doc_type        VARCHAR(40) NOT NULL,
                kind            VARCHAR(20) NOT NULL DEFAULT 'form_fillable'
                                  CHECK (kind IN ('form_fillable','acknowledgment')),
                title           VARCHAR(200) NOT NULL,
                sort_order      INTEGER NOT NULL DEFAULT 0,
                form_data       JSONB NOT NULL DEFAULT '{}',
                ssn_encrypted   BYTEA,
                status          VARCHAR(16) NOT NULL DEFAULT 'pending'
                                  CHECK (status IN ('pending','completed')),
                signature_text  VARCHAR(255),
                signed_at       TIMESTAMPTZ,
                signed_ip       VARCHAR(64),
                signed_pdf      BYTEA,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        $ddl$, p_schema_name, p_schema_name);
        EXECUTE format($ddl$
            CREATE INDEX IF NOT EXISTS idx_onboarding_docs_packet
                ON %I.onboarding_documents (packet_id, sort_order)
        $ddl$, p_schema_name);
        EXECUTE format($ddl$
            CREATE INDEX IF NOT EXISTS idx_onboarding_docs_user
                ON %I.onboarding_documents (user_id)
        $ddl$, p_schema_name);
    END;
    $_$;

CREATE FUNCTION af_global.add_online_membership_trial_fields(p_schema text) RETURNS void
    LANGUAGE plpgsql
    AS $_$
        BEGIN
            EXECUTE format($f$
                ALTER TABLE %I.members
                ADD COLUMN IF NOT EXISTS facility_name TEXT
            $f$, p_schema);

            EXECUTE format($f$
                ALTER TABLE %I.member_memberships
                ADD COLUMN IF NOT EXISTS trial_period_end TIMESTAMPTZ
            $f$, p_schema);

            EXECUTE format($f$
                ALTER TABLE %I.membership_types
                ADD COLUMN IF NOT EXISTS is_online BOOLEAN NOT NULL DEFAULT FALSE,
                ADD COLUMN IF NOT EXISTS standing_zoom_url TEXT,
                ADD COLUMN IF NOT EXISTS standing_zoom_meeting_id TEXT,
                ADD COLUMN IF NOT EXISTS standing_zoom_password TEXT
            $f$, p_schema);

            -- Find trial conversions due (the renewal scheduler charges these).
            EXECUTE format($f$
                CREATE INDEX IF NOT EXISTS member_memberships_trial_period_end_idx
                ON %I.member_memberships (trial_period_end)
                WHERE trial_period_end IS NOT NULL
            $f$, p_schema);
        END;
        $_$;

CREATE FUNCTION af_global.add_sub_requests_table(p_schema_name text) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.sub_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            class_session_id UUID NOT NULL,
            original_instructor_id UUID NOT NULL,
            reason TEXT,
            status VARCHAR(20) NOT NULL DEFAULT ''searching''
                CHECK (status IN (''searching'', ''sub_found'', ''escalated'', ''cancelled'')),
            sub_instructor_id UUID,
            current_attempt_instructor_id UUID,
            attempt_count INTEGER DEFAULT 0,
            attempted_instructor_ids UUID[] DEFAULT ''{}'',
            resolved_at TIMESTAMPTZ,
            escalated_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )', p_schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_sub_requests_session ON %I.sub_requests (class_session_id)', p_schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_sub_requests_status ON %I.sub_requests (status) WHERE status = ''searching''', p_schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_sub_requests_current ON %I.sub_requests (current_attempt_instructor_id) WHERE status = ''searching''', p_schema_name);
END;
$$;

CREATE FUNCTION af_global.touch_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$;

CREATE FUNCTION af_global.update_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

-- ── provision_tenant_schema (COMPLETE — every tenant table) ─────────
CREATE OR REPLACE FUNCTION af_global.provision_tenant_schema(p_schema TEXT, p_org_id UUID)
RETURNS VOID AS $fn$
BEGIN
    EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I', p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.acct_categories (
    code text NOT NULL,
    label text NOT NULL,
    kind text NOT NULL,
    schedule_c_line text,
    txf_ref text,
    sort_order integer DEFAULT 0 NOT NULL,
    is_custom boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT acct_categories_kind_check CHECK ((kind = ANY (ARRAY['income'::text, 'expense'::text, 'distribution'::text, 'transfer'::text])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.acct_members (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    email text,
    ownership_pct numeric(6,3) DEFAULT 0 NOT NULL,
    capital_cents bigint DEFAULT 0 NOT NULL,
    tin_encrypted bytea,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT acct_members_capital_cents_check CHECK ((capital_cents >= 0)),
    CONSTRAINT acct_members_ownership_pct_check CHECK (((ownership_pct >= (0)::numeric) AND (ownership_pct <= (100)::numeric)))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.acct_owner_draws (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    owner_pattern text NOT NULL,
    monthly_cents bigint NOT NULL,
    effective_from date NOT NULL,
    effective_to date,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.acct_payout_items (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    payout_id uuid NOT NULL,
    provider_payment_id text NOT NULL,
    auraflow_txn_id uuid,
    member_id uuid,
    category text,
    gross_cents bigint DEFAULT 0 NOT NULL,
    fee_cents bigint DEFAULT 0 NOT NULL,
    net_cents bigint DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.acct_payouts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    provider text NOT NULL,
    provider_payout_id text NOT NULL,
    payout_date date,
    gross_cents bigint DEFAULT 0 NOT NULL,
    fee_cents bigint DEFAULT 0 NOT NULL,
    net_cents bigint DEFAULT 0 NOT NULL,
    status text,
    bank_txn_id uuid,
    reconciled boolean DEFAULT false NOT NULL,
    discrepancy_cents bigint DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT acct_payouts_provider_check CHECK ((provider = ANY (ARRAY['stripe'::text, 'square'::text])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.acct_settings (
    id integer DEFAULT 1 NOT NULL,
    llc_name text,
    llc_ein text,
    llc_state text,
    llc_tax_class text,
    mercury_api_key_enc bytea,
    mercury_accounts jsonb,
    last_sync_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    payroll_w2_start_date date,
    CONSTRAINT acct_settings_id_check CHECK ((id = 1))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.acct_transactions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    txn_date date NOT NULL,
    description text NOT NULL,
    type text NOT NULL,
    category text,
    amount_cents bigint NOT NULL,
    source text DEFAULT 'manual'::text NOT NULL,
    external_id text,
    auraflow_txn_id uuid,
    payout_id uuid,
    member_id uuid,
    status text DEFAULT 'pending'::text NOT NULL,
    notes text,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    processor_payment_id text,
    CONSTRAINT acct_transactions_amount_cents_check CHECK ((amount_cents >= 0)),
    CONSTRAINT acct_transactions_source_check CHECK ((source = ANY (ARRAY['bank'::text, 'auraflow'::text, 'manual'::text]))),
    CONSTRAINT acct_transactions_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'reconciled'::text]))),
    CONSTRAINT acct_transactions_type_check CHECK ((type = ANY (ARRAY['income'::text, 'expense'::text, 'distribution'::text, 'transfer'::text])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.acct_vendor_rules (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    pattern text NOT NULL,
    category text NOT NULL,
    txn_type text,
    note text,
    priority integer DEFAULT 100 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT acct_vendor_rules_txn_type_check CHECK ((txn_type = ANY (ARRAY['income'::text, 'expense'::text, 'distribution'::text, 'transfer'::text])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.activity_log (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    actor_type text NOT NULL,
    actor_id uuid,
    action text NOT NULL,
    resource_type text,
    resource_id uuid,
    description text,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.api_keys (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    key_hash text NOT NULL,
    key_prefix text NOT NULL,
    scopes text[] DEFAULT '{}'::text[] NOT NULL,
    rate_limit_rpm integer DEFAULT 60 NOT NULL,
    is_active boolean DEFAULT true,
    last_used_at timestamp with time zone,
    expires_at timestamp with time zone,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    revoked_at timestamp with time zone
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.bookings (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    member_id uuid NOT NULL,
    class_session_id uuid NOT NULL,
    status character varying(20) DEFAULT 'confirmed'::character varying,
    booked_at timestamp with time zone DEFAULT now(),
    cancelled_at timestamp with time zone,
    cancellation_reason text,
    checked_in_at timestamp with time zone,
    late_cancel boolean DEFAULT false,
    late_cancel_fee_charged boolean DEFAULT false,
    source character varying(50) DEFAULT 'web'::character varying,
    waitlist_position integer,
    membership_id uuid,
    notes text,
    guest_name character varying(255),
    guest_email character varying(255),
    reminder_sent_at timestamp with time zone,
    zoom_link_sent_at timestamp with time zone,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    post_class_followup_sent_at timestamp with time zone,
    attendance_mode text DEFAULT 'in_studio'::text NOT NULL,
    CONSTRAINT bookings_attendance_mode_check CHECK ((attendance_mode = ANY (ARRAY['in_studio'::text, 'online'::text]))),
    CONSTRAINT bookings_status_check CHECK (((status)::text = ANY ((ARRAY['confirmed'::character varying, 'booked'::character varying, 'waitlisted'::character varying, 'checked_in'::character varying, 'no_show'::character varying, 'cancelled'::character varying, 'late_cancel'::character varying, 'attended'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.chatbot_conversations (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    user_id uuid NOT NULL,
    title text,
    message_count integer DEFAULT 0,
    last_message_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.chatbot_messages (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    conversation_id uuid NOT NULL,
    role text NOT NULL,
    content text NOT NULL,
    tool_calls jsonb,
    tokens_used integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chatbot_messages_role_check CHECK ((role = ANY (ARRAY['user'::text, 'assistant'::text])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.class_series (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    studio_id uuid NOT NULL,
    class_type_id uuid NOT NULL,
    instructor_id uuid,
    room_id uuid,
    title character varying(255) NOT NULL,
    rrule text NOT NULL,
    start_time time without time zone NOT NULL,
    duration_minutes integer NOT NULL,
    capacity integer,
    waitlist_capacity integer DEFAULT 10,
    effective_from date NOT NULL,
    effective_until date,
    timezone character varying(50) DEFAULT 'America/Los_Angeles'::character varying NOT NULL,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    is_virtual boolean DEFAULT false,
    auto_record boolean DEFAULT false
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.class_sessions (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    studio_id uuid NOT NULL,
    class_type_id uuid NOT NULL,
    instructor_id uuid,
    title character varying(255) NOT NULL,
    description text,
    starts_at timestamp with time zone NOT NULL,
    ends_at timestamp with time zone NOT NULL,
    timezone character varying(50) NOT NULL,
    capacity integer NOT NULL,
    waitlist_capacity integer DEFAULT 10,
    is_virtual boolean DEFAULT false,
    zoom_meeting_id character varying(100),
    zoom_join_url text,
    zoom_password character varying(100),
    status character varying(20) DEFAULT 'scheduled'::character varying,
    cancellation_reason text,
    recurrence_id uuid,
    room_id uuid,
    series_id uuid,
    substitute_instructor_id uuid,
    notes text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    auto_record boolean DEFAULT false,
    recording_status character varying(30) DEFAULT 'none'::character varying,
    recording_url text,
    video_id uuid,
    drop_in_price_cents integer,
    dynamic_price_cents integer,
    is_community boolean DEFAULT false,
    modality text DEFAULT 'in_studio'::text NOT NULL,
    CONSTRAINT chk_af_tenant_recording_status CHECK (((recording_status)::text = ANY ((ARRAY['none'::character varying, 'recording'::character varying, 'processing'::character varying, 'ready'::character varying, 'published'::character varying, 'failed'::character varying])::text[]))),
    CONSTRAINT class_sessions_modality_check CHECK ((modality = ANY (ARRAY['in_studio'::text, 'virtual'::text, 'hybrid'::text]))),
    CONSTRAINT class_sessions_status_check CHECK (((status)::text = ANY ((ARRAY['scheduled'::character varying, 'in_progress'::character varying, 'completed'::character varying, 'cancelled'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.class_types (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    studio_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    duration_minutes integer DEFAULT 60 NOT NULL,
    color character varying(7) DEFAULT '#4F46E5'::character varying,
    capacity integer DEFAULT 20,
    level character varying(30) DEFAULT 'all_levels'::character varying,
    tags text[] DEFAULT '{}'::text[],
    category character varying(100),
    image_url text,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now()
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.classpass_config (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    studio_id uuid NOT NULL,
    venue_id character varying(100),
    api_key_encrypted bytea,
    is_active boolean DEFAULT false,
    credit_rate integer DEFAULT 1,
    auto_confirm boolean DEFAULT true,
    max_spots_per_class integer DEFAULT 3,
    blackout_class_types uuid[] DEFAULT '{}'::uuid[],
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.classpass_reservations (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    classpass_reservation_id character varying(100) NOT NULL,
    class_session_id uuid,
    booking_id uuid,
    customer_name character varying(255),
    customer_email character varying(255),
    credits integer DEFAULT 0,
    status character varying(20) DEFAULT 'reserved'::character varying,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT classpass_reservations_status_check CHECK (((status)::text = ANY ((ARRAY['reserved'::character varying, 'confirmed'::character varying, 'cancelled'::character varying, 'no_show'::character varying, 'completed'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.communication_log (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    member_id uuid,
    channel character varying(20) NOT NULL,
    type character varying(50) NOT NULL,
    recipient character varying(255) NOT NULL,
    subject character varying(500),
    body_preview text,
    provider_id character varying(255),
    status character varying(20) DEFAULT 'sent'::character varying,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT communication_log_channel_check CHECK (((channel)::text = ANY ((ARRAY['email'::character varying, 'sms'::character varying, 'push'::character varying])::text[]))),
    CONSTRAINT communication_log_status_check CHECK (((status)::text = ANY ((ARRAY['sent'::character varying, 'delivered'::character varying, 'failed'::character varying, 'bounced'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.course_enrollments (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    course_id uuid NOT NULL,
    member_id uuid NOT NULL,
    status character varying(20) DEFAULT 'enrolled'::character varying,
    paid_price_cents integer,
    transaction_id uuid,
    enrolled_at timestamp with time zone DEFAULT now(),
    withdrawn_at timestamp with time zone,
    completed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT course_enrollments_status_check CHECK (((status)::text = ANY ((ARRAY['enrolled'::character varying, 'withdrawn'::character varying, 'completed'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.course_session_attendance (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    course_session_id uuid NOT NULL,
    member_id uuid NOT NULL,
    status character varying(20) DEFAULT 'attended'::character varying,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT course_session_attendance_status_check CHECK (((status)::text = ANY ((ARRAY['attended'::character varying, 'absent'::character varying, 'late'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.course_sessions (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    course_id uuid NOT NULL,
    title character varying(500),
    session_number integer DEFAULT 1 NOT NULL,
    starts_at timestamp with time zone NOT NULL,
    ends_at timestamp with time zone NOT NULL,
    location text,
    is_virtual boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.courses (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    studio_id uuid,
    title character varying(500) NOT NULL,
    description text,
    type character varying(30) DEFAULT 'workshop'::character varying NOT NULL,
    instructor_id uuid,
    price_cents integer DEFAULT 0 NOT NULL,
    early_bird_price_cents integer,
    early_bird_deadline timestamp with time zone,
    capacity integer,
    min_enrollment integer,
    location text,
    is_virtual boolean DEFAULT false,
    image_url text,
    prerequisites text,
    status character varying(20) DEFAULT 'draft'::character varying,
    registration_opens timestamp with time zone,
    registration_closes timestamp with time zone,
    starts_at timestamp with time zone,
    ends_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    guest_instructor_id uuid,
    flyer_image_data bytea,
    flyer_image_mime character varying(50),
    CONSTRAINT chk_courses_guest_only_for_workshops CHECK (((guest_instructor_id IS NULL) OR ((type)::text = 'workshop'::text))),
    CONSTRAINT courses_status_check CHECK (((status)::text = ANY ((ARRAY['draft'::character varying, 'published'::character varying, 'in_progress'::character varying, 'completed'::character varying, 'cancelled'::character varying])::text[]))),
    CONSTRAINT courses_type_check CHECK (((type)::text = ANY ((ARRAY['workshop'::character varying, 'course'::character varying, 'teacher_training'::character varying, 'retreat'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.de34_filings (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    filed_at timestamp with time zone DEFAULT now() NOT NULL,
    filed_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.email_campaign_sends (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    campaign_id uuid NOT NULL,
    member_id uuid NOT NULL,
    email character varying(255) NOT NULL,
    status character varying(20) DEFAULT 'queued'::character varying,
    sendgrid_message_id character varying(255),
    opened_at timestamp with time zone,
    clicked_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT email_campaign_sends_status_check CHECK (((status)::text = ANY ((ARRAY['queued'::character varying, 'sent'::character varying, 'delivered'::character varying, 'opened'::character varying, 'clicked'::character varying, 'bounced'::character varying, 'failed'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.email_campaigns (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    name character varying(255) NOT NULL,
    subject character varying(500) NOT NULL,
    html_content text,
    status character varying(20) DEFAULT 'draft'::character varying,
    audience_filter jsonb DEFAULT '{}'::jsonb,
    scheduled_at timestamp with time zone,
    sent_at timestamp with time zone,
    recipients integer DEFAULT 0,
    delivered integer DEFAULT 0,
    opened integer DEFAULT 0,
    clicked integer DEFAULT 0,
    bounced integer DEFAULT 0,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT email_campaigns_status_check CHECK (((status)::text = ANY ((ARRAY['draft'::character varying, 'scheduled'::character varying, 'sending'::character varying, 'sent'::character varying, 'cancelled'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.employee_w4_forms (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    application_id uuid,
    user_id uuid NOT NULL,
    first_name character varying(120) NOT NULL,
    middle_initial character varying(4),
    last_name character varying(120) NOT NULL,
    address_line1 character varying(255),
    address_line2 character varying(255),
    city character varying(120),
    state character varying(60),
    postal_code character varying(20),
    ssn_encrypted bytea,
    filing_status character varying(24),
    multiple_jobs boolean DEFAULT false NOT NULL,
    dependents_amount_cents integer DEFAULT 0 NOT NULL,
    other_income_cents integer DEFAULT 0 NOT NULL,
    deductions_cents integer DEFAULT 0 NOT NULL,
    extra_withholding_cents integer DEFAULT 0 NOT NULL,
    exempt boolean DEFAULT false NOT NULL,
    signing_token character(64),
    signing_token_expires_at timestamp with time zone,
    signature_text character varying(255),
    signed_at timestamp with time zone,
    signed_ip character varying(64),
    status character varying(16) DEFAULT 'pending'::character varying NOT NULL,
    signed_pdf bytea,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT employee_w4_forms_filing_status_check CHECK (((filing_status IS NULL) OR ((filing_status)::text = ANY ((ARRAY['single'::character varying, 'married_jointly'::character varying, 'head_of_household'::character varying])::text[])))),
    CONSTRAINT employee_w4_forms_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'completed'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.employer_profile (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    legal_name character varying(255),
    dba_name character varying(255),
    ein character varying(20),
    edd_account_number character varying(40),
    address_line1 character varying(255),
    address_line2 character varying(255),
    city character varying(120),
    state character varying(2) DEFAULT 'CA'::character varying NOT NULL,
    postal_code character varying(20),
    phone character varying(40),
    wc_carrier_name character varying(255),
    wc_policy_number character varying(80),
    wc_carrier_phone character varying(40),
    wc_policy_effective date,
    pay_schedule character varying(20),
    regular_payday character varying(120),
    overtime_basis character varying(120),
    sick_leave_policy text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT employer_profile_pay_schedule_check CHECK (((pay_schedule IS NULL) OR ((pay_schedule)::text = ANY ((ARRAY['weekly'::character varying, 'biweekly'::character varying, 'semimonthly'::character varying, 'monthly'::character varying])::text[]))))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.emr_encounter_log (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    booking_id uuid NOT NULL,
    member_id uuid NOT NULL,
    emr_encounter_id character varying(255),
    encounter_type character varying(50) NOT NULL,
    class_title character varying(255),
    instructor_name character varying(255),
    session_start timestamp with time zone,
    session_end timestamp with time zone,
    status character varying(20) DEFAULT 'pending'::character varying,
    error_message text,
    created_at timestamp with time zone DEFAULT now()
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.emr_patient_map (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    member_id uuid NOT NULL,
    emr_patient_id character varying(255) NOT NULL,
    emr_system character varying(50) NOT NULL,
    last_synced_at timestamp with time zone,
    sync_direction character varying(10) NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.emr_sync_log (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    direction character varying(10) NOT NULL,
    resource_type character varying(50) NOT NULL,
    operation character varying(20) NOT NULL,
    emr_resource_id character varying(255),
    auraflow_resource_id uuid,
    status character varying(20) NOT NULL,
    error_message text,
    created_at timestamp with time zone DEFAULT now()
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.engagement_campaigns (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    member_id uuid NOT NULL,
    engagement_type character varying(30) NOT NULL,
    status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    priority_score double precision,
    initial_email_sent_at timestamp with time zone,
    last_email_sent_at timestamp with time zone,
    followup_count integer DEFAULT 0,
    reply_count integer DEFAULT 0,
    outcome character varying(30),
    outcome_at timestamp with time zone,
    escalated_to uuid,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT engagement_campaigns_status_check CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'replied'::character varying, 'converted'::character varying, 'completed'::character varying, 'escalated'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.engagement_messages (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    campaign_id uuid NOT NULL,
    direction character varying(10) NOT NULL,
    message_type character varying(20) NOT NULL,
    subject text,
    body_text text,
    body_html text,
    email_sent_at timestamp with time zone,
    email_message_id character varying(255),
    created_at timestamp with time zone DEFAULT now()
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.engagement_settings (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    enabled boolean DEFAULT true,
    max_campaigns_per_day integer DEFAULT 20,
    followup_interval_days integer DEFAULT 3,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.equipment (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    studio_id uuid NOT NULL,
    room_id uuid,
    name character varying(255) NOT NULL,
    category character varying(30) DEFAULT 'props'::character varying NOT NULL,
    description text,
    quantity integer DEFAULT 1,
    purchase_date date,
    purchase_cost_cents integer,
    condition character varying(20) DEFAULT 'good'::character varying,
    warranty_expiry date,
    serial_number character varying(255),
    photo_url text,
    notes text,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT equipment_category_check CHECK (((category)::text = ANY ((ARRAY['props'::character varying, 'mats'::character varying, 'weights'::character varying, 'machines'::character varying, 'audio_visual'::character varying, 'furniture'::character varying, 'cleaning'::character varying, 'other'::character varying])::text[]))),
    CONSTRAINT equipment_condition_check CHECK (((condition)::text = ANY ((ARRAY['new'::character varying, 'good'::character varying, 'fair'::character varying, 'poor'::character varying, 'retired'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.facility_schedule_completions (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    schedule_id uuid NOT NULL,
    completed_by uuid,
    completed_at timestamp with time zone DEFAULT now(),
    notes text,
    photos jsonb DEFAULT '[]'::jsonb
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.facility_schedules (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    studio_id uuid NOT NULL,
    room_id uuid,
    equipment_id uuid,
    schedule_type character varying(20) DEFAULT 'cleaning'::character varying NOT NULL,
    title character varying(255) NOT NULL,
    description text,
    rrule text,
    assigned_to text,
    last_completed_at timestamp with time zone,
    next_due_at timestamp with time zone,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT facility_schedule_type_check CHECK (((schedule_type)::text = ANY ((ARRAY['cleaning'::character varying, 'inspection'::character varying, 'maintenance'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.failed_payment_attempts (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    member_id uuid NOT NULL,
    membership_id uuid,
    stripe_invoice_id character varying(100),
    stripe_payment_intent_id character varying(100),
    amount_cents integer NOT NULL,
    failure_reason text,
    attempt_number integer DEFAULT 1,
    next_retry_at timestamp with time zone,
    resolved boolean DEFAULT false,
    resolved_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now()
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.gdpr_deletion_requests (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    member_id uuid NOT NULL,
    requested_at timestamp with time zone DEFAULT now() NOT NULL,
    scheduled_deletion_at timestamp with time zone NOT NULL,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    completed_at timestamp with time zone,
    cancelled_at timestamp with time zone
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.gift_card_redemptions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    gift_card_id uuid NOT NULL,
    member_id uuid NOT NULL,
    amount_cents integer NOT NULL,
    transaction_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT gift_card_redemptions_amount_cents_check CHECK ((amount_cents > 0))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.gift_cards (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    code character varying(19) NOT NULL,
    amount_cents integer NOT NULL,
    balance_cents integer NOT NULL,
    status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    purchaser_member_id uuid,
    purchased_by_name character varying(255),
    recipient_email character varying(255),
    recipient_name character varying(255),
    message text,
    expires_at timestamp with time zone,
    voided_at timestamp with time zone,
    void_reason text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT gift_cards_amount_cents_check CHECK ((amount_cents > 0)),
    CONSTRAINT gift_cards_balance_cents_check CHECK ((balance_cents >= 0)),
    CONSTRAINT gift_cards_status_check CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'fully_redeemed'::character varying, 'voided'::character varying, 'expired'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.guest_instructors (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    studio_id uuid,
    name character varying(255) NOT NULL,
    bio text,
    photo_url text,
    email character varying(255),
    phone character varying(50),
    address_line1 character varying(255),
    city character varying(100),
    state character varying(50),
    postal_code character varying(20),
    tax_id_encrypted bytea,
    revenue_share_percent_to_guest integer DEFAULT 60 NOT NULL,
    notes text,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    photo_data bytea,
    photo_mime character varying(50),
    CONSTRAINT guest_instructors_revenue_share_percent_to_guest_check CHECK (((revenue_share_percent_to_guest >= 0) AND (revenue_share_percent_to_guest <= 100)))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.instructor_availability (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    instructor_id uuid NOT NULL,
    day_of_week integer,
    start_time time without time zone NOT NULL,
    end_time time without time zone NOT NULL,
    is_recurring boolean DEFAULT true,
    specific_date date,
    is_blocked boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT instructor_availability_day_of_week_check CHECK (((day_of_week >= 0) AND (day_of_week <= 6)))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.instructors (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    user_id uuid NOT NULL,
    display_name character varying(255) NOT NULL,
    bio text,
    photo_url text,
    specialties text[],
    certifications text[],
    zoom_user_id character varying(100),
    email character varying(255),
    phone character varying(20),
    pay_rate_cents integer,
    pay_type character varying(20) DEFAULT 'per_class'::character varying,
    tax_classification character varying(20) DEFAULT '1099'::character varying,
    color character varying(7) DEFAULT '#4F46E5'::character varying,
    sort_order integer DEFAULT 0,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    workshop_pay_percent integer DEFAULT 60,
    private_session_pay_percent integer DEFAULT 70,
    training_pay_percent integer DEFAULT 50,
    salary_cents integer DEFAULT 0,
    phone_hash character varying(64)
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.inventory (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    product_id uuid NOT NULL,
    quantity_on_hand integer DEFAULT 0 NOT NULL,
    reorder_point integer DEFAULT 5 NOT NULL,
    reorder_quantity integer DEFAULT 20 NOT NULL,
    last_counted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT inventory_quantity_on_hand_check CHECK ((quantity_on_hand >= 0))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.inventory_transactions (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    product_id uuid NOT NULL,
    quantity_change integer NOT NULL,
    reason character varying(50) NOT NULL,
    reference_id uuid,
    notes text,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT inventory_transactions_reason_check CHECK (((reason)::text = ANY ((ARRAY['sale'::character varying, 'restock'::character varying, 'adjustment'::character varying, 'shrinkage'::character varying, 'opening_count'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.job_application_documents (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    application_id uuid NOT NULL,
    doc_type character varying(30) DEFAULT 'other'::character varying NOT NULL,
    filename character varying(255) NOT NULL,
    content_type character varying(120) NOT NULL,
    file_data bytea NOT NULL,
    size_bytes integer NOT NULL,
    uploaded_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT job_application_documents_doc_type_check CHECK (((doc_type)::text = ANY ((ARRAY['resume'::character varying, 'certification'::character varying, 'insurance'::character varying, 'yoga_alliance'::character varying, 'other'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.job_application_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    application_id uuid NOT NULL,
    event_type character varying(30) NOT NULL,
    from_status character varying(20),
    to_status character varying(20),
    note text,
    actor_user_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT job_application_events_event_type_check CHECK (((event_type)::text = ANY ((ARRAY['created'::character varying, 'status_changed'::character varying, 'note'::character varying, 'rated'::character varying, 'document_uploaded'::character varying, 'hired'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.job_applications (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    first_name character varying(120) NOT NULL,
    last_name character varying(120) NOT NULL,
    email character varying(255) NOT NULL,
    phone character varying(40),
    address_line1 character varying(255),
    address_line2 character varying(255),
    city character varying(120),
    state character varying(60),
    postal_code character varying(20),
    position_type character varying(30) DEFAULT 'instructor'::character varying NOT NULL,
    position_title character varying(160),
    employment_type character varying(20),
    availability text,
    earliest_start_date date,
    desired_pay_text character varying(160),
    authorized_to_work boolean DEFAULT false NOT NULL,
    over_18 boolean DEFAULT false NOT NULL,
    years_experience integer,
    experience_seniors text,
    experience_injuries text,
    experience_pain text,
    specialties text[] DEFAULT '{}'::text[] NOT NULL,
    work_history jsonb DEFAULT '[]'::jsonb NOT NULL,
    certifications jsonb DEFAULT '[]'::jsonb NOT NULL,
    yoga_alliance_number character varying(60),
    yoga_alliance_level character varying(40),
    cpr_first_aid boolean DEFAULT false NOT NULL,
    liability_insurance boolean DEFAULT false NOT NULL,
    "references" jsonb DEFAULT '[]'::jsonb NOT NULL,
    cover_letter text,
    hear_about_us character varying(160),
    attestation boolean DEFAULT false NOT NULL,
    status character varying(20) DEFAULT 'new'::character varying NOT NULL,
    rating smallint,
    assigned_reviewer_id uuid,
    reviewed_by uuid,
    reviewed_at timestamp with time zone,
    rejection_reason text,
    hired_user_id uuid,
    hired_studio_id uuid,
    hired_role character varying(30),
    hired_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT job_applications_employment_type_check CHECK (((employment_type IS NULL) OR ((employment_type)::text = ANY ((ARRAY['full_time'::character varying, 'part_time'::character varying, 'contract'::character varying])::text[])))),
    CONSTRAINT job_applications_position_type_check CHECK (((position_type)::text = ANY ((ARRAY['instructor'::character varying, 'front_desk'::character varying, 'admin'::character varying, 'other'::character varying])::text[]))),
    CONSTRAINT job_applications_rating_check CHECK (((rating IS NULL) OR ((rating >= 0) AND (rating <= 5)))),
    CONSTRAINT job_applications_status_check CHECK (((status)::text = ANY ((ARRAY['new'::character varying, 'reviewed'::character varying, 'shortlisted'::character varying, 'interviewed'::character varying, 'offer'::character varying, 'hired'::character varying, 'rejected'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.maintenance_requests (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    studio_id uuid NOT NULL,
    room_id uuid,
    equipment_id uuid,
    title character varying(255) NOT NULL,
    description text,
    priority character varying(20) DEFAULT 'medium'::character varying,
    status character varying(20) DEFAULT 'open'::character varying,
    category character varying(30) DEFAULT 'repair'::character varying,
    requested_by uuid,
    assigned_to text,
    estimated_cost_cents integer,
    actual_cost_cents integer,
    scheduled_date date,
    completed_at timestamp with time zone,
    completion_notes text,
    photos jsonb DEFAULT '[]'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT maintenance_category_check CHECK (((category)::text = ANY ((ARRAY['repair'::character varying, 'cleaning'::character varying, 'replacement'::character varying, 'inspection'::character varying, 'safety'::character varying])::text[]))),
    CONSTRAINT maintenance_priority_check CHECK (((priority)::text = ANY ((ARRAY['low'::character varying, 'medium'::character varying, 'high'::character varying, 'urgent'::character varying])::text[]))),
    CONSTRAINT maintenance_status_check CHECK (((status)::text = ANY ((ARRAY['open'::character varying, 'in_progress'::character varying, 'completed'::character varying, 'cancelled'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.marketing_drafts (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    prompt_context text NOT NULL,
    draft_type character varying(50) DEFAULT 'email'::character varying NOT NULL,
    subject text,
    body text NOT NULL,
    status character varying(20) DEFAULT 'draft'::character varying NOT NULL,
    created_by uuid,
    reviewed_by uuid,
    reviewed_at timestamp with time zone,
    campaign_id uuid,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT marketing_drafts_draft_type_check CHECK (((draft_type)::text = ANY ((ARRAY['email'::character varying, 'social'::character varying, 'sms'::character varying, 'class_description'::character varying])::text[]))),
    CONSTRAINT marketing_drafts_status_check CHECK (((status)::text = ANY ((ARRAY['draft'::character varying, 'approved'::character varying, 'rejected'::character varying, 'sent'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.member_credits (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    member_id uuid NOT NULL,
    source character varying(40) NOT NULL,
    source_ref_id uuid,
    service_filter character varying(40),
    amount_cents integer NOT NULL,
    expires_at timestamp with time zone,
    used_at timestamp with time zone,
    used_booking_id uuid,
    used_booking_table character varying(40),
    notes_enc bytea,
    granted_by_user_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT member_credits_amount_cents_check CHECK ((amount_cents >= 0)),
    CONSTRAINT member_credits_service_filter_chk CHECK (((service_filter IS NULL) OR ((service_filter)::text = ANY ((ARRAY['private_session'::character varying, 'class'::character varying, 'workshop'::character varying])::text[])))),
    CONSTRAINT member_credits_source_chk CHECK (((source)::text = ANY ((ARRAY['instructor_cancellation'::character varying, 'courtesy'::character varying, 'refund_to_credit'::character varying, 'gift'::character varying, 'manual_grant'::character varying])::text[]))),
    CONSTRAINT member_credits_used_consistency_chk CHECK ((((used_at IS NULL) AND (used_booking_id IS NULL)) OR ((used_at IS NOT NULL) AND (used_booking_id IS NOT NULL))))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.member_health_data (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    member_id uuid NOT NULL,
    health_data_encrypted bytea,
    injuries_encrypted bytea,
    conditions_encrypted bytea,
    medications_encrypted bytea,
    updated_at timestamp with time zone DEFAULT now()
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.member_memberships (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    member_id uuid NOT NULL,
    membership_type_id uuid NOT NULL,
    status character varying(20) DEFAULT 'active'::character varying,
    starts_at timestamp with time zone NOT NULL,
    ends_at timestamp with time zone,
    classes_remaining integer,
    stripe_subscription_id character varying(100),
    frozen_at timestamp with time zone,
    frozen_until timestamp with time zone,
    cancelled_at timestamp with time zone,
    cancellation_reason text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    current_period_end timestamp with time zone,
    square_subscription_id text,
    billing_provider text DEFAULT 'stripe'::text NOT NULL,
    square_card_id text,
    trial_period_end timestamp with time zone,
    CONSTRAINT member_memberships_billing_provider_chk CHECK ((billing_provider = ANY (ARRAY['stripe'::text, 'square'::text]))),
    CONSTRAINT member_memberships_status_check CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'frozen'::character varying, 'cancelled'::character varying, 'expired'::character varying, 'past_due'::character varying, 'paused'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.member_milestones (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    member_id uuid NOT NULL,
    milestone_type character varying(50) NOT NULL,
    achieved_at timestamp with time zone DEFAULT now(),
    notified_at timestamp with time zone,
    video_url text,
    video_provider text,
    video_id text,
    video_status text
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.member_notes (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    member_id uuid NOT NULL,
    author_id uuid NOT NULL,
    is_pinned boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    note_enc bytea
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.members (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    user_id uuid NOT NULL,
    member_number character varying(20),
    first_name character varying(100) NOT NULL,
    last_name character varying(100) NOT NULL,
    email character varying(255) NOT NULL,
    gender character varying(20),
    tags text[],
    stripe_customer_id character varying(100),
    is_active boolean DEFAULT true,
    joined_at timestamp with time zone DEFAULT now(),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    photo_url text,
    source character varying(50) DEFAULT 'manual'::character varying,
    referral_source character varying(255),
    last_visit_at timestamp with time zone,
    total_visits integer DEFAULT 0,
    lifetime_revenue_cents integer DEFAULT 0,
    email_opt_in boolean DEFAULT true,
    sms_opt_in boolean DEFAULT true,
    email_opt_out_at timestamp with time zone,
    sms_opt_out_at timestamp with time zone,
    churn_risk_flagged_at timestamp with time zone,
    churn_probability double precision,
    churn_risk_level text,
    churn_scored_at timestamp with time zone,
    churn_outreach_sent_at timestamp with time zone,
    stripe_coupon_id character varying(50),
    payment_setup_required boolean DEFAULT false,
    date_of_birth_enc bytea,
    phone_enc bytea,
    address_line1_enc bytea,
    city_enc bytea,
    state_enc bytea,
    postal_code_enc bytea,
    emergency_contact_name_enc bytea,
    emergency_contact_phone_enc bytea,
    notes_enc bytea,
    birthday_month smallint,
    birthday_day smallint,
    phone_hash character(64),
    square_customer_id text,
    square_card_on_file_id text,
    square_card_on_file_brand text,
    square_card_on_file_last4 text,
    square_card_on_file_exp_month integer,
    square_card_on_file_exp_year integer,
    square_card_on_file_saved_at timestamp with time zone,
    facility_name text
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.membership_types (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    studio_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    type character varying(30) NOT NULL,
    class_count integer,
    price_cents integer NOT NULL,
    billing_period character varying(20),
    duration_days integer,
    stripe_price_id character varying(100),
    is_active boolean DEFAULT true,
    is_public boolean DEFAULT true,
    sort_order integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT now(),
    is_founding_rate boolean DEFAULT false,
    max_enrollments integer,
    auto_renew boolean DEFAULT true,
    trial_days integer DEFAULT 0,
    freeze_allowed boolean DEFAULT false,
    max_freeze_days integer DEFAULT 30,
    cancellation_notice_days integer DEFAULT 0,
    class_types_allowed uuid[],
    updated_at timestamp with time zone DEFAULT now(),
    access_scope character varying(30) DEFAULT 'in_studio'::character varying,
    is_template boolean DEFAULT false,
    template_key character varying(50),
    square_plan_id text,
    square_plan_variation_id text,
    trial_starts_on_first_class boolean DEFAULT false NOT NULL,
    new_members_only boolean DEFAULT false NOT NULL,
    is_online boolean DEFAULT false NOT NULL,
    standing_zoom_url text,
    standing_zoom_meeting_id text,
    standing_zoom_password text,
    CONSTRAINT membership_types_access_scope_check CHECK (((access_scope)::text = ANY ((ARRAY['in_studio'::character varying, 'online'::character varying, 'all_access'::character varying])::text[]))),
    CONSTRAINT membership_types_billing_period_check CHECK (((billing_period IS NULL) OR ((billing_period)::text = ANY (ARRAY['monthly'::text, 'yearly'::text, 'quarterly'::text, 'semi_annual'::text, 'one_time'::text, 'none'::text])))),
    CONSTRAINT membership_types_type_check CHECK (((type)::text = ANY ((ARRAY['unlimited'::character varying, 'class_pack'::character varying, 'intro_offer'::character varying, 'day_pass'::character varying, 'single_class'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.notifications (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    user_id uuid NOT NULL,
    type text NOT NULL,
    title text NOT NULL,
    body text,
    action_url text,
    metadata jsonb DEFAULT '{}'::jsonb,
    is_read boolean DEFAULT false,
    read_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.onboarding_checklist (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    step_key text NOT NULL,
    title text NOT NULL,
    description text,
    sort_order integer DEFAULT 0,
    completed_at timestamp with time zone,
    completed_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.onboarding_documents (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    packet_id uuid NOT NULL,
    user_id uuid NOT NULL,
    doc_type character varying(40) NOT NULL,
    kind character varying(20) DEFAULT 'form_fillable'::character varying NOT NULL,
    title character varying(200) NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    form_data jsonb DEFAULT '{}'::jsonb NOT NULL,
    ssn_encrypted bytea,
    status character varying(16) DEFAULT 'pending'::character varying NOT NULL,
    signature_text character varying(255),
    signed_at timestamp with time zone,
    signed_ip character varying(64),
    signed_pdf bytea,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT onboarding_documents_kind_check CHECK (((kind)::text = ANY ((ARRAY['form_fillable'::character varying, 'acknowledgment'::character varying])::text[]))),
    CONSTRAINT onboarding_documents_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'completed'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.onboarding_packets (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    application_id uuid,
    first_name character varying(120),
    last_name character varying(120),
    email character varying(255),
    signing_token character(64),
    signing_token_expires_at timestamp with time zone,
    status character varying(16) DEFAULT 'pending'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT onboarding_packets_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'completed'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.payout_summaries (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    report_date date NOT NULL,
    period character varying(10) NOT NULL,
    gross_revenue_cents integer DEFAULT 0,
    fee_cents integer DEFAULT 0,
    net_revenue_cents integer DEFAULT 0,
    refund_cents integer DEFAULT 0,
    transaction_count integer DEFAULT 0,
    drop_in_count integer DEFAULT 0,
    membership_count integer DEFAULT 0,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now()
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.payroll_employee_mapping (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    instructor_id uuid NOT NULL,
    provider character varying(20) NOT NULL,
    external_employee_id character varying(255) NOT NULL,
    external_employee_name character varying(255),
    mapped_at timestamp with time zone DEFAULT now(),
    CONSTRAINT payroll_mapping_provider_check CHECK (((provider)::text = ANY ((ARRAY['gusto'::character varying, 'quickbooks'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.payroll_line_items (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    payroll_run_id uuid NOT NULL,
    instructor_id uuid,
    hours_worked numeric(8,2) DEFAULT 0,
    overtime_hours numeric(8,2) DEFAULT 0,
    classes_taught integer DEFAULT 0,
    class_pay_cents integer DEFAULT 0,
    hourly_pay_cents integer DEFAULT 0,
    overtime_pay_cents integer DEFAULT 0,
    total_gross_cents integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT now(),
    private_sessions_count integer DEFAULT 0,
    private_session_revenue_cents integer DEFAULT 0,
    private_session_pay_cents integer DEFAULT 0,
    workshops_count integer DEFAULT 0,
    workshop_revenue_cents integer DEFAULT 0,
    workshop_pay_cents integer DEFAULT 0,
    training_pay_cents integer DEFAULT 0,
    paid_at timestamp with time zone,
    paid_by uuid,
    guest_instructor_id uuid,
    CONSTRAINT payroll_line_items_one_owner_chk CHECK ((((instructor_id IS NOT NULL) AND (guest_instructor_id IS NULL)) OR ((instructor_id IS NULL) AND (guest_instructor_id IS NOT NULL))))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.payroll_runs (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    period_start date NOT NULL,
    period_end date NOT NULL,
    status character varying(20) DEFAULT 'draft'::character varying,
    total_gross_cents integer DEFAULT 0,
    total_hours numeric(8,2) DEFAULT 0,
    created_by uuid,
    finalized_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    exported_at timestamp with time zone,
    export_method character varying(20),
    CONSTRAINT payroll_runs_status_check CHECK (((status)::text = ANY ((ARRAY['draft'::character varying, 'finalized'::character varying, 'exported'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.pos_line_items (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    transaction_id uuid NOT NULL,
    product_id uuid NOT NULL,
    quantity integer DEFAULT 1 NOT NULL,
    unit_price_cents integer NOT NULL,
    tax_cents integer DEFAULT 0 NOT NULL,
    total_cents integer NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT pos_line_items_quantity_check CHECK ((quantity > 0)),
    CONSTRAINT pos_line_items_unit_price_cents_check CHECK ((unit_price_cents >= 0))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.pos_terminal_checkouts (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    member_id uuid NOT NULL,
    amount_cents integer NOT NULL,
    app_fee_cents integer DEFAULT 0 NOT NULL,
    description text,
    device_id text,
    flow text NOT NULL,
    square_checkout_id text,
    square_payment_id text,
    square_card_id text,
    square_customer_id text,
    membership_type_id uuid,
    status text DEFAULT 'pending'::text NOT NULL,
    failure_reason text,
    reference_id text,
    initiated_by_user_id uuid,
    initiated_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    expires_at timestamp with time zone DEFAULT (now() + '00:10:00'::interval) NOT NULL,
    course_id uuid,
    CONSTRAINT pos_terminal_checkouts_amount_cents_check CHECK ((amount_cents > 0)),
    CONSTRAINT pos_terminal_checkouts_flow_check CHECK ((flow = ANY (ARRAY['terminal'::text, 'deeplink'::text]))),
    CONSTRAINT pos_terminal_checkouts_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'in_progress'::text, 'completed'::text, 'cancelled'::text, 'failed'::text, 'expired'::text])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.pos_transactions (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    member_id uuid,
    subtotal_cents integer DEFAULT 0 NOT NULL,
    tax_cents integer DEFAULT 0 NOT NULL,
    total_cents integer DEFAULT 0 NOT NULL,
    payment_method character varying(20) DEFAULT 'cash'::character varying NOT NULL,
    stripe_payment_id character varying(255),
    status character varying(20) DEFAULT 'completed'::character varying NOT NULL,
    notes text,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    square_payment_id text,
    CONSTRAINT pos_transactions_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'completed'::character varying, 'refunded'::character varying, 'voided'::character varying])::text[]))),
    CONSTRAINT pos_transactions_total_cents_check CHECK ((total_cents >= 0)),
    CONSTRAINT pos_txn_payment_method_check CHECK (((payment_method)::text = ANY ((ARRAY['cash'::character varying, 'card'::character varying, 'comp'::character varying, 'stripe'::character varying, 'send_payment_link'::character varying, 'paypal'::character varying, 'apple_pay'::character varying, 'google_pay'::character varying, 'venmo'::character varying, 'check'::character varying, 'bank_transfer'::character varying, 'gift_card'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.price_adjustments_log (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    class_session_id uuid NOT NULL,
    original_price_cents integer NOT NULL,
    adjusted_price_cents integer NOT NULL,
    reason text,
    rules_applied jsonb DEFAULT '[]'::jsonb,
    ai_explanation text,
    applied_by character varying(50) DEFAULT 'ai'::character varying,
    status character varying(20) DEFAULT 'suggested'::character varying,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT price_adjustments_log_applied_by_check CHECK (((applied_by)::text = ANY ((ARRAY['ai'::character varying, 'manual'::character varying])::text[]))),
    CONSTRAINT price_adjustments_log_status_check CHECK (((status)::text = ANY ((ARRAY['suggested'::character varying, 'approved'::character varying, 'rejected'::character varying, 'applied'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.pricing_rules (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    studio_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    rule_type character varying(50) NOT NULL,
    config jsonb DEFAULT '{}'::jsonb NOT NULL,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT pricing_rules_rule_type_check CHECK (((rule_type)::text = ANY ((ARRAY['peak_hour'::character varying, 'fill_rate'::character varying, 'day_of_week'::character varying, 'seasonal'::character varying, 'last_minute'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.private_bookings (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    member_id uuid NOT NULL,
    instructor_id uuid NOT NULL,
    private_service_id uuid NOT NULL,
    starts_at timestamp with time zone NOT NULL,
    ends_at timestamp with time zone NOT NULL,
    status character varying(20) DEFAULT 'pending'::character varying,
    is_virtual boolean DEFAULT false,
    zoom_meeting_id character varying(100),
    zoom_join_url text,
    intake_notes text,
    instructor_notes text,
    transaction_id uuid,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    cancelled_at timestamp with time zone,
    cancellation_reason text,
    reminder_sent boolean DEFAULT false,
    price_cents integer,
    payment_url text,
    zoom_password text,
    payment_status text DEFAULT 'unpaid'::text,
    cancelled_by_role character varying(20),
    CONSTRAINT private_bookings_cancelled_by_role_check CHECK (((cancelled_by_role IS NULL) OR ((cancelled_by_role)::text = ANY ((ARRAY['instructor'::character varying, 'member'::character varying, 'staff'::character varying])::text[])))),
    CONSTRAINT private_bookings_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'confirmed'::character varying, 'cancelled'::character varying, 'completed'::character varying, 'no_show'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.private_services (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    instructor_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    duration_minutes integer DEFAULT 60 NOT NULL,
    price_cents integer NOT NULL,
    buffer_before_minutes integer DEFAULT 0,
    buffer_after_minutes integer DEFAULT 15,
    max_per_day integer,
    visibility character varying(30) DEFAULT 'members_only'::character varying,
    required_membership_type_id uuid,
    is_virtual boolean DEFAULT false,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now(),
    package_sessions integer,
    package_price_cents integer,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT private_services_visibility_check CHECK (((visibility)::text = ANY ((ARRAY['public'::character varying, 'members_only'::character varying, 'tier_specific'::character varying, 'invite_only'::character varying, 'staff_only'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.products (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    studio_id uuid,
    name character varying(255) NOT NULL,
    description text,
    sku character varying(100),
    price_cents integer DEFAULT 0 NOT NULL,
    cost_cents integer DEFAULT 0 NOT NULL,
    category character varying(50) DEFAULT 'retail'::character varying NOT NULL,
    tax_rate numeric(5,4) DEFAULT 0.0000 NOT NULL,
    image_url text,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT products_category_check CHECK (((category)::text = ANY ((ARRAY['retail'::character varying, 'beverages'::character varying, 'rental'::character varying, 'merchandise'::character varying])::text[]))),
    CONSTRAINT products_cost_nonneg CHECK ((cost_cents >= 0)),
    CONSTRAINT products_price_nonneg CHECK ((price_cents >= 0)),
    CONSTRAINT products_tax_rate_check CHECK (((tax_rate >= (0)::numeric) AND (tax_rate <= (1)::numeric)))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.resolution_requests (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    member_id uuid,
    category character varying(50) NOT NULL,
    status character varying(20) DEFAULT 'open'::character varying,
    member_message text NOT NULL,
    ai_summary text,
    ai_decision text,
    ai_action_taken text,
    ai_confidence numeric(3,2),
    requires_approval boolean DEFAULT true,
    approved_by uuid,
    approved_at timestamp with time zone,
    resolved_at timestamp with time zone,
    escalated_to uuid,
    escalation_reason text,
    audit_trail jsonb DEFAULT '[]'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    response_text text,
    intent character varying(50),
    sender_type character varying(20),
    sender_id uuid,
    sender_phone character varying(20),
    actions_taken jsonb DEFAULT '[]'::jsonb,
    CONSTRAINT resolution_requests_category_check CHECK (((category)::text = ANY ((ARRAY['billing'::character varying, 'scheduling'::character varying, 'membership'::character varying, 'technical'::character varying, 'general'::character varying])::text[]))),
    CONSTRAINT resolution_requests_status_check CHECK (((status)::text = ANY ((ARRAY['open'::character varying, 'ai_processing'::character varying, 'awaiting_approval'::character varying, 'resolved'::character varying, 'escalated'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.reviews (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    member_id uuid NOT NULL,
    class_session_id uuid NOT NULL,
    rating integer NOT NULL,
    review_text text,
    sentiment character varying(20),
    sentiment_score numeric(4,3),
    ai_analysis text,
    response_text text,
    response_draft text,
    responded_by uuid,
    responded_at timestamp with time zone,
    is_published boolean DEFAULT true,
    is_flagged boolean DEFAULT false,
    flag_reason text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    source text DEFAULT 'internal'::text,
    gmb_review_id text,
    gmb_metadata jsonb,
    CONSTRAINT reviews_rating_check CHECK (((rating >= 1) AND (rating <= 5))),
    CONSTRAINT reviews_sentiment_check CHECK (((sentiment)::text = ANY ((ARRAY['positive'::character varying, 'neutral'::character varying, 'negative'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.rooms (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    studio_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    capacity integer,
    color character varying(7) DEFAULT '#6366F1'::character varying,
    sort_order integer DEFAULT 0,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now(),
    description text,
    room_type character varying(30) DEFAULT 'studio'::character varying,
    amenities jsonb DEFAULT '[]'::jsonb,
    photo_url text,
    hourly_rate_cents integer,
    max_classes_per_day integer,
    floor_area_sqft integer,
    setup_instructions text,
    is_bookable boolean DEFAULT true,
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT rooms_type_check CHECK (((room_type)::text = ANY ((ARRAY['studio'::character varying, 'meeting'::character varying, 'outdoor'::character varying, 'virtual'::character varying, 'therapy'::character varying, 'storage'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.sms_campaign_sends (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    campaign_id uuid NOT NULL,
    member_id uuid NOT NULL,
    to_phone character varying(20) NOT NULL,
    status character varying(20) DEFAULT 'queued'::character varying,
    twilio_sid character varying(100),
    error_message text,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT sms_campaign_sends_status_check CHECK (((status)::text = ANY ((ARRAY['queued'::character varying, 'sent'::character varying, 'delivered'::character varying, 'failed'::character varying, 'opted_out'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.sms_campaigns (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    name character varying(255) NOT NULL,
    body text NOT NULL,
    template_id uuid,
    status character varying(20) DEFAULT 'draft'::character varying,
    audience_filter jsonb DEFAULT '{}'::jsonb,
    scheduled_at timestamp with time zone,
    sent_at timestamp with time zone,
    recipients integer DEFAULT 0,
    delivered integer DEFAULT 0,
    failed integer DEFAULT 0,
    opt_outs integer DEFAULT 0,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT sms_campaigns_status_check CHECK (((status)::text = ANY ((ARRAY['draft'::character varying, 'scheduled'::character varying, 'sending'::character varying, 'sent'::character varying, 'cancelled'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.sms_messages (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    member_id uuid,
    to_phone character varying(20) NOT NULL,
    body text NOT NULL,
    type character varying(20) DEFAULT 'transactional'::character varying,
    status character varying(20) DEFAULT 'queued'::character varying,
    twilio_sid character varying(100),
    error_message text,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT sms_messages_status_check CHECK (((status)::text = ANY ((ARRAY['queued'::character varying, 'sent'::character varying, 'delivered'::character varying, 'failed'::character varying])::text[]))),
    CONSTRAINT sms_messages_type_check CHECK (((type)::text = ANY ((ARRAY['transactional'::character varying, 'marketing'::character varying, 'reminder'::character varying, 'ai_response'::character varying, 'booking_confirmation'::character varying, 'booking_cancellation'::character varying, 'waitlist_promotion'::character varying, 'payment_failed'::character varying, 'campaign'::character varying, 'winback'::character varying, 'milestone'::character varying, 'opt_out'::character varying, 'opt_in'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.sms_templates (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    name character varying(255) NOT NULL,
    slug character varying(100) NOT NULL,
    body text NOT NULL,
    description text,
    variables text[] DEFAULT ARRAY[]::text[],
    category character varying(50) DEFAULT 'general'::character varying,
    is_active boolean DEFAULT true,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT sms_templates_category_check CHECK (((category)::text = ANY ((ARRAY['general'::character varying, 'booking'::character varying, 'reminder'::character varying, 'cancellation'::character varying, 'waitlist'::character varying, 'payment'::character varying, 'winback'::character varying, 'milestone'::character varying, 'marketing'::character varying, 'welcome'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.stripe_payouts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    stripe_payout_id character varying(100) NOT NULL,
    amount_cents integer NOT NULL,
    currency character varying(3) DEFAULT 'USD'::character varying,
    status character varying(20),
    arrival_date timestamp with time zone,
    description text,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.studio_email_accounts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    email_address character varying(255) NOT NULL,
    display_name character varying(255),
    imap_host character varying(255) NOT NULL,
    imap_port integer DEFAULT 993,
    imap_use_tls boolean DEFAULT true,
    smtp_host character varying(255) NOT NULL,
    smtp_port integer DEFAULT 465,
    smtp_use_tls boolean DEFAULT true,
    username character varying(255) NOT NULL,
    password_enc bytea NOT NULL,
    is_active boolean DEFAULT true,
    last_checked_at timestamp with time zone,
    last_uid integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT now()
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.studio_inbox_messages (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    account_id uuid NOT NULL,
    message_uid integer,
    message_id_header character varying(500),
    in_reply_to character varying(500),
    from_email character varying(255) NOT NULL,
    from_name character varying(255),
    to_email character varying(255),
    subject text,
    body_text text,
    body_html text,
    received_at timestamp with time zone,
    classification character varying(30),
    status character varying(20) DEFAULT 'new'::character varying,
    ai_response_text text,
    ai_response_html text,
    ai_response_sent_at timestamp with time zone,
    ai_confidence_score double precision,
    assigned_to uuid,
    resolved_by uuid,
    resolved_at timestamp with time zone,
    member_id uuid,
    engagement_campaign_id uuid,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT studio_inbox_messages_status_check CHECK (((status)::text = ANY ((ARRAY['new'::character varying, 'ai_resolved'::character varying, 'needs_attention'::character varying, 'in_progress'::character varying, 'resolved'::character varying, 'spam'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.studio_inbox_replies (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    message_id uuid NOT NULL,
    reply_by uuid,
    reply_type character varying(10) NOT NULL,
    body_text text,
    body_html text,
    sent_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT studio_inbox_replies_reply_type_check CHECK (((reply_type)::text = ANY ((ARRAY['ai'::character varying, 'manual'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.studio_social_accounts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    platform character varying(20) NOT NULL,
    page_id character varying(100),
    page_name character varying(255),
    access_token_enc bytea NOT NULL,
    instagram_business_id character varying(100),
    is_active boolean DEFAULT true,
    connected_at timestamp with time zone DEFAULT now()
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.studio_social_messages (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    account_id uuid NOT NULL,
    platform character varying(20) NOT NULL,
    conversation_id character varying(255),
    sender_id character varying(255),
    sender_name character varying(255),
    message_text text,
    message_type character varying(20),
    post_id uuid,
    ai_status character varying(20) DEFAULT 'pending'::character varying,
    ai_response text,
    responded_at timestamp with time zone,
    received_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now()
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.studio_social_posts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    account_id uuid NOT NULL,
    platform character varying(20) NOT NULL,
    content text NOT NULL,
    media_urls jsonb,
    post_type character varying(20) DEFAULT 'post'::character varying,
    status character varying(20) DEFAULT 'draft'::character varying,
    platform_post_id character varying(255),
    scheduled_at timestamp with time zone,
    published_at timestamp with time zone,
    engagement jsonb DEFAULT '{}'::jsonb,
    ai_generated boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT studio_social_posts_status_check CHECK (((status)::text = ANY ((ARRAY['draft'::character varying, 'scheduled'::character varying, 'published'::character varying, 'failed'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.studio_user_roles (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    studio_id uuid NOT NULL,
    user_id uuid NOT NULL,
    role character varying(50) NOT NULL,
    is_primary boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT studio_user_roles_role_check CHECK (((role)::text = ANY ((ARRAY['admin'::character varying, 'instructor'::character varying, 'front_desk'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.studios (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    organization_id uuid DEFAULT '4bb3c9ba-b996-464b-9f13-c4cb5c407374'::uuid NOT NULL,
    name character varying(255) NOT NULL,
    slug character varying(100) NOT NULL,
    address_line1 character varying(255),
    address_line2 character varying(255),
    city character varying(100),
    state character varying(50),
    postal_code character varying(20),
    country character varying(2) DEFAULT 'US'::character varying,
    phone character varying(20),
    email character varying(255),
    timezone character varying(50) DEFAULT 'America/Los_Angeles'::character varying,
    is_virtual boolean DEFAULT false,
    is_active boolean DEFAULT true,
    settings jsonb DEFAULT '{}'::jsonb,
    cancellation_policy_hours integer DEFAULT 12,
    late_cancel_fee_cents integer DEFAULT 0,
    booking_window_days integer DEFAULT 14,
    allow_guest_booking boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    waitlist_mode character varying(20) DEFAULT 'fifo'::character varying,
    CONSTRAINT chk_waitlist_mode CHECK (((waitlist_mode)::text = ANY ((ARRAY['fifo'::character varying, 'ai_priority'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.sub_finder_requests (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    class_session_id uuid NOT NULL,
    original_instructor_id uuid NOT NULL,
    reason text,
    status character varying(20) DEFAULT 'searching'::character varying,
    substitute_instructor_id uuid,
    contacted_instructors jsonb DEFAULT '[]'::jsonb,
    ai_summary text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT sub_finder_requests_status_check CHECK (((status)::text = ANY ((ARRAY['searching'::character varying, 'offered'::character varying, 'filled'::character varying, 'unfilled'::character varying, 'cancelled'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.sub_requests (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    class_session_id uuid NOT NULL,
    original_instructor_id uuid NOT NULL,
    reason text,
    status character varying(20) DEFAULT 'searching'::character varying,
    sub_instructor_id uuid,
    current_attempt_instructor_id uuid,
    attempt_count integer DEFAULT 0,
    attempted_instructor_ids uuid[] DEFAULT '{}'::uuid[],
    resolved_at timestamp with time zone,
    escalated_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT sub_requests_status_check CHECK (((status)::text = ANY ((ARRAY['searching'::character varying, 'sub_found'::character varying, 'escalated'::character varying, 'cancelled'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.time_entries (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    instructor_id uuid NOT NULL,
    clock_in timestamp with time zone NOT NULL,
    clock_out timestamp with time zone,
    break_minutes integer DEFAULT 0,
    shift_type character varying(20) DEFAULT 'regular'::character varying,
    notes text,
    status character varying(20) DEFAULT 'pending'::character varying,
    approved_by uuid,
    approved_at timestamp with time zone,
    total_minutes integer,
    overtime_minutes integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT time_entries_shift_type_check CHECK (((shift_type)::text = ANY ((ARRAY['regular'::character varying, 'training'::character varying, 'admin'::character varying, 'event'::character varying])::text[]))),
    CONSTRAINT time_entries_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'approved'::character varying, 'rejected'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.transactions (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    member_id uuid,
    type character varying(50) NOT NULL,
    amount_cents integer NOT NULL,
    currency character varying(3) DEFAULT 'USD'::character varying,
    status character varying(20) DEFAULT 'pending'::character varying,
    stripe_payment_intent_id character varying(100),
    stripe_charge_id character varying(100),
    description text,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    membership_id uuid,
    booking_id uuid,
    stripe_invoice_id character varying(100),
    refund_amount_cents integer,
    refund_reason text,
    refunded_at timestamp with time zone,
    fee_cents integer DEFAULT 0,
    net_amount_cents integer,
    updated_at timestamp with time zone DEFAULT now(),
    square_payment_id text,
    square_refund_id text,
    CONSTRAINT transactions_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'completed'::character varying, 'failed'::character varying, 'refunded'::character varying, 'partially_refunded'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.video_categories (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    slug character varying(100) NOT NULL,
    sort_order integer DEFAULT 0,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.video_membership_access (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    video_id uuid NOT NULL,
    membership_type_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now()
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.video_views (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    video_id uuid NOT NULL,
    member_id uuid NOT NULL,
    watched_seconds integer DEFAULT 0,
    completed boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now()
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.videos (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    source character varying(20) NOT NULL,
    external_id character varying(255),
    title character varying(500) NOT NULL,
    description text,
    thumbnail_url text,
    duration_seconds integer,
    youtube_video_id character varying(50),
    youtube_playlist_id character varying(100),
    mux_asset_id character varying(100),
    mux_playback_id character varying(100),
    mux_asset_status character varying(30),
    category_id uuid,
    instructor_id uuid,
    tags text[],
    visibility character varying(30) DEFAULT 'all_members'::character varying,
    is_published boolean DEFAULT false,
    published_at timestamp with time zone,
    sort_order integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT videos_source_check CHECK (((source)::text = ANY ((ARRAY['youtube'::character varying, 'mux'::character varying, 'manual'::character varying, 'zoom_recording'::character varying])::text[]))),
    CONSTRAINT videos_visibility_check CHECK (((visibility)::text = ANY ((ARRAY['all_members'::character varying, 'specific_memberships'::character varying, 'staff_only'::character varying, 'hidden'::character varying])::text[])))
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.voice_calls (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    member_id uuid,
    call_type text NOT NULL,
    twilio_sid text,
    to_phone text NOT NULL,
    status text DEFAULT 'initiated'::text NOT NULL,
    reference_id text,
    reference_type text,
    error_message text,
    digits_pressed text,
    completed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.waiver_signatures (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    waiver_template_id uuid NOT NULL,
    member_id uuid NOT NULL,
    signed_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone,
    ip_address character varying(45),
    user_agent text,
    signature_text character varying(255) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.waiver_templates (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    title character varying(255) NOT NULL,
    content text NOT NULL,
    require_resign boolean DEFAULT false NOT NULL,
    expiration_days integer,
    is_active boolean DEFAULT true NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.webhook_configs (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    url text NOT NULL,
    secret text,
    events text[] DEFAULT '{}'::text[] NOT NULL,
    is_active boolean DEFAULT true,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.webhook_deliveries (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    webhook_config_id uuid NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    response_status integer,
    response_body text,
    attempt_count integer DEFAULT 0,
    max_attempts integer DEFAULT 5,
    next_retry_at timestamp with time zone,
    last_attempt_at timestamp with time zone,
    delivered_at timestamp with time zone,
    error_message text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
)$prov$, p_schema);
    EXECUTE format($prov$CREATE TABLE IF NOT EXISTS %I.workshop_contracts (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    course_id uuid NOT NULL,
    guest_instructor_id uuid NOT NULL,
    template_version character varying(50) NOT NULL,
    status character varying(20) DEFAULT 'prepared'::character varying NOT NULL,
    signing_token character(64),
    signing_token_expires_at timestamp with time zone NOT NULL,
    effective_date date NOT NULL,
    prefilled_data jsonb NOT NULL,
    instructor_data jsonb,
    signature_image bytea,
    signed_at timestamp with time zone,
    signed_ip text,
    signed_user_agent text,
    signed_pdf bytea,
    email_sent_at timestamp with time zone,
    first_viewed_at timestamp with time zone,
    last_viewed_at timestamp with time zone,
    view_count integer DEFAULT 0 NOT NULL,
    reminder_sent_at timestamp with time zone,
    voided_at timestamp with time zone,
    voided_by uuid,
    void_reason text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    instructor_photo_data bytea,
    instructor_photo_mime character varying(50),
    workshop_flyer_data bytea,
    workshop_flyer_mime character varying(50),
    signed_combined_pdf bytea,
    CONSTRAINT workshop_contracts_status_chk CHECK (((status)::text = ANY ((ARRAY['prepared'::character varying, 'sent'::character varying, 'viewed'::character varying, 'signed'::character varying, 'voided'::character varying])::text[])))
)$prov$, p_schema);
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.acct_categories
    ADD CONSTRAINT acct_categories_pkey PRIMARY KEY (code)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.acct_members
    ADD CONSTRAINT acct_members_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.acct_owner_draws
    ADD CONSTRAINT acct_owner_draws_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.acct_payout_items
    ADD CONSTRAINT acct_payout_items_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.acct_payouts
    ADD CONSTRAINT acct_payouts_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.acct_settings
    ADD CONSTRAINT acct_settings_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.acct_transactions
    ADD CONSTRAINT acct_transactions_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.acct_vendor_rules
    ADD CONSTRAINT acct_vendor_rules_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.activity_log
    ADD CONSTRAINT activity_log_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.api_keys
    ADD CONSTRAINT api_keys_key_hash_key UNIQUE (key_hash)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.api_keys
    ADD CONSTRAINT api_keys_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.bookings
    ADD CONSTRAINT bookings_member_id_class_session_id_key UNIQUE (member_id, class_session_id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.bookings
    ADD CONSTRAINT bookings_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.chatbot_conversations
    ADD CONSTRAINT chatbot_conversations_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.chatbot_messages
    ADD CONSTRAINT chatbot_messages_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.class_series
    ADD CONSTRAINT class_series_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.class_sessions
    ADD CONSTRAINT class_sessions_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.class_types
    ADD CONSTRAINT class_types_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.classpass_config
    ADD CONSTRAINT classpass_config_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.classpass_config
    ADD CONSTRAINT classpass_config_studio_id_key UNIQUE (studio_id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.classpass_reservations
    ADD CONSTRAINT classpass_reservations_classpass_reservation_id_key UNIQUE (classpass_reservation_id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.classpass_reservations
    ADD CONSTRAINT classpass_reservations_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.communication_log
    ADD CONSTRAINT communication_log_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.course_enrollments
    ADD CONSTRAINT course_enrollments_course_id_member_id_key UNIQUE (course_id, member_id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.course_enrollments
    ADD CONSTRAINT course_enrollments_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.course_session_attendance
    ADD CONSTRAINT course_session_attendance_course_session_id_member_id_key UNIQUE (course_session_id, member_id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.course_session_attendance
    ADD CONSTRAINT course_session_attendance_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.course_sessions
    ADD CONSTRAINT course_sessions_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.courses
    ADD CONSTRAINT courses_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.de34_filings
    ADD CONSTRAINT de34_filings_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.de34_filings
    ADD CONSTRAINT de34_filings_user_id_key UNIQUE (user_id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.email_campaign_sends
    ADD CONSTRAINT email_campaign_sends_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.email_campaigns
    ADD CONSTRAINT email_campaigns_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.employee_w4_forms
    ADD CONSTRAINT employee_w4_forms_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.employer_profile
    ADD CONSTRAINT employer_profile_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.emr_encounter_log
    ADD CONSTRAINT emr_encounter_log_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.emr_patient_map
    ADD CONSTRAINT emr_patient_map_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.emr_sync_log
    ADD CONSTRAINT emr_sync_log_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.engagement_campaigns
    ADD CONSTRAINT engagement_campaigns_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.engagement_messages
    ADD CONSTRAINT engagement_messages_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.engagement_settings
    ADD CONSTRAINT engagement_settings_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.equipment
    ADD CONSTRAINT equipment_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.facility_schedule_completions
    ADD CONSTRAINT facility_schedule_completions_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.facility_schedules
    ADD CONSTRAINT facility_schedules_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.failed_payment_attempts
    ADD CONSTRAINT failed_payment_attempts_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.gdpr_deletion_requests
    ADD CONSTRAINT gdpr_deletion_requests_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.gift_card_redemptions
    ADD CONSTRAINT gift_card_redemptions_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.gift_cards
    ADD CONSTRAINT gift_cards_code_key UNIQUE (code)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.gift_cards
    ADD CONSTRAINT gift_cards_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.guest_instructors
    ADD CONSTRAINT guest_instructors_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.instructor_availability
    ADD CONSTRAINT instructor_availability_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.instructors
    ADD CONSTRAINT instructors_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.inventory
    ADD CONSTRAINT inventory_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.inventory
    ADD CONSTRAINT inventory_product_id_key UNIQUE (product_id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.inventory_transactions
    ADD CONSTRAINT inventory_transactions_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.job_application_documents
    ADD CONSTRAINT job_application_documents_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.job_application_events
    ADD CONSTRAINT job_application_events_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.job_applications
    ADD CONSTRAINT job_applications_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.maintenance_requests
    ADD CONSTRAINT maintenance_requests_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.marketing_drafts
    ADD CONSTRAINT marketing_drafts_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.member_credits
    ADD CONSTRAINT member_credits_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.member_health_data
    ADD CONSTRAINT member_health_data_member_id_key UNIQUE (member_id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.member_health_data
    ADD CONSTRAINT member_health_data_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.member_memberships
    ADD CONSTRAINT member_memberships_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.member_milestones
    ADD CONSTRAINT member_milestones_member_id_milestone_type_key UNIQUE (member_id, milestone_type)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.member_milestones
    ADD CONSTRAINT member_milestones_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.member_notes
    ADD CONSTRAINT member_notes_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.members
    ADD CONSTRAINT members_member_number_key UNIQUE (member_number)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.members
    ADD CONSTRAINT members_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.membership_types
    ADD CONSTRAINT membership_types_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.onboarding_checklist
    ADD CONSTRAINT onboarding_checklist_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.onboarding_checklist
    ADD CONSTRAINT onboarding_checklist_step_key_key UNIQUE (step_key)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.onboarding_documents
    ADD CONSTRAINT onboarding_documents_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.onboarding_packets
    ADD CONSTRAINT onboarding_packets_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.payout_summaries
    ADD CONSTRAINT payout_summaries_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.payout_summaries
    ADD CONSTRAINT payout_summaries_report_date_period_key UNIQUE (report_date, period)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.payroll_employee_mapping
    ADD CONSTRAINT payroll_employee_mapping_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.payroll_line_items
    ADD CONSTRAINT payroll_line_items_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.payroll_line_items
    ADD CONSTRAINT payroll_line_items_unique UNIQUE (payroll_run_id, instructor_id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.payroll_employee_mapping
    ADD CONSTRAINT payroll_mapping_unique UNIQUE (instructor_id, provider)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.payroll_runs
    ADD CONSTRAINT payroll_runs_period_unique UNIQUE (period_start, period_end)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.payroll_runs
    ADD CONSTRAINT payroll_runs_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.pos_line_items
    ADD CONSTRAINT pos_line_items_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.pos_terminal_checkouts
    ADD CONSTRAINT pos_terminal_checkouts_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.pos_transactions
    ADD CONSTRAINT pos_transactions_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.price_adjustments_log
    ADD CONSTRAINT price_adjustments_log_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.pricing_rules
    ADD CONSTRAINT pricing_rules_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.private_bookings
    ADD CONSTRAINT private_bookings_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.private_services
    ADD CONSTRAINT private_services_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.products
    ADD CONSTRAINT products_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.resolution_requests
    ADD CONSTRAINT resolution_requests_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.reviews
    ADD CONSTRAINT review_unique UNIQUE (member_id, class_session_id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.reviews
    ADD CONSTRAINT reviews_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.rooms
    ADD CONSTRAINT rooms_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.sms_campaign_sends
    ADD CONSTRAINT sms_campaign_sends_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.sms_campaigns
    ADD CONSTRAINT sms_campaigns_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.sms_messages
    ADD CONSTRAINT sms_messages_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.sms_templates
    ADD CONSTRAINT sms_templates_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.sms_templates
    ADD CONSTRAINT sms_templates_slug_key UNIQUE (slug)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.stripe_payouts
    ADD CONSTRAINT stripe_payouts_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.stripe_payouts
    ADD CONSTRAINT stripe_payouts_stripe_payout_id_key UNIQUE (stripe_payout_id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.studio_email_accounts
    ADD CONSTRAINT studio_email_accounts_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.studio_inbox_messages
    ADD CONSTRAINT studio_inbox_messages_account_uid_unique UNIQUE (account_id, message_uid)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.studio_inbox_messages
    ADD CONSTRAINT studio_inbox_messages_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.studio_inbox_replies
    ADD CONSTRAINT studio_inbox_replies_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.studio_social_accounts
    ADD CONSTRAINT studio_social_accounts_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.studio_social_messages
    ADD CONSTRAINT studio_social_messages_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.studio_social_posts
    ADD CONSTRAINT studio_social_posts_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.studio_user_roles
    ADD CONSTRAINT studio_user_roles_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.studio_user_roles
    ADD CONSTRAINT studio_user_roles_studio_id_user_id_key UNIQUE (studio_id, user_id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.studios
    ADD CONSTRAINT studios_organization_id_slug_key UNIQUE (organization_id, slug)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.studios
    ADD CONSTRAINT studios_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.sub_finder_requests
    ADD CONSTRAINT sub_finder_requests_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.sub_requests
    ADD CONSTRAINT sub_requests_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.time_entries
    ADD CONSTRAINT time_entries_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.transactions
    ADD CONSTRAINT transactions_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.video_categories
    ADD CONSTRAINT video_categories_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.video_categories
    ADD CONSTRAINT video_categories_slug_key UNIQUE (slug)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.video_membership_access
    ADD CONSTRAINT video_membership_access_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.video_membership_access
    ADD CONSTRAINT video_membership_access_video_id_membership_type_id_key UNIQUE (video_id, membership_type_id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.video_views
    ADD CONSTRAINT video_views_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.videos
    ADD CONSTRAINT videos_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.voice_calls
    ADD CONSTRAINT voice_calls_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.waiver_signatures
    ADD CONSTRAINT waiver_signatures_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.waiver_templates
    ADD CONSTRAINT waiver_templates_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.webhook_configs
    ADD CONSTRAINT webhook_configs_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.webhook_deliveries
    ADD CONSTRAINT webhook_deliveries_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.workshop_contracts
    ADD CONSTRAINT workshop_contracts_pkey PRIMARY KEY (id)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.workshop_contracts
    ADD CONSTRAINT workshop_contracts_signing_token_key UNIQUE (signing_token)$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.acct_payout_items
    ADD CONSTRAINT acct_payout_items_payout_id_fkey FOREIGN KEY (payout_id) REFERENCES %I.acct_payouts(id) ON DELETE CASCADE$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.chatbot_messages
    ADD CONSTRAINT chatbot_messages_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES %I.chatbot_conversations(id) ON DELETE CASCADE$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.courses
    ADD CONSTRAINT courses_guest_instructor_id_fkey FOREIGN KEY (guest_instructor_id) REFERENCES %I.guest_instructors(id) ON DELETE SET NULL$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.employee_w4_forms
    ADD CONSTRAINT employee_w4_forms_application_id_fkey FOREIGN KEY (application_id) REFERENCES %I.job_applications(id) ON DELETE SET NULL$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.equipment
    ADD CONSTRAINT equipment_room_id_fkey FOREIGN KEY (room_id) REFERENCES %I.rooms(id)$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.equipment
    ADD CONSTRAINT equipment_studio_id_fkey FOREIGN KEY (studio_id) REFERENCES %I.studios(id)$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.facility_schedule_completions
    ADD CONSTRAINT facility_schedule_completions_schedule_id_fkey FOREIGN KEY (schedule_id) REFERENCES %I.facility_schedules(id) ON DELETE CASCADE$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.facility_schedules
    ADD CONSTRAINT facility_schedules_equipment_id_fkey FOREIGN KEY (equipment_id) REFERENCES %I.equipment(id)$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.facility_schedules
    ADD CONSTRAINT facility_schedules_room_id_fkey FOREIGN KEY (room_id) REFERENCES %I.rooms(id)$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.facility_schedules
    ADD CONSTRAINT facility_schedules_studio_id_fkey FOREIGN KEY (studio_id) REFERENCES %I.studios(id)$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.bookings
    ADD CONSTRAINT fk_bookings_class_session FOREIGN KEY (class_session_id) REFERENCES %I.class_sessions(id) ON DELETE CASCADE$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.bookings
    ADD CONSTRAINT fk_bookings_membership FOREIGN KEY (membership_id) REFERENCES %I.member_memberships(id) ON DELETE SET NULL$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.class_sessions
    ADD CONSTRAINT fk_class_sessions_class_type FOREIGN KEY (class_type_id) REFERENCES %I.class_types(id) ON DELETE RESTRICT$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.class_sessions
    ADD CONSTRAINT fk_class_sessions_instructor FOREIGN KEY (instructor_id) REFERENCES %I.instructors(id) ON DELETE RESTRICT$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.class_sessions
    ADD CONSTRAINT fk_class_sessions_room FOREIGN KEY (room_id) REFERENCES %I.rooms(id) ON DELETE SET NULL$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.gift_card_redemptions
    ADD CONSTRAINT gift_card_redemptions_gift_card_id_fkey FOREIGN KEY (gift_card_id) REFERENCES %I.gift_cards(id) ON DELETE CASCADE$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.inventory
    ADD CONSTRAINT inventory_product_id_fkey FOREIGN KEY (product_id) REFERENCES %I.products(id) ON DELETE CASCADE$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.inventory_transactions
    ADD CONSTRAINT inventory_transactions_product_id_fkey FOREIGN KEY (product_id) REFERENCES %I.products(id) ON DELETE CASCADE$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.job_application_documents
    ADD CONSTRAINT job_application_documents_application_id_fkey FOREIGN KEY (application_id) REFERENCES %I.job_applications(id) ON DELETE CASCADE$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.job_application_events
    ADD CONSTRAINT job_application_events_application_id_fkey FOREIGN KEY (application_id) REFERENCES %I.job_applications(id) ON DELETE CASCADE$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.maintenance_requests
    ADD CONSTRAINT maintenance_requests_equipment_id_fkey FOREIGN KEY (equipment_id) REFERENCES %I.equipment(id)$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.maintenance_requests
    ADD CONSTRAINT maintenance_requests_room_id_fkey FOREIGN KEY (room_id) REFERENCES %I.rooms(id)$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.maintenance_requests
    ADD CONSTRAINT maintenance_requests_studio_id_fkey FOREIGN KEY (studio_id) REFERENCES %I.studios(id)$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.member_credits
    ADD CONSTRAINT member_credits_member_id_fkey FOREIGN KEY (member_id) REFERENCES %I.members(id) ON DELETE CASCADE$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.member_milestones
    ADD CONSTRAINT member_milestones_member_id_fkey FOREIGN KEY (member_id) REFERENCES %I.members(id) ON DELETE CASCADE$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.onboarding_documents
    ADD CONSTRAINT onboarding_documents_packet_id_fkey FOREIGN KEY (packet_id) REFERENCES %I.onboarding_packets(id) ON DELETE CASCADE$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.payroll_employee_mapping
    ADD CONSTRAINT payroll_employee_mapping_instructor_id_fkey FOREIGN KEY (instructor_id) REFERENCES %I.instructors(id)$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.payroll_line_items
    ADD CONSTRAINT payroll_line_items_guest_instructor_id_fkey FOREIGN KEY (guest_instructor_id) REFERENCES %I.guest_instructors(id) ON DELETE SET NULL$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.payroll_line_items
    ADD CONSTRAINT payroll_line_items_instructor_id_fkey FOREIGN KEY (instructor_id) REFERENCES %I.instructors(id)$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.payroll_line_items
    ADD CONSTRAINT payroll_line_items_payroll_run_id_fkey FOREIGN KEY (payroll_run_id) REFERENCES %I.payroll_runs(id) ON DELETE CASCADE$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.pos_line_items
    ADD CONSTRAINT pos_line_items_product_id_fkey FOREIGN KEY (product_id) REFERENCES %I.products(id)$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.pos_line_items
    ADD CONSTRAINT pos_line_items_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES %I.pos_transactions(id) ON DELETE CASCADE$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.price_adjustments_log
    ADD CONSTRAINT price_adjustments_log_class_session_id_fkey FOREIGN KEY (class_session_id) REFERENCES %I.class_sessions(id) ON DELETE CASCADE$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.pricing_rules
    ADD CONSTRAINT pricing_rules_studio_id_fkey FOREIGN KEY (studio_id) REFERENCES %I.studios(id) ON DELETE CASCADE$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.reviews
    ADD CONSTRAINT reviews_class_session_id_fkey FOREIGN KEY (class_session_id) REFERENCES %I.class_sessions(id) ON DELETE CASCADE$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.reviews
    ADD CONSTRAINT reviews_member_id_fkey FOREIGN KEY (member_id) REFERENCES %I.members(id) ON DELETE CASCADE$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.sms_campaign_sends
    ADD CONSTRAINT sms_campaign_sends_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES %I.sms_campaigns(id) ON DELETE CASCADE$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.sms_campaigns
    ADD CONSTRAINT sms_campaigns_template_id_fkey FOREIGN KEY (template_id) REFERENCES %I.sms_templates(id) ON DELETE SET NULL$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.studio_user_roles
    ADD CONSTRAINT studio_user_roles_studio_id_fkey FOREIGN KEY (studio_id) REFERENCES %I.studios(id) ON DELETE CASCADE$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.sub_finder_requests
    ADD CONSTRAINT sub_finder_requests_class_session_id_fkey FOREIGN KEY (class_session_id) REFERENCES %I.class_sessions(id)$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.sub_finder_requests
    ADD CONSTRAINT sub_finder_requests_original_instructor_id_fkey FOREIGN KEY (original_instructor_id) REFERENCES %I.instructors(id)$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.sub_finder_requests
    ADD CONSTRAINT sub_finder_requests_substitute_instructor_id_fkey FOREIGN KEY (substitute_instructor_id) REFERENCES %I.instructors(id)$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.time_entries
    ADD CONSTRAINT time_entries_instructor_id_fkey FOREIGN KEY (instructor_id) REFERENCES %I.instructors(id)$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.video_membership_access
    ADD CONSTRAINT video_membership_access_membership_type_id_fkey FOREIGN KEY (membership_type_id) REFERENCES %I.membership_types(id) ON DELETE CASCADE$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.video_membership_access
    ADD CONSTRAINT video_membership_access_video_id_fkey FOREIGN KEY (video_id) REFERENCES %I.videos(id) ON DELETE CASCADE$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.video_views
    ADD CONSTRAINT video_views_video_id_fkey FOREIGN KEY (video_id) REFERENCES %I.videos(id) ON DELETE CASCADE$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.videos
    ADD CONSTRAINT videos_category_id_fkey FOREIGN KEY (category_id) REFERENCES %I.video_categories(id) ON DELETE SET NULL$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.voice_calls
    ADD CONSTRAINT voice_calls_member_id_fkey FOREIGN KEY (member_id) REFERENCES %I.members(id)$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.waiver_signatures
    ADD CONSTRAINT waiver_signatures_waiver_template_id_fkey FOREIGN KEY (waiver_template_id) REFERENCES %I.waiver_templates(id) ON DELETE CASCADE$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.webhook_deliveries
    ADD CONSTRAINT webhook_deliveries_webhook_config_id_fkey FOREIGN KEY (webhook_config_id) REFERENCES %I.webhook_configs(id) ON DELETE CASCADE$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.workshop_contracts
    ADD CONSTRAINT workshop_contracts_course_id_fkey FOREIGN KEY (course_id) REFERENCES %I.courses(id) ON DELETE CASCADE$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$ALTER TABLE ONLY %I.workshop_contracts
    ADD CONSTRAINT workshop_contracts_guest_instructor_id_fkey FOREIGN KEY (guest_instructor_id) REFERENCES %I.guest_instructors(id) ON DELETE RESTRICT$prov$, p_schema, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS acct_payout_items_auraflow_idx ON %I.acct_payout_items USING btree (auraflow_txn_id) WHERE (auraflow_txn_id IS NOT NULL)$prov$, p_schema);
    EXECUTE format($prov$CREATE UNIQUE INDEX IF NOT EXISTS acct_payout_items_uniq_idx ON %I.acct_payout_items USING btree (payout_id, provider_payment_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS acct_payouts_date_idx ON %I.acct_payouts USING btree (payout_date)$prov$, p_schema);
    EXECUTE format($prov$CREATE UNIQUE INDEX IF NOT EXISTS acct_payouts_provider_id_idx ON %I.acct_payouts USING btree (provider, provider_payout_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS acct_payouts_unreconciled_idx ON %I.acct_payouts USING btree (reconciled) WHERE (reconciled = false)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS acct_transactions_auraflow_idx ON %I.acct_transactions USING btree (auraflow_txn_id) WHERE (auraflow_txn_id IS NOT NULL)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS acct_transactions_date_idx ON %I.acct_transactions USING btree (txn_date)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS acct_transactions_payout_idx ON %I.acct_transactions USING btree (payout_id) WHERE (payout_id IS NOT NULL)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS acct_transactions_processor_pid_idx ON %I.acct_transactions USING btree (processor_payment_id) WHERE (processor_payment_id IS NOT NULL)$prov$, p_schema);
    EXECUTE format($prov$CREATE UNIQUE INDEX IF NOT EXISTS acct_transactions_source_extid_idx ON %I.acct_transactions USING btree (source, external_id) WHERE (external_id IS NOT NULL)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS acct_transactions_type_idx ON %I.acct_transactions USING btree (type, status)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS acct_vendor_rules_active_idx ON %I.acct_vendor_rules USING btree (priority) WHERE is_active$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_activity_actor ON %I.activity_log USING btree (actor_id, created_at DESC)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_activity_created ON %I.activity_log USING btree (created_at DESC)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_activity_resource ON %I.activity_log USING btree (resource_type, resource_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_avail_instructor_day ON %I.instructor_availability USING btree (instructor_id, day_of_week)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_bookings_class_session_id ON %I.bookings USING btree (class_session_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_bookings_member ON %I.bookings USING btree (member_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_bookings_member_id ON %I.bookings USING btree (member_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_bookings_reminder_sent ON %I.bookings USING btree (reminder_sent_at)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_bookings_session ON %I.bookings USING btree (class_session_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_bookings_status ON %I.bookings USING btree (status)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_campaigns_status ON %I.email_campaigns USING btree (status)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_cenroll_course ON %I.course_enrollments USING btree (course_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_cenroll_member ON %I.course_enrollments USING btree (member_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_class_series_studio ON %I.class_series USING btree (studio_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_class_sessions_series_id ON %I.class_sessions USING btree (series_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_class_sessions_starts_at ON %I.class_sessions USING btree (starts_at)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_class_sessions_studio_id ON %I.class_sessions USING btree (studio_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_comm_log_member ON %I.communication_log USING btree (member_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_comm_log_type ON %I.communication_log USING btree (type)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_communication_log_type_created ON %I.communication_log USING btree (type, created_at)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_courses_status ON %I.courses USING btree (status)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_courses_type ON %I.courses USING btree (type)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_cp_reservations_session ON %I.classpass_reservations USING btree (class_session_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_cp_reservations_status ON %I.classpass_reservations USING btree (status)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_csends_campaign ON %I.email_campaign_sends USING btree (campaign_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_csess_course ON %I.course_sessions USING btree (course_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_equipment_category ON %I.equipment USING btree (category)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_equipment_room ON %I.equipment USING btree (room_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_equipment_studio ON %I.equipment USING btree (studio_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_fac_completion_schedule ON %I.facility_schedule_completions USING btree (schedule_id, completed_at DESC)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_fac_schedule_overdue ON %I.facility_schedules USING btree (next_due_at) WHERE (is_active = true)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_fac_schedule_studio ON %I.facility_schedules USING btree (studio_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_failed_pay_member ON %I.failed_payment_attempts USING btree (member_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_gdpr_del_member ON %I.gdpr_deletion_requests USING btree (member_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_gdpr_del_scheduled ON %I.gdpr_deletion_requests USING btree (scheduled_deletion_at) WHERE ((status)::text = 'pending'::text)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_gdpr_del_status ON %I.gdpr_deletion_requests USING btree (status) WHERE ((status)::text = 'pending'::text)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_instructors_phone_hash ON %I.instructors USING btree (phone_hash) WHERE (phone_hash IS NOT NULL)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_instructors_user ON %I.instructors USING btree (user_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_maintenance_open ON %I.maintenance_requests USING btree (status) WHERE ((status)::text = ANY ((ARRAY['open'::character varying, 'in_progress'::character varying])::text[]))$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_maintenance_status ON %I.maintenance_requests USING btree (status)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_maintenance_studio ON %I.maintenance_requests USING btree (studio_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_member_credits_available ON %I.member_credits USING btree (member_id, service_filter, expires_at) WHERE (used_at IS NULL)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_member_credits_source_ref ON %I.member_credits USING btree (source_ref_id) WHERE (source_ref_id IS NOT NULL)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_member_memberships_member ON %I.member_memberships USING btree (member_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_member_memberships_member_status ON %I.member_memberships USING btree (member_id, status)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_member_memberships_status ON %I.member_memberships USING btree (status)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_member_notes_member ON %I.member_notes USING btree (member_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_members_birthday ON %I.members USING btree (birthday_month, birthday_day)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_members_email ON %I.members USING btree (email)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_members_name ON %I.members USING btree (last_name, first_name)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_members_stripe_customer ON %I.members USING btree (stripe_customer_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_membership_types_template_key ON %I.membership_types USING btree (template_key) WHERE (template_key IS NOT NULL)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_payroll_mapping_provider ON %I.payroll_employee_mapping USING btree (provider)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_pb_instructor_starts ON %I.private_bookings USING btree (instructor_id, starts_at)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_pb_starts ON %I.private_bookings USING btree (starts_at)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_price_adj_created ON %I.price_adjustments_log USING btree (created_at DESC)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_price_adj_session ON %I.price_adjustments_log USING btree (class_session_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_pricing_rules_studio ON %I.pricing_rules USING btree (studio_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_reviews_created ON %I.reviews USING btree (created_at DESC)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_reviews_member ON %I.reviews USING btree (member_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_reviews_rating ON %I.reviews USING btree (rating)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_reviews_sentiment ON %I.reviews USING btree (sentiment)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_reviews_session ON %I.reviews USING btree (class_session_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_rooms_studio ON %I.rooms USING btree (studio_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_sessions_recording_status ON %I.class_sessions USING btree (recording_status) WHERE ((recording_status)::text <> 'none'::text)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_sessions_room ON %I.class_sessions USING btree (room_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_sessions_series ON %I.class_sessions USING btree (series_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_sessions_starts ON %I.class_sessions USING btree (starts_at)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_sms_member ON %I.sms_messages USING btree (member_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_smscampaigns_scheduled ON %I.sms_campaigns USING btree (scheduled_at) WHERE ((status)::text = 'scheduled'::text)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_smscampaigns_status ON %I.sms_campaigns USING btree (status)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_smssends_campaign ON %I.sms_campaign_sends USING btree (campaign_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_smstemplates_category ON %I.sms_templates USING btree (category)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_smstemplates_slug ON %I.sms_templates USING btree (slug)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_subfinder_session ON %I.sub_finder_requests USING btree (class_session_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_subfinder_status ON %I.sub_finder_requests USING btree (status) WHERE ((status)::text = ANY ((ARRAY['searching'::character varying, 'offered'::character varying])::text[]))$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_subreq_current ON %I.sub_requests USING btree (current_attempt_instructor_id) WHERE ((status)::text = 'searching'::text)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_subreq_session ON %I.sub_requests USING btree (class_session_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_subreq_status ON %I.sub_requests USING btree (status) WHERE ((status)::text = 'searching'::text)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_transactions_created_at ON %I.transactions USING btree (created_at)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_transactions_member ON %I.transactions USING btree (member_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_transactions_membership ON %I.transactions USING btree (membership_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_transactions_status ON %I.transactions USING btree (status)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_transactions_stripe_pi ON %I.transactions USING btree (stripe_payment_intent_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_video_access_video ON %I.video_membership_access USING btree (video_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_video_views_member ON %I.video_views USING btree (member_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_video_views_video ON %I.video_views USING btree (video_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_videos_category ON %I.videos USING btree (category_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_videos_published ON %I.videos USING btree (is_published, sort_order)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_videos_source ON %I.videos USING btree (source)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_wsig_member_expires ON %I.waiver_signatures USING btree (member_id, expires_at)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_wsig_member_template ON %I.waiver_signatures USING btree (member_id, waiver_template_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_af_tenant_wtpl_active ON %I.waiver_templates USING btree (is_active) WHERE (is_active = true)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON %I.api_keys USING btree (key_hash) WHERE (is_active = true)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_api_keys_prefix ON %I.api_keys USING btree (key_prefix)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_chatbot_conv_last ON %I.chatbot_conversations USING btree (last_message_at DESC)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_chatbot_conv_user ON %I.chatbot_conversations USING btree (user_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_chatbot_msg_conv ON %I.chatbot_messages USING btree (conversation_id, created_at)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_class_sessions_modality ON %I.class_sessions USING btree (modality)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_courses_guest_instructor ON %I.courses USING btree (guest_instructor_id) WHERE (guest_instructor_id IS NOT NULL)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_drafts_created ON %I.marketing_drafts USING btree (created_at DESC)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_drafts_status ON %I.marketing_drafts USING btree (status)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_emr_encounter_log_booking ON %I.emr_encounter_log USING btree (booking_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_emr_encounter_log_status ON %I.emr_encounter_log USING btree (status) WHERE ((status)::text = 'failed'::text)$prov$, p_schema);
    EXECUTE format($prov$CREATE UNIQUE INDEX IF NOT EXISTS idx_emr_patient_map_emr ON %I.emr_patient_map USING btree (emr_patient_id, emr_system)$prov$, p_schema);
    EXECUTE format($prov$CREATE UNIQUE INDEX IF NOT EXISTS idx_emr_patient_map_member ON %I.emr_patient_map USING btree (member_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_emr_sync_log_created ON %I.emr_sync_log USING btree (created_at DESC)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_eng_campaigns_member ON %I.engagement_campaigns USING btree (member_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_eng_campaigns_status ON %I.engagement_campaigns USING btree (status)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_eng_campaigns_type ON %I.engagement_campaigns USING btree (engagement_type)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_eng_messages_campaign ON %I.engagement_messages USING btree (campaign_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_gc_redemptions_gc ON %I.gift_card_redemptions USING btree (gift_card_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_gc_redemptions_member ON %I.gift_card_redemptions USING btree (member_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_gift_cards_code ON %I.gift_cards USING btree (code)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_gift_cards_status ON %I.gift_cards USING btree (status)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_tnt_members_email_trgm ON %I.members USING gin (email public.gin_trgm_ops)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_tnt_members_fullname_trgm ON %I.members USING gin (((((first_name)::text || ' '::text) || (last_name)::text)) public.gin_trgm_ops)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_guest_instructors_name ON %I.guest_instructors USING btree (lower((name)::text))$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_guest_instructors_studio_active ON %I.guest_instructors USING btree (studio_id, is_active)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_inv_txn_product_date ON %I.inventory_transactions USING btree (product_id, created_at DESC)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_job_app_docs_app ON %I.job_application_documents USING btree (application_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_job_app_events_app ON %I.job_application_events USING btree (application_id, created_at)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_job_apps_email ON %I.job_applications USING btree (lower((email)::text))$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_job_apps_status ON %I.job_applications USING btree (status, created_at DESC)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_members_phone_hash ON %I.members USING btree (phone_hash) WHERE (phone_hash IS NOT NULL)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_milestones_member ON %I.member_milestones USING btree (member_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_notif_unread ON %I.notifications USING btree (user_id) WHERE (is_read = false)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_notif_user ON %I.notifications USING btree (user_id, created_at DESC)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_onboarding_docs_packet ON %I.onboarding_documents USING btree (packet_id, sort_order)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_onboarding_docs_user ON %I.onboarding_documents USING btree (user_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE UNIQUE INDEX IF NOT EXISTS idx_onboarding_packet_token ON %I.onboarding_packets USING btree (signing_token) WHERE (signing_token IS NOT NULL)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_onboarding_packet_user ON %I.onboarding_packets USING btree (user_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_pos_line_txn ON %I.pos_line_items USING btree (transaction_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_pos_txn_created ON %I.pos_transactions USING btree (created_at DESC)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_products_category ON %I.products USING btree (category) WHERE (active = true)$prov$, p_schema);
    EXECUTE format($prov$CREATE UNIQUE INDEX IF NOT EXISTS idx_products_sku ON %I.products USING btree (sku) WHERE ((sku IS NOT NULL) AND (active = true))$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_reviews_gmb_id ON %I.reviews USING btree (gmb_review_id) WHERE (gmb_review_id IS NOT NULL)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_reviews_source ON %I.reviews USING btree (source)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_sessions_community ON %I.class_sessions USING btree (is_community) WHERE (is_community = true)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_social_msgs_status ON %I.studio_social_messages USING btree (ai_status)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_social_posts_status ON %I.studio_social_posts USING btree (status)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_studio_inbox_account ON %I.studio_inbox_messages USING btree (account_id, received_at DESC)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_studio_inbox_class ON %I.studio_inbox_messages USING btree (classification)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_studio_inbox_from ON %I.studio_inbox_messages USING btree (from_email)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_studio_inbox_member ON %I.studio_inbox_messages USING btree (member_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_studio_inbox_status ON %I.studio_inbox_messages USING btree (status)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_studio_replies_msg ON %I.studio_inbox_replies USING btree (message_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_studio_user_roles_user ON %I.studio_user_roles USING btree (user_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_sub_requests_current ON %I.sub_requests USING btree (current_attempt_instructor_id) WHERE ((status)::text = 'searching'::text)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_sub_requests_session ON %I.sub_requests USING btree (class_session_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_sub_requests_status ON %I.sub_requests USING btree (status) WHERE ((status)::text = 'searching'::text)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_time_entries_instructor_clock ON %I.time_entries USING btree (instructor_id, clock_in)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_time_entries_pending ON %I.time_entries USING btree (status) WHERE ((status)::text = 'pending'::text)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_transactions_external_reference ON %I.transactions USING btree (((metadata ->> 'external_reference'::text))) WHERE ((metadata ->> 'external_reference'::text) IS NOT NULL)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_voice_calls_member ON %I.voice_calls USING btree (member_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_voice_calls_reference ON %I.voice_calls USING btree (reference_type, reference_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_voice_calls_twilio_sid ON %I.voice_calls USING btree (twilio_sid)$prov$, p_schema);
    EXECUTE format($prov$CREATE UNIQUE INDEX IF NOT EXISTS idx_w4_token ON %I.employee_w4_forms USING btree (signing_token) WHERE (signing_token IS NOT NULL)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_w4_user ON %I.employee_w4_forms USING btree (user_id)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_wh_del_config ON %I.webhook_deliveries USING btree (webhook_config_id, created_at DESC)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_wh_del_retry ON %I.webhook_deliveries USING btree (status, next_retry_at) WHERE (status = ANY (ARRAY['pending'::text, 'failed'::text]))$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_workshop_contracts_guest ON %I.workshop_contracts USING btree (guest_instructor_id, signed_at DESC NULLS LAST)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_workshop_contracts_reminder ON %I.workshop_contracts USING btree (email_sent_at, reminder_sent_at) WHERE (((status)::text = ANY ((ARRAY['sent'::character varying, 'viewed'::character varying])::text[])) AND (reminder_sent_at IS NULL))$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_workshop_contracts_status ON %I.workshop_contracts USING btree (status) WHERE ((status)::text = ANY ((ARRAY['prepared'::character varying, 'sent'::character varying, 'viewed'::character varying])::text[]))$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS idx_workshop_contracts_token ON %I.workshop_contracts USING btree (signing_token) WHERE (signing_token IS NOT NULL)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS member_memberships_trial_period_end_idx ON %I.member_memberships USING btree (trial_period_end) WHERE (trial_period_end IS NOT NULL)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS members_square_customer_idx ON %I.members USING btree (square_customer_id) WHERE (square_customer_id IS NOT NULL)$prov$, p_schema);
    EXECUTE format($prov$CREATE UNIQUE INDEX IF NOT EXISTS payroll_line_items_run_guest_uq ON %I.payroll_line_items USING btree (payroll_run_id, guest_instructor_id) WHERE (guest_instructor_id IS NOT NULL)$prov$, p_schema);
    EXECUTE format($prov$CREATE UNIQUE INDEX IF NOT EXISTS payroll_line_items_run_instructor_uq ON %I.payroll_line_items USING btree (payroll_run_id, instructor_id) WHERE (instructor_id IS NOT NULL)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS pos_terminal_checkouts_member_idx ON %I.pos_terminal_checkouts USING btree (member_id, initiated_at DESC)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS pos_terminal_checkouts_square_idx ON %I.pos_terminal_checkouts USING btree (square_checkout_id) WHERE (square_checkout_id IS NOT NULL)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS pos_terminal_checkouts_status_idx ON %I.pos_terminal_checkouts USING btree (status, expires_at)$prov$, p_schema);
    EXECUTE format($prov$CREATE UNIQUE INDEX IF NOT EXISTS studio_inbox_messages_msgid_unique ON %I.studio_inbox_messages USING btree (message_id_header) WHERE (message_id_header IS NOT NULL)$prov$, p_schema);
    EXECUTE format($prov$CREATE INDEX IF NOT EXISTS transactions_square_payment_idx ON %I.transactions USING btree (square_payment_id) WHERE (square_payment_id IS NOT NULL)$prov$, p_schema);
    EXECUTE format($prov$CREATE UNIQUE INDEX IF NOT EXISTS uq_workshop_contracts_active_per_course ON %I.workshop_contracts USING btree (course_id) WHERE ((status)::text <> 'voided'::text)$prov$, p_schema);
    BEGIN EXECUTE format($prov$CREATE TRIGGER af_tenant_touch_bookings BEFORE UPDATE ON %I.bookings FOR EACH ROW EXECUTE FUNCTION af_global.touch_updated_at()$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$CREATE TRIGGER af_tenant_touch_instructor_availability BEFORE UPDATE ON %I.instructor_availability FOR EACH ROW EXECUTE FUNCTION af_global.touch_updated_at()$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$CREATE TRIGGER af_tenant_touch_private_services BEFORE UPDATE ON %I.private_services FOR EACH ROW EXECUTE FUNCTION af_global.touch_updated_at()$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
    BEGIN EXECUTE format($prov$CREATE TRIGGER af_tenant_touch_rooms BEFORE UPDATE ON %I.rooms FOR EACH ROW EXECUTE FUNCTION af_global.touch_updated_at()$prov$, p_schema);
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END;
END;
$fn$ LANGUAGE plpgsql;

-- ── af_global tables ────────────────────────────────────────────────
CREATE TABLE af_global.ai_token_usage (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    organization_id uuid NOT NULL,
    service_name character varying(100) NOT NULL,
    function_name character varying(200) NOT NULL,
    model character varying(100) NOT NULL,
    input_tokens integer DEFAULT 0 NOT NULL,
    output_tokens integer DEFAULT 0 NOT NULL,
    total_tokens integer DEFAULT 0 NOT NULL,
    stripe_meter_event_id character varying(100),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE af_global.api_key_routing (
    key_prefix text NOT NULL,
    org_slug text NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);
CREATE TABLE af_global.audit_log (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    organization_id uuid,
    user_id uuid,
    action character varying(100) NOT NULL,
    resource_type character varying(100),
    resource_id uuid,
    metadata jsonb DEFAULT '{}'::jsonb,
    ip_address inet,
    created_at timestamp with time zone DEFAULT now()
);
CREATE TABLE af_global.coupons (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    code character varying(50) NOT NULL,
    discount_type character varying(10) NOT NULL,
    discount_value integer NOT NULL,
    max_uses integer,
    uses_count integer DEFAULT 0 NOT NULL,
    expires_at timestamp with time zone,
    description text,
    stripe_coupon_id character varying(255),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT coupons_discount_type_check CHECK (((discount_type)::text = ANY ((ARRAY['percent'::character varying, 'fixed'::character varying])::text[])))
);
CREATE TABLE af_global.dead_letter_tasks (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    task_name character varying(255) NOT NULL,
    task_id character varying(255),
    args jsonb,
    kwargs jsonb,
    exception text,
    traceback text,
    retries integer DEFAULT 0,
    failed_at timestamp with time zone DEFAULT now() NOT NULL,
    replayed_at timestamp with time zone,
    replayed_by uuid,
    resolution character varying(30) DEFAULT 'pending'::character varying,
    CONSTRAINT dlt_resolution_check CHECK (((resolution)::text = ANY ((ARRAY['pending'::character varying, 'replayed'::character varying, 'ignored'::character varying, 'investigating'::character varying])::text[])))
);
CREATE TABLE af_global.email_suppressions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    email text NOT NULL,
    reason text DEFAULT 'bounce'::text NOT NULL,
    detail text,
    lead_id uuid,
    source text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE af_global.feature_flags (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    organization_id uuid,
    flag_key character varying(100) NOT NULL,
    is_enabled boolean DEFAULT false,
    config jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);
CREATE TABLE af_global.kiosk_devices (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    organization_id uuid NOT NULL,
    device_token text NOT NULL,
    ip_hash text,
    user_agent_hash text,
    label text NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    registered_by uuid,
    registered_at timestamp with time zone DEFAULT now() NOT NULL,
    last_seen_at timestamp with time zone,
    revoked_at timestamp with time zone,
    revoked_by uuid
);
CREATE TABLE af_global.membership_templates (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    template_key character varying(50) NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    type character varying(30) NOT NULL,
    access_scope character varying(30) DEFAULT 'in_studio'::character varying NOT NULL,
    suggested_price_cents integer,
    billing_period character varying(20),
    class_count integer,
    duration_days integer,
    auto_renew boolean DEFAULT true,
    freeze_allowed boolean DEFAULT false,
    sort_order integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT membership_templates_access_scope_check CHECK (((access_scope)::text = ANY ((ARRAY['in_studio'::character varying, 'online'::character varying, 'all_access'::character varying])::text[]))),
    CONSTRAINT membership_templates_billing_period_check CHECK (((billing_period)::text = ANY ((ARRAY['monthly'::character varying, 'yearly'::character varying, 'quarterly'::character varying, 'semi_annual'::character varying, 'one_time'::character varying])::text[]))),
    CONSTRAINT membership_templates_type_check CHECK (((type)::text = ANY ((ARRAY['unlimited'::character varying, 'class_pack'::character varying, 'intro_offer'::character varying, 'day_pass'::character varying, 'single_class'::character varying])::text[])))
);
CREATE TABLE af_global.organization_integrations (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    organization_id uuid NOT NULL,
    integration_type text NOT NULL,
    access_token text,
    refresh_token text,
    token_expires_at timestamp with time zone,
    metadata jsonb DEFAULT '{}'::jsonb,
    connected_at timestamp with time zone DEFAULT now(),
    disconnected_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE af_global.organization_users (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    organization_id uuid NOT NULL,
    user_id uuid NOT NULL,
    role character varying(50) DEFAULT 'member'::character varying NOT NULL,
    is_active boolean DEFAULT true,
    invited_by uuid,
    invited_at timestamp with time zone,
    joined_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    title character varying(100),
    department character varying(100),
    hire_date date,
    notes text,
    kiosk_pin_hash text,
    kiosk_pin_set_at timestamp with time zone,
    CONSTRAINT organization_users_role_check CHECK (((role)::text = ANY ((ARRAY['owner'::character varying, 'admin'::character varying, 'instructor'::character varying, 'front_desk'::character varying, 'member'::character varying])::text[])))
);
CREATE TABLE af_global.organizations (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    slug character varying(100) NOT NULL,
    name character varying(255) NOT NULL,
    schema_name character varying(100) NOT NULL,
    status character varying(20) DEFAULT 'trial'::character varying,
    plan_id character varying(50),
    trial_ends_at timestamp with time zone,
    stripe_customer_id character varying(100),
    stripe_account_id character varying(100),
    stripe_subscription_id character varying(100),
    custom_domain character varying(255),
    primary_color character varying(7) DEFAULT '#4F46E5'::character varying,
    logo_url text,
    timezone character varying(50) DEFAULT 'America/Los_Angeles'::character varying,
    country character varying(2) DEFAULT 'US'::character varying,
    currency character varying(3) DEFAULT 'USD'::character varying,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    youtube_api_key_encrypted bytea,
    youtube_channel_id character varying(100),
    youtube_connected_at timestamp with time zone,
    mux_token_id_encrypted bytea,
    mux_token_secret_encrypted bytea,
    mux_environment_id character varying(100),
    mux_connected_at timestamp with time zone,
    classpass_partner_id character varying(100),
    zoom_account_id character varying(100),
    zoom_client_id_encrypted bytea,
    zoom_client_secret_encrypted bytea,
    zoom_connected_at timestamp with time zone,
    zoom_webhook_secret_encrypted bytea,
    zoom_auto_record boolean DEFAULT true,
    zoom_auto_publish boolean DEFAULT false,
    youtube_refresh_token_encrypted bytea,
    sendgrid_api_key_encrypted bytea,
    sendgrid_from_email character varying(255),
    sendgrid_from_name character varying(100),
    sendgrid_connected_at timestamp with time zone,
    sendgrid_webhook_verified boolean DEFAULT false,
    twilio_account_sid_encrypted bytea,
    twilio_auth_token_encrypted bytea,
    twilio_phone_number character varying(20),
    twilio_connected_at timestamp with time zone,
    gusto_company_id character varying(100),
    gusto_connected_at timestamp with time zone,
    gusto_access_token_encrypted bytea,
    gusto_refresh_token_encrypted bytea,
    qb_realm_id character varying(100),
    qb_connected_at timestamp with time zone,
    qb_access_token_encrypted bytea,
    qb_refresh_token_encrypted bytea,
    gusto_client_id_encrypted bytea,
    qb_client_id_encrypted bytea,
    qb_client_secret_encrypted bytea,
    custom_domain_status character varying(20),
    custom_domain_verified_at timestamp with time zone,
    emr_protocol character varying(10),
    emr_base_url text,
    emr_client_id_encrypted bytea,
    emr_client_secret_encrypted bytea,
    emr_webhook_secret character varying(128),
    emr_hl7_host text,
    emr_hl7_port integer,
    emr_connected_at timestamp with time zone,
    emr_sync_enabled boolean DEFAULT false,
    cancellation_reason character varying(100),
    cancellation_feedback text,
    cancellation_requested_at timestamp with time zone,
    cancellation_effective_at timestamp with time zone,
    mailchimp_api_key_encrypted bytea,
    mailchimp_list_id character varying(50),
    mailchimp_connected_at timestamp with time zone,
    stripe_charges_enabled boolean DEFAULT false,
    stripe_payouts_enabled boolean DEFAULT false,
    discount_coupon_code character varying(50),
    discount_percent integer,
    custom_price_cents integer,
    meta_ad_account_id character varying(100),
    google_ads_customer_id character varying(100),
    stripe_publishable_key character varying(255),
    stripe_secret_key_encrypted bytea,
    stripe_webhook_secret_encrypted bytea,
    stripe_direct_mode boolean DEFAULT false,
    website_url character varying(500),
    address text,
    meta_access_token_encrypted bytea,
    meta_connected_at timestamp with time zone,
    google_ads_refresh_token_encrypted bytea,
    google_ads_connected_at timestamp with time zone,
    allowed_portal_origins text[] DEFAULT ARRAY[]::text[] NOT NULL,
    brand_config jsonb DEFAULT '{}'::jsonb NOT NULL,
    square_merchant_id text,
    square_access_token_encrypted bytea,
    square_refresh_token_encrypted bytea,
    square_token_expires_at timestamp with time zone,
    square_location_id text,
    billing_provider text DEFAULT 'square'::text NOT NULL,
    square_subscription_id text,
    square_pos_default_device_id uuid,
    square_pos_tip_settings jsonb,
    CONSTRAINT organizations_billing_provider_chk CHECK ((billing_provider = ANY (ARRAY['stripe'::text, 'square'::text]))),
    CONSTRAINT organizations_status_check CHECK (((status)::text = ANY ((ARRAY['trial'::character varying, 'active'::character varying, 'suspended'::character varying, 'cancelled'::character varying, 'cancelling'::character varying, 'trial_expired'::character varying])::text[])))
);
CREATE TABLE af_global.platform_ads_config (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    google_max_monthly_cents bigint DEFAULT 0,
    meta_max_monthly_cents bigint DEFAULT 0,
    location_targets jsonb DEFAULT '[]'::jsonb,
    google_enabled boolean DEFAULT false,
    meta_enabled boolean DEFAULT false,
    ai_auto_optimize boolean DEFAULT false,
    approval_threshold_cents bigint DEFAULT 5000,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);
CREATE TABLE af_global.platform_ai_agent_log (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    agent_type character varying(50) NOT NULL,
    action character varying(100) NOT NULL,
    details jsonb DEFAULT '{}'::jsonb,
    status character varying(20) DEFAULT 'success'::character varying,
    related_id uuid,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT platform_ai_agent_log_status_check CHECK (((status)::text = ANY ((ARRAY['success'::character varying, 'failure'::character varying, 'pending'::character varying])::text[])))
);
CREATE TABLE af_global.platform_announcements (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    title character varying(500) NOT NULL,
    body text,
    type character varying(20) DEFAULT 'info'::character varying,
    is_active boolean DEFAULT true,
    starts_at timestamp with time zone,
    ends_at timestamp with time zone,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT platform_announcements_type_check CHECK (((type)::text = ANY ((ARRAY['info'::character varying, 'warning'::character varying, 'maintenance'::character varying, 'feature'::character varying])::text[])))
);
CREATE TABLE af_global.platform_backup_schedule (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    backup_type character varying(20) NOT NULL,
    cron_expression character varying(100) DEFAULT '0 3 * * *'::character varying NOT NULL,
    retention_days integer DEFAULT 30,
    is_active boolean DEFAULT true,
    last_run_at timestamp with time zone,
    next_run_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT platform_backup_schedule_backup_type_check CHECK (((backup_type)::text = ANY ((ARRAY['database'::character varying, 'files'::character varying])::text[])))
);
CREATE TABLE af_global.platform_backups (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    backup_type character varying(20) NOT NULL,
    status character varying(20) DEFAULT 'pending'::character varying,
    file_name character varying(500),
    file_size_bytes bigint,
    b2_file_id character varying(255),
    b2_bucket character varying(100),
    duration_seconds integer,
    error_message text,
    triggered_by character varying(20) DEFAULT 'manual'::character varying,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    verified boolean,
    CONSTRAINT platform_backups_backup_type_check CHECK (((backup_type)::text = ANY ((ARRAY['database'::character varying, 'files'::character varying])::text[]))),
    CONSTRAINT platform_backups_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'running'::character varying, 'completed'::character varying, 'failed'::character varying])::text[]))),
    CONSTRAINT platform_backups_triggered_by_check CHECK (((triggered_by)::text = ANY ((ARRAY['manual'::character varying, 'scheduled'::character varying, 'manual_test'::character varying, 'nightly'::character varying])::text[])))
);
CREATE TABLE af_global.platform_config (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    sendgrid_api_key_enc bytea,
    sendgrid_from_email character varying(255) DEFAULT 'hello@auraflow.fit'::character varying,
    sendgrid_from_name character varying(100) DEFAULT 'AuraFlow'::character varying,
    sendgrid_inbound_webhook_secret_enc bytea,
    platform_admin_alert_email character varying(255) DEFAULT 'support2@auraflow.fit'::character varying,
    support_escalation_email character varying(255) DEFAULT 'support2@auraflow.fit'::character varying,
    google_ads_developer_token_enc bytea,
    google_ads_login_customer_id character varying(100),
    google_client_id character varying(255),
    google_client_secret_enc bytea,
    meta_app_id character varying(255),
    meta_app_secret_enc bytea,
    meta_page_access_token_enc bytea,
    meta_page_id character varying(255),
    instagram_business_account_id character varying(255),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);
CREATE TABLE af_global.platform_email_accounts (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    email_address character varying(255) NOT NULL,
    display_name character varying(255) DEFAULT 'AuraFlow'::character varying,
    imap_host character varying(255) DEFAULT 'imap.purelymail.com'::character varying NOT NULL,
    imap_port integer DEFAULT 993 NOT NULL,
    imap_use_tls boolean DEFAULT true NOT NULL,
    smtp_host character varying(255) DEFAULT 'smtp.purelymail.com'::character varying NOT NULL,
    smtp_port integer DEFAULT 465 NOT NULL,
    smtp_use_tls boolean DEFAULT true NOT NULL,
    username character varying(255) NOT NULL,
    password_enc bytea NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    last_checked_at timestamp with time zone,
    last_uid integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);
CREATE TABLE af_global.platform_email_inbox (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    message_id character varying(500),
    mailbox character varying(50) DEFAULT 'support'::character varying NOT NULL,
    from_email character varying(255) NOT NULL,
    from_name character varying(255),
    to_email character varying(255) NOT NULL,
    subject character varying(1000),
    body_text text,
    body_html text,
    ai_status character varying(20) DEFAULT 'pending'::character varying,
    ai_response text,
    ai_summary text,
    ai_actions jsonb DEFAULT '[]'::jsonb,
    escalated_to character varying(255),
    escalation_reason text,
    resolved_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    account_id uuid,
    CONSTRAINT platform_email_inbox_ai_status_check CHECK (((ai_status)::text = ANY ((ARRAY['pending'::character varying, 'processing'::character varying, 'resolved'::character varying, 'escalated'::character varying, 'failed'::character varying])::text[]))),
    CONSTRAINT platform_email_inbox_mailbox_check CHECK (((mailbox)::text = ANY ((ARRAY['hello'::character varying, 'support'::character varying])::text[])))
);
CREATE TABLE af_global.platform_invoices (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    organization_id uuid NOT NULL,
    square_invoice_id text,
    square_order_id text,
    period_start date NOT NULL,
    period_end date NOT NULL,
    plan_fee_cents integer DEFAULT 0 NOT NULL,
    token_overage_cents integer DEFAULT 0 NOT NULL,
    token_count integer DEFAULT 0 NOT NULL,
    total_cents integer DEFAULT 0 NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    sent_at timestamp with time zone,
    paid_at timestamp with time zone,
    failed_at timestamp with time zone,
    failure_reason text
);
CREATE TABLE af_global.platform_landing_pages (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    slug character varying(200) NOT NULL,
    title character varying(500) NOT NULL,
    campaign_source character varying(50),
    campaign_id character varying(255),
    hero_headline text,
    hero_subheadline text,
    hero_cta_text character varying(100) DEFAULT 'Get Started'::character varying,
    hero_cta_url character varying(500),
    features_json jsonb DEFAULT '[]'::jsonb,
    testimonials_json jsonb DEFAULT '[]'::jsonb,
    custom_sections_json jsonb DEFAULT '[]'::jsonb,
    meta_title character varying(200),
    meta_description character varying(500),
    utm_source character varying(100),
    utm_medium character varying(100),
    utm_campaign character varying(200),
    views integer DEFAULT 0,
    conversions integer DEFAULT 0,
    status character varying(20) DEFAULT 'draft'::character varying,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT platform_landing_pages_status_check CHECK (((status)::text = ANY ((ARRAY['draft'::character varying, 'active'::character varying, 'paused'::character varying])::text[])))
);
CREATE TABLE af_global.platform_metrics_daily (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    metric_date date NOT NULL,
    total_organizations integer DEFAULT 0,
    active_organizations integer DEFAULT 0,
    total_users integer DEFAULT 0,
    total_members integer DEFAULT 0,
    total_revenue_cents bigint DEFAULT 0,
    total_bookings integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT now()
);
CREATE TABLE af_global.platform_plans (
    id character varying(30) NOT NULL,
    name character varying(100) NOT NULL,
    price_cents integer DEFAULT 0 NOT NULL,
    price_display character varying(50) NOT NULL,
    "interval" character varying(20) DEFAULT 'month'::character varying NOT NULL,
    tagline text,
    price_note text,
    additional_location_cents integer,
    contact_sales boolean DEFAULT false,
    popular boolean DEFAULT false,
    features jsonb DEFAULT '[]'::jsonb NOT NULL,
    limits jsonb DEFAULT '{}'::jsonb NOT NULL,
    sort_order integer DEFAULT 0,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);
CREATE TABLE af_global.platform_request_metrics (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    period_start timestamp with time zone NOT NULL,
    total_requests integer DEFAULT 0,
    avg_response_ms numeric(10,2) DEFAULT 0,
    p95_response_ms numeric(10,2) DEFAULT 0,
    p99_response_ms numeric(10,2) DEFAULT 0,
    error_count integer DEFAULT 0,
    unique_ips integer DEFAULT 0,
    top_endpoints jsonb DEFAULT '[]'::jsonb,
    status_codes jsonb DEFAULT '{}'::jsonb,
    geo_data jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now()
);
CREATE TABLE af_global.platform_security_events (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    event_type character varying(50) NOT NULL,
    severity character varying(10) DEFAULT 'low'::character varying,
    source_ip character varying(45),
    user_agent text,
    endpoint character varying(500),
    details jsonb DEFAULT '{}'::jsonb,
    acknowledged boolean DEFAULT false,
    acknowledged_at timestamp with time zone,
    acknowledged_by uuid,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT platform_security_events_event_type_check CHECK (((event_type)::text = ANY ((ARRAY['failed_login'::character varying, 'rate_limit'::character varying, 'brute_force'::character varying, 'unusual_api'::character varying, 'suspicious_ip'::character varying, 'error_spike'::character varying])::text[]))),
    CONSTRAINT platform_security_events_severity_check CHECK (((severity)::text = ANY ((ARRAY['low'::character varying, 'medium'::character varying, 'high'::character varying, 'critical'::character varying])::text[])))
);
CREATE TABLE af_global.platform_settings (
    key character varying(100) NOT NULL,
    value jsonb NOT NULL,
    description text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_by uuid
);
CREATE TABLE af_global.platform_social_messages (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    platform character varying(20) NOT NULL,
    conversation_id character varying(255),
    sender_id character varying(255),
    sender_name character varying(255),
    message_text text,
    message_type character varying(20) DEFAULT 'message'::character varying,
    post_id uuid,
    ai_status character varying(20) DEFAULT 'pending'::character varying,
    ai_response text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT platform_social_messages_ai_status_check CHECK (((ai_status)::text = ANY ((ARRAY['pending'::character varying, 'processing'::character varying, 'resolved'::character varying, 'ignored'::character varying])::text[]))),
    CONSTRAINT platform_social_messages_message_type_check CHECK (((message_type)::text = ANY ((ARRAY['message'::character varying, 'comment'::character varying, 'mention'::character varying])::text[]))),
    CONSTRAINT platform_social_messages_platform_check CHECK (((platform)::text = ANY ((ARRAY['facebook'::character varying, 'instagram'::character varying])::text[])))
);
CREATE TABLE af_global.platform_social_posts (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    platform character varying(20) NOT NULL,
    platform_post_id character varying(255),
    content text NOT NULL,
    media_urls jsonb DEFAULT '[]'::jsonb,
    post_type character varying(30) DEFAULT 'post'::character varying,
    status character varying(20) DEFAULT 'draft'::character varying,
    scheduled_at timestamp with time zone,
    published_at timestamp with time zone,
    engagement jsonb DEFAULT '{}'::jsonb,
    ai_generated boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT platform_social_posts_platform_check CHECK (((platform)::text = ANY ((ARRAY['facebook'::character varying, 'instagram'::character varying])::text[]))),
    CONSTRAINT platform_social_posts_post_type_check CHECK (((post_type)::text = ANY ((ARRAY['post'::character varying, 'story'::character varying, 'reel'::character varying, 'carousel'::character varying])::text[]))),
    CONSTRAINT platform_social_posts_status_check CHECK (((status)::text = ANY ((ARRAY['draft'::character varying, 'scheduled'::character varying, 'published'::character varying, 'failed'::character varying])::text[])))
);
CREATE TABLE af_global.pos_checkout_index (
    checkout_id uuid NOT NULL,
    schema_name text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone DEFAULT (now() + '00:15:00'::interval) NOT NULL
);
CREATE TABLE af_global.processed_webhook_events (
    event_id character varying(255) NOT NULL,
    event_type character varying(100),
    processed_at timestamp with time zone DEFAULT now(),
    provider text DEFAULT 'stripe'::text NOT NULL
);
CREATE TABLE af_global.refresh_tokens (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    user_id uuid NOT NULL,
    token_hash text NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    user_agent_hash character varying(64),
    ip_first_seen inet,
    last_refresh_at timestamp with time zone
);
CREATE TABLE af_global.square_pos_devices (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    organization_id uuid NOT NULL,
    device_id text NOT NULL,
    name text NOT NULL,
    device_type text,
    paired_at timestamp with time zone DEFAULT now() NOT NULL,
    last_seen_at timestamp with time zone,
    status text DEFAULT 'unknown'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE af_global.user_permissions (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    organization_id uuid NOT NULL,
    user_id uuid NOT NULL,
    permission_key character varying(100) NOT NULL,
    is_granted boolean DEFAULT true NOT NULL,
    granted_by uuid,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);
CREATE TABLE af_global.users (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    email character varying(255) NOT NULL,
    email_verified boolean DEFAULT false,
    password_hash text,
    first_name character varying(100),
    last_name character varying(100),
    phone character varying(20),
    avatar_url text,
    is_platform_admin boolean DEFAULT false,
    is_active boolean DEFAULT true,
    last_login_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    force_password_reset boolean DEFAULT false,
    totp_secret text,
    totp_enabled boolean DEFAULT false NOT NULL,
    backup_codes text[],
    utm_source character varying(255),
    utm_medium character varying(255),
    utm_campaign character varying(255),
    gclid character varying(512),
    fbclid character varying(512),
    force_password_change boolean DEFAULT false,
    phone_enc bytea
);

-- ── af_global constraints ───────────────────────────────────────────
ALTER TABLE ONLY af_global.ai_token_usage
    ADD CONSTRAINT ai_token_usage_pkey PRIMARY KEY (id);
ALTER TABLE ONLY af_global.api_key_routing
    ADD CONSTRAINT api_key_routing_pkey PRIMARY KEY (key_prefix);
ALTER TABLE ONLY af_global.audit_log
    ADD CONSTRAINT audit_log_pkey PRIMARY KEY (id);
ALTER TABLE ONLY af_global.coupons
    ADD CONSTRAINT coupons_code_key UNIQUE (code);
ALTER TABLE ONLY af_global.coupons
    ADD CONSTRAINT coupons_pkey PRIMARY KEY (id);
ALTER TABLE ONLY af_global.dead_letter_tasks
    ADD CONSTRAINT dead_letter_tasks_pkey PRIMARY KEY (id);
ALTER TABLE ONLY af_global.dead_letter_tasks
    ADD CONSTRAINT dead_letter_tasks_task_id_key UNIQUE (task_id);
ALTER TABLE ONLY af_global.email_suppressions
    ADD CONSTRAINT email_suppressions_pkey PRIMARY KEY (id);
ALTER TABLE ONLY af_global.feature_flags
    ADD CONSTRAINT feature_flags_organization_id_flag_key_key UNIQUE (organization_id, flag_key);
ALTER TABLE ONLY af_global.feature_flags
    ADD CONSTRAINT feature_flags_pkey PRIMARY KEY (id);
ALTER TABLE ONLY af_global.kiosk_devices
    ADD CONSTRAINT kiosk_devices_device_token_key UNIQUE (device_token);
ALTER TABLE ONLY af_global.kiosk_devices
    ADD CONSTRAINT kiosk_devices_pkey PRIMARY KEY (id);
ALTER TABLE ONLY af_global.membership_templates
    ADD CONSTRAINT membership_templates_pkey PRIMARY KEY (id);
ALTER TABLE ONLY af_global.membership_templates
    ADD CONSTRAINT membership_templates_template_key_key UNIQUE (template_key);
ALTER TABLE ONLY af_global.organization_integrations
    ADD CONSTRAINT organization_integrations_organization_id_integration_type_key UNIQUE (organization_id, integration_type);
ALTER TABLE ONLY af_global.organization_integrations
    ADD CONSTRAINT organization_integrations_pkey PRIMARY KEY (id);
ALTER TABLE ONLY af_global.organization_users
    ADD CONSTRAINT organization_users_organization_id_user_id_key UNIQUE (organization_id, user_id);
ALTER TABLE ONLY af_global.organization_users
    ADD CONSTRAINT organization_users_pkey PRIMARY KEY (id);
ALTER TABLE ONLY af_global.organizations
    ADD CONSTRAINT organizations_pkey PRIMARY KEY (id);
ALTER TABLE ONLY af_global.organizations
    ADD CONSTRAINT organizations_schema_name_key UNIQUE (schema_name);
ALTER TABLE ONLY af_global.organizations
    ADD CONSTRAINT organizations_slug_key UNIQUE (slug);
ALTER TABLE ONLY af_global.platform_ads_config
    ADD CONSTRAINT platform_ads_config_pkey PRIMARY KEY (id);
ALTER TABLE ONLY af_global.platform_ai_agent_log
    ADD CONSTRAINT platform_ai_agent_log_pkey PRIMARY KEY (id);
ALTER TABLE ONLY af_global.platform_announcements
    ADD CONSTRAINT platform_announcements_pkey PRIMARY KEY (id);
ALTER TABLE ONLY af_global.platform_backup_schedule
    ADD CONSTRAINT platform_backup_schedule_pkey PRIMARY KEY (id);
ALTER TABLE ONLY af_global.platform_backups
    ADD CONSTRAINT platform_backups_pkey PRIMARY KEY (id);
ALTER TABLE ONLY af_global.platform_config
    ADD CONSTRAINT platform_config_pkey PRIMARY KEY (id);
ALTER TABLE ONLY af_global.platform_email_accounts
    ADD CONSTRAINT platform_email_accounts_email_address_key UNIQUE (email_address);
ALTER TABLE ONLY af_global.platform_email_accounts
    ADD CONSTRAINT platform_email_accounts_pkey PRIMARY KEY (id);
ALTER TABLE ONLY af_global.platform_email_inbox
    ADD CONSTRAINT platform_email_inbox_pkey PRIMARY KEY (id);
ALTER TABLE ONLY af_global.platform_invoices
    ADD CONSTRAINT platform_invoices_organization_id_period_start_key UNIQUE (organization_id, period_start);
ALTER TABLE ONLY af_global.platform_invoices
    ADD CONSTRAINT platform_invoices_pkey PRIMARY KEY (id);
ALTER TABLE ONLY af_global.platform_invoices
    ADD CONSTRAINT platform_invoices_square_invoice_id_key UNIQUE (square_invoice_id);
ALTER TABLE ONLY af_global.platform_landing_pages
    ADD CONSTRAINT platform_landing_pages_pkey PRIMARY KEY (id);
ALTER TABLE ONLY af_global.platform_landing_pages
    ADD CONSTRAINT platform_landing_pages_slug_key UNIQUE (slug);
ALTER TABLE ONLY af_global.platform_metrics_daily
    ADD CONSTRAINT platform_metrics_daily_metric_date_key UNIQUE (metric_date);
ALTER TABLE ONLY af_global.platform_metrics_daily
    ADD CONSTRAINT platform_metrics_daily_pkey PRIMARY KEY (id);
ALTER TABLE ONLY af_global.platform_plans
    ADD CONSTRAINT platform_plans_pkey PRIMARY KEY (id);
ALTER TABLE ONLY af_global.platform_request_metrics
    ADD CONSTRAINT platform_request_metrics_pkey PRIMARY KEY (id);
ALTER TABLE ONLY af_global.platform_security_events
    ADD CONSTRAINT platform_security_events_pkey PRIMARY KEY (id);
ALTER TABLE ONLY af_global.platform_settings
    ADD CONSTRAINT platform_settings_pkey PRIMARY KEY (key);
ALTER TABLE ONLY af_global.platform_social_messages
    ADD CONSTRAINT platform_social_messages_pkey PRIMARY KEY (id);
ALTER TABLE ONLY af_global.platform_social_posts
    ADD CONSTRAINT platform_social_posts_pkey PRIMARY KEY (id);
ALTER TABLE ONLY af_global.pos_checkout_index
    ADD CONSTRAINT pos_checkout_index_pkey PRIMARY KEY (checkout_id);
ALTER TABLE ONLY af_global.processed_webhook_events
    ADD CONSTRAINT processed_webhook_events_pkey PRIMARY KEY (provider, event_id);
ALTER TABLE ONLY af_global.refresh_tokens
    ADD CONSTRAINT refresh_tokens_pkey PRIMARY KEY (id);
ALTER TABLE ONLY af_global.refresh_tokens
    ADD CONSTRAINT refresh_tokens_token_hash_key UNIQUE (token_hash);
ALTER TABLE ONLY af_global.square_pos_devices
    ADD CONSTRAINT square_pos_devices_organization_id_device_id_key UNIQUE (organization_id, device_id);
ALTER TABLE ONLY af_global.square_pos_devices
    ADD CONSTRAINT square_pos_devices_pkey PRIMARY KEY (id);
ALTER TABLE ONLY af_global.user_permissions
    ADD CONSTRAINT user_permissions_organization_id_user_id_permission_key_key UNIQUE (organization_id, user_id, permission_key);
ALTER TABLE ONLY af_global.user_permissions
    ADD CONSTRAINT user_permissions_pkey PRIMARY KEY (id);
ALTER TABLE ONLY af_global.users
    ADD CONSTRAINT users_email_key UNIQUE (email);
ALTER TABLE ONLY af_global.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);
ALTER TABLE ONLY af_global.ai_token_usage
    ADD CONSTRAINT ai_token_usage_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES af_global.organizations(id) ON DELETE CASCADE;
ALTER TABLE ONLY af_global.audit_log
    ADD CONSTRAINT audit_log_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES af_global.organizations(id);
ALTER TABLE ONLY af_global.audit_log
    ADD CONSTRAINT audit_log_user_id_fkey FOREIGN KEY (user_id) REFERENCES af_global.users(id);
ALTER TABLE ONLY af_global.feature_flags
    ADD CONSTRAINT feature_flags_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES af_global.organizations(id) ON DELETE CASCADE;
ALTER TABLE ONLY af_global.kiosk_devices
    ADD CONSTRAINT kiosk_devices_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES af_global.organizations(id) ON DELETE CASCADE;
ALTER TABLE ONLY af_global.kiosk_devices
    ADD CONSTRAINT kiosk_devices_registered_by_fkey FOREIGN KEY (registered_by) REFERENCES af_global.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY af_global.kiosk_devices
    ADD CONSTRAINT kiosk_devices_revoked_by_fkey FOREIGN KEY (revoked_by) REFERENCES af_global.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY af_global.organization_integrations
    ADD CONSTRAINT organization_integrations_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES af_global.organizations(id);
ALTER TABLE ONLY af_global.organization_users
    ADD CONSTRAINT organization_users_invited_by_fkey FOREIGN KEY (invited_by) REFERENCES af_global.users(id);
ALTER TABLE ONLY af_global.organization_users
    ADD CONSTRAINT organization_users_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES af_global.organizations(id) ON DELETE CASCADE;
ALTER TABLE ONLY af_global.organization_users
    ADD CONSTRAINT organization_users_user_id_fkey FOREIGN KEY (user_id) REFERENCES af_global.users(id) ON DELETE CASCADE;
ALTER TABLE ONLY af_global.organizations
    ADD CONSTRAINT organizations_square_pos_default_device_id_fkey FOREIGN KEY (square_pos_default_device_id) REFERENCES af_global.square_pos_devices(id) ON DELETE SET NULL;
ALTER TABLE ONLY af_global.platform_email_inbox
    ADD CONSTRAINT platform_email_inbox_account_id_fkey FOREIGN KEY (account_id) REFERENCES af_global.platform_email_accounts(id) ON DELETE SET NULL;
ALTER TABLE ONLY af_global.platform_invoices
    ADD CONSTRAINT platform_invoices_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES af_global.organizations(id) ON DELETE CASCADE;
ALTER TABLE ONLY af_global.platform_social_messages
    ADD CONSTRAINT platform_social_messages_post_id_fkey FOREIGN KEY (post_id) REFERENCES af_global.platform_social_posts(id) ON DELETE SET NULL;
ALTER TABLE ONLY af_global.refresh_tokens
    ADD CONSTRAINT refresh_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES af_global.users(id) ON DELETE CASCADE;
ALTER TABLE ONLY af_global.square_pos_devices
    ADD CONSTRAINT square_pos_devices_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES af_global.organizations(id) ON DELETE CASCADE;
ALTER TABLE ONLY af_global.user_permissions
    ADD CONSTRAINT user_permissions_granted_by_fkey FOREIGN KEY (granted_by) REFERENCES af_global.users(id);
ALTER TABLE ONLY af_global.user_permissions
    ADD CONSTRAINT user_permissions_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES af_global.organizations(id) ON DELETE CASCADE;
ALTER TABLE ONLY af_global.user_permissions
    ADD CONSTRAINT user_permissions_user_id_fkey FOREIGN KEY (user_id) REFERENCES af_global.users(id) ON DELETE CASCADE;

-- ── af_global indexes ───────────────────────────────────────────────
CREATE UNIQUE INDEX email_suppressions_email_uidx ON af_global.email_suppressions USING btree (lower(email));
CREATE INDEX idx_ai_agent_log_created ON af_global.platform_ai_agent_log USING btree (created_at DESC);
CREATE INDEX idx_ai_agent_log_type ON af_global.platform_ai_agent_log USING btree (agent_type);
CREATE INDEX idx_ai_usage_org ON af_global.ai_token_usage USING btree (organization_id, created_at DESC);
CREATE INDEX idx_ai_usage_service ON af_global.ai_token_usage USING btree (service_name, created_at DESC);
CREATE INDEX idx_announcements_active ON af_global.platform_announcements USING btree (is_active);
CREATE INDEX idx_audit_log_action ON af_global.audit_log USING btree (action);
CREATE INDEX idx_audit_log_created ON af_global.audit_log USING btree (created_at DESC);
CREATE INDEX idx_audit_log_org ON af_global.audit_log USING btree (organization_id);
CREATE INDEX idx_audit_log_resource ON af_global.audit_log USING btree (resource_type, resource_id);
CREATE INDEX idx_audit_log_user ON af_global.audit_log USING btree (user_id);
CREATE INDEX idx_backups_created ON af_global.platform_backups USING btree (created_at DESC);
CREATE INDEX idx_backups_status ON af_global.platform_backups USING btree (status);
CREATE INDEX idx_backups_type ON af_global.platform_backups USING btree (backup_type);
CREATE INDEX idx_coupons_code ON af_global.coupons USING btree (code);
CREATE INDEX idx_dlt_failed_at ON af_global.dead_letter_tasks USING btree (failed_at DESC);
CREATE INDEX idx_dlt_resolution ON af_global.dead_letter_tasks USING btree (resolution);
CREATE INDEX idx_dlt_task_name ON af_global.dead_letter_tasks USING btree (task_name);
CREATE INDEX idx_email_inbox_account ON af_global.platform_email_inbox USING btree (account_id);
CREATE INDEX idx_email_inbox_created ON af_global.platform_email_inbox USING btree (created_at DESC);
CREATE INDEX idx_email_inbox_mailbox ON af_global.platform_email_inbox USING btree (mailbox);
CREATE UNIQUE INDEX idx_email_inbox_message_id ON af_global.platform_email_inbox USING btree (message_id) WHERE (message_id IS NOT NULL);
CREATE INDEX idx_email_inbox_status ON af_global.platform_email_inbox USING btree (ai_status);
CREATE INDEX idx_feature_flags_key ON af_global.feature_flags USING btree (flag_key);
CREATE INDEX idx_feature_flags_org ON af_global.feature_flags USING btree (organization_id);
CREATE INDEX idx_kiosk_devices_fingerprint ON af_global.kiosk_devices USING btree (organization_id, ip_hash, user_agent_hash) WHERE (is_active = true);
CREATE INDEX idx_kiosk_devices_org_active ON af_global.kiosk_devices USING btree (organization_id, is_active) WHERE (is_active = true);
CREATE INDEX idx_landing_pages_slug ON af_global.platform_landing_pages USING btree (slug);
CREATE INDEX idx_landing_pages_status ON af_global.platform_landing_pages USING btree (status);
CREATE INDEX idx_metrics_date ON af_global.platform_metrics_daily USING btree (metric_date);
CREATE INDEX idx_org_integrations_org ON af_global.organization_integrations USING btree (organization_id);
CREATE INDEX idx_org_integrations_type ON af_global.organization_integrations USING btree (integration_type);
CREATE INDEX idx_org_users_org ON af_global.organization_users USING btree (organization_id);
CREATE INDEX idx_org_users_user ON af_global.organization_users USING btree (user_id);
CREATE INDEX idx_organizations_billing_provider ON af_global.organizations USING btree (billing_provider) WHERE (billing_provider = 'square'::text);
CREATE INDEX idx_organizations_square_merchant ON af_global.organizations USING btree (square_merchant_id) WHERE (square_merchant_id IS NOT NULL);
CREATE INDEX idx_platform_invoices_org ON af_global.platform_invoices USING btree (organization_id, period_start DESC);
CREATE INDEX idx_platform_invoices_status ON af_global.platform_invoices USING btree (status) WHERE (status = ANY (ARRAY['pending'::text, 'sent'::text, 'failed'::text]));
CREATE INDEX idx_refresh_tokens_user ON af_global.refresh_tokens USING btree (user_id);
CREATE INDEX idx_request_metrics_created ON af_global.platform_request_metrics USING btree (created_at DESC);
CREATE UNIQUE INDEX idx_request_metrics_period ON af_global.platform_request_metrics USING btree (period_start);
CREATE INDEX idx_security_events_created ON af_global.platform_security_events USING btree (created_at DESC);
CREATE INDEX idx_security_events_severity ON af_global.platform_security_events USING btree (severity);
CREATE INDEX idx_security_events_type ON af_global.platform_security_events USING btree (event_type);
CREATE INDEX idx_security_events_unacked ON af_global.platform_security_events USING btree (acknowledged) WHERE (acknowledged = false);
CREATE INDEX idx_social_messages_platform ON af_global.platform_social_messages USING btree (platform);
CREATE INDEX idx_social_messages_status ON af_global.platform_social_messages USING btree (ai_status);
CREATE INDEX idx_social_posts_platform ON af_global.platform_social_posts USING btree (platform);
CREATE INDEX idx_social_posts_scheduled ON af_global.platform_social_posts USING btree (scheduled_at) WHERE ((status)::text = 'scheduled'::text);
CREATE INDEX idx_social_posts_status ON af_global.platform_social_posts USING btree (status);
CREATE INDEX idx_user_permissions_org_user ON af_global.user_permissions USING btree (organization_id, user_id);
CREATE INDEX idx_user_permissions_org_user_granted ON af_global.user_permissions USING btree (organization_id, user_id) WHERE (is_granted = true);
CREATE INDEX idx_users_email ON af_global.users USING btree (email);
CREATE INDEX idx_users_utm_campaign ON af_global.users USING btree (utm_campaign) WHERE (utm_campaign IS NOT NULL);
CREATE INDEX idx_users_utm_source ON af_global.users USING btree (utm_source) WHERE (utm_source IS NOT NULL);
CREATE INDEX idx_webhook_events_processed_at ON af_global.processed_webhook_events USING btree (processed_at DESC);
CREATE INDEX pos_checkout_index_expires_at_idx ON af_global.pos_checkout_index USING btree (expires_at);
CREATE INDEX square_pos_devices_org_idx ON af_global.square_pos_devices USING btree (organization_id);

-- ── af_global triggers ──────────────────────────────────────────────
CREATE TRIGGER organizations_updated_at BEFORE UPDATE ON af_global.organizations FOR EACH ROW EXECUTE FUNCTION af_global.update_updated_at();
CREATE TRIGGER trg_platform_ads_config_updated_at BEFORE UPDATE ON af_global.platform_ads_config FOR EACH ROW EXECUTE FUNCTION af_global.update_updated_at();
CREATE TRIGGER trg_platform_backup_schedule_updated_at BEFORE UPDATE ON af_global.platform_backup_schedule FOR EACH ROW EXECUTE FUNCTION af_global.update_updated_at();
CREATE TRIGGER trg_platform_backups_updated_at BEFORE UPDATE ON af_global.platform_backups FOR EACH ROW EXECUTE FUNCTION af_global.update_updated_at();
CREATE TRIGGER trg_platform_config_updated_at BEFORE UPDATE ON af_global.platform_config FOR EACH ROW EXECUTE FUNCTION af_global.update_updated_at();
CREATE TRIGGER trg_platform_email_accounts_updated_at BEFORE UPDATE ON af_global.platform_email_accounts FOR EACH ROW EXECUTE FUNCTION af_global.update_updated_at();
CREATE TRIGGER trg_platform_email_inbox_updated_at BEFORE UPDATE ON af_global.platform_email_inbox FOR EACH ROW EXECUTE FUNCTION af_global.update_updated_at();
CREATE TRIGGER trg_platform_landing_pages_updated_at BEFORE UPDATE ON af_global.platform_landing_pages FOR EACH ROW EXECUTE FUNCTION af_global.update_updated_at();
CREATE TRIGGER trg_platform_social_messages_updated_at BEFORE UPDATE ON af_global.platform_social_messages FOR EACH ROW EXECUTE FUNCTION af_global.update_updated_at();
CREATE TRIGGER trg_platform_social_posts_updated_at BEFORE UPDATE ON af_global.platform_social_posts FOR EACH ROW EXECUTE FUNCTION af_global.update_updated_at();
CREATE TRIGGER user_permissions_updated_at BEFORE UPDATE ON af_global.user_permissions FOR EACH ROW EXECUTE FUNCTION af_global.update_updated_at();
CREATE TRIGGER users_updated_at BEFORE UPDATE ON af_global.users FOR EACH ROW EXECUTE FUNCTION af_global.update_updated_at();

-- ── config seed ─────────────────────────────────────────────────────
INSERT INTO af_global.membership_templates (id, template_key, name, description, type, access_scope, suggested_price_cents, billing_period, class_count, duration_days, auto_renew, freeze_allowed, sort_order, created_at) VALUES ('35e671da-fdd7-4c7b-8790-f19d55841035', 'unlimited_in_studio_monthly', 'Unlimited In-Studio (Monthly)', 'Unlimited in-person classes at the studio', 'unlimited', 'in_studio', 14900, 'monthly', NULL, NULL, true, true, 1, '2026-02-27 21:33:21.8733+00');
INSERT INTO af_global.membership_templates (id, template_key, name, description, type, access_scope, suggested_price_cents, billing_period, class_count, duration_days, auto_renew, freeze_allowed, sort_order, created_at) VALUES ('332b035c-275e-4195-bd87-1d87d2cfbc47', 'unlimited_in_studio_yearly', 'Unlimited In-Studio (Yearly)', 'Unlimited in-person classes — annual plan with savings', 'unlimited', 'in_studio', 149000, 'yearly', NULL, NULL, true, true, 2, '2026-02-27 21:33:21.8733+00');
INSERT INTO af_global.membership_templates (id, template_key, name, description, type, access_scope, suggested_price_cents, billing_period, class_count, duration_days, auto_renew, freeze_allowed, sort_order, created_at) VALUES ('c32fe8ef-7510-43cb-a36e-80c2f48aa9b2', 'unlimited_online_monthly', 'Unlimited Online (Monthly)', 'Unlimited livestream and on-demand video access', 'unlimited', 'online', 9900, 'monthly', NULL, NULL, true, true, 3, '2026-02-27 21:33:21.8733+00');
INSERT INTO af_global.membership_templates (id, template_key, name, description, type, access_scope, suggested_price_cents, billing_period, class_count, duration_days, auto_renew, freeze_allowed, sort_order, created_at) VALUES ('d6e5ecfd-89c1-4b68-96c9-a7943f4e25dd', 'unlimited_online_yearly', 'Unlimited Online (Yearly)', 'Unlimited online access — annual plan with savings', 'unlimited', 'online', 99000, 'yearly', NULL, NULL, true, true, 4, '2026-02-27 21:33:21.8733+00');
INSERT INTO af_global.membership_templates (id, template_key, name, description, type, access_scope, suggested_price_cents, billing_period, class_count, duration_days, auto_renew, freeze_allowed, sort_order, created_at) VALUES ('318948aa-e4b3-49bc-aae9-30d185763ae4', 'unlimited_all_access_monthly', 'Unlimited All-Access (Monthly)', 'Full access: in-studio classes plus livestream and on-demand video', 'unlimited', 'all_access', 19900, 'monthly', NULL, NULL, true, true, 5, '2026-02-27 21:33:21.8733+00');
INSERT INTO af_global.membership_templates (id, template_key, name, description, type, access_scope, suggested_price_cents, billing_period, class_count, duration_days, auto_renew, freeze_allowed, sort_order, created_at) VALUES ('fe018bdb-735b-40fc-a1df-8294ab38500a', 'unlimited_all_access_yearly', 'Unlimited All-Access (Yearly)', 'Full all-access — annual plan with savings', 'unlimited', 'all_access', 199000, 'yearly', NULL, NULL, true, true, 6, '2026-02-27 21:33:21.8733+00');
INSERT INTO af_global.membership_templates (id, template_key, name, description, type, access_scope, suggested_price_cents, billing_period, class_count, duration_days, auto_renew, freeze_allowed, sort_order, created_at) VALUES ('96a47d3b-34f0-4e86-a6a1-3dbc0fcb75be', 'class_pack_5', '5-Class Pack', 'Bundle of 5 classes, use at your own pace', 'class_pack', 'in_studio', 8500, 'one_time', 5, 90, false, false, 10, '2026-02-27 21:33:21.8733+00');
INSERT INTO af_global.membership_templates (id, template_key, name, description, type, access_scope, suggested_price_cents, billing_period, class_count, duration_days, auto_renew, freeze_allowed, sort_order, created_at) VALUES ('1e1aa3b2-9501-4dba-a13e-f230b8213a62', 'class_pack_10', '10-Class Pack', 'Bundle of 10 classes, great value', 'class_pack', 'in_studio', 15000, 'one_time', 10, 180, false, false, 11, '2026-02-27 21:33:21.8733+00');
INSERT INTO af_global.membership_templates (id, template_key, name, description, type, access_scope, suggested_price_cents, billing_period, class_count, duration_days, auto_renew, freeze_allowed, sort_order, created_at) VALUES ('51c29280-020d-40dd-a201-8929b76401d5', 'class_pack_20', '20-Class Pack', 'Bundle of 20 classes, best per-class rate', 'class_pack', 'in_studio', 26000, 'one_time', 20, 365, false, false, 12, '2026-02-27 21:33:21.8733+00');
INSERT INTO af_global.membership_templates (id, template_key, name, description, type, access_scope, suggested_price_cents, billing_period, class_count, duration_days, auto_renew, freeze_allowed, sort_order, created_at) VALUES ('e948bf11-258b-49f0-bee4-f435912ca39c', 'single_class', 'Single Class Drop-In', 'One class visit, no commitment', 'single_class', 'in_studio', 2500, 'one_time', 1, NULL, false, false, 20, '2026-02-27 21:33:21.8733+00');
INSERT INTO af_global.membership_templates (id, template_key, name, description, type, access_scope, suggested_price_cents, billing_period, class_count, duration_days, auto_renew, freeze_allowed, sort_order, created_at) VALUES ('9dabbed2-d039-41b6-b010-781bc00ea6d6', 'intro_30', 'New Student 30-Day Intro', '30 days of unlimited classes for new students', 'intro_offer', 'all_access', 4900, 'one_time', NULL, 30, false, false, 30, '2026-02-27 21:33:21.8733+00');
INSERT INTO af_global.platform_config (id, sendgrid_api_key_enc, sendgrid_from_email, sendgrid_from_name, sendgrid_inbound_webhook_secret_enc, platform_admin_alert_email, support_escalation_email, google_ads_developer_token_enc, google_ads_login_customer_id, google_client_id, google_client_secret_enc, meta_app_id, meta_app_secret_enc, meta_page_access_token_enc, meta_page_id, instagram_business_account_id, created_at, updated_at) VALUES ('af90fed4-2266-4f98-9423-b6b2e1bebf07', '\xc30d0407030259b53d8473d85f9d79d2760189d2c34f6e1c197b362338adf76c5df89b643b849f7a6a3f2f985bc44777b245e4968aece57281f3f80d06c14965d90c918ed55f9a9de7cbd901e1d3c62cf881c129a9097f2a3598a39e56a3b766894f66db2af469d71acb6235f79eb4c61799d78871a9932e079de53313a537fcc595efeae8294a', 'hello@auraflow.fit', 'AuraFlow', NULL, 'support@auraflow.fit', 'support@auraflow.fit', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-03-03 05:34:24.299934+00', '2026-03-26 04:29:30.669053+00');
INSERT INTO af_global.platform_plans (id, name, price_cents, price_display, "interval", tagline, price_note, additional_location_cents, contact_sales, popular, features, limits, sort_order, is_active, created_at, updated_at) VALUES ('enterprise', 'Enterprise', 0, 'Call Us', 'month', 'For franchise and large studio networks', NULL, NULL, true, false, '["Everything in Scale", "Unlimited members", "Unlimited locations", "Custom integrations", "Dedicated account manager", "Custom onboarding", "SLA guarantee"]', '{"members": 999999, "locations": 999999, "instructors": 999999}', 4, true, '2026-03-25 05:56:19.386784+00', '2026-03-25 05:56:19.386784+00');
INSERT INTO af_global.platform_plans (id, name, price_cents, price_display, "interval", tagline, price_note, additional_location_cents, contact_sales, popular, features, limits, sort_order, is_active, created_at, updated_at) VALUES ('scale', 'Scale', 19900, '$199', 'month', 'For multi-location studios', '+$100/mo per additional location', 0, false, false, '["Everything in Growth", "AI churn prediction", "AI autonomous resolution", "Multi-location support", "API access", "Advanced analytics", "Priority support"]', '{"members": 5000, "locations": 10, "instructors": 50}', 3, true, '2026-03-25 05:56:19.386784+00', '2026-03-29 03:16:29.983683+00');
INSERT INTO af_global.platform_plans (id, name, price_cents, price_display, "interval", tagline, price_note, additional_location_cents, contact_sales, popular, features, limits, sort_order, is_active, created_at, updated_at) VALUES ('starter', 'Starter', 7900, '$79', 'month', 'For solo instructors and new studios', NULL, NULL, false, false, '["Group class scheduling", "Private session booking", "Zoom integration", "YouTube video embeds", "On-demand video library", "Mux video hosting", "POS & retail", "Gift cards"]', '{"members": 200, "locations": 1, "instructors": 3}', 1, true, '2026-03-25 05:56:19.386784+00', '2026-03-29 03:16:40.842425+00');
INSERT INTO af_global.platform_plans (id, name, price_cents, price_display, "interval", tagline, price_note, additional_location_cents, contact_sales, popular, features, limits, sort_order, is_active, created_at, updated_at) VALUES ('growth', 'Growth', 12900, '$129', 'month', 'For growing studios with marketing needs', NULL, NULL, false, true, '["Everything in Starter", "Workshops & teacher training", "ClassPass integration", "EMR integration (FHIR R4)", "Email campaigns", "SMS messaging", "AI newsletter generator"]', '{"members": 1000, "locations": 1, "instructors": 10}', 2, true, '2026-03-25 05:56:19.386784+00', '2026-03-29 03:16:43.314446+00');
INSERT INTO af_global.platform_settings (key, value, description, updated_at, updated_by) VALUES ('ai_token_rate_cents_per_1k', '3.0', 'Cost per 1,000 AI tokens in cents (after free tier)', '2026-03-05 18:37:12.933623+00', NULL);
INSERT INTO af_global.platform_settings (key, value, description, updated_at, updated_by) VALUES ('ai_token_billing_enabled', 'true', 'Whether AI token billing is active', '2026-03-05 18:37:12.933623+00', NULL);
INSERT INTO af_global.platform_settings (key, value, description, updated_at, updated_by) VALUES ('ai_token_stripe_meter_id', 'null', 'Stripe Billing Meter ID for ai_tokens', '2026-03-05 18:37:12.933623+00', NULL);
INSERT INTO af_global.platform_settings (key, value, description, updated_at, updated_by) VALUES ('ai_token_stripe_price_id', 'null', 'Stripe Price ID for metered AI usage', '2026-03-05 18:37:12.933623+00', NULL);
INSERT INTO af_global.platform_settings (key, value, description, updated_at, updated_by) VALUES ('ai_token_free_tier', '1000000', 'Free tokens per organization per month', '2026-03-16 05:50:44.209049+00', NULL);

-- ── demo tenant + login ─────────────────────────────────────────────
DO $demo$
DECLARE v_org UUID := public.uuid_generate_v4();
        v_user UUID := public.uuid_generate_v4();
BEGIN
    INSERT INTO af_global.users (id, email, first_name, last_name, password_hash, is_active, email_verified)
    VALUES (v_user, 'owner@demo.example.com', 'Demo', 'Owner', crypt('demo1234', gen_salt('bf', 12)), TRUE, TRUE)
    ON CONFLICT (email) DO NOTHING;
    INSERT INTO af_global.organizations (id, slug, name, schema_name, status)
    VALUES (v_org, 'demo', 'Demo Studio', 'af_tenant_demo', 'active')
    ON CONFLICT (slug) DO NOTHING;
    INSERT INTO af_global.organization_users (organization_id, user_id, role)
    VALUES (v_org, v_user, 'owner') ON CONFLICT DO NOTHING;
    PERFORM af_global.provision_tenant_schema('af_tenant_demo', v_org);
END $demo$;
