"""Liability waiver management — templates, signatures, and booking gate check."""
import uuid
from datetime import datetime, timedelta, timezone

from app.db.session import get_tenant_db


class WaiverService:

    async def get_active_template(self) -> dict | None:
        """Return the current active waiver template, or None."""
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                "SELECT * FROM waiver_templates WHERE is_active = TRUE ORDER BY version DESC LIMIT 1"
            )
            return dict(row) if row else None

    async def list_templates(self) -> list[dict]:
        """Return all waiver template versions, newest first."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                "SELECT * FROM waiver_templates ORDER BY version DESC"
            )
            return [dict(r) for r in rows]

    async def create_template(
        self,
        title: str,
        content: str,
        require_resign: bool = False,
        expiration_days: int | None = None,
        created_by: str | None = None,
    ) -> dict:
        """Create a new waiver template version. Deactivates the previous one."""
        template_id = str(uuid.uuid4())
        async with get_tenant_db() as db:
            async with db.transaction():
                # Get next version number
                max_v = await db.fetchval(
                    "SELECT COALESCE(MAX(version), 0) FROM waiver_templates"
                )
                next_version = max_v + 1

                # Deactivate previous active template
                await db.execute(
                    "UPDATE waiver_templates SET is_active = FALSE, updated_at = NOW() WHERE is_active = TRUE"
                )

                row = await db.fetchrow(
                    """
                    INSERT INTO waiver_templates (id, version, title, content, require_resign, expiration_days, is_active, created_by)
                    VALUES ($1, $2, $3, $4, $5, $6, TRUE, $7)
                    RETURNING *
                    """,
                    template_id, next_version, title, content, require_resign, expiration_days, created_by,
                )
                return dict(row)

    async def check_waiver_status(self, member_id: str) -> dict:
        """Check if a member has a valid waiver signature.

        Returns {"signed": True} if no active template exists (pass-through).
        Handles expiration and require_resign logic.
        """
        async with get_tenant_db() as db:
            template = await db.fetchrow(
                "SELECT * FROM waiver_templates WHERE is_active = TRUE ORDER BY version DESC LIMIT 1"
            )
            if not template:
                return {"signed": True, "expired": False, "needs_resign": False, "template": None, "signature": None}

            tpl = dict(template)

            # Find member's most recent signature
            sig = await db.fetchrow(
                """
                SELECT ws.* FROM waiver_signatures ws
                WHERE ws.member_id = $1
                ORDER BY ws.signed_at DESC LIMIT 1
                """,
                member_id,
            )

            if not sig:
                return {"signed": False, "expired": False, "needs_resign": False, "template": tpl, "signature": None}

            sig_dict = dict(sig)

            # Check if template requires re-sign and signature is for an older version
            if tpl["require_resign"] and sig_dict["waiver_template_id"] != tpl["id"]:
                return {"signed": False, "expired": False, "needs_resign": True, "template": tpl, "signature": sig_dict}

            # Check expiration
            if sig_dict.get("expires_at"):
                now = datetime.now(timezone.utc)
                if sig_dict["expires_at"].replace(tzinfo=timezone.utc) < now:
                    return {"signed": False, "expired": True, "needs_resign": False, "template": tpl, "signature": sig_dict}

            return {"signed": True, "expired": False, "needs_resign": False, "template": tpl, "signature": sig_dict}

    async def sign_waiver(
        self,
        member_id: str,
        template_id: str,
        signature_text: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict:
        """Record a member's waiver signature."""
        sig_id = str(uuid.uuid4())
        async with get_tenant_db() as db:
            # Look up template for expiration_days
            tpl = await db.fetchrow("SELECT * FROM waiver_templates WHERE id = $1", template_id)
            if not tpl:
                raise ValueError("Waiver template not found")

            expires_at = None
            if tpl["expiration_days"]:
                expires_at = datetime.now(timezone.utc) + timedelta(days=tpl["expiration_days"])

            row = await db.fetchrow(
                """
                INSERT INTO waiver_signatures (id, waiver_template_id, member_id, signature_text, ip_address, user_agent, expires_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING *
                """,
                sig_id, template_id, member_id, signature_text, ip_address, user_agent, expires_at,
            )
            return dict(row)

    async def get_member_signatures(self, member_id: str) -> list[dict]:
        """Return all waiver signatures for a member."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT ws.*, wt.title AS template_title, wt.version AS template_version
                FROM waiver_signatures ws
                JOIN waiver_templates wt ON wt.id = ws.waiver_template_id
                WHERE ws.member_id = $1
                ORDER BY ws.signed_at DESC
                """,
                member_id,
            )
            return [dict(r) for r in rows]

    async def get_unsigned_members(self) -> list[dict]:
        """Return members who haven't signed the current active waiver."""
        async with get_tenant_db() as db:
            template = await db.fetchrow(
                "SELECT * FROM waiver_templates WHERE is_active = TRUE ORDER BY version DESC LIMIT 1"
            )
            if not template:
                return []

            rows = await db.fetch(
                """
                SELECT m.id, m.first_name, m.last_name, m.email
                FROM members m
                WHERE m.is_active = TRUE
                  AND NOT EXISTS (
                    SELECT 1 FROM waiver_signatures ws
                    WHERE ws.member_id = m.id
                      AND ws.waiver_template_id = $1
                      AND (ws.expires_at IS NULL OR ws.expires_at > NOW())
                  )
                ORDER BY m.last_name, m.first_name
                """,
                template["id"],
            )
            return [dict(r) for r in rows]
