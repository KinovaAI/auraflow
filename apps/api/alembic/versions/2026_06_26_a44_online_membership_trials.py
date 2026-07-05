"""a44_online_membership_trials — self-serve free-trial + standing-Zoom online memberships

Revision ID: a44_online_membership_trials
Revises: a43_de34_filings
Create Date: 2026-06-26

Adds the per-tenant schema needed for organization-independent self-serve
online-membership signup with a free trial that auto-converts to paid:

  per-tenant: members.facility_name                    TEXT
                  (the facility/organization name when the member IS a
                   facility account; contact name stays in first/last_name)
              member_memberships.trial_period_end       TIMESTAMPTZ
                  (when a free trial converts to its first paid charge;
                   while current_period_end <= trial_period_end the
                   membership is still in trial / not yet converted)
              membership_types.is_online                BOOLEAN DEFAULT FALSE
              membership_types.standing_zoom_url        TEXT
              membership_types.standing_zoom_meeting_id  TEXT
              membership_types.standing_zoom_password   TEXT
                  (the always-on recurring Zoom meeting handed to every
                   member of an online plan on signup)

All columns are nullable / defaulted, so the migration is non-destructive —
existing rows and Stripe-mode studios are untouched. The DDL is wrapped in
af_global.add_online_membership_trial_fields(schema) so the SAME idempotent
ALTER runs for (a) every existing tenant in the loop below and (b) every NEW
tenant via tenant_provisioning.py — keeping the feature turnkey for any studio.
"""
from alembic import op

revision = "a44_online_membership_trials"
down_revision = "a43_de34_filings"
branch_labels = None
depends_on = None


def upgrade():
    # ── Idempotent per-schema installer (also called from provisioning) ──
    op.execute(
        """
        CREATE OR REPLACE FUNCTION af_global.add_online_membership_trial_fields(p_schema TEXT)
        RETURNS void AS $fn$
        BEGIN
            EXECUTE format($f$
                ALTER TABLE %I.members
                ADD COLUMN IF NOT EXISTS facility_name TEXT
            $f$, p_schema);

            EXECUTE format($f$
                ALTER TABLE %I.member_memberships
                ADD COLUMN IF NOT EXISTS trial_period_end TIMESTAMPTZ
            $f$, p_schema);

            EXECUTE format($f$
                ALTER TABLE %I.membership_types
                ADD COLUMN IF NOT EXISTS is_online BOOLEAN NOT NULL DEFAULT FALSE,
                ADD COLUMN IF NOT EXISTS standing_zoom_url TEXT,
                ADD COLUMN IF NOT EXISTS standing_zoom_meeting_id TEXT,
                ADD COLUMN IF NOT EXISTS standing_zoom_password TEXT
            $f$, p_schema);

            -- Find trial conversions due (the renewal scheduler charges these).
            EXECUTE format($f$
                CREATE INDEX IF NOT EXISTS member_memberships_trial_period_end_idx
                ON %I.member_memberships (trial_period_end)
                WHERE trial_period_end IS NOT NULL
            $f$, p_schema);
        END;
        $fn$ LANGUAGE plpgsql;
        """
    )

    # ── Apply to every existing tenant ───────────────────────────────────
    op.execute(
        """
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
                PERFORM af_global.add_online_membership_trial_fields(schema_name);
            END LOOP;
        END $$;
        """
    )


def downgrade():
    op.execute(
        """
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
                    DROP INDEX IF EXISTS %I.member_memberships_trial_period_end_idx
                $f$, schema_name);
                EXECUTE format($f$
                    ALTER TABLE %I.member_memberships
                    DROP COLUMN IF EXISTS trial_period_end
                $f$, schema_name);
                EXECUTE format($f$
                    ALTER TABLE %I.membership_types
                    DROP COLUMN IF EXISTS is_online,
                    DROP COLUMN IF EXISTS standing_zoom_url,
                    DROP COLUMN IF EXISTS standing_zoom_meeting_id,
                    DROP COLUMN IF EXISTS standing_zoom_password
                $f$, schema_name);
                EXECUTE format($f$
                    ALTER TABLE %I.members
                    DROP COLUMN IF EXISTS facility_name
                $f$, schema_name);
            END LOOP;
        END $$;
        """
    )
    op.execute("DROP FUNCTION IF EXISTS af_global.add_online_membership_trial_fields(TEXT)")
