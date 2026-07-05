"""Merge a14_emr_integration into the main chain — bring alembic to a single head

The EMR integration migration (a14_emr_integration) was applied to the DB
historically (its columns are present on af_global.organizations) but
alembic_version was never advanced past a13_merge_heads to include it.
Subsequent migrations chained from a13_merge_heads, leaving
a14_emr_integration as a dangling head.

This merge revision has both prior heads as parents, converging the
chain so `alembic upgrade head` works again. Empty upgrade/downgrade —
no DB state change. After deploy, run `alembic stamp a19_merge_emr_main`
once to advance alembic_version from a18_ads_tokens to a19_merge_emr_main.

Revision ID: a19_merge_emr_main
Revises: a14_emr_integration, a18_ads_tokens
Create Date: 2026-04-18
"""

revision = "a19_merge_emr_main"
down_revision = ("a14_emr_integration", "a18_ads_tokens")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op. Both parent heads' SQL was already applied; this only converges
    the alembic chain."""
    pass


def downgrade() -> None:
    """No-op."""
    pass
