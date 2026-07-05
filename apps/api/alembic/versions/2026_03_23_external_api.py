"""External API infrastructure — api_keys + global routing

Add af_global.api_key_routing table for cross-tenant key prefix lookup,
api_keys table to every existing tenant schema, and a PL/pgSQL function
af_global.add_api_keys_table() for provisioning new tenants.

Revision ID: a16_external_api
Revises: a14_account_cancel
Create Date: 2026-03-23
"""

revision = "a16_external_api"
down_revision = "a14_account_cancel"
branch_labels = None
depends_on = None


def upgrade():
    from alembic import op

    # ── Global: API key routing table ────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS af_global.api_key_routing (
            key_prefix TEXT PRIMARY KEY,
            org_slug   TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_api_key_routing_org_slug
            ON af_global.api_key_routing (org_slug);
    """)

    # ── Tenant: api_keys table for all existing tenant schemas ───────────
    op.execute("""
        DO $$
        DECLARE
            tenant_schema TEXT;
        BEGIN
            FOR tenant_schema IN
                SELECT schema_name FROM information_schema.schemata
                WHERE schema_name LIKE 'af_tenant_%'
            LOOP
                EXECUTE format('
                    CREATE TABLE IF NOT EXISTS %I.api_keys (
                        id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        name           TEXT NOT NULL,
                        key_hash       TEXT NOT NULL,
                        key_prefix     TEXT NOT NULL,
                        scopes         TEXT[] DEFAULT ''{}''::TEXT[],
                        rate_limit_rpm INTEGER DEFAULT 60,
                        is_active      BOOLEAN DEFAULT TRUE,
                        last_used_at   TIMESTAMPTZ,
                        expires_at     TIMESTAMPTZ,
                        created_by     UUID,
                        created_at     TIMESTAMPTZ DEFAULT NOW(),
                        revoked_at     TIMESTAMPTZ
                    )', tenant_schema);

                -- Unique index on key_hash (only active keys)
                EXECUTE format('
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_api_keys_hash_active
                    ON %I.api_keys (key_hash) WHERE is_active = TRUE
                ', tenant_schema);

                -- Index on key_prefix for fast lookup
                EXECUTE format('
                    CREATE INDEX IF NOT EXISTS idx_api_keys_prefix
                    ON %I.api_keys (key_prefix)
                ', tenant_schema);
            END LOOP;
        END $$;
    """)

    # ── PL/pgSQL function for new tenant provisioning ────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION af_global.add_api_keys_table(p_schema_name TEXT)
        RETURNS VOID
        LANGUAGE plpgsql
        AS $fn$
        BEGIN
            EXECUTE format('
                CREATE TABLE IF NOT EXISTS %I.api_keys (
                    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    name           TEXT NOT NULL,
                    key_hash       TEXT NOT NULL,
                    key_prefix     TEXT NOT NULL,
                    scopes         TEXT[] DEFAULT ''{}''::TEXT[],
                    rate_limit_rpm INTEGER DEFAULT 60,
                    is_active      BOOLEAN DEFAULT TRUE,
                    last_used_at   TIMESTAMPTZ,
                    expires_at     TIMESTAMPTZ,
                    created_by     UUID,
                    created_at     TIMESTAMPTZ DEFAULT NOW(),
                    revoked_at     TIMESTAMPTZ
                )', p_schema_name);

            EXECUTE format('
                CREATE UNIQUE INDEX IF NOT EXISTS idx_api_keys_hash_active
                ON %I.api_keys (key_hash) WHERE is_active = TRUE
            ', p_schema_name);

            EXECUTE format('
                CREATE INDEX IF NOT EXISTS idx_api_keys_prefix
                ON %I.api_keys (key_prefix)
            ', p_schema_name);
        END;
        $fn$;
    """)


def downgrade():
    from alembic import op

    # Drop provisioning function
    op.execute("DROP FUNCTION IF EXISTS af_global.add_api_keys_table(TEXT);")

    # Drop tenant api_keys tables
    op.execute("""
        DO $$
        DECLARE
            tenant_schema TEXT;
        BEGIN
            FOR tenant_schema IN
                SELECT schema_name FROM information_schema.schemata
                WHERE schema_name LIKE 'af_tenant_%'
            LOOP
                EXECUTE format('DROP TABLE IF EXISTS %I.api_keys CASCADE', tenant_schema);
            END LOOP;
        END $$;
    """)

    # Drop global routing table
    op.execute("DROP TABLE IF EXISTS af_global.api_key_routing CASCADE;")
