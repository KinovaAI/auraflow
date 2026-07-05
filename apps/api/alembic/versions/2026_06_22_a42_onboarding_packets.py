"""onboarding packets + documents (unified new-hire packet)

Revision ID: a42_onboarding_packets
Revises: a41_employer_profile
Create Date: 2026-06-22

One secure link per hire that surfaces every required new-hire document
(W-4, DE-4, I-9 §1, DLSE-NTE, DWC-7, paid-sick-leave + SB-294 notices, and
the CRD/EDD pamphlets) with per-document completion state. Standard CA/
federal forms are system-shipped templates that auto-fill from the tenant's
employer_profile + the employee's data — turnkey for any studio.

`onboarding_packets`   — the per-hire packet + signing token (replaces the
                         standalone W-4 token flow).
`onboarding_documents` — each document in a packet. kind 'form_fillable'
                         (employee fills + signs, may collect SSN →
                         ssn_encrypted) or 'acknowledgment' (employee
                         confirms receipt of a notice/pamphlet + signs).
                         signed_pdf BYTEA holds the rendered, signed PDF.
"""
revision = "a42_onboarding_packets"
down_revision = "a41_employer_profile"
branch_labels = None
depends_on = None


def upgrade():
    from alembic import op

    op.execute(r"""
    CREATE OR REPLACE FUNCTION af_global.add_onboarding_tables_to_schema(p_schema_name TEXT)
    RETURNS VOID
    LANGUAGE plpgsql
    AS $fn$
    BEGIN
        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.onboarding_packets (
                id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id                  UUID NOT NULL,
                application_id           UUID,
                first_name               VARCHAR(120),
                last_name                VARCHAR(120),
                email                    VARCHAR(255),
                signing_token            CHAR(64),
                signing_token_expires_at TIMESTAMPTZ,
                status                   VARCHAR(16) NOT NULL DEFAULT 'pending'
                                           CHECK (status IN ('pending','completed')),
                created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        $ddl$, p_schema_name);
        EXECUTE format($ddl$
            CREATE UNIQUE INDEX IF NOT EXISTS idx_onboarding_packet_token
                ON %I.onboarding_packets (signing_token) WHERE signing_token IS NOT NULL
        $ddl$, p_schema_name);
        EXECUTE format($ddl$
            CREATE INDEX IF NOT EXISTS idx_onboarding_packet_user
                ON %I.onboarding_packets (user_id)
        $ddl$, p_schema_name);

        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.onboarding_documents (
                id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                packet_id       UUID NOT NULL REFERENCES %I.onboarding_packets(id) ON DELETE CASCADE,
                user_id         UUID NOT NULL,
                doc_type        VARCHAR(40) NOT NULL,
                kind            VARCHAR(20) NOT NULL DEFAULT 'form_fillable'
                                  CHECK (kind IN ('form_fillable','acknowledgment')),
                title           VARCHAR(200) NOT NULL,
                sort_order      INTEGER NOT NULL DEFAULT 0,
                form_data       JSONB NOT NULL DEFAULT '{}',
                ssn_encrypted   BYTEA,
                status          VARCHAR(16) NOT NULL DEFAULT 'pending'
                                  CHECK (status IN ('pending','completed')),
                signature_text  VARCHAR(255),
                signed_at       TIMESTAMPTZ,
                signed_ip       VARCHAR(64),
                signed_pdf      BYTEA,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        $ddl$, p_schema_name, p_schema_name);
        EXECUTE format($ddl$
            CREATE INDEX IF NOT EXISTS idx_onboarding_docs_packet
                ON %I.onboarding_documents (packet_id, sort_order)
        $ddl$, p_schema_name);
        EXECUTE format($ddl$
            CREATE INDEX IF NOT EXISTS idx_onboarding_docs_user
                ON %I.onboarding_documents (user_id)
        $ddl$, p_schema_name);
    END;
    $fn$;
    """)

    op.execute(r"""
    DO $$
    DECLARE s TEXT;
    BEGIN
        FOR s IN SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'af_tenant_%'
        LOOP PERFORM af_global.add_onboarding_tables_to_schema(s); END LOOP;
    END $$;
    """)


def downgrade():
    from alembic import op
    op.execute(r"""
    DO $$
    DECLARE s TEXT;
    BEGIN
        FOR s IN SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'af_tenant_%'
        LOOP
            EXECUTE format($d$ DROP TABLE IF EXISTS %I.onboarding_documents CASCADE $d$, s);
            EXECUTE format($d$ DROP TABLE IF EXISTS %I.onboarding_packets CASCADE $d$, s);
        END LOOP;
    END $$;
    """)
    op.execute("DROP FUNCTION IF EXISTS af_global.add_onboarding_tables_to_schema(TEXT);")
