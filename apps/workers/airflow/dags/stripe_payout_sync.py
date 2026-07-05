"""AuraFlow — Stripe Payout Sync DAG

Runs every 6 hours. For each tenant with a Stripe Connect account,
fetches recent payouts from Stripe and upserts them into the local
stripe_payouts table.
"""
import os
from datetime import datetime, timedelta

from airflow.decorators import dag, task

from helpers.db import get_tenant_conn, execute, fetch_one
from helpers.tenants import get_tenants_with_stripe

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")


@dag(
    dag_id="stripe_payout_sync",
    schedule="0 */6 * * *",
    start_date=datetime(2026, 3, 1),
    catchup=False,
    tags=["payments", "stripe"],
    default_args={
        "owner": "auraflow",
        "retries": 3,
        "retry_delay": timedelta(minutes=10),
    },
)
def stripe_payout_sync():

    @task()
    def get_stripe_tenants() -> list[dict]:
        tenants = get_tenants_with_stripe()
        for t in tenants:
            t["id"] = str(t["id"])
        return tenants

    @task()
    def sync_payouts(tenant: dict) -> dict:
        if not STRIPE_SECRET_KEY:
            return {"tenant": tenant["slug"], "synced": 0, "error": "No Stripe key"}

        import stripe
        stripe.api_key = STRIPE_SECRET_KEY

        schema = tenant["schema_name"]
        stripe_account_id = tenant["stripe_account_id"]
        synced = 0

        try:
            payouts = stripe.Payout.list(
                limit=25,
                stripe_account=stripe_account_id,
            )
        except stripe.StripeError as e:
            return {"tenant": tenant["slug"], "synced": 0, "error": str(e)}

        for payout in payouts.data:
            amount_cents = payout.amount
            currency = payout.currency.upper()
            status = payout.status
            arrival_ts = datetime.utcfromtimestamp(payout.arrival_date) if payout.arrival_date else None
            description = payout.description or ""

            with get_tenant_conn(schema) as conn:
                existing = fetch_one(
                    conn,
                    "SELECT id FROM stripe_payouts WHERE stripe_payout_id = %s",
                    (payout.id,),
                )

                if existing:
                    execute(
                        conn,
                        """
                        UPDATE stripe_payouts
                        SET status = %s, arrival_date = %s, updated_at = now()
                        WHERE stripe_payout_id = %s
                        """,
                        (status, arrival_ts, payout.id),
                    )
                else:
                    execute(
                        conn,
                        """
                        INSERT INTO stripe_payouts
                            (stripe_payout_id, amount_cents, currency, status,
                             arrival_date, description)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (payout.id, amount_cents, currency, status, arrival_ts, description),
                    )
                synced += 1

        return {"tenant": tenant["slug"], "synced": synced}

    tenants = get_stripe_tenants()
    sync_payouts.expand(tenant=tenants)


stripe_payout_sync()
