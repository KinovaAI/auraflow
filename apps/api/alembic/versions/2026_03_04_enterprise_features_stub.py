"""Enterprise features — chain-integrity stub

The original enterprise_features migration file was malformed (no
`revision = ` declaration, no upgrade/downgrade — just SQL constants).
The schema (api_keys table, webhook_configs, webhook_deliveries, etc.)
was applied to existing tenants via init.sql + historical manual SQL;
new tenants get it from init.sql.

At least one well-formed migration declares
`down_revision = "enterprise_features_001"`, so this stub preserves chain
integrity. It's a root (no parent) — alembic doesn't need to walk back
further. Empty upgrade/downgrade.

The original file lives at `alembic/legacy_pre_alembic/2026_03_04_enterprise_features.py`
for reference.

Revision ID: enterprise_features_001
Revises: (none — root)
Create Date: 2026-03-04
"""

revision = "enterprise_features_001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op. Schema applied via init.sql + historical manual SQL."""
    pass


def downgrade() -> None:
    """No-op."""
    pass
