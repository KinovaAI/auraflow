"""Add birthday_month + birthday_day derived columns to members

Revision ID: a26_birthday_derived
Revises: a25_refresh_device
Create Date: 2026-04-26

HIPAA 2C Phase C support: enables the daily birthday-emails task to
filter by month+day WITHOUT reading the encrypted date_of_birth_enc
column server-side (which is impossible since it's encrypted) or
loading every member into Python and decrypting (which is slow).

A month+day combo is not PHI on its own under HIPAA Safe Harbor
(§164.514) — millions of people share any given calendar date. The
full date_of_birth (with year) stays encrypted in date_of_birth_enc.
We only extract month + day separately for fast filtering.
"""

revision = "a26_birthday_derived"
down_revision = "a25_refresh_device"
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
                'ALTER TABLE %I.members
                   ADD COLUMN IF NOT EXISTS birthday_month SMALLINT,
                   ADD COLUMN IF NOT EXISTS birthday_day   SMALLINT',
                schema_name
            );
            -- Backfill from existing plaintext date_of_birth. Once
            -- plaintext drops in Phase C, this is maintained by app
            -- code on member create / update.
            EXECUTE format(
                'UPDATE %I.members
                   SET birthday_month = EXTRACT(MONTH FROM date_of_birth)::smallint,
                       birthday_day   = EXTRACT(DAY   FROM date_of_birth)::smallint
                   WHERE date_of_birth IS NOT NULL
                     AND (birthday_month IS NULL OR birthday_day IS NULL)',
                schema_name
            );
            -- Composite index for the daily birthday-emails task
            EXECUTE format(
                'CREATE INDEX IF NOT EXISTS idx_%s_members_birthday
                   ON %I.members(birthday_month, birthday_day)',
                replace(schema_name, '-', '_'), schema_name
            );
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
            SELECT o.schema_name FROM af_global.organizations o
            WHERE o.status IN ('active', 'trial')
        LOOP
            EXECUTE format(
                'DROP INDEX IF EXISTS %I.idx_%s_members_birthday',
                schema_name, replace(schema_name, '-', '_')
            );
            EXECUTE format(
                'ALTER TABLE %I.members
                   DROP COLUMN IF EXISTS birthday_month,
                   DROP COLUMN IF EXISTS birthday_day',
                schema_name
            );
        END LOOP;
    END$$;
    """)
