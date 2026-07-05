"""AuraFlow — Setup Payout Tables DAG

One-time DAG that creates payout_summaries and stripe_payouts tables
in all active tenant schemas.
"""
from datetime import datetime

from airflow.decorators import dag, task

from helpers.tenants import get_active_tenants
from helpers.migration import create_payout_tables


@dag(
    dag_id="setup_payout_tables",
    schedule="@once",
    start_date=datetime(2026, 3, 1),
    catchup=False,
    tags=["migration", "payments"],
    default_args={"owner": "auraflow"},
)
def setup_payout_tables():

    @task()
    def get_tenants() -> list[dict]:
        tenants = get_active_tenants()
        for t in tenants:
            t["id"] = str(t["id"])
        return tenants

    @task()
    def create_tables(tenant: dict):
        create_payout_tables(tenant["schema_name"])
        return f"Created tables in {tenant['schema_name']}"

    tenants = get_tenants()
    create_tables.expand(tenant=tenants)


setup_payout_tables()
