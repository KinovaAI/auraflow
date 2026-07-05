"""member_credits + private_bookings.cancelled_by_role

Revision ID: a32_member_credits
Revises: a31_phase_c_drop_phi
Create Date: 2026-05-18

Adds a generic banked-credits system so cancelled paid sessions, courtesy
grants, and refunded-to-credit balances can be tracked and applied to
future bookings.

`member_credits`:
- Source of the credit (instructor_cancellation, courtesy, refund_to_credit, gift)
- Optional source_ref_id linking back to the originating private_booking
- Monetary amount the credit is worth (amount_cents)
- service_filter restricts which booking flow can consume it
- Expiry (6mo default per pack policy)
- used_at + used_booking_id stamped atomically when applied
- notes_enc: HIPAA-compliant encrypted free text (staff context like
  "instructor sub-out — Sarah covered for John 5/12")

`private_bookings.cancelled_by_role`:
- 'instructor' | 'member' | 'staff' | NULL (for non-cancelled rows)
- Determines whether the cancellation grants a credit (instructor) or
  forfeits it (member late-cancel outside policy window).
"""
revision = "a32_member_credits"
down_revision = "a31_phase_c_drop_phi"
branch_labels = None
depends_on = None


def upgrade():
    from alembic import op

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
            -- 1. member_credits table
            EXECUTE format($f$
                CREATE TABLE IF NOT EXISTS %I.member_credits (
                    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    member_id       UUID NOT NULL REFERENCES %I.members(id) ON DELETE CASCADE,
                    source          VARCHAR(40) NOT NULL,
                    source_ref_id   UUID,
                    service_filter  VARCHAR(40),
                    amount_cents    INTEGER NOT NULL CHECK (amount_cents >= 0),
                    expires_at      TIMESTAMPTZ,
                    used_at         TIMESTAMPTZ,
                    used_booking_id UUID,
                    used_booking_table VARCHAR(40),
                    notes_enc       BYTEA,
                    granted_by_user_id UUID,
                    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT member_credits_source_chk
                        CHECK (source IN (
                            'instructor_cancellation', 'courtesy',
                            'refund_to_credit', 'gift', 'manual_grant'
                        )),
                    CONSTRAINT member_credits_service_filter_chk
                        CHECK (service_filter IS NULL OR service_filter IN (
                            'private_session', 'class', 'workshop'
                        )),
                    CONSTRAINT member_credits_used_consistency_chk
                        CHECK ((used_at IS NULL AND used_booking_id IS NULL)
                            OR (used_at IS NOT NULL AND used_booking_id IS NOT NULL))
                )
            $f$, schema_name, schema_name);

            -- 2. Indexes — "available credits for member" is the hot query
            EXECUTE format($f$
                CREATE INDEX IF NOT EXISTS idx_%I_member_credits_available
                    ON %I.member_credits (member_id, service_filter, expires_at)
                    WHERE used_at IS NULL
            $f$, replace(schema_name, '-', '_'), schema_name);

            EXECUTE format($f$
                CREATE INDEX IF NOT EXISTS idx_%I_member_credits_source_ref
                    ON %I.member_credits (source_ref_id)
                    WHERE source_ref_id IS NOT NULL
            $f$, replace(schema_name, '-', '_'), schema_name);

            -- 3. private_bookings.cancelled_by_role
            EXECUTE format($f$
                ALTER TABLE %I.private_bookings
                    ADD COLUMN IF NOT EXISTS cancelled_by_role VARCHAR(20)
                        CHECK (cancelled_by_role IS NULL OR cancelled_by_role IN
                            ('instructor', 'member', 'staff'))
            $f$, schema_name);
        END LOOP;
    END$$;
    """)


def downgrade():
    from alembic import op

    op.execute("""
    DO $$
    DECLARE
        schema_name TEXT;
    BEGIN
        FOR schema_name IN
            SELECT s.schema_name FROM af_global.organizations o
            JOIN information_schema.schemata s ON s.schema_name = o.schema_name
            WHERE o.status IN ('active', 'trial')
        LOOP
            EXECUTE format($f$
                ALTER TABLE %I.private_bookings DROP COLUMN IF EXISTS cancelled_by_role
            $f$, schema_name);
            EXECUTE format($f$
                DROP TABLE IF EXISTS %I.member_credits CASCADE
            $f$, schema_name);
        END LOOP;
    END$$;
    """)
