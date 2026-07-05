"""AuraFlow Airflow — Schema Migration Helpers

Creates payout-related tables in tenant schemas.
"""
import logging

from helpers.db import get_tenant_conn, execute

logger = logging.getLogger("auraflow.airflow.migration")

PAYOUT_SUMMARIES_DDL = """
CREATE TABLE IF NOT EXISTS payout_summaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_date DATE NOT NULL,
    period VARCHAR(10) NOT NULL,
    gross_revenue_cents INTEGER DEFAULT 0,
    fee_cents INTEGER DEFAULT 0,
    net_revenue_cents INTEGER DEFAULT 0,
    refund_cents INTEGER DEFAULT 0,
    transaction_count INTEGER DEFAULT 0,
    drop_in_count INTEGER DEFAULT 0,
    membership_count INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(report_date, period)
);
"""

STRIPE_PAYOUTS_DDL = """
CREATE TABLE IF NOT EXISTS stripe_payouts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stripe_payout_id VARCHAR(100) UNIQUE NOT NULL,
    amount_cents INTEGER NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',
    status VARCHAR(20),
    arrival_date TIMESTAMPTZ,
    description TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
"""


def create_payout_tables(schema_name: str):
    """Create payout_summaries and stripe_payouts tables in a tenant schema."""
    with get_tenant_conn(schema_name) as conn:
        execute(conn, PAYOUT_SUMMARIES_DDL)
        execute(conn, STRIPE_PAYOUTS_DDL)
        logger.info("Payout tables created in %s", schema_name)
