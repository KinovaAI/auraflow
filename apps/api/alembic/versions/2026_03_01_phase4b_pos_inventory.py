"""Phase 4B — POS & Inventory: products, inventory, POS transactions

Adds products, inventory, inventory_transactions, pos_transactions,
and pos_line_items tables to each tenant schema.

Revision ID: a4b_pos01
Revises: a2tc01
"""
from alembic import op
import sqlalchemy as sa


revision = "a4b_pos01"
down_revision = "a2tc01"
branch_labels = None
depends_on = None


def _tenant_schemas(connection) -> list[str]:
    """Return all tenant schema names."""
    rows = connection.execute(
        sa.text("SELECT schema_name FROM af_global.organizations")
    ).fetchall()
    return [r[0] for r in rows]


def upgrade() -> None:
    conn = op.get_bind()

    for schema in _tenant_schemas(conn):
        # ── products ────────────────────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".products (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                studio_id       UUID,
                name            VARCHAR(255) NOT NULL,
                description     TEXT,
                sku             VARCHAR(100),
                price_cents     INTEGER NOT NULL DEFAULT 0,
                cost_cents      INTEGER NOT NULL DEFAULT 0,
                category        VARCHAR(50) NOT NULL DEFAULT 'retail',
                tax_rate        NUMERIC(5,4) NOT NULL DEFAULT 0.0000,
                image_url       TEXT,
                active          BOOLEAN NOT NULL DEFAULT TRUE,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW(),
                CONSTRAINT products_category_check
                    CHECK (category IN ('retail', 'beverages', 'rental', 'merchandise')),
                CONSTRAINT products_price_nonneg CHECK (price_cents >= 0),
                CONSTRAINT products_cost_nonneg CHECK (cost_cents >= 0),
                CONSTRAINT products_tax_rate_check CHECK (tax_rate >= 0 AND tax_rate <= 1)
            )
        """))
        conn.execute(sa.text(f"""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_products_sku
            ON "{schema}".products (sku) WHERE sku IS NOT NULL AND active = TRUE
        """))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_products_category
            ON "{schema}".products (category) WHERE active = TRUE
        """))

        # ── inventory ───────────────────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".inventory (
                id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                product_id        UUID NOT NULL REFERENCES "{schema}".products(id) ON DELETE CASCADE,
                quantity_on_hand  INTEGER NOT NULL DEFAULT 0,
                reorder_point     INTEGER NOT NULL DEFAULT 5,
                reorder_quantity  INTEGER NOT NULL DEFAULT 20,
                last_counted_at   TIMESTAMPTZ,
                created_at        TIMESTAMPTZ DEFAULT NOW(),
                updated_at        TIMESTAMPTZ DEFAULT NOW(),
                CONSTRAINT inventory_product_unique UNIQUE (product_id),
                CONSTRAINT inventory_qty_nonneg CHECK (quantity_on_hand >= 0)
            )
        """))

        # ── inventory_transactions ──────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".inventory_transactions (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                product_id      UUID NOT NULL REFERENCES "{schema}".products(id) ON DELETE CASCADE,
                quantity_change  INTEGER NOT NULL,
                reason          VARCHAR(50) NOT NULL,
                reference_id    UUID,
                notes           TEXT,
                created_by      UUID,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                CONSTRAINT inv_txn_reason_check
                    CHECK (reason IN ('sale', 'restock', 'adjustment', 'shrinkage', 'opening_count'))
            )
        """))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_inv_txn_product_date
            ON "{schema}".inventory_transactions (product_id, created_at DESC)
        """))

        # ── pos_transactions ────────────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".pos_transactions (
                id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                member_id         UUID,
                subtotal_cents    INTEGER NOT NULL DEFAULT 0,
                tax_cents         INTEGER NOT NULL DEFAULT 0,
                total_cents       INTEGER NOT NULL DEFAULT 0,
                payment_method    VARCHAR(20) NOT NULL DEFAULT 'cash',
                stripe_payment_id VARCHAR(255),
                status            VARCHAR(20) NOT NULL DEFAULT 'completed',
                notes             TEXT,
                created_by        UUID,
                created_at        TIMESTAMPTZ DEFAULT NOW(),
                updated_at        TIMESTAMPTZ DEFAULT NOW(),
                CONSTRAINT pos_txn_payment_method_check
                    CHECK (payment_method IN ('cash', 'card', 'comp')),
                CONSTRAINT pos_txn_status_check
                    CHECK (status IN ('pending', 'completed', 'refunded', 'voided')),
                CONSTRAINT pos_txn_total_nonneg CHECK (total_cents >= 0)
            )
        """))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_pos_txn_created
            ON "{schema}".pos_transactions (created_at DESC)
        """))

        # ── pos_line_items ──────────────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".pos_line_items (
                id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                transaction_id  UUID NOT NULL REFERENCES "{schema}".pos_transactions(id) ON DELETE CASCADE,
                product_id      UUID NOT NULL REFERENCES "{schema}".products(id),
                quantity        INTEGER NOT NULL DEFAULT 1,
                unit_price_cents INTEGER NOT NULL,
                tax_cents       INTEGER NOT NULL DEFAULT 0,
                total_cents     INTEGER NOT NULL,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                CONSTRAINT pos_line_qty_positive CHECK (quantity > 0),
                CONSTRAINT pos_line_price_nonneg CHECK (unit_price_cents >= 0)
            )
        """))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_pos_line_txn
            ON "{schema}".pos_line_items (transaction_id)
        """))


def downgrade() -> None:
    conn = op.get_bind()

    for schema in _tenant_schemas(conn):
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{schema}".pos_line_items CASCADE'))
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{schema}".pos_transactions CASCADE'))
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{schema}".inventory_transactions CASCADE'))
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{schema}".inventory CASCADE'))
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{schema}".products CASCADE'))
