"""payroll_line_items: allow guest_instructor rows

Revision ID: a34_payroll_guest
Revises: a33_kiosk_devices
Create Date: 2026-05-31

Guest instructors (1099 contractors who teach standalone workshops with
guest_instructor_id set on the course) need to be paid through the
same payroll workflow as staff. Previously payroll_line_items.instructor_id
was NOT NULL with an FK to instructors only, so there was no way to
persist a "paid" row for a guest.

Schema change per tenant schema:
  - Make instructor_id nullable
  - Add guest_instructor_id NULL with FK to guest_instructors
  - CHECK: exactly one of (instructor_id, guest_instructor_id) is set
  - Replace the (payroll_run_id, instructor_id) unique constraint with
    two partial unique indexes:
       (payroll_run_id, instructor_id)        WHERE instructor_id IS NOT NULL
       (payroll_run_id, guest_instructor_id)  WHERE guest_instructor_id IS NOT NULL
    This preserves "one line per instructor per run" for both kinds
    without forcing a single column to carry both ID types.
"""
revision = "a34_payroll_guest"
down_revision = "a33_kiosk_devices"
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
            -- 1. Drop the old unique constraint (it forced instructor_id NOT NULL via the index)
            EXECUTE format($f$
                ALTER TABLE %I.payroll_line_items
                DROP CONSTRAINT IF EXISTS payroll_line_items_payroll_run_id_instructor_id_key
            $f$, schema_name);

            -- 2. Make instructor_id nullable
            EXECUTE format($f$
                ALTER TABLE %I.payroll_line_items
                ALTER COLUMN instructor_id DROP NOT NULL
            $f$, schema_name);

            -- 3. Add guest_instructor_id with FK to guest_instructors
            EXECUTE format($f$
                ALTER TABLE %I.payroll_line_items
                ADD COLUMN IF NOT EXISTS guest_instructor_id UUID
                    REFERENCES %I.guest_instructors(id) ON DELETE SET NULL
            $f$, schema_name, schema_name);

            -- 4. XOR check — exactly one of the two columns must be set
            EXECUTE format($f$
                ALTER TABLE %I.payroll_line_items
                DROP CONSTRAINT IF EXISTS payroll_line_items_one_owner_chk
            $f$, schema_name);
            EXECUTE format($f$
                ALTER TABLE %I.payroll_line_items
                ADD CONSTRAINT payroll_line_items_one_owner_chk
                CHECK (
                    (instructor_id IS NOT NULL AND guest_instructor_id IS NULL)
                    OR (instructor_id IS NULL AND guest_instructor_id IS NOT NULL)
                )
            $f$, schema_name);

            -- 5. Partial unique indexes — one line per (run, owner)
            EXECUTE format($f$
                CREATE UNIQUE INDEX IF NOT EXISTS payroll_line_items_run_instructor_uq
                ON %I.payroll_line_items (payroll_run_id, instructor_id)
                WHERE instructor_id IS NOT NULL
            $f$, schema_name);
            EXECUTE format($f$
                CREATE UNIQUE INDEX IF NOT EXISTS payroll_line_items_run_guest_uq
                ON %I.payroll_line_items (payroll_run_id, guest_instructor_id)
                WHERE guest_instructor_id IS NOT NULL
            $f$, schema_name);
        END LOOP;
    END $$;
    """)


def downgrade():
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
            EXECUTE format($f$
                DROP INDEX IF EXISTS %I.payroll_line_items_run_guest_uq
            $f$, schema_name);
            EXECUTE format($f$
                DROP INDEX IF EXISTS %I.payroll_line_items_run_instructor_uq
            $f$, schema_name);
            EXECUTE format($f$
                ALTER TABLE %I.payroll_line_items
                DROP CONSTRAINT IF EXISTS payroll_line_items_one_owner_chk
            $f$, schema_name);
            EXECUTE format($f$
                ALTER TABLE %I.payroll_line_items
                DROP COLUMN IF EXISTS guest_instructor_id
            $f$, schema_name);
            -- Don't re-NOT-NULL the column on downgrade — there may be
            -- guest rows with NULL instructor_id.
        END LOOP;
    END $$;
    """)
