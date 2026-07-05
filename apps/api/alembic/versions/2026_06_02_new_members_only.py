"""a37_new_members_only — restrict trial/intro types to first-time members

Revision ID: a37_new_members_only
Revises: a36_trial_first_class
Create Date: 2026-06-02

Adds `membership_types.new_members_only` (BOOLEAN, default FALSE).
When TRUE, the type:
  - is hidden from the public portal listing for any member who
    already has at least one member_memberships row (active or
    historical, any type)
  - is rejected at assignment / purchase time with a clear 400 if
    the member has any prior membership history

Auto-sets TRUE on any existing "FREE First Week Unlimited" row (the
new offer added today is new-students-only by design; the legacy
"FREE First Class" rows are deprecated and don't need the flag).
"""
from alembic import op

revision = "a37_new_members_only"
down_revision = "a36_trial_first_class"
branch_labels = None
depends_on = None


def upgrade():
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
                ALTER TABLE %I.membership_types
                ADD COLUMN IF NOT EXISTS new_members_only
                    BOOLEAN NOT NULL DEFAULT FALSE
            $f$, schema_name);

            EXECUTE format($f$
                UPDATE %I.membership_types
                SET new_members_only = TRUE
                WHERE LOWER(name) LIKE '%%first week%%'
                  AND type = 'unlimited'
            $f$, schema_name);
        END LOOP;
    END $$;
    """)


def downgrade():
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
                ALTER TABLE %I.membership_types
                DROP COLUMN IF EXISTS new_members_only
            $f$, schema_name);
        END LOOP;
    END $$;
    """)
