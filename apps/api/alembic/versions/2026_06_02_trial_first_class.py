"""a36_trial_first_class — trial-style memberships activate on first attendance

Revision ID: a36_trial_first_class
Revises: a35_square_billing
Create Date: 2026-06-02

Adds `membership_types.trial_starts_on_first_class` (BOOLEAN, default
FALSE). When TRUE on a type, the assignment flow no longer
pre-computes `ends_at` — the row is created with ends_at NULL and the
check-in flow activates it (ends_at = NOW() + duration_days) when the
member attends their FIRST class on the membership. This lets a
"FREE First Week Unlimited" trial give the member a full 7 days from
when they actually start coming, not from when they signed up.

Also sets the flag TRUE on Your Studio' "FREE First Week Unlimited"
row created earlier today.
"""
from alembic import op

revision = "a36_trial_first_class"
down_revision = "a35_square_billing"
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
                ADD COLUMN IF NOT EXISTS trial_starts_on_first_class
                    BOOLEAN NOT NULL DEFAULT FALSE
            $f$, schema_name);

            -- Auto-set TRUE on any "FREE First Week Unlimited" row that
            -- exists in this tenant (Your Studio already has one; other
            -- tenants may add the same type later — they can flip the
            -- flag from the staff UI when they do).
            EXECUTE format($f$
                UPDATE %I.membership_types
                SET trial_starts_on_first_class = TRUE
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
                DROP COLUMN IF EXISTS trial_starts_on_first_class
            $f$, schema_name);
        END LOOP;
    END $$;
    """)
