"""Mercury bank auto-import for the Accounting module.

Faithful port of a standalone single-tenant LLC accounting app's Mercury sync —
verify + paginated transaction sync + `mercury_id` dedup — now **per-tenant and async**.
Each studio stores its own Mercury API key (encrypted at rest via pgcrypto). This
is **read-only** against Mercury; it only writes to the tenant's acct_transactions.

Mercury amounts are signed (>0 = money in, <0 = money out); mirroring the LLC app
we store the absolute amount and put the sign in `type` (income vs expense).
"""
from datetime import date

import httpx

from app.utils.encryption import decrypt_credential
from app.services.accounting.categories import (
    DEFAULT_INCOME_CATEGORY,
    DEFAULT_EXPENSE_CATEGORY,
)

MERCURY_API_URL = "https://api.mercury.com/api/v1"
PAGE_LIMIT = 500
SYNC_START = "2020-01-01T00:00:00Z"


async def _get_key(db) -> str | None:
    """Read + decrypt the tenant's Mercury key from acct_settings (db is tenant-scoped)."""
    row = await db.fetchrow(
        "SELECT mercury_api_key_enc FROM acct_settings WHERE id = 1"
    )
    if not row or not row["mercury_api_key_enc"]:
        return None
    return await decrypt_credential(db, row["mercury_api_key_enc"])


async def list_accounts(key: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=30.0) as http:
        r = await http.get(
            f"{MERCURY_API_URL}/accounts",
            headers={"Authorization": f"Bearer {key}"},
        )
        r.raise_for_status()
        data = r.json()
    return data.get("accounts", data if isinstance(data, list) else [])


async def list_credit_accounts(key: str) -> list[dict]:
    """Mercury's IO charge-card account(s). The /accounts endpoint hides these,
    but /credit returns them and their transactions are reachable at
    /account/{id}/transactions — so the individual card charges (utility, telecom, …)
    get itemized instead of only seeing the monthly payoff lump. Best-effort:
    returns [] if the endpoint isn't available for this key."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as http:
            r = await http.get(
                f"{MERCURY_API_URL}/credit",
                headers={"Authorization": f"Bearer {key}"},
            )
            if r.status_code != 200:
                return []
            return r.json().get("accounts", [])
    except Exception:  # noqa: BLE001
        return []


def _map_txn(tx: dict) -> dict | None:
    """Mercury tx -> acct_transactions fields. Mirrors server.js:773-808."""
    mercury_id = tx.get("id")
    if not mercury_id:
        return None
    raw = tx.get("amount")
    if raw is None and tx.get("amountCents") is not None:
        raw = tx["amountCents"] / 100.0
    if raw is None:
        return None
    amount = float(raw)
    desc_l = ((tx.get("bankDescription") or "") + " "
              + (tx.get("counterpartyName") or "")).lower()
    # Not income/expense — exclude from the P&L:
    #   - Checking↔Savings internal transfers
    #   - IO card payoff (money Checking→IO card, and the matching credit into the
    #     card). The individual card CHARGES are the real expenses; the payoff is
    #     just settling them, so counting it too would double.
    is_payoff = "io autopay" in desc_l or (tx.get("counterpartyName") == "Mercury Credit")
    if (tx.get("kind") or "") == "internalTransfer" or is_payoff:
        ttype = "transfer"
    else:
        ttype = "income" if amount > 0 else "expense"
    amount_cents = int(round(abs(amount) * 100))
    when = tx.get("postedAt") or tx.get("createdAt") or tx.get("date") or ""
    day = when.split("T")[0] if when else None
    try:
        txn_date = date.fromisoformat(day) if day else None
    except ValueError:
        txn_date = None
    # Lead with the counterparty (the instructor/vendor name) so payroll + vendor
    # auto-categorization can match on it, then the bank memo for readability.
    parts = [tx.get("counterpartyName"), tx.get("bankDescription")]
    desc = " — ".join(p for p in parts if p) or tx.get("note") or "Mercury Transaction"
    desc = desc[:500]
    if ttype == "transfer":
        category = "card_settlement" if is_payoff else "internal_transfer"
    elif ttype == "income":
        category = DEFAULT_INCOME_CATEGORY
    else:
        category = DEFAULT_EXPENSE_CATEGORY
    return {
        "external_id": str(mercury_id),
        "txn_date": txn_date,
        "type": ttype,
        "amount_cents": amount_cents,
        "description": desc,
        "category": category,
    }


async def sync_tenant(db) -> dict:
    """Pull every Mercury transaction for the tenant and upsert into
    acct_transactions deduped on (source='bank', external_id). `db` is a
    tenant-scoped connection. Returns import counts + per-account warnings.
    Never raises on a single-account failure — collects warnings (server.js:862-868).
    """
    key = await _get_key(db)
    if not key:
        return {"imported": 0, "skipped": 0, "error": "no_mercury_key"}

    try:
        accounts = await list_accounts(key)
    except Exception as e:  # noqa: BLE001
        return {"imported": 0, "skipped": 0, "error": f"accounts_failed: {e}"}
    # Include the IO charge-card account(s) so individual card charges (utility,
    # telecom, …) get itemized, not just the monthly payoff lump.
    credit = await list_credit_accounts(key)
    account_ids = [a["id"] for a in accounts + credit if a.get("id")]

    imported = skipped = 0
    warnings: list[str] = []
    async with httpx.AsyncClient(timeout=30.0) as http:
        headers = {"Authorization": f"Bearer {key}"}
        for acct_id in account_ids:
            offset = 0
            try:
                while True:
                    r = await http.get(
                        f"{MERCURY_API_URL}/account/{acct_id}/transactions",
                        headers=headers,
                        params={"limit": PAGE_LIMIT, "offset": offset, "start": SYNC_START},
                    )
                    r.raise_for_status()
                    txns = r.json().get("transactions", [])
                    if not txns:
                        break
                    for tx in txns:
                        row = _map_txn(tx)
                        if not row or not row["txn_date"]:
                            continue
                        status = await db.execute(
                            """
                            INSERT INTO acct_transactions
                                (txn_date, description, type, category, amount_cents,
                                 source, external_id, status)
                            VALUES ($1::date, $2, $3, $4, $5, 'bank', $6, 'pending')
                            ON CONFLICT (source, external_id)
                                WHERE external_id IS NOT NULL
                            DO NOTHING
                            """,
                            row["txn_date"], row["description"], row["type"],
                            row["category"], row["amount_cents"], row["external_id"],
                        )
                        if status and status.endswith(" 1"):
                            imported += 1
                        else:
                            skipped += 1
                    if len(txns) < PAGE_LIMIT:
                        break
                    offset += PAGE_LIMIT
            except Exception as e:  # noqa: BLE001
                warnings.append(f"account {acct_id}: {e}")

    await db.execute("UPDATE acct_settings SET last_sync_at = NOW() WHERE id = 1")
    return {"imported": imported, "skipped": skipped, "warnings": warnings}
