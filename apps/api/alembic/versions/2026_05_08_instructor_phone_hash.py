"""Add phone_hash column to instructors

Revision ID: a30_instructor_phone_hash
Revises: a29_workshop_contracts
Create Date: 2026-05-08

HIPAA 2C Phase C support for the SMS-routing path. The Office Manager
service looks up instructors by their phone number when a Twilio webhook
delivers an inbound message — that lookup currently uses
`WHERE phone = $1` against the plaintext column. After the Phase C drop
of plaintext PHI, that query returns zero rows and instructor SMS routing
breaks.

phone_hash is HMAC-SHA256(APP_SECRET, normalized_phone) — deterministic,
non-reversible, queryable. Members already have it; this adds it to
instructors with a backfill from the existing plaintext column.
"""

revision = "a30_instructor_phone_hash"
down_revision = "a29_workshop_contracts"
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
            EXECUTE format(
                'ALTER TABLE %I.instructors
                   ADD COLUMN IF NOT EXISTS phone_hash VARCHAR(64)',
                schema_name
            );
            EXECUTE format(
                'CREATE INDEX IF NOT EXISTS idx_%s_instructors_phone_hash
                   ON %I.instructors(phone_hash) WHERE phone_hash IS NOT NULL',
                replace(schema_name, '-', '_'), schema_name
            );
        END LOOP;
    END$$;
    """)
    # Backfill is done in app code (uses APP_SECRET-derived HMAC; can't run
    # in raw SQL without exposing the key). See the post-deploy backfill
    # script: scripts/backfill_instructor_phone_hash.py.


def downgrade():
    from alembic import op
    op.execute("""
    DO $$
    DECLARE
        schema_name TEXT;
    BEGIN
        FOR schema_name IN
            SELECT o.schema_name FROM af_global.organizations o
            WHERE o.status IN ('active', 'trial')
        LOOP
            EXECUTE format(
                'DROP INDEX IF EXISTS %I.idx_%s_instructors_phone_hash',
                schema_name, replace(schema_name, '-', '_')
            );
            EXECUTE format(
                'ALTER TABLE %I.instructors
                   DROP COLUMN IF EXISTS phone_hash',
                schema_name
            );
        END LOOP;
    END$$;
    """)
