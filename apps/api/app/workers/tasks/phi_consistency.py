"""
AuraFlow — HIPAA 2C PHI Consistency Nightly Task

Runs the consistency scanner every night at 3am Pacific. Any drift between
plaintext and the encrypted shadow columns is reported to Sentry as a
high-priority alert + logged so morning triage can catch it before members
feel the impact.

A clean run for 7 consecutive days is the accepted gate for HIPAA 2C
Phase C (drop plaintext columns).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.core.logging import logger
from app.db.session import get_global_db, get_tenant_db
from app.core.tenant_context import set_tenant_context_from_schema, clear_tenant_context
from app.services.members.member_service import _decrypt, _get_fernet
from app.workers.celery_app import app


MEMBER_PHI_ENC_COLS = [
    "phone_enc",
    "date_of_birth_enc",
    "address_line1_enc",
    "city_enc",
    "state_enc",
    "postal_code_enc",
    "emergency_contact_name_enc",
    "emergency_contact_phone_enc",
    "notes_enc",
]


def _normalize(v) -> str:
    if v is None:
        return ""
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


async def _scan_schema(schema: str) -> dict:
    """Scan one tenant schema, return summary counts.

    Post-Phase-C only: plaintext PHI columns are dropped. The scan now
    verifies that every _enc shadow is readable (decryptable) and that
    phone_hash + birthday_month/day derived columns are populated where
    expected.
    """
    result = {
        "schema": schema,
        "members_scanned": 0,
        "members_consistent": 0,
        "members_missing_phone_hash": 0,
        "notes_scanned": 0,
        "notes_consistent": 0,
        "instructors_scanned": 0,
        "instructors_missing_phone_hash": 0,
        "mismatches": [],
    }

    await set_tenant_context_from_schema(schema)
    try:
        async with get_tenant_db(schema_override=schema) as db:
            member_rows = await db.fetch(
                "SELECT id, email, phone_hash, "
                + ", ".join(MEMBER_PHI_ENC_COLS)
                + " FROM members"
            )
            note_rows = await db.fetch(
                "SELECT id, member_id, note_enc FROM member_notes"
            )
            # instructors.phone is NOT in the Phase C drop scope — keep
            # reading plain to detect any rows missing phone_hash.
            instructor_rows = await db.fetch(
                "SELECT id, display_name, phone, phone_hash FROM instructors"
            )

        for row in member_rows:
            result["members_scanned"] += 1
            issues: list[dict] = []
            for enc_col in MEMBER_PHI_ENC_COLS:
                enc = row[enc_col]
                if enc is None:
                    continue
                try:
                    _decrypt(bytes(enc))
                except Exception as e:
                    issues.append({
                        "column": enc_col,
                        "kind": "decrypt_error",
                        "error": str(e),
                    })
            # phone_hash readiness — required for inbound-SMS lookup
            # (TCPA STOP/START, office_manager_service sender ID, etc.).
            # Tolerate canary test rows and any member whose phone is
            # libphonenumber-invalid (those rows were never searchable by
            # phone anyway). Decrypt phone_enc to verify validity.
            if row["phone_enc"] is not None and row["phone_hash"] is None:
                is_test = (row["email"] or "").endswith("@test.auraflow.dev")
                if not is_test:
                    from app.services.members.phone_hash import normalize_phone
                    try:
                        plain = _decrypt(bytes(row["phone_enc"]))
                    except Exception:
                        plain = None
                    if plain and normalize_phone(plain) is not None:
                        result["members_missing_phone_hash"] += 1
                        issues.append({
                            "column": "phone_hash",
                            "kind": "missing_hash",
                        })
                    # else: unparseable phone, never hashable — not a blocker
            if issues:
                result["mismatches"].append({
                    "member_id": str(row["id"]),
                    "email": row["email"],
                    "issues": issues,
                })
            else:
                result["members_consistent"] += 1

        from app.services.members.phone_hash import normalize_phone
        for row in instructor_rows:
            result["instructors_scanned"] += 1
            if row["phone"] and not row["phone_hash"]:
                if normalize_phone(row["phone"]) is None:
                    pass  # junk phone, not a Phase C blocker
                else:
                    result["instructors_missing_phone_hash"] += 1
                    result["mismatches"].append({
                        "instructor_id": str(row["id"]),
                        "name": row["display_name"],
                        "kind": "missing_instructor_hash",
                    })

        for row in note_rows:
            result["notes_scanned"] += 1
            enc = row["note_enc"]
            if not enc:
                # Post-drop: a note row with note_enc NULL is data loss.
                result["mismatches"].append({
                    "note_id": str(row["id"]),
                    "kind": "missing_enc",
                })
                continue
            try:
                _decrypt(bytes(enc))
                result["notes_consistent"] += 1
            except Exception as e:
                result["mismatches"].append({
                    "note_id": str(row["id"]),
                    "kind": "decrypt_error",
                    "error": str(e),
                })

    finally:
        clear_tenant_context()

    return result


async def _scan_all() -> dict:
    async with get_global_db() as db:
        schemas = await db.fetch(
            "SELECT schema_name FROM af_global.organizations "
            "WHERE status IN ('active', 'trial')"
        )

    summary = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "schemas": [],
        "total_mismatches": 0,
    }
    for s in schemas:
        report = await _scan_schema(s["schema_name"])
        summary["schemas"].append(report)
        summary["total_mismatches"] += len(report["mismatches"])

    return summary


@app.task(name="app.workers.tasks.phi_consistency.nightly_phi_scan")
def nightly_phi_scan():
    """Celery beat task — runs nightly at 3am Pacific.

    Reports drift to Sentry at fatal severity if any mismatch is found.
    """
    if _get_fernet() is None:
        logger.error(
            "HIPAA consistency scanner aborted — HEALTH_DATA_ENCRYPTION_KEY missing"
        )
        return {"error": "no_encryption_key"}

    loop = asyncio.new_event_loop()
    try:
        summary = loop.run_until_complete(_scan_all())
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        loop.close()

    logger.info(
        "PHI consistency scan complete",
        total_mismatches=summary["total_mismatches"],
        schemas=[
            {"schema": s["schema"],
             "members_consistent": s["members_consistent"],
             "members_needing_backfill": s["members_needing_backfill"],
             "notes_consistent": s["notes_consistent"],
             "mismatch_count": len(s["mismatches"])}
            for s in summary["schemas"]
        ],
    )

    if summary["total_mismatches"] > 0:
        # Fire a Sentry fatal so on-call gets paged — this is a HIPAA-adjacent
        # data-integrity failure that could leak PHI or block Phase C.
        try:
            import sentry_sdk
            sentry_sdk.capture_message(
                f"HIPAA 2C PHI drift detected: {summary['total_mismatches']} mismatches",
                level="fatal",
                extras=summary,
            )
        except Exception as exc:
            logger.warning("Sentry alert failed", error=str(exc))

    return summary
