"""baseline schema from init_sql

Baseline migration — represents the schema created by infra/docker/postgres/init.sql.
For existing databases (where init.sql already ran), stamp this revision:
    alembic stamp 636bec46eb60
For fresh databases, this migration creates the full af_global schema.

Revision ID: 636bec46eb60
Revises:
Create Date: 2026-02-26 21:15:48.991601
"""
from typing import Sequence, Union

from alembic import op

revision: str = '636bec46eb60'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS af_global")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "btree_gin"')

    # -- Users --
    op.execute("""
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
    )
    """)

    # -- Organizations --
    op.execute("""
    CREATE TABLE IF NOT EXISTS af_global.organizations (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        slug            VARCHAR(100) UNIQUE NOT NULL,
        name            VARCHAR(255) NOT NULL,
        schema_name     VARCHAR(100) UNIQUE NOT NULL,
        status          VARCHAR(20) DEFAULT 'trial'
                            CHECK (status IN ('trial', 'active', 'suspended', 'cancelled')),
        plan_id         VARCHAR(50),
        trial_ends_at   TIMESTAMPTZ,
        stripe_customer_id      VARCHAR(100),
        stripe_account_id       VARCHAR(100),
        stripe_subscription_id  VARCHAR(100),
        custom_domain   VARCHAR(255),
        primary_color   VARCHAR(7) DEFAULT '#4F46E5',
        logo_url        TEXT,
        timezone        VARCHAR(50) DEFAULT 'America/Los_Angeles',
        country         VARCHAR(2) DEFAULT 'US',
        currency        VARCHAR(3) DEFAULT 'USD',
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        updated_at      TIMESTAMPTZ DEFAULT NOW()
    )
    """)

    # -- Organization Users --
    op.execute("""
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
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE(organization_id, user_id)
    )
    """)

    # -- Feature Flags --
    op.execute("""
    CREATE TABLE IF NOT EXISTS af_global.feature_flags (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        organization_id UUID REFERENCES af_global.organizations(id) ON DELETE CASCADE,
        flag_key        VARCHAR(100) NOT NULL,
        is_enabled      BOOLEAN DEFAULT FALSE,
        config          JSONB DEFAULT '{}',
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        updated_at      TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE(organization_id, flag_key)
    )
    """)

    # -- Default feature flags --
    op.execute("""
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
        (NULL, 'multi_location', FALSE)
    ON CONFLICT DO NOTHING
    """)

    # -- Refresh Tokens --
    op.execute("""
    CREATE TABLE IF NOT EXISTS af_global.refresh_tokens (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        user_id         UUID NOT NULL REFERENCES af_global.users(id) ON DELETE CASCADE,
        token_hash      TEXT NOT NULL UNIQUE,
        expires_at      TIMESTAMPTZ NOT NULL,
        revoked_at      TIMESTAMPTZ,
        created_at      TIMESTAMPTZ DEFAULT NOW()
    )
    """)

    # -- Audit Log --
    op.execute("""
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
    )
    """)

    # -- Indexes --
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON af_global.users(email)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_org_users_org ON af_global.organization_users(organization_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_org_users_user ON af_global.organization_users(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_feature_flags_org ON af_global.feature_flags(organization_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_feature_flags_key ON af_global.feature_flags(flag_key)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON af_global.refresh_tokens(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_org ON af_global.audit_log(organization_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_created ON af_global.audit_log(created_at DESC)")

    # -- Updated At Trigger --
    op.execute("""
    CREATE OR REPLACE FUNCTION af_global.update_updated_at()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = NOW();
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """)

    op.execute("""
    CREATE OR REPLACE TRIGGER users_updated_at
        BEFORE UPDATE ON af_global.users
        FOR EACH ROW EXECUTE FUNCTION af_global.update_updated_at()
    """)

    op.execute("""
    CREATE OR REPLACE TRIGGER organizations_updated_at
        BEFORE UPDATE ON af_global.organizations
        FOR EACH ROW EXECUTE FUNCTION af_global.update_updated_at()
    """)

    # -- Tenant Schema Provisioning Function --
    # This is defined here so fresh databases get it via Alembic.
    # The full function body is in infra/docker/postgres/init.sql.
    op.execute("""
    CREATE OR REPLACE FUNCTION af_global.provision_tenant_schema(
        p_schema_name VARCHAR,
        p_organization_id UUID
    )
    RETURNS VOID AS $fn$
    BEGIN
        EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I', p_schema_name);
        EXECUTE format('SET search_path TO %I, public', p_schema_name);

        -- Studios
        EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.studios (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            organization_id UUID NOT NULL DEFAULT %L,
            name VARCHAR(255) NOT NULL,
            slug VARCHAR(100) NOT NULL,
            address_line1 VARCHAR(255), address_line2 VARCHAR(255),
            city VARCHAR(100), state VARCHAR(50), postal_code VARCHAR(20),
            country VARCHAR(2) DEFAULT ''US'', phone VARCHAR(20), email VARCHAR(255),
            timezone VARCHAR(50) DEFAULT ''America/Los_Angeles'',
            is_virtual BOOLEAN DEFAULT FALSE, is_active BOOLEAN DEFAULT TRUE,
            settings JSONB DEFAULT ''{}''::jsonb,
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(organization_id, slug)
        )', p_schema_name, p_organization_id);

        -- Instructors
        EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.instructors (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id UUID NOT NULL, display_name VARCHAR(255) NOT NULL,
            bio TEXT, photo_url TEXT, specialties TEXT[], certifications TEXT[],
            zoom_user_id VARCHAR(100), is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW()
        )', p_schema_name);

        -- Class Types
        EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.class_types (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            studio_id UUID NOT NULL, name VARCHAR(255) NOT NULL,
            description TEXT, duration_minutes INTEGER NOT NULL DEFAULT 60,
            color VARCHAR(7) DEFAULT ''#4F46E5'', capacity INTEGER DEFAULT 20,
            is_active BOOLEAN DEFAULT TRUE, created_at TIMESTAMPTZ DEFAULT NOW()
        )', p_schema_name);

        -- Class Sessions
        EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.class_sessions (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            studio_id UUID NOT NULL, class_type_id UUID NOT NULL,
            instructor_id UUID, title VARCHAR(255) NOT NULL, description TEXT,
            starts_at TIMESTAMPTZ NOT NULL, ends_at TIMESTAMPTZ NOT NULL,
            timezone VARCHAR(50) NOT NULL, capacity INTEGER NOT NULL,
            waitlist_capacity INTEGER DEFAULT 10,
            is_virtual BOOLEAN DEFAULT FALSE,
            zoom_meeting_id VARCHAR(100), zoom_join_url TEXT, zoom_password VARCHAR(100),
            status VARCHAR(20) DEFAULT ''scheduled''
                CHECK (status IN (''scheduled'', ''in_progress'', ''completed'', ''cancelled'')),
            cancellation_reason TEXT, recurrence_id UUID,
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW()
        )', p_schema_name);

        -- Members
        EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.members (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id UUID NOT NULL, member_number VARCHAR(20) UNIQUE,
            first_name VARCHAR(100) NOT NULL, last_name VARCHAR(100) NOT NULL,
            email VARCHAR(255) NOT NULL, phone VARCHAR(20),
            date_of_birth DATE, gender VARCHAR(20),
            address_line1 VARCHAR(255), city VARCHAR(100), state VARCHAR(50), postal_code VARCHAR(20),
            emergency_contact_name VARCHAR(255), emergency_contact_phone VARCHAR(20),
            notes TEXT, tags TEXT[], stripe_customer_id VARCHAR(100),
            is_active BOOLEAN DEFAULT TRUE,
            joined_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW()
        )', p_schema_name);

        -- Health Data (HIPAA)
        EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.member_health_data (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            member_id UUID NOT NULL UNIQUE,
            health_data_encrypted BYTEA, injuries_encrypted BYTEA,
            conditions_encrypted BYTEA, medications_encrypted BYTEA,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )', p_schema_name);

        -- Bookings
        EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.bookings (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            member_id UUID NOT NULL, class_session_id UUID NOT NULL,
            status VARCHAR(20) DEFAULT ''confirmed''
                CHECK (status IN (''confirmed'', ''waitlisted'', ''cancelled'', ''no_show'', ''attended'')),
            booked_at TIMESTAMPTZ DEFAULT NOW(), cancelled_at TIMESTAMPTZ,
            cancellation_reason TEXT, checked_in_at TIMESTAMPTZ,
            late_cancel BOOLEAN DEFAULT FALSE, late_cancel_fee_charged BOOLEAN DEFAULT FALSE,
            source VARCHAR(50) DEFAULT ''web'',
            UNIQUE(member_id, class_session_id)
        )', p_schema_name);

        -- Membership Types
        EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.membership_types (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            studio_id UUID NOT NULL, name VARCHAR(255) NOT NULL, description TEXT,
            type VARCHAR(30) NOT NULL
                CHECK (type IN (''unlimited'', ''class_pack'', ''intro_offer'', ''day_pass'')),
            class_count INTEGER, price_cents INTEGER NOT NULL,
            billing_period VARCHAR(20)
                CHECK (billing_period IN (''monthly'', ''yearly'', ''one_time'')),
            duration_days INTEGER, stripe_price_id VARCHAR(100),
            is_active BOOLEAN DEFAULT TRUE, is_public BOOLEAN DEFAULT TRUE,
            sort_order INTEGER DEFAULT 0, created_at TIMESTAMPTZ DEFAULT NOW()
        )', p_schema_name);

        -- Member Memberships
        EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.member_memberships (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            member_id UUID NOT NULL, membership_type_id UUID NOT NULL,
            status VARCHAR(20) DEFAULT ''active''
                CHECK (status IN (''active'', ''frozen'', ''cancelled'', ''expired'', ''pending'')),
            starts_at TIMESTAMPTZ NOT NULL, ends_at TIMESTAMPTZ,
            classes_remaining INTEGER, stripe_subscription_id VARCHAR(100),
            frozen_at TIMESTAMPTZ, frozen_until TIMESTAMPTZ,
            cancelled_at TIMESTAMPTZ, cancellation_reason TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW()
        )', p_schema_name);

        -- Transactions
        EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.transactions (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            member_id UUID, type VARCHAR(50) NOT NULL,
            amount_cents INTEGER NOT NULL, currency VARCHAR(3) DEFAULT ''USD'',
            status VARCHAR(20) DEFAULT ''pending''
                CHECK (status IN (''pending'', ''completed'', ''failed'', ''refunded'', ''partially_refunded'')),
            stripe_payment_intent_id VARCHAR(100), stripe_charge_id VARCHAR(100),
            description TEXT, metadata JSONB DEFAULT ''{}''::jsonb,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )', p_schema_name);

        -- Private Services
        EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.private_services (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            instructor_id UUID NOT NULL, name VARCHAR(255) NOT NULL, description TEXT,
            duration_minutes INTEGER NOT NULL DEFAULT 60, price_cents INTEGER NOT NULL,
            buffer_before_minutes INTEGER DEFAULT 0, buffer_after_minutes INTEGER DEFAULT 15,
            max_per_day INTEGER,
            visibility VARCHAR(30) DEFAULT ''members_only''
                CHECK (visibility IN (''public'', ''members_only'', ''tier_specific'', ''invite_only'', ''staff_only'')),
            required_membership_type_id UUID,
            is_virtual BOOLEAN DEFAULT FALSE, is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )', p_schema_name);

        -- Instructor Availability
        EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.instructor_availability (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            instructor_id UUID NOT NULL,
            day_of_week INTEGER CHECK (day_of_week BETWEEN 0 AND 6),
            start_time TIME NOT NULL, end_time TIME NOT NULL,
            is_recurring BOOLEAN DEFAULT TRUE, specific_date DATE,
            is_blocked BOOLEAN DEFAULT FALSE, created_at TIMESTAMPTZ DEFAULT NOW()
        )', p_schema_name);

        -- Private Bookings
        EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.private_bookings (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            member_id UUID NOT NULL, instructor_id UUID NOT NULL,
            private_service_id UUID NOT NULL,
            starts_at TIMESTAMPTZ NOT NULL, ends_at TIMESTAMPTZ NOT NULL,
            status VARCHAR(20) DEFAULT ''pending''
                CHECK (status IN (''pending'', ''confirmed'', ''cancelled'', ''completed'', ''no_show'')),
            is_virtual BOOLEAN DEFAULT FALSE,
            zoom_meeting_id VARCHAR(100), zoom_join_url TEXT,
            intake_notes TEXT, instructor_notes TEXT, transaction_id UUID,
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW()
        )', p_schema_name);

        -- Resolution Requests
        EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.resolution_requests (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            member_id UUID,
            category VARCHAR(50) NOT NULL
                CHECK (category IN (''billing'', ''scheduling'', ''membership'', ''technical'', ''general'')),
            status VARCHAR(20) DEFAULT ''open''
                CHECK (status IN (''open'', ''ai_processing'', ''awaiting_approval'', ''resolved'', ''escalated'')),
            member_message TEXT NOT NULL,
            ai_summary TEXT, ai_decision TEXT, ai_action_taken TEXT,
            ai_confidence DECIMAL(3,2), requires_approval BOOLEAN DEFAULT TRUE,
            approved_by UUID, approved_at TIMESTAMPTZ,
            resolved_at TIMESTAMPTZ, escalated_to UUID, escalation_reason TEXT,
            audit_trail JSONB DEFAULT ''[]''::jsonb,
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW()
        )', p_schema_name);

        -- Tenant indexes
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_bookings_member ON %I.bookings(member_id)',
            replace(p_schema_name, '-', '_'), p_schema_name);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_bookings_session ON %I.bookings(class_session_id)',
            replace(p_schema_name, '-', '_'), p_schema_name);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_sessions_starts ON %I.class_sessions(starts_at)',
            replace(p_schema_name, '-', '_'), p_schema_name);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_members_email ON %I.members(email)',
            replace(p_schema_name, '-', '_'), p_schema_name);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_transactions_member ON %I.transactions(member_id)',
            replace(p_schema_name, '-', '_'), p_schema_name);

        RAISE NOTICE 'Tenant schema % provisioned for organization %', p_schema_name, p_organization_id;
    END;
    $fn$ LANGUAGE plpgsql
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS af_global.provision_tenant_schema(VARCHAR, UUID)")
    op.execute("DROP FUNCTION IF EXISTS af_global.update_updated_at() CASCADE")
    op.execute("DROP TABLE IF EXISTS af_global.audit_log")
    op.execute("DROP TABLE IF EXISTS af_global.refresh_tokens")
    op.execute("DROP TABLE IF EXISTS af_global.feature_flags")
    op.execute("DROP TABLE IF EXISTS af_global.organization_users")
    op.execute("DROP TABLE IF EXISTS af_global.organizations")
    op.execute("DROP TABLE IF EXISTS af_global.users")
    op.execute("DROP SCHEMA IF EXISTS af_global CASCADE")
