"""Real processing fees — the actual amounts Stripe and Square charged.

No estimates, no gross-minus-net calculation: we read the real fee off each
payment at the source.

  - Stripe: the tenant's own key (organizations.stripe_secret_key_encrypted, the
    legacy/direct-mode key) retrieves each charge with its balance_transaction,
    which carries the real `fee`.
  - Square: the PAYMENTS scope already granted returns each payment's real
    `processing_fee`.

Summed per month and posted as a Commissions & Fees expense (Schedule C Line 10),
source='auraflow', deduped on external_id 'procfee:YYYY-MM'. `db` is tenant-scoped;
`org_id` is the global org id.
"""
import asyncio
import collections
from datetime import date, datetime, timezone

import httpx

from app.core.logging import logger

SQUARE_VER = "2024-11-20"


def _square_base() -> str:
    from app.core.config import settings
    if (settings.SQUARE_ENVIRONMENT or "sandbox").lower() == "production":
        return "https://connect.squareup.com"
    return "https://connect.squareupsandbox.com"


def _ym(ts) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m")


async def _stripe_fees_by_month(db, org_id) -> dict:
    """Every real Stripe fee on the studio's account, from the balance-transaction
    ledger (not just AuraFlow-linked charges) — so the full fee picture is
    captured. Uses the tenant's own Stripe key."""
    from app.db.session import get_global_db
    from app.utils.encryption import decrypt_credential
    async with get_global_db() as g:
        row = await g.fetchrow(
            "SELECT stripe_secret_key_encrypted FROM af_global.organizations WHERE id = $1",
            org_id,
        )
        if not row or not row["stripe_secret_key_encrypted"]:
            return {}
        key = await decrypt_credential(g, row["stripe_secret_key_encrypted"])

    import stripe
    by_month: dict = collections.defaultdict(int)
    starting_after = None
    while True:
        params = {"limit": 100, "api_key": key}
        if starting_after:
            params["starting_after"] = starting_after
        page = await asyncio.to_thread(lambda p=params: stripe.BalanceTransaction.list(**p))
        data = page.get("data", [])
        if not data:
            break
        for bt in data:
            # charge/payment fees are positive fees; refunds carry negative fee
            fee = int(bt.get("fee") or 0)
            if fee:
                ym = _ym(bt.get("created"))
                if ym:
                    by_month[ym] += fee
        if not page.get("has_more"):
            break
        starting_after = data[-1]["id"]
    return by_month


async def _square_fees_by_month(db, org_id) -> dict:
    from app.services.payments.square_oauth_service import SquareOAuthService
    token = await SquareOAuthService().get_merchant_access_token(org_id)
    if not token:
        return {}
    by_month: dict = collections.defaultdict(int)
    headers = {"Authorization": f"Bearer {token}", "Square-Version": SQUARE_VER}
    cursor = None
    async with httpx.AsyncClient(timeout=30.0) as http:
        while True:
            params = {"limit": 100, "begin_time": "2020-01-01T00:00:00Z"}
            if cursor:
                params["cursor"] = cursor
            r = await http.get(f"{_square_base()}/v2/payments", headers=headers, params=params)
            r.raise_for_status()
            body = r.json()
            for p in body.get("payments", []):
                ym = (p.get("created_at") or "")[:7]
                for f in p.get("processing_fee", []) or []:
                    by_month[ym] += (f.get("amount_money") or {}).get("amount", 0)
            cursor = body.get("cursor")
            if not cursor:
                break
    return by_month


async def sync_fees(db, org_id) -> dict:
    combined: dict = collections.defaultdict(int)
    warnings = []
    try:
        for ym, c in (await _stripe_fees_by_month(db, org_id)).items():
            combined[ym] += c
    except Exception as e:  # noqa: BLE001
        warnings.append(f"stripe: {e}")
    try:
        for ym, c in (await _square_fees_by_month(db, org_id)).items():
            combined[ym] += c
    except Exception as e:  # noqa: BLE001
        warnings.append(f"square: {e}")

    posted = total = 0
    for ym, cents in combined.items():
        if not ym or cents <= 0:
            continue
        y, m = int(ym[:4]), int(ym[5:7])
        await db.execute(
            """
            INSERT INTO acct_transactions
                (txn_date, description, type, category, amount_cents, source,
                 external_id, status)
            VALUES ($1,$2,'expense','commissions_fees',$3,'auraflow',$4,'reconciled')
            ON CONFLICT (source, external_id) WHERE external_id IS NOT NULL
            DO UPDATE SET amount_cents = EXCLUDED.amount_cents, updated_at = NOW()
            """,
            date(y, m, 1), f"Card processing fees (Stripe/Square) — {ym}",
            cents, f"procfee:{ym}",
        )
        posted += 1
        total += cents
    result = {"fee_months": posted, "total_fee_cents": total, "warnings": warnings}
    logger.info("Accounting processing fees", fee_months=posted, total_fee_cents=total)
    return result
