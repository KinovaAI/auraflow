#!/usr/bin/env python3
"""
AuraFlow — HIPAA 2C PHI Consistency Scan

Read-only scan over every PHI-bearing row to verify dual-mode is in sync.
For each member + note, compares the plaintext value to the decrypted _enc
value and reports any mismatch.

A clean scan (0 mismatches) is the ground-truth precondition for HIPAA 2C
Phase C (drop plaintext columns).

Usage:
    # Run from the api container (has HEALTH_DATA_ENCRYPTION_KEY in env):
    sudo docker exec auraflow_api python /app/scripts/phi_consistency_scan.py
    sudo docker exec auraflow_api python /app/scripts/phi_consistency_scan.py --verbose
    sudo docker exec auraflow_api python /app/scripts/phi_consistency_scan.py --schema af_tenant_demo

Exit codes:
    0  — all rows consistent OR dual-mode hasn't been backfilled (informational)
    1  — at least one mismatch found (ACTION REQUIRED before Phase C)
    2  — scanner failure (env, DB, crypto)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/app")

from app.core.tenant_context import set_tenant_context, clear_tenant_context
from app.db.session import get_tenant_db, get_global_db
from app.services.members.member_service import _decrypt, _get_fernet


MEMBER_PHI_PAIRS = [
    ("phone",                    "phone_enc"),
    ("date_of_birth",            "date_of_birth_enc"),
    ("address_line1",            "address_line1_enc"),
    ("city",                     "city_enc"),
    ("state",                    "state_enc"),
    ("postal_code",              "postal_code_enc"),
    ("emergency_contact_name",   "emergency_contact_name_enc"),
    ("emergency_contact_phone",  "emergency_contact_phone_enc"),
    ("notes",                    "notes_enc"),
]


def _normalize(v) -> str:
    """Normalize a value for string comparison."""
    if v is None:
        return ""
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


async def _scan_members(schema: str, verbose: bool) -> dict:
    report = {
        "schema": schema,
        "table": "members",
        "rows_scanned": 0,
        "rows_with_any_phi": 0,
        "rows_fully_consistent": 0,
        "rows_dual_mode_empty": 0,  # plaintext present, _enc NULL (pre-backfill)
        "mismatches": [],
    }

    async with get_tenant_db(schema_override=schema) as db:
        rows = await db.fetch(
            "SELECT id, first_name, last_name, email, "
            + ", ".join(c for pair in MEMBER_PHI_PAIRS for c in pair)
            + " FROM members"
        )

    for row in rows:
        report["rows_scanned"] += 1
        has_phi = False
        mismatches_for_row: list[dict] = []
        missing_enc: list[str] = []

        for plain_col, enc_col in MEMBER_PHI_PAIRS:
            plain = row[plain_col]
            enc_bytes = row[enc_col]

            if plain:
                has_phi = True

            if plain and not enc_bytes:
                missing_enc.append(plain_col)
                continue
            if enc_bytes and not plain:
                # _enc present, plaintext NULL — could be real (legitimate clear)
                # or ghost data (plaintext was nulled but _enc wasn't). Flag it.
                try:
                    decrypted = _decrypt(bytes(enc_bytes))
                    if decrypted:
                        mismatches_for_row.append({
                            "column": plain_col,
                            "kind": "ghost_enc",
                            "plaintext": None,
                            "decrypted": decrypted,
                        })
                except Exception as e:
                    mismatches_for_row.append({
                        "column": plain_col,
                        "kind": "decrypt_error",
                        "error": str(e),
                    })
                continue
            if plain and enc_bytes:
                try:
                    decrypted = _decrypt(bytes(enc_bytes))
                except Exception as e:
                    mismatches_for_row.append({
                        "column": plain_col,
                        "kind": "decrypt_error",
                        "plaintext": _normalize(plain),
                        "error": str(e),
                    })
                    continue
                if _normalize(plain) != _normalize(decrypted):
                    mismatches_for_row.append({
                        "column": plain_col,
                        "kind": "value_mismatch",
                        "plaintext": _normalize(plain),
                        "decrypted": decrypted,
                    })

        if has_phi:
            report["rows_with_any_phi"] += 1

        if missing_enc and not mismatches_for_row:
            report["rows_dual_mode_empty"] += 1
            if verbose:
                print(f"  [INFO] member {row['id']} ({row['email']}): "
                      f"plaintext present but _enc NULL for {missing_enc}")
        elif not mismatches_for_row and not missing_enc:
            report["rows_fully_consistent"] += 1
        if mismatches_for_row:
            report["mismatches"].append({
                "member_id": str(row["id"]),
                "email": row["email"],
                "name": f"{row['first_name']} {row['last_name']}",
                "issues": mismatches_for_row,
            })

    return report


async def _scan_notes(schema: str, verbose: bool) -> dict:
    report = {
        "schema": schema,
        "table": "member_notes",
        "rows_scanned": 0,
        "rows_fully_consistent": 0,
        "rows_dual_mode_empty": 0,
        "mismatches": [],
    }

    async with get_tenant_db(schema_override=schema) as db:
        rows = await db.fetch(
            "SELECT id, member_id, note, note_enc FROM member_notes"
        )

    for row in rows:
        report["rows_scanned"] += 1
        plain = row["note"]
        enc_bytes = row["note_enc"]

        if plain and not enc_bytes:
            report["rows_dual_mode_empty"] += 1
            if verbose:
                print(f"  [INFO] note {row['id']}: plaintext present but note_enc NULL")
            continue
        if enc_bytes and not plain:
            try:
                decrypted = _decrypt(bytes(enc_bytes))
                if decrypted:
                    report["mismatches"].append({
                        "note_id": str(row["id"]),
                        "member_id": str(row["member_id"]),
                        "kind": "ghost_enc",
                        "decrypted": decrypted,
                    })
            except Exception as e:
                report["mismatches"].append({
                    "note_id": str(row["id"]),
                    "member_id": str(row["member_id"]),
                    "kind": "decrypt_error",
                    "error": str(e),
                })
            continue
        if plain and enc_bytes:
            try:
                decrypted = _decrypt(bytes(enc_bytes))
            except Exception as e:
                report["mismatches"].append({
                    "note_id": str(row["id"]),
                    "member_id": str(row["member_id"]),
                    "kind": "decrypt_error",
                    "plaintext": plain,
                    "error": str(e),
                })
                continue
            if plain != decrypted:
                report["mismatches"].append({
                    "note_id": str(row["id"]),
                    "member_id": str(row["member_id"]),
                    "kind": "value_mismatch",
                    "plaintext": plain,
                    "decrypted": decrypted,
                })
            else:
                report["rows_fully_consistent"] += 1
        else:
            report["rows_fully_consistent"] += 1

    return report


async def _list_tenant_schemas() -> list[str]:
    async with get_global_db() as db:
        rows = await db.fetch(
            "SELECT schema_name FROM af_global.organizations "
            "WHERE status IN ('active', 'trial') ORDER BY schema_name"
        )
    return [r["schema_name"] for r in rows]


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", help="Scan only this tenant schema")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print info about rows missing _enc backfill")
    parser.add_argument("--json", action="store_true",
                        help="Emit machine-readable JSON report")
    args = parser.parse_args()

    if _get_fernet() is None:
        print("[FATAL] HEALTH_DATA_ENCRYPTION_KEY not configured — cannot scan",
              file=sys.stderr)
        sys.exit(2)

    schemas = [args.schema] if args.schema else await _list_tenant_schemas()
    all_reports = []
    total_mismatches = 0

    for schema in schemas:
        # Scanner queries run without tenant_ctx since we override schema.
        set_tenant_context(organization_id="", schema_name=schema, slug=schema)
        try:
            m = await _scan_members(schema, args.verbose)
            n = await _scan_notes(schema, args.verbose)
        finally:
            clear_tenant_context()
        all_reports.append(m)
        all_reports.append(n)
        total_mismatches += len(m["mismatches"]) + len(n["mismatches"])

    summary = {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "schemas_scanned": schemas,
        "total_mismatches": total_mismatches,
        "reports": all_reports,
    }

    if args.json:
        print(json.dumps(summary, indent=2, default=str))
    else:
        print(f"HIPAA 2C PHI consistency scan — {summary['scanned_at']}")
        print(f"Schemas: {', '.join(schemas)}")
        print()
        for r in all_reports:
            schema = r["schema"]
            table = r["table"]
            print(f"  {schema}.{table}:")
            print(f"    rows scanned:            {r['rows_scanned']}")
            if table == "members":
                print(f"    rows with any PHI:       {r['rows_with_any_phi']}")
            print(f"    rows fully consistent:   {r['rows_fully_consistent']}")
            print(f"    rows dual-mode-empty:    {r['rows_dual_mode_empty']}  "
                  "(plaintext present, _enc NULL — needs backfill)")
            print(f"    mismatches:              {len(r['mismatches'])}")
            for m in r["mismatches"][:10]:
                print(f"      ⚠ {m}")
            if len(r["mismatches"]) > 10:
                print(f"      ... ({len(r['mismatches']) - 10} more)")
            print()
        print(f"TOTAL MISMATCHES: {total_mismatches}")
        if total_mismatches == 0:
            print("✅ All rows consistent. Phase C (drop plaintext) is safe.")
        else:
            print("❌ Mismatches found. Do NOT drop plaintext until resolved.")

    sys.exit(1 if total_mismatches else 0)


if __name__ == "__main__":
    asyncio.run(main())
