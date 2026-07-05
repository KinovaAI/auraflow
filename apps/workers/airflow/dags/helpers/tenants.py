"""AuraFlow Airflow — Tenant Helpers

Fetch active tenants from the global organizations table.
"""
from helpers.db import get_global_conn, fetch_all


def get_active_tenants() -> list[dict]:
    """Return all active/trial tenant orgs with their metadata."""
    with get_global_conn() as conn:
        return fetch_all(
            conn,
            """
            SELECT id, slug, name, schema_name, stripe_account_id,
                   timezone, currency
            FROM organizations
            WHERE status IN ('active', 'trial')
            ORDER BY slug
            """,
        )


def get_tenants_with_stripe() -> list[dict]:
    """Return active tenants that have a Stripe Connect account configured."""
    with get_global_conn() as conn:
        return fetch_all(
            conn,
            """
            SELECT id, slug, name, schema_name, stripe_account_id,
                   timezone, currency
            FROM organizations
            WHERE status IN ('active', 'trial')
              AND stripe_account_id IS NOT NULL
              AND stripe_account_id != ''
            ORDER BY slug
            """,
        )


def get_owner_email(org_id: str) -> str | None:
    """Look up the owner's email for a given organization."""
    with get_global_conn() as conn:
        row = fetch_all(
            conn,
            """
            SELECT u.email
            FROM users u
            JOIN org_memberships om ON u.id = om.user_id
            WHERE om.organization_id = %s AND om.role = 'owner'
            LIMIT 1
            """,
            (org_id,),
        )
        return row[0]["email"] if row else None
