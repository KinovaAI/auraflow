"""kiosk_devices — server-side device-bound kiosk lockdown

Revision ID: a33_kiosk_devices
Revises: a32_member_credits
Create Date: 2026-05-26

Adds `af_global.kiosk_devices`: when a studio registers an iPad as a
dedicated check-in kiosk, a row is written here and a long-lived
httponly cookie is set on the device. The middleware enforces that the
device can ONLY reach `/dashboard/check-in/kiosk` and the read-only
APIs the check-in flow needs.

The previous lock was a client-side cookie only — anyone could clear
Safari cookies and sign in. With this table, the API can also rebind
the cookie automatically when (source_ip, user_agent) matches a
previously-registered device, so clearing cookies no longer escapes
the lockdown.

Fingerprint values are hashed (sha256) so we never store a raw IP or
UA on disk.
"""
from alembic import op
import sqlalchemy as sa

revision = "a33_kiosk_devices"
down_revision = "a32_member_credits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS af_global.kiosk_devices (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id UUID NOT NULL REFERENCES af_global.organizations(id) ON DELETE CASCADE,
            device_token TEXT NOT NULL UNIQUE,
            -- sha256 hashes for fingerprint rebind. Never store raw values.
            ip_hash TEXT,
            user_agent_hash TEXT,
            label TEXT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            registered_by UUID REFERENCES af_global.users(id) ON DELETE SET NULL,
            registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen_at TIMESTAMPTZ,
            revoked_at TIMESTAMPTZ,
            revoked_by UUID REFERENCES af_global.users(id) ON DELETE SET NULL
        );
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_kiosk_devices_org_active
            ON af_global.kiosk_devices (organization_id, is_active)
            WHERE is_active = TRUE;
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_kiosk_devices_fingerprint
            ON af_global.kiosk_devices (organization_id, ip_hash, user_agent_hash)
            WHERE is_active = TRUE;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS af_global.kiosk_devices CASCADE;")
