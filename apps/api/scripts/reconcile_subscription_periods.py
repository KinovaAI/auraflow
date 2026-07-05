#!/usr/bin/env python3
"""One-shot reconciliation for member_memberships drifted by the
Stripe 2025-11-17.clover API version change.

Background: the `invoice.payment_succeeded` webhook used to read
`invoice.subscription` at the top level. In Stripe API 2025-11-17 that
field was moved to `invoice.parent.subscription_details.subscription`,
and our handler started silently no-op'ing on every renewal. Result:
local `current_period_end` and (where applicable) `ends_at` drifted
behind Stripe's authoritative value.

This script:
  1. Iterates every active tenant.
  2. For each member_memberships row with a non-null
     stripe_subscription_id, fetches the canonical
     current_period_end from Stripe.
  3. Updates the local row if drift is more than 1 day.
  4. Reports a dry-run by default; pass `--apply` to actually write.

Run from inside the api container:
    sudo docker exec auraflow_api python /app/scripts/reconcile_subscription_periods.py
    sudo docker exec auraflow_api python /app/scripts/reconcile_subscription_periods.py --apply
"""
import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/app")

import stripe

from app.db.session import get_global_db, get_tenant_db
from app.utils.encryption import decrypt_credential


def _resolve_period_end(sub) -> int | None:
    """Pull current_period_end from the subscription in either schema."""
    pe = getattr(sub, "current_period_end", None)
    if pe:
        return pe
    items = getattr(sub, "items", None)
    if items and getattr(items, "data", None):
        return getattr(items.data[0], "current_period_end", None)
    return None


async def reconcile(apply: bool) -> None:
    drift_threshold = timedelta(days=1)
    fixed = 0
    skipped = 0
    errors = 0

    async with get_global_db() as gdb:
        orgs = await gdb.fetch(
            "SELECT id, schema_name, stripe_secret_key_encrypted "
            "FROM af_global.organizations "
            "WHERE status IN ('active', 'trial')"
        )

    for org in orgs:
        if not org["stripe_secret_key_encrypted"]:
            print(f"[{org['schema_name']}] no Stripe key, skipping")
            continue
        async with get_global_db() as gdb:
            sk = await decrypt_credential(gdb, org["stripe_secret_key_encrypted"])
        stripe.api_key = sk

        async with get_tenant_db(schema_override=org["schema_name"]) as db:
            rows = await db.fetch(
                """
                SELECT mm.id, mm.stripe_subscription_id,
                       mm.current_period_end, mm.ends_at,
                       m.first_name, m.last_name, m.email
                FROM member_memberships mm
                JOIN members m ON m.id = mm.member_id
                WHERE mm.stripe_subscription_id IS NOT NULL
                  AND mm.status IN ('active', 'past_due')
                """
            )

        print(f"\n[{org['schema_name']}] checking {len(rows)} subscription rows")

        for r in rows:
            sub_id = r["stripe_subscription_id"]
            name = f"{r['first_name']} {r['last_name']}"
            try:
                sub = stripe.Subscription.retrieve(sub_id)
            except Exception as e:
                print(f"  ERROR  {name:30}  retrieve({sub_id}): {e}")
                errors += 1
                continue

            true_pe_ts = _resolve_period_end(sub)
            if not true_pe_ts:
                print(f"  SKIP   {name:30}  no current_period_end available (sub status={sub.status})")
                skipped += 1
                continue
            true_pe = datetime.fromtimestamp(true_pe_ts, tz=timezone.utc)

            local_cpe = r["current_period_end"]
            local_ends = r["ends_at"]

            cpe_drift = abs((true_pe - local_cpe).total_seconds()) if local_cpe else float("inf")
            ends_drift = abs((true_pe - local_ends).total_seconds()) if local_ends else None

            updates = []
            if cpe_drift > drift_threshold.total_seconds():
                updates.append(("current_period_end", local_cpe, true_pe))
            # Only touch ends_at if it was previously tracking the period
            # (i.e. not NULL — null means unlimited / no expiry).
            if local_ends is not None and ends_drift > drift_threshold.total_seconds():
                updates.append(("ends_at", local_ends, true_pe))

            if not updates:
                continue

            change_summary = ", ".join(
                f"{col}: {old} → {new}" for col, old, new in updates
            )
            print(f"  {'FIX' if apply else 'DRY'}    {name:30}  {change_summary}")

            if apply:
                async with get_tenant_db(schema_override=org["schema_name"]) as db:
                    await db.execute(
                        """
                        UPDATE member_memberships
                        SET current_period_end = $1::timestamptz,
                            ends_at = CASE WHEN ends_at IS NULL
                                           THEN NULL
                                           ELSE $1::timestamptz END,
                            updated_at = NOW()
                        WHERE id = $2
                        """,
                        true_pe, r["id"],
                    )
                fixed += 1

    print(f"\n{'Applied' if apply else 'Would apply'}: {fixed} fix(es), {skipped} skipped, {errors} errors")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="Actually write to the DB (default is dry-run)")
    args = parser.parse_args()
    asyncio.run(reconcile(apply=args.apply))


if __name__ == "__main__":
    main()
