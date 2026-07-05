"""Phase 4C — Expand POS payment methods

Adds stripe, paypal, apple_pay, google_pay, venmo, check, bank_transfer
to the pos_transactions.payment_method CHECK constraint.

Revision ID: a4c_pay01
Revises: a3h_ai01
"""
from alembic import op
import sqlalchemy as sa


revision = "a4c_pay01"
down_revision = "a3h_ai01"
branch_labels = None
depends_on = None

NEW_METHODS = "('cash', 'card', 'comp', 'stripe', 'paypal', 'apple_pay', 'google_pay', 'venmo', 'check', 'bank_transfer')"
OLD_METHODS = "('cash', 'card', 'comp')"


def _tenant_schemas(connection) -> list[str]:
    rows = connection.execute(
        sa.text("SELECT schema_name FROM af_global.organizations")
    ).fetchall()
    return [r[0] for r in rows]


def upgrade() -> None:
    conn = op.get_bind()

    for schema in _tenant_schemas(conn):
        # Drop both old-style (from init.sql) and named constraint
        conn.execute(sa.text(
            f'ALTER TABLE "{schema}".pos_transactions '
            f'DROP CONSTRAINT IF EXISTS pos_transactions_payment_method_check'
        ))
        conn.execute(sa.text(
            f'ALTER TABLE "{schema}".pos_transactions '
            f'DROP CONSTRAINT IF EXISTS pos_txn_payment_method_check'
        ))
        conn.execute(sa.text(
            f'ALTER TABLE "{schema}".pos_transactions '
            f'ADD CONSTRAINT pos_txn_payment_method_check '
            f'CHECK (payment_method IN {NEW_METHODS})'
        ))


def downgrade() -> None:
    conn = op.get_bind()

    for schema in _tenant_schemas(conn):
        conn.execute(sa.text(
            f'ALTER TABLE "{schema}".pos_transactions '
            f'DROP CONSTRAINT IF EXISTS pos_txn_payment_method_check'
        ))
        conn.execute(sa.text(
            f'ALTER TABLE "{schema}".pos_transactions '
            f'ADD CONSTRAINT pos_txn_payment_method_check '
            f'CHECK (payment_method IN {OLD_METHODS})'
        ))
