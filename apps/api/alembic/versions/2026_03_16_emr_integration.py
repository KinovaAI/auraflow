"""EMR Integration — schema + org columns

Add EMR connection columns to af_global.organizations and
EMR mapping/logging tables to the tenant schema provisioning.

Revision ID: a14_emr_integration
Revises: a13_merge_heads
Create Date: 2026-03-16
"""

revision = "a14_emr_integration"
down_revision = "a13_merge_heads"
branch_labels = None
depends_on = None


def upgrade():
    from alembic import op

    # ── Global: EMR columns on organizations ──────────────────────────────
    op.execute("""
        ALTER TABLE af_global.organizations
            ADD COLUMN IF NOT EXISTS emr_protocol VARCHAR(10),
            ADD COLUMN IF NOT EXISTS emr_base_url TEXT,
            ADD COLUMN IF NOT EXISTS emr_client_id_encrypted BYTEA,
            ADD COLUMN IF NOT EXISTS emr_client_secret_encrypted BYTEA,
            ADD COLUMN IF NOT EXISTS emr_webhook_secret VARCHAR(128),
            ADD COLUMN IF NOT EXISTS emr_hl7_host TEXT,
            ADD COLUMN IF NOT EXISTS emr_hl7_port INTEGER,
            ADD COLUMN IF NOT EXISTS emr_connected_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS emr_sync_enabled BOOLEAN DEFAULT FALSE;
    """)

    # ── Tenant: EMR mapping/logging tables (apply to all existing tenants) ─
    op.execute("""
        DO $$
        DECLARE
            tenant_schema TEXT;
        BEGIN
            FOR tenant_schema IN
                SELECT schema_name FROM information_schema.schemata
                WHERE schema_name LIKE 'af_tenant_%'
            LOOP
                -- Patient mapping table
                EXECUTE format('
                    CREATE TABLE IF NOT EXISTS %I.emr_patient_map (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        member_id UUID NOT NULL,
                        emr_patient_id VARCHAR(255) NOT NULL,
                        emr_system VARCHAR(50) NOT NULL,
                        last_synced_at TIMESTAMPTZ,
                        sync_direction VARCHAR(10) NOT NULL,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    )', tenant_schema);

                -- Unique constraints (idempotent)
                EXECUTE format('
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_emr_patient_map_member
                    ON %I.emr_patient_map (member_id)', tenant_schema);

                EXECUTE format('
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_emr_patient_map_emr
                    ON %I.emr_patient_map (emr_patient_id, emr_system)', tenant_schema);

                -- Encounter log table
                EXECUTE format('
                    CREATE TABLE IF NOT EXISTS %I.emr_encounter_log (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        booking_id UUID NOT NULL,
                        member_id UUID NOT NULL,
                        emr_encounter_id VARCHAR(255),
                        encounter_type VARCHAR(50) NOT NULL,
                        class_title VARCHAR(255),
                        instructor_name VARCHAR(255),
                        session_start TIMESTAMPTZ,
                        session_end TIMESTAMPTZ,
                        status VARCHAR(20) DEFAULT ''pending'',
                        error_message TEXT,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    )', tenant_schema);

                EXECUTE format('
                    CREATE INDEX IF NOT EXISTS idx_emr_encounter_log_booking
                    ON %I.emr_encounter_log (booking_id)', tenant_schema);

                EXECUTE format('
                    CREATE INDEX IF NOT EXISTS idx_emr_encounter_log_status
                    ON %I.emr_encounter_log (status) WHERE status = ''failed''', tenant_schema);

                -- Sync audit log table
                EXECUTE format('
                    CREATE TABLE IF NOT EXISTS %I.emr_sync_log (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        direction VARCHAR(10) NOT NULL,
                        resource_type VARCHAR(50) NOT NULL,
                        operation VARCHAR(20) NOT NULL,
                        emr_resource_id VARCHAR(255),
                        auraflow_resource_id UUID,
                        status VARCHAR(20) NOT NULL,
                        error_message TEXT,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    )', tenant_schema);

                EXECUTE format('
                    CREATE INDEX IF NOT EXISTS idx_emr_sync_log_created
                    ON %I.emr_sync_log (created_at DESC)', tenant_schema);
            END LOOP;
        END $$;
    """)


def downgrade():
    from alembic import op

    # Drop tenant tables
    op.execute("""
        DO $$
        DECLARE
            tenant_schema TEXT;
        BEGIN
            FOR tenant_schema IN
                SELECT schema_name FROM information_schema.schemata
                WHERE schema_name LIKE 'af_tenant_%'
            LOOP
                EXECUTE format('DROP TABLE IF EXISTS %I.emr_sync_log', tenant_schema);
                EXECUTE format('DROP TABLE IF EXISTS %I.emr_encounter_log', tenant_schema);
                EXECUTE format('DROP TABLE IF EXISTS %I.emr_patient_map', tenant_schema);
            END LOOP;
        END $$;
    """)

    # Drop global columns
    op.execute("""
        ALTER TABLE af_global.organizations
            DROP COLUMN IF EXISTS emr_protocol,
            DROP COLUMN IF EXISTS emr_base_url,
            DROP COLUMN IF EXISTS emr_client_id_encrypted,
            DROP COLUMN IF EXISTS emr_client_secret_encrypted,
            DROP COLUMN IF EXISTS emr_webhook_secret,
            DROP COLUMN IF EXISTS emr_hl7_host,
            DROP COLUMN IF EXISTS emr_hl7_port,
            DROP COLUMN IF EXISTS emr_connected_at,
            DROP COLUMN IF EXISTS emr_sync_enabled;
    """)
