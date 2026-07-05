"""Add modality column to class_sessions across every tenant schema

Revision ID: a27_class_modality
Revises: a26_birthday_derived
Create Date: 2026-04-28

Multi-tenant correctness: the `is_virtual` boolean alone can't represent
the three real class modalities — in-studio only, virtual only, and
hybrid (both). Different studios run different mixes. Without a clean
modality field, eligibility and Zoom-link delivery can't be gated
correctly per access_scope without ambiguity.

Adds a TEXT column `modality` with CHECK constraint enforcing one of
('in_studio', 'virtual', 'hybrid'), defaulting to 'in_studio'. Backfill
strategy is per-tenant policy:

  - Your Studio (af_tenant_demo): every existing
    is_virtual=True session is HYBRID by their actual operational
    pattern (members in-studio + on Zoom for the same class). Backfill
    is_virtual=True → 'hybrid', is_virtual=False → 'in_studio'.

  - All other tenants: assume the platform default — is_virtual=True →
    'virtual' (could be virtual-only or hybrid depending on studio
    operations; staff can edit per-class as needed). is_virtual=False →
    'in_studio'.

is_virtual stays as the "has Zoom side" flag — drives Zoom meeting
creation in scheduling_service. modality is the access semantics. The
two are aligned by create_session/update_session: setting modality to
in_studio sets is_virtual=False; virtual or hybrid sets is_virtual=True.
"""

revision = "a27_class_modality"
down_revision = "a26_birthday_derived"
branch_labels = None
depends_on = None


def upgrade():
    from alembic import op
    from sqlalchemy import text
    conn = op.get_bind()

    schemas = conn.execute(text(
        "SELECT schema_name FROM af_global.organizations "
        "WHERE schema_name LIKE 'af_tenant_%'"
    )).fetchall()

    for (schema,) in schemas:
        op.execute(f"""
            ALTER TABLE {schema}.class_sessions
            ADD COLUMN IF NOT EXISTS modality TEXT
                NOT NULL DEFAULT 'in_studio'
                CHECK (modality IN ('in_studio', 'virtual', 'hybrid'))
        """)

        # Per-tenant backfill: Your Studio ran every is_virtual=True as
        # hybrid. New tenants without explicit operational policy get
        # the platform default mapping (is_virtual=True → 'virtual').
        if schema == "af_tenant_demo":
            virtual_target = "hybrid"
        else:
            virtual_target = "virtual"

        op.execute(f"""
            UPDATE {schema}.class_sessions
               SET modality = CASE
                   WHEN is_virtual IS TRUE THEN '{virtual_target}'
                   ELSE 'in_studio'
               END
        """)

        op.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_class_sessions_modality
                ON {schema}.class_sessions (modality)
        """)


def downgrade():
    from alembic import op
    from sqlalchemy import text
    conn = op.get_bind()

    schemas = conn.execute(text(
        "SELECT schema_name FROM af_global.organizations "
        "WHERE schema_name LIKE 'af_tenant_%'"
    )).fetchall()

    for (schema,) in schemas:
        op.execute(f"DROP INDEX IF EXISTS {schema}.idx_class_sessions_modality")
        op.execute(f"ALTER TABLE {schema}.class_sessions DROP COLUMN IF EXISTS modality")
