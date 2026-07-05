-- ================================================
-- AuraFlow PostgreSQL Initialization
-- ================================================
-- Creates global schema and Airflow database
-- Tenant schemas are provisioned dynamically via API

-- Global schema for platform-level data
CREATE SCHEMA IF NOT EXISTS af_global;

-- Airflow gets its own database
CREATE DATABASE auraflow_airflow
    WITH ENCODING 'UTF8'
    LC_COLLATE 'C'
    LC_CTYPE 'C'
    TEMPLATE template0;

-- Extensions we'll need
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";   -- for fast text search
CREATE EXTENSION IF NOT EXISTS "btree_gin"; -- for composite indexes

-- ── Global Tables ─────────────────────────────────────────────────────────────
-- These live in af_global and are shared across all tenants

SET search_path TO af_global, public;

-- Platform users (studio owners, super admins)
CREATE TABLE IF NOT EXISTS af_global.users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    email_verified  BOOLEAN DEFAULT FALSE,
    password_hash   TEXT,
    first_name      VARCHAR(100),
    last_name       VARCHAR(100),
    phone           VARCHAR(20),
    avatar_url      TEXT,
    is_platform_admin BOOLEAN DEFAULT FALSE,
    is_active       BOOLEAN DEFAULT TRUE,
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Studio organizations (tenants)
CREATE TABLE IF NOT EXISTS af_global.organizations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    slug            VARCHAR(100) UNIQUE NOT NULL,  -- used in URLs and schema name
    name            VARCHAR(255) NOT NULL,
    schema_name     VARCHAR(100) UNIQUE NOT NULL,  -- e.g. af_tenant_abc123
    status          VARCHAR(20) DEFAULT 'trial'    -- trial, active, suspended, cancelled
                        CHECK (status IN ('trial', 'active', 'suspended', 'cancelled')),
    plan_id         VARCHAR(50),                   -- ties to Stripe product
    trial_ends_at   TIMESTAMPTZ,
    stripe_customer_id      VARCHAR(100),
    stripe_account_id       VARCHAR(100),          -- Stripe Connect account
    stripe_subscription_id  VARCHAR(100),
    stripe_charges_enabled  BOOLEAN DEFAULT FALSE, -- Stripe Connect onboarding complete
    stripe_payouts_enabled  BOOLEAN DEFAULT FALSE, -- Stripe Connect payouts active
    custom_domain   VARCHAR(255),
    primary_color   VARCHAR(7) DEFAULT '#4F46E5',
    logo_url        TEXT,
    timezone        VARCHAR(50) DEFAULT 'America/Los_Angeles',
    country         VARCHAR(2) DEFAULT 'US',
    currency        VARCHAR(3) DEFAULT 'USD',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    -- Google Ads integration
    google_ads_customer_id           VARCHAR(20),
    google_ads_refresh_token_encrypted BYTEA,
    google_ads_connected_at          TIMESTAMPTZ,
    -- Meta/Facebook Ads integration
    meta_ad_account_id               VARCHAR(50),
    meta_access_token_encrypted      BYTEA,
    meta_connected_at                TIMESTAMPTZ
);

-- Which users belong to which organizations
CREATE TABLE IF NOT EXISTS af_global.organization_users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL REFERENCES af_global.organizations(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES af_global.users(id) ON DELETE CASCADE,
    role            VARCHAR(50) NOT NULL DEFAULT 'member'
                        CHECK (role IN ('owner', 'admin', 'instructor', 'front_desk', 'member')),
    is_active       BOOLEAN DEFAULT TRUE,
    invited_by      UUID REFERENCES af_global.users(id),
    invited_at      TIMESTAMPTZ,
    joined_at       TIMESTAMPTZ,
    title           VARCHAR(100),
    department      VARCHAR(100),
    hire_date       DATE,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(organization_id, user_id)
);

-- User permissions — granular per-function access control
CREATE TABLE IF NOT EXISTS af_global.user_permissions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL REFERENCES af_global.organizations(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES af_global.users(id) ON DELETE CASCADE,
    permission_key  VARCHAR(100) NOT NULL,
    is_granted      BOOLEAN NOT NULL DEFAULT TRUE,
    granted_by      UUID REFERENCES af_global.users(id),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(organization_id, user_id, permission_key)
);

-- Platform-level feature flags (per organization)
CREATE TABLE IF NOT EXISTS af_global.feature_flags (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID REFERENCES af_global.organizations(id) ON DELETE CASCADE,
    flag_key        VARCHAR(100) NOT NULL,
    is_enabled      BOOLEAN DEFAULT FALSE,
    config          JSONB DEFAULT '{}',
    -- NULL organization_id = platform-wide default
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(organization_id, flag_key)
);

-- Default feature flags (organization_id IS NULL = platform default)
INSERT INTO af_global.feature_flags (organization_id, flag_key, is_enabled) VALUES
    (NULL, 'scheduling.group_classes', TRUE),
    (NULL, 'scheduling.private_sessions', TRUE),
    (NULL, 'scheduling.zoom_integration', TRUE),
    (NULL, 'video.on_demand_library', FALSE),
    (NULL, 'video.mux_hosting', FALSE),
    (NULL, 'video.youtube_embed', TRUE),
    (NULL, 'courses.workshops', FALSE),
    (NULL, 'courses.teacher_training', FALSE),
    (NULL, 'payments.pos_retail', FALSE),
    (NULL, 'payments.gift_cards', FALSE),
    (NULL, 'integrations.classpass', FALSE),
    (NULL, 'marketing.email_campaigns', FALSE),
    (NULL, 'marketing.sms', FALSE),
    (NULL, 'ai.newsletter_generator', FALSE),
    (NULL, 'ai.churn_prediction', FALSE),
    (NULL, 'ai.autonomous_resolution', FALSE),
    (NULL, 'marketing.google_ads', FALSE),
    (NULL, 'marketing.meta_ads', FALSE),
    (NULL, 'multi_location', FALSE)
ON CONFLICT DO NOTHING;

-- Auth refresh tokens
CREATE TABLE IF NOT EXISTS af_global.refresh_tokens (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES af_global.users(id) ON DELETE CASCADE,
    token_hash      TEXT NOT NULL UNIQUE,
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Audit log (platform level)
CREATE TABLE IF NOT EXISTS af_global.audit_log (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID REFERENCES af_global.organizations(id),
    user_id         UUID REFERENCES af_global.users(id),
    action          VARCHAR(100) NOT NULL,
    resource_type   VARCHAR(100),
    resource_id     UUID,
    metadata        JSONB DEFAULT '{}',
    ip_address      INET,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Webhook event deduplication (idempotency for Stripe etc.)
CREATE TABLE IF NOT EXISTS af_global.processed_webhook_events (
    event_id        VARCHAR(255) PRIMARY KEY,
    event_type      VARCHAR(100),
    processed_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_webhook_events_processed_at
    ON af_global.processed_webhook_events(processed_at DESC);

-- ── Indexes ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_users_email ON af_global.users(email);
CREATE INDEX IF NOT EXISTS idx_org_users_org ON af_global.organization_users(organization_id);
CREATE INDEX IF NOT EXISTS idx_org_users_user ON af_global.organization_users(user_id);
CREATE INDEX IF NOT EXISTS idx_feature_flags_org ON af_global.feature_flags(organization_id);
CREATE INDEX IF NOT EXISTS idx_feature_flags_key ON af_global.feature_flags(flag_key);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON af_global.refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_org ON af_global.audit_log(organization_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON af_global.audit_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_permissions_org_user ON af_global.user_permissions(organization_id, user_id);
CREATE INDEX IF NOT EXISTS idx_user_permissions_org_user_granted ON af_global.user_permissions(organization_id, user_id) WHERE is_granted = TRUE;

-- ── Updated At Trigger ────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION af_global.update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER users_updated_at
    BEFORE UPDATE ON af_global.users
    FOR EACH ROW EXECUTE FUNCTION af_global.update_updated_at();

CREATE OR REPLACE TRIGGER organizations_updated_at
    BEFORE UPDATE ON af_global.organizations
    FOR EACH ROW EXECUTE FUNCTION af_global.update_updated_at();

CREATE OR REPLACE TRIGGER user_permissions_updated_at
    BEFORE UPDATE ON af_global.user_permissions
    FOR EACH ROW EXECUTE FUNCTION af_global.update_updated_at();


-- ── Tenant Schema Template Function ──────────────────────────────────────────
-- Called by the API when a new studio signs up to provision their schema
CREATE OR REPLACE FUNCTION af_global.provision_tenant_schema(
    p_schema_name TEXT,
    p_org_id UUID
) RETURNS VOID AS $fn$
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

            -- ── Rooms ────────────────────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.rooms (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                studio_id       UUID NOT NULL,
                name            VARCHAR(100) NOT NULL,
                capacity        INTEGER,
                color           VARCHAR(7),
                sort_order      INTEGER DEFAULT 0,
                is_active       BOOLEAN DEFAULT TRUE,
                created_at      TIMESTAMPTZ DEFAULT NOW()
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
                email_opt_in    BOOLEAN DEFAULT TRUE,
                sms_opt_in      BOOLEAN DEFAULT TRUE,
                email_opt_out_at TIMESTAMPTZ,
                sms_opt_out_at  TIMESTAMPTZ,
                churn_risk_flagged_at TIMESTAMPTZ,
                churn_outreach_sent_at TIMESTAMPTZ,
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
                reminder_sent_at TIMESTAMPTZ,
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
                                    CHECK (status IN (''active'',''frozen'',''cancelled'',''expired'',''past_due'',''paused'')),
                starts_at       TIMESTAMPTZ NOT NULL,
                ends_at         TIMESTAMPTZ,
                current_period_end TIMESTAMPTZ,          -- synced from Stripe subscription
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
                response_text   TEXT,
                intent          VARCHAR(50),
                sender_type     VARCHAR(20),
                sender_id       UUID,
                sender_phone    VARCHAR(20),
                actions_taken   JSONB DEFAULT ''[]''::jsonb,
                status          VARCHAR(20) DEFAULT ''pending''
                                    CHECK (status IN (''pending'',''processing'',''resolved'',''escalated'')),
                assigned_to     UUID,
                resolved_at     TIMESTAMPTZ,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Sub-Finder Requests ─────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.sub_finder_requests (
                id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                class_session_id        UUID NOT NULL,
                original_instructor_id  UUID NOT NULL,
                reason                  TEXT,
                status                  VARCHAR(20) DEFAULT ''searching''
                                        CHECK (status IN (''searching'',''offered'',''filled'',''unfilled'',''cancelled'')),
                substitute_instructor_id UUID,
                contacted_instructors   JSONB DEFAULT ''[]''::jsonb,
                ai_summary              TEXT,
                created_at              TIMESTAMPTZ DEFAULT NOW(),
                updated_at              TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Office Manager Sub Requests ─────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.sub_requests (
                id                          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                class_session_id            UUID NOT NULL,
                original_instructor_id      UUID NOT NULL,
                reason                      TEXT,
                status                      VARCHAR(20) DEFAULT ''searching''
                                            CHECK (status IN (''searching'',''sub_found'',''escalated'',''cancelled'')),
                sub_instructor_id           UUID,
                current_attempt_instructor_id UUID,
                attempt_count               INTEGER DEFAULT 0,
                attempted_instructor_ids    UUID[] DEFAULT ''{}''::uuid[],
                resolved_at                 TIMESTAMPTZ,
                escalated_at                TIMESTAMPTZ,
                created_at                  TIMESTAMPTZ DEFAULT NOW()
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
                type            VARCHAR(30) DEFAULT ''transactional''
                                    CHECK (type IN (''transactional'',''marketing'',''reminder'',
                                        ''booking_confirmation'',''booking_cancellation'',''waitlist_promotion'',
                                        ''payment_failed'',''sub_request'',''sub_confirmation'',''sub_notification'',
                                        ''ai_response'')),
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

            -- ── Time Entries (Clock In/Out) ─────────────────────────────
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

            -- ── Payroll Runs ────────────────────────────────────────────
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
                created_at        TIMESTAMPTZ DEFAULT NOW(),
                updated_at        TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (period_start, period_end)
            )', p_schema_name);

            -- ── Payroll Line Items ──────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.payroll_line_items (
                id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                payroll_run_id     UUID NOT NULL,
                instructor_id      UUID NOT NULL,
                hours_worked       NUMERIC(8,2) DEFAULT 0,
                overtime_hours     NUMERIC(8,2) DEFAULT 0,
                classes_taught     INTEGER DEFAULT 0,
                class_pay_cents    INTEGER DEFAULT 0,
                hourly_pay_cents   INTEGER DEFAULT 0,
                overtime_pay_cents INTEGER DEFAULT 0,
                total_gross_cents  INTEGER DEFAULT 0,
                created_at         TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (payroll_run_id, instructor_id)
            )', p_schema_name);

            -- ── Products ──────────────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.products (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                studio_id       UUID,
                name            VARCHAR(255) NOT NULL,
                description     TEXT,
                sku             VARCHAR(100),
                price_cents     INTEGER NOT NULL DEFAULT 0,
                cost_cents      INTEGER NOT NULL DEFAULT 0,
                category        VARCHAR(50) NOT NULL DEFAULT ''retail''
                                    CHECK (category IN (''retail'', ''beverages'', ''rental'', ''merchandise'')),
                tax_rate        NUMERIC(5,4) NOT NULL DEFAULT 0.0000
                                    CHECK (tax_rate >= 0 AND tax_rate <= 1),
                image_url       TEXT,
                active          BOOLEAN NOT NULL DEFAULT TRUE,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW(),
                CONSTRAINT products_price_nonneg CHECK (price_cents >= 0),
                CONSTRAINT products_cost_nonneg CHECK (cost_cents >= 0)
            )', p_schema_name);

            -- ── Inventory ─────────────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.inventory (
                id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                product_id        UUID NOT NULL UNIQUE REFERENCES %I.products(id) ON DELETE CASCADE,
                quantity_on_hand  INTEGER NOT NULL DEFAULT 0 CHECK (quantity_on_hand >= 0),
                reorder_point     INTEGER NOT NULL DEFAULT 5,
                reorder_quantity  INTEGER NOT NULL DEFAULT 20,
                last_counted_at   TIMESTAMPTZ,
                created_at        TIMESTAMPTZ DEFAULT NOW(),
                updated_at        TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name, p_schema_name);

            -- ── Inventory Transactions (audit ledger) ─────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.inventory_transactions (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                product_id      UUID NOT NULL REFERENCES %I.products(id) ON DELETE CASCADE,
                quantity_change  INTEGER NOT NULL,
                reason          VARCHAR(50) NOT NULL
                                    CHECK (reason IN (''sale'', ''restock'', ''adjustment'', ''shrinkage'', ''opening_count'')),
                reference_id    UUID,
                notes           TEXT,
                created_by      UUID,
                created_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name, p_schema_name);

            -- ── POS Transactions ──────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.pos_transactions (
                id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                member_id         UUID,
                subtotal_cents    INTEGER NOT NULL DEFAULT 0,
                tax_cents         INTEGER NOT NULL DEFAULT 0,
                total_cents       INTEGER NOT NULL DEFAULT 0 CHECK (total_cents >= 0),
                payment_method    VARCHAR(20) NOT NULL DEFAULT ''cash''
                                      CHECK (payment_method IN (''cash'', ''card'', ''comp'', ''stripe'', ''paypal'', ''apple_pay'', ''google_pay'', ''venmo'', ''check'', ''bank_transfer'')),
                stripe_payment_id VARCHAR(255),
                status            VARCHAR(20) NOT NULL DEFAULT ''completed''
                                      CHECK (status IN (''pending'', ''completed'', ''refunded'', ''voided'')),
                notes             TEXT,
                created_by        UUID,
                created_at        TIMESTAMPTZ DEFAULT NOW(),
                updated_at        TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── POS Line Items ────────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.pos_line_items (
                id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                transaction_id   UUID NOT NULL REFERENCES %I.pos_transactions(id) ON DELETE CASCADE,
                product_id       UUID NOT NULL REFERENCES %I.products(id),
                quantity         INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
                unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0),
                tax_cents        INTEGER NOT NULL DEFAULT 0,
                total_cents      INTEGER NOT NULL,
                created_at       TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name, p_schema_name, p_schema_name);

            -- ── Member Milestones ─────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.member_milestones (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                member_id       UUID NOT NULL REFERENCES %I.members(id) ON DELETE CASCADE,
                milestone_type  VARCHAR(50) NOT NULL,
                achieved_at     TIMESTAMPTZ DEFAULT NOW(),
                notified_at     TIMESTAMPTZ,
                UNIQUE (member_id, milestone_type)
            )', p_schema_name, p_schema_name);

            -- ── Marketing Drafts ──────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.marketing_drafts (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                prompt_context  TEXT NOT NULL,
                draft_type      VARCHAR(50) NOT NULL DEFAULT ''email''
                                    CHECK (draft_type IN (''email'', ''social'', ''sms'', ''class_description'')),
                subject         TEXT,
                body            TEXT NOT NULL,
                status          VARCHAR(20) NOT NULL DEFAULT ''draft''
                                    CHECK (status IN (''draft'', ''approved'', ''rejected'', ''sent'')),
                created_by      UUID,
                reviewed_by     UUID,
                reviewed_at     TIMESTAMPTZ,
                campaign_id     UUID,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Google Ads Config ───────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.google_ads_config (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                is_enabled      BOOLEAN DEFAULT FALSE,
                max_monthly_spend_cents INTEGER NOT NULL DEFAULT 50000,
                target_latitude DECIMAL(10, 7),
                target_longitude DECIMAL(10, 7),
                target_radius_miles INTEGER DEFAULT 15,
                target_locations TEXT[] DEFAULT ''{}''::TEXT[],
                class_focus     UUID[] DEFAULT ''{}''::UUID[],
                brand_voice     VARCHAR(50) DEFAULT ''warm_professional'',
                negative_keywords TEXT[] DEFAULT ''{}''::TEXT[],
                approval_threshold_cents INTEGER DEFAULT 10000,
                auto_pause_on_zero_budget BOOLEAN DEFAULT TRUE,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Google Ads Campaigns ────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.google_ads_campaigns (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                google_campaign_id VARCHAR(50) NOT NULL,
                campaign_type   VARCHAR(30) NOT NULL
                                    CHECK (campaign_type IN (''search'', ''performance_max'', ''local_services'')),
                name            VARCHAR(255) NOT NULL,
                status          VARCHAR(20) DEFAULT ''active''
                                    CHECK (status IN (''draft'', ''active'', ''paused'', ''removed'', ''ended'')),
                daily_budget_cents INTEGER,
                bidding_strategy VARCHAR(50),
                target_roas     DECIMAL(5,2),
                start_date      DATE,
                end_date        DATE,
                created_by_ai   BOOLEAN DEFAULT TRUE,
                metadata        JSONB DEFAULT ''{}'',
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Google Ads Performance ──────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.google_ads_performance (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                campaign_id     UUID REFERENCES %I.google_ads_campaigns(id) ON DELETE CASCADE,
                google_campaign_id VARCHAR(50),
                date            DATE NOT NULL,
                impressions     INTEGER DEFAULT 0,
                clicks          INTEGER DEFAULT 0,
                conversions     DECIMAL(10,2) DEFAULT 0,
                cost_micros     BIGINT DEFAULT 0,
                conversion_value_micros BIGINT DEFAULT 0,
                ctr             DECIMAL(6,4),
                avg_cpc_micros  BIGINT,
                roas            DECIMAL(8,4),
                search_impression_share DECIMAL(6,4),
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(campaign_id, date)
            )', p_schema_name, p_schema_name);

            -- ── Google Ads AI Actions ───────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.google_ads_ai_actions (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                action_type     VARCHAR(50) NOT NULL,
                description     TEXT NOT NULL,
                reasoning       TEXT,
                campaign_id     UUID REFERENCES %I.google_ads_campaigns(id) ON DELETE SET NULL,
                changes_json    JSONB NOT NULL DEFAULT ''{}'',
                status          VARCHAR(20) DEFAULT ''executed''
                                    CHECK (status IN (''proposed'', ''approved'', ''executed'', ''rejected'', ''failed'')),
                requires_approval BOOLEAN DEFAULT FALSE,
                approved_by     UUID,
                approved_at     TIMESTAMPTZ,
                error_message   TEXT,
                created_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name, p_schema_name);

            -- ── Google Ads Conversions ──────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.google_ads_conversions (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                conversion_type VARCHAR(50) NOT NULL
                                    CHECK (conversion_type IN (''trial_signup'', ''membership_purchase'', ''class_booking'', ''class_pack_purchase'', ''contact_form'')),
                google_conversion_action_id VARCHAR(50),
                member_id       UUID,
                gclid           VARCHAR(255),
                conversion_value_cents INTEGER DEFAULT 0,
                converted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                reported_to_google BOOLEAN DEFAULT FALSE,
                reported_at     TIMESTAMPTZ,
                created_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Meta/Facebook Ads Config ──────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.meta_ads_config (
                id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                is_active               BOOLEAN DEFAULT FALSE,
                max_monthly_spend_cents  INTEGER NOT NULL DEFAULT 50000,
                target_latitude          DECIMAL(10, 7),
                target_longitude         DECIMAL(10, 7),
                target_radius_miles      INTEGER DEFAULT 15,
                target_age_min           INTEGER DEFAULT 18,
                target_age_max           INTEGER DEFAULT 65,
                target_genders           TEXT[] DEFAULT ''{}''::TEXT[],
                target_interests         TEXT[] DEFAULT ''{}''::TEXT[],
                class_focus              UUID[] DEFAULT ''{}''::UUID[],
                brand_voice              TEXT,
                excluded_interests       TEXT[] DEFAULT ''{}''::TEXT[],
                approval_threshold_cents INTEGER DEFAULT 10000,
                meta_pixel_id            VARCHAR(50),
                default_page_id          VARCHAR(50),
                instagram_account_id     VARCHAR(50),
                created_at               TIMESTAMPTZ DEFAULT NOW(),
                updated_at               TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Meta/Facebook Ads Campaigns ───────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.meta_ads_campaigns (
                id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                meta_campaign_id      VARCHAR(50) NOT NULL,
                campaign_objective    VARCHAR(50) NOT NULL
                                          CHECK (campaign_objective IN (
                                              ''OUTCOME_LEADS'', ''OUTCOME_TRAFFIC'', ''OUTCOME_AWARENESS'',
                                              ''OUTCOME_ENGAGEMENT'', ''OUTCOME_SALES''
                                          )),
                name                  VARCHAR(255) NOT NULL,
                status                VARCHAR(20) DEFAULT ''active''
                                          CHECK (status IN (''draft'', ''active'', ''paused'', ''removed'', ''ended'')),
                daily_budget_cents    INTEGER,
                lifetime_budget_cents INTEGER,
                created_by_ai         BOOLEAN DEFAULT TRUE,
                metadata              JSONB DEFAULT ''{}''::JSONB,
                created_at            TIMESTAMPTZ DEFAULT NOW(),
                updated_at            TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Meta/Facebook Ads Performance ─────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.meta_ads_performance (
                id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                campaign_id             UUID REFERENCES %I.meta_ads_campaigns(id) ON DELETE CASCADE,
                date                    DATE NOT NULL,
                impressions             INTEGER DEFAULT 0,
                reach                   INTEGER DEFAULT 0,
                clicks                  INTEGER DEFAULT 0,
                conversions             DECIMAL(10,2) DEFAULT 0,
                spend_cents             INTEGER DEFAULT 0,
                ctr                     DECIMAL(6,4),
                cpm_cents               INTEGER,
                cpc_cents               INTEGER,
                frequency               DECIMAL(6,2),
                actions_json            JSONB DEFAULT ''{}''::JSONB,
                cost_per_action_json    JSONB DEFAULT ''{}''::JSONB,
                roas                    DECIMAL(8,4),
                created_at              TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(campaign_id, date)
            )', p_schema_name, p_schema_name);

            -- ── Meta/Facebook Ads AI Actions ──────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.meta_ads_ai_actions (
                id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                action_type         VARCHAR(50) NOT NULL,
                description         TEXT NOT NULL,
                reasoning           TEXT,
                campaign_id         UUID REFERENCES %I.meta_ads_campaigns(id) ON DELETE SET NULL,
                changes_json        JSONB NOT NULL DEFAULT ''{}''::JSONB,
                status              VARCHAR(20) DEFAULT ''executed''
                                        CHECK (status IN (''proposed'', ''approved'', ''executed'', ''rejected'', ''failed'')),
                requires_approval   BOOLEAN DEFAULT FALSE,
                approved_by         UUID,
                approved_at         TIMESTAMPTZ,
                error_message       TEXT,
                created_at          TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name, p_schema_name);

            -- ── Meta/Facebook Ads Conversions ─────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.meta_ads_conversions (
                id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                conversion_type         VARCHAR(50) NOT NULL
                                            CHECK (conversion_type IN (
                                                ''trial_signup'', ''membership_purchase'', ''class_booking'',
                                                ''class_pack_purchase'', ''contact_form'', ''lead''
                                            )),
                event_name              VARCHAR(50) NOT NULL DEFAULT ''Lead'',
                member_id               UUID,
                fbclid                  VARCHAR(255),
                fbc                     VARCHAR(255),
                fbp                     VARCHAR(255),
                email_hash              VARCHAR(64),
                phone_hash              VARCHAR(64),
                conversion_value_cents  INTEGER DEFAULT 0,
                currency                VARCHAR(3) DEFAULT ''USD'',
                converted_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                reported_to_meta        BOOLEAN DEFAULT FALSE,
                reported_at             TIMESTAMPTZ,
                event_id                VARCHAR(100),
                created_at              TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            -- ── Studio User Roles (per-location staff roles) ────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.studio_user_roles (
                id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                studio_id   UUID NOT NULL REFERENCES %I.studios(id) ON DELETE CASCADE,
                user_id     UUID NOT NULL,
                role        VARCHAR(50) NOT NULL CHECK (role IN (''admin'', ''instructor'', ''front_desk'')),
                is_primary  BOOLEAN DEFAULT FALSE,
                created_at  TIMESTAMPTZ DEFAULT NOW(),
                updated_at  TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(studio_id, user_id)
            )', p_schema_name, p_schema_name);

            -- ── Engagement Autopilot ─────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.engagement_campaigns (
                id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                member_id             UUID NOT NULL REFERENCES %I.members(id) ON DELETE CASCADE,
                engagement_type       VARCHAR(30) NOT NULL CHECK (engagement_type IN (''new_dormant'', ''lapsing'', ''at_risk'')),
                status                VARCHAR(30) NOT NULL DEFAULT ''active'' CHECK (status IN (''active'', ''replied'', ''converted'', ''completed'', ''escalated'')),
                outcome               VARCHAR(60),
                followup_count        INTEGER DEFAULT 0,
                reply_count           INTEGER DEFAULT 0,
                initial_email_sent_at TIMESTAMPTZ,
                last_email_sent_at    TIMESTAMPTZ,
                created_at            TIMESTAMPTZ DEFAULT NOW(),
                updated_at            TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name, p_schema_name);

            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.engagement_messages (
                id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                campaign_id   UUID NOT NULL REFERENCES %I.engagement_campaigns(id) ON DELETE CASCADE,
                direction     VARCHAR(10) NOT NULL CHECK (direction IN (''outbound'', ''inbound'')),
                subject       TEXT,
                body          TEXT,
                sent_at       TIMESTAMPTZ,
                created_at    TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name, p_schema_name);

            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.engagement_settings (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                enabled         BOOLEAN DEFAULT FALSE,
                max_per_day     INTEGER DEFAULT 5,
                follow_up_days  INTEGER DEFAULT 7,
                singleton       BOOLEAN NOT NULL DEFAULT TRUE UNIQUE CHECK (singleton = TRUE),
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
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_te_instructor_clock ON %I.time_entries(instructor_id, clock_in)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_te_pending ON %I.time_entries(status) WHERE status = ''pending''', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_pli_run ON %I.payroll_line_items(payroll_run_id)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE UNIQUE INDEX IF NOT EXISTS idx_%s_products_sku ON %I.products(sku) WHERE sku IS NOT NULL AND active = TRUE', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_products_category ON %I.products(category) WHERE active = TRUE', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_inv_txn_product_date ON %I.inventory_transactions(product_id, created_at DESC)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_pos_txn_created ON %I.pos_transactions(created_at DESC)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_pos_line_txn ON %I.pos_line_items(transaction_id)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_milestones_member ON %I.member_milestones(member_id)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_drafts_status ON %I.marketing_drafts(status)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_drafts_created ON %I.marketing_drafts(created_at DESC)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_subfinder_session ON %I.sub_finder_requests(class_session_id)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_subfinder_status ON %I.sub_finder_requests(status) WHERE status IN (''searching'', ''offered'')', replace(p_schema_name, '-', '_'), p_schema_name);
            -- Office Manager sub_requests indexes
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_subreq_session ON %I.sub_requests(class_session_id)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_subreq_status ON %I.sub_requests(status) WHERE status = ''searching''', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_subreq_current ON %I.sub_requests(current_attempt_instructor_id) WHERE status = ''searching''', replace(p_schema_name, '-', '_'), p_schema_name);
            -- Google Ads indexes
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_gads_perf_campaign_date ON %I.google_ads_performance(campaign_id, date DESC)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_gads_actions_created ON %I.google_ads_ai_actions(created_at DESC)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_gads_actions_pending ON %I.google_ads_ai_actions(status) WHERE status = ''proposed''', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_gads_conv_gclid ON %I.google_ads_conversions(gclid) WHERE gclid IS NOT NULL', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_gads_conv_unreported ON %I.google_ads_conversions(reported_to_google) WHERE reported_to_google = FALSE', replace(p_schema_name, '-', '_'), p_schema_name);
            -- Meta/Facebook Ads indexes
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_meta_perf_campaign_date ON %I.meta_ads_performance(campaign_id, date DESC)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_meta_actions_created ON %I.meta_ads_ai_actions(created_at DESC)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_meta_actions_pending ON %I.meta_ads_ai_actions(status) WHERE status = ''proposed''', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_meta_conv_fbclid ON %I.meta_ads_conversions(fbclid) WHERE fbclid IS NOT NULL', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_meta_conv_unreported ON %I.meta_ads_conversions(reported_to_meta) WHERE reported_to_meta = FALSE', replace(p_schema_name, '-', '_'), p_schema_name);
            -- Studio user roles indexes
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_studio_user_roles_user ON %I.studio_user_roles(user_id)', replace(p_schema_name, '-', '_'), p_schema_name);
            -- Engagement autopilot indexes
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_eng_camp_member ON %I.engagement_campaigns(member_id)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_eng_camp_status ON %I.engagement_campaigns(status) WHERE status = ''active''', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_eng_camp_created ON %I.engagement_campaigns(created_at DESC)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_eng_msg_campaign ON %I.engagement_messages(campaign_id)', replace(p_schema_name, '-', '_'), p_schema_name);

            -- ── Studio Email Inbox ─────────────────────────────────────────
            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.studio_email_accounts (
                id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email_address   VARCHAR(255) NOT NULL,
                display_name    VARCHAR(255),
                imap_host       VARCHAR(255) NOT NULL,
                imap_port       INTEGER DEFAULT 993,
                imap_use_tls    BOOLEAN DEFAULT TRUE,
                smtp_host       VARCHAR(255) NOT NULL,
                smtp_port       INTEGER DEFAULT 465,
                smtp_use_tls    BOOLEAN DEFAULT TRUE,
                username        VARCHAR(255) NOT NULL,
                password_enc    BYTEA NOT NULL,
                is_active       BOOLEAN DEFAULT TRUE,
                last_checked_at TIMESTAMPTZ,
                last_uid        INTEGER DEFAULT 0,
                created_at      TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name);

            EXECUTE format('CREATE UNIQUE INDEX IF NOT EXISTS uq_%s_studio_email_accounts_email ON %I.studio_email_accounts (email_address)', replace(p_schema_name, '-', '_'), p_schema_name);

            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.studio_inbox_messages (
                id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                account_id              UUID NOT NULL REFERENCES %I.studio_email_accounts(id),
                message_uid             INTEGER,
                message_id_header       VARCHAR(500),
                in_reply_to             VARCHAR(500),
                from_email              VARCHAR(255) NOT NULL,
                from_name               VARCHAR(255),
                to_email                VARCHAR(255),
                subject                 TEXT,
                body_text               TEXT,
                body_html               TEXT,
                received_at             TIMESTAMPTZ,
                classification          VARCHAR(30) CHECK (classification IN (
                    ''booking_inquiry'', ''pricing_question'', ''schedule_question'',
                    ''cancellation'', ''complaint'', ''feedback'',
                    ''general_question'', ''spam'', ''engagement_reply''
                )),
                status                  VARCHAR(20) DEFAULT ''new'' CHECK (status IN (
                    ''new'', ''ai_resolved'', ''needs_attention'',
                    ''in_progress'', ''resolved'', ''spam''
                )),
                ai_response_text        TEXT,
                ai_response_html        TEXT,
                ai_response_sent_at     TIMESTAMPTZ,
                ai_confidence_score     FLOAT,
                assigned_to             UUID,
                resolved_by             UUID,
                resolved_at             TIMESTAMPTZ,
                member_id               UUID,
                engagement_campaign_id  UUID,
                created_at              TIMESTAMPTZ DEFAULT NOW(),
                updated_at              TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name, p_schema_name);

            -- Deduplicate by Message-ID header (unique constraint for all tenants)
            EXECUTE format('CREATE UNIQUE INDEX IF NOT EXISTS uq_%s_studio_inbox_msgid ON %I.studio_inbox_messages (message_id_header) WHERE message_id_header IS NOT NULL', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_studio_inbox_account_recv ON %I.studio_inbox_messages (account_id, received_at DESC)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_studio_inbox_status ON %I.studio_inbox_messages (status)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_studio_inbox_class ON %I.studio_inbox_messages (classification)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_studio_inbox_member ON %I.studio_inbox_messages (member_id)', replace(p_schema_name, '-', '_'), p_schema_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_studio_inbox_from ON %I.studio_inbox_messages (from_email)', replace(p_schema_name, '-', '_'), p_schema_name);

            EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I.studio_inbox_replies (
                id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                message_id  UUID NOT NULL REFERENCES %I.studio_inbox_messages(id),
                reply_by    UUID,
                reply_type  VARCHAR(10) NOT NULL CHECK (reply_type IN (''ai'', ''manual'')),
                body_text   TEXT,
                body_html   TEXT,
                sent_at     TIMESTAMPTZ,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            )', p_schema_name, p_schema_name);

            EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_studio_inbox_replies_msg ON %I.studio_inbox_replies (message_id)', replace(p_schema_name, '-', '_'), p_schema_name);

        END;
        $fn$ LANGUAGE plpgsql;

-- ── Seed a demo/dev tenant ────────────────────────────────────────
DO $$
DECLARE
    v_org_id UUID := uuid_generate_v4();
    v_user_id UUID := uuid_generate_v4();
    v_schema TEXT := 'af_tenant_demo';
BEGIN
    -- Create demo user
    INSERT INTO af_global.users (id, email, first_name, last_name, is_platform_admin, email_verified)
    VALUES (v_user_id, 'demo@example.com', 'Demo', 'Owner', TRUE, TRUE)
    ON CONFLICT (email) DO NOTHING;

    -- Create demo organization
    INSERT INTO af_global.organizations (id, slug, name, schema_name, status, timezone)
    VALUES (v_org_id, 'demo', 'Demo Studio', v_schema, 'active', 'America/Los_Angeles')
    ON CONFLICT (slug) DO NOTHING;

    -- Link user to org as owner
    INSERT INTO af_global.organization_users (organization_id, user_id, role)
    VALUES (v_org_id, v_user_id, 'owner')
    ON CONFLICT DO NOTHING;

    -- Provision the tenant schema
    PERFORM af_global.provision_tenant_schema(v_schema, v_org_id);

    RAISE NOTICE 'Demo dev tenant ready';
END $$;
