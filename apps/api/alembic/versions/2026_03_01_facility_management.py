"""Facility Management — rooms enhancement, equipment, maintenance, schedules

Extends the rooms table with additional columns (description, room_type,
amenities, etc.) and creates equipment, maintenance_requests,
facility_schedules, and facility_schedule_completions tables per tenant.

Revision ID: a5_fac01
Revises: a3f_pe01
"""
from alembic import op
import sqlalchemy as sa


revision = "a5_fac01"
down_revision = "a3f_pe01"
branch_labels = None
depends_on = None


def _tenant_schemas(connection) -> list[str]:
    """Return all tenant schema names."""
    rows = connection.execute(
        sa.text("SELECT schema_name FROM af_global.organizations")
    ).fetchall()
    return [r[0] for r in rows]


def upgrade() -> None:
    conn = op.get_bind()

    for schema in _tenant_schemas(conn):
        safe = schema.replace("-", "_")

        # ── A. Extend rooms table ───────────────────────────────────────
        conn.execute(sa.text(f"""
            ALTER TABLE "{schema}".rooms
            ADD COLUMN IF NOT EXISTS description TEXT,
            ADD COLUMN IF NOT EXISTS room_type VARCHAR(30) DEFAULT 'studio',
            ADD COLUMN IF NOT EXISTS amenities JSONB DEFAULT '[]'::jsonb,
            ADD COLUMN IF NOT EXISTS photo_url TEXT,
            ADD COLUMN IF NOT EXISTS hourly_rate_cents INTEGER,
            ADD COLUMN IF NOT EXISTS max_classes_per_day INTEGER,
            ADD COLUMN IF NOT EXISTS floor_area_sqft INTEGER,
            ADD COLUMN IF NOT EXISTS setup_instructions TEXT,
            ADD COLUMN IF NOT EXISTS is_bookable BOOLEAN DEFAULT TRUE,
            ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()
        """))
        conn.execute(sa.text(f"""
            DO $$ BEGIN
                ALTER TABLE "{schema}".rooms
                ADD CONSTRAINT rooms_type_check
                    CHECK (room_type IN ('studio','meeting','outdoor','virtual','therapy','storage'));
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """))

        # ── B. Equipment table ──────────────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".equipment (
                id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                studio_id           UUID NOT NULL REFERENCES "{schema}".studios(id),
                room_id             UUID REFERENCES "{schema}".rooms(id),
                name                VARCHAR(255) NOT NULL,
                category            VARCHAR(30) NOT NULL DEFAULT 'props',
                description         TEXT,
                quantity            INTEGER DEFAULT 1,
                purchase_date       DATE,
                purchase_cost_cents INTEGER,
                condition           VARCHAR(20) DEFAULT 'good',
                warranty_expiry     DATE,
                serial_number       VARCHAR(255),
                photo_url           TEXT,
                notes               TEXT,
                is_active           BOOLEAN DEFAULT TRUE,
                created_at          TIMESTAMPTZ DEFAULT NOW(),
                updated_at          TIMESTAMPTZ DEFAULT NOW(),
                CONSTRAINT equipment_category_check
                    CHECK (category IN ('props','mats','weights','machines','audio_visual','furniture','cleaning','other')),
                CONSTRAINT equipment_condition_check
                    CHECK (condition IN ('new','good','fair','poor','retired'))
            )
        """))
        conn.execute(sa.text(f'CREATE INDEX IF NOT EXISTS idx_{safe}_equipment_studio ON "{schema}".equipment (studio_id)'))
        conn.execute(sa.text(f'CREATE INDEX IF NOT EXISTS idx_{safe}_equipment_room ON "{schema}".equipment (room_id)'))
        conn.execute(sa.text(f'CREATE INDEX IF NOT EXISTS idx_{safe}_equipment_category ON "{schema}".equipment (category)'))

        # ── C. Maintenance requests table ───────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".maintenance_requests (
                id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                studio_id           UUID NOT NULL REFERENCES "{schema}".studios(id),
                room_id             UUID REFERENCES "{schema}".rooms(id),
                equipment_id        UUID REFERENCES "{schema}".equipment(id),
                title               VARCHAR(255) NOT NULL,
                description         TEXT,
                priority            VARCHAR(20) DEFAULT 'medium',
                status              VARCHAR(20) DEFAULT 'open',
                category            VARCHAR(30) DEFAULT 'repair',
                requested_by        UUID,
                assigned_to         TEXT,
                estimated_cost_cents INTEGER,
                actual_cost_cents   INTEGER,
                scheduled_date      DATE,
                completed_at        TIMESTAMPTZ,
                completion_notes    TEXT,
                photos              JSONB DEFAULT '[]'::jsonb,
                created_at          TIMESTAMPTZ DEFAULT NOW(),
                updated_at          TIMESTAMPTZ DEFAULT NOW(),
                CONSTRAINT maintenance_priority_check
                    CHECK (priority IN ('low','medium','high','urgent')),
                CONSTRAINT maintenance_status_check
                    CHECK (status IN ('open','in_progress','completed','cancelled')),
                CONSTRAINT maintenance_category_check
                    CHECK (category IN ('repair','cleaning','replacement','inspection','safety'))
            )
        """))
        conn.execute(sa.text(f'CREATE INDEX IF NOT EXISTS idx_{safe}_maintenance_studio ON "{schema}".maintenance_requests (studio_id)'))
        conn.execute(sa.text(f'CREATE INDEX IF NOT EXISTS idx_{safe}_maintenance_status ON "{schema}".maintenance_requests (status)'))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_{safe}_maintenance_open
            ON "{schema}".maintenance_requests (status) WHERE status IN ('open','in_progress')
        """))

        # ── D. Facility schedules table ─────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".facility_schedules (
                id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                studio_id           UUID NOT NULL REFERENCES "{schema}".studios(id),
                room_id             UUID REFERENCES "{schema}".rooms(id),
                equipment_id        UUID REFERENCES "{schema}".equipment(id),
                schedule_type       VARCHAR(20) NOT NULL DEFAULT 'cleaning',
                title               VARCHAR(255) NOT NULL,
                description         TEXT,
                rrule               TEXT,
                assigned_to         TEXT,
                last_completed_at   TIMESTAMPTZ,
                next_due_at         TIMESTAMPTZ,
                is_active           BOOLEAN DEFAULT TRUE,
                created_at          TIMESTAMPTZ DEFAULT NOW(),
                updated_at          TIMESTAMPTZ DEFAULT NOW(),
                CONSTRAINT facility_schedule_type_check
                    CHECK (schedule_type IN ('cleaning','inspection','maintenance'))
            )
        """))
        conn.execute(sa.text(f'CREATE INDEX IF NOT EXISTS idx_{safe}_fac_schedule_studio ON "{schema}".facility_schedules (studio_id)'))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_{safe}_fac_schedule_overdue
            ON "{schema}".facility_schedules (next_due_at) WHERE is_active = TRUE
        """))

        # ── E. Facility schedule completions ────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".facility_schedule_completions (
                id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                schedule_id         UUID NOT NULL REFERENCES "{schema}".facility_schedules(id) ON DELETE CASCADE,
                completed_by        UUID,
                completed_at        TIMESTAMPTZ DEFAULT NOW(),
                notes               TEXT,
                photos              JSONB DEFAULT '[]'::jsonb
            )
        """))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_{safe}_fac_completion_schedule
            ON "{schema}".facility_schedule_completions (schedule_id, completed_at DESC)
        """))

    # ── Update provision function ─────────────────────────────────────
    conn.execute(sa.text(
        "DROP FUNCTION IF EXISTS af_global.provision_tenant_schema(TEXT, UUID);"
    ))
    conn.execute(sa.text(_provision_function_sql()))


def downgrade() -> None:
    conn = op.get_bind()

    for schema in _tenant_schemas(conn):
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{schema}".facility_schedule_completions CASCADE'))
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{schema}".facility_schedules CASCADE'))
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{schema}".maintenance_requests CASCADE'))
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{schema}".equipment CASCADE'))
        conn.execute(sa.text(f"""
            ALTER TABLE "{schema}".rooms
            DROP COLUMN IF EXISTS description,
            DROP COLUMN IF EXISTS room_type,
            DROP COLUMN IF EXISTS amenities,
            DROP COLUMN IF EXISTS photo_url,
            DROP COLUMN IF EXISTS hourly_rate_cents,
            DROP COLUMN IF EXISTS max_classes_per_day,
            DROP COLUMN IF EXISTS floor_area_sqft,
            DROP COLUMN IF EXISTS setup_instructions,
            DROP COLUMN IF EXISTS is_bookable,
            DROP COLUMN IF EXISTS updated_at
        """))
        conn.execute(sa.text(f"""
            DO $$ BEGIN
                ALTER TABLE "{schema}".rooms DROP CONSTRAINT IF EXISTS rooms_type_check;
            EXCEPTION WHEN undefined_object THEN NULL;
            END $$;
        """))


def _provision_function_sql():
    """Full provision function including facility management tables."""
    return """
        CREATE FUNCTION af_global.provision_tenant_schema(
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
        $fn$ LANGUAGE plpgsql;
    """
