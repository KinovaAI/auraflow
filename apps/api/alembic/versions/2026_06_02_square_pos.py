"""a38_square_pos — Square POS (Terminal API + saved-card) infrastructure

Revision ID: a38_square_pos
Revises: a37_new_members_only
Create Date: 2026-06-02

Global:
  - af_global.square_pos_devices: paired Terminal / Square POS app /
    Register devices per organization. One row per (org, device_id).
  - af_global.organizations: square_pos_default_device_id (FK to row in
    square_pos_devices by uuid — kept as UUID, app enforces consistency).

Tenant:
  - <schema>.pos_terminal_checkouts: in-flight POS sales. Webhook
    handler updates these as Square reports completion / cancel / fail.
    Amount has a CHECK constraint > 0 so hand-crafted zero-amount
    charges are rejected. The endpoint enforces an exact-price match
    against the source membership_type / drop_in / class_pack — staff
    are NEVER allowed to override pricing (feedback_no_staff_discounts).
  - <schema>.members: square_card_on_file_id + brand/last4/exp metadata.
    Card data itself stays in Square; we only store the pointer + last4
    for the staff UI. PCI scope unchanged.

ALWAYS save card on file (feedback_always_save_card) — there is no
toggle, no customer prompt at the terminal hardware, no staff override.
The webhook handler saves the card via Cards API post-checkout using
the resulting payment_id as the source. Customer's consent is captured
implicitly via the studio's enrollment terms + the act of completing
the in-person transaction.
"""
from alembic import op

revision = "a38_square_pos"
down_revision = "a37_new_members_only"
branch_labels = None
depends_on = None


def upgrade():
    # ── Global ────────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS af_global.square_pos_devices (
        id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        organization_id  UUID NOT NULL REFERENCES af_global.organizations(id) ON DELETE CASCADE,
        device_id        TEXT NOT NULL,
        name             TEXT NOT NULL,
        device_type      TEXT,
        paired_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_seen_at     TIMESTAMPTZ,
        status           TEXT NOT NULL DEFAULT 'unknown',
        created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (organization_id, device_id)
    );
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS square_pos_devices_org_idx
        ON af_global.square_pos_devices (organization_id);
    """)
    op.execute("""
    ALTER TABLE af_global.organizations
        ADD COLUMN IF NOT EXISTS square_pos_default_device_id UUID
            REFERENCES af_global.square_pos_devices(id) ON DELETE SET NULL,
        ADD COLUMN IF NOT EXISTS square_pos_tip_settings JSONB;
    """)

    # ── Tenant loop ───────────────────────────────────────────────────
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
            -- pos_terminal_checkouts: in-flight POS sales
            EXECUTE format($f$
                CREATE TABLE IF NOT EXISTS %I.pos_terminal_checkouts (
                    id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    member_id             UUID NOT NULL,
                    amount_cents          INT NOT NULL CHECK (amount_cents > 0),
                    app_fee_cents         INT NOT NULL DEFAULT 0,
                    description           TEXT,
                    device_id             TEXT,
                    flow                  TEXT NOT NULL CHECK (flow IN ('terminal','deeplink')),
                    square_checkout_id    TEXT,
                    square_payment_id     TEXT,
                    square_card_id        TEXT,
                    square_customer_id    TEXT,
                    membership_type_id    UUID,
                    status                TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','in_progress','completed','cancelled','failed','expired')),
                    failure_reason        TEXT,
                    reference_id          TEXT,
                    initiated_by_user_id  UUID,
                    initiated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    completed_at          TIMESTAMPTZ,
                    expires_at            TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '10 minutes')
                )
            $f$, schema_name);

            EXECUTE format($f$
                CREATE INDEX IF NOT EXISTS pos_terminal_checkouts_status_idx
                    ON %I.pos_terminal_checkouts (status, expires_at)
            $f$, schema_name);
            EXECUTE format($f$
                CREATE INDEX IF NOT EXISTS pos_terminal_checkouts_member_idx
                    ON %I.pos_terminal_checkouts (member_id, initiated_at DESC)
            $f$, schema_name);
            EXECUTE format($f$
                CREATE INDEX IF NOT EXISTS pos_terminal_checkouts_square_idx
                    ON %I.pos_terminal_checkouts (square_checkout_id)
                    WHERE square_checkout_id IS NOT NULL
            $f$, schema_name);

            -- members.square_card_on_file_* — pointer only, never PAN
            EXECUTE format($f$
                ALTER TABLE %I.members
                    ADD COLUMN IF NOT EXISTS square_card_on_file_id TEXT,
                    ADD COLUMN IF NOT EXISTS square_card_on_file_brand TEXT,
                    ADD COLUMN IF NOT EXISTS square_card_on_file_last4 TEXT,
                    ADD COLUMN IF NOT EXISTS square_card_on_file_exp_month INT,
                    ADD COLUMN IF NOT EXISTS square_card_on_file_exp_year INT,
                    ADD COLUMN IF NOT EXISTS square_card_on_file_saved_at TIMESTAMPTZ
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
            EXECUTE format($f$DROP TABLE IF EXISTS %I.pos_terminal_checkouts$f$, schema_name);
            EXECUTE format($f$
                ALTER TABLE %I.members
                    DROP COLUMN IF EXISTS square_card_on_file_id,
                    DROP COLUMN IF EXISTS square_card_on_file_brand,
                    DROP COLUMN IF EXISTS square_card_on_file_last4,
                    DROP COLUMN IF EXISTS square_card_on_file_exp_month,
                    DROP COLUMN IF EXISTS square_card_on_file_exp_year,
                    DROP COLUMN IF EXISTS square_card_on_file_saved_at
            $f$, schema_name);
        END LOOP;
    END $$;
    """)
    op.execute("""
    ALTER TABLE af_global.organizations
        DROP COLUMN IF EXISTS square_pos_default_device_id,
        DROP COLUMN IF EXISTS square_pos_tip_settings;
    """)
    op.execute("DROP TABLE IF EXISTS af_global.square_pos_devices;")
