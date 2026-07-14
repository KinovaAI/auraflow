"""Payout tracking for the Accounting module.

A payment-processor **payout** is a batch of many member payments that lands in
the studio's bank as ONE deposit, net of fees. To make AuraFlow's recorded
income tie out to the bank statement (the authoritative record the IRS looks at),
we have to know which member payments composed each bank deposit. AuraFlow does
not persist payouts, so this service fetches the payout composition straight from
Stripe / Square and stores it per tenant:

  - acct_payouts       — one row per payout (net == the bank deposit amount).
  - acct_payout_items  — the payments in it (charge / payment id + fee), each
                         linked back to the AuraFlow `transactions` row it came
                         from (per-sale detail + Schedule C category).

`reconciliation.py` then matches each acct_payouts row to its imported bank
deposit. Uses the tenant's own Stripe Connect account / Square OAuth token — the
same credentials AuraFlow already charges through. Read-only against both APIs.
"""
from datetime import date, datetime, timezone

import httpx
import stripe

from app.core.logging import logger
from app.db.session import get_global_db
from app.utils.encryption import decrypt_credential
from app.services.payments import connect_account
from app.services.accounting.categories import DEFAULT_INCOME_CATEGORY

STRIPE_PAGE = 100
SQUARE_PAGE = 100
# Balance-transaction / payout-entry types that represent money movement we can
# attribute to a specific member payment.
_STRIPE_ITEM_TYPES = {"charge", "payment", "refund", "payment_refund"}


def _ts_to_date(ts) -> date | None:
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).date()
    except (ValueError, OSError, TypeError):
        return None


async def _tenant_providers(org_id: str) -> dict:
    """Resolve the tenant's Stripe Connect account + Square token/location."""
    stripe_acct = await connect_account.resolve_stripe_account_for_org(org_id)
    square_token = None
    square_location = None
    async with get_global_db() as gdb:
        row = await gdb.fetchrow(
            """
            SELECT square_access_token_encrypted, square_location_id
            FROM af_global.organizations WHERE id = $1
            """,
            org_id,
        )
        if row and row["square_access_token_encrypted"]:
            square_token = await decrypt_credential(
                gdb, row["square_access_token_encrypted"]
            )
            square_location = row["square_location_id"]
    return {
        "stripe_account": stripe_acct,
        "square_token": square_token,
        "square_location": square_location,
    }


async def _link_auraflow_txn(db, *, charge_id=None, payment_intent_id=None,
                             square_payment_id=None) -> dict:
    """Find the AuraFlow transactions row a payout item came from. `db` is
    tenant-scoped, so `transactions` resolves inside the tenant schema."""
    row = None
    if charge_id:
        row = await db.fetchrow(
            "SELECT id, member_id FROM transactions WHERE stripe_charge_id = $1",
            charge_id,
        )
    if not row and payment_intent_id:
        row = await db.fetchrow(
            "SELECT id, member_id FROM transactions WHERE stripe_payment_intent_id = $1",
            payment_intent_id,
        )
    if not row and square_payment_id:
        row = await db.fetchrow(
            "SELECT id, member_id FROM transactions WHERE square_payment_id = $1",
            square_payment_id,
        )
    # POS retail sales live in pos_transactions, not transactions — check there too
    # so POS card sales link into their payout (stripe_payment_id holds the id).
    if not row:
        pid = charge_id or payment_intent_id or square_payment_id
        if pid:
            row = await db.fetchrow(
                "SELECT id, member_id FROM pos_transactions WHERE stripe_payment_id = $1",
                pid,
            )
    if not row:
        return {"auraflow_txn_id": None, "member_id": None}
    return {"auraflow_txn_id": row["id"], "member_id": row["member_id"]}


async def _upsert_payout(db, provider, provider_id, payout_date, gross, fee, net,
                         status) -> str:
    row = await db.fetchrow(
        """
        INSERT INTO acct_payouts
            (provider, provider_payout_id, payout_date, gross_cents, fee_cents,
             net_cents, status)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (provider, provider_payout_id) DO UPDATE SET
            payout_date = EXCLUDED.payout_date,
            gross_cents = EXCLUDED.gross_cents,
            fee_cents   = EXCLUDED.fee_cents,
            net_cents   = EXCLUDED.net_cents,
            status      = EXCLUDED.status,
            updated_at  = NOW()
        RETURNING id
        """,
        provider, provider_id, payout_date, gross, fee, net, status,
    )
    return row["id"]


async def _upsert_item(db, payout_id, provider_payment_id, link, gross, fee, net):
    await db.execute(
        """
        INSERT INTO acct_payout_items
            (payout_id, provider_payment_id, auraflow_txn_id, member_id, category,
             gross_cents, fee_cents, net_cents)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (payout_id, provider_payment_id) DO UPDATE SET
            auraflow_txn_id = EXCLUDED.auraflow_txn_id,
            member_id       = EXCLUDED.member_id,
            gross_cents     = EXCLUDED.gross_cents,
            fee_cents       = EXCLUDED.fee_cents,
            net_cents       = EXCLUDED.net_cents
        """,
        payout_id, provider_payment_id, link["auraflow_txn_id"], link["member_id"],
        DEFAULT_INCOME_CATEGORY, gross, fee, net,
    )


# ── Stripe ────────────────────────────────────────────────────────────────

async def _sync_stripe(db, acct: str) -> dict:
    """List every Stripe payout for the tenant + its constituent charges."""
    from app.services.payments.stripe_service import _configure_stripe
    _configure_stripe()

    payouts_synced = items_synced = 0
    starting_after = None
    while True:
        params = {"limit": STRIPE_PAGE, "stripe_account": acct}
        if starting_after:
            params["starting_after"] = starting_after
        page = await _to_thread(lambda p=params: stripe.Payout.list(**p))
        data = page.get("data", [])
        if not data:
            break
        for po in data:
            gross = 0
            fee = 0
            # Walk the payout's balance transactions to find its charges.
            bt_after = None
            item_rows = []
            while True:
                bparams = {"payout": po["id"], "limit": STRIPE_PAGE,
                           "stripe_account": acct}
                if bt_after:
                    bparams["starting_after"] = bt_after
                bpage = await _to_thread(lambda p=bparams: stripe.BalanceTransaction.list(**p))
                bdata = bpage.get("data", [])
                if not bdata:
                    break
                for bt in bdata:
                    if bt.get("type") not in _STRIPE_ITEM_TYPES:
                        continue
                    source = bt.get("source")  # ch_... (or re_... for refunds)
                    if not source:
                        continue
                    b_gross = int(bt.get("amount") or 0)
                    b_fee = int(bt.get("fee") or 0)
                    b_net = int(bt.get("net") or (b_gross - b_fee))
                    gross += b_gross
                    fee += b_fee
                    item_rows.append((str(source), b_gross, b_fee, b_net))
                if not bpage.get("has_more"):
                    break
                bt_after = bdata[-1]["id"]

            net = int(po.get("amount") or 0)
            payout_id = await _upsert_payout(
                db, "stripe", str(po["id"]), _ts_to_date(po.get("arrival_date")),
                gross or net, fee, net, po.get("status"),
            )
            for source, b_gross, b_fee, b_net in item_rows:
                charge_id = source if str(source).startswith("ch_") else None
                link = await _link_auraflow_txn(db, charge_id=charge_id)
                await _upsert_item(db, payout_id, source, link, b_gross, b_fee, b_net)
                items_synced += 1
            payouts_synced += 1
        if not page.get("has_more"):
            break
        starting_after = data[-1]["id"]
    return {"payouts": payouts_synced, "items": items_synced}


# ── Square ────────────────────────────────────────────────────────────────

def _square_base() -> str:
    from app.core.config import settings
    if (settings.SQUARE_ENVIRONMENT or "sandbox").lower() == "production":
        return "https://connect.squareup.com"
    return "https://connect.squareupsandbox.com"


def _money(m) -> int:
    return int((m or {}).get("amount") or 0)


async def _sync_square(db, token: str, location_id: str | None) -> dict:
    headers = {
        "Authorization": f"Bearer {token}",
        "Square-Version": "2024-11-20",
        "Content-Type": "application/json",
    }
    base = _square_base()
    payouts_synced = items_synced = 0
    async with httpx.AsyncClient(timeout=30.0) as http:
        cursor = None
        while True:
            params = {"limit": SQUARE_PAGE}
            if location_id:
                params["location_id"] = location_id
            if cursor:
                params["cursor"] = cursor
            r = await http.get(f"{base}/v2/payouts", headers=headers, params=params)
            r.raise_for_status()
            body = r.json()
            for po in body.get("payouts", []):
                gross = fee = 0
                item_rows = []
                # Fetch this payout's entries (its member payments + fees).
                ecursor = None
                while True:
                    eparams = {"limit": SQUARE_PAGE}
                    if ecursor:
                        eparams["cursor"] = ecursor
                    er = await http.get(
                        f"{base}/v2/payouts/{po['id']}/payout-entries",
                        headers=headers, params=eparams,
                    )
                    er.raise_for_status()
                    ebody = er.json()
                    for e in ebody.get("payout_entries", []):
                        etype = e.get("type")
                        payment_id = None
                        if etype in ("CHARGE", "REFUND", "DISPUTE"):
                            details = (
                                e.get("type_charge_details")
                                or e.get("type_refund_details")
                                or e.get("type_dispute_details")
                                or {}
                            )
                            payment_id = details.get("payment_id")
                        if not payment_id:
                            # fee-only / non-payment entries roll into payout fee
                            fee += -_money(e.get("fee_amount_money")) \
                                if e.get("fee_amount_money") else 0
                            continue
                        e_gross = _money(e.get("gross_amount_money"))
                        e_fee = -_money(e.get("fee_amount_money"))
                        e_net = _money(e.get("net_amount_money")) or (e_gross - e_fee)
                        gross += e_gross
                        fee += e_fee
                        item_rows.append((str(payment_id), e_gross, e_fee, e_net))
                    ecursor = ebody.get("cursor")
                    if not ecursor:
                        break

                net = _money(po.get("amount_money"))
                payout_id = await _upsert_payout(
                    db, "square", str(po["id"]),
                    _parse_square_date(po.get("arrival_date") or po.get("created_at")),
                    gross or net, fee, net, po.get("status"),
                )
                for payment_id, e_gross, e_fee, e_net in item_rows:
                    link = await _link_auraflow_txn(db, square_payment_id=payment_id)
                    await _upsert_item(db, payout_id, payment_id, link, e_gross, e_fee, e_net)
                    items_synced += 1
                payouts_synced += 1
            cursor = body.get("cursor")
            if not cursor:
                break
    return {"payouts": payouts_synced, "items": items_synced}


def _parse_square_date(s) -> date | None:
    if not s:
        return None
    try:
        # Square dates are RFC3339 ("2026-01-05" or full timestamp)
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(str(s)[:10])
        except ValueError:
            return None


# ── Orchestration ───────────────────────────────────────────────────────────

async def _to_thread(fn):
    import asyncio
    return await asyncio.to_thread(fn)


async def sync_payouts(db, org_id: str) -> dict:
    """Pull every Stripe + Square payout (+ its items) for the tenant into
    acct_payouts / acct_payout_items. `db` is a tenant-scoped connection.
    Tolerates a single-provider failure (collects it as a warning). Returns
    per-provider counts. Does NOT reconcile — call reconciliation.reconcile()."""
    prov = await _tenant_providers(org_id)
    result = {"stripe": None, "square": None, "warnings": []}

    if prov["stripe_account"]:
        try:
            result["stripe"] = await _sync_stripe(db, prov["stripe_account"])
        except Exception as e:  # noqa: BLE001
            result["warnings"].append(f"stripe: {e}")
            logger.warning("Payout sync (stripe) failed", org_id=str(org_id), error=str(e))

    if prov["square_token"]:
        try:
            result["square"] = await _sync_square(
                db, prov["square_token"], prov["square_location"]
            )
        except Exception as e:  # noqa: BLE001
            result["warnings"].append(f"square: {e}")
            logger.warning("Payout sync (square) failed", org_id=str(org_id), error=str(e))

    return result
