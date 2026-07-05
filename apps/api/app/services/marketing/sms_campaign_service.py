"""AuraFlow — SMS Campaign & Template Service

Bulk SMS campaigns, template management, audience resolution, scheduling,
campaign stats, and retry logic.
"""
import re
import uuid
from datetime import datetime, timezone

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_tenant_db
from app.services.marketing.campaign_service import SmsService

sms_svc = SmsService()

_SMS_CAMPAIGN_UPDATE_COLS = {
    "name", "body", "template_id", "audience_filter", "scheduled_at",
}


class SmsTemplateService:
    """CRUD for SMS message templates with variable substitution."""

    async def list_templates(
        self, category: str | None = None, active_only: bool = True
    ) -> list[dict]:
        async with get_tenant_db() as db:
            if category and active_only:
                rows = await db.fetch(
                    "SELECT * FROM sms_templates WHERE category = $1 AND is_active = TRUE ORDER BY name",
                    category,
                )
            elif active_only:
                rows = await db.fetch(
                    "SELECT * FROM sms_templates WHERE is_active = TRUE ORDER BY name"
                )
            else:
                rows = await db.fetch("SELECT * FROM sms_templates ORDER BY name")
            return [dict(r) for r in rows]

    async def get_template(self, template_id: str) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow("SELECT * FROM sms_templates WHERE id = $1", template_id)
            return dict(row) if row else None

    async def get_template_by_slug(self, slug: str) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow("SELECT * FROM sms_templates WHERE slug = $1", slug)
            return dict(row) if row else None

    async def create_template(self, data: dict) -> dict:
        tid = str(uuid.uuid4())
        # Auto-extract variables from {{variable_name}} patterns
        variables = re.findall(r"\{\{(\w+)\}\}", data.get("body", ""))
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                INSERT INTO sms_templates (id, name, slug, body, description, variables, category, created_by)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING *
                """,
                tid, data["name"], data["slug"], data["body"],
                data.get("description"), variables,
                data.get("category", "general"), data.get("created_by"),
            )
            return dict(row)

    async def update_template(self, template_id: str, data: dict) -> dict | None:
        async with get_tenant_db() as db:
            existing = await db.fetchrow("SELECT * FROM sms_templates WHERE id = $1", template_id)
            if not existing:
                return None

            body = data.get("body", existing["body"])
            variables = re.findall(r"\{\{(\w+)\}\}", body)

            row = await db.fetchrow(
                """
                UPDATE sms_templates
                SET name = COALESCE($2, name),
                    body = COALESCE($3, body),
                    description = COALESCE($4, description),
                    variables = $5,
                    category = COALESCE($6, category),
                    is_active = COALESCE($7, is_active),
                    updated_at = NOW()
                WHERE id = $1
                RETURNING *
                """,
                template_id,
                data.get("name"), data.get("body"), data.get("description"),
                variables, data.get("category"), data.get("is_active"),
            )
            return dict(row) if row else None

    async def delete_template(self, template_id: str) -> bool:
        async with get_tenant_db() as db:
            result = await db.execute(
                "DELETE FROM sms_templates WHERE id = $1", template_id
            )
            return "DELETE 1" in result

    def render_template(self, body: str, variables: dict) -> str:
        """Replace {{variable}} placeholders with values."""
        result = body
        for key, value in variables.items():
            result = result.replace(f"{{{{{key}}}}}", str(value))
        return result


class SmsCampaignService:
    """Bulk SMS campaign management with audience targeting, scheduling, and stats."""

    def __init__(self):
        self._template_svc = SmsTemplateService()

    # ── Campaign CRUD ──────────────────────────────────────────────────────

    async def create_campaign(self, data: dict) -> dict:
        campaign_id = str(uuid.uuid4())
        import json
        audience_filter = data.get("audience_filter") or {}
        if isinstance(audience_filter, dict):
            audience_filter = json.dumps(audience_filter)

        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                INSERT INTO sms_campaigns
                    (id, name, body, template_id, audience_filter, scheduled_at, created_by)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6::timestamptz, $7)
                RETURNING *
                """,
                campaign_id, data["name"], data["body"],
                data.get("template_id"), audience_filter,
                data.get("scheduled_at"), data.get("created_by"),
            )
            logger.info("SMS campaign created", campaign_id=campaign_id, name=data["name"])
            return dict(row)

    async def get_campaign(self, campaign_id: str) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow("SELECT * FROM sms_campaigns WHERE id = $1", campaign_id)
            return dict(row) if row else None

    async def list_campaigns(self, status: str | None = None) -> list[dict]:
        async with get_tenant_db() as db:
            if status:
                rows = await db.fetch(
                    "SELECT * FROM sms_campaigns WHERE status = $1 ORDER BY created_at DESC",
                    status,
                )
            else:
                rows = await db.fetch("SELECT * FROM sms_campaigns ORDER BY created_at DESC")
            return [dict(r) for r in rows]

    async def update_campaign(self, campaign_id: str, data: dict) -> dict | None:
        data = {k: v for k, v in data.items() if k in _SMS_CAMPAIGN_UPDATE_COLS}
        async with get_tenant_db() as db:
            sets, params, idx = [], [], 1
            for k, v in data.items():
                sets.append(f"{k} = ${idx}")
                params.append(v)
                idx += 1
            if not sets:
                return await self.get_campaign(campaign_id)
            sets.append(f"updated_at = ${idx}")
            params.append(datetime.now(timezone.utc))
            idx += 1
            params.append(campaign_id)
            query = f"UPDATE sms_campaigns SET {', '.join(sets)} WHERE id = ${idx} AND status = 'draft' RETURNING *"
            row = await db.fetchrow(query, *params)
            return dict(row) if row else None

    async def delete_campaign(self, campaign_id: str) -> bool:
        async with get_tenant_db() as db:
            result = await db.execute(
                "DELETE FROM sms_campaigns WHERE id = $1 AND status = 'draft'", campaign_id
            )
            return "DELETE 1" in result

    async def schedule_campaign(self, campaign_id: str, scheduled_at: str) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                UPDATE sms_campaigns
                SET status = 'scheduled', scheduled_at = $2::timestamptz, updated_at = NOW()
                WHERE id = $1 AND status = 'draft'
                RETURNING *
                """,
                campaign_id, scheduled_at,
            )
            return dict(row) if row else None

    async def cancel_campaign(self, campaign_id: str) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                UPDATE sms_campaigns
                SET status = 'cancelled', updated_at = NOW()
                WHERE id = $1 AND status IN ('draft', 'scheduled')
                RETURNING *
                """,
                campaign_id,
            )
            return dict(row) if row else None

    # ── Audience Resolution ────────────────────────────────────────────────

    async def preview_audience(self, audience_filter: dict) -> dict:
        """Count members matching filter who have phone + sms_opt_in."""
        async with get_tenant_db() as db:
            # phone_enc populated for every member who has a phone (dual-write
            # has been live since Phase B). Filtering on _enc keeps working
            # after the plaintext column drops.
            conditions = ["is_active = TRUE", "phone_enc IS NOT NULL", "sms_opt_in = TRUE"]
            params = []
            idx = 1

            if audience_filter.get("tags"):
                conditions.append(f"tags && ${idx}")
                params.append(audience_filter["tags"])
                idx += 1

            if audience_filter.get("membership_type_ids"):
                conditions.append(f"""
                    id IN (
                        SELECT mm.member_id FROM member_memberships mm
                        WHERE mm.membership_type_id = ANY(${idx})
                        AND mm.status = 'active'
                    )
                """)
                params.append(audience_filter["membership_type_ids"])
                idx += 1

            where = " AND ".join(conditions)
            count = await db.fetchval(f"SELECT COUNT(*) FROM members WHERE {where}", *params)
            return {"count": count, "filter": audience_filter}

    async def _resolve_sms_audience(self, audience_filter: dict) -> list[dict]:
        """Get members with phone + sms_opt_in matching the filter."""
        async with get_tenant_db() as db:
            # phone_enc populated for every member who has a phone (dual-write
            # has been live since Phase B). Filtering on _enc keeps working
            # after the plaintext column drops.
            conditions = ["is_active = TRUE", "phone_enc IS NOT NULL", "sms_opt_in = TRUE"]
            params = []
            idx = 1

            if audience_filter.get("tags"):
                conditions.append(f"tags && ${idx}")
                params.append(audience_filter["tags"])
                idx += 1

            if audience_filter.get("membership_type_ids"):
                conditions.append(f"""
                    id IN (
                        SELECT mm.member_id FROM member_memberships mm
                        WHERE mm.membership_type_id = ANY(${idx})
                        AND mm.status = 'active'
                    )
                """)
                params.append(audience_filter["membership_type_ids"])
                idx += 1

            where = " AND ".join(conditions)
            rows = await db.fetch(
                f"SELECT id, phone_enc, first_name FROM members WHERE {where}",
                *params,
            )
            # Decrypt phone now so downstream send_sms gets the resolved
            # value regardless of which column actually carried it.
            from app.services.members.phi_helpers import decrypt_phone
            return [
                {**dict(r), "phone": decrypt_phone(r)}
                for r in rows
            ]

    # ── Send Campaign ──────────────────────────────────────────────────────

    async def send_campaign(self, campaign_id: str) -> dict:
        """Send an SMS campaign to its resolved audience."""
        campaign = await self.get_campaign(campaign_id)
        if not campaign:
            raise ValueError("Campaign not found")
        if campaign["status"] not in ("draft", "scheduled"):
            raise ValueError(f"Cannot send campaign in '{campaign['status']}' status")

        import json
        audience_filter = campaign.get("audience_filter") or {}
        if isinstance(audience_filter, str):
            audience_filter = json.loads(audience_filter)

        members = await self._resolve_sms_audience(audience_filter)

        async with get_tenant_db() as db:
            # Mark as sending
            await db.execute(
                "UPDATE sms_campaigns SET status = 'sending', recipients = $2, updated_at = NOW() WHERE id = $1",
                campaign_id, len(members),
            )

            sent = 0
            failed = 0
            for member in members:
                send_id = str(uuid.uuid4())
                member_name = member.get("first_name") or "there"
                # Render body with member variables
                body = campaign["body"].replace("{{member_name}}", member_name)
                body = body.replace("{{first_name}}", member_name)

                try:
                    result = await sms_svc.send_sms(
                        to_phone=member["phone"],
                        body=body,
                        member_id=str(member["id"]),
                        sms_type="campaign",
                    )
                    status = "sent"
                    twilio_sid = result.get("twilio_sid")
                    sent += 1
                except Exception as e:
                    status = "failed"
                    twilio_sid = None
                    failed += 1
                    logger.error(
                        "SMS campaign send failed",
                        member_phone=member["phone"],
                        error=str(e),
                    )

                await db.fetchrow(
                    """
                    INSERT INTO sms_campaign_sends
                        (id, campaign_id, member_id, to_phone, status, twilio_sid, error_message)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    RETURNING *
                    """,
                    send_id, campaign_id, str(member["id"]), member["phone"],
                    status, twilio_sid,
                    None if status == "sent" else "Send failed",
                )

            # Mark as sent
            await db.execute(
                """
                UPDATE sms_campaigns
                SET status = 'sent', sent_at = NOW(), delivered = $2, failed = $3, updated_at = NOW()
                WHERE id = $1
                """,
                campaign_id, sent, failed,
            )

        logger.info(
            "SMS campaign sent",
            campaign_id=campaign_id,
            recipients=len(members),
            delivered=sent,
            failed=failed,
        )
        return {"sent": sent, "failed": failed, "total": len(members)}

    # ── Campaign Stats ─────────────────────────────────────────────────────

    async def get_campaign_stats(self, campaign_id: str) -> dict:
        async with get_tenant_db() as db:
            campaign = await db.fetchrow("SELECT * FROM sms_campaigns WHERE id = $1", campaign_id)
            if not campaign:
                return {}

            stats = await db.fetchrow(
                """
                SELECT
                    COUNT(*) AS total_sends,
                    COUNT(*) FILTER (WHERE status = 'sent') AS sent,
                    COUNT(*) FILTER (WHERE status = 'delivered') AS delivered,
                    COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                    COUNT(*) FILTER (WHERE status = 'opted_out') AS opted_out
                FROM sms_campaign_sends WHERE campaign_id = $1
                """,
                campaign_id,
            )
            return {**dict(campaign), "send_stats": dict(stats) if stats else {}}

    # ── SMS Analytics ──────────────────────────────────────────────────────

    async def get_sms_stats(self, days: int = 30) -> dict:
        """Aggregate SMS stats across all message types."""
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                SELECT
                    COUNT(*) AS total_messages,
                    COUNT(*) FILTER (WHERE status = 'sent') AS sent,
                    COUNT(*) FILTER (WHERE status = 'delivered') AS delivered,
                    COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                    COUNT(DISTINCT member_id) AS unique_recipients,
                    COUNT(*) FILTER (WHERE type = 'campaign') AS campaign_messages,
                    COUNT(*) FILTER (WHERE type = 'transactional') AS transactional_messages,
                    COUNT(*) FILTER (WHERE type = 'reminder') AS reminder_messages
                FROM sms_messages
                WHERE created_at >= $1
                """,
                cutoff,
            )
            # Campaign-level stats
            campaigns = await db.fetchrow(
                """
                SELECT
                    COUNT(*) AS total_campaigns,
                    COUNT(*) FILTER (WHERE status = 'sent') AS sent_campaigns,
                    COUNT(*) FILTER (WHERE status = 'draft') AS draft_campaigns,
                    COUNT(*) FILTER (WHERE status = 'scheduled') AS scheduled_campaigns
                FROM sms_campaigns
                WHERE created_at >= $1
                """,
                cutoff,
            )
            return {
                "messages": dict(row) if row else {},
                "campaigns": dict(campaigns) if campaigns else {},
                "period_days": days,
            }

    # ── Retry Failed Messages ──────────────────────────────────────────────

    async def retry_failed_sends(self, campaign_id: str) -> dict:
        """Retry all failed sends for a campaign."""
        async with get_tenant_db() as db:
            failed_sends = await db.fetch(
                """
                SELECT id, member_id, to_phone FROM sms_campaign_sends
                WHERE campaign_id = $1 AND status = 'failed'
                """,
                campaign_id,
            )

        campaign = await self.get_campaign(campaign_id)
        if not campaign:
            raise ValueError("Campaign not found")

        retried = 0
        still_failed = 0

        for send in failed_sends:
            try:
                result = await sms_svc.send_sms(
                    to_phone=send["to_phone"],
                    body=campaign["body"],
                    member_id=str(send["member_id"]),
                    sms_type="campaign",
                )
                async with get_tenant_db() as db:
                    await db.execute(
                        """
                        UPDATE sms_campaign_sends
                        SET status = 'sent', twilio_sid = $2, error_message = NULL
                        WHERE id = $1
                        """,
                        str(send["id"]), result.get("twilio_sid"),
                    )
                retried += 1
            except Exception as e:
                still_failed += 1
                logger.warning("SMS retry failed", send_id=str(send["id"]), error=str(e))

        # Update campaign counters
        async with get_tenant_db() as db:
            await db.execute(
                """
                UPDATE sms_campaigns
                SET delivered = delivered + $2, failed = failed - $2, updated_at = NOW()
                WHERE id = $1
                """,
                campaign_id, retried,
            )

        return {"retried": retried, "still_failed": still_failed}
