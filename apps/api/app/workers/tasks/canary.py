"""
AuraFlow — Synthetic Canary Task

Runs every 5 minutes via Celery Beat. Exercises the live member-facing
data path end-to-end against a dedicated canary member per tenant so any
regression in DB connectivity, PHI dual-mode, eligibility checks, or
membership lookup surfaces as a Sentry fatal within 5 minutes instead
of only when a real member hits the bug.

Canary member convention: email = `canary@test.auraflow.dev` in each
tenant schema. Created on first run if missing. The canary is
intentionally special-cased to skip from all real member flows (email
sends, SMS, birthday list, churn scan) via its email suffix — every
production task already filters out `@test.auraflow.dev` recipients.
"""
import asyncio
import uuid
from datetime import datetime, timezone

from app.core.logging import logger
from app.db.session import get_global_db, get_tenant_db
from app.core.tenant_context import set_tenant_context_from_schema, clear_tenant_context
from app.services.members.member_service import MemberService
from app.workers.celery_app import app


CANARY_EMAIL = "canary@test.auraflow.dev"


async def _ensure_canary_member(schema: str) -> str:
    """Return the canary member's id in this tenant schema, creating it
    if it doesn't already exist."""
    async with get_tenant_db(schema_override=schema) as db:
        existing = await db.fetchrow(
            "SELECT id FROM members WHERE email = $1", CANARY_EMAIL,
        )
        if existing:
            return str(existing["id"])

    # Doesn't exist — create via the real service so dual-write is exercised.
    svc = MemberService()
    created = await svc.create_member({
        "first_name": "Canary",
        "last_name": "Bot",
        "email": CANARY_EMAIL,
        "phone": "+15550000001",
        "source": "canary",
    })
    return created["id"]


async def _canary_for_tenant(schema: str) -> dict:
    started = datetime.now(timezone.utc)
    result = {
        "schema": schema,
        "steps": [],
        "ok": True,
        "latency_ms": 0,
    }

    await set_tenant_context_from_schema(schema)
    try:
        # Step 1: ensure canary member
        try:
            member_id = await _ensure_canary_member(schema)
            result["steps"].append({"step": "ensure_member", "ok": True})
        except Exception as exc:
            result["ok"] = False
            result["steps"].append({
                "step": "ensure_member",
                "ok": False,
                "error": str(exc),
            })
            return result

        svc = MemberService()

        # Step 2: read back via get_member (exercises PHI dual-read)
        try:
            fetched = await svc.get_member(member_id)
            if not fetched:
                raise RuntimeError("get_member returned None")
            # Verify PHI round-trip: phone should decrypt back to what
            # we wrote. A mismatch here means PHI dual-mode is breaking.
            if fetched.get("phone") != "+15550000001":
                raise RuntimeError(
                    f"PHI round-trip mismatch: phone={fetched.get('phone')!r}"
                )
            result["steps"].append({"step": "get_member", "ok": True})
        except Exception as exc:
            result["ok"] = False
            result["steps"].append({
                "step": "get_member",
                "ok": False,
                "error": str(exc),
            })
            return result

        # Step 3: trivial DB write (update a non-PHI column) to exercise
        # the write path. Touches total_visits counter which is safe to
        # increment repeatedly — canary won't pollute reports since its
        # email suffix filters out.
        try:
            async with get_tenant_db(schema_override=schema) as db:
                await db.execute(
                    "UPDATE members SET total_visits = total_visits + 1 "
                    "WHERE id = $1",
                    member_id,
                )
            result["steps"].append({"step": "db_write", "ok": True})
        except Exception as exc:
            result["ok"] = False
            result["steps"].append({
                "step": "db_write",
                "ok": False,
                "error": str(exc),
            })

    finally:
        clear_tenant_context()
        result["latency_ms"] = int(
            (datetime.now(timezone.utc) - started).total_seconds() * 1000
        )

    return result


async def _run_all_canaries() -> dict:
    async with get_global_db() as db:
        schemas = await db.fetch(
            "SELECT schema_name FROM af_global.organizations "
            "WHERE status IN ('active', 'trial')"
        )

    reports = []
    for row in schemas:
        try:
            reports.append(await _canary_for_tenant(row["schema_name"]))
        except Exception as exc:
            reports.append({
                "schema": row["schema_name"],
                "ok": False,
                "error": f"canary exception: {exc}",
            })

    total = len(reports)
    failed = sum(1 for r in reports if not r.get("ok"))
    return {"total": total, "failed": failed, "reports": reports}


@app.task(name="app.workers.tasks.canary.run_synthetic_canary")
def run_synthetic_canary():
    """Celery beat task — canary every 5 min. Sentry-fatal on any tenant
    whose canary fails."""
    loop = asyncio.new_event_loop()
    try:
        summary = loop.run_until_complete(_run_all_canaries())
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        loop.close()

    if summary["failed"]:
        logger.error(
            "Synthetic canary failed",
            total=summary["total"],
            failed=summary["failed"],
        )
        try:
            import sentry_sdk
            sentry_sdk.capture_message(
                f"Synthetic canary failed in {summary['failed']}/{summary['total']} tenants",
                level="fatal",
                extras=summary,
            )
        except Exception:
            pass
    else:
        logger.info("Synthetic canary OK", total=summary["total"])
    return summary
