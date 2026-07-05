"""Merge all migration heads into single lineage

Revision ID: a13_merge_heads
Revises: a10_gdpr_cd01, a12_force_pw_reset, a9_sms01, liability_waivers_001
Create Date: 2026-03-16
"""
from alembic import op

revision = "a13_merge_heads"
down_revision = ("a10_gdpr_cd01", "a12_force_pw_reset", "a9_sms01", "liability_waivers_001")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
