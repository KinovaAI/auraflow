"""Scheduled accounting sync for the Accounting module.

Iterates every active/trial tenant and runs the full books-refresh pass:
  1. Mercury bank auto-import  → acct_transactions (income + all expenses, deduped)
  2. Stripe/Square payout sync → acct_payouts / acct_payout_items
  3. Reconciliation           → matches each payout to its bank deposit so
                                AuraFlow ties out to the bank statement.

Tenants without a stored Mercury key no-op cheaply (steps 2-3 still run so
payout↔bank matching stays current). Read-only against Mercury/Stripe/Square;
only writes the tenant's own acct_* ledger.

Mirrors the multi-tenant worker pattern in recurring_membership_renewals.py.
"""
import asyncio

from app.workers.celery_app import app
from app.core.logging import logger
from app.db.session import get_global_db, get_tenant_db
from app.core.tenant_context import set_tenant_context_from_schema, clear_tenant_context
from app.services.accounting import (
    income_sync, mercury_service, payout_service, reconciliation, categorize, fees,
    draws,
)


async def _sync_tenant(schema: str, org_id: str) -> dict:
    await set_tenant_context_from_schema(schema)
    try:
        async with get_tenant_db(schema_override=schema) as db:
            # 1. Post every AuraFlow sale into the books (POS + memberships + …).
            try:
                income = await income_sync.sync_income(db)
            except Exception as e:  # noqa: BLE001
                income = {"error": str(e)}
            # 1b. Real processor fees (Square + Stripe) → Commissions & Fees.
            try:
                fee = await fees.sync_fees(db, org_id)
            except Exception as e:  # noqa: BLE001
                fee = {"error": str(e)}
            # 2. Mercury bank import (deposits + all expenses).
            bank = await mercury_service.sync_tenant(db)
            # 2b. Auto-categorize: instructor payouts → payroll, common vendors.
            try:
                cats = await categorize.categorize_bank(db)
            except Exception as e:  # noqa: BLE001
                cats = {"error": str(e)}
            # 2c. Owner draw schedule: fixed monthly draw → distribution, rest wages.
            try:
                dr = await draws.apply_draws(db)
            except Exception as e:  # noqa: BLE001
                dr = {"error": str(e)}
            # 3. Stripe/Square payout tracking.
            try:
                payouts = await payout_service.sync_payouts(db, org_id)
            except Exception as e:  # noqa: BLE001
                payouts = {"error": str(e)}
            # 4. Reconcile: settle payouts↔deposits, post fees, tie out.
            try:
                recon = await reconciliation.reconcile(db)
            except Exception as e:  # noqa: BLE001
                recon = {"error": str(e)}
            return {"income": income, "fees": fee, "bank": bank, "categorize": cats,
                    "draws": dr, "payouts": payouts, "reconciliation": recon}
    finally:
        clear_tenant_context()


async def _sync_all() -> dict:
    async with get_global_db() as gdb:
        orgs = await gdb.fetch(
            "SELECT id, schema_name, name FROM af_global.organizations "
            "WHERE status IN ('active', 'trial')"
        )
    total_imported = 0
    total_matched = 0
    by_tenant: dict[str, dict] = {}
    for org in orgs:
        schema = org["schema_name"]
        try:
            res = await _sync_tenant(schema, str(org["id"]))
        except Exception as e:  # noqa: BLE001
            res = {"error": str(e)}
        bank = res.get("bank", {}) if isinstance(res, dict) else {}
        recon = res.get("reconciliation", {}) if isinstance(res, dict) else {}
        # skip a fully-idle tenant (no Mercury key AND nothing reconciled) from noise
        no_key = bank.get("error") == "no_mercury_key"
        if no_key and not recon.get("newly_matched"):
            continue
        by_tenant[schema] = res
        total_imported += bank.get("imported", 0)
        total_matched += recon.get("newly_matched", 0) if isinstance(recon, dict) else 0
    return {
        "total_imported": total_imported,
        "total_reconciled": total_matched,
        "by_tenant": by_tenant,
    }


@app.task(name="app.workers.tasks.accounting_bank_sync.run_bank_sync")
def run_bank_sync():
    loop = asyncio.new_event_loop()
    try:
        summary = loop.run_until_complete(_sync_all())
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        loop.close()
    logger.info("Accounting bank sync run", **summary)
    return summary
