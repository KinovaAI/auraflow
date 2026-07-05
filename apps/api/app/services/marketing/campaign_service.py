"""AuraFlow — Campaign & SMS Service

Email campaign management, audience resolution, and SMS messaging.
"""
import asyncio
import uuid
from datetime import datetime, timezone

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_tenant_db
from app.services.email.email_service import EmailService


email_svc = EmailService()

_EMAIL_CAMPAIGN_UPDATE_COLS = {
    "name", "subject", "html_content", "audience_filter", "scheduled_at",
}


class CampaignService:

    # ── Campaign CRUD ─────────────────────────────────────────────────────

    async def create_campaign(self, data: dict) -> dict:
        campaign_id = str(uuid.uuid4())
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                INSERT INTO email_campaigns
                    (id, name, subject, html_content, audience_filter, created_by)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING *
                """,
                campaign_id, data["name"], data["subject"],
                data.get("html_content"), data.get("audience_filter", "{}"),
                data.get("created_by"),
            )
            logger.info("Campaign created", campaign_id=campaign_id, name=data["name"])
            return dict(row)

    async def get_campaign(self, campaign_id: str) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow("SELECT * FROM email_campaigns WHERE id = $1", campaign_id)
            return dict(row) if row else None

    async def list_campaigns(self, status: str | None = None) -> list[dict]:
        async with get_tenant_db() as db:
            if status:
                rows = await db.fetch(
                    "SELECT * FROM email_campaigns WHERE status = $1 ORDER BY created_at DESC", status
                )
            else:
                rows = await db.fetch("SELECT * FROM email_campaigns ORDER BY created_at DESC")
            return [dict(r) for r in rows]

    async def update_campaign(self, campaign_id: str, data: dict) -> dict | None:
        data = {k: v for k, v in data.items() if k in _EMAIL_CAMPAIGN_UPDATE_COLS}
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
            query = f"UPDATE email_campaigns SET {', '.join(sets)} WHERE id = ${idx} AND status = 'draft' RETURNING *"
            row = await db.fetchrow(query, *params)
            return dict(row) if row else None

    async def delete_campaign(self, campaign_id: str) -> bool:
        async with get_tenant_db() as db:
            result = await db.execute(
                "DELETE FROM email_campaigns WHERE id = $1 AND status = 'draft'", campaign_id
            )
            return "DELETE 1" in result

    # ── Audience ──────────────────────────────────────────────────────────

    async def preview_audience(self, audience_filter: dict) -> dict:
        """Resolve member count matching a filter."""
        async with get_tenant_db() as db:
            conditions = ["is_active = TRUE", "email IS NOT NULL"]
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

    async def _resolve_audience(self, audience_filter: dict) -> list[dict]:
        """Get members matching the filter."""
        async with get_tenant_db() as db:
            conditions = ["is_active = TRUE", "email IS NOT NULL"]
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
            rows = await db.fetch(f"SELECT id, email, first_name FROM members WHERE {where}", *params)
            return [dict(r) for r in rows]

    # ── Send Campaign ─────────────────────────────────────────────────────

    async def send_campaign(self, campaign_id: str) -> dict:
        """Send a campaign to its resolved audience."""
        campaign = await self.get_campaign(campaign_id)
        if not campaign:
            raise ValueError("Campaign not found")
        if campaign["status"] not in ("draft", "scheduled"):
            raise ValueError(f"Cannot send campaign in '{campaign['status']}' status")

        import json
        audience_filter = campaign.get("audience_filter") or {}
        if isinstance(audience_filter, str):
            audience_filter = json.loads(audience_filter)

        members = await self._resolve_audience(audience_filter)

        async with get_tenant_db() as db:
            # Mark as sending
            await db.execute(
                "UPDATE email_campaigns SET status = 'sending', recipients = $2, updated_at = NOW() WHERE id = $1",
                campaign_id, len(members),
            )

            sent = 0
            for member in members:
                send_id = str(uuid.uuid4())
                try:
                    result = await email_svc.send_email(
                        to_email=member["email"],
                        subject=campaign["subject"],
                        html_content=campaign.get("html_content") or "",
                        member_id=str(member["id"]),
                        email_type="campaign",
                    )
                    status = "sent"
                    sent += 1
                except Exception as e:
                    status = "failed"
                    logger.error("Campaign send failed", member_email=member["email"], error=str(e))

                await db.fetchrow(
                    """
                    INSERT INTO email_campaign_sends
                        (id, campaign_id, member_id, email, status)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING *
                    """,
                    send_id, campaign_id, str(member["id"]), member["email"], status,
                )

            # Mark as sent
            await db.execute(
                "UPDATE email_campaigns SET status = 'sent', sent_at = NOW(), delivered = $2, updated_at = NOW() WHERE id = $1",
                campaign_id, sent,
            )

        logger.info("Campaign sent", campaign_id=campaign_id, recipients=len(members), delivered=sent)
        return {"sent": sent, "total": len(members)}

    # ── Campaign Stats ────────────────────────────────────────────────────

    async def get_campaign_stats(self, campaign_id: str) -> dict:
        async with get_tenant_db() as db:
            campaign = await db.fetchrow("SELECT * FROM email_campaigns WHERE id = $1", campaign_id)
            if not campaign:
                return {}

            stats = await db.fetchrow(
                """
                SELECT
                    COUNT(*) AS total_sends,
                    COUNT(*) FILTER (WHERE status = 'sent') AS sent,
                    COUNT(*) FILTER (WHERE status = 'delivered') AS delivered,
                    COUNT(*) FILTER (WHERE status = 'opened') AS opened,
                    COUNT(*) FILTER (WHERE status = 'clicked') AS clicked,
                    COUNT(*) FILTER (WHERE status = 'bounced') AS bounced,
                    COUNT(*) FILTER (WHERE status = 'failed') AS failed
                FROM email_campaign_sends WHERE campaign_id = $1
                """,
                campaign_id,
            )
            return {**dict(campaign), "send_stats": dict(stats) if stats else {}}


class SmsService:

    async def send_sms(self, to_phone: str, body: str, member_id: str | None = None,
                       sms_type: str = "transactional") -> dict:
        """Send an SMS via Twilio and log it."""
        sms_id = str(uuid.uuid4())
        twilio_sid = None
        status = "sent"
        error_message = None

        if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN:
            try:
                from twilio.rest import Client
                from app.services.sms.sms_service import _normalize_phone, TWILIO_MESSAGING_SERVICE_SID
                from app.core.circuit_breakers import twilio_breaker
                client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
                to_phone = _normalize_phone(to_phone)
                # Build status callback URL for delivery tracking
                status_callback = f"{settings.API_URL}/webhooks/twilio/status"

                async def _do_send():
                    return await asyncio.to_thread(
                        lambda: client.messages.create(
                            body=body,
                            messaging_service_sid=TWILIO_MESSAGING_SERVICE_SID,
                            to=to_phone,
                            status_callback=status_callback,
                        )
                    )
                message = await twilio_breaker.call_async(_do_send)
                twilio_sid = message.sid
            except Exception as e:
                status = "failed"
                error_message = str(e)
                logger.error("SMS send failed", to=to_phone, error=str(e))
        else:
            status = "sent"  # Mock/skip if not configured
            logger.info("SMS skipped (Twilio not configured)", to=to_phone)

        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                INSERT INTO sms_messages
                    (id, member_id, to_phone, body, type, status, twilio_sid, error_message)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING *
                """,
                sms_id, member_id, to_phone, body, sms_type, status, twilio_sid, error_message,
            )
            # Also log to communication_log
            await db.execute(
                """
                INSERT INTO communication_log
                    (id, member_id, channel, type, recipient, body_preview, provider_id, status)
                VALUES ($1, $2, 'sms', $3, $4, $5, $6, $7)
                """,
                str(uuid.uuid4()), member_id, sms_type, to_phone,
                body[:200], twilio_sid, status,
            )
            return dict(row)

    # ── Convenience Methods ───────────────────────────────────────────────────

    async def send_booking_confirmation(
        self,
        member_id: str,
        to_phone: str,
        member_name: str,
        class_title: str,
        session_date: str,
        session_time: str,
    ) -> dict:
        body = (
            f"Hi {member_name}! You're booked for {class_title} "
            f"on {session_date} at {session_time}. See you there!"
        )
        return await self.send_sms(to_phone, body, member_id, "booking_confirmation")

    async def send_booking_cancellation(
        self,
        member_id: str,
        to_phone: str,
        member_name: str,
        class_title: str,
        session_date: str,
    ) -> dict:
        body = (
            f"Hi {member_name}, your booking for {class_title} "
            f"on {session_date} has been cancelled."
        )
        return await self.send_sms(to_phone, body, member_id, "booking_cancellation")

    async def send_waitlist_promotion(
        self,
        member_id: str,
        to_phone: str,
        member_name: str,
        class_title: str,
        session_date: str,
        session_time: str,
    ) -> dict:
        body = (
            f"Great news {member_name}! A spot opened up in {class_title} "
            f"on {session_date} at {session_time}. You're confirmed!"
        )
        return await self.send_sms(to_phone, body, member_id, "waitlist_promotion")

    async def send_class_reminder(
        self,
        member_id: str,
        to_phone: str,
        member_name: str,
        class_title: str,
        session_time: str,
    ) -> dict:
        body = (
            f"Reminder: {member_name}, your {class_title} class "
            f"starts at {session_time} today. See you soon!"
        )
        return await self.send_sms(to_phone, body, member_id, "reminder")

    async def send_payment_failed(
        self,
        member_id: str,
        to_phone: str,
        member_name: str,
        amount_display: str,
    ) -> dict:
        body = (
            f"Hi {member_name}, your payment of {amount_display} "
            f"could not be processed. Please update your payment method."
        )
        return await self.send_sms(to_phone, body, member_id, "payment_failed")

    async def list_sms(self, member_id: str | None = None, limit: int = 50) -> list[dict]:
        async with get_tenant_db() as db:
            if member_id:
                rows = await db.fetch(
                    "SELECT * FROM sms_messages WHERE member_id = $1 ORDER BY created_at DESC LIMIT $2",
                    member_id, limit,
                )
            else:
                rows = await db.fetch(
                    "SELECT * FROM sms_messages ORDER BY created_at DESC LIMIT $1", limit,
                )
            return [dict(r) for r in rows]
