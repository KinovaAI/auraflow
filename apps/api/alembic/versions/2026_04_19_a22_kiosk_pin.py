"""Add kiosk_pin_hash + kiosk_pin_set_at to af_global.organization_users

Phase 3 of the white-label portal — lets a staff member (front_desk /
admin / owner) authenticate at a kiosk via a 4-digit PIN instead of
full email+password. The PIN is bcrypt-hashed; the salt + cost are in
the hash itself.

  kiosk_pin_hash      TEXT NULL  — bcrypt hash of the PIN (NULL = no PIN set)
  kiosk_pin_set_at    TIMESTAMPTZ NULL — when set/rotated, for audit

Behavior change: NONE in this migration alone — both columns default
NULL. The /external/kiosk/session endpoint that READS these columns
lands in the same branch.

Existing dashboard kiosk path (`apps/web/(dashboard)/check-in/kiosk`)
uses standard JWT auth and is unaffected. PIN-based kiosk auth is a
SECOND, additive way to obtain a JWT for a staff identity — used by
the white-label portal kiosk so a staff member doesn't have to type
their full password on a public-facing tablet.

Revision ID: a22_kiosk_pin
Revises: a21_portal_branding_columns
Create Date: 2026-04-19
"""
from alembic import op
import sqlalchemy as sa


revision = "a22_kiosk_pin"
down_revision = "a21_portal_branding_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organization_users",
        sa.Column("kiosk_pin_hash", sa.Text(), nullable=True),
        schema="af_global",
    )
    op.add_column(
        "organization_users",
        sa.Column("kiosk_pin_set_at", sa.DateTime(timezone=True), nullable=True),
        schema="af_global",
    )


def downgrade() -> None:
    op.drop_column("organization_users", "kiosk_pin_set_at", schema="af_global")
    op.drop_column("organization_users", "kiosk_pin_hash", schema="af_global")
