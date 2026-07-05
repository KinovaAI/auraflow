"""a39_pos_checkout_index — O(1) checkout_id → schema lookup

Revision ID: a39_pos_checkout_index
Revises: a38_square_pos
Create Date: 2026-06-07

The /pos/deeplink-return endpoint must find the tenant schema that owns
a checkout_id WITHOUT a JWT (the callback is public — Square POS can't
authenticate). The original implementation iterated every active org
and tried fetching the row in each schema — O(N) per callback.

With this index, the callback does one global lookup to map
checkout_id → schema_name, then targets exactly that schema. Stays
correct under load and as N grows.

The index is populated on insert into `pos_terminal_checkouts` (by the
endpoint that inserts the row — see payments.py /pos/charge and
/pos/deeplink-charge). Rows are auto-cleaned when their corresponding
pos_terminal_checkouts row expires (handled by the same Celery sweep
task that runs every 5 min).
"""
from alembic import op

revision = "a39_pos_checkout_index"
down_revision = "a38_square_pos"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE IF NOT EXISTS af_global.pos_checkout_index (
        checkout_id   UUID PRIMARY KEY,
        schema_name   TEXT NOT NULL,
        created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        expires_at    TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '15 minutes')
    );
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS pos_checkout_index_expires_at_idx
        ON af_global.pos_checkout_index (expires_at);
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS af_global.pos_checkout_index;")
