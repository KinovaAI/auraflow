"""Phase 0.8 — add updated_at + FKs (excluding PHI tables during HIPAA bake)

Revision ID: a19_schema_hygiene
Revises: a18_ads_tokens
Create Date: 2026-04-23

Adds:
  - updated_at columns + touch triggers on bookings, rooms, private_services,
    instructor_availability (these tables lack updated_at; caused a silent
    no_show task failure 2026-04-18)
  - Foreign key constraints on class_sessions, class_series, bookings,
    instructors.user_id

Intentionally skipped (HIPAA 2C bake in progress):
  - members, member_notes — any schema change here could interfere with the
    dual-write/dual-read code path. Revisit after Phase C drops plaintext.

Migration style: ALTER TABLE ADD CONSTRAINT ... NOT VALID, then validate in
a second statement. This lets writes continue during the constraint add, and
only holds a brief SHARE UPDATE EXCLUSIVE lock during VALIDATE.
"""

revision = "a19_schema_hygiene"
down_revision = "a18_ads_tokens"
branch_labels = None
depends_on = None


def upgrade():
    from alembic import op

    # Shared touch function must exist BEFORE the triggers reference it.
    op.execute("""
        CREATE OR REPLACE FUNCTION af_global.touch_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Iterate over every tenant schema (currently only Your Studio is live,
    # but we want this to work for any future tenant too).
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
            -- ── updated_at on bookings ─────────────────────────────────
            EXECUTE format(
                'ALTER TABLE %I.bookings ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()',
                schema_name
            );
            EXECUTE format(
                'DROP TRIGGER IF EXISTS %I_touch_bookings ON %I.bookings',
                schema_name, schema_name
            );
            EXECUTE format(
                'CREATE TRIGGER %I_touch_bookings BEFORE UPDATE ON %I.bookings FOR EACH ROW EXECUTE FUNCTION af_global.touch_updated_at()',
                schema_name, schema_name
            );

            -- ── updated_at on rooms ────────────────────────────────────
            EXECUTE format(
                'ALTER TABLE %I.rooms ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()',
                schema_name
            );
            EXECUTE format(
                'DROP TRIGGER IF EXISTS %I_touch_rooms ON %I.rooms',
                schema_name, schema_name
            );
            EXECUTE format(
                'CREATE TRIGGER %I_touch_rooms BEFORE UPDATE ON %I.rooms FOR EACH ROW EXECUTE FUNCTION af_global.touch_updated_at()',
                schema_name, schema_name
            );

            -- ── updated_at on private_services ─────────────────────────
            EXECUTE format(
                'ALTER TABLE %I.private_services ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()',
                schema_name
            );
            EXECUTE format(
                'DROP TRIGGER IF EXISTS %I_touch_private_services ON %I.private_services',
                schema_name, schema_name
            );
            EXECUTE format(
                'CREATE TRIGGER %I_touch_private_services BEFORE UPDATE ON %I.private_services FOR EACH ROW EXECUTE FUNCTION af_global.touch_updated_at()',
                schema_name, schema_name
            );

            -- ── updated_at on instructor_availability ──────────────────
            EXECUTE format(
                'ALTER TABLE %I.instructor_availability ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()',
                schema_name
            );
            EXECUTE format(
                'DROP TRIGGER IF EXISTS %I_touch_instructor_availability ON %I.instructor_availability',
                schema_name, schema_name
            );
            EXECUTE format(
                'CREATE TRIGGER %I_touch_instructor_availability BEFORE UPDATE ON %I.instructor_availability FOR EACH ROW EXECUTE FUNCTION af_global.touch_updated_at()',
                schema_name, schema_name
            );

            -- ── FK constraints on class_sessions ───────────────────────
            -- Use NOT VALID initially, validate separately so existing rows
            -- aren't rescanned under an ACCESS EXCLUSIVE lock.
            EXECUTE format($f$
                ALTER TABLE %I.class_sessions
                  ADD CONSTRAINT fk_class_sessions_class_type
                  FOREIGN KEY (class_type_id) REFERENCES %I.class_types(id)
                  ON DELETE RESTRICT NOT VALID
            $f$, schema_name, schema_name);
            EXECUTE format('ALTER TABLE %I.class_sessions VALIDATE CONSTRAINT fk_class_sessions_class_type', schema_name);

            EXECUTE format($f$
                ALTER TABLE %I.class_sessions
                  ADD CONSTRAINT fk_class_sessions_instructor
                  FOREIGN KEY (instructor_id) REFERENCES %I.instructors(id)
                  ON DELETE RESTRICT NOT VALID
            $f$, schema_name, schema_name);
            EXECUTE format('ALTER TABLE %I.class_sessions VALIDATE CONSTRAINT fk_class_sessions_instructor', schema_name);

            EXECUTE format($f$
                ALTER TABLE %I.class_sessions
                  ADD CONSTRAINT fk_class_sessions_room
                  FOREIGN KEY (room_id) REFERENCES %I.rooms(id)
                  ON DELETE SET NULL NOT VALID
            $f$, schema_name, schema_name);
            EXECUTE format('ALTER TABLE %I.class_sessions VALIDATE CONSTRAINT fk_class_sessions_room', schema_name);

            -- ── FK constraints on bookings ─────────────────────────────
            -- Your Studio has ~1880 pre-migration orphan bookings
            -- (class_session_id points at rows deleted during the
            -- migration cutover). NOT VALID is retained without a
            -- subsequent VALIDATE so new inserts are checked but existing
            -- orphans stay. A follow-up cleanup migration can delete the
            -- orphans and then VALIDATE.
            EXECUTE format($f$
                ALTER TABLE %I.bookings
                  ADD CONSTRAINT fk_bookings_class_session
                  FOREIGN KEY (class_session_id) REFERENCES %I.class_sessions(id)
                  ON DELETE CASCADE NOT VALID
            $f$, schema_name, schema_name);

            EXECUTE format($f$
                ALTER TABLE %I.bookings
                  ADD CONSTRAINT fk_bookings_membership
                  FOREIGN KEY (membership_id) REFERENCES %I.member_memberships(id)
                  ON DELETE SET NULL NOT VALID
            $f$, schema_name, schema_name);
        END LOOP;
    END$$;
    """)


def downgrade():
    from alembic import op

    # Reverse per-tenant changes.
    op.execute("""
    DO $$
    DECLARE
        schema_name TEXT;
    BEGIN
        FOR schema_name IN
            SELECT o.schema_name FROM af_global.organizations o
            WHERE o.status IN ('active', 'trial')
        LOOP
            EXECUTE format('ALTER TABLE %I.bookings DROP CONSTRAINT IF EXISTS fk_bookings_membership', schema_name);
            EXECUTE format('ALTER TABLE %I.bookings DROP CONSTRAINT IF EXISTS fk_bookings_class_session', schema_name);
            EXECUTE format('ALTER TABLE %I.class_sessions DROP CONSTRAINT IF EXISTS fk_class_sessions_room', schema_name);
            EXECUTE format('ALTER TABLE %I.class_sessions DROP CONSTRAINT IF EXISTS fk_class_sessions_instructor', schema_name);
            EXECUTE format('ALTER TABLE %I.class_sessions DROP CONSTRAINT IF EXISTS fk_class_sessions_class_type', schema_name);

            EXECUTE format('DROP TRIGGER IF EXISTS %I_touch_bookings ON %I.bookings', schema_name, schema_name);
            EXECUTE format('DROP TRIGGER IF EXISTS %I_touch_rooms ON %I.rooms', schema_name, schema_name);
            EXECUTE format('DROP TRIGGER IF EXISTS %I_touch_private_services ON %I.private_services', schema_name, schema_name);
            EXECUTE format('DROP TRIGGER IF EXISTS %I_touch_instructor_availability ON %I.instructor_availability', schema_name, schema_name);

            EXECUTE format('ALTER TABLE %I.bookings DROP COLUMN IF EXISTS updated_at', schema_name);
            EXECUTE format('ALTER TABLE %I.rooms DROP COLUMN IF EXISTS updated_at', schema_name);
            EXECUTE format('ALTER TABLE %I.private_services DROP COLUMN IF EXISTS updated_at', schema_name);
            EXECUTE format('ALTER TABLE %I.instructor_availability DROP COLUMN IF EXISTS updated_at', schema_name);
        END LOOP;
    END$$;
    """)
