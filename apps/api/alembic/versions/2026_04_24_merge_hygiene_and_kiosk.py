"""Merge a19_schema_hygiene + a22_kiosk_pin heads

Revision ID: a23_merge_heads
Revises: a19_schema_hygiene, a22_kiosk_pin
Create Date: 2026-04-24

Pure merge commit — no schema changes. The schema_hygiene branch
(a18_ads_tokens -> a19_schema_hygiene) and the main chain
(a18_ads_tokens -> a19_merge_emr_main -> … -> a22_kiosk_pin) diverged from
a shared parent; this commit rejoins them so `alembic upgrade head` works
without specifying a branch.
"""

revision = "a23_merge_heads"
down_revision = ("a19_schema_hygiene", "a22_kiosk_pin")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
