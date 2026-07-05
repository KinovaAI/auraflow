"""HIPAA 2C Phase C — drop plaintext PHI columns

Revision ID: a31_phase_c_drop_phi
Revises: a30_instructor_phone_hash
Create Date: 2026-05-09

Final cut of the HIPAA 2C migration. Drops the plaintext columns that
have been dual-written alongside *_enc shadows since Phase B
(2026-04-23). After this migration only the encrypted columns + their
derived helpers (birthday_month/day, phone_hash) remain.

Pre-flight checklist (DO NOT apply this migration without each box
checked):

    [ ] PHI consistency scan returns 0 mismatches AND 0 backfill-needed
        for ≥3 consecutive days (run via
        `app.workers.tasks.phi_consistency.nightly_phi_scan`).
    [ ] At-rest sanity SQL shows 0 plain-only rows on every column
        listed below across every tenant schema (not just Your Studio —
        re-run the audit if other tenants have been added since
        2026-05-09).
    [ ] `pg_dump` of `members` + `member_notes` taken and stored
        encrypted off-host. The downgrade in this file restores the
        column SHAPE but not the DATA — without a snapshot, a
        rollback would leave members with NULL plaintext.
    [ ] Code fallbacks removed from
        `app/services/members/member_service.py:_row_with_decrypted_phi`
        and `app/services/ai/office_manager_service.py:_lookup_sender`
        (or their plaintext-fallback branches verified harmless when
        the column is gone — they currently fall back to plaintext
        when *_enc / phone_hash is NULL, which is impossible after
        Phase B closed those gaps).
    [ ] Late-evening Pacific deploy window — column drops on a 100k+
        row table take seconds but lock the table briefly; off-hours
        is the right time.

Columns dropped per tenant schema:

  members.phone                     (covered by phone_enc + phone_hash)
  members.date_of_birth             (covered by date_of_birth_enc + birthday_month/day)
  members.address_line1             (covered by address_line1_enc)
  members.city                      (covered by city_enc)
  members.state                     (covered by state_enc)
  members.postal_code               (covered by postal_code_enc)
  members.emergency_contact_name    (covered by emergency_contact_name_enc)
  members.emergency_contact_phone   (covered by emergency_contact_phone_enc)
  members.notes                     (covered by notes_enc)
  member_notes.note                 (covered by note_enc)
"""

revision = "a31_phase_c_drop_phi"
down_revision = "a30_instructor_phone_hash"
branch_labels = None
depends_on = None


_PLAINTEXT_COLUMNS_TO_DROP = [
    ("members", "phone"),
    ("members", "date_of_birth"),
    ("members", "address_line1"),
    ("members", "city"),
    ("members", "state"),
    ("members", "postal_code"),
    ("members", "emergency_contact_name"),
    ("members", "emergency_contact_phone"),
    ("members", "notes"),
    ("member_notes", "note"),
]


def upgrade():
    from alembic import op

    # Single DO block iterates active tenant schemas. Each ALTER TABLE
    # runs as its own statement inside the migration's transaction so
    # if any one fails (e.g. a schema is missing a table because of a
    # half-applied prior migration) the whole migration rolls back.
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
            -- members
            EXECUTE format(
                'ALTER TABLE %I.members
                   DROP COLUMN IF EXISTS phone,
                   DROP COLUMN IF EXISTS date_of_birth,
                   DROP COLUMN IF EXISTS address_line1,
                   DROP COLUMN IF EXISTS city,
                   DROP COLUMN IF EXISTS state,
                   DROP COLUMN IF EXISTS postal_code,
                   DROP COLUMN IF EXISTS emergency_contact_name,
                   DROP COLUMN IF EXISTS emergency_contact_phone,
                   DROP COLUMN IF EXISTS notes',
                schema_name
            );
            -- member_notes
            EXECUTE format(
                'ALTER TABLE %I.member_notes
                   DROP COLUMN IF EXISTS note',
                schema_name
            );
        END LOOP;
    END$$;
    """)


def downgrade():
    """Restore the column shape ONLY. Data is gone — without a pg_dump
    snapshot from before the upgrade, rollback leaves members with NULL
    plaintext. The dual-read helpers
    (member_service._row_with_decrypted_phi etc.) will fall through to
    the *_enc shadows automatically, so the system stays functional
    on rollback even with NULL plaintext, but the plaintext columns
    will be empty until a manual restore from the snapshot.
    """
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
            EXECUTE format(
                'ALTER TABLE %I.members
                   ADD COLUMN IF NOT EXISTS phone                    VARCHAR(20),
                   ADD COLUMN IF NOT EXISTS date_of_birth            DATE,
                   ADD COLUMN IF NOT EXISTS address_line1            VARCHAR(255),
                   ADD COLUMN IF NOT EXISTS city                     VARCHAR(100),
                   ADD COLUMN IF NOT EXISTS state                    VARCHAR(50),
                   ADD COLUMN IF NOT EXISTS postal_code              VARCHAR(20),
                   ADD COLUMN IF NOT EXISTS emergency_contact_name   VARCHAR(100),
                   ADD COLUMN IF NOT EXISTS emergency_contact_phone  VARCHAR(20),
                   ADD COLUMN IF NOT EXISTS notes                    TEXT',
                schema_name
            );
            EXECUTE format(
                'ALTER TABLE %I.member_notes
                   ADD COLUMN IF NOT EXISTS note TEXT',
                schema_name
            );
        END LOOP;
    END$$;
    """)
