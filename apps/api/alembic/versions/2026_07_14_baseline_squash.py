"""baseline — complete AuraFlow open-core schema (squashed)

Single squashed baseline replacing the prior 71-migration chain. The full schema
also ships as infra/docker/postgres/init.sql (executed by the Postgres entrypoint
for docker installs, which then run `alembic stamp head`). This migration embeds
the same schema so `alembic upgrade head` builds it from an empty database too.

Revision ID: baseline_squash_2026_07
Revises:
Create Date: 2026-07-14
"""
from alembic import op

revision = "baseline_squash_2026_07"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA_SQL = r"""-- ============================================================================
-- AuraFlow (open core) — complete baseline schema.
-- Single-file install: the Postgres entrypoint runs this, then `alembic stamp head`.
-- Regenerated 2026-07-14 from the full migration chain (squashed to one baseline).
-- Includes a demo tenant "Sunrise Yoga Studio" (login owner@sunrise-yoga.example.com / demo1234).
-- ============================================================================
--
-- PostgreSQL database dump
--


-- Dumped from database version 16.13
-- Dumped by pg_dump version 16.13

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: af_global; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA af_global;


--
-- Name: af_tenant_sunrise_yoga; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA af_tenant_sunrise_yoga;


--
-- Name: btree_gin; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS btree_gin WITH SCHEMA public;


--
-- Name: EXTENSION btree_gin; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION btree_gin IS 'support for indexing common datatypes in GIN';


--
-- Name: pg_trgm; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;


--
-- Name: EXTENSION pg_trgm; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';


--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


--
-- Name: uuid-ossp; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;


--
-- Name: EXTENSION "uuid-ossp"; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION "uuid-ossp" IS 'generate universally unique identifiers (UUIDs)';


--
-- Name: add_accounting_income_link_to_schema(text); Type: FUNCTION; Schema: af_global; Owner: -
--

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


--
-- Name: add_accounting_tables_to_schema(text); Type: FUNCTION; Schema: af_global; Owner: -
--

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


--
-- Name: add_acct_owner_draws_to_schema(text); Type: FUNCTION; Schema: af_global; Owner: -
--

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


--
-- Name: add_acct_vendor_rules_to_schema(text); Type: FUNCTION; Schema: af_global; Owner: -
--

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


--
-- Name: add_api_keys_table(text); Type: FUNCTION; Schema: af_global; Owner: -
--

CREATE FUNCTION af_global.add_api_keys_table(p_schema_name text) RETURNS void
    LANGUAGE plpgsql
    AS $$
        BEGIN
            EXECUTE format('
                CREATE TABLE IF NOT EXISTS %I.api_keys (
                    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    name           TEXT NOT NULL,
                    key_hash       TEXT NOT NULL,
                    key_prefix     TEXT NOT NULL,
                    scopes         TEXT[] DEFAULT ''{}''::TEXT[],
                    rate_limit_rpm INTEGER DEFAULT 60,
                    is_active      BOOLEAN DEFAULT TRUE,
                    last_used_at   TIMESTAMPTZ,
                    expires_at     TIMESTAMPTZ,
                    created_by     UUID,
                    created_at     TIMESTAMPTZ DEFAULT NOW(),
                    revoked_at     TIMESTAMPTZ
                )', p_schema_name);

            EXECUTE format('
                CREATE UNIQUE INDEX IF NOT EXISTS idx_api_keys_hash_active
                ON %I.api_keys (key_hash) WHERE is_active = TRUE
            ', p_schema_name);

            EXECUTE format('
                CREATE INDEX IF NOT EXISTS idx_api_keys_prefix
                ON %I.api_keys (key_prefix)
            ', p_schema_name);
        END;
        $$;


--
-- Name: add_de34_filings_to_schema(text); Type: FUNCTION; Schema: af_global; Owner: -
--

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


--
-- Name: add_employer_profile_to_schema(text); Type: FUNCTION; Schema: af_global; Owner: -
--

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


--
-- Name: add_emr_tables_to_schema(text); Type: FUNCTION; Schema: af_global; Owner: -
--

CREATE FUNCTION af_global.add_emr_tables_to_schema(p_schema_name text) RETURNS void
    LANGUAGE plpgsql
    AS $$
        BEGIN
            EXECUTE format('CREATE TABLE IF NOT EXISTS %I.emr_patient_map (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(), member_id UUID NOT NULL,
                emr_patient_id VARCHAR(255) NOT NULL, emr_system VARCHAR(50) NOT NULL,
                last_synced_at TIMESTAMPTZ, sync_direction VARCHAR(10) NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW())', p_schema_name);
            EXECUTE format('CREATE UNIQUE INDEX IF NOT EXISTS idx_emr_patient_map_member ON %I.emr_patient_map (member_id)', p_schema_name);
            EXECUTE format('CREATE UNIQUE INDEX IF NOT EXISTS idx_emr_patient_map_emr ON %I.emr_patient_map (emr_patient_id, emr_system)', p_schema_name);
            EXECUTE format('CREATE TABLE IF NOT EXISTS %I.emr_encounter_log (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(), booking_id UUID NOT NULL, member_id UUID NOT NULL,
                emr_encounter_id VARCHAR(255), encounter_type VARCHAR(50) NOT NULL, class_title VARCHAR(255),
                instructor_name VARCHAR(255), session_start TIMESTAMPTZ, session_end TIMESTAMPTZ,
                status VARCHAR(20) DEFAULT ''pending'', error_message TEXT, created_at TIMESTAMPTZ DEFAULT NOW())', p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_emr_encounter_log_booking ON %I.emr_encounter_log (booking_id)', p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_emr_encounter_log_status ON %I.emr_encounter_log (status) WHERE status = ''failed''', p_schema_name);
            EXECUTE format('CREATE TABLE IF NOT EXISTS %I.emr_sync_log (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(), direction VARCHAR(10) NOT NULL, resource_type VARCHAR(50) NOT NULL,
                operation VARCHAR(20) NOT NULL, emr_resource_id VARCHAR(255), auraflow_resource_id UUID,
                status VARCHAR(20) NOT NULL, error_message TEXT, created_at TIMESTAMPTZ DEFAULT NOW())', p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_emr_sync_log_created ON %I.emr_sync_log (created_at DESC)', p_schema_name);
        END;
        $$;


--
-- Name: add_hiring_tables_to_schema(text); Type: FUNCTION; Schema: af_global; Owner: -
--

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


--
-- Name: add_onboarding_tables_to_schema(text); Type: FUNCTION; Schema: af_global; Owner: -
--

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


--
-- Name: add_online_membership_trial_fields(text); Type: FUNCTION; Schema: af_global; Owner: -
--

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


--
-- Name: provision_tenant_schema(text, uuid); Type: FUNCTION; Schema: af_global; Owner: -
--

CREATE FUNCTION af_global.provision_tenant_schema(p_schema_name text, p_org_id uuid) RETURNS void
    LANGUAGE plpgsql
    AS $$
        BEGIN
            EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I', p_schema_name);
            EXECUTE format('SET search_path TO %I, public', p_schema_name);

            -- ── Studios ──────────────────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.studios (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                organization_id UUID NOT NULL DEFAULT %L,
                name            VARCHAR(255) NOT NULL,
                slug            VARCHAR(100),
                address_line1   VARCHAR(255),
                address_line2   VARCHAR(255),
                city            VARCHAR(100),
                state           VARCHAR(50),
                postal_code     VARCHAR(20),
                country         VARCHAR(3) DEFAULT ''US'',
                phone           VARCHAR(20),
                email           VARCHAR(255),
                timezone        VARCHAR(50) DEFAULT ''America/Los_Angeles'',
                is_active       BOOLEAN DEFAULT TRUE,
                is_virtual      BOOLEAN DEFAULT FALSE,
                settings        JSONB,
                cancellation_policy_hours INTEGER DEFAULT 12,
                late_cancel_fee_cents INTEGER DEFAULT 0,
                booking_window_days INTEGER DEFAULT 14,
                allow_guest_booking BOOLEAN DEFAULT FALSE,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(organization_id, slug)
            )', p_schema_name, p_org_id);

            -- ── Rooms (enhanced) ────────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.rooms (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                studio_id       UUID NOT NULL,
                name            VARCHAR(100) NOT NULL,
                capacity        INTEGER,
                color           VARCHAR(7),
                sort_order      INTEGER DEFAULT 0,
                is_active       BOOLEAN DEFAULT TRUE,
                description     TEXT,
                room_type       VARCHAR(30) DEFAULT ''studio''
                                    CHECK (room_type IN (''studio'',''meeting'',''outdoor'',''virtual'',''therapy'',''storage'')),
                amenities       JSONB DEFAULT ''[]''::jsonb,
                photo_url       TEXT,
                hourly_rate_cents INTEGER,
                max_classes_per_day INTEGER,
                floor_area_sqft INTEGER,
                setup_instructions TEXT,
                is_bookable     BOOLEAN DEFAULT TRUE,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Instructors ──────────────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.instructors (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                user_id         UUID,
                display_name    VARCHAR(255) NOT NULL,
                bio             TEXT,
                photo_url       TEXT,
                specialties     TEXT[] DEFAULT ''{}'',
                certifications  TEXT[] DEFAULT ''{}'',
                zoom_user_id    VARCHAR(100),
                email           VARCHAR(255),
                phone           VARCHAR(20),
                pay_rate_cents  INTEGER,
                pay_type        VARCHAR(20) DEFAULT ''per_class'',
                tax_classification VARCHAR(20) DEFAULT ''1099'',
                color           VARCHAR(7) DEFAULT ''#4F46E5'',
                sort_order      INTEGER DEFAULT 0,
                is_active       BOOLEAN DEFAULT TRUE,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Class Types ──────────────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.class_types (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                studio_id       UUID NOT NULL,
                name            VARCHAR(255) NOT NULL,
                description     TEXT,
                duration_minutes INTEGER DEFAULT 60,
                color           VARCHAR(7) DEFAULT ''#6366F1'',
                capacity        INTEGER,
                level           VARCHAR(30) DEFAULT ''all_levels'',
                tags            TEXT[] DEFAULT ''{}'',
                category        VARCHAR(100),
                image_url       TEXT,
                is_active       BOOLEAN DEFAULT TRUE,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Class Series ─────────────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.class_series (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                studio_id       UUID NOT NULL,
                class_type_id   UUID NOT NULL,
                instructor_id   UUID,
                room_id         UUID,
                title           VARCHAR(255),
                rrule           TEXT NOT NULL,
                start_time      TIME NOT NULL,
                duration_minutes INTEGER NOT NULL DEFAULT 60,
                capacity        INTEGER,
                waitlist_capacity INTEGER DEFAULT 10,
                effective_from  DATE NOT NULL,
                effective_until DATE,
                timezone        VARCHAR(50) DEFAULT ''America/Los_Angeles'',
                is_virtual      BOOLEAN DEFAULT FALSE,
                auto_record     BOOLEAN DEFAULT FALSE,
                is_active       BOOLEAN DEFAULT TRUE,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Class Sessions ───────────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.class_sessions (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                studio_id       UUID,
                class_type_id   UUID NOT NULL,
                instructor_id   UUID,
                room_id         UUID,
                series_id       UUID,
                substitute_instructor_id UUID,
                title           VARCHAR(255) NOT NULL,
                description     TEXT,
                starts_at       TIMESTAMPTZ NOT NULL,
                ends_at         TIMESTAMPTZ NOT NULL,
                timezone        VARCHAR(50) DEFAULT ''America/Los_Angeles'',
                capacity        INTEGER NOT NULL DEFAULT 20,
                booked_count    INTEGER DEFAULT 0,
                waitlist_count  INTEGER DEFAULT 0,
                waitlist_capacity INTEGER DEFAULT 10,
                status          VARCHAR(20) DEFAULT ''scheduled'',
                color           VARCHAR(7),
                notes           TEXT,
                is_virtual      BOOLEAN DEFAULT FALSE,
                zoom_meeting_id VARCHAR(100),
                zoom_join_url   TEXT,
                zoom_password   VARCHAR(100),
                auto_record     BOOLEAN DEFAULT FALSE,
                recording_status VARCHAR(30) DEFAULT ''none''
                                    CHECK (recording_status IN (''none'',''recording'',''processing'',''ready'',''published'',''failed'')),
                recording_url   TEXT,
                video_id        UUID,
                cancellation_reason TEXT,
                recurrence_id   UUID,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Members ──────────────────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.members (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                user_id         UUID,
                first_name      VARCHAR(100) NOT NULL,
                last_name       VARCHAR(100) NOT NULL,
                email           VARCHAR(255),
                phone           VARCHAR(20),
                date_of_birth   DATE,
                gender          VARCHAR(20),
                address_line1   VARCHAR(255),
                city            VARCHAR(100),
                state           VARCHAR(50),
                postal_code     VARCHAR(20),
                emergency_contact_name  VARCHAR(255),
                emergency_contact_phone VARCHAR(20),
                notes           TEXT,
                tags            TEXT[] DEFAULT ''{}'',
                stripe_customer_id VARCHAR(100),
                photo_url       TEXT,
                source          VARCHAR(50) DEFAULT ''manual'',
                referral_source VARCHAR(255),
                last_visit_at   TIMESTAMPTZ,
                total_visits    INTEGER DEFAULT 0,
                lifetime_revenue_cents INTEGER DEFAULT 0,
                is_active       BOOLEAN DEFAULT TRUE,
                member_number   VARCHAR(20) UNIQUE,
                joined_at       TIMESTAMPTZ DEFAULT NOW(),
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Member Notes ─────────────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.member_notes (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                member_id       UUID NOT NULL,
                author_id       UUID,
                note            TEXT NOT NULL,
                is_pinned       BOOLEAN DEFAULT FALSE,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Member Health Data ───────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.member_health_data (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                member_id       UUID NOT NULL UNIQUE,
                health_data_encrypted   BYTEA,
                injuries_encrypted      BYTEA,
                conditions_encrypted    BYTEA,
                medications_encrypted   BYTEA,
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Bookings ─────────────────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.bookings (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                member_id       UUID NOT NULL,
                class_session_id UUID NOT NULL,
                status          VARCHAR(20) DEFAULT ''confirmed''
                                    CHECK (status IN (''confirmed'',''booked'',''waitlisted'',''checked_in'',''no_show'',''cancelled'',''late_cancel'',''attended'')),
                source          VARCHAR(20) DEFAULT ''web'',
                waitlist_position INTEGER,
                membership_id   UUID,
                notes           TEXT,
                guest_name      VARCHAR(255),
                guest_email     VARCHAR(255),
                cancellation_reason TEXT,
                late_cancel     BOOLEAN DEFAULT FALSE,
                booked_at       TIMESTAMPTZ DEFAULT NOW(),
                cancelled_at    TIMESTAMPTZ,
                checked_in_at   TIMESTAMPTZ,
                created_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Membership Types ─────────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.membership_types (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                studio_id       UUID NOT NULL,
                name            VARCHAR(255) NOT NULL,
                description     TEXT,
                type            VARCHAR(30) NOT NULL
                                    CHECK (type IN (''unlimited'',''class_pack'',''intro_offer'',''day_pass'',''single_class'')),
                access_scope    VARCHAR(30) DEFAULT ''in_studio''
                                    CHECK (access_scope IN (''in_studio'',''online'',''all_access'')),
                class_count     INTEGER,
                price_cents     INTEGER NOT NULL,
                billing_period  VARCHAR(30) DEFAULT ''monthly''
                                    CHECK (billing_period IN (''monthly'',''quarterly'',''semi_annual'',''yearly'',''one_time'')),
                duration_days   INTEGER,
                is_founding_rate BOOLEAN DEFAULT FALSE,
                max_enrollments INTEGER,
                auto_renew      BOOLEAN DEFAULT TRUE,
                trial_days      INTEGER DEFAULT 0,
                freeze_allowed  BOOLEAN DEFAULT FALSE,
                max_freeze_days INTEGER DEFAULT 30,
                cancellation_notice_days INTEGER DEFAULT 0,
                class_types_allowed UUID[],
                is_template     BOOLEAN DEFAULT FALSE,
                template_key    VARCHAR(50),
                is_active       BOOLEAN DEFAULT TRUE,
                is_public       BOOLEAN DEFAULT TRUE,
                sort_order      INTEGER DEFAULT 0,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Member Memberships ───────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.member_memberships (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                member_id       UUID NOT NULL,
                membership_type_id UUID NOT NULL,
                status          VARCHAR(20) DEFAULT ''active''
                                    CHECK (status IN (''active'',''frozen'',''cancelled'',''expired'')),
                starts_at       TIMESTAMPTZ NOT NULL,
                ends_at         TIMESTAMPTZ,
                classes_remaining INTEGER,
                frozen_at       TIMESTAMPTZ,
                frozen_until    TIMESTAMPTZ,
                cancelled_at    TIMESTAMPTZ,
                cancellation_reason TEXT,
                stripe_subscription_id VARCHAR(100),
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Transactions ─────────────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.transactions (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                member_id       UUID NOT NULL,
                type            VARCHAR(30) NOT NULL
                                    CHECK (type IN (''payment'',''refund'',''credit'',''adjustment'',''subscription'')),
                amount_cents    INTEGER NOT NULL,
                currency        VARCHAR(3) DEFAULT ''USD'',
                description     TEXT,
                stripe_payment_intent_id VARCHAR(100),
                stripe_invoice_id VARCHAR(100),
                membership_id   UUID,
                booking_id      UUID,
                fee_cents       INTEGER DEFAULT 0,
                net_amount_cents INTEGER,
                refund_amount_cents INTEGER,
                refund_reason   TEXT,
                refunded_at     TIMESTAMPTZ,
                status          VARCHAR(20) DEFAULT ''completed''
                                    CHECK (status IN (''pending'',''completed'',''failed'',''refunded'',''partially_refunded'')),
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Failed Payment Attempts ──────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.failed_payment_attempts (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                member_id       UUID NOT NULL,
                membership_id   UUID,
                stripe_payment_intent_id VARCHAR(100),
                stripe_invoice_id VARCHAR(100),
                amount_cents    INTEGER NOT NULL,
                failure_reason  TEXT,
                attempt_number  INTEGER DEFAULT 1,
                created_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Communication Log ────────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.communication_log (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                member_id       UUID,
                channel         VARCHAR(20) NOT NULL CHECK (channel IN (''email'',''sms'',''push'',''in_app'')),
                type            VARCHAR(50),
                recipient       VARCHAR(255) NOT NULL,
                subject         VARCHAR(500),
                body_preview    TEXT,
                provider_id     VARCHAR(255),
                status          VARCHAR(20) DEFAULT ''sent'',
                metadata        JSONB DEFAULT ''{}''::jsonb,
                created_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Private Services ─────────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.private_services (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                instructor_id   UUID NOT NULL,
                name            VARCHAR(255) NOT NULL,
                description     TEXT,
                duration_minutes INTEGER NOT NULL DEFAULT 60,
                price_cents     INTEGER NOT NULL,
                buffer_before_minutes INTEGER DEFAULT 0,
                buffer_after_minutes  INTEGER DEFAULT 15,
                max_per_day     INTEGER,
                visibility      VARCHAR(30) DEFAULT ''members_only''
                                    CHECK (visibility IN (''public'', ''members_only'', ''tier_specific'', ''invite_only'', ''staff_only'')),
                required_membership_type_id UUID,
                is_virtual      BOOLEAN DEFAULT FALSE,
                is_active       BOOLEAN DEFAULT TRUE,
                created_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Instructor Availability ──────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.instructor_availability (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                instructor_id   UUID NOT NULL,
                day_of_week     INTEGER CHECK (day_of_week BETWEEN 0 AND 6),
                start_time      TIME NOT NULL,
                end_time        TIME NOT NULL,
                is_recurring    BOOLEAN DEFAULT TRUE,
                specific_date   DATE,
                is_blocked      BOOLEAN DEFAULT FALSE,
                created_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Private Bookings ─────────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.private_bookings (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                member_id       UUID NOT NULL,
                instructor_id   UUID NOT NULL,
                private_service_id UUID NOT NULL,
                starts_at       TIMESTAMPTZ NOT NULL,
                ends_at         TIMESTAMPTZ NOT NULL,
                status          VARCHAR(20) DEFAULT ''pending''
                                    CHECK (status IN (''pending'', ''confirmed'', ''cancelled'', ''completed'', ''no_show'')),
                is_virtual      BOOLEAN DEFAULT FALSE,
                zoom_meeting_id VARCHAR(100),
                zoom_join_url   TEXT,
                intake_notes    TEXT,
                instructor_notes TEXT,
                transaction_id  UUID,
                cancelled_at    TIMESTAMPTZ,
                cancellation_reason TEXT,
                reminder_sent   BOOLEAN DEFAULT FALSE,
                price_cents     INTEGER,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── AI Resolution Queue ──────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.resolution_requests (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                member_id       UUID,
                channel         VARCHAR(20),
                subject         VARCHAR(500),
                body            TEXT,
                ai_summary      TEXT,
                ai_suggested_action TEXT,
                status          VARCHAR(20) DEFAULT ''pending''
                                    CHECK (status IN (''pending'',''processing'',''resolved'',''escalated'')),
                assigned_to     UUID,
                resolved_at     TIMESTAMPTZ,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Video Categories ─────────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.video_categories (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                name            VARCHAR(255) NOT NULL,
                slug            VARCHAR(255) NOT NULL,
                description     TEXT,
                sort_order      INTEGER DEFAULT 0,
                is_active       BOOLEAN DEFAULT TRUE,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Videos ───────────────────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.videos (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                source          VARCHAR(20) NOT NULL CHECK (source IN (''youtube'', ''mux'', ''manual'', ''zoom_recording'')),
                external_id     VARCHAR(255),
                title           VARCHAR(500) NOT NULL,
                description     TEXT,
                thumbnail_url   TEXT,
                duration_seconds INTEGER,
                youtube_video_id VARCHAR(50),
                youtube_playlist_id VARCHAR(100),
                mux_asset_id    VARCHAR(255),
                mux_playback_id VARCHAR(255),
                mux_asset_status VARCHAR(30),
                category_id     UUID,
                instructor_id   UUID,
                tags            TEXT[] DEFAULT ''{}'',
                visibility      VARCHAR(30) DEFAULT ''all_members''
                                    CHECK (visibility IN (''all_members'', ''specific_memberships'', ''staff_only'', ''hidden'')),
                is_published    BOOLEAN DEFAULT TRUE,
                published_at    TIMESTAMPTZ,
                sort_order      INTEGER DEFAULT 0,
                embed_url       TEXT,
                metadata        JSONB DEFAULT ''{}''::jsonb,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Video Membership Access ──────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.video_membership_access (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                video_id        UUID NOT NULL,
                membership_type_id UUID NOT NULL,
                UNIQUE(video_id, membership_type_id)
            )', p_schema_name);

            -- ── Video Views ──────────────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.video_views (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                video_id        UUID NOT NULL,
                member_id       UUID NOT NULL,
                watched_seconds INTEGER DEFAULT 0,
                completed       BOOLEAN DEFAULT FALSE,
                created_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Email Campaigns ──────────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.email_campaigns (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                name            VARCHAR(255) NOT NULL,
                subject         VARCHAR(500) NOT NULL,
                html_content    TEXT,
                status          VARCHAR(20) DEFAULT ''draft''
                                    CHECK (status IN (''draft'',''scheduled'',''sending'',''sent'',''cancelled'')),
                audience_filter JSONB DEFAULT ''{}''::jsonb,
                scheduled_at    TIMESTAMPTZ,
                sent_at         TIMESTAMPTZ,
                recipients      INTEGER DEFAULT 0,
                delivered       INTEGER DEFAULT 0,
                opened          INTEGER DEFAULT 0,
                clicked         INTEGER DEFAULT 0,
                bounced         INTEGER DEFAULT 0,
                created_by      UUID,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Email Campaign Sends ─────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.email_campaign_sends (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                campaign_id     UUID NOT NULL,
                member_id       UUID NOT NULL,
                email           VARCHAR(255) NOT NULL,
                status          VARCHAR(20) DEFAULT ''queued''
                                    CHECK (status IN (''queued'',''sent'',''delivered'',''opened'',''clicked'',''bounced'',''failed'')),
                sendgrid_message_id VARCHAR(255),
                opened_at       TIMESTAMPTZ,
                clicked_at      TIMESTAMPTZ,
                created_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── SMS Messages ─────────────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.sms_messages (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                member_id       UUID,
                to_phone        VARCHAR(20) NOT NULL,
                body            TEXT NOT NULL,
                type            VARCHAR(20) DEFAULT ''transactional''
                                    CHECK (type IN (''transactional'',''marketing'',''reminder'')),
                status          VARCHAR(20) DEFAULT ''queued''
                                    CHECK (status IN (''queued'',''sent'',''delivered'',''failed'')),
                twilio_sid      VARCHAR(100),
                error_message   TEXT,
                created_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Courses ──────────────────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.courses (
                id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                studio_id           UUID,
                title               VARCHAR(500) NOT NULL,
                description         TEXT,
                type                VARCHAR(30) NOT NULL DEFAULT ''workshop''
                                        CHECK (type IN (''workshop'',''course'',''teacher_training'',''retreat'')),
                instructor_id       UUID,
                price_cents         INTEGER NOT NULL DEFAULT 0,
                early_bird_price_cents INTEGER,
                early_bird_deadline TIMESTAMPTZ,
                capacity            INTEGER,
                min_enrollment      INTEGER,
                location            TEXT,
                is_virtual          BOOLEAN DEFAULT FALSE,
                image_url           TEXT,
                prerequisites       TEXT,
                status              VARCHAR(20) DEFAULT ''draft''
                                        CHECK (status IN (''draft'',''published'',''in_progress'',''completed'',''cancelled'')),
                registration_opens  TIMESTAMPTZ,
                registration_closes TIMESTAMPTZ,
                starts_at           TIMESTAMPTZ,
                ends_at             TIMESTAMPTZ,
                created_at          TIMESTAMPTZ DEFAULT NOW(),
                updated_at          TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Course Sessions ──────────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.course_sessions (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                course_id       UUID NOT NULL,
                title           VARCHAR(500),
                session_number  INTEGER NOT NULL DEFAULT 1,
                starts_at       TIMESTAMPTZ NOT NULL,
                ends_at         TIMESTAMPTZ NOT NULL,
                location        TEXT,
                is_virtual      BOOLEAN DEFAULT FALSE,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Course Enrollments ───────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.course_enrollments (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                course_id       UUID NOT NULL,
                member_id       UUID NOT NULL,
                status          VARCHAR(20) DEFAULT ''enrolled''
                                    CHECK (status IN (''enrolled'',''withdrawn'',''completed'')),
                paid_price_cents INTEGER,
                transaction_id  UUID,
                enrolled_at     TIMESTAMPTZ DEFAULT NOW(),
                withdrawn_at    TIMESTAMPTZ,
                completed_at    TIMESTAMPTZ,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(course_id, member_id)
            )', p_schema_name);

            -- ── Course Session Attendance ────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.course_session_attendance (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                course_session_id UUID NOT NULL,
                member_id       UUID NOT NULL,
                status          VARCHAR(20) DEFAULT ''attended''
                                    CHECK (status IN (''attended'',''absent'',''late'')),
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(course_session_id, member_id)
            )', p_schema_name);

            -- ── ClassPass Config ─────────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.classpass_config (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                studio_id       UUID NOT NULL UNIQUE,
                venue_id        VARCHAR(100),
                api_key_encrypted BYTEA,
                is_active       BOOLEAN DEFAULT FALSE,
                credit_rate     INTEGER DEFAULT 1,
                auto_confirm    BOOLEAN DEFAULT TRUE,
                max_spots_per_class INTEGER DEFAULT 3,
                blackout_class_types UUID[] DEFAULT ''{}'',
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── ClassPass Reservations ───────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.classpass_reservations (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                classpass_reservation_id VARCHAR(100) NOT NULL UNIQUE,
                class_session_id UUID,
                booking_id      UUID,
                customer_name   VARCHAR(255),
                customer_email  VARCHAR(255),
                credits         INTEGER DEFAULT 0,
                status          VARCHAR(20) DEFAULT ''reserved''
                                    CHECK (status IN (''reserved'',''confirmed'',''cancelled'',''no_show'',''completed'')),
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Time Entries ─────────────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.time_entries (
                id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                instructor_id     UUID NOT NULL,
                clock_in          TIMESTAMPTZ NOT NULL,
                clock_out         TIMESTAMPTZ,
                break_minutes     INTEGER DEFAULT 0,
                shift_type        VARCHAR(20) DEFAULT ''regular''
                                      CHECK (shift_type IN (''regular'', ''training'', ''admin'', ''event'')),
                notes             TEXT,
                status            VARCHAR(20) DEFAULT ''pending''
                                      CHECK (status IN (''pending'', ''approved'', ''rejected'')),
                approved_by       UUID,
                approved_at       TIMESTAMPTZ,
                total_minutes     INTEGER,
                overtime_minutes  INTEGER DEFAULT 0,
                created_at        TIMESTAMPTZ DEFAULT NOW(),
                updated_at        TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Payroll Runs ─────────────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.payroll_runs (
                id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                period_start      DATE NOT NULL,
                period_end        DATE NOT NULL,
                status            VARCHAR(20) DEFAULT ''draft''
                                      CHECK (status IN (''draft'', ''finalized'', ''exported'')),
                total_gross_cents INTEGER DEFAULT 0,
                total_hours       NUMERIC(8,2) DEFAULT 0,
                created_by        UUID,
                finalized_at      TIMESTAMPTZ,
                exported_at       TIMESTAMPTZ,
                export_method     VARCHAR(20),
                created_at        TIMESTAMPTZ DEFAULT NOW(),
                updated_at        TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (period_start, period_end)
            )', p_schema_name);

            -- ── Payroll Line Items ───────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.payroll_line_items (
                id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                payroll_run_id    UUID NOT NULL,
                instructor_id     UUID NOT NULL,
                hours_worked      NUMERIC(8,2) DEFAULT 0,
                overtime_hours    NUMERIC(8,2) DEFAULT 0,
                classes_taught    INTEGER DEFAULT 0,
                class_pay_cents   INTEGER DEFAULT 0,
                hourly_pay_cents  INTEGER DEFAULT 0,
                overtime_pay_cents INTEGER DEFAULT 0,
                total_gross_cents INTEGER DEFAULT 0,
                created_at        TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (payroll_run_id, instructor_id)
            )', p_schema_name);

            -- ── Payroll Employee Mapping ─────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.payroll_employee_mapping (
                id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                instructor_id         UUID NOT NULL,
                provider              VARCHAR(20) NOT NULL
                                          CHECK (provider IN (''gusto'', ''quickbooks'')),
                external_employee_id  VARCHAR(255) NOT NULL,
                external_employee_name VARCHAR(255),
                mapped_at             TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (instructor_id, provider)
            )', p_schema_name);

            -- ── Equipment ────────────────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.equipment (
                id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                studio_id           UUID NOT NULL,
                room_id             UUID,
                name                VARCHAR(255) NOT NULL,
                category            VARCHAR(30) NOT NULL DEFAULT ''props''
                                        CHECK (category IN (''props'',''mats'',''weights'',''machines'',''audio_visual'',''furniture'',''cleaning'',''other'')),
                description         TEXT,
                quantity            INTEGER DEFAULT 1,
                purchase_date       DATE,
                purchase_cost_cents INTEGER,
                condition           VARCHAR(20) DEFAULT ''good''
                                        CHECK (condition IN (''new'',''good'',''fair'',''poor'',''retired'')),
                warranty_expiry     DATE,
                serial_number       VARCHAR(255),
                photo_url           TEXT,
                notes               TEXT,
                is_active           BOOLEAN DEFAULT TRUE,
                created_at          TIMESTAMPTZ DEFAULT NOW(),
                updated_at          TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Maintenance Requests ─────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.maintenance_requests (
                id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                studio_id           UUID NOT NULL,
                room_id             UUID,
                equipment_id        UUID,
                title               VARCHAR(255) NOT NULL,
                description         TEXT,
                priority            VARCHAR(20) DEFAULT ''medium''
                                        CHECK (priority IN (''low'',''medium'',''high'',''urgent'')),
                status              VARCHAR(20) DEFAULT ''open''
                                        CHECK (status IN (''open'',''in_progress'',''completed'',''cancelled'')),
                category            VARCHAR(30) DEFAULT ''repair''
                                        CHECK (category IN (''repair'',''cleaning'',''replacement'',''inspection'',''safety'')),
                requested_by        UUID,
                assigned_to         TEXT,
                estimated_cost_cents INTEGER,
                actual_cost_cents   INTEGER,
                scheduled_date      DATE,
                completed_at        TIMESTAMPTZ,
                completion_notes    TEXT,
                photos              JSONB DEFAULT ''[]''::jsonb,
                created_at          TIMESTAMPTZ DEFAULT NOW(),
                updated_at          TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Facility Schedules ───────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.facility_schedules (
                id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                studio_id           UUID NOT NULL,
                room_id             UUID,
                equipment_id        UUID,
                schedule_type       VARCHAR(20) NOT NULL DEFAULT ''cleaning''
                                        CHECK (schedule_type IN (''cleaning'',''inspection'',''maintenance'')),
                title               VARCHAR(255) NOT NULL,
                description         TEXT,
                rrule               TEXT,
                assigned_to         TEXT,
                last_completed_at   TIMESTAMPTZ,
                next_due_at         TIMESTAMPTZ,
                is_active           BOOLEAN DEFAULT TRUE,
                created_at          TIMESTAMPTZ DEFAULT NOW(),
                updated_at          TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Facility Schedule Completions ────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.facility_schedule_completions (
                id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                schedule_id         UUID NOT NULL,
                completed_by        UUID,
                completed_at        TIMESTAMPTZ DEFAULT NOW(),
                notes               TEXT,
                photos              JSONB DEFAULT ''[]''::jsonb
            )', p_schema_name);

            -- ── Sub-Finder Requests ──────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.sub_finder_requests (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                class_session_id UUID NOT NULL,
                original_instructor_id UUID NOT NULL,
                reason          TEXT,
                status          VARCHAR(20) DEFAULT ''open''
                                    CHECK (status IN (''open'',''filled'',''cancelled'',''expired'')),
                filled_by_id    UUID,
                filled_at       TIMESTAMPTZ,
                expires_at      TIMESTAMPTZ,
                notified_instructors UUID[] DEFAULT ''{}'',
                created_by      UUID,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Indexes ──────────────────────────────────────────────────
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_sessions_starts ON %I.class_sessions(starts_at)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_bookings_member ON %I.bookings(member_id)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_bookings_session ON %I.bookings(class_session_id)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_members_email ON %I.members(email)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_transactions_member ON %I.transactions(member_id)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_videos_source ON %I.videos(source)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_videos_published ON %I.videos(is_published)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_avail_instructor_day ON %I.instructor_availability(instructor_id, day_of_week)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_pb_starts ON %I.private_bookings(starts_at)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_pb_instructor_starts ON %I.private_bookings(instructor_id, starts_at)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_campaigns_status ON %I.email_campaigns(status)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_csends_campaign ON %I.email_campaign_sends(campaign_id)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_sms_member ON %I.sms_messages(member_id)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_courses_status ON %I.courses(status)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_courses_type ON %I.courses(type)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_csess_course ON %I.course_sessions(course_id)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_cenroll_course ON %I.course_enrollments(course_id)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_cenroll_member ON %I.course_enrollments(member_id)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_cp_reservations_session ON %I.classpass_reservations(class_session_id)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_cp_reservations_status ON %I.classpass_reservations(status)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_sessions_recording ON %I.class_sessions(recording_status) WHERE recording_status != ''none''', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_time_entries_instructor ON %I.time_entries(instructor_id, clock_in)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_time_entries_pending ON %I.time_entries(status) WHERE status = ''pending''', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_payroll_mapping_provider ON %I.payroll_employee_mapping(provider)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_equipment_studio ON %I.equipment(studio_id)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_equipment_room ON %I.equipment(room_id)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_equipment_category ON %I.equipment(category)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_maintenance_studio ON %I.maintenance_requests(studio_id)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_maintenance_status ON %I.maintenance_requests(status)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_fac_schedule_studio ON %I.facility_schedules(studio_id)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_fac_completion_schedule ON %I.facility_schedule_completions(schedule_id, completed_at DESC)', replace(p_schema_name, '-', '_'), p_schema_name);

        END;
        $$;


--
-- Name: touch_updated_at(); Type: FUNCTION; Schema: af_global; Owner: -
--

CREATE FUNCTION af_global.touch_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$;


--
-- Name: update_updated_at(); Type: FUNCTION; Schema: af_global; Owner: -
--

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

--
-- Name: ai_token_usage; Type: TABLE; Schema: af_global; Owner: -
--

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


--
-- Name: api_key_routing; Type: TABLE; Schema: af_global; Owner: -
--

CREATE TABLE af_global.api_key_routing (
    key_prefix text NOT NULL,
    org_slug text NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: audit_log; Type: TABLE; Schema: af_global; Owner: -
--

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


--
-- Name: dead_letter_tasks; Type: TABLE; Schema: af_global; Owner: -
--

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


--
-- Name: feature_flags; Type: TABLE; Schema: af_global; Owner: -
--

CREATE TABLE af_global.feature_flags (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    organization_id uuid,
    flag_key character varying(100) NOT NULL,
    is_enabled boolean DEFAULT false,
    config jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: kiosk_devices; Type: TABLE; Schema: af_global; Owner: -
--

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


--
-- Name: membership_templates; Type: TABLE; Schema: af_global; Owner: -
--

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


--
-- Name: organization_users; Type: TABLE; Schema: af_global; Owner: -
--

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
    kiosk_pin_hash text,
    kiosk_pin_set_at timestamp with time zone,
    CONSTRAINT organization_users_role_check CHECK (((role)::text = ANY ((ARRAY['owner'::character varying, 'admin'::character varying, 'instructor'::character varying, 'front_desk'::character varying, 'member'::character varying])::text[])))
);


--
-- Name: organizations; Type: TABLE; Schema: af_global; Owner: -
--

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
    gusto_client_id_encrypted bytea,
    gusto_access_token_encrypted bytea,
    gusto_refresh_token_encrypted bytea,
    gusto_company_id character varying(100),
    gusto_connected_at timestamp with time zone,
    qb_client_id_encrypted bytea,
    qb_client_secret_encrypted bytea,
    qb_access_token_encrypted bytea,
    qb_refresh_token_encrypted bytea,
    qb_realm_id character varying(100),
    qb_connected_at timestamp with time zone,
    custom_domain_status character varying(20),
    custom_domain_verified_at timestamp with time zone,
    cancellation_reason character varying(100),
    cancellation_feedback text,
    cancellation_requested_at timestamp with time zone,
    cancellation_effective_at timestamp with time zone,
    meta_access_token_encrypted bytea,
    meta_connected_at timestamp with time zone,
    google_ads_refresh_token_encrypted bytea,
    google_ads_connected_at timestamp with time zone,
    emr_protocol character varying(10),
    emr_base_url text,
    emr_client_id_encrypted bytea,
    emr_client_secret_encrypted bytea,
    emr_webhook_secret character varying(128),
    emr_hl7_host text,
    emr_hl7_port integer,
    emr_connected_at timestamp with time zone,
    emr_sync_enabled boolean DEFAULT false,
    allowed_portal_origins text[] DEFAULT ARRAY[]::text[] NOT NULL,
    brand_config jsonb DEFAULT '{}'::jsonb NOT NULL,
    square_merchant_id text,
    square_access_token_encrypted bytea,
    square_refresh_token_encrypted bytea,
    square_token_expires_at timestamp with time zone,
    square_location_id text,
    billing_provider text DEFAULT 'square'::text NOT NULL,
    square_subscription_id text,
    stripe_direct_mode boolean DEFAULT false NOT NULL,
    square_pos_default_device_id uuid,
    square_pos_tip_settings jsonb,
    CONSTRAINT organizations_billing_provider_chk CHECK ((billing_provider = ANY (ARRAY['stripe'::text, 'square'::text]))),
    CONSTRAINT organizations_status_check CHECK (((status)::text = ANY ((ARRAY['trial'::character varying, 'active'::character varying, 'suspended'::character varying, 'cancelling'::character varying, 'cancelled'::character varying])::text[])))
);


--
-- Name: platform_ads_config; Type: TABLE; Schema: af_global; Owner: -
--

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


--
-- Name: platform_ai_agent_log; Type: TABLE; Schema: af_global; Owner: -
--

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


--
-- Name: platform_announcements; Type: TABLE; Schema: af_global; Owner: -
--

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


--
-- Name: platform_backup_schedule; Type: TABLE; Schema: af_global; Owner: -
--

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


--
-- Name: platform_backups; Type: TABLE; Schema: af_global; Owner: -
--

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
    CONSTRAINT platform_backups_triggered_by_check CHECK (((triggered_by)::text = ANY ((ARRAY['manual'::character varying, 'scheduled'::character varying])::text[])))
);


--
-- Name: platform_config; Type: TABLE; Schema: af_global; Owner: -
--

CREATE TABLE af_global.platform_config (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    sendgrid_api_key_enc bytea,
    sendgrid_from_email character varying(255) DEFAULT 'hello@example.com'::character varying,
    sendgrid_from_name character varying(100) DEFAULT 'AuraFlow'::character varying,
    sendgrid_inbound_webhook_secret_enc bytea,
    platform_admin_alert_email character varying(255) DEFAULT 'alerts@example.com'::character varying,
    support_escalation_email character varying(255) DEFAULT 'alerts@example.com'::character varying,
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


--
-- Name: platform_email_accounts; Type: TABLE; Schema: af_global; Owner: -
--

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


--
-- Name: platform_email_inbox; Type: TABLE; Schema: af_global; Owner: -
--

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


--
-- Name: platform_invoices; Type: TABLE; Schema: af_global; Owner: -
--

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


--
-- Name: platform_landing_pages; Type: TABLE; Schema: af_global; Owner: -
--

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


--
-- Name: platform_metrics_daily; Type: TABLE; Schema: af_global; Owner: -
--

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


--
-- Name: platform_request_metrics; Type: TABLE; Schema: af_global; Owner: -
--

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


--
-- Name: platform_security_events; Type: TABLE; Schema: af_global; Owner: -
--

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


--
-- Name: platform_settings; Type: TABLE; Schema: af_global; Owner: -
--

CREATE TABLE af_global.platform_settings (
    key character varying(100) NOT NULL,
    value jsonb NOT NULL,
    description text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_by uuid
);


--
-- Name: platform_social_messages; Type: TABLE; Schema: af_global; Owner: -
--

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


--
-- Name: platform_social_posts; Type: TABLE; Schema: af_global; Owner: -
--

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


--
-- Name: pos_checkout_index; Type: TABLE; Schema: af_global; Owner: -
--

CREATE TABLE af_global.pos_checkout_index (
    checkout_id uuid NOT NULL,
    schema_name text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone DEFAULT (now() + '00:15:00'::interval) NOT NULL
);


--
-- Name: processed_webhook_events; Type: TABLE; Schema: af_global; Owner: -
--

CREATE TABLE af_global.processed_webhook_events (
    event_id text NOT NULL,
    event_type text,
    processed_at timestamp with time zone DEFAULT now(),
    provider text DEFAULT 'stripe'::text NOT NULL
);


--
-- Name: refresh_tokens; Type: TABLE; Schema: af_global; Owner: -
--

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


--
-- Name: square_pos_devices; Type: TABLE; Schema: af_global; Owner: -
--

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


--
-- Name: users; Type: TABLE; Schema: af_global; Owner: -
--

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
    totp_secret text,
    totp_enabled boolean DEFAULT false NOT NULL,
    backup_codes text[],
    force_password_reset boolean DEFAULT false NOT NULL,
    force_password_change boolean DEFAULT false NOT NULL
);


--
-- Name: acct_categories; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.acct_categories (
    code text NOT NULL,
    label text NOT NULL,
    kind text NOT NULL,
    schedule_c_line text,
    txf_ref text,
    sort_order integer DEFAULT 0 NOT NULL,
    is_custom boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT acct_categories_kind_check CHECK ((kind = ANY (ARRAY['income'::text, 'expense'::text, 'distribution'::text, 'transfer'::text])))
);


--
-- Name: acct_members; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.acct_members (
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
);


--
-- Name: acct_owner_draws; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.acct_owner_draws (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    owner_pattern text NOT NULL,
    monthly_cents bigint NOT NULL,
    effective_from date NOT NULL,
    effective_to date,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: acct_payout_items; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.acct_payout_items (
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
);


--
-- Name: acct_payouts; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.acct_payouts (
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
);


--
-- Name: acct_settings; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.acct_settings (
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
);


--
-- Name: acct_transactions; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.acct_transactions (
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
);


--
-- Name: acct_vendor_rules; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.acct_vendor_rules (
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
);


--
-- Name: api_keys; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.api_keys (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    key_hash text NOT NULL,
    key_prefix text NOT NULL,
    scopes text[] DEFAULT '{}'::text[],
    rate_limit_rpm integer DEFAULT 60,
    is_active boolean DEFAULT true,
    last_used_at timestamp with time zone,
    expires_at timestamp with time zone,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now(),
    revoked_at timestamp with time zone
);


--
-- Name: bookings; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.bookings (
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
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT bookings_status_check CHECK (((status)::text = ANY ((ARRAY['confirmed'::character varying, 'waitlisted'::character varying, 'cancelled'::character varying, 'no_show'::character varying, 'attended'::character varying])::text[])))
);


--
-- Name: class_series; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.class_series (
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
);


--
-- Name: class_sessions; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.class_sessions (
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
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    room_id uuid,
    series_id uuid,
    substitute_instructor_id uuid,
    notes text,
    auto_record boolean DEFAULT false,
    recording_status character varying(30) DEFAULT 'none'::character varying,
    recording_url text,
    video_id uuid,
    drop_in_price_cents integer,
    dynamic_price_cents integer,
    modality text DEFAULT 'in_studio'::text NOT NULL,
    CONSTRAINT chk_af_tenant_sunrise_yoga_recording_status CHECK (((recording_status)::text = ANY ((ARRAY['none'::character varying, 'recording'::character varying, 'processing'::character varying, 'ready'::character varying, 'published'::character varying, 'failed'::character varying])::text[]))),
    CONSTRAINT class_sessions_modality_check CHECK ((modality = ANY (ARRAY['in_studio'::text, 'virtual'::text, 'hybrid'::text]))),
    CONSTRAINT class_sessions_status_check CHECK (((status)::text = ANY ((ARRAY['scheduled'::character varying, 'in_progress'::character varying, 'completed'::character varying, 'cancelled'::character varying])::text[])))
);


--
-- Name: class_types; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.class_types (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    studio_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    duration_minutes integer DEFAULT 60 NOT NULL,
    color character varying(7) DEFAULT '#4F46E5'::character varying,
    capacity integer DEFAULT 20,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now(),
    level character varying(30) DEFAULT 'all_levels'::character varying,
    tags text[] DEFAULT '{}'::text[],
    category character varying(100),
    image_url text
);


--
-- Name: classpass_config; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.classpass_config (
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
);


--
-- Name: classpass_reservations; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.classpass_reservations (
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
);


--
-- Name: communication_log; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.communication_log (
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
);


--
-- Name: course_enrollments; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.course_enrollments (
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
);


--
-- Name: course_session_attendance; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.course_session_attendance (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    course_session_id uuid NOT NULL,
    member_id uuid NOT NULL,
    status character varying(20) DEFAULT 'attended'::character varying,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT course_session_attendance_status_check CHECK (((status)::text = ANY ((ARRAY['attended'::character varying, 'absent'::character varying, 'late'::character varying])::text[])))
);


--
-- Name: course_sessions; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.course_sessions (
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
);


--
-- Name: courses; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.courses (
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
    CONSTRAINT chk_courses_guest_only_for_workshops CHECK (((guest_instructor_id IS NULL) OR ((type)::text = 'workshop'::text))),
    CONSTRAINT courses_status_check CHECK (((status)::text = ANY ((ARRAY['draft'::character varying, 'published'::character varying, 'in_progress'::character varying, 'completed'::character varying, 'cancelled'::character varying])::text[]))),
    CONSTRAINT courses_type_check CHECK (((type)::text = ANY ((ARRAY['workshop'::character varying, 'course'::character varying, 'teacher_training'::character varying, 'retreat'::character varying])::text[])))
);


--
-- Name: de34_filings; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.de34_filings (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    filed_at timestamp with time zone DEFAULT now() NOT NULL,
    filed_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: email_campaign_sends; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.email_campaign_sends (
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
);


--
-- Name: email_campaigns; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.email_campaigns (
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
);


--
-- Name: employee_w4_forms; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.employee_w4_forms (
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
);


--
-- Name: employer_profile; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.employer_profile (
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
);


--
-- Name: emr_encounter_log; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.emr_encounter_log (
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
);


--
-- Name: emr_patient_map; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.emr_patient_map (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    member_id uuid NOT NULL,
    emr_patient_id character varying(255) NOT NULL,
    emr_system character varying(50) NOT NULL,
    last_synced_at timestamp with time zone,
    sync_direction character varying(10) NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: emr_sync_log; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.emr_sync_log (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    direction character varying(10) NOT NULL,
    resource_type character varying(50) NOT NULL,
    operation character varying(20) NOT NULL,
    emr_resource_id character varying(255),
    auraflow_resource_id uuid,
    status character varying(20) NOT NULL,
    error_message text,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: equipment; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.equipment (
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
);


--
-- Name: facility_schedule_completions; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.facility_schedule_completions (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    schedule_id uuid NOT NULL,
    completed_by uuid,
    completed_at timestamp with time zone DEFAULT now(),
    notes text,
    photos jsonb DEFAULT '[]'::jsonb
);


--
-- Name: facility_schedules; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.facility_schedules (
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
);


--
-- Name: failed_payment_attempts; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.failed_payment_attempts (
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
);


--
-- Name: gdpr_deletion_requests; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.gdpr_deletion_requests (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    member_id uuid NOT NULL,
    requested_at timestamp with time zone DEFAULT now() NOT NULL,
    scheduled_deletion_at timestamp with time zone NOT NULL,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    completed_at timestamp with time zone,
    cancelled_at timestamp with time zone
);


--
-- Name: guest_instructors; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.guest_instructors (
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
    CONSTRAINT guest_instructors_revenue_share_percent_to_guest_check CHECK (((revenue_share_percent_to_guest >= 0) AND (revenue_share_percent_to_guest <= 100)))
);


--
-- Name: instructor_availability; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.instructor_availability (
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
);


--
-- Name: instructors; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.instructors (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    user_id uuid NOT NULL,
    display_name character varying(255) NOT NULL,
    bio text,
    photo_url text,
    specialties text[],
    certifications text[],
    zoom_user_id character varying(100),
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    pay_rate_cents integer,
    pay_type character varying(20) DEFAULT 'per_class'::character varying,
    tax_classification character varying(20) DEFAULT '1099'::character varying,
    email character varying(255),
    phone character varying(20),
    color character varying(7) DEFAULT '#4F46E5'::character varying,
    sort_order integer DEFAULT 0,
    phone_hash character varying(64)
);


--
-- Name: inventory; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.inventory (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    product_id uuid NOT NULL,
    quantity_on_hand integer DEFAULT 0 NOT NULL,
    reorder_point integer DEFAULT 5 NOT NULL,
    reorder_quantity integer DEFAULT 20 NOT NULL,
    last_counted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT inventory_qty_nonneg CHECK ((quantity_on_hand >= 0))
);


--
-- Name: inventory_transactions; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.inventory_transactions (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    product_id uuid NOT NULL,
    quantity_change integer NOT NULL,
    reason character varying(50) NOT NULL,
    reference_id uuid,
    notes text,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT inv_txn_reason_check CHECK (((reason)::text = ANY ((ARRAY['sale'::character varying, 'restock'::character varying, 'adjustment'::character varying, 'shrinkage'::character varying, 'opening_count'::character varying])::text[])))
);


--
-- Name: job_application_documents; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.job_application_documents (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    application_id uuid NOT NULL,
    doc_type character varying(30) DEFAULT 'other'::character varying NOT NULL,
    filename character varying(255) NOT NULL,
    content_type character varying(120) NOT NULL,
    file_data bytea NOT NULL,
    size_bytes integer NOT NULL,
    uploaded_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT job_application_documents_doc_type_check CHECK (((doc_type)::text = ANY ((ARRAY['resume'::character varying, 'certification'::character varying, 'insurance'::character varying, 'yoga_alliance'::character varying, 'other'::character varying])::text[])))
);


--
-- Name: job_application_events; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.job_application_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    application_id uuid NOT NULL,
    event_type character varying(30) NOT NULL,
    from_status character varying(20),
    to_status character varying(20),
    note text,
    actor_user_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT job_application_events_event_type_check CHECK (((event_type)::text = ANY ((ARRAY['created'::character varying, 'status_changed'::character varying, 'note'::character varying, 'rated'::character varying, 'document_uploaded'::character varying, 'hired'::character varying])::text[])))
);


--
-- Name: job_applications; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.job_applications (
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
);


--
-- Name: maintenance_requests; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.maintenance_requests (
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
);


--
-- Name: marketing_drafts; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.marketing_drafts (
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
    CONSTRAINT draft_status_check CHECK (((status)::text = ANY ((ARRAY['draft'::character varying, 'approved'::character varying, 'rejected'::character varying, 'sent'::character varying])::text[]))),
    CONSTRAINT draft_type_check CHECK (((draft_type)::text = ANY ((ARRAY['email'::character varying, 'social'::character varying, 'sms'::character varying, 'class_description'::character varying])::text[])))
);


--
-- Name: member_credits; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.member_credits (
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
);


--
-- Name: member_health_data; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.member_health_data (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    member_id uuid NOT NULL,
    health_data_encrypted bytea,
    injuries_encrypted bytea,
    conditions_encrypted bytea,
    medications_encrypted bytea,
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: member_memberships; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.member_memberships (
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
    square_subscription_id text,
    billing_provider text DEFAULT 'stripe'::text NOT NULL,
    trial_period_end timestamp with time zone,
    CONSTRAINT member_memberships_billing_provider_chk CHECK ((billing_provider = ANY (ARRAY['stripe'::text, 'square'::text]))),
    CONSTRAINT member_memberships_status_check CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'frozen'::character varying, 'cancelled'::character varying, 'expired'::character varying, 'pending'::character varying])::text[])))
);


--
-- Name: member_milestones; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.member_milestones (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    member_id uuid NOT NULL,
    milestone_type character varying(50) NOT NULL,
    achieved_at timestamp with time zone DEFAULT now(),
    notified_at timestamp with time zone
);


--
-- Name: member_notes; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.member_notes (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    member_id uuid NOT NULL,
    author_id uuid NOT NULL,
    is_pinned boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: members; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.members (
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
    birthday_month smallint,
    birthday_day smallint,
    square_customer_id text,
    square_card_on_file_id text,
    square_card_on_file_brand text,
    square_card_on_file_last4 text,
    square_card_on_file_exp_month integer,
    square_card_on_file_exp_year integer,
    square_card_on_file_saved_at timestamp with time zone,
    facility_name text
);


--
-- Name: membership_types; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.membership_types (
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
    CONSTRAINT membership_types_billing_period_check CHECK (((billing_period)::text = ANY ((ARRAY['monthly'::character varying, 'yearly'::character varying, 'quarterly'::character varying, 'semi_annual'::character varying, 'one_time'::character varying])::text[]))),
    CONSTRAINT membership_types_type_check CHECK (((type)::text = ANY ((ARRAY['unlimited'::character varying, 'class_pack'::character varying, 'intro_offer'::character varying, 'day_pass'::character varying, 'single_class'::character varying])::text[])))
);


--
-- Name: onboarding_documents; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.onboarding_documents (
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
);


--
-- Name: onboarding_packets; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.onboarding_packets (
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
);


--
-- Name: payroll_employee_mapping; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.payroll_employee_mapping (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    instructor_id uuid NOT NULL,
    provider character varying(20) NOT NULL,
    external_employee_id character varying(255) NOT NULL,
    external_employee_name character varying(255),
    mapped_at timestamp with time zone DEFAULT now(),
    CONSTRAINT payroll_mapping_provider_check CHECK (((provider)::text = ANY ((ARRAY['gusto'::character varying, 'quickbooks'::character varying])::text[])))
);


--
-- Name: payroll_line_items; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.payroll_line_items (
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
    guest_instructor_id uuid,
    CONSTRAINT payroll_line_items_one_owner_chk CHECK ((((instructor_id IS NOT NULL) AND (guest_instructor_id IS NULL)) OR ((instructor_id IS NULL) AND (guest_instructor_id IS NOT NULL))))
);


--
-- Name: payroll_runs; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.payroll_runs (
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
);


--
-- Name: pos_line_items; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.pos_line_items (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    transaction_id uuid NOT NULL,
    product_id uuid NOT NULL,
    quantity integer DEFAULT 1 NOT NULL,
    unit_price_cents integer NOT NULL,
    tax_cents integer DEFAULT 0 NOT NULL,
    total_cents integer NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT pos_line_price_nonneg CHECK ((unit_price_cents >= 0)),
    CONSTRAINT pos_line_qty_positive CHECK ((quantity > 0))
);


--
-- Name: pos_terminal_checkouts; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.pos_terminal_checkouts (
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
    CONSTRAINT pos_terminal_checkouts_amount_cents_check CHECK ((amount_cents > 0)),
    CONSTRAINT pos_terminal_checkouts_flow_check CHECK ((flow = ANY (ARRAY['terminal'::text, 'deeplink'::text]))),
    CONSTRAINT pos_terminal_checkouts_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'in_progress'::text, 'completed'::text, 'cancelled'::text, 'failed'::text, 'expired'::text])))
);


--
-- Name: pos_transactions; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.pos_transactions (
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
    CONSTRAINT pos_txn_payment_method_check CHECK (((payment_method)::text = ANY ((ARRAY['cash'::character varying, 'card'::character varying, 'comp'::character varying, 'stripe'::character varying, 'paypal'::character varying, 'apple_pay'::character varying, 'google_pay'::character varying, 'venmo'::character varying, 'check'::character varying, 'bank_transfer'::character varying])::text[]))),
    CONSTRAINT pos_txn_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'completed'::character varying, 'refunded'::character varying, 'voided'::character varying])::text[]))),
    CONSTRAINT pos_txn_total_nonneg CHECK ((total_cents >= 0))
);


--
-- Name: price_adjustments_log; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.price_adjustments_log (
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
);


--
-- Name: pricing_rules; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.pricing_rules (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    studio_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    rule_type character varying(50) NOT NULL,
    config jsonb DEFAULT '{}'::jsonb NOT NULL,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT pricing_rules_rule_type_check CHECK (((rule_type)::text = ANY ((ARRAY['peak_hour'::character varying, 'fill_rate'::character varying, 'day_of_week'::character varying, 'seasonal'::character varying, 'last_minute'::character varying])::text[])))
);


--
-- Name: private_bookings; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.private_bookings (
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
    cancelled_by_role character varying(20),
    CONSTRAINT private_bookings_cancelled_by_role_check CHECK (((cancelled_by_role IS NULL) OR ((cancelled_by_role)::text = ANY ((ARRAY['instructor'::character varying, 'member'::character varying, 'staff'::character varying])::text[])))),
    CONSTRAINT private_bookings_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'confirmed'::character varying, 'cancelled'::character varying, 'completed'::character varying, 'no_show'::character varying])::text[])))
);


--
-- Name: private_services; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.private_services (
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
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT private_services_visibility_check CHECK (((visibility)::text = ANY ((ARRAY['public'::character varying, 'members_only'::character varying, 'tier_specific'::character varying, 'invite_only'::character varying, 'staff_only'::character varying])::text[])))
);


--
-- Name: products; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.products (
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
);


--
-- Name: resolution_requests; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.resolution_requests (
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
);


--
-- Name: reviews; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.reviews (
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
    CONSTRAINT reviews_rating_check CHECK (((rating >= 1) AND (rating <= 5))),
    CONSTRAINT reviews_sentiment_check CHECK (((sentiment)::text = ANY ((ARRAY['positive'::character varying, 'neutral'::character varying, 'negative'::character varying])::text[])))
);


--
-- Name: rooms; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.rooms (
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
);


--
-- Name: sms_campaign_sends; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.sms_campaign_sends (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    campaign_id uuid NOT NULL,
    member_id uuid NOT NULL,
    to_phone character varying(20) NOT NULL,
    status character varying(20) DEFAULT 'queued'::character varying,
    twilio_sid character varying(100),
    error_message text,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT sms_campaign_sends_status_check CHECK (((status)::text = ANY ((ARRAY['queued'::character varying, 'sent'::character varying, 'delivered'::character varying, 'failed'::character varying, 'opted_out'::character varying])::text[])))
);


--
-- Name: sms_campaigns; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.sms_campaigns (
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
);


--
-- Name: sms_messages; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.sms_messages (
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
);


--
-- Name: sms_templates; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.sms_templates (
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
);


--
-- Name: studios; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.studios (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    organization_id uuid DEFAULT '50065def-79b0-4550-8dbd-e0b623b2954d'::uuid NOT NULL,
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
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    cancellation_policy_hours integer DEFAULT 12,
    late_cancel_fee_cents integer DEFAULT 0,
    booking_window_days integer DEFAULT 14,
    allow_guest_booking boolean DEFAULT false,
    waitlist_mode character varying(20) DEFAULT 'fifo'::character varying,
    CONSTRAINT chk_waitlist_mode CHECK (((waitlist_mode)::text = ANY ((ARRAY['fifo'::character varying, 'ai_priority'::character varying])::text[])))
);


--
-- Name: sub_finder_requests; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.sub_finder_requests (
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
);


--
-- Name: time_entries; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.time_entries (
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
);


--
-- Name: transactions; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.transactions (
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
);


--
-- Name: video_categories; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.video_categories (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    slug character varying(100) NOT NULL,
    sort_order integer DEFAULT 0,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: video_membership_access; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.video_membership_access (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    video_id uuid NOT NULL,
    membership_type_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: video_views; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.video_views (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    video_id uuid NOT NULL,
    member_id uuid NOT NULL,
    watched_seconds integer DEFAULT 0,
    completed boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: videos; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.videos (
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
);


--
-- Name: waiver_signatures; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.waiver_signatures (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    waiver_template_id uuid NOT NULL,
    member_id uuid NOT NULL,
    signed_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone,
    ip_address character varying(45),
    user_agent text,
    signature_text character varying(255) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: waiver_templates; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.waiver_templates (
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
);


--
-- Name: workshop_contracts; Type: TABLE; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TABLE af_tenant_sunrise_yoga.workshop_contracts (
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
    CONSTRAINT workshop_contracts_status_chk CHECK (((status)::text = ANY ((ARRAY['prepared'::character varying, 'sent'::character varying, 'viewed'::character varying, 'signed'::character varying, 'voided'::character varying])::text[])))
);


--
--



--
-- Data for Name: ai_token_usage; Type: TABLE DATA; Schema: af_global; Owner: -
--



--
-- Data for Name: api_key_routing; Type: TABLE DATA; Schema: af_global; Owner: -
--



--
-- Data for Name: audit_log; Type: TABLE DATA; Schema: af_global; Owner: -
--

INSERT INTO af_global.audit_log VALUES ('fc7916b2-329f-4952-b0ab-7240ec2cfce1', NULL, '8bacd899-04c4-471e-adad-820f8f9b0a74', 'auth.login_success', 'user', '8bacd899-04c4-471e-adad-820f8f9b0a74', '{"email": "owner@sunrise-yoga.example.com", "mfa_used": false}', '172.20.0.1', '2026-07-15 04:55:08.567632+00');


--
-- Data for Name: dead_letter_tasks; Type: TABLE DATA; Schema: af_global; Owner: -
--



--
-- Data for Name: feature_flags; Type: TABLE DATA; Schema: af_global; Owner: -
--

INSERT INTO af_global.feature_flags VALUES ('634c81e9-82d5-4dd0-a75e-922b835e5c72', NULL, 'scheduling.group_classes', true, '{}', '2026-07-15 04:55:04.789561+00', '2026-07-15 04:55:04.789561+00');
INSERT INTO af_global.feature_flags VALUES ('7822e7ea-e261-4b9b-a59d-fb5d9de50a70', NULL, 'scheduling.private_sessions', true, '{}', '2026-07-15 04:55:04.789561+00', '2026-07-15 04:55:04.789561+00');
INSERT INTO af_global.feature_flags VALUES ('3cdce295-cef3-4c75-ac5b-195ef0436e94', NULL, 'scheduling.zoom_integration', true, '{}', '2026-07-15 04:55:04.789561+00', '2026-07-15 04:55:04.789561+00');
INSERT INTO af_global.feature_flags VALUES ('4154f45b-007c-4517-8b10-2d605d5c27d6', NULL, 'video.on_demand_library', false, '{}', '2026-07-15 04:55:04.789561+00', '2026-07-15 04:55:04.789561+00');
INSERT INTO af_global.feature_flags VALUES ('f66194ab-a39c-41cf-95dc-f64e5064a49c', NULL, 'video.mux_hosting', false, '{}', '2026-07-15 04:55:04.789561+00', '2026-07-15 04:55:04.789561+00');
INSERT INTO af_global.feature_flags VALUES ('36ba83fb-d103-4252-873c-c5708340c50d', NULL, 'video.youtube_embed', true, '{}', '2026-07-15 04:55:04.789561+00', '2026-07-15 04:55:04.789561+00');
INSERT INTO af_global.feature_flags VALUES ('8e4b46d1-3b78-4903-aed9-33bda972d679', NULL, 'courses.workshops', false, '{}', '2026-07-15 04:55:04.789561+00', '2026-07-15 04:55:04.789561+00');
INSERT INTO af_global.feature_flags VALUES ('172a0e44-5845-4ad6-a111-6928e97bf3f7', NULL, 'courses.teacher_training', false, '{}', '2026-07-15 04:55:04.789561+00', '2026-07-15 04:55:04.789561+00');
INSERT INTO af_global.feature_flags VALUES ('285b0a2f-4bd4-42a0-bf26-533c5006a0ee', NULL, 'payments.pos_retail', false, '{}', '2026-07-15 04:55:04.789561+00', '2026-07-15 04:55:04.789561+00');
INSERT INTO af_global.feature_flags VALUES ('48cb35c4-7784-410e-a7bc-9db7cbc77e4f', NULL, 'payments.gift_cards', false, '{}', '2026-07-15 04:55:04.789561+00', '2026-07-15 04:55:04.789561+00');
INSERT INTO af_global.feature_flags VALUES ('7b5b4e3b-4d7f-4fb4-a7ac-f9a117e78a87', NULL, 'integrations.classpass', false, '{}', '2026-07-15 04:55:04.789561+00', '2026-07-15 04:55:04.789561+00');
INSERT INTO af_global.feature_flags VALUES ('f0d1fcd3-c2d4-4820-94cf-7538aa73e0f0', NULL, 'marketing.email_campaigns', false, '{}', '2026-07-15 04:55:04.789561+00', '2026-07-15 04:55:04.789561+00');
INSERT INTO af_global.feature_flags VALUES ('b9938c86-2683-4985-a1fa-6eed66506595', NULL, 'marketing.sms', false, '{}', '2026-07-15 04:55:04.789561+00', '2026-07-15 04:55:04.789561+00');
INSERT INTO af_global.feature_flags VALUES ('17c9135d-11dd-4962-9ed3-0299e29793a6', NULL, 'ai.newsletter_generator', false, '{}', '2026-07-15 04:55:04.789561+00', '2026-07-15 04:55:04.789561+00');
INSERT INTO af_global.feature_flags VALUES ('9e33923d-d5ca-467d-8781-5f8ff18285cb', NULL, 'ai.churn_prediction', false, '{}', '2026-07-15 04:55:04.789561+00', '2026-07-15 04:55:04.789561+00');
INSERT INTO af_global.feature_flags VALUES ('dd4d4d98-235b-4dfb-bccf-05e19f7d4b51', NULL, 'ai.autonomous_resolution', false, '{}', '2026-07-15 04:55:04.789561+00', '2026-07-15 04:55:04.789561+00');
INSERT INTO af_global.feature_flags VALUES ('8c6b31a0-539e-4b3f-9c24-534d39667619', NULL, 'multi_location', false, '{}', '2026-07-15 04:55:04.789561+00', '2026-07-15 04:55:04.789561+00');


--
-- Data for Name: kiosk_devices; Type: TABLE DATA; Schema: af_global; Owner: -
--



--
-- Data for Name: membership_templates; Type: TABLE DATA; Schema: af_global; Owner: -
--

INSERT INTO af_global.membership_templates VALUES ('be4aef58-170f-495f-9a78-0962edb8d404', 'unlimited_in_studio_monthly', 'Unlimited In-Studio (Monthly)', 'Unlimited in-person classes at the studio', 'unlimited', 'in_studio', 14900, 'monthly', NULL, NULL, true, true, 1, '2026-07-15 04:55:05.586297+00');
INSERT INTO af_global.membership_templates VALUES ('c73d0998-e035-4631-8b8b-a1dc8ed7daa9', 'unlimited_in_studio_yearly', 'Unlimited In-Studio (Yearly)', 'Unlimited in-person classes — annual plan with savings', 'unlimited', 'in_studio', 149000, 'yearly', NULL, NULL, true, true, 2, '2026-07-15 04:55:05.586297+00');
INSERT INTO af_global.membership_templates VALUES ('751a432d-aff0-451d-9605-3356a4007c5d', 'unlimited_online_monthly', 'Unlimited Online (Monthly)', 'Unlimited livestream and on-demand video access', 'unlimited', 'online', 9900, 'monthly', NULL, NULL, true, true, 3, '2026-07-15 04:55:05.586297+00');
INSERT INTO af_global.membership_templates VALUES ('0850cbbf-a931-4f58-87a1-760095a3cf31', 'unlimited_online_yearly', 'Unlimited Online (Yearly)', 'Unlimited online access — annual plan with savings', 'unlimited', 'online', 99000, 'yearly', NULL, NULL, true, true, 4, '2026-07-15 04:55:05.586297+00');
INSERT INTO af_global.membership_templates VALUES ('739ecef7-7782-405b-8457-3ec02faa1e58', 'unlimited_all_access_monthly', 'Unlimited All-Access (Monthly)', 'Full access: in-studio classes plus livestream and on-demand video', 'unlimited', 'all_access', 19900, 'monthly', NULL, NULL, true, true, 5, '2026-07-15 04:55:05.586297+00');
INSERT INTO af_global.membership_templates VALUES ('213503c5-e194-4a55-a7b7-1630587bafa3', 'unlimited_all_access_yearly', 'Unlimited All-Access (Yearly)', 'Full all-access — annual plan with savings', 'unlimited', 'all_access', 199000, 'yearly', NULL, NULL, true, true, 6, '2026-07-15 04:55:05.586297+00');
INSERT INTO af_global.membership_templates VALUES ('a17b0579-ae1b-4be9-a750-69ef4b379e9d', 'class_pack_5', '5-Class Pack', 'Bundle of 5 classes, use at your own pace', 'class_pack', 'in_studio', 8500, 'one_time', 5, 90, false, false, 10, '2026-07-15 04:55:05.586297+00');
INSERT INTO af_global.membership_templates VALUES ('0ef3ccc9-397f-41b7-bfd4-8f375eed152c', 'class_pack_10', '10-Class Pack', 'Bundle of 10 classes, great value', 'class_pack', 'in_studio', 15000, 'one_time', 10, 180, false, false, 11, '2026-07-15 04:55:05.586297+00');
INSERT INTO af_global.membership_templates VALUES ('200c7ea3-443a-4056-ab42-545346b2c052', 'class_pack_20', '20-Class Pack', 'Bundle of 20 classes, best per-class rate', 'class_pack', 'in_studio', 26000, 'one_time', 20, 365, false, false, 12, '2026-07-15 04:55:05.586297+00');
INSERT INTO af_global.membership_templates VALUES ('ae39e9a6-efa5-4258-bd55-a3421a300ceb', 'single_class', 'Single Class Drop-In', 'One class visit, no commitment', 'single_class', 'in_studio', 2500, 'one_time', 1, NULL, false, false, 20, '2026-07-15 04:55:05.586297+00');
INSERT INTO af_global.membership_templates VALUES ('45372def-4242-4d13-8c81-73c6a2fbed64', 'intro_30', 'New Student 30-Day Intro', '30 days of unlimited classes for new students', 'intro_offer', 'all_access', 4900, 'one_time', NULL, 30, false, false, 30, '2026-07-15 04:55:05.586297+00');


--
-- Data for Name: organization_users; Type: TABLE DATA; Schema: af_global; Owner: -
--

INSERT INTO af_global.organization_users VALUES ('49f9b222-6fe6-41b4-83e3-48cafe89a101', '50065def-79b0-4550-8dbd-e0b623b2954d', '8bacd899-04c4-471e-adad-820f8f9b0a74', 'owner', true, NULL, NULL, '2026-07-15 04:55:07.588748+00', '2026-07-15 04:55:07.588748+00', NULL, NULL);
INSERT INTO af_global.organization_users VALUES ('b0ef8c26-41f5-4919-91b0-9bbfb8b04eeb', '50065def-79b0-4550-8dbd-e0b623b2954d', 'cbf2bfdd-904a-43b8-93aa-768b4a099785', 'instructor', true, NULL, NULL, '2026-07-15 04:55:07.612341+00', '2026-07-15 04:55:07.612341+00', NULL, NULL);
INSERT INTO af_global.organization_users VALUES ('63f577fb-bdea-466e-80d8-94e6fd0f5d43', '50065def-79b0-4550-8dbd-e0b623b2954d', '4fca6e36-7b1e-4fc9-88c5-691ab6141787', 'instructor', true, NULL, NULL, '2026-07-15 04:55:07.614759+00', '2026-07-15 04:55:07.614759+00', NULL, NULL);
INSERT INTO af_global.organization_users VALUES ('5480624b-8f46-430a-b558-4d96860439da', '50065def-79b0-4550-8dbd-e0b623b2954d', '379a26fa-30e7-4358-b1e3-f3cf9103fccd', 'instructor', true, NULL, NULL, '2026-07-15 04:55:07.616258+00', '2026-07-15 04:55:07.616258+00', NULL, NULL);
INSERT INTO af_global.organization_users VALUES ('42323e71-595b-434e-b790-c4976167018a', '50065def-79b0-4550-8dbd-e0b623b2954d', '27943cc1-1efb-4365-b04f-f91ebcfeb877', 'member', true, NULL, NULL, '2026-07-15 04:55:07.621235+00', '2026-07-15 04:55:07.621235+00', NULL, NULL);
INSERT INTO af_global.organization_users VALUES ('07a01b07-3730-4f17-9649-3634f1a1afd3', '50065def-79b0-4550-8dbd-e0b623b2954d', '8f055020-d340-465c-b44f-bd0059bd3bf6', 'member', true, NULL, NULL, '2026-07-15 04:55:07.622785+00', '2026-07-15 04:55:07.622785+00', NULL, NULL);
INSERT INTO af_global.organization_users VALUES ('8dc9ee17-3a33-4a8b-bf59-5646375634be', '50065def-79b0-4550-8dbd-e0b623b2954d', '9d0ebec0-598f-41cc-919b-895d896cf667', 'member', true, NULL, NULL, '2026-07-15 04:55:07.624345+00', '2026-07-15 04:55:07.624345+00', NULL, NULL);
INSERT INTO af_global.organization_users VALUES ('e15c634d-aa70-4796-b8b7-02c0b227e417', '50065def-79b0-4550-8dbd-e0b623b2954d', 'a3daa7a2-d1bc-43ea-b34e-3f97676c3730', 'member', true, NULL, NULL, '2026-07-15 04:55:07.625835+00', '2026-07-15 04:55:07.625835+00', NULL, NULL);
INSERT INTO af_global.organization_users VALUES ('9b39a19b-208f-4c20-9d5c-0f2c0871163d', '50065def-79b0-4550-8dbd-e0b623b2954d', '654c4dfb-6a3f-42ae-9512-e1240e2f6b91', 'member', true, NULL, NULL, '2026-07-15 04:55:07.627401+00', '2026-07-15 04:55:07.627401+00', NULL, NULL);
INSERT INTO af_global.organization_users VALUES ('3f76b8eb-d4f3-4ff6-b303-91372af596ff', '50065def-79b0-4550-8dbd-e0b623b2954d', '9e2f1753-ffd6-43be-9cfb-e393587e8663', 'member', true, NULL, NULL, '2026-07-15 04:55:07.628969+00', '2026-07-15 04:55:07.628969+00', NULL, NULL);
INSERT INTO af_global.organization_users VALUES ('8b3eeb3c-cb9b-403c-9c20-bd063e5bdde2', '50065def-79b0-4550-8dbd-e0b623b2954d', 'd0c86fde-0638-4a9d-9d86-0747c70295bc', 'member', true, NULL, NULL, '2026-07-15 04:55:07.630555+00', '2026-07-15 04:55:07.630555+00', NULL, NULL);
INSERT INTO af_global.organization_users VALUES ('0f39b640-e406-4f8a-a4bc-d970d8a6a61a', '50065def-79b0-4550-8dbd-e0b623b2954d', 'c8e41d5d-fdb2-4542-93fc-88aba0a1001c', 'member', true, NULL, NULL, '2026-07-15 04:55:07.632094+00', '2026-07-15 04:55:07.632094+00', NULL, NULL);
INSERT INTO af_global.organization_users VALUES ('0d9b205d-bc81-49d9-8303-4c69f3a034f8', '50065def-79b0-4550-8dbd-e0b623b2954d', 'f1d9a096-76fc-4904-89c7-eac8aca7d82c', 'member', true, NULL, NULL, '2026-07-15 04:55:07.633652+00', '2026-07-15 04:55:07.633652+00', NULL, NULL);
INSERT INTO af_global.organization_users VALUES ('4271abb9-8998-4cdb-bd73-4754fe149b56', '50065def-79b0-4550-8dbd-e0b623b2954d', '56fe023d-c097-42df-b2e1-5932a113e531', 'member', true, NULL, NULL, '2026-07-15 04:55:07.635223+00', '2026-07-15 04:55:07.635223+00', NULL, NULL);


--
-- Data for Name: organizations; Type: TABLE DATA; Schema: af_global; Owner: -
--

INSERT INTO af_global.organizations VALUES ('50065def-79b0-4550-8dbd-e0b623b2954d', 'sunrise-yoga', 'Sunrise Yoga Studio', 'af_tenant_sunrise_yoga', 'trial', NULL, NULL, NULL, NULL, NULL, NULL, '#4F46E5', NULL, 'America/Los_Angeles', 'US', 'USD', '2026-07-15 04:55:05.002176+00', '2026-07-15 04:55:05.002176+00', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, true, false, NULL, NULL, NULL, NULL, NULL, false, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, false, '{}', '{}', NULL, NULL, NULL, NULL, NULL, 'square', NULL, false, NULL, NULL);


--
-- Data for Name: platform_ads_config; Type: TABLE DATA; Schema: af_global; Owner: -
--

INSERT INTO af_global.platform_ads_config VALUES ('b3b82cf3-0726-46bc-b5a8-d35ae1cab00f', 0, 0, '[]', false, false, false, 5000, '2026-07-15 04:55:05.586297+00', '2026-07-15 04:55:05.586297+00');


--
-- Data for Name: platform_ai_agent_log; Type: TABLE DATA; Schema: af_global; Owner: -
--



--
-- Data for Name: platform_announcements; Type: TABLE DATA; Schema: af_global; Owner: -
--



--
-- Data for Name: platform_backup_schedule; Type: TABLE DATA; Schema: af_global; Owner: -
--

INSERT INTO af_global.platform_backup_schedule VALUES ('7430163b-aa2c-4fc9-b71b-da0ac1396fb4', 'database', '0 3 * * *', 30, true, NULL, NULL, '2026-07-15 04:55:05.586297+00', '2026-07-15 04:55:05.586297+00');
INSERT INTO af_global.platform_backup_schedule VALUES ('6d733eee-3985-4071-8bbd-4fece94f0afa', 'files', '0 4 * * 0', 60, true, NULL, NULL, '2026-07-15 04:55:05.586297+00', '2026-07-15 04:55:05.586297+00');


--
-- Data for Name: platform_backups; Type: TABLE DATA; Schema: af_global; Owner: -
--



--
-- Data for Name: platform_config; Type: TABLE DATA; Schema: af_global; Owner: -
--

INSERT INTO af_global.platform_config VALUES ('b6b302ee-49c8-424c-bb3b-1245314c08ef', NULL, 'hello@example.com', 'AuraFlow', NULL, 'alerts@example.com', 'alerts@example.com', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-07-15 04:55:05.586297+00', '2026-07-15 04:55:05.586297+00');


--
-- Data for Name: platform_email_accounts; Type: TABLE DATA; Schema: af_global; Owner: -
--



--
-- Data for Name: platform_email_inbox; Type: TABLE DATA; Schema: af_global; Owner: -
--



--
-- Data for Name: platform_invoices; Type: TABLE DATA; Schema: af_global; Owner: -
--



--
-- Data for Name: platform_landing_pages; Type: TABLE DATA; Schema: af_global; Owner: -
--



--
-- Data for Name: platform_metrics_daily; Type: TABLE DATA; Schema: af_global; Owner: -
--



--
-- Data for Name: platform_request_metrics; Type: TABLE DATA; Schema: af_global; Owner: -
--



--
-- Data for Name: platform_security_events; Type: TABLE DATA; Schema: af_global; Owner: -
--



--
-- Data for Name: platform_settings; Type: TABLE DATA; Schema: af_global; Owner: -
--

INSERT INTO af_global.platform_settings VALUES ('ai_token_rate_cents_per_1k', '3.0', 'Cost per 1,000 AI tokens in cents (after free tier)', '2026-07-15 04:55:05.586297+00', NULL);
INSERT INTO af_global.platform_settings VALUES ('ai_token_free_tier', '50000', 'Free tokens per organization per month', '2026-07-15 04:55:05.586297+00', NULL);
INSERT INTO af_global.platform_settings VALUES ('ai_token_billing_enabled', '"true"', 'Whether AI token billing is active', '2026-07-15 04:55:05.586297+00', NULL);
INSERT INTO af_global.platform_settings VALUES ('ai_token_stripe_meter_id', 'null', 'Stripe Billing Meter ID for ai_tokens', '2026-07-15 04:55:05.586297+00', NULL);
INSERT INTO af_global.platform_settings VALUES ('ai_token_stripe_price_id', 'null', 'Stripe Price ID for metered AI usage', '2026-07-15 04:55:05.586297+00', NULL);


--
-- Data for Name: platform_social_messages; Type: TABLE DATA; Schema: af_global; Owner: -
--



--
-- Data for Name: platform_social_posts; Type: TABLE DATA; Schema: af_global; Owner: -
--



--
-- Data for Name: pos_checkout_index; Type: TABLE DATA; Schema: af_global; Owner: -
--



--
-- Data for Name: processed_webhook_events; Type: TABLE DATA; Schema: af_global; Owner: -
--



--
-- Data for Name: refresh_tokens; Type: TABLE DATA; Schema: af_global; Owner: -
--

INSERT INTO af_global.refresh_tokens VALUES ('65c0e294-5364-4134-8bb2-40cff7671042', '8bacd899-04c4-471e-adad-820f8f9b0a74', 'fbfde775b6b93a4bd861d529423a895fcfc38b6bfff994f3547bafd60132c9dc', '2026-08-14 04:55:08.571268+00', NULL, '2026-07-15 04:55:08.571478+00', '87da89131acc05cb861c80340d3d7610f6b74ee9', '172.20.0.1', '2026-07-15 04:55:08.571478+00');


--
-- Data for Name: square_pos_devices; Type: TABLE DATA; Schema: af_global; Owner: -
--



--
-- Data for Name: users; Type: TABLE DATA; Schema: af_global; Owner: -
--

INSERT INTO af_global.users VALUES ('cbf2bfdd-904a-43b8-93aa-768b4a099785', 'maya@example.com', false, '$2b$12$uXkNxR86lzR0hxj/97kI9uEszFoDypFQzQVT2ve672C/RKDS2IIsi', 'Maya', 'Johnson', NULL, NULL, false, true, NULL, '2026-07-15 04:55:07.611722+00', '2026-07-15 04:55:07.611722+00', NULL, false, NULL, false, false);
INSERT INTO af_global.users VALUES ('4fca6e36-7b1e-4fc9-88c5-691ab6141787', 'alex@example.com', false, '$2b$12$uXkNxR86lzR0hxj/97kI9uEszFoDypFQzQVT2ve672C/RKDS2IIsi', 'Alex', 'Rivera', NULL, NULL, false, true, NULL, '2026-07-15 04:55:07.614433+00', '2026-07-15 04:55:07.614433+00', NULL, false, NULL, false, false);
INSERT INTO af_global.users VALUES ('379a26fa-30e7-4358-b1e3-f3cf9103fccd', 'sam@example.com', false, '$2b$12$uXkNxR86lzR0hxj/97kI9uEszFoDypFQzQVT2ve672C/RKDS2IIsi', 'Sam', 'Patel', NULL, NULL, false, true, NULL, '2026-07-15 04:55:07.615949+00', '2026-07-15 04:55:07.615949+00', NULL, false, NULL, false, false);
INSERT INTO af_global.users VALUES ('27943cc1-1efb-4365-b04f-f91ebcfeb877', 'demo1@example.com', false, '$2b$12$uXkNxR86lzR0hxj/97kI9uEszFoDypFQzQVT2ve672C/RKDS2IIsi', 'Alice', 'Demo', NULL, NULL, false, true, NULL, '2026-07-15 04:55:07.620861+00', '2026-07-15 04:55:07.620861+00', NULL, false, NULL, true, false);
INSERT INTO af_global.users VALUES ('8f055020-d340-465c-b44f-bd0059bd3bf6', 'demo2@example.com', false, '$2b$12$uXkNxR86lzR0hxj/97kI9uEszFoDypFQzQVT2ve672C/RKDS2IIsi', 'Bob', 'Demo', NULL, NULL, false, true, NULL, '2026-07-15 04:55:07.622433+00', '2026-07-15 04:55:07.622433+00', NULL, false, NULL, true, false);
INSERT INTO af_global.users VALUES ('9d0ebec0-598f-41cc-919b-895d896cf667', 'demo3@example.com', false, '$2b$12$uXkNxR86lzR0hxj/97kI9uEszFoDypFQzQVT2ve672C/RKDS2IIsi', 'Carol', 'Demo', NULL, NULL, false, true, NULL, '2026-07-15 04:55:07.623962+00', '2026-07-15 04:55:07.623962+00', NULL, false, NULL, true, false);
INSERT INTO af_global.users VALUES ('a3daa7a2-d1bc-43ea-b34e-3f97676c3730', 'demo4@example.com', false, '$2b$12$uXkNxR86lzR0hxj/97kI9uEszFoDypFQzQVT2ve672C/RKDS2IIsi', 'David', 'Demo', NULL, NULL, false, true, NULL, '2026-07-15 04:55:07.625418+00', '2026-07-15 04:55:07.625418+00', NULL, false, NULL, true, false);
INSERT INTO af_global.users VALUES ('654c4dfb-6a3f-42ae-9512-e1240e2f6b91', 'demo5@example.com', false, '$2b$12$uXkNxR86lzR0hxj/97kI9uEszFoDypFQzQVT2ve672C/RKDS2IIsi', 'Eva', 'Demo', NULL, NULL, false, true, NULL, '2026-07-15 04:55:07.626983+00', '2026-07-15 04:55:07.626983+00', NULL, false, NULL, true, false);
INSERT INTO af_global.users VALUES ('9e2f1753-ffd6-43be-9cfb-e393587e8663', 'demo6@example.com', false, '$2b$12$uXkNxR86lzR0hxj/97kI9uEszFoDypFQzQVT2ve672C/RKDS2IIsi', 'Frank', 'Demo', NULL, NULL, false, true, NULL, '2026-07-15 04:55:07.628558+00', '2026-07-15 04:55:07.628558+00', NULL, false, NULL, true, false);
INSERT INTO af_global.users VALUES ('d0c86fde-0638-4a9d-9d86-0747c70295bc', 'demo7@example.com', false, '$2b$12$uXkNxR86lzR0hxj/97kI9uEszFoDypFQzQVT2ve672C/RKDS2IIsi', 'Grace', 'Demo', NULL, NULL, false, true, NULL, '2026-07-15 04:55:07.630114+00', '2026-07-15 04:55:07.630114+00', NULL, false, NULL, true, false);
INSERT INTO af_global.users VALUES ('c8e41d5d-fdb2-4542-93fc-88aba0a1001c', 'demo8@example.com', false, '$2b$12$uXkNxR86lzR0hxj/97kI9uEszFoDypFQzQVT2ve672C/RKDS2IIsi', 'Henry', 'Demo', NULL, NULL, false, true, NULL, '2026-07-15 04:55:07.631664+00', '2026-07-15 04:55:07.631664+00', NULL, false, NULL, true, false);
INSERT INTO af_global.users VALUES ('f1d9a096-76fc-4904-89c7-eac8aca7d82c', 'demo9@example.com', false, '$2b$12$uXkNxR86lzR0hxj/97kI9uEszFoDypFQzQVT2ve672C/RKDS2IIsi', 'Iris', 'Demo', NULL, NULL, false, true, NULL, '2026-07-15 04:55:07.633228+00', '2026-07-15 04:55:07.633228+00', NULL, false, NULL, true, false);
INSERT INTO af_global.users VALUES ('56fe023d-c097-42df-b2e1-5932a113e531', 'demo10@example.com', false, '$2b$12$uXkNxR86lzR0hxj/97kI9uEszFoDypFQzQVT2ve672C/RKDS2IIsi', 'Jack', 'Demo', NULL, NULL, false, true, NULL, '2026-07-15 04:55:07.634787+00', '2026-07-15 04:55:07.634787+00', NULL, false, NULL, true, false);
INSERT INTO af_global.users VALUES ('8bacd899-04c4-471e-adad-820f8f9b0a74', 'owner@sunrise-yoga.example.com', false, '$2b$12$uXkNxR86lzR0hxj/97kI9uEszFoDypFQzQVT2ve672C/RKDS2IIsi', 'Studio', 'Owner', NULL, NULL, false, true, '2026-07-15 04:55:08.561068+00', '2026-07-15 04:55:07.585093+00', '2026-07-15 04:55:08.561068+00', NULL, false, NULL, false, false);


--
-- Data for Name: acct_categories; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: acct_members; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: acct_owner_draws; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: acct_payout_items; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: acct_payouts; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: acct_settings; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: acct_transactions; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: acct_vendor_rules; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: api_keys; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: bookings; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: class_series; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: class_sessions; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: class_types; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--

INSERT INTO af_tenant_sunrise_yoga.class_types VALUES ('b4d2d932-ce11-409b-ba97-79389d3fb7c8', '79c93b7d-7dea-45fb-ab86-e7ec84af8d42', 'Vinyasa Flow', NULL, 60, '#4F46E5', 25, true, '2026-07-15 04:55:07.617706+00', 'all_levels', '{}', NULL, NULL);
INSERT INTO af_tenant_sunrise_yoga.class_types VALUES ('1d9d9ab7-e6c0-4a80-9409-f359fd0675ee', '79c93b7d-7dea-45fb-ab86-e7ec84af8d42', 'Yin Yoga', NULL, 75, '#7C3AED', 20, true, '2026-07-15 04:55:07.618142+00', 'all_levels', '{}', NULL, NULL);
INSERT INTO af_tenant_sunrise_yoga.class_types VALUES ('3d3928eb-4167-4807-85d4-f96bdc61a9a2', '79c93b7d-7dea-45fb-ab86-e7ec84af8d42', 'Power Yoga', NULL, 60, '#DC2626', 20, true, '2026-07-15 04:55:07.618643+00', 'intermediate', '{}', NULL, NULL);
INSERT INTO af_tenant_sunrise_yoga.class_types VALUES ('5237c645-8493-49a9-8b7f-01de14ed141a', '79c93b7d-7dea-45fb-ab86-e7ec84af8d42', 'Meditation', NULL, 45, '#059669', 30, true, '2026-07-15 04:55:07.61915+00', 'all_levels', '{}', NULL, NULL);
INSERT INTO af_tenant_sunrise_yoga.class_types VALUES ('2fdcb5e0-b0da-487f-bbc2-e3abc94b26b0', '79c93b7d-7dea-45fb-ab86-e7ec84af8d42', 'Beginner Yoga', NULL, 60, '#2563EB', 25, true, '2026-07-15 04:55:07.619675+00', 'beginner', '{}', NULL, NULL);


--
-- Data for Name: classpass_config; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: classpass_reservations; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: communication_log; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: course_enrollments; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: course_session_attendance; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: course_sessions; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: courses; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: de34_filings; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: email_campaign_sends; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: email_campaigns; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: employee_w4_forms; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: employer_profile; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: emr_encounter_log; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: emr_patient_map; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: emr_sync_log; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: equipment; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: facility_schedule_completions; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: facility_schedules; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: failed_payment_attempts; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: gdpr_deletion_requests; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: guest_instructors; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: instructor_availability; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: instructors; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--

INSERT INTO af_tenant_sunrise_yoga.instructors VALUES ('8ddee03f-97b5-4078-8b67-7aa4b9871b86', 'cbf2bfdd-904a-43b8-93aa-768b4a099785', 'Maya Johnson', 'RYT-500 certified with 10 years of experience in Vinyasa and Yin yoga.', NULL, NULL, NULL, NULL, true, '2026-07-15 04:55:07.613735+00', '2026-07-15 04:55:07.613735+00', NULL, 'per_class', '1099', 'maya@example.com', NULL, '#4F46E5', 0, NULL);
INSERT INTO af_tenant_sunrise_yoga.instructors VALUES ('32a0bc22-f8ec-4544-ae39-0d2eb37588cc', '4fca6e36-7b1e-4fc9-88c5-691ab6141787', 'Alex Rivera', 'Former athlete turned yoga teacher, specializing in Power Yoga and conditioning.', NULL, NULL, NULL, NULL, true, '2026-07-15 04:55:07.615346+00', '2026-07-15 04:55:07.615346+00', NULL, 'per_class', '1099', 'alex@example.com', NULL, '#4F46E5', 0, NULL);
INSERT INTO af_tenant_sunrise_yoga.instructors VALUES ('92d4e2fe-fc22-4ddb-a3f3-fd6916daeb72', '379a26fa-30e7-4358-b1e3-f3cf9103fccd', 'Sam Patel', 'Meditation and mindfulness teacher with a background in Ayurveda.', NULL, NULL, NULL, NULL, true, '2026-07-15 04:55:07.616841+00', '2026-07-15 04:55:07.616841+00', NULL, 'per_class', '1099', 'sam@example.com', NULL, '#4F46E5', 0, NULL);


--
-- Data for Name: inventory; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: inventory_transactions; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: job_application_documents; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: job_application_events; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: job_applications; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: maintenance_requests; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: marketing_drafts; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: member_credits; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: member_health_data; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: member_memberships; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: member_milestones; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: member_notes; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: members; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--

INSERT INTO af_tenant_sunrise_yoga.members VALUES ('05ae2ff0-7995-4a88-ab62-b34ca4dc3c30', '27943cc1-1efb-4365-b04f-f91ebcfeb877', NULL, 'Alice', 'Demo', 'demo1@example.com', NULL, NULL, NULL, true, '2026-07-15 04:55:07.621809+00', '2026-07-15 04:55:07.621809+00', '2026-07-15 04:55:07.621809+00', NULL, 'manual', NULL, NULL, 0, 0, true, true, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO af_tenant_sunrise_yoga.members VALUES ('0900d100-49f1-47c1-8e94-53b249600731', '8f055020-d340-465c-b44f-bd0059bd3bf6', NULL, 'Bob', 'Demo', 'demo2@example.com', NULL, NULL, NULL, true, '2026-07-15 04:55:07.623361+00', '2026-07-15 04:55:07.623361+00', '2026-07-15 04:55:07.623361+00', NULL, 'manual', NULL, NULL, 0, 0, true, true, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO af_tenant_sunrise_yoga.members VALUES ('157f1b62-5ba2-4226-bc21-264c4d76efe1', '9d0ebec0-598f-41cc-919b-895d896cf667', NULL, 'Carol', 'Demo', 'demo3@example.com', NULL, NULL, NULL, true, '2026-07-15 04:55:07.624852+00', '2026-07-15 04:55:07.624852+00', '2026-07-15 04:55:07.624852+00', NULL, 'manual', NULL, NULL, 0, 0, true, true, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO af_tenant_sunrise_yoga.members VALUES ('48c266c7-a731-4db2-96e5-e36c81623255', 'a3daa7a2-d1bc-43ea-b34e-3f97676c3730', NULL, 'David', 'Demo', 'demo4@example.com', NULL, NULL, NULL, true, '2026-07-15 04:55:07.626417+00', '2026-07-15 04:55:07.626417+00', '2026-07-15 04:55:07.626417+00', NULL, 'manual', NULL, NULL, 0, 0, true, true, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO af_tenant_sunrise_yoga.members VALUES ('bb3cf981-34ad-496f-9aa5-fabab3a25b83', '654c4dfb-6a3f-42ae-9512-e1240e2f6b91', NULL, 'Eva', 'Demo', 'demo5@example.com', NULL, NULL, NULL, true, '2026-07-15 04:55:07.627974+00', '2026-07-15 04:55:07.627974+00', '2026-07-15 04:55:07.627974+00', NULL, 'manual', NULL, NULL, 0, 0, true, true, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO af_tenant_sunrise_yoga.members VALUES ('7022fda2-b3a8-4079-9921-1e3b48070569', '9e2f1753-ffd6-43be-9cfb-e393587e8663', NULL, 'Frank', 'Demo', 'demo6@example.com', NULL, NULL, NULL, true, '2026-07-15 04:55:07.629534+00', '2026-07-15 04:55:07.629534+00', '2026-07-15 04:55:07.629534+00', NULL, 'manual', NULL, NULL, 0, 0, true, true, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO af_tenant_sunrise_yoga.members VALUES ('2481e7e3-769c-42d9-90b4-b998b2ceec0d', 'd0c86fde-0638-4a9d-9d86-0747c70295bc', NULL, 'Grace', 'Demo', 'demo7@example.com', NULL, NULL, NULL, true, '2026-07-15 04:55:07.631114+00', '2026-07-15 04:55:07.631114+00', '2026-07-15 04:55:07.631114+00', NULL, 'manual', NULL, NULL, 0, 0, true, true, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO af_tenant_sunrise_yoga.members VALUES ('fb716984-021c-4419-94cb-3ce56c5ad4e3', 'c8e41d5d-fdb2-4542-93fc-88aba0a1001c', NULL, 'Henry', 'Demo', 'demo8@example.com', NULL, NULL, NULL, true, '2026-07-15 04:55:07.632669+00', '2026-07-15 04:55:07.632669+00', '2026-07-15 04:55:07.632669+00', NULL, 'manual', NULL, NULL, 0, 0, true, true, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO af_tenant_sunrise_yoga.members VALUES ('7ceab745-63aa-4a7e-84b9-f48ea7a41d4c', 'f1d9a096-76fc-4904-89c7-eac8aca7d82c', NULL, 'Iris', 'Demo', 'demo9@example.com', NULL, NULL, NULL, true, '2026-07-15 04:55:07.634232+00', '2026-07-15 04:55:07.634232+00', '2026-07-15 04:55:07.634232+00', NULL, 'manual', NULL, NULL, 0, 0, true, true, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO af_tenant_sunrise_yoga.members VALUES ('379eab68-beeb-4248-8b01-5e6128f5a592', '56fe023d-c097-42df-b2e1-5932a113e531', NULL, 'Jack', 'Demo', 'demo10@example.com', NULL, NULL, NULL, true, '2026-07-15 04:55:07.635794+00', '2026-07-15 04:55:07.635794+00', '2026-07-15 04:55:07.635794+00', NULL, 'manual', NULL, NULL, 0, 0, true, true, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);


--
-- Data for Name: membership_types; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--

INSERT INTO af_tenant_sunrise_yoga.membership_types VALUES ('1dffae97-704a-441a-baa2-6ff8f8992e37', '79c93b7d-7dea-45fb-ab86-e7ec84af8d42', 'Drop-in', NULL, 'day_pass', 1, 2000, 'one_time', 1, NULL, true, true, 0, '2026-07-15 04:55:07.591634+00', false, NULL, true, 0, false, 30, 0, NULL, '2026-07-15 04:55:07.591634+00', 'in_studio', false, NULL, NULL, NULL, false, false, false, NULL, NULL, NULL);
INSERT INTO af_tenant_sunrise_yoga.membership_types VALUES ('7e62074b-a7be-4a74-83f3-156f2d8b1489', '79c93b7d-7dea-45fb-ab86-e7ec84af8d42', '10-Class Pack', NULL, 'class_pack', 10, 15000, 'one_time', 90, NULL, true, true, 0, '2026-07-15 04:55:07.592169+00', false, NULL, true, 0, false, 30, 0, NULL, '2026-07-15 04:55:07.592169+00', 'in_studio', false, NULL, NULL, NULL, false, false, false, NULL, NULL, NULL);
INSERT INTO af_tenant_sunrise_yoga.membership_types VALUES ('c9d9b876-5732-4b24-a43a-e3abc4aa2d81', '79c93b7d-7dea-45fb-ab86-e7ec84af8d42', 'Monthly Unlimited', NULL, 'unlimited', NULL, 9900, 'monthly', NULL, NULL, true, true, 0, '2026-07-15 04:55:07.592655+00', false, NULL, true, 0, false, 30, 0, NULL, '2026-07-15 04:55:07.592655+00', 'in_studio', false, NULL, NULL, NULL, false, false, false, NULL, NULL, NULL);
INSERT INTO af_tenant_sunrise_yoga.membership_types VALUES ('64b3ccf4-0dff-4778-82c4-70ed1130cb9d', '79c93b7d-7dea-45fb-ab86-e7ec84af8d42', 'Annual Unlimited', NULL, 'unlimited', NULL, 89900, 'yearly', NULL, NULL, true, true, 0, '2026-07-15 04:55:07.593164+00', false, NULL, true, 0, false, 30, 0, NULL, '2026-07-15 04:55:07.593164+00', 'in_studio', false, NULL, NULL, NULL, false, false, false, NULL, NULL, NULL);


--
-- Data for Name: onboarding_documents; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: onboarding_packets; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: payroll_employee_mapping; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: payroll_line_items; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: payroll_runs; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: pos_line_items; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: pos_terminal_checkouts; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: pos_transactions; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: price_adjustments_log; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: pricing_rules; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: private_bookings; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: private_services; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: products; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: resolution_requests; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: reviews; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: rooms; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: sms_campaign_sends; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: sms_campaigns; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: sms_messages; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: sms_templates; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--

INSERT INTO af_tenant_sunrise_yoga.sms_templates VALUES ('2dc1b394-84bd-4230-8c0c-e57bb3b63362', 'Booking Confirmation', 'booking_confirmation', 'Hi {{member_name}}! You''re booked for {{class_title}} on {{session_date}} at {{session_time}}. See you there!', 'Sent when a member books a class', '{member_name,class_title,session_date,session_time}', 'booking', true, NULL, '2026-07-15 04:55:05.586297+00', '2026-07-15 04:55:05.586297+00');
INSERT INTO af_tenant_sunrise_yoga.sms_templates VALUES ('33cdf540-112b-49d8-92c2-97d852af9a86', 'Booking Cancellation', 'booking_cancellation', 'Hi {{member_name}}, your booking for {{class_title}} on {{session_date}} has been cancelled.', 'Sent when a booking is cancelled', '{member_name,class_title,session_date}', 'cancellation', true, NULL, '2026-07-15 04:55:05.586297+00', '2026-07-15 04:55:05.586297+00');
INSERT INTO af_tenant_sunrise_yoga.sms_templates VALUES ('45c50820-b27a-4be4-adde-80c21ef7d278', 'Class Reminder', 'class_reminder', 'Reminder: {{member_name}}, your {{class_title}} class starts at {{session_time}} today. See you soon!', 'Sent 2 hours before class', '{member_name,class_title,session_time}', 'reminder', true, NULL, '2026-07-15 04:55:05.586297+00', '2026-07-15 04:55:05.586297+00');
INSERT INTO af_tenant_sunrise_yoga.sms_templates VALUES ('6f581ba7-74ea-40e6-96ab-04d5172cfedf', 'Waitlist Promotion', 'waitlist_promotion', 'Great news {{member_name}}! A spot opened up in {{class_title}} on {{session_date}} at {{session_time}}. You''re confirmed!', 'Sent when promoted from waitlist', '{member_name,class_title,session_date,session_time}', 'waitlist', true, NULL, '2026-07-15 04:55:05.586297+00', '2026-07-15 04:55:05.586297+00');
INSERT INTO af_tenant_sunrise_yoga.sms_templates VALUES ('4daf7f23-0684-483e-9fe1-810f515ee2f0', 'Payment Failed', 'payment_failed', 'Hi {{member_name}}, your payment of {{amount}} could not be processed. Please update your payment method.', 'Sent on failed payment', '{member_name,amount}', 'payment', true, NULL, '2026-07-15 04:55:05.586297+00', '2026-07-15 04:55:05.586297+00');
INSERT INTO af_tenant_sunrise_yoga.sms_templates VALUES ('00f8bc1f-4345-4d83-8ef5-f3d24f9dd933', 'Welcome', 'welcome', 'Welcome to {{studio_name}}, {{member_name}}! We''re excited to have you. Book your first class today!', 'Sent to new members', '{member_name,studio_name}', 'welcome', true, NULL, '2026-07-15 04:55:05.586297+00', '2026-07-15 04:55:05.586297+00');
INSERT INTO af_tenant_sunrise_yoga.sms_templates VALUES ('2f7da063-4f87-4524-98d7-1e1c96d8b628', 'Winback', 'winback', 'We miss you, {{member_name}}! It''s been a while since your last visit. Come back and try a class this week!', 'Sent to members at risk of churning', '{member_name}', 'winback', true, NULL, '2026-07-15 04:55:05.586297+00', '2026-07-15 04:55:05.586297+00');
INSERT INTO af_tenant_sunrise_yoga.sms_templates VALUES ('50c8a4f9-bcfc-4dcb-a2dc-0cf5c3754bd8', 'Milestone Celebration', 'milestone', 'Congratulations {{member_name}}! You just hit {{milestone}} classes! Keep up the amazing work!', 'Sent when a member reaches a class milestone', '{member_name,milestone}', 'milestone', true, NULL, '2026-07-15 04:55:05.586297+00', '2026-07-15 04:55:05.586297+00');


--
-- Data for Name: studios; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--

INSERT INTO af_tenant_sunrise_yoga.studios VALUES ('79c93b7d-7dea-45fb-ab86-e7ec84af8d42', '50065def-79b0-4550-8dbd-e0b623b2954d', 'Sunrise Yoga Studio', 'sunrise-yoga', NULL, NULL, 'Portland', 'OR', NULL, 'US', NULL, NULL, 'America/Los_Angeles', false, true, '{}', '2026-07-15 04:55:07.590493+00', '2026-07-15 04:55:07.590493+00', 12, 0, 14, false, 'fifo');


--
-- Data for Name: sub_finder_requests; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: time_entries; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: transactions; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: video_categories; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: video_membership_access; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: video_views; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: videos; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: waiver_signatures; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: waiver_templates; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
-- Data for Name: workshop_contracts; Type: TABLE DATA; Schema: af_tenant_sunrise_yoga; Owner: -
--



--
--



--
-- Name: ai_token_usage ai_token_usage_pkey; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.ai_token_usage
    ADD CONSTRAINT ai_token_usage_pkey PRIMARY KEY (id);


--
-- Name: api_key_routing api_key_routing_pkey; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.api_key_routing
    ADD CONSTRAINT api_key_routing_pkey PRIMARY KEY (key_prefix);


--
-- Name: audit_log audit_log_pkey; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.audit_log
    ADD CONSTRAINT audit_log_pkey PRIMARY KEY (id);


--
-- Name: dead_letter_tasks dead_letter_tasks_pkey; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.dead_letter_tasks
    ADD CONSTRAINT dead_letter_tasks_pkey PRIMARY KEY (id);


--
-- Name: dead_letter_tasks dead_letter_tasks_task_id_key; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.dead_letter_tasks
    ADD CONSTRAINT dead_letter_tasks_task_id_key UNIQUE (task_id);


--
-- Name: feature_flags feature_flags_organization_id_flag_key_key; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.feature_flags
    ADD CONSTRAINT feature_flags_organization_id_flag_key_key UNIQUE (organization_id, flag_key);


--
-- Name: feature_flags feature_flags_pkey; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.feature_flags
    ADD CONSTRAINT feature_flags_pkey PRIMARY KEY (id);


--
-- Name: kiosk_devices kiosk_devices_device_token_key; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.kiosk_devices
    ADD CONSTRAINT kiosk_devices_device_token_key UNIQUE (device_token);


--
-- Name: kiosk_devices kiosk_devices_pkey; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.kiosk_devices
    ADD CONSTRAINT kiosk_devices_pkey PRIMARY KEY (id);


--
-- Name: membership_templates membership_templates_pkey; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.membership_templates
    ADD CONSTRAINT membership_templates_pkey PRIMARY KEY (id);


--
-- Name: membership_templates membership_templates_template_key_key; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.membership_templates
    ADD CONSTRAINT membership_templates_template_key_key UNIQUE (template_key);


--
-- Name: organization_users organization_users_organization_id_user_id_key; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.organization_users
    ADD CONSTRAINT organization_users_organization_id_user_id_key UNIQUE (organization_id, user_id);


--
-- Name: organization_users organization_users_pkey; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.organization_users
    ADD CONSTRAINT organization_users_pkey PRIMARY KEY (id);


--
-- Name: organizations organizations_pkey; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.organizations
    ADD CONSTRAINT organizations_pkey PRIMARY KEY (id);


--
-- Name: organizations organizations_schema_name_key; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.organizations
    ADD CONSTRAINT organizations_schema_name_key UNIQUE (schema_name);


--
-- Name: organizations organizations_slug_key; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.organizations
    ADD CONSTRAINT organizations_slug_key UNIQUE (slug);


--
-- Name: platform_ads_config platform_ads_config_pkey; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.platform_ads_config
    ADD CONSTRAINT platform_ads_config_pkey PRIMARY KEY (id);


--
-- Name: platform_ai_agent_log platform_ai_agent_log_pkey; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.platform_ai_agent_log
    ADD CONSTRAINT platform_ai_agent_log_pkey PRIMARY KEY (id);


--
-- Name: platform_announcements platform_announcements_pkey; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.platform_announcements
    ADD CONSTRAINT platform_announcements_pkey PRIMARY KEY (id);


--
-- Name: platform_backup_schedule platform_backup_schedule_pkey; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.platform_backup_schedule
    ADD CONSTRAINT platform_backup_schedule_pkey PRIMARY KEY (id);


--
-- Name: platform_backups platform_backups_pkey; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.platform_backups
    ADD CONSTRAINT platform_backups_pkey PRIMARY KEY (id);


--
-- Name: platform_config platform_config_pkey; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.platform_config
    ADD CONSTRAINT platform_config_pkey PRIMARY KEY (id);


--
-- Name: platform_email_accounts platform_email_accounts_email_address_key; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.platform_email_accounts
    ADD CONSTRAINT platform_email_accounts_email_address_key UNIQUE (email_address);


--
-- Name: platform_email_accounts platform_email_accounts_pkey; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.platform_email_accounts
    ADD CONSTRAINT platform_email_accounts_pkey PRIMARY KEY (id);


--
-- Name: platform_email_inbox platform_email_inbox_pkey; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.platform_email_inbox
    ADD CONSTRAINT platform_email_inbox_pkey PRIMARY KEY (id);


--
-- Name: platform_invoices platform_invoices_organization_id_period_start_key; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.platform_invoices
    ADD CONSTRAINT platform_invoices_organization_id_period_start_key UNIQUE (organization_id, period_start);


--
-- Name: platform_invoices platform_invoices_pkey; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.platform_invoices
    ADD CONSTRAINT platform_invoices_pkey PRIMARY KEY (id);


--
-- Name: platform_invoices platform_invoices_square_invoice_id_key; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.platform_invoices
    ADD CONSTRAINT platform_invoices_square_invoice_id_key UNIQUE (square_invoice_id);


--
-- Name: platform_landing_pages platform_landing_pages_pkey; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.platform_landing_pages
    ADD CONSTRAINT platform_landing_pages_pkey PRIMARY KEY (id);


--
-- Name: platform_landing_pages platform_landing_pages_slug_key; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.platform_landing_pages
    ADD CONSTRAINT platform_landing_pages_slug_key UNIQUE (slug);


--
-- Name: platform_metrics_daily platform_metrics_daily_metric_date_key; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.platform_metrics_daily
    ADD CONSTRAINT platform_metrics_daily_metric_date_key UNIQUE (metric_date);


--
-- Name: platform_metrics_daily platform_metrics_daily_pkey; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.platform_metrics_daily
    ADD CONSTRAINT platform_metrics_daily_pkey PRIMARY KEY (id);


--
-- Name: platform_request_metrics platform_request_metrics_pkey; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.platform_request_metrics
    ADD CONSTRAINT platform_request_metrics_pkey PRIMARY KEY (id);


--
-- Name: platform_security_events platform_security_events_pkey; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.platform_security_events
    ADD CONSTRAINT platform_security_events_pkey PRIMARY KEY (id);


--
-- Name: platform_settings platform_settings_pkey; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.platform_settings
    ADD CONSTRAINT platform_settings_pkey PRIMARY KEY (key);


--
-- Name: platform_social_messages platform_social_messages_pkey; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.platform_social_messages
    ADD CONSTRAINT platform_social_messages_pkey PRIMARY KEY (id);


--
-- Name: platform_social_posts platform_social_posts_pkey; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.platform_social_posts
    ADD CONSTRAINT platform_social_posts_pkey PRIMARY KEY (id);


--
-- Name: pos_checkout_index pos_checkout_index_pkey; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.pos_checkout_index
    ADD CONSTRAINT pos_checkout_index_pkey PRIMARY KEY (checkout_id);


--
-- Name: processed_webhook_events processed_webhook_events_pkey; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.processed_webhook_events
    ADD CONSTRAINT processed_webhook_events_pkey PRIMARY KEY (provider, event_id);


--
-- Name: refresh_tokens refresh_tokens_pkey; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.refresh_tokens
    ADD CONSTRAINT refresh_tokens_pkey PRIMARY KEY (id);


--
-- Name: refresh_tokens refresh_tokens_token_hash_key; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.refresh_tokens
    ADD CONSTRAINT refresh_tokens_token_hash_key UNIQUE (token_hash);


--
-- Name: square_pos_devices square_pos_devices_organization_id_device_id_key; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.square_pos_devices
    ADD CONSTRAINT square_pos_devices_organization_id_device_id_key UNIQUE (organization_id, device_id);


--
-- Name: square_pos_devices square_pos_devices_pkey; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.square_pos_devices
    ADD CONSTRAINT square_pos_devices_pkey PRIMARY KEY (id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: acct_categories acct_categories_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.acct_categories
    ADD CONSTRAINT acct_categories_pkey PRIMARY KEY (code);


--
-- Name: acct_members acct_members_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.acct_members
    ADD CONSTRAINT acct_members_pkey PRIMARY KEY (id);


--
-- Name: acct_owner_draws acct_owner_draws_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.acct_owner_draws
    ADD CONSTRAINT acct_owner_draws_pkey PRIMARY KEY (id);


--
-- Name: acct_payout_items acct_payout_items_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.acct_payout_items
    ADD CONSTRAINT acct_payout_items_pkey PRIMARY KEY (id);


--
-- Name: acct_payouts acct_payouts_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.acct_payouts
    ADD CONSTRAINT acct_payouts_pkey PRIMARY KEY (id);


--
-- Name: acct_settings acct_settings_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.acct_settings
    ADD CONSTRAINT acct_settings_pkey PRIMARY KEY (id);


--
-- Name: acct_transactions acct_transactions_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.acct_transactions
    ADD CONSTRAINT acct_transactions_pkey PRIMARY KEY (id);


--
-- Name: acct_vendor_rules acct_vendor_rules_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.acct_vendor_rules
    ADD CONSTRAINT acct_vendor_rules_pkey PRIMARY KEY (id);


--
-- Name: api_keys api_keys_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.api_keys
    ADD CONSTRAINT api_keys_pkey PRIMARY KEY (id);


--
-- Name: bookings bookings_member_id_class_session_id_key; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.bookings
    ADD CONSTRAINT bookings_member_id_class_session_id_key UNIQUE (member_id, class_session_id);


--
-- Name: bookings bookings_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.bookings
    ADD CONSTRAINT bookings_pkey PRIMARY KEY (id);


--
-- Name: class_series class_series_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.class_series
    ADD CONSTRAINT class_series_pkey PRIMARY KEY (id);


--
-- Name: class_sessions class_sessions_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.class_sessions
    ADD CONSTRAINT class_sessions_pkey PRIMARY KEY (id);


--
-- Name: class_types class_types_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.class_types
    ADD CONSTRAINT class_types_pkey PRIMARY KEY (id);


--
-- Name: classpass_config classpass_config_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.classpass_config
    ADD CONSTRAINT classpass_config_pkey PRIMARY KEY (id);


--
-- Name: classpass_config classpass_config_studio_id_key; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.classpass_config
    ADD CONSTRAINT classpass_config_studio_id_key UNIQUE (studio_id);


--
-- Name: classpass_reservations classpass_reservations_classpass_reservation_id_key; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.classpass_reservations
    ADD CONSTRAINT classpass_reservations_classpass_reservation_id_key UNIQUE (classpass_reservation_id);


--
-- Name: classpass_reservations classpass_reservations_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.classpass_reservations
    ADD CONSTRAINT classpass_reservations_pkey PRIMARY KEY (id);


--
-- Name: communication_log communication_log_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.communication_log
    ADD CONSTRAINT communication_log_pkey PRIMARY KEY (id);


--
-- Name: course_enrollments course_enrollments_course_id_member_id_key; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.course_enrollments
    ADD CONSTRAINT course_enrollments_course_id_member_id_key UNIQUE (course_id, member_id);


--
-- Name: course_enrollments course_enrollments_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.course_enrollments
    ADD CONSTRAINT course_enrollments_pkey PRIMARY KEY (id);


--
-- Name: course_session_attendance course_session_attendance_course_session_id_member_id_key; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.course_session_attendance
    ADD CONSTRAINT course_session_attendance_course_session_id_member_id_key UNIQUE (course_session_id, member_id);


--
-- Name: course_session_attendance course_session_attendance_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.course_session_attendance
    ADD CONSTRAINT course_session_attendance_pkey PRIMARY KEY (id);


--
-- Name: course_sessions course_sessions_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.course_sessions
    ADD CONSTRAINT course_sessions_pkey PRIMARY KEY (id);


--
-- Name: courses courses_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.courses
    ADD CONSTRAINT courses_pkey PRIMARY KEY (id);


--
-- Name: de34_filings de34_filings_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.de34_filings
    ADD CONSTRAINT de34_filings_pkey PRIMARY KEY (id);


--
-- Name: de34_filings de34_filings_user_id_key; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.de34_filings
    ADD CONSTRAINT de34_filings_user_id_key UNIQUE (user_id);


--
-- Name: email_campaign_sends email_campaign_sends_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.email_campaign_sends
    ADD CONSTRAINT email_campaign_sends_pkey PRIMARY KEY (id);


--
-- Name: email_campaigns email_campaigns_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.email_campaigns
    ADD CONSTRAINT email_campaigns_pkey PRIMARY KEY (id);


--
-- Name: employee_w4_forms employee_w4_forms_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.employee_w4_forms
    ADD CONSTRAINT employee_w4_forms_pkey PRIMARY KEY (id);


--
-- Name: employer_profile employer_profile_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.employer_profile
    ADD CONSTRAINT employer_profile_pkey PRIMARY KEY (id);


--
-- Name: emr_encounter_log emr_encounter_log_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.emr_encounter_log
    ADD CONSTRAINT emr_encounter_log_pkey PRIMARY KEY (id);


--
-- Name: emr_patient_map emr_patient_map_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.emr_patient_map
    ADD CONSTRAINT emr_patient_map_pkey PRIMARY KEY (id);


--
-- Name: emr_sync_log emr_sync_log_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.emr_sync_log
    ADD CONSTRAINT emr_sync_log_pkey PRIMARY KEY (id);


--
-- Name: equipment equipment_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.equipment
    ADD CONSTRAINT equipment_pkey PRIMARY KEY (id);


--
-- Name: facility_schedule_completions facility_schedule_completions_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.facility_schedule_completions
    ADD CONSTRAINT facility_schedule_completions_pkey PRIMARY KEY (id);


--
-- Name: facility_schedules facility_schedules_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.facility_schedules
    ADD CONSTRAINT facility_schedules_pkey PRIMARY KEY (id);


--
-- Name: failed_payment_attempts failed_payment_attempts_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.failed_payment_attempts
    ADD CONSTRAINT failed_payment_attempts_pkey PRIMARY KEY (id);


--
-- Name: gdpr_deletion_requests gdpr_deletion_requests_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.gdpr_deletion_requests
    ADD CONSTRAINT gdpr_deletion_requests_pkey PRIMARY KEY (id);


--
-- Name: guest_instructors guest_instructors_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.guest_instructors
    ADD CONSTRAINT guest_instructors_pkey PRIMARY KEY (id);


--
-- Name: instructor_availability instructor_availability_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.instructor_availability
    ADD CONSTRAINT instructor_availability_pkey PRIMARY KEY (id);


--
-- Name: instructors instructors_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.instructors
    ADD CONSTRAINT instructors_pkey PRIMARY KEY (id);


--
-- Name: inventory inventory_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.inventory
    ADD CONSTRAINT inventory_pkey PRIMARY KEY (id);


--
-- Name: inventory inventory_product_unique; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.inventory
    ADD CONSTRAINT inventory_product_unique UNIQUE (product_id);


--
-- Name: inventory_transactions inventory_transactions_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.inventory_transactions
    ADD CONSTRAINT inventory_transactions_pkey PRIMARY KEY (id);


--
-- Name: job_application_documents job_application_documents_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.job_application_documents
    ADD CONSTRAINT job_application_documents_pkey PRIMARY KEY (id);


--
-- Name: job_application_events job_application_events_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.job_application_events
    ADD CONSTRAINT job_application_events_pkey PRIMARY KEY (id);


--
-- Name: job_applications job_applications_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.job_applications
    ADD CONSTRAINT job_applications_pkey PRIMARY KEY (id);


--
-- Name: maintenance_requests maintenance_requests_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.maintenance_requests
    ADD CONSTRAINT maintenance_requests_pkey PRIMARY KEY (id);


--
-- Name: marketing_drafts marketing_drafts_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.marketing_drafts
    ADD CONSTRAINT marketing_drafts_pkey PRIMARY KEY (id);


--
-- Name: member_credits member_credits_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.member_credits
    ADD CONSTRAINT member_credits_pkey PRIMARY KEY (id);


--
-- Name: member_health_data member_health_data_member_id_key; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.member_health_data
    ADD CONSTRAINT member_health_data_member_id_key UNIQUE (member_id);


--
-- Name: member_health_data member_health_data_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.member_health_data
    ADD CONSTRAINT member_health_data_pkey PRIMARY KEY (id);


--
-- Name: member_memberships member_memberships_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.member_memberships
    ADD CONSTRAINT member_memberships_pkey PRIMARY KEY (id);


--
-- Name: member_milestones member_milestone_unique; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.member_milestones
    ADD CONSTRAINT member_milestone_unique UNIQUE (member_id, milestone_type);


--
-- Name: member_milestones member_milestones_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.member_milestones
    ADD CONSTRAINT member_milestones_pkey PRIMARY KEY (id);


--
-- Name: member_notes member_notes_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.member_notes
    ADD CONSTRAINT member_notes_pkey PRIMARY KEY (id);


--
-- Name: members members_member_number_key; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.members
    ADD CONSTRAINT members_member_number_key UNIQUE (member_number);


--
-- Name: members members_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.members
    ADD CONSTRAINT members_pkey PRIMARY KEY (id);


--
-- Name: membership_types membership_types_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.membership_types
    ADD CONSTRAINT membership_types_pkey PRIMARY KEY (id);


--
-- Name: onboarding_documents onboarding_documents_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.onboarding_documents
    ADD CONSTRAINT onboarding_documents_pkey PRIMARY KEY (id);


--
-- Name: onboarding_packets onboarding_packets_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.onboarding_packets
    ADD CONSTRAINT onboarding_packets_pkey PRIMARY KEY (id);


--
-- Name: payroll_employee_mapping payroll_employee_mapping_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.payroll_employee_mapping
    ADD CONSTRAINT payroll_employee_mapping_pkey PRIMARY KEY (id);


--
-- Name: payroll_line_items payroll_line_items_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.payroll_line_items
    ADD CONSTRAINT payroll_line_items_pkey PRIMARY KEY (id);


--
-- Name: payroll_line_items payroll_line_items_unique; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.payroll_line_items
    ADD CONSTRAINT payroll_line_items_unique UNIQUE (payroll_run_id, instructor_id);


--
-- Name: payroll_employee_mapping payroll_mapping_unique; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.payroll_employee_mapping
    ADD CONSTRAINT payroll_mapping_unique UNIQUE (instructor_id, provider);


--
-- Name: payroll_runs payroll_runs_period_unique; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.payroll_runs
    ADD CONSTRAINT payroll_runs_period_unique UNIQUE (period_start, period_end);


--
-- Name: payroll_runs payroll_runs_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.payroll_runs
    ADD CONSTRAINT payroll_runs_pkey PRIMARY KEY (id);


--
-- Name: pos_line_items pos_line_items_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.pos_line_items
    ADD CONSTRAINT pos_line_items_pkey PRIMARY KEY (id);


--
-- Name: pos_terminal_checkouts pos_terminal_checkouts_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.pos_terminal_checkouts
    ADD CONSTRAINT pos_terminal_checkouts_pkey PRIMARY KEY (id);


--
-- Name: pos_transactions pos_transactions_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.pos_transactions
    ADD CONSTRAINT pos_transactions_pkey PRIMARY KEY (id);


--
-- Name: price_adjustments_log price_adjustments_log_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.price_adjustments_log
    ADD CONSTRAINT price_adjustments_log_pkey PRIMARY KEY (id);


--
-- Name: pricing_rules pricing_rules_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.pricing_rules
    ADD CONSTRAINT pricing_rules_pkey PRIMARY KEY (id);


--
-- Name: private_bookings private_bookings_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.private_bookings
    ADD CONSTRAINT private_bookings_pkey PRIMARY KEY (id);


--
-- Name: private_services private_services_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.private_services
    ADD CONSTRAINT private_services_pkey PRIMARY KEY (id);


--
-- Name: products products_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.products
    ADD CONSTRAINT products_pkey PRIMARY KEY (id);


--
-- Name: resolution_requests resolution_requests_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.resolution_requests
    ADD CONSTRAINT resolution_requests_pkey PRIMARY KEY (id);


--
-- Name: reviews review_unique; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.reviews
    ADD CONSTRAINT review_unique UNIQUE (member_id, class_session_id);


--
-- Name: reviews reviews_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.reviews
    ADD CONSTRAINT reviews_pkey PRIMARY KEY (id);


--
-- Name: rooms rooms_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.rooms
    ADD CONSTRAINT rooms_pkey PRIMARY KEY (id);


--
-- Name: sms_campaign_sends sms_campaign_sends_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.sms_campaign_sends
    ADD CONSTRAINT sms_campaign_sends_pkey PRIMARY KEY (id);


--
-- Name: sms_campaigns sms_campaigns_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.sms_campaigns
    ADD CONSTRAINT sms_campaigns_pkey PRIMARY KEY (id);


--
-- Name: sms_messages sms_messages_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.sms_messages
    ADD CONSTRAINT sms_messages_pkey PRIMARY KEY (id);


--
-- Name: sms_templates sms_templates_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.sms_templates
    ADD CONSTRAINT sms_templates_pkey PRIMARY KEY (id);


--
-- Name: sms_templates sms_templates_slug_key; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.sms_templates
    ADD CONSTRAINT sms_templates_slug_key UNIQUE (slug);


--
-- Name: studios studios_organization_id_slug_key; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.studios
    ADD CONSTRAINT studios_organization_id_slug_key UNIQUE (organization_id, slug);


--
-- Name: studios studios_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.studios
    ADD CONSTRAINT studios_pkey PRIMARY KEY (id);


--
-- Name: sub_finder_requests sub_finder_requests_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.sub_finder_requests
    ADD CONSTRAINT sub_finder_requests_pkey PRIMARY KEY (id);


--
-- Name: time_entries time_entries_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.time_entries
    ADD CONSTRAINT time_entries_pkey PRIMARY KEY (id);


--
-- Name: transactions transactions_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.transactions
    ADD CONSTRAINT transactions_pkey PRIMARY KEY (id);


--
-- Name: video_categories video_categories_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.video_categories
    ADD CONSTRAINT video_categories_pkey PRIMARY KEY (id);


--
-- Name: video_categories video_categories_slug_key; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.video_categories
    ADD CONSTRAINT video_categories_slug_key UNIQUE (slug);


--
-- Name: video_membership_access video_membership_access_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.video_membership_access
    ADD CONSTRAINT video_membership_access_pkey PRIMARY KEY (id);


--
-- Name: video_membership_access video_membership_access_video_id_membership_type_id_key; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.video_membership_access
    ADD CONSTRAINT video_membership_access_video_id_membership_type_id_key UNIQUE (video_id, membership_type_id);


--
-- Name: video_views video_views_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.video_views
    ADD CONSTRAINT video_views_pkey PRIMARY KEY (id);


--
-- Name: videos videos_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.videos
    ADD CONSTRAINT videos_pkey PRIMARY KEY (id);


--
-- Name: waiver_signatures waiver_signatures_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.waiver_signatures
    ADD CONSTRAINT waiver_signatures_pkey PRIMARY KEY (id);


--
-- Name: waiver_templates waiver_templates_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.waiver_templates
    ADD CONSTRAINT waiver_templates_pkey PRIMARY KEY (id);


--
-- Name: workshop_contracts workshop_contracts_pkey; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.workshop_contracts
    ADD CONSTRAINT workshop_contracts_pkey PRIMARY KEY (id);


--
-- Name: workshop_contracts workshop_contracts_signing_token_key; Type: CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.workshop_contracts
    ADD CONSTRAINT workshop_contracts_signing_token_key UNIQUE (signing_token);


--
--



--
-- Name: idx_ai_agent_log_created; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_ai_agent_log_created ON af_global.platform_ai_agent_log USING btree (created_at DESC);


--
-- Name: idx_ai_agent_log_type; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_ai_agent_log_type ON af_global.platform_ai_agent_log USING btree (agent_type);


--
-- Name: idx_ai_usage_org; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_ai_usage_org ON af_global.ai_token_usage USING btree (organization_id, created_at DESC);


--
-- Name: idx_ai_usage_org_month; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_ai_usage_org_month ON af_global.ai_token_usage USING btree (organization_id, date_trunc('month'::text, (created_at AT TIME ZONE 'UTC'::text)));


--
-- Name: idx_ai_usage_service; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_ai_usage_service ON af_global.ai_token_usage USING btree (service_name, created_at DESC);


--
-- Name: idx_announcements_active; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_announcements_active ON af_global.platform_announcements USING btree (is_active);


--
-- Name: idx_api_key_routing_org_slug; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_api_key_routing_org_slug ON af_global.api_key_routing USING btree (org_slug);


--
-- Name: idx_audit_log_created; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_audit_log_created ON af_global.audit_log USING btree (created_at DESC);


--
-- Name: idx_audit_log_org; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_audit_log_org ON af_global.audit_log USING btree (organization_id);


--
-- Name: idx_backups_created; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_backups_created ON af_global.platform_backups USING btree (created_at DESC);


--
-- Name: idx_backups_status; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_backups_status ON af_global.platform_backups USING btree (status);


--
-- Name: idx_backups_type; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_backups_type ON af_global.platform_backups USING btree (backup_type);


--
-- Name: idx_dlt_failed_at; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_dlt_failed_at ON af_global.dead_letter_tasks USING btree (failed_at DESC);


--
-- Name: idx_dlt_resolution; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_dlt_resolution ON af_global.dead_letter_tasks USING btree (resolution);


--
-- Name: idx_dlt_task_name; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_dlt_task_name ON af_global.dead_letter_tasks USING btree (task_name);


--
-- Name: idx_email_inbox_account; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_email_inbox_account ON af_global.platform_email_inbox USING btree (account_id);


--
-- Name: idx_email_inbox_created; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_email_inbox_created ON af_global.platform_email_inbox USING btree (created_at DESC);


--
-- Name: idx_email_inbox_mailbox; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_email_inbox_mailbox ON af_global.platform_email_inbox USING btree (mailbox);


--
-- Name: idx_email_inbox_message_id; Type: INDEX; Schema: af_global; Owner: -
--

CREATE UNIQUE INDEX idx_email_inbox_message_id ON af_global.platform_email_inbox USING btree (message_id) WHERE (message_id IS NOT NULL);


--
-- Name: idx_email_inbox_status; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_email_inbox_status ON af_global.platform_email_inbox USING btree (ai_status);


--
-- Name: idx_feature_flags_key; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_feature_flags_key ON af_global.feature_flags USING btree (flag_key);


--
-- Name: idx_feature_flags_org; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_feature_flags_org ON af_global.feature_flags USING btree (organization_id);


--
-- Name: idx_kiosk_devices_fingerprint; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_kiosk_devices_fingerprint ON af_global.kiosk_devices USING btree (organization_id, ip_hash, user_agent_hash) WHERE (is_active = true);


--
-- Name: idx_kiosk_devices_org_active; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_kiosk_devices_org_active ON af_global.kiosk_devices USING btree (organization_id, is_active) WHERE (is_active = true);


--
-- Name: idx_landing_pages_slug; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_landing_pages_slug ON af_global.platform_landing_pages USING btree (slug);


--
-- Name: idx_landing_pages_status; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_landing_pages_status ON af_global.platform_landing_pages USING btree (status);


--
-- Name: idx_metrics_date; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_metrics_date ON af_global.platform_metrics_daily USING btree (metric_date);


--
-- Name: idx_org_users_org; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_org_users_org ON af_global.organization_users USING btree (organization_id);


--
-- Name: idx_org_users_user; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_org_users_user ON af_global.organization_users USING btree (user_id);


--
-- Name: idx_organizations_billing_provider; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_organizations_billing_provider ON af_global.organizations USING btree (billing_provider) WHERE (billing_provider = 'square'::text);


--
-- Name: idx_organizations_square_merchant; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_organizations_square_merchant ON af_global.organizations USING btree (square_merchant_id) WHERE (square_merchant_id IS NOT NULL);


--
-- Name: idx_platform_invoices_org; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_platform_invoices_org ON af_global.platform_invoices USING btree (organization_id, period_start DESC);


--
-- Name: idx_platform_invoices_status; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_platform_invoices_status ON af_global.platform_invoices USING btree (status) WHERE (status = ANY (ARRAY['pending'::text, 'sent'::text, 'failed'::text]));


--
-- Name: idx_refresh_tokens_user; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_refresh_tokens_user ON af_global.refresh_tokens USING btree (user_id);


--
-- Name: idx_request_metrics_created; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_request_metrics_created ON af_global.platform_request_metrics USING btree (created_at DESC);


--
-- Name: idx_request_metrics_period; Type: INDEX; Schema: af_global; Owner: -
--

CREATE UNIQUE INDEX idx_request_metrics_period ON af_global.platform_request_metrics USING btree (period_start);


--
-- Name: idx_security_events_created; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_security_events_created ON af_global.platform_security_events USING btree (created_at DESC);


--
-- Name: idx_security_events_severity; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_security_events_severity ON af_global.platform_security_events USING btree (severity);


--
-- Name: idx_security_events_type; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_security_events_type ON af_global.platform_security_events USING btree (event_type);


--
-- Name: idx_security_events_unacked; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_security_events_unacked ON af_global.platform_security_events USING btree (acknowledged) WHERE (acknowledged = false);


--
-- Name: idx_social_messages_platform; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_social_messages_platform ON af_global.platform_social_messages USING btree (platform);


--
-- Name: idx_social_messages_status; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_social_messages_status ON af_global.platform_social_messages USING btree (ai_status);


--
-- Name: idx_social_posts_platform; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_social_posts_platform ON af_global.platform_social_posts USING btree (platform);


--
-- Name: idx_social_posts_scheduled; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_social_posts_scheduled ON af_global.platform_social_posts USING btree (scheduled_at) WHERE ((status)::text = 'scheduled'::text);


--
-- Name: idx_social_posts_status; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_social_posts_status ON af_global.platform_social_posts USING btree (status);


--
-- Name: idx_users_email; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_users_email ON af_global.users USING btree (email);


--
-- Name: idx_webhook_events_processed_at; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX idx_webhook_events_processed_at ON af_global.processed_webhook_events USING btree (processed_at);


--
-- Name: pos_checkout_index_expires_at_idx; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX pos_checkout_index_expires_at_idx ON af_global.pos_checkout_index USING btree (expires_at);


--
-- Name: square_pos_devices_org_idx; Type: INDEX; Schema: af_global; Owner: -
--

CREATE INDEX square_pos_devices_org_idx ON af_global.square_pos_devices USING btree (organization_id);


--
-- Name: acct_payout_items_auraflow_idx; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX acct_payout_items_auraflow_idx ON af_tenant_sunrise_yoga.acct_payout_items USING btree (auraflow_txn_id) WHERE (auraflow_txn_id IS NOT NULL);


--
-- Name: acct_payout_items_uniq_idx; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE UNIQUE INDEX acct_payout_items_uniq_idx ON af_tenant_sunrise_yoga.acct_payout_items USING btree (payout_id, provider_payment_id);


--
-- Name: acct_payouts_date_idx; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX acct_payouts_date_idx ON af_tenant_sunrise_yoga.acct_payouts USING btree (payout_date);


--
-- Name: acct_payouts_provider_id_idx; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE UNIQUE INDEX acct_payouts_provider_id_idx ON af_tenant_sunrise_yoga.acct_payouts USING btree (provider, provider_payout_id);


--
-- Name: acct_payouts_unreconciled_idx; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX acct_payouts_unreconciled_idx ON af_tenant_sunrise_yoga.acct_payouts USING btree (reconciled) WHERE (reconciled = false);


--
-- Name: acct_transactions_auraflow_idx; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX acct_transactions_auraflow_idx ON af_tenant_sunrise_yoga.acct_transactions USING btree (auraflow_txn_id) WHERE (auraflow_txn_id IS NOT NULL);


--
-- Name: acct_transactions_date_idx; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX acct_transactions_date_idx ON af_tenant_sunrise_yoga.acct_transactions USING btree (txn_date);


--
-- Name: acct_transactions_payout_idx; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX acct_transactions_payout_idx ON af_tenant_sunrise_yoga.acct_transactions USING btree (payout_id) WHERE (payout_id IS NOT NULL);


--
-- Name: acct_transactions_processor_pid_idx; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX acct_transactions_processor_pid_idx ON af_tenant_sunrise_yoga.acct_transactions USING btree (processor_payment_id) WHERE (processor_payment_id IS NOT NULL);


--
-- Name: acct_transactions_source_extid_idx; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE UNIQUE INDEX acct_transactions_source_extid_idx ON af_tenant_sunrise_yoga.acct_transactions USING btree (source, external_id) WHERE (external_id IS NOT NULL);


--
-- Name: acct_transactions_type_idx; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX acct_transactions_type_idx ON af_tenant_sunrise_yoga.acct_transactions USING btree (type, status);


--
-- Name: acct_vendor_rules_active_idx; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX acct_vendor_rules_active_idx ON af_tenant_sunrise_yoga.acct_vendor_rules USING btree (priority) WHERE is_active;


--
-- Name: idx_af_tenant_sunrise_yoga_avail_instructor_day; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_avail_instructor_day ON af_tenant_sunrise_yoga.instructor_availability USING btree (instructor_id, day_of_week);


--
-- Name: idx_af_tenant_sunrise_yoga_bookings_class_session_id; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_bookings_class_session_id ON af_tenant_sunrise_yoga.bookings USING btree (class_session_id);


--
-- Name: idx_af_tenant_sunrise_yoga_bookings_member; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_bookings_member ON af_tenant_sunrise_yoga.bookings USING btree (member_id);


--
-- Name: idx_af_tenant_sunrise_yoga_bookings_member_id; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_bookings_member_id ON af_tenant_sunrise_yoga.bookings USING btree (member_id);


--
-- Name: idx_af_tenant_sunrise_yoga_bookings_reminder_sent; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_bookings_reminder_sent ON af_tenant_sunrise_yoga.bookings USING btree (reminder_sent_at);


--
-- Name: idx_af_tenant_sunrise_yoga_bookings_session; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_bookings_session ON af_tenant_sunrise_yoga.bookings USING btree (class_session_id);


--
-- Name: idx_af_tenant_sunrise_yoga_bookings_status; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_bookings_status ON af_tenant_sunrise_yoga.bookings USING btree (status);


--
-- Name: idx_af_tenant_sunrise_yoga_campaigns_status; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_campaigns_status ON af_tenant_sunrise_yoga.email_campaigns USING btree (status);


--
-- Name: idx_af_tenant_sunrise_yoga_cenroll_course; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_cenroll_course ON af_tenant_sunrise_yoga.course_enrollments USING btree (course_id);


--
-- Name: idx_af_tenant_sunrise_yoga_cenroll_member; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_cenroll_member ON af_tenant_sunrise_yoga.course_enrollments USING btree (member_id);


--
-- Name: idx_af_tenant_sunrise_yoga_class_series_studio; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_class_series_studio ON af_tenant_sunrise_yoga.class_series USING btree (studio_id);


--
-- Name: idx_af_tenant_sunrise_yoga_class_sessions_series_id; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_class_sessions_series_id ON af_tenant_sunrise_yoga.class_sessions USING btree (series_id);


--
-- Name: idx_af_tenant_sunrise_yoga_class_sessions_starts_at; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_class_sessions_starts_at ON af_tenant_sunrise_yoga.class_sessions USING btree (starts_at);


--
-- Name: idx_af_tenant_sunrise_yoga_class_sessions_studio_id; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_class_sessions_studio_id ON af_tenant_sunrise_yoga.class_sessions USING btree (studio_id);


--
-- Name: idx_af_tenant_sunrise_yoga_comm_log_member; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_comm_log_member ON af_tenant_sunrise_yoga.communication_log USING btree (member_id);


--
-- Name: idx_af_tenant_sunrise_yoga_comm_log_type; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_comm_log_type ON af_tenant_sunrise_yoga.communication_log USING btree (type);


--
-- Name: idx_af_tenant_sunrise_yoga_communication_log_type_created; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_communication_log_type_created ON af_tenant_sunrise_yoga.communication_log USING btree (type, created_at);


--
-- Name: idx_af_tenant_sunrise_yoga_courses_status; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_courses_status ON af_tenant_sunrise_yoga.courses USING btree (status);


--
-- Name: idx_af_tenant_sunrise_yoga_courses_type; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_courses_type ON af_tenant_sunrise_yoga.courses USING btree (type);


--
-- Name: idx_af_tenant_sunrise_yoga_cp_reservations_session; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_cp_reservations_session ON af_tenant_sunrise_yoga.classpass_reservations USING btree (class_session_id);


--
-- Name: idx_af_tenant_sunrise_yoga_cp_reservations_status; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_cp_reservations_status ON af_tenant_sunrise_yoga.classpass_reservations USING btree (status);


--
-- Name: idx_af_tenant_sunrise_yoga_csends_campaign; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_csends_campaign ON af_tenant_sunrise_yoga.email_campaign_sends USING btree (campaign_id);


--
-- Name: idx_af_tenant_sunrise_yoga_csess_course; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_csess_course ON af_tenant_sunrise_yoga.course_sessions USING btree (course_id);


--
-- Name: idx_af_tenant_sunrise_yoga_equipment_category; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_equipment_category ON af_tenant_sunrise_yoga.equipment USING btree (category);


--
-- Name: idx_af_tenant_sunrise_yoga_equipment_room; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_equipment_room ON af_tenant_sunrise_yoga.equipment USING btree (room_id);


--
-- Name: idx_af_tenant_sunrise_yoga_equipment_studio; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_equipment_studio ON af_tenant_sunrise_yoga.equipment USING btree (studio_id);


--
-- Name: idx_af_tenant_sunrise_yoga_fac_completion_schedule; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_fac_completion_schedule ON af_tenant_sunrise_yoga.facility_schedule_completions USING btree (schedule_id, completed_at DESC);


--
-- Name: idx_af_tenant_sunrise_yoga_fac_schedule_overdue; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_fac_schedule_overdue ON af_tenant_sunrise_yoga.facility_schedules USING btree (next_due_at) WHERE (is_active = true);


--
-- Name: idx_af_tenant_sunrise_yoga_fac_schedule_studio; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_fac_schedule_studio ON af_tenant_sunrise_yoga.facility_schedules USING btree (studio_id);


--
-- Name: idx_af_tenant_sunrise_yoga_failed_pay_member; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_failed_pay_member ON af_tenant_sunrise_yoga.failed_payment_attempts USING btree (member_id);


--
-- Name: idx_af_tenant_sunrise_yoga_gdpr_del_member; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_gdpr_del_member ON af_tenant_sunrise_yoga.gdpr_deletion_requests USING btree (member_id);


--
-- Name: idx_af_tenant_sunrise_yoga_gdpr_del_scheduled; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_gdpr_del_scheduled ON af_tenant_sunrise_yoga.gdpr_deletion_requests USING btree (scheduled_deletion_at) WHERE ((status)::text = 'pending'::text);


--
-- Name: idx_af_tenant_sunrise_yoga_gdpr_del_status; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_gdpr_del_status ON af_tenant_sunrise_yoga.gdpr_deletion_requests USING btree (status) WHERE ((status)::text = 'pending'::text);


--
-- Name: idx_af_tenant_sunrise_yoga_instructors_phone_hash; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_instructors_phone_hash ON af_tenant_sunrise_yoga.instructors USING btree (phone_hash) WHERE (phone_hash IS NOT NULL);


--
-- Name: idx_af_tenant_sunrise_yoga_instructors_user; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_instructors_user ON af_tenant_sunrise_yoga.instructors USING btree (user_id);


--
-- Name: idx_af_tenant_sunrise_yoga_maintenance_open; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_maintenance_open ON af_tenant_sunrise_yoga.maintenance_requests USING btree (status) WHERE ((status)::text = ANY ((ARRAY['open'::character varying, 'in_progress'::character varying])::text[]));


--
-- Name: idx_af_tenant_sunrise_yoga_maintenance_status; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_maintenance_status ON af_tenant_sunrise_yoga.maintenance_requests USING btree (status);


--
-- Name: idx_af_tenant_sunrise_yoga_maintenance_studio; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_maintenance_studio ON af_tenant_sunrise_yoga.maintenance_requests USING btree (studio_id);


--
-- Name: idx_af_tenant_sunrise_yoga_member_credits_available; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_member_credits_available ON af_tenant_sunrise_yoga.member_credits USING btree (member_id, service_filter, expires_at) WHERE (used_at IS NULL);


--
-- Name: idx_af_tenant_sunrise_yoga_member_credits_source_ref; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_member_credits_source_ref ON af_tenant_sunrise_yoga.member_credits USING btree (source_ref_id) WHERE (source_ref_id IS NOT NULL);


--
-- Name: idx_af_tenant_sunrise_yoga_member_memberships_member; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_member_memberships_member ON af_tenant_sunrise_yoga.member_memberships USING btree (member_id);


--
-- Name: idx_af_tenant_sunrise_yoga_member_memberships_member_status; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_member_memberships_member_status ON af_tenant_sunrise_yoga.member_memberships USING btree (member_id, status);


--
-- Name: idx_af_tenant_sunrise_yoga_member_memberships_status; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_member_memberships_status ON af_tenant_sunrise_yoga.member_memberships USING btree (status);


--
-- Name: idx_af_tenant_sunrise_yoga_member_notes_member; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_member_notes_member ON af_tenant_sunrise_yoga.member_notes USING btree (member_id);


--
-- Name: idx_af_tenant_sunrise_yoga_members_birthday; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_members_birthday ON af_tenant_sunrise_yoga.members USING btree (birthday_month, birthday_day);


--
-- Name: idx_af_tenant_sunrise_yoga_members_email; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_members_email ON af_tenant_sunrise_yoga.members USING btree (email);


--
-- Name: idx_af_tenant_sunrise_yoga_members_name; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_members_name ON af_tenant_sunrise_yoga.members USING btree (last_name, first_name);


--
-- Name: idx_af_tenant_sunrise_yoga_members_stripe_customer; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_members_stripe_customer ON af_tenant_sunrise_yoga.members USING btree (stripe_customer_id);


--
-- Name: idx_af_tenant_sunrise_yoga_membership_types_template_key; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_membership_types_template_key ON af_tenant_sunrise_yoga.membership_types USING btree (template_key) WHERE (template_key IS NOT NULL);


--
-- Name: idx_af_tenant_sunrise_yoga_payroll_mapping_provider; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_payroll_mapping_provider ON af_tenant_sunrise_yoga.payroll_employee_mapping USING btree (provider);


--
-- Name: idx_af_tenant_sunrise_yoga_pb_instructor_starts; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_pb_instructor_starts ON af_tenant_sunrise_yoga.private_bookings USING btree (instructor_id, starts_at);


--
-- Name: idx_af_tenant_sunrise_yoga_pb_starts; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_pb_starts ON af_tenant_sunrise_yoga.private_bookings USING btree (starts_at);


--
-- Name: idx_af_tenant_sunrise_yoga_price_adj_created; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_price_adj_created ON af_tenant_sunrise_yoga.price_adjustments_log USING btree (created_at DESC);


--
-- Name: idx_af_tenant_sunrise_yoga_price_adj_session; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_price_adj_session ON af_tenant_sunrise_yoga.price_adjustments_log USING btree (class_session_id);


--
-- Name: idx_af_tenant_sunrise_yoga_pricing_rules_studio; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_pricing_rules_studio ON af_tenant_sunrise_yoga.pricing_rules USING btree (studio_id);


--
-- Name: idx_af_tenant_sunrise_yoga_reviews_created; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_reviews_created ON af_tenant_sunrise_yoga.reviews USING btree (created_at DESC);


--
-- Name: idx_af_tenant_sunrise_yoga_reviews_member; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_reviews_member ON af_tenant_sunrise_yoga.reviews USING btree (member_id);


--
-- Name: idx_af_tenant_sunrise_yoga_reviews_rating; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_reviews_rating ON af_tenant_sunrise_yoga.reviews USING btree (rating);


--
-- Name: idx_af_tenant_sunrise_yoga_reviews_sentiment; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_reviews_sentiment ON af_tenant_sunrise_yoga.reviews USING btree (sentiment);


--
-- Name: idx_af_tenant_sunrise_yoga_reviews_session; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_reviews_session ON af_tenant_sunrise_yoga.reviews USING btree (class_session_id);


--
-- Name: idx_af_tenant_sunrise_yoga_rooms_studio; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_rooms_studio ON af_tenant_sunrise_yoga.rooms USING btree (studio_id);


--
-- Name: idx_af_tenant_sunrise_yoga_sessions_recording; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_sessions_recording ON af_tenant_sunrise_yoga.class_sessions USING btree (recording_status) WHERE ((recording_status)::text <> 'none'::text);


--
-- Name: idx_af_tenant_sunrise_yoga_sessions_recording_status; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_sessions_recording_status ON af_tenant_sunrise_yoga.class_sessions USING btree (recording_status) WHERE ((recording_status)::text <> 'none'::text);


--
-- Name: idx_af_tenant_sunrise_yoga_sessions_room; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_sessions_room ON af_tenant_sunrise_yoga.class_sessions USING btree (room_id);


--
-- Name: idx_af_tenant_sunrise_yoga_sessions_series; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_sessions_series ON af_tenant_sunrise_yoga.class_sessions USING btree (series_id);


--
-- Name: idx_af_tenant_sunrise_yoga_sessions_starts; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_sessions_starts ON af_tenant_sunrise_yoga.class_sessions USING btree (starts_at);


--
-- Name: idx_af_tenant_sunrise_yoga_sms_member; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_sms_member ON af_tenant_sunrise_yoga.sms_messages USING btree (member_id);


--
-- Name: idx_af_tenant_sunrise_yoga_smscampaigns_scheduled; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_smscampaigns_scheduled ON af_tenant_sunrise_yoga.sms_campaigns USING btree (scheduled_at) WHERE ((status)::text = 'scheduled'::text);


--
-- Name: idx_af_tenant_sunrise_yoga_smscampaigns_status; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_smscampaigns_status ON af_tenant_sunrise_yoga.sms_campaigns USING btree (status);


--
-- Name: idx_af_tenant_sunrise_yoga_smssends_campaign; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_smssends_campaign ON af_tenant_sunrise_yoga.sms_campaign_sends USING btree (campaign_id);


--
-- Name: idx_af_tenant_sunrise_yoga_smstemplates_category; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_smstemplates_category ON af_tenant_sunrise_yoga.sms_templates USING btree (category);


--
-- Name: idx_af_tenant_sunrise_yoga_smstemplates_slug; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_smstemplates_slug ON af_tenant_sunrise_yoga.sms_templates USING btree (slug);


--
-- Name: idx_af_tenant_sunrise_yoga_subfinder_session; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_subfinder_session ON af_tenant_sunrise_yoga.sub_finder_requests USING btree (class_session_id);


--
-- Name: idx_af_tenant_sunrise_yoga_subfinder_status; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_subfinder_status ON af_tenant_sunrise_yoga.sub_finder_requests USING btree (status) WHERE ((status)::text = ANY ((ARRAY['searching'::character varying, 'offered'::character varying])::text[]));


--
-- Name: idx_af_tenant_sunrise_yoga_time_entries_instructor; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_time_entries_instructor ON af_tenant_sunrise_yoga.time_entries USING btree (instructor_id, clock_in);


--
-- Name: idx_af_tenant_sunrise_yoga_time_entries_pending; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_time_entries_pending ON af_tenant_sunrise_yoga.time_entries USING btree (status) WHERE ((status)::text = 'pending'::text);


--
-- Name: idx_af_tenant_sunrise_yoga_transactions_created_at; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_transactions_created_at ON af_tenant_sunrise_yoga.transactions USING btree (created_at);


--
-- Name: idx_af_tenant_sunrise_yoga_transactions_member; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_transactions_member ON af_tenant_sunrise_yoga.transactions USING btree (member_id);


--
-- Name: idx_af_tenant_sunrise_yoga_transactions_membership; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_transactions_membership ON af_tenant_sunrise_yoga.transactions USING btree (membership_id);


--
-- Name: idx_af_tenant_sunrise_yoga_transactions_status; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_transactions_status ON af_tenant_sunrise_yoga.transactions USING btree (status);


--
-- Name: idx_af_tenant_sunrise_yoga_transactions_stripe_pi; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_transactions_stripe_pi ON af_tenant_sunrise_yoga.transactions USING btree (stripe_payment_intent_id);


--
-- Name: idx_af_tenant_sunrise_yoga_video_access_video; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_video_access_video ON af_tenant_sunrise_yoga.video_membership_access USING btree (video_id);


--
-- Name: idx_af_tenant_sunrise_yoga_video_views_member; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_video_views_member ON af_tenant_sunrise_yoga.video_views USING btree (member_id);


--
-- Name: idx_af_tenant_sunrise_yoga_video_views_video; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_video_views_video ON af_tenant_sunrise_yoga.video_views USING btree (video_id);


--
-- Name: idx_af_tenant_sunrise_yoga_videos_category; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_videos_category ON af_tenant_sunrise_yoga.videos USING btree (category_id);


--
-- Name: idx_af_tenant_sunrise_yoga_videos_published; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_videos_published ON af_tenant_sunrise_yoga.videos USING btree (is_published, sort_order);


--
-- Name: idx_af_tenant_sunrise_yoga_videos_source; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_videos_source ON af_tenant_sunrise_yoga.videos USING btree (source);


--
-- Name: idx_af_tenant_sunrise_yoga_wsig_member_expires; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_wsig_member_expires ON af_tenant_sunrise_yoga.waiver_signatures USING btree (member_id, expires_at);


--
-- Name: idx_af_tenant_sunrise_yoga_wsig_member_template; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_wsig_member_template ON af_tenant_sunrise_yoga.waiver_signatures USING btree (member_id, waiver_template_id);


--
-- Name: idx_af_tenant_sunrise_yoga_wtpl_active; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_af_tenant_sunrise_yoga_wtpl_active ON af_tenant_sunrise_yoga.waiver_templates USING btree (is_active) WHERE (is_active = true);


--
-- Name: idx_api_keys_hash_active; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE UNIQUE INDEX idx_api_keys_hash_active ON af_tenant_sunrise_yoga.api_keys USING btree (key_hash) WHERE (is_active = true);


--
-- Name: idx_api_keys_prefix; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_api_keys_prefix ON af_tenant_sunrise_yoga.api_keys USING btree (key_prefix);


--
-- Name: idx_class_sessions_modality; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_class_sessions_modality ON af_tenant_sunrise_yoga.class_sessions USING btree (modality);


--
-- Name: idx_courses_guest_instructor; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_courses_guest_instructor ON af_tenant_sunrise_yoga.courses USING btree (guest_instructor_id) WHERE (guest_instructor_id IS NOT NULL);


--
-- Name: idx_drafts_created; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_drafts_created ON af_tenant_sunrise_yoga.marketing_drafts USING btree (created_at DESC);


--
-- Name: idx_drafts_status; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_drafts_status ON af_tenant_sunrise_yoga.marketing_drafts USING btree (status);


--
-- Name: idx_emr_encounter_log_booking; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_emr_encounter_log_booking ON af_tenant_sunrise_yoga.emr_encounter_log USING btree (booking_id);


--
-- Name: idx_emr_encounter_log_status; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_emr_encounter_log_status ON af_tenant_sunrise_yoga.emr_encounter_log USING btree (status) WHERE ((status)::text = 'failed'::text);


--
-- Name: idx_emr_patient_map_emr; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE UNIQUE INDEX idx_emr_patient_map_emr ON af_tenant_sunrise_yoga.emr_patient_map USING btree (emr_patient_id, emr_system);


--
-- Name: idx_emr_patient_map_member; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE UNIQUE INDEX idx_emr_patient_map_member ON af_tenant_sunrise_yoga.emr_patient_map USING btree (member_id);


--
-- Name: idx_emr_sync_log_created; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_emr_sync_log_created ON af_tenant_sunrise_yoga.emr_sync_log USING btree (created_at DESC);


--
-- Name: idx_guest_instructors_name; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_guest_instructors_name ON af_tenant_sunrise_yoga.guest_instructors USING btree (lower((name)::text));


--
-- Name: idx_guest_instructors_studio_active; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_guest_instructors_studio_active ON af_tenant_sunrise_yoga.guest_instructors USING btree (studio_id, is_active);


--
-- Name: idx_inv_txn_product_date; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_inv_txn_product_date ON af_tenant_sunrise_yoga.inventory_transactions USING btree (product_id, created_at DESC);


--
-- Name: idx_job_app_docs_app; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_job_app_docs_app ON af_tenant_sunrise_yoga.job_application_documents USING btree (application_id);


--
-- Name: idx_job_app_events_app; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_job_app_events_app ON af_tenant_sunrise_yoga.job_application_events USING btree (application_id, created_at);


--
-- Name: idx_job_apps_email; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_job_apps_email ON af_tenant_sunrise_yoga.job_applications USING btree (lower((email)::text));


--
-- Name: idx_job_apps_status; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_job_apps_status ON af_tenant_sunrise_yoga.job_applications USING btree (status, created_at DESC);


--
-- Name: idx_milestones_member; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_milestones_member ON af_tenant_sunrise_yoga.member_milestones USING btree (member_id);


--
-- Name: idx_onboarding_docs_packet; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_onboarding_docs_packet ON af_tenant_sunrise_yoga.onboarding_documents USING btree (packet_id, sort_order);


--
-- Name: idx_onboarding_docs_user; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_onboarding_docs_user ON af_tenant_sunrise_yoga.onboarding_documents USING btree (user_id);


--
-- Name: idx_onboarding_packet_token; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE UNIQUE INDEX idx_onboarding_packet_token ON af_tenant_sunrise_yoga.onboarding_packets USING btree (signing_token) WHERE (signing_token IS NOT NULL);


--
-- Name: idx_onboarding_packet_user; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_onboarding_packet_user ON af_tenant_sunrise_yoga.onboarding_packets USING btree (user_id);


--
-- Name: idx_pos_line_txn; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_pos_line_txn ON af_tenant_sunrise_yoga.pos_line_items USING btree (transaction_id);


--
-- Name: idx_pos_txn_created; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_pos_txn_created ON af_tenant_sunrise_yoga.pos_transactions USING btree (created_at DESC);


--
-- Name: idx_products_category; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_products_category ON af_tenant_sunrise_yoga.products USING btree (category) WHERE (active = true);


--
-- Name: idx_products_sku; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE UNIQUE INDEX idx_products_sku ON af_tenant_sunrise_yoga.products USING btree (sku) WHERE ((sku IS NOT NULL) AND (active = true));


--
-- Name: idx_time_entries_instructor_clock; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_time_entries_instructor_clock ON af_tenant_sunrise_yoga.time_entries USING btree (instructor_id, clock_in);


--
-- Name: idx_time_entries_pending; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_time_entries_pending ON af_tenant_sunrise_yoga.time_entries USING btree (status) WHERE ((status)::text = 'pending'::text);


--
-- Name: idx_transactions_external_reference; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_transactions_external_reference ON af_tenant_sunrise_yoga.transactions USING btree (((metadata ->> 'external_reference'::text))) WHERE ((metadata ->> 'external_reference'::text) IS NOT NULL);


--
-- Name: idx_w4_token; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE UNIQUE INDEX idx_w4_token ON af_tenant_sunrise_yoga.employee_w4_forms USING btree (signing_token) WHERE (signing_token IS NOT NULL);


--
-- Name: idx_w4_user; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_w4_user ON af_tenant_sunrise_yoga.employee_w4_forms USING btree (user_id);


--
-- Name: idx_workshop_contracts_guest; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_workshop_contracts_guest ON af_tenant_sunrise_yoga.workshop_contracts USING btree (guest_instructor_id, signed_at DESC NULLS LAST);


--
-- Name: idx_workshop_contracts_reminder; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_workshop_contracts_reminder ON af_tenant_sunrise_yoga.workshop_contracts USING btree (email_sent_at, reminder_sent_at) WHERE (((status)::text = ANY ((ARRAY['sent'::character varying, 'viewed'::character varying])::text[])) AND (reminder_sent_at IS NULL));


--
-- Name: idx_workshop_contracts_status; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_workshop_contracts_status ON af_tenant_sunrise_yoga.workshop_contracts USING btree (status) WHERE ((status)::text = ANY ((ARRAY['prepared'::character varying, 'sent'::character varying, 'viewed'::character varying])::text[]));


--
-- Name: idx_workshop_contracts_token; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX idx_workshop_contracts_token ON af_tenant_sunrise_yoga.workshop_contracts USING btree (signing_token) WHERE (signing_token IS NOT NULL);


--
-- Name: member_memberships_trial_period_end_idx; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX member_memberships_trial_period_end_idx ON af_tenant_sunrise_yoga.member_memberships USING btree (trial_period_end) WHERE (trial_period_end IS NOT NULL);


--
-- Name: members_square_customer_idx; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX members_square_customer_idx ON af_tenant_sunrise_yoga.members USING btree (square_customer_id) WHERE (square_customer_id IS NOT NULL);


--
-- Name: payroll_line_items_run_guest_uq; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE UNIQUE INDEX payroll_line_items_run_guest_uq ON af_tenant_sunrise_yoga.payroll_line_items USING btree (payroll_run_id, guest_instructor_id) WHERE (guest_instructor_id IS NOT NULL);


--
-- Name: payroll_line_items_run_instructor_uq; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE UNIQUE INDEX payroll_line_items_run_instructor_uq ON af_tenant_sunrise_yoga.payroll_line_items USING btree (payroll_run_id, instructor_id) WHERE (instructor_id IS NOT NULL);


--
-- Name: pos_terminal_checkouts_member_idx; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX pos_terminal_checkouts_member_idx ON af_tenant_sunrise_yoga.pos_terminal_checkouts USING btree (member_id, initiated_at DESC);


--
-- Name: pos_terminal_checkouts_square_idx; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX pos_terminal_checkouts_square_idx ON af_tenant_sunrise_yoga.pos_terminal_checkouts USING btree (square_checkout_id) WHERE (square_checkout_id IS NOT NULL);


--
-- Name: pos_terminal_checkouts_status_idx; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX pos_terminal_checkouts_status_idx ON af_tenant_sunrise_yoga.pos_terminal_checkouts USING btree (status, expires_at);


--
-- Name: transactions_square_payment_idx; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE INDEX transactions_square_payment_idx ON af_tenant_sunrise_yoga.transactions USING btree (square_payment_id) WHERE (square_payment_id IS NOT NULL);


--
-- Name: uq_workshop_contracts_active_per_course; Type: INDEX; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE UNIQUE INDEX uq_workshop_contracts_active_per_course ON af_tenant_sunrise_yoga.workshop_contracts USING btree (course_id) WHERE ((status)::text <> 'voided'::text);


--
-- Name: organizations organizations_updated_at; Type: TRIGGER; Schema: af_global; Owner: -
--

CREATE TRIGGER organizations_updated_at BEFORE UPDATE ON af_global.organizations FOR EACH ROW EXECUTE FUNCTION af_global.update_updated_at();


--
-- Name: platform_ads_config trg_platform_ads_config_updated_at; Type: TRIGGER; Schema: af_global; Owner: -
--

CREATE TRIGGER trg_platform_ads_config_updated_at BEFORE UPDATE ON af_global.platform_ads_config FOR EACH ROW EXECUTE FUNCTION af_global.update_updated_at();


--
-- Name: platform_backup_schedule trg_platform_backup_schedule_updated_at; Type: TRIGGER; Schema: af_global; Owner: -
--

CREATE TRIGGER trg_platform_backup_schedule_updated_at BEFORE UPDATE ON af_global.platform_backup_schedule FOR EACH ROW EXECUTE FUNCTION af_global.update_updated_at();


--
-- Name: platform_backups trg_platform_backups_updated_at; Type: TRIGGER; Schema: af_global; Owner: -
--

CREATE TRIGGER trg_platform_backups_updated_at BEFORE UPDATE ON af_global.platform_backups FOR EACH ROW EXECUTE FUNCTION af_global.update_updated_at();


--
-- Name: platform_config trg_platform_config_updated_at; Type: TRIGGER; Schema: af_global; Owner: -
--

CREATE TRIGGER trg_platform_config_updated_at BEFORE UPDATE ON af_global.platform_config FOR EACH ROW EXECUTE FUNCTION af_global.update_updated_at();


--
-- Name: platform_email_accounts trg_platform_email_accounts_updated_at; Type: TRIGGER; Schema: af_global; Owner: -
--

CREATE TRIGGER trg_platform_email_accounts_updated_at BEFORE UPDATE ON af_global.platform_email_accounts FOR EACH ROW EXECUTE FUNCTION af_global.update_updated_at();


--
-- Name: platform_email_inbox trg_platform_email_inbox_updated_at; Type: TRIGGER; Schema: af_global; Owner: -
--

CREATE TRIGGER trg_platform_email_inbox_updated_at BEFORE UPDATE ON af_global.platform_email_inbox FOR EACH ROW EXECUTE FUNCTION af_global.update_updated_at();


--
-- Name: platform_landing_pages trg_platform_landing_pages_updated_at; Type: TRIGGER; Schema: af_global; Owner: -
--

CREATE TRIGGER trg_platform_landing_pages_updated_at BEFORE UPDATE ON af_global.platform_landing_pages FOR EACH ROW EXECUTE FUNCTION af_global.update_updated_at();


--
-- Name: platform_social_messages trg_platform_social_messages_updated_at; Type: TRIGGER; Schema: af_global; Owner: -
--

CREATE TRIGGER trg_platform_social_messages_updated_at BEFORE UPDATE ON af_global.platform_social_messages FOR EACH ROW EXECUTE FUNCTION af_global.update_updated_at();


--
-- Name: platform_social_posts trg_platform_social_posts_updated_at; Type: TRIGGER; Schema: af_global; Owner: -
--

CREATE TRIGGER trg_platform_social_posts_updated_at BEFORE UPDATE ON af_global.platform_social_posts FOR EACH ROW EXECUTE FUNCTION af_global.update_updated_at();


--
-- Name: users users_updated_at; Type: TRIGGER; Schema: af_global; Owner: -
--

CREATE TRIGGER users_updated_at BEFORE UPDATE ON af_global.users FOR EACH ROW EXECUTE FUNCTION af_global.update_updated_at();


--
-- Name: bookings af_tenant_sunrise_yoga_touch_bookings; Type: TRIGGER; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TRIGGER af_tenant_sunrise_yoga_touch_bookings BEFORE UPDATE ON af_tenant_sunrise_yoga.bookings FOR EACH ROW EXECUTE FUNCTION af_global.touch_updated_at();


--
-- Name: instructor_availability af_tenant_sunrise_yoga_touch_instructor_availability; Type: TRIGGER; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TRIGGER af_tenant_sunrise_yoga_touch_instructor_availability BEFORE UPDATE ON af_tenant_sunrise_yoga.instructor_availability FOR EACH ROW EXECUTE FUNCTION af_global.touch_updated_at();


--
-- Name: private_services af_tenant_sunrise_yoga_touch_private_services; Type: TRIGGER; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TRIGGER af_tenant_sunrise_yoga_touch_private_services BEFORE UPDATE ON af_tenant_sunrise_yoga.private_services FOR EACH ROW EXECUTE FUNCTION af_global.touch_updated_at();


--
-- Name: rooms af_tenant_sunrise_yoga_touch_rooms; Type: TRIGGER; Schema: af_tenant_sunrise_yoga; Owner: -
--

CREATE TRIGGER af_tenant_sunrise_yoga_touch_rooms BEFORE UPDATE ON af_tenant_sunrise_yoga.rooms FOR EACH ROW EXECUTE FUNCTION af_global.touch_updated_at();


--
-- Name: ai_token_usage ai_token_usage_organization_id_fkey; Type: FK CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.ai_token_usage
    ADD CONSTRAINT ai_token_usage_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES af_global.organizations(id) ON DELETE CASCADE;


--
-- Name: audit_log audit_log_organization_id_fkey; Type: FK CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.audit_log
    ADD CONSTRAINT audit_log_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES af_global.organizations(id);


--
-- Name: audit_log audit_log_user_id_fkey; Type: FK CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.audit_log
    ADD CONSTRAINT audit_log_user_id_fkey FOREIGN KEY (user_id) REFERENCES af_global.users(id);


--
-- Name: feature_flags feature_flags_organization_id_fkey; Type: FK CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.feature_flags
    ADD CONSTRAINT feature_flags_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES af_global.organizations(id) ON DELETE CASCADE;


--
-- Name: kiosk_devices kiosk_devices_organization_id_fkey; Type: FK CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.kiosk_devices
    ADD CONSTRAINT kiosk_devices_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES af_global.organizations(id) ON DELETE CASCADE;


--
-- Name: kiosk_devices kiosk_devices_registered_by_fkey; Type: FK CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.kiosk_devices
    ADD CONSTRAINT kiosk_devices_registered_by_fkey FOREIGN KEY (registered_by) REFERENCES af_global.users(id) ON DELETE SET NULL;


--
-- Name: kiosk_devices kiosk_devices_revoked_by_fkey; Type: FK CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.kiosk_devices
    ADD CONSTRAINT kiosk_devices_revoked_by_fkey FOREIGN KEY (revoked_by) REFERENCES af_global.users(id) ON DELETE SET NULL;


--
-- Name: organization_users organization_users_invited_by_fkey; Type: FK CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.organization_users
    ADD CONSTRAINT organization_users_invited_by_fkey FOREIGN KEY (invited_by) REFERENCES af_global.users(id);


--
-- Name: organization_users organization_users_organization_id_fkey; Type: FK CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.organization_users
    ADD CONSTRAINT organization_users_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES af_global.organizations(id) ON DELETE CASCADE;


--
-- Name: organization_users organization_users_user_id_fkey; Type: FK CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.organization_users
    ADD CONSTRAINT organization_users_user_id_fkey FOREIGN KEY (user_id) REFERENCES af_global.users(id) ON DELETE CASCADE;


--
-- Name: organizations organizations_square_pos_default_device_id_fkey; Type: FK CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.organizations
    ADD CONSTRAINT organizations_square_pos_default_device_id_fkey FOREIGN KEY (square_pos_default_device_id) REFERENCES af_global.square_pos_devices(id) ON DELETE SET NULL;


--
-- Name: platform_email_inbox platform_email_inbox_account_id_fkey; Type: FK CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.platform_email_inbox
    ADD CONSTRAINT platform_email_inbox_account_id_fkey FOREIGN KEY (account_id) REFERENCES af_global.platform_email_accounts(id) ON DELETE SET NULL;


--
-- Name: platform_invoices platform_invoices_organization_id_fkey; Type: FK CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.platform_invoices
    ADD CONSTRAINT platform_invoices_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES af_global.organizations(id) ON DELETE CASCADE;


--
-- Name: platform_social_messages platform_social_messages_post_id_fkey; Type: FK CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.platform_social_messages
    ADD CONSTRAINT platform_social_messages_post_id_fkey FOREIGN KEY (post_id) REFERENCES af_global.platform_social_posts(id) ON DELETE SET NULL;


--
-- Name: refresh_tokens refresh_tokens_user_id_fkey; Type: FK CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.refresh_tokens
    ADD CONSTRAINT refresh_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES af_global.users(id) ON DELETE CASCADE;


--
-- Name: square_pos_devices square_pos_devices_organization_id_fkey; Type: FK CONSTRAINT; Schema: af_global; Owner: -
--

ALTER TABLE ONLY af_global.square_pos_devices
    ADD CONSTRAINT square_pos_devices_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES af_global.organizations(id) ON DELETE CASCADE;


--
-- Name: acct_payout_items acct_payout_items_payout_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.acct_payout_items
    ADD CONSTRAINT acct_payout_items_payout_id_fkey FOREIGN KEY (payout_id) REFERENCES af_tenant_sunrise_yoga.acct_payouts(id) ON DELETE CASCADE;


--
-- Name: courses courses_guest_instructor_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.courses
    ADD CONSTRAINT courses_guest_instructor_id_fkey FOREIGN KEY (guest_instructor_id) REFERENCES af_tenant_sunrise_yoga.guest_instructors(id) ON DELETE SET NULL;


--
-- Name: employee_w4_forms employee_w4_forms_application_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.employee_w4_forms
    ADD CONSTRAINT employee_w4_forms_application_id_fkey FOREIGN KEY (application_id) REFERENCES af_tenant_sunrise_yoga.job_applications(id) ON DELETE SET NULL;


--
-- Name: equipment equipment_room_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.equipment
    ADD CONSTRAINT equipment_room_id_fkey FOREIGN KEY (room_id) REFERENCES af_tenant_sunrise_yoga.rooms(id);


--
-- Name: equipment equipment_studio_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.equipment
    ADD CONSTRAINT equipment_studio_id_fkey FOREIGN KEY (studio_id) REFERENCES af_tenant_sunrise_yoga.studios(id);


--
-- Name: facility_schedule_completions facility_schedule_completions_schedule_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.facility_schedule_completions
    ADD CONSTRAINT facility_schedule_completions_schedule_id_fkey FOREIGN KEY (schedule_id) REFERENCES af_tenant_sunrise_yoga.facility_schedules(id) ON DELETE CASCADE;


--
-- Name: facility_schedules facility_schedules_equipment_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.facility_schedules
    ADD CONSTRAINT facility_schedules_equipment_id_fkey FOREIGN KEY (equipment_id) REFERENCES af_tenant_sunrise_yoga.equipment(id);


--
-- Name: facility_schedules facility_schedules_room_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.facility_schedules
    ADD CONSTRAINT facility_schedules_room_id_fkey FOREIGN KEY (room_id) REFERENCES af_tenant_sunrise_yoga.rooms(id);


--
-- Name: facility_schedules facility_schedules_studio_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.facility_schedules
    ADD CONSTRAINT facility_schedules_studio_id_fkey FOREIGN KEY (studio_id) REFERENCES af_tenant_sunrise_yoga.studios(id);


--
-- Name: bookings fk_bookings_class_session; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.bookings
    ADD CONSTRAINT fk_bookings_class_session FOREIGN KEY (class_session_id) REFERENCES af_tenant_sunrise_yoga.class_sessions(id) ON DELETE CASCADE NOT VALID;


--
-- Name: bookings fk_bookings_membership; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.bookings
    ADD CONSTRAINT fk_bookings_membership FOREIGN KEY (membership_id) REFERENCES af_tenant_sunrise_yoga.member_memberships(id) ON DELETE SET NULL NOT VALID;


--
-- Name: class_sessions fk_class_sessions_class_type; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.class_sessions
    ADD CONSTRAINT fk_class_sessions_class_type FOREIGN KEY (class_type_id) REFERENCES af_tenant_sunrise_yoga.class_types(id) ON DELETE RESTRICT;


--
-- Name: class_sessions fk_class_sessions_instructor; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.class_sessions
    ADD CONSTRAINT fk_class_sessions_instructor FOREIGN KEY (instructor_id) REFERENCES af_tenant_sunrise_yoga.instructors(id) ON DELETE RESTRICT;


--
-- Name: class_sessions fk_class_sessions_room; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.class_sessions
    ADD CONSTRAINT fk_class_sessions_room FOREIGN KEY (room_id) REFERENCES af_tenant_sunrise_yoga.rooms(id) ON DELETE SET NULL;


--
-- Name: inventory inventory_product_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.inventory
    ADD CONSTRAINT inventory_product_id_fkey FOREIGN KEY (product_id) REFERENCES af_tenant_sunrise_yoga.products(id) ON DELETE CASCADE;


--
-- Name: inventory_transactions inventory_transactions_product_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.inventory_transactions
    ADD CONSTRAINT inventory_transactions_product_id_fkey FOREIGN KEY (product_id) REFERENCES af_tenant_sunrise_yoga.products(id) ON DELETE CASCADE;


--
-- Name: job_application_documents job_application_documents_application_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.job_application_documents
    ADD CONSTRAINT job_application_documents_application_id_fkey FOREIGN KEY (application_id) REFERENCES af_tenant_sunrise_yoga.job_applications(id) ON DELETE CASCADE;


--
-- Name: job_application_events job_application_events_application_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.job_application_events
    ADD CONSTRAINT job_application_events_application_id_fkey FOREIGN KEY (application_id) REFERENCES af_tenant_sunrise_yoga.job_applications(id) ON DELETE CASCADE;


--
-- Name: maintenance_requests maintenance_requests_equipment_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.maintenance_requests
    ADD CONSTRAINT maintenance_requests_equipment_id_fkey FOREIGN KEY (equipment_id) REFERENCES af_tenant_sunrise_yoga.equipment(id);


--
-- Name: maintenance_requests maintenance_requests_room_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.maintenance_requests
    ADD CONSTRAINT maintenance_requests_room_id_fkey FOREIGN KEY (room_id) REFERENCES af_tenant_sunrise_yoga.rooms(id);


--
-- Name: maintenance_requests maintenance_requests_studio_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.maintenance_requests
    ADD CONSTRAINT maintenance_requests_studio_id_fkey FOREIGN KEY (studio_id) REFERENCES af_tenant_sunrise_yoga.studios(id);


--
-- Name: member_credits member_credits_member_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.member_credits
    ADD CONSTRAINT member_credits_member_id_fkey FOREIGN KEY (member_id) REFERENCES af_tenant_sunrise_yoga.members(id) ON DELETE CASCADE;


--
-- Name: member_milestones member_milestones_member_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.member_milestones
    ADD CONSTRAINT member_milestones_member_id_fkey FOREIGN KEY (member_id) REFERENCES af_tenant_sunrise_yoga.members(id) ON DELETE CASCADE;


--
-- Name: onboarding_documents onboarding_documents_packet_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.onboarding_documents
    ADD CONSTRAINT onboarding_documents_packet_id_fkey FOREIGN KEY (packet_id) REFERENCES af_tenant_sunrise_yoga.onboarding_packets(id) ON DELETE CASCADE;


--
-- Name: payroll_employee_mapping payroll_employee_mapping_instructor_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.payroll_employee_mapping
    ADD CONSTRAINT payroll_employee_mapping_instructor_id_fkey FOREIGN KEY (instructor_id) REFERENCES af_tenant_sunrise_yoga.instructors(id);


--
-- Name: payroll_line_items payroll_line_items_guest_instructor_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.payroll_line_items
    ADD CONSTRAINT payroll_line_items_guest_instructor_id_fkey FOREIGN KEY (guest_instructor_id) REFERENCES af_tenant_sunrise_yoga.guest_instructors(id) ON DELETE SET NULL;


--
-- Name: payroll_line_items payroll_line_items_instructor_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.payroll_line_items
    ADD CONSTRAINT payroll_line_items_instructor_id_fkey FOREIGN KEY (instructor_id) REFERENCES af_tenant_sunrise_yoga.instructors(id);


--
-- Name: payroll_line_items payroll_line_items_payroll_run_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.payroll_line_items
    ADD CONSTRAINT payroll_line_items_payroll_run_id_fkey FOREIGN KEY (payroll_run_id) REFERENCES af_tenant_sunrise_yoga.payroll_runs(id) ON DELETE CASCADE;


--
-- Name: pos_line_items pos_line_items_product_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.pos_line_items
    ADD CONSTRAINT pos_line_items_product_id_fkey FOREIGN KEY (product_id) REFERENCES af_tenant_sunrise_yoga.products(id);


--
-- Name: pos_line_items pos_line_items_transaction_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.pos_line_items
    ADD CONSTRAINT pos_line_items_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES af_tenant_sunrise_yoga.pos_transactions(id) ON DELETE CASCADE;


--
-- Name: price_adjustments_log price_adjustments_log_class_session_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.price_adjustments_log
    ADD CONSTRAINT price_adjustments_log_class_session_id_fkey FOREIGN KEY (class_session_id) REFERENCES af_tenant_sunrise_yoga.class_sessions(id) ON DELETE CASCADE;


--
-- Name: pricing_rules pricing_rules_studio_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.pricing_rules
    ADD CONSTRAINT pricing_rules_studio_id_fkey FOREIGN KEY (studio_id) REFERENCES af_tenant_sunrise_yoga.studios(id) ON DELETE CASCADE;


--
-- Name: reviews reviews_class_session_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.reviews
    ADD CONSTRAINT reviews_class_session_id_fkey FOREIGN KEY (class_session_id) REFERENCES af_tenant_sunrise_yoga.class_sessions(id) ON DELETE CASCADE;


--
-- Name: reviews reviews_member_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.reviews
    ADD CONSTRAINT reviews_member_id_fkey FOREIGN KEY (member_id) REFERENCES af_tenant_sunrise_yoga.members(id) ON DELETE CASCADE;


--
-- Name: sms_campaign_sends sms_campaign_sends_campaign_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.sms_campaign_sends
    ADD CONSTRAINT sms_campaign_sends_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES af_tenant_sunrise_yoga.sms_campaigns(id) ON DELETE CASCADE;


--
-- Name: sms_campaigns sms_campaigns_template_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.sms_campaigns
    ADD CONSTRAINT sms_campaigns_template_id_fkey FOREIGN KEY (template_id) REFERENCES af_tenant_sunrise_yoga.sms_templates(id) ON DELETE SET NULL;


--
-- Name: sub_finder_requests sub_finder_requests_class_session_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.sub_finder_requests
    ADD CONSTRAINT sub_finder_requests_class_session_id_fkey FOREIGN KEY (class_session_id) REFERENCES af_tenant_sunrise_yoga.class_sessions(id);


--
-- Name: sub_finder_requests sub_finder_requests_original_instructor_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.sub_finder_requests
    ADD CONSTRAINT sub_finder_requests_original_instructor_id_fkey FOREIGN KEY (original_instructor_id) REFERENCES af_tenant_sunrise_yoga.instructors(id);


--
-- Name: sub_finder_requests sub_finder_requests_substitute_instructor_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.sub_finder_requests
    ADD CONSTRAINT sub_finder_requests_substitute_instructor_id_fkey FOREIGN KEY (substitute_instructor_id) REFERENCES af_tenant_sunrise_yoga.instructors(id);


--
-- Name: time_entries time_entries_instructor_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.time_entries
    ADD CONSTRAINT time_entries_instructor_id_fkey FOREIGN KEY (instructor_id) REFERENCES af_tenant_sunrise_yoga.instructors(id);


--
-- Name: video_membership_access video_membership_access_membership_type_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.video_membership_access
    ADD CONSTRAINT video_membership_access_membership_type_id_fkey FOREIGN KEY (membership_type_id) REFERENCES af_tenant_sunrise_yoga.membership_types(id) ON DELETE CASCADE;


--
-- Name: video_membership_access video_membership_access_video_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.video_membership_access
    ADD CONSTRAINT video_membership_access_video_id_fkey FOREIGN KEY (video_id) REFERENCES af_tenant_sunrise_yoga.videos(id) ON DELETE CASCADE;


--
-- Name: video_views video_views_video_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.video_views
    ADD CONSTRAINT video_views_video_id_fkey FOREIGN KEY (video_id) REFERENCES af_tenant_sunrise_yoga.videos(id) ON DELETE CASCADE;


--
-- Name: videos videos_category_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.videos
    ADD CONSTRAINT videos_category_id_fkey FOREIGN KEY (category_id) REFERENCES af_tenant_sunrise_yoga.video_categories(id) ON DELETE SET NULL;


--
-- Name: waiver_signatures waiver_signatures_waiver_template_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.waiver_signatures
    ADD CONSTRAINT waiver_signatures_waiver_template_id_fkey FOREIGN KEY (waiver_template_id) REFERENCES af_tenant_sunrise_yoga.waiver_templates(id) ON DELETE CASCADE;


--
-- Name: workshop_contracts workshop_contracts_course_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.workshop_contracts
    ADD CONSTRAINT workshop_contracts_course_id_fkey FOREIGN KEY (course_id) REFERENCES af_tenant_sunrise_yoga.courses(id) ON DELETE CASCADE;


--
-- Name: workshop_contracts workshop_contracts_guest_instructor_id_fkey; Type: FK CONSTRAINT; Schema: af_tenant_sunrise_yoga; Owner: -
--

ALTER TABLE ONLY af_tenant_sunrise_yoga.workshop_contracts
    ADD CONSTRAINT workshop_contracts_guest_instructor_id_fkey FOREIGN KEY (guest_instructor_id) REFERENCES af_tenant_sunrise_yoga.guest_instructors(id) ON DELETE RESTRICT;


--
-- PostgreSQL database dump complete
--



SET search_path TO public;
"""


def upgrade():
    op.execute(SCHEMA_SQL)


def downgrade():
    op.execute(
        """
        DO $$
        DECLARE s TEXT;
        BEGIN
            FOR s IN SELECT schema_name FROM information_schema.schemata
                     WHERE schema_name LIKE 'af_tenant_%' OR schema_name = 'af_global'
            LOOP
                EXECUTE format('DROP SCHEMA IF EXISTS %I CASCADE', s);
            END LOOP;
        END $$;
        """
    )
