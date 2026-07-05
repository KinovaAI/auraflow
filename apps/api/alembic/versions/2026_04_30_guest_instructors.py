"""Add guest_instructors table + courses.guest_instructor_id

Revision ID: a28_guest_instructors
Revises: a27_class_modality
Create Date: 2026-04-30

Guest instructors are 1099 contractors who teach WORKSHOPS only.
California labor law prohibits 1099 contractors from teaching regular
classes, so the schema enforces that with a CHECK constraint:
guest_instructor_id may only be set on courses with type='workshop'.

Per Don's rule the guest_instructors table is fully separate from
the staff `instructors` table — guests must never appear in staff
pickers, payroll runs, or any view that joins through `instructors`.
A returning guest re-uses their existing row so tax history stays
attached.

Pay split lives on the guest record as
`revenue_share_percent_to_guest`, default 60% to guest / 40% to
studio. The 1099 report applies the guest's current percent against
each workshop's revenue.

tax_id_encrypted is Fernet-encrypted at rest using the same
HEALTH_DATA_ENCRYPTION_KEY that protects PHI columns. Plaintext is
never stored.
"""

revision = "a28_guest_instructors"
down_revision = "a27_class_modality"
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
            CREATE TABLE IF NOT EXISTS {schema}.guest_instructors (
                id                              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                studio_id                       UUID,
                name                            VARCHAR(255) NOT NULL,
                bio                             TEXT,
                photo_url                       TEXT,
                email                           VARCHAR(255),
                phone                           VARCHAR(50),
                address_line1                   VARCHAR(255),
                city                            VARCHAR(100),
                state                           VARCHAR(50),
                postal_code                     VARCHAR(20),
                tax_id_encrypted                BYTEA,
                revenue_share_percent_to_guest  INT NOT NULL DEFAULT 60
                    CHECK (revenue_share_percent_to_guest BETWEEN 0 AND 100),
                notes                           TEXT,
                is_active                       BOOLEAN NOT NULL DEFAULT TRUE,
                created_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        op.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_guest_instructors_studio_active
                ON {schema}.guest_instructors (studio_id, is_active)
        """)
        op.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_guest_instructors_name
                ON {schema}.guest_instructors (LOWER(name))
        """)

        # Add guest_instructor_id to courses (nullable). Workshops can
        # have either a staff instructor_id OR a guest_instructor_id;
        # non-workshop course types CANNOT have guest_instructor_id.
        op.execute(f"""
            ALTER TABLE {schema}.courses
                ADD COLUMN IF NOT EXISTS guest_instructor_id UUID
                REFERENCES {schema}.guest_instructors(id) ON DELETE SET NULL
        """)
        op.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_courses_guest_instructor
                ON {schema}.courses (guest_instructor_id)
                WHERE guest_instructor_id IS NOT NULL
        """)

        # Hard CA-labor-law gate: guest_instructor_id is forbidden on
        # any non-workshop course type. There's no admin override.
        op.execute(f"""
            ALTER TABLE {schema}.courses
                DROP CONSTRAINT IF EXISTS chk_courses_guest_only_for_workshops
        """)
        op.execute(f"""
            ALTER TABLE {schema}.courses
                ADD CONSTRAINT chk_courses_guest_only_for_workshops
                CHECK (
                    guest_instructor_id IS NULL
                    OR type = 'workshop'
                )
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
        op.execute(f"""
            ALTER TABLE {schema}.courses
                DROP CONSTRAINT IF EXISTS chk_courses_guest_only_for_workshops
        """)
        op.execute(f"DROP INDEX IF EXISTS {schema}.idx_courses_guest_instructor")
        op.execute(f"""
            ALTER TABLE {schema}.courses
                DROP COLUMN IF EXISTS guest_instructor_id
        """)
        op.execute(f"DROP INDEX IF EXISTS {schema}.idx_guest_instructors_name")
        op.execute(f"DROP INDEX IF EXISTS {schema}.idx_guest_instructors_studio_active")
        op.execute(f"DROP TABLE IF EXISTS {schema}.guest_instructors")
