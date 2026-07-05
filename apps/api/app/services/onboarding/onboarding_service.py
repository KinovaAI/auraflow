"""AuraFlow — Onboarding Checklist Service

Manages the tenant onboarding checklist: fetch steps, mark them complete,
and auto-detect completions by inspecting actual tenant data.
"""
import uuid
from datetime import datetime, timezone

from app.core.logging import logger
from app.db.session import get_tenant_db


class OnboardingService:
    """Reads/updates the onboarding_checklist table and auto-detects progress."""

    async def get_checklist(self) -> list[dict]:
        """Get all checklist steps ordered by sort_order."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT * FROM onboarding_checklist
                ORDER BY sort_order, created_at
                """,
            )
        return [_step_to_dict(r) for r in rows]

    async def complete_step(
        self, step_key: str, completed_by: str
    ) -> dict | None:
        """Mark a checklist step as completed.

        Returns the updated step, or None if *step_key* does not exist.
        """
        now = datetime.now(timezone.utc)
        async with get_tenant_db() as db:
            result = await db.execute(
                """
                UPDATE onboarding_checklist
                SET completed_at = COALESCE(completed_at, $2),
                    completed_by = COALESCE(completed_by, $3)
                WHERE step_key = $1
                """,
                step_key,
                now,
                completed_by,
            )
            if "UPDATE 0" in result:
                return None

            row = await db.fetchrow(
                "SELECT * FROM onboarding_checklist WHERE step_key = $1",
                step_key,
            )

        logger.info(
            "Onboarding step completed",
            step_key=step_key,
            completed_by=completed_by,
        )
        return _step_to_dict(row) if row else None

    async def auto_detect_completions(self) -> list[str]:
        """Auto-detect which onboarding steps are already done.

        Checks actual data in the tenant schema and marks incomplete steps
        as completed when their criteria are met.

        Returns a list of step_keys that were newly completed.
        """
        # Map step_key -> SQL that returns a truthy count when the step is done
        checks: dict[str, str] = {
            "create_studio": (
                "SELECT COUNT(*) FROM studios WHERE is_active = TRUE"
            ),
            "add_class_type": (
                "SELECT COUNT(*) FROM class_types WHERE is_active = TRUE"
            ),
            "create_schedule": (
                "SELECT COUNT(*) FROM class_sessions LIMIT 1"
            ),
            "invite_instructor": (
                "SELECT COUNT(*) FROM instructors WHERE is_active = TRUE"
            ),
            "add_member": (
                "SELECT COUNT(*) FROM members WHERE is_active = TRUE"
            ),
            "setup_payments": (
                "SELECT COUNT(*) FROM integration_configs "
                "WHERE provider = 'stripe' AND is_active = TRUE"
            ),
            "create_membership": (
                "SELECT COUNT(*) FROM membership_types WHERE is_active = TRUE"
            ),
            "send_first_email": (
                "SELECT COUNT(*) FROM email_campaigns WHERE status = 'sent' LIMIT 1"
            ),
            "customize_branding": (
                "SELECT COUNT(*) FROM branding_settings LIMIT 1"
            ),
            "explore_ai": (
                "SELECT COUNT(*) FROM chatbot_conversations LIMIT 1"
            ),
        }

        now = datetime.now(timezone.utc)
        newly_completed: list[str] = []

        async with get_tenant_db() as db:
            # Load current incomplete steps
            rows = await db.fetch(
                """
                SELECT step_key FROM onboarding_checklist
                WHERE completed_at IS NULL
                """,
            )
            incomplete_keys = {r["step_key"] for r in rows}

            for step_key, sql in checks.items():
                if step_key not in incomplete_keys:
                    continue  # already marked done

                try:
                    count = await db.fetchval(sql)
                    if count and count > 0:
                        await db.execute(
                            """
                            UPDATE onboarding_checklist
                            SET completed_at = $2,
                                completed_by = NULL
                            WHERE step_key = $1
                              AND completed_at IS NULL
                            """,
                            step_key,
                            now,
                        )
                        newly_completed.append(step_key)
                except Exception as exc:
                    # Table might not exist yet for some tenants — skip gracefully
                    logger.debug(
                        "Onboarding auto-detect skipped step",
                        step_key=step_key,
                        error=str(exc),
                    )

        if newly_completed:
            logger.info(
                "Onboarding auto-detect completed steps",
                steps=newly_completed,
            )
        return newly_completed


# ── Serialization ──────────────────────────────────────────────────────


def _step_to_dict(row) -> dict:
    """Convert an onboarding_checklist row to a JSON-safe dict."""
    d = dict(row)
    for k in ("id", "completed_by"):
        if d.get(k):
            d[k] = str(d[k])
    for k in ("completed_at", "created_at"):
        if d.get(k):
            d[k] = d[k].isoformat()
    d["is_completed"] = d.get("completed_at") is not None
    return d
