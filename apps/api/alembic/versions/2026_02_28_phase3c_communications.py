"""Phase 3C — Communications: preferences, reminders, provider credentials

Adds email/sms opt-in columns on members, reminder_sent on bookings,
and encrypted SendGrid/Twilio credentials on af_global.organizations.

Revision ID: a2cm01
Revises: a2yt01
"""
from alembic import op
import sqlalchemy as sa


revision = "a2cm01"
down_revision = "a2yt01"
branch_labels = None
depends_on = None


def _tenant_schemas(connection) -> list[str]:
    """Return all tenant schema names."""
    rows = connection.execute(
        sa.text("SELECT schema_name FROM af_global.organizations")
    ).fetchall()
    return [r[0] for r in rows]


def upgrade() -> None:
    conn = op.get_bind()

    # ── Global schema: provider credentials ─────────────────────────────
    op.add_column(
        "organizations",
        sa.Column("sendgrid_api_key_encrypted", sa.LargeBinary(), nullable=True),
        schema="af_global",
    )
    op.add_column(
        "organizations",
        sa.Column("sendgrid_from_email", sa.String(255), nullable=True),
        schema="af_global",
    )
    op.add_column(
        "organizations",
        sa.Column("sendgrid_from_name", sa.String(100), nullable=True),
        schema="af_global",
    )
    op.add_column(
        "organizations",
        sa.Column("sendgrid_connected_at", sa.DateTime(timezone=True), nullable=True),
        schema="af_global",
    )
    op.add_column(
        "organizations",
        sa.Column("sendgrid_webhook_verified", sa.Boolean(), server_default="false"),
        schema="af_global",
    )
    op.add_column(
        "organizations",
        sa.Column("twilio_account_sid_encrypted", sa.LargeBinary(), nullable=True),
        schema="af_global",
    )
    op.add_column(
        "organizations",
        sa.Column("twilio_auth_token_encrypted", sa.LargeBinary(), nullable=True),
        schema="af_global",
    )
    op.add_column(
        "organizations",
        sa.Column("twilio_phone_number", sa.String(20), nullable=True),
        schema="af_global",
    )
    op.add_column(
        "organizations",
        sa.Column("twilio_connected_at", sa.DateTime(timezone=True), nullable=True),
        schema="af_global",
    )

    # ── Tenant schemas ──────────────────────────────────────────────────
    for schema in _tenant_schemas(conn):
        # Communication preferences on members
        conn.execute(sa.text(
            f'ALTER TABLE "{schema}".members '
            f"ADD COLUMN IF NOT EXISTS email_opt_in BOOLEAN DEFAULT TRUE"
        ))
        conn.execute(sa.text(
            f'ALTER TABLE "{schema}".members '
            f"ADD COLUMN IF NOT EXISTS sms_opt_in BOOLEAN DEFAULT TRUE"
        ))
        conn.execute(sa.text(
            f'ALTER TABLE "{schema}".members '
            f"ADD COLUMN IF NOT EXISTS email_opt_out_at TIMESTAMPTZ"
        ))
        conn.execute(sa.text(
            f'ALTER TABLE "{schema}".members '
            f"ADD COLUMN IF NOT EXISTS sms_opt_out_at TIMESTAMPTZ"
        ))

        # Reminder tracking on bookings
        conn.execute(sa.text(
            f'ALTER TABLE "{schema}".bookings '
            f"ADD COLUMN IF NOT EXISTS reminder_sent_at TIMESTAMPTZ"
        ))


def downgrade() -> None:
    conn = op.get_bind()

    for schema in _tenant_schemas(conn):
        conn.execute(sa.text(f'ALTER TABLE "{schema}".bookings DROP COLUMN IF EXISTS reminder_sent_at'))
        conn.execute(sa.text(f'ALTER TABLE "{schema}".members DROP COLUMN IF EXISTS sms_opt_out_at'))
        conn.execute(sa.text(f'ALTER TABLE "{schema}".members DROP COLUMN IF EXISTS email_opt_out_at'))
        conn.execute(sa.text(f'ALTER TABLE "{schema}".members DROP COLUMN IF EXISTS sms_opt_in'))
        conn.execute(sa.text(f'ALTER TABLE "{schema}".members DROP COLUMN IF EXISTS email_opt_in'))

    op.drop_column("organizations", "twilio_connected_at", schema="af_global")
    op.drop_column("organizations", "twilio_phone_number", schema="af_global")
    op.drop_column("organizations", "twilio_auth_token_encrypted", schema="af_global")
    op.drop_column("organizations", "twilio_account_sid_encrypted", schema="af_global")
    op.drop_column("organizations", "sendgrid_webhook_verified", schema="af_global")
    op.drop_column("organizations", "sendgrid_connected_at", schema="af_global")
    op.drop_column("organizations", "sendgrid_from_name", schema="af_global")
    op.drop_column("organizations", "sendgrid_from_email", schema="af_global")
    op.drop_column("organizations", "sendgrid_api_key_encrypted", schema="af_global")
