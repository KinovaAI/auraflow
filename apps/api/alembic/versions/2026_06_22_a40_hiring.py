"""hiring: job_applications, documents, events, employee_w4_forms

Revision ID: a40_hiring
Revises: a39_pos_checkout_index
Create Date: 2026-06-22

Applicant-tracking + onboarding system. Per-tenant tables, created via the
af_global.add_hiring_tables_to_schema() helper so they exist for BOTH every
existing tenant (looped here) AND every newly-provisioned tenant
(tenant_provisioning.py calls the same function) — same pattern as
add_api_keys_table / add_emr_tables_to_schema.

`job_applications`   — public application (api-key submit). No SSN.
`job_application_documents` — resume + supporting docs as BYTEA.
`job_application_events`    — status/note timeline.
`employee_w4_forms`  — post-hire digital W-4. ssn_encrypted BYTEA (pgcrypto),
                       tokenized e-sign, weasyprint signed_pdf BYTEA.
"""
revision = "a40_hiring"
down_revision = "a39_pos_checkout_index"
branch_labels = None
depends_on = None


def upgrade():
    from alembic import op

    # ── Provisioning helper (single source of truth for the DDL) ─────────────
    op.execute(r"""
    CREATE OR REPLACE FUNCTION af_global.add_hiring_tables_to_schema(p_schema_name TEXT)
    RETURNS VOID
    LANGUAGE plpgsql
    AS $fn$
    BEGIN
        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.job_applications (
                id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                first_name           VARCHAR(120) NOT NULL,
                last_name            VARCHAR(120) NOT NULL,
                email                VARCHAR(255) NOT NULL,
                phone                VARCHAR(40),
                address_line1        VARCHAR(255),
                address_line2        VARCHAR(255),
                city                 VARCHAR(120),
                state                VARCHAR(60),
                postal_code          VARCHAR(20),
                position_type        VARCHAR(30) NOT NULL DEFAULT 'instructor'
                                       CHECK (position_type IN ('instructor','front_desk','admin','other')),
                position_title       VARCHAR(160),
                employment_type      VARCHAR(20)
                                       CHECK (employment_type IS NULL OR employment_type IN ('full_time','part_time','contract')),
                availability         TEXT,
                earliest_start_date  DATE,
                desired_pay_text     VARCHAR(160),
                authorized_to_work   BOOLEAN NOT NULL DEFAULT FALSE,
                over_18              BOOLEAN NOT NULL DEFAULT FALSE,
                years_experience     INTEGER,
                experience_seniors   TEXT,
                experience_injuries  TEXT,
                experience_pain      TEXT,
                specialties          TEXT[] NOT NULL DEFAULT '{}',
                work_history         JSONB NOT NULL DEFAULT '[]',
                certifications       JSONB NOT NULL DEFAULT '[]',
                yoga_alliance_number VARCHAR(60),
                yoga_alliance_level  VARCHAR(40),
                cpr_first_aid        BOOLEAN NOT NULL DEFAULT FALSE,
                liability_insurance  BOOLEAN NOT NULL DEFAULT FALSE,
                "references"         JSONB NOT NULL DEFAULT '[]',
                cover_letter         TEXT,
                hear_about_us        VARCHAR(160),
                attestation          BOOLEAN NOT NULL DEFAULT FALSE,
                status               VARCHAR(20) NOT NULL DEFAULT 'new'
                                       CHECK (status IN ('new','reviewed','shortlisted','interviewed','offer','hired','rejected')),
                rating               SMALLINT CHECK (rating IS NULL OR (rating >= 0 AND rating <= 5)),
                assigned_reviewer_id UUID,
                reviewed_by          UUID,
                reviewed_at          TIMESTAMPTZ,
                rejection_reason     TEXT,
                hired_user_id        UUID,
                hired_studio_id      UUID,
                hired_role           VARCHAR(30),
                hired_at             TIMESTAMPTZ,
                created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        $ddl$, p_schema_name);

        EXECUTE format($ddl$
            CREATE INDEX IF NOT EXISTS idx_job_apps_status
                ON %I.job_applications (status, created_at DESC)
        $ddl$, p_schema_name);
        EXECUTE format($ddl$
            CREATE INDEX IF NOT EXISTS idx_job_apps_email
                ON %I.job_applications (lower(email))
        $ddl$, p_schema_name);

        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.job_application_documents (
                id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                application_id   UUID NOT NULL REFERENCES %I.job_applications(id) ON DELETE CASCADE,
                doc_type         VARCHAR(30) NOT NULL DEFAULT 'other'
                                   CHECK (doc_type IN ('resume','certification','insurance','yoga_alliance','other')),
                filename         VARCHAR(255) NOT NULL,
                content_type     VARCHAR(120) NOT NULL,
                file_data        BYTEA NOT NULL,
                size_bytes       INTEGER NOT NULL,
                uploaded_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        $ddl$, p_schema_name, p_schema_name);
        EXECUTE format($ddl$
            CREATE INDEX IF NOT EXISTS idx_job_app_docs_app
                ON %I.job_application_documents (application_id)
        $ddl$, p_schema_name);

        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.job_application_events (
                id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                application_id   UUID NOT NULL REFERENCES %I.job_applications(id) ON DELETE CASCADE,
                event_type       VARCHAR(30) NOT NULL
                                   CHECK (event_type IN ('created','status_changed','note','rated','document_uploaded','hired')),
                from_status      VARCHAR(20),
                to_status        VARCHAR(20),
                note             TEXT,
                actor_user_id    UUID,
                created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        $ddl$, p_schema_name, p_schema_name);
        EXECUTE format($ddl$
            CREATE INDEX IF NOT EXISTS idx_job_app_events_app
                ON %I.job_application_events (application_id, created_at)
        $ddl$, p_schema_name);

        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.employee_w4_forms (
                id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                application_id          UUID REFERENCES %I.job_applications(id) ON DELETE SET NULL,
                user_id                 UUID NOT NULL,
                first_name              VARCHAR(120) NOT NULL,
                middle_initial          VARCHAR(4),
                last_name               VARCHAR(120) NOT NULL,
                address_line1           VARCHAR(255),
                address_line2           VARCHAR(255),
                city                    VARCHAR(120),
                state                   VARCHAR(60),
                postal_code             VARCHAR(20),
                ssn_encrypted           BYTEA,
                filing_status           VARCHAR(24)
                                          CHECK (filing_status IS NULL OR filing_status IN ('single','married_jointly','head_of_household')),
                multiple_jobs           BOOLEAN NOT NULL DEFAULT FALSE,
                dependents_amount_cents INTEGER NOT NULL DEFAULT 0,
                other_income_cents      INTEGER NOT NULL DEFAULT 0,
                deductions_cents        INTEGER NOT NULL DEFAULT 0,
                extra_withholding_cents INTEGER NOT NULL DEFAULT 0,
                exempt                  BOOLEAN NOT NULL DEFAULT FALSE,
                signing_token           CHAR(64),
                signing_token_expires_at TIMESTAMPTZ,
                signature_text          VARCHAR(255),
                signed_at               TIMESTAMPTZ,
                signed_ip               VARCHAR(64),
                status                  VARCHAR(16) NOT NULL DEFAULT 'pending'
                                          CHECK (status IN ('pending','completed')),
                signed_pdf              BYTEA,
                created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        $ddl$, p_schema_name, p_schema_name);
        EXECUTE format($ddl$
            CREATE UNIQUE INDEX IF NOT EXISTS idx_w4_token
                ON %I.employee_w4_forms (signing_token)
                WHERE signing_token IS NOT NULL
        $ddl$, p_schema_name);
        EXECUTE format($ddl$
            CREATE INDEX IF NOT EXISTS idx_w4_user
                ON %I.employee_w4_forms (user_id)
        $ddl$, p_schema_name);
    END;
    $fn$;
    """)

    # ── Apply to every existing tenant schema ────────────────────────────────
    op.execute(r"""
    DO $$
    DECLARE
        s TEXT;
    BEGIN
        FOR s IN
            SELECT schema_name FROM information_schema.schemata
            WHERE schema_name LIKE 'af_tenant_%'
        LOOP
            PERFORM af_global.add_hiring_tables_to_schema(s);
        END LOOP;
    END $$;
    """)


def downgrade():
    from alembic import op

    op.execute(r"""
    DO $$
    DECLARE
        s TEXT;
    BEGIN
        FOR s IN
            SELECT schema_name FROM information_schema.schemata
            WHERE schema_name LIKE 'af_tenant_%'
        LOOP
            EXECUTE format($d$ DROP TABLE IF EXISTS %I.employee_w4_forms CASCADE $d$, s);
            EXECUTE format($d$ DROP TABLE IF EXISTS %I.job_application_events CASCADE $d$, s);
            EXECUTE format($d$ DROP TABLE IF EXISTS %I.job_application_documents CASCADE $d$, s);
            EXECUTE format($d$ DROP TABLE IF EXISTS %I.job_applications CASCADE $d$, s);
        END LOOP;
    END $$;
    """)
    op.execute("DROP FUNCTION IF EXISTS af_global.add_hiring_tables_to_schema(TEXT);")
