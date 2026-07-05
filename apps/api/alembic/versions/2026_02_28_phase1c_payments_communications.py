"""Phase 1C — payments, communications, transaction enhancements

Adds communication_log, failed_payment_attempts tables.
Extends transactions with membership_id, booking_id, refund fields, fees.
Updates provision_tenant_schema() for new tenants.

Revision ID: a1c001
Revises: a1b001
Create Date: 2026-02-28
"""
from typing import Sequence, Union

from alembic import op

revision: str = "a1c001"
down_revision: Union[str, None] = "a1b001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _apply_to_tenant(schema: str) -> None:
    """Apply Phase 1C schema changes to a single tenant schema."""

    # ── New table: communication_log ─────────────────────────────
    op.execute(f"""
    CREATE TABLE IF NOT EXISTS {schema}.communication_log (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        member_id       UUID,
        channel         VARCHAR(20) NOT NULL CHECK (channel IN ('email', 'sms', 'push')),
        type            VARCHAR(50) NOT NULL,
        recipient       VARCHAR(255) NOT NULL,
        subject         VARCHAR(500),
        body_preview    TEXT,
        provider_id     VARCHAR(255),
        status          VARCHAR(20) DEFAULT 'sent' CHECK (status IN ('sent', 'delivered', 'failed', 'bounced')),
        metadata        JSONB DEFAULT '{{}}'::jsonb,
        created_at      TIMESTAMPTZ DEFAULT NOW()
    )
    """)

    # ── New table: failed_payment_attempts ────────────────────────
    op.execute(f"""
    CREATE TABLE IF NOT EXISTS {schema}.failed_payment_attempts (
        id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        member_id               UUID NOT NULL,
        membership_id           UUID,
        stripe_invoice_id       VARCHAR(100),
        stripe_payment_intent_id VARCHAR(100),
        amount_cents            INTEGER NOT NULL,
        failure_reason          TEXT,
        attempt_number          INTEGER DEFAULT 1,
        next_retry_at           TIMESTAMPTZ,
        resolved                BOOLEAN DEFAULT FALSE,
        resolved_at             TIMESTAMPTZ,
        created_at              TIMESTAMPTZ DEFAULT NOW()
    )
    """)

    # ── ALTER transactions — add relational + refund fields ──────
    op.execute(f"ALTER TABLE {schema}.transactions ADD COLUMN IF NOT EXISTS membership_id UUID")
    op.execute(f"ALTER TABLE {schema}.transactions ADD COLUMN IF NOT EXISTS booking_id UUID")
    op.execute(f"ALTER TABLE {schema}.transactions ADD COLUMN IF NOT EXISTS stripe_invoice_id VARCHAR(100)")
    op.execute(f"ALTER TABLE {schema}.transactions ADD COLUMN IF NOT EXISTS refund_amount_cents INTEGER")
    op.execute(f"ALTER TABLE {schema}.transactions ADD COLUMN IF NOT EXISTS refund_reason TEXT")
    op.execute(f"ALTER TABLE {schema}.transactions ADD COLUMN IF NOT EXISTS refunded_at TIMESTAMPTZ")
    op.execute(f"ALTER TABLE {schema}.transactions ADD COLUMN IF NOT EXISTS fee_cents INTEGER DEFAULT 0")
    op.execute(f"ALTER TABLE {schema}.transactions ADD COLUMN IF NOT EXISTS net_amount_cents INTEGER")
    op.execute(f"ALTER TABLE {schema}.transactions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()")

    # ── New indexes ──────────────────────────────────────────────
    safe = schema.replace("-", "_")
    op.execute(f"CREATE INDEX IF NOT EXISTS idx_{safe}_comm_log_member ON {schema}.communication_log(member_id)")
    op.execute(f"CREATE INDEX IF NOT EXISTS idx_{safe}_comm_log_type ON {schema}.communication_log(type)")
    op.execute(f"CREATE INDEX IF NOT EXISTS idx_{safe}_failed_pay_member ON {schema}.failed_payment_attempts(member_id)")
    op.execute(f"CREATE INDEX IF NOT EXISTS idx_{safe}_transactions_membership ON {schema}.transactions(membership_id)")
    op.execute(f"CREATE INDEX IF NOT EXISTS idx_{safe}_transactions_status ON {schema}.transactions(status)")


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        __import__("sqlalchemy").text(
            "SELECT schema_name FROM af_global.organizations WHERE status != 'cancelled'"
        )
    ).fetchall()
    for row in rows:
        _apply_to_tenant(row[0])

    # ── Update provision_tenant_schema() ─────────────────────────
    # Add new tables to the provisioning function
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
            cancellation_policy_hours INTEGER DEFAULT 12,
            late_cancel_fee_cents INTEGER DEFAULT 0,
            booking_window_days INTEGER DEFAULT 14,
            allow_guest_booking BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(organization_id, slug)
        )', p_schema_name, p_organization_id);

        -- Rooms
        EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.rooms (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            studio_id UUID NOT NULL, name VARCHAR(255) NOT NULL,
            capacity INTEGER, color VARCHAR(7) DEFAULT ''#6366F1'',
            sort_order INTEGER DEFAULT 0, is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )', p_schema_name);

        -- Instructors
        EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.instructors (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id UUID NOT NULL, display_name VARCHAR(255) NOT NULL,
            bio TEXT, photo_url TEXT, specialties TEXT[], certifications TEXT[],
            zoom_user_id VARCHAR(100), email VARCHAR(255), phone VARCHAR(20),
            pay_rate_cents INTEGER, pay_type VARCHAR(20) DEFAULT ''per_class'',
            tax_classification VARCHAR(20) DEFAULT ''1099'',
            color VARCHAR(7) DEFAULT ''#4F46E5'', sort_order INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW()
        )', p_schema_name);

        -- Class Types
        EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.class_types (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            studio_id UUID NOT NULL, name VARCHAR(255) NOT NULL,
            description TEXT, duration_minutes INTEGER NOT NULL DEFAULT 60,
            color VARCHAR(7) DEFAULT ''#4F46E5'', capacity INTEGER DEFAULT 20,
            level VARCHAR(30) DEFAULT ''all_levels'', tags TEXT[] DEFAULT ''{}''::text[],
            category VARCHAR(100), image_url TEXT,
            is_active BOOLEAN DEFAULT TRUE, created_at TIMESTAMPTZ DEFAULT NOW()
        )', p_schema_name);

        -- Class Series
        EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.class_series (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            studio_id UUID NOT NULL, class_type_id UUID NOT NULL,
            instructor_id UUID, room_id UUID, title VARCHAR(255) NOT NULL,
            rrule TEXT NOT NULL, start_time TIME NOT NULL, duration_minutes INTEGER NOT NULL,
            capacity INTEGER, waitlist_capacity INTEGER DEFAULT 10,
            effective_from DATE NOT NULL, effective_until DATE,
            timezone VARCHAR(50) NOT NULL DEFAULT ''America/Los_Angeles'',
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW()
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
            room_id UUID, series_id UUID,
            substitute_instructor_id UUID, notes TEXT,
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
            photo_url TEXT, source VARCHAR(50) DEFAULT ''manual'', referral_source VARCHAR(255),
            last_visit_at TIMESTAMPTZ, total_visits INTEGER DEFAULT 0,
            lifetime_revenue_cents INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            joined_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW()
        )', p_schema_name);

        -- Member Notes
        EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.member_notes (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            member_id UUID NOT NULL, author_id UUID NOT NULL,
            note TEXT NOT NULL, is_pinned BOOLEAN DEFAULT FALSE,
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
            waitlist_position INTEGER, membership_id UUID, notes TEXT,
            guest_name VARCHAR(255), guest_email VARCHAR(255),
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
            is_founding_rate BOOLEAN DEFAULT FALSE, max_enrollments INTEGER,
            auto_renew BOOLEAN DEFAULT TRUE, trial_days INTEGER DEFAULT 0,
            freeze_allowed BOOLEAN DEFAULT FALSE, max_freeze_days INTEGER DEFAULT 30,
            cancellation_notice_days INTEGER DEFAULT 0, class_types_allowed UUID[],
            is_active BOOLEAN DEFAULT TRUE, is_public BOOLEAN DEFAULT TRUE,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW()
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
            stripe_invoice_id VARCHAR(100),
            membership_id UUID, booking_id UUID,
            refund_amount_cents INTEGER, refund_reason TEXT, refunded_at TIMESTAMPTZ,
            fee_cents INTEGER DEFAULT 0, net_amount_cents INTEGER,
            description TEXT, metadata JSONB DEFAULT ''{}''::jsonb,
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW()
        )', p_schema_name);

        -- Communication Log
        EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.communication_log (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            member_id UUID,
            channel VARCHAR(20) NOT NULL CHECK (channel IN (''email'', ''sms'', ''push'')),
            type VARCHAR(50) NOT NULL,
            recipient VARCHAR(255) NOT NULL,
            subject VARCHAR(500), body_preview TEXT,
            provider_id VARCHAR(255),
            status VARCHAR(20) DEFAULT ''sent''
                CHECK (status IN (''sent'', ''delivered'', ''failed'', ''bounced'')),
            metadata JSONB DEFAULT ''{}''::jsonb,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )', p_schema_name);

        -- Failed Payment Attempts
        EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.failed_payment_attempts (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            member_id UUID NOT NULL, membership_id UUID,
            stripe_invoice_id VARCHAR(100), stripe_payment_intent_id VARCHAR(100),
            amount_cents INTEGER NOT NULL, failure_reason TEXT,
            attempt_number INTEGER DEFAULT 1,
            next_retry_at TIMESTAMPTZ, resolved BOOLEAN DEFAULT FALSE,
            resolved_at TIMESTAMPTZ,
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

        -- All indexes
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_bookings_member ON %I.bookings(member_id)',
            replace(p_schema_name, '-', '_'), p_schema_name);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_bookings_session ON %I.bookings(class_session_id)',
            replace(p_schema_name, '-', '_'), p_schema_name);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_bookings_status ON %I.bookings(status)',
            replace(p_schema_name, '-', '_'), p_schema_name);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_sessions_starts ON %I.class_sessions(starts_at)',
            replace(p_schema_name, '-', '_'), p_schema_name);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_members_email ON %I.members(email)',
            replace(p_schema_name, '-', '_'), p_schema_name);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_members_name ON %I.members(last_name, first_name)',
            replace(p_schema_name, '-', '_'), p_schema_name);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_transactions_member ON %I.transactions(member_id)',
            replace(p_schema_name, '-', '_'), p_schema_name);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_transactions_membership ON %I.transactions(membership_id)',
            replace(p_schema_name, '-', '_'), p_schema_name);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_transactions_status ON %I.transactions(status)',
            replace(p_schema_name, '-', '_'), p_schema_name);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_sessions_series ON %I.class_sessions(series_id)',
            replace(p_schema_name, '-', '_'), p_schema_name);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_sessions_room ON %I.class_sessions(room_id)',
            replace(p_schema_name, '-', '_'), p_schema_name);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_class_series_studio ON %I.class_series(studio_id)',
            replace(p_schema_name, '-', '_'), p_schema_name);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_rooms_studio ON %I.rooms(studio_id)',
            replace(p_schema_name, '-', '_'), p_schema_name);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_instructors_user ON %I.instructors(user_id)',
            replace(p_schema_name, '-', '_'), p_schema_name);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_member_notes_member ON %I.member_notes(member_id)',
            replace(p_schema_name, '-', '_'), p_schema_name);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_member_memberships_member ON %I.member_memberships(member_id)',
            replace(p_schema_name, '-', '_'), p_schema_name);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_member_memberships_status ON %I.member_memberships(status)',
            replace(p_schema_name, '-', '_'), p_schema_name);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_comm_log_member ON %I.communication_log(member_id)',
            replace(p_schema_name, '-', '_'), p_schema_name);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_comm_log_type ON %I.communication_log(type)',
            replace(p_schema_name, '-', '_'), p_schema_name);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_failed_pay_member ON %I.failed_payment_attempts(member_id)',
            replace(p_schema_name, '-', '_'), p_schema_name);

        RAISE NOTICE 'Tenant schema % provisioned for organization %', p_schema_name, p_organization_id;
    END;
    $fn$ LANGUAGE plpgsql
    """)


def downgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        __import__("sqlalchemy").text(
            "SELECT schema_name FROM af_global.organizations WHERE status != 'cancelled'"
        )
    ).fetchall()
    for row in rows:
        schema = row[0]
        op.execute(f"DROP TABLE IF EXISTS {schema}.communication_log")
        op.execute(f"DROP TABLE IF EXISTS {schema}.failed_payment_attempts")
        for col in ["membership_id", "booking_id", "stripe_invoice_id",
                     "refund_amount_cents", "refund_reason", "refunded_at",
                     "fee_cents", "net_amount_cents", "updated_at"]:
            op.execute(f"ALTER TABLE {schema}.transactions DROP COLUMN IF EXISTS {col}")
