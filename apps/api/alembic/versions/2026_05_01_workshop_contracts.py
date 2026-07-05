"""Add workshop_contracts table for e-signed guest instructor agreements

Revision ID: a29_workshop_contracts
Revises: a28_guest_instructors
Create Date: 2026-05-01

Stores prepared / sent / signed Guest Instructor Workshop Services
Agreements. Each contract attaches to one course (a workshop) and one
guest_instructors row. Signing happens via an unguessable token over a
public your-domain.com page; the instructor draws their signature
on an HTML5 canvas. SSN/EIN collected on the sign form is written to
guest_instructors.tax_id_encrypted (NOT stored on this table).

Studio acknowledgment is via typed-name electronic affixation per §18.7
of the contract — no studio drawn signature; auraflow stamps the studio
block as "/s/ Don Kolz, Owner — affixed by electronic preparation on
[date]" when the contract is prepared.
"""

revision = "a29_workshop_contracts"
down_revision = "a28_guest_instructors"
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
            CREATE TABLE IF NOT EXISTS {schema}.workshop_contracts (
                id                       UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                course_id                UUID NOT NULL REFERENCES {schema}.courses(id) ON DELETE CASCADE,
                guest_instructor_id      UUID NOT NULL REFERENCES {schema}.guest_instructors(id) ON DELETE RESTRICT,
                template_version         VARCHAR(50) NOT NULL,
                status                   VARCHAR(20) NOT NULL DEFAULT 'prepared',
                signing_token            CHAR(64) UNIQUE,
                signing_token_expires_at TIMESTAMPTZ NOT NULL,
                effective_date           DATE NOT NULL,
                prefilled_data           JSONB NOT NULL,
                instructor_data          JSONB,
                signature_image          BYTEA,
                signed_at                TIMESTAMPTZ,
                signed_ip                TEXT,
                signed_user_agent        TEXT,
                signed_pdf               BYTEA,
                email_sent_at            TIMESTAMPTZ,
                first_viewed_at          TIMESTAMPTZ,
                last_viewed_at           TIMESTAMPTZ,
                view_count               INT NOT NULL DEFAULT 0,
                reminder_sent_at         TIMESTAMPTZ,
                voided_at                TIMESTAMPTZ,
                voided_by                UUID,
                void_reason              TEXT,
                created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT workshop_contracts_status_chk
                    CHECK (status IN ('prepared','sent','viewed','signed','voided'))
            )
        """)
        op.execute(f"""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_workshop_contracts_active_per_course
                ON {schema}.workshop_contracts (course_id)
                WHERE status != 'voided'
        """)
        op.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_workshop_contracts_status
                ON {schema}.workshop_contracts (status)
                WHERE status IN ('prepared','sent','viewed')
        """)
        op.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_workshop_contracts_token
                ON {schema}.workshop_contracts (signing_token)
                WHERE signing_token IS NOT NULL
        """)
        op.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_workshop_contracts_reminder
                ON {schema}.workshop_contracts (email_sent_at, reminder_sent_at)
                WHERE status IN ('sent','viewed') AND reminder_sent_at IS NULL
        """)
        op.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_workshop_contracts_guest
                ON {schema}.workshop_contracts (guest_instructor_id, signed_at DESC NULLS LAST)
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
        op.execute(f"DROP TABLE IF EXISTS {schema}.workshop_contracts CASCADE")
