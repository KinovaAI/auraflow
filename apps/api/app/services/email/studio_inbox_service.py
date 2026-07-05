"""AuraFlow — Per-Tenant Studio Email Inbox Service

Each studio gets their own email inbox connected via IMAP, with AI as
first responder.  Studio-side inbound email handling for
tenant context: credentials are stored inside the tenant schema with
pgcrypto-encrypted passwords, and every query is scoped via
get_tenant_db(schema).

AI classification and response use ANTHROPIC_MODEL_FAST (claude-haiku)
to keep costs low.  Replies are sent through the studio's own SMTP
credentials so threads appear correctly in Gmail / Outlook.
"""
import asyncio
import email as email_stdlib
import imaplib
import json
import re
import uuid
from datetime import datetime, timezone
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr
from typing import Optional

import aiosmtplib

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_tenant_db
from app.services.ai.token_tracking_service import track_ai_usage
from app.services.members.phi_helpers import decrypt_phone
from app.utils.encryption import decrypt_credential, encrypt_credential

# ── Constants ─────────────────────────────────────────────────────────────

MAX_AI_EXCHANGES_PER_THREAD = 3

CLASSIFICATION_VALUES = [
    "booking_inquiry",
    "pricing_question",
    "schedule_question",
    "cancellation",
    "complaint",
    "feedback",
    "general_question",
    "spam",
    "engagement_reply",
]

AI_RESOLVABLE = {
    "booking_inquiry",
    "pricing_question",
    "schedule_question",
    "general_question",
}

STATUS_VALUES = ["new", "ai_resolved", "needs_attention", "in_progress", "resolved", "spam"]


# ── Email-parsing helpers ──────────────────────────────────────────────────

def _decode_header_value(value: str | None) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    decoded = []
    for data, charset in parts:
        if isinstance(data, bytes):
            decoded.append(data.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(data)
    return " ".join(decoded)


def _extract_body(msg: email_stdlib.message.Message) -> tuple[str, str]:
    body_text = ""
    body_html = ""

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in disposition:
                continue
            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                text = payload.decode(charset, errors="replace")
                if content_type == "text/plain" and not body_text:
                    body_text = text
                elif content_type == "text/html" and not body_html:
                    body_html = text
            except Exception:
                continue
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                text = payload.decode(charset, errors="replace")
                if msg.get_content_type() == "text/html":
                    body_html = text
                else:
                    body_text = text
        except Exception:
            pass

    return body_text, body_html


# ── Service ───────────────────────────────────────────────────────────────

class StudioInboxService:

    # ══════════════════════════════════════════════════════════════════════
    #  IMAP / SMTP Account Management
    # ══════════════════════════════════════════════════════════════════════

    async def connect_email_account(self, schema: str, config: dict) -> dict:
        """Store IMAP/SMTP credentials (encrypted) and test the connection. Upserts by email."""
        async with get_tenant_db(schema_override=schema) as db:
            password_enc = await encrypt_credential(db, config["password"])

            # Check if account already exists for this email
            existing = await db.fetchrow(
                "SELECT id FROM studio_email_accounts WHERE email_address = $1",
                config["email_address"],
            )

            if existing:
                # Update existing account
                row = await db.fetchrow("""
                    UPDATE studio_email_accounts SET
                        display_name = $2,
                        imap_host = $3, imap_port = $4, imap_use_tls = $5,
                        smtp_host = $6, smtp_port = $7, smtp_use_tls = $8,
                        username = $9, password_enc = $10, is_active = TRUE
                    WHERE id = $1
                    RETURNING id, email_address, display_name,
                              imap_host, imap_port, smtp_host, smtp_port,
                              is_active, last_checked_at, last_uid, created_at
                """,
                    str(existing["id"]),
                    config.get("display_name", "Studio"),
                    config.get("imap_host", "imap.gmail.com"),
                    config.get("imap_port", 993),
                    config.get("imap_use_tls", True),
                    config.get("smtp_host", "smtp.gmail.com"),
                    config.get("smtp_port", 465),
                    config.get("smtp_use_tls", True),
                    config.get("username", config["email_address"]),
                    password_enc,
                )
            else:
                row = await db.fetchrow("""
                    INSERT INTO studio_email_accounts
                        (email_address, display_name,
                         imap_host, imap_port, imap_use_tls,
                         smtp_host, smtp_port, smtp_use_tls,
                         username, password_enc, is_active)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, TRUE)
                    RETURNING id, email_address, display_name,
                              imap_host, imap_port, smtp_host, smtp_port,
                              is_active, last_checked_at, last_uid, created_at
                """,
                    config["email_address"],
                    config.get("display_name", "Studio"),
                    config.get("imap_host", "imap.gmail.com"),
                    config.get("imap_port", 993),
                    config.get("imap_use_tls", True),
                    config.get("smtp_host", "smtp.gmail.com"),
                    config.get("smtp_port", 465),
                    config.get("smtp_use_tls", True),
                    config.get("username", config["email_address"]),
                    password_enc,
                )
            account = dict(row) if row else {}

        # Test connection asynchronously (don't fail the insert if test fails)
        if account:
            try:
                test_result = await self.test_connection(schema, str(account["id"]))
                account["connection_test"] = test_result
            except Exception as e:
                account["connection_test"] = {"imap": False, "smtp": False, "error": str(e)}

        return account

    async def disconnect_email_account(self, schema: str, account_id: str) -> bool:
        """Deactivate and soft-delete an email account."""
        async with get_tenant_db(schema_override=schema) as db:
            result = await db.execute("""
                UPDATE studio_email_accounts
                SET is_active = FALSE
                WHERE id = $1
            """, account_id)
        return "UPDATE 1" in result

    async def get_account_status(self, schema: str) -> dict:
        """Return the connected account status (first active account)."""
        async with get_tenant_db(schema_override=schema) as db:
            row = await db.fetchrow("""
                SELECT id, email_address, display_name, imap_host, smtp_host,
                       is_active, last_checked_at, last_uid, created_at
                FROM studio_email_accounts
                WHERE is_active = TRUE
                ORDER BY created_at ASC LIMIT 1
            """)
        if not row:
            return {"connected": False}
        return {"connected": True, **dict(row)}

    async def test_connection(self, schema: str, account_id: str) -> dict:
        """Test both IMAP and SMTP connections for a studio email account."""
        account, password = await self._get_credentials(schema, account_id)
        results = {"imap": False, "smtp": False, "imap_error": None, "smtp_error": None}

        # IMAP
        try:
            imap = await asyncio.to_thread(
                self._connect_imap,
                account["imap_host"], account["imap_port"],
                account["imap_use_tls"], account["username"], password,
            )
            await asyncio.to_thread(imap.select, "INBOX")
            await asyncio.to_thread(imap.close)
            await asyncio.to_thread(imap.logout)
            results["imap"] = True
        except Exception as e:
            results["imap_error"] = str(e)

        # SMTP
        try:
            port = account["smtp_port"]
            # Port 465 = implicit SSL (use_tls), Port 587 = STARTTLS (start_tls)
            if port == 465:
                smtp = aiosmtplib.SMTP(
                    hostname=account["smtp_host"], port=port, use_tls=True,
                )
            else:
                smtp = aiosmtplib.SMTP(
                    hostname=account["smtp_host"], port=port, start_tls=True,
                )
            await smtp.connect()
            await smtp.login(account["username"], password)
            await smtp.quit()
            results["smtp"] = True
        except Exception as e:
            results["smtp_error"] = str(e)

        return results

    # ══════════════════════════════════════════════════════════════════════
    #  Email Fetching (IMAP)
    # ══════════════════════════════════════════════════════════════════════

    async def fetch_new_emails(self, schema: str, account_id: str) -> int:
        """Connect to IMAP, fetch new emails since last_uid, store in
        studio_inbox_messages.  Returns number of new emails fetched."""
        account, password = await self._get_credentials(schema, account_id)

        if not account["is_active"]:
            return 0

        last_uid = account.get("last_uid") or 0
        fetched = 0

        try:
            imap = await asyncio.to_thread(
                self._connect_imap,
                account["imap_host"], account["imap_port"],
                account["imap_use_tls"], account["username"], password,
            )
            await asyncio.to_thread(imap.select, "INBOX")

            if last_uid > 0:
                search_criteria = f"(UID {last_uid + 1}:*)"
            else:
                search_criteria = "ALL"

            status, data = await asyncio.to_thread(
                imap.uid, "search", None, search_criteria,
            )

            if status != "OK" or not data[0]:
                await asyncio.to_thread(imap.close)
                await asyncio.to_thread(imap.logout)
                async with get_tenant_db(schema_override=schema) as db:
                    await db.execute(
                        "UPDATE studio_email_accounts SET last_checked_at = NOW() WHERE id = $1",
                        account_id,
                    )
                return 0

            uid_list = data[0].split()

            # First fetch: limit to last 50 messages
            if last_uid == 0 and len(uid_list) > 50:
                uid_list = uid_list[-50:]

            max_uid = last_uid

            for uid_bytes in uid_list:
                uid = int(uid_bytes)
                if uid <= last_uid:
                    continue

                try:
                    st, msg_data = await asyncio.to_thread(
                        imap.uid, "fetch", uid_bytes, "(RFC822)",
                    )
                    if st != "OK" or not msg_data or not msg_data[0]:
                        continue

                    raw_email = msg_data[0][1]
                    if not isinstance(raw_email, bytes):
                        continue
                    msg = email_stdlib.message_from_bytes(raw_email)

                    # Parse headers
                    message_id_header = msg.get("Message-ID", "")
                    in_reply_to = msg.get("In-Reply-To", "")
                    from_name, from_email_addr = parseaddr(msg.get("From", ""))
                    from_name = _decode_header_value(from_name)
                    _, to_email_addr = parseaddr(msg.get("To", ""))
                    subject = _decode_header_value(msg.get("Subject"))
                    body_text, body_html = _extract_body(msg)

                    # Parse date
                    received_at = None
                    date_str = msg.get("Date")
                    if date_str:
                        try:
                            from email.utils import parsedate_to_datetime
                            received_at = parsedate_to_datetime(date_str)
                        except Exception:
                            received_at = datetime.now(timezone.utc)
                    else:
                        received_at = datetime.now(timezone.utc)

                    stored = await self._store_email(
                        schema=schema,
                        account_id=str(account["id"]),
                        message_uid=uid,
                        message_id_header=message_id_header or f"imap-{account_id}-{uid}",
                        in_reply_to=in_reply_to,
                        from_email=from_email_addr,
                        from_name=from_name,
                        to_email=to_email_addr or account["email_address"],
                        subject=subject,
                        body_text=body_text,
                        body_html=body_html,
                        received_at=received_at,
                    )
                    if stored:
                        fetched += 1
                    if uid > max_uid:
                        max_uid = uid

                except Exception as e:
                    logger.error(
                        f"Failed to fetch UID {uid} from {account['email_address']}: {e}"
                    )
                    continue

            await asyncio.to_thread(imap.close)
            await asyncio.to_thread(imap.logout)

            # Update last_uid and last_checked_at
            async with get_tenant_db(schema_override=schema) as db:
                await db.execute("""
                    UPDATE studio_email_accounts
                    SET last_uid = $2, last_checked_at = NOW()
                    WHERE id = $1
                """, account_id, max_uid)

            if fetched:
                logger.info(
                    f"Fetched {fetched} new studio emails from {account['email_address']}",
                    schema=schema,
                )

        except Exception as e:
            logger.error(
                f"IMAP fetch failed for studio {account.get('email_address', account_id)}: {e}",
                schema=schema,
            )
            raise

        return fetched

    async def _store_email(
        self,
        schema: str,
        account_id: str,
        message_uid: int,
        message_id_header: str,
        in_reply_to: str,
        from_email: str,
        from_name: str | None,
        to_email: str,
        subject: str | None,
        body_text: str | None,
        body_html: str | None,
        received_at: datetime | None = None,
    ) -> bool:
        """Store a fetched email in studio_inbox_messages.  Returns True if inserted."""
        async with get_tenant_db(schema_override=schema) as db:
            # Check for duplicate by message_id_header
            row = await db.fetchrow("""
                INSERT INTO studio_inbox_messages
                    (account_id, message_uid, message_id_header, in_reply_to,
                     from_email, from_name, to_email, subject,
                     body_text, body_html, received_at, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, 'new')
                ON CONFLICT (message_id_header) WHERE message_id_header IS NOT NULL
                    DO NOTHING
                RETURNING id
            """,
                account_id, message_uid, message_id_header, in_reply_to,
                from_email, from_name, to_email, subject,
                body_text, body_html, received_at or datetime.now(timezone.utc),
            )

            if row:
                # Try to match to a member by email
                member = await db.fetchrow(
                    "SELECT id FROM members WHERE LOWER(email) = LOWER($1) LIMIT 1",
                    from_email,
                )
                if member:
                    await db.execute(
                        "UPDATE studio_inbox_messages SET member_id = $2 WHERE id = $1",
                        row["id"], member["id"],
                    )

                # Try to match to an engagement campaign
                campaign = await db.fetchrow("""
                    SELECT id FROM engagement_campaigns
                    WHERE member_id IN (SELECT id FROM members WHERE LOWER(email) = LOWER($1))
                      AND status IN ('active', 'follow_up_1', 'follow_up_2', 'replied')
                    ORDER BY created_at DESC LIMIT 1
                """, from_email)
                if campaign:
                    await db.execute(
                        "UPDATE studio_inbox_messages SET engagement_campaign_id = $2 WHERE id = $1",
                        row["id"], campaign["id"],
                    )

        return row is not None

    # ══════════════════════════════════════════════════════════════════════
    #  AI First Responder
    # ══════════════════════════════════════════════════════════════════════

    async def process_new_email(self, schema: str, message_id: str) -> dict:
        """AI classifies and responds to a new studio inbox email.

        1. Classify intent
        2. If engagement_reply -> route to engagement autopilot
        3. If spam -> mark as spam, no response
        4. If AI can handle -> generate response, send via SMTP
        5. If complaint / complex -> mark needs_attention
        """
        # Set tenant context so track_ai_usage can attribute Anthropic spend
        # to this org. Without it the Stripe billing meter never gets the
        # call and we eat the cost ourselves.
        from app.core.tenant_context import (
            set_tenant_context, clear_tenant_context, get_tenant_context,
        )
        ctx_set_here = False
        if not get_tenant_context():
            from app.db.session import get_global_db
            async with get_global_db() as gdb:
                org_row = await gdb.fetchrow(
                    "SELECT id FROM af_global.organizations WHERE schema_name = $1",
                    schema,
                )
            if org_row:
                set_tenant_context(
                    organization_id=str(org_row["id"]),
                    schema_name=schema,
                    slug=schema.replace("af_tenant_", ""),
                )
                ctx_set_here = True

        try:
            return await self._process_new_email_inner(schema, message_id)
        finally:
            if ctx_set_here:
                clear_tenant_context()

    async def _process_new_email_inner(self, schema: str, message_id: str) -> dict:
        async with get_tenant_db(schema_override=schema) as db:
            email_row = await db.fetchrow(
                "SELECT * FROM studio_inbox_messages WHERE id = $1", message_id,
            )
        if not email_row:
            raise ValueError(f"Email {message_id} not found")

        email_data = dict(email_row)

        # ── 1. Classify ─────────────────────────────────────────────────
        classification = await self._classify_email(schema, email_data)

        async with get_tenant_db(schema_override=schema) as db:
            await db.execute(
                "UPDATE studio_inbox_messages SET classification = $2 WHERE id = $1",
                message_id, classification,
            )

        # ── 2. Engagement reply ──────────────────────────────────────────
        if classification == "engagement_reply" and email_data.get("engagement_campaign_id"):
            try:
                from app.services.ai.engagement_autopilot import EngagementAutopilot
                autopilot = EngagementAutopilot()
                body = email_data.get("body_text") or email_data.get("body_html") or ""
                await autopilot.handle_reply(
                    schema,
                    str(email_data["engagement_campaign_id"]),
                    body,
                )
                async with get_tenant_db(schema_override=schema) as db:
                    await db.execute("""
                        UPDATE studio_inbox_messages
                        SET status = 'ai_resolved',
                            ai_response_text = 'Routed to engagement autopilot',
                            ai_response_sent_at = NOW(),
                            updated_at = NOW()
                        WHERE id = $1
                    """, message_id)
                return {"status": "ai_resolved", "classification": classification,
                        "action": "routed_to_engagement"}
            except Exception as e:
                logger.error(f"Engagement route failed: {e}", schema=schema)
                # Fall through to needs_attention

        # ── 3. Spam ──────────────────────────────────────────────────────
        if classification == "spam":
            async with get_tenant_db(schema_override=schema) as db:
                await db.execute("""
                    UPDATE studio_inbox_messages
                    SET status = 'spam', updated_at = NOW()
                    WHERE id = $1
                """, message_id)
            return {"status": "spam", "classification": classification}

        # ── 4. Check thread depth (limit AI to 3 exchanges) ─────────────
        ai_exchange_count = await self._count_ai_exchanges(schema, email_data)
        if ai_exchange_count >= MAX_AI_EXCHANGES_PER_THREAD:
            async with get_tenant_db(schema_override=schema) as db:
                await db.execute("""
                    UPDATE studio_inbox_messages
                    SET status = 'needs_attention', updated_at = NOW()
                    WHERE id = $1
                """, message_id)
            return {"status": "needs_attention", "classification": classification,
                    "reason": "max_ai_exchanges_reached"}

        # ── 5. AI-resolvable ─────────────────────────────────────────────
        if classification in AI_RESOLVABLE:
            studio_ctx = await self._get_studio_context(schema)
            member_ctx = await self._get_member_context(schema, email_data.get("member_id"))
            ai_result = await self._generate_ai_response(
                schema, email_data, classification, studio_ctx, member_ctx,
            )

            if ai_result.get("confidence_score", 0) >= 0.6:
                # Send via SMTP
                try:
                    await self._send_reply(
                        schema,
                        str(email_data["account_id"]),
                        email_data,
                        ai_result["response_html"],
                    )
                    async with get_tenant_db(schema_override=schema) as db:
                        await db.execute("""
                            UPDATE studio_inbox_messages
                            SET status = 'ai_resolved',
                                ai_response_text = $2,
                                ai_response_html = $3,
                                ai_response_sent_at = NOW(),
                                ai_confidence_score = $4,
                                updated_at = NOW()
                            WHERE id = $1
                        """, message_id,
                            ai_result["response_text"],
                            ai_result["response_html"],
                            ai_result["confidence_score"],
                        )

                        # Also store in studio_inbox_replies
                        await db.execute("""
                            INSERT INTO studio_inbox_replies
                                (message_id, reply_by, reply_type, body_text, body_html, sent_at)
                            VALUES ($1, NULL, 'ai', $2, $3, NOW())
                        """, message_id, ai_result["response_text"], ai_result["response_html"])

                    return {"status": "ai_resolved", "classification": classification,
                            "confidence": ai_result["confidence_score"]}
                except Exception as e:
                    logger.error(f"SMTP send failed for AI reply: {e}", schema=schema)
                    # Fall through to needs_attention

            # Low confidence -> flag for human
            async with get_tenant_db(schema_override=schema) as db:
                await db.execute("""
                    UPDATE studio_inbox_messages
                    SET status = 'needs_attention',
                        ai_response_text = $2,
                        ai_response_html = $3,
                        ai_confidence_score = $4,
                        updated_at = NOW()
                    WHERE id = $1
                """, message_id,
                    ai_result.get("response_text"),
                    ai_result.get("response_html"),
                    ai_result.get("confidence_score", 0),
                )
            return {"status": "needs_attention", "classification": classification,
                    "reason": "low_confidence"}

        # ── 6. Complaint / feedback / cancellation / unknown -> human ────
        async with get_tenant_db(schema_override=schema) as db:
            await db.execute("""
                UPDATE studio_inbox_messages
                SET status = 'needs_attention', updated_at = NOW()
                WHERE id = $1
            """, message_id)
        return {"status": "needs_attention", "classification": classification,
                "reason": "requires_human"}

    # ── AI Classification ────────────────────────────────────────────────

    async def _classify_email(self, schema: str, email_data: dict) -> str:
        """Classify the email intent using Claude (fast model)."""
        if not settings.ANTHROPIC_API_KEY:
            return "general_question"

        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        prompt = f"""Classify this incoming studio email into exactly one category.

Categories:
- booking_inquiry: wants to book a class, asks about availability
- pricing_question: asks about membership costs, packages, pricing
- schedule_question: asks about class times, schedule, cancellations of classes
- cancellation: wants to cancel membership or booking
- complaint: unhappy, reporting a problem, negative feedback
- feedback: positive feedback, testimonials, suggestions
- general_question: any other question about the studio
- spam: marketing, unsolicited, not from a real person
- engagement_reply: reply to an outreach/re-engagement email from the studio

From: {email_data.get('from_name', '')} <{email_data['from_email']}>
Subject: {email_data.get('subject', '(no subject)')}

Body:
{(email_data.get('body_text') or email_data.get('body_html') or '(empty)')[:2000]}

Respond with ONLY the category name, nothing else."""

        try:
            response = await client.messages.create(
                model=settings.ANTHROPIC_MODEL_FAST,
                max_tokens=50,
                messages=[{"role": "user", "content": prompt}],
            )
            await track_ai_usage(
                service_name="studio_inbox",
                function_name="classify_email",
                model=settings.ANTHROPIC_MODEL_FAST,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )
            raw = response.content[0].text.strip().lower().replace(" ", "_")
            # Validate
            if raw in CLASSIFICATION_VALUES:
                return raw
            # Fuzzy match
            for cv in CLASSIFICATION_VALUES:
                if cv in raw:
                    return cv
            return "general_question"
        except Exception as e:
            logger.error(f"Email classification failed: {e}", schema=schema)
            return "general_question"

    # ── AI Response Generation ───────────────────────────────────────────

    async def _generate_ai_response(
        self,
        schema: str,
        email_data: dict,
        classification: str,
        studio_context: dict,
        member_context: dict | None = None,
    ) -> dict:
        """Generate a helpful AI response.  Returns
        {response_text, response_html, confidence_score}."""
        if not settings.ANTHROPIC_API_KEY:
            return {"response_text": "", "response_html": "", "confidence_score": 0.0}

        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        studio_name = studio_context.get("studio_name", "our studio")
        studio_info = self._format_studio_context(studio_context)
        member_info = self._format_member_context(member_context) if member_context else ""

        system = f"""You are the helpful email assistant for {studio_name}, a yoga/fitness studio.
You answer incoming emails on behalf of the studio team.

Studio information:
{studio_info}

{f'Member information:{chr(10)}{member_info}' if member_info else ''}

Guidelines:
- Be warm, professional, and helpful
- Answer the question directly using the studio information provided
- If you are not confident you have the right answer, say so and set confidence lower
- Keep responses concise but thorough (2-4 paragraphs max)
- Sign off as "{studio_name} Team"
- Do NOT make up information not provided in the studio context
- For booking inquiries, mention how they can book (online, phone, walk-in)
- For pricing questions, provide the exact prices from the context
- For schedule questions, provide the relevant class times

Respond in JSON format:
{{"response_text": "plain text version", "response_html": "HTML version with basic formatting", "confidence_score": 0.0-1.0}}

The confidence_score should reflect how confident you are that your response fully and correctly addresses the inquiry.  Use 0.9+ if the answer is clearly in the context, 0.7-0.9 for likely correct, below 0.7 if unsure."""

        prompt = f"""Classification: {classification}

From: {email_data.get('from_name', '')} <{email_data['from_email']}>
Subject: {email_data.get('subject', '(no subject)')}

Body:
{(email_data.get('body_text') or email_data.get('body_html') or '(empty)')[:3000]}

Generate a helpful reply."""

        try:
            response = await client.messages.create(
                model=settings.ANTHROPIC_MODEL_FAST,
                max_tokens=1500,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            await track_ai_usage(
                service_name="studio_inbox",
                function_name="generate_response",
                model=settings.ANTHROPIC_MODEL_FAST,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )

            raw = response.content[0].text.strip()
            # Parse JSON from the response
            try:
                # Try to extract JSON even if wrapped in markdown code blocks
                json_match = re.search(r'\{[\s\S]*\}', raw)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    result = json.loads(raw)
            except json.JSONDecodeError:
                result = {
                    "response_text": raw,
                    "response_html": f"<p>{raw}</p>",
                    "confidence_score": 0.5,
                }

            # Ensure all fields present
            result.setdefault("response_text", "")
            result.setdefault("response_html", f"<p>{result.get('response_text', '')}</p>")
            result.setdefault("confidence_score", 0.5)

            return result

        except Exception as e:
            logger.error(f"AI response generation failed: {e}", schema=schema)
            return {"response_text": "", "response_html": "", "confidence_score": 0.0}

    # ── SMTP Reply ───────────────────────────────────────────────────────

    async def _send_reply(
        self,
        schema: str,
        account_id: str,
        original_email: dict,
        response_html: str,
    ) -> bool:
        """Send a reply via the studio's own SMTP credentials.
        Sets In-Reply-To and References headers for proper threading."""
        account, password = await self._get_credentials(schema, account_id)
        studio_ctx = await self._get_studio_context(schema)
        studio_name = studio_ctx.get("studio_name", "Studio")

        subject = original_email.get("subject") or "Your inquiry"
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        msg = MIMEMultipart("alternative")
        msg["From"] = f"{account.get('display_name', studio_name)} <{account['email_address']}>"
        msg["To"] = original_email["from_email"]
        msg["Subject"] = subject
        msg["Reply-To"] = account["email_address"]

        # Threading headers
        original_msg_id = original_email.get("message_id_header", "")
        if original_msg_id:
            msg["In-Reply-To"] = original_msg_id
            msg["References"] = original_msg_id

        # Wrap HTML in a styled container
        html_body = f"""
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto;">
    {response_html}
    <br><br>
    <p style="color: #6b7280; font-size: 13px;">
        &mdash; {studio_name} Team
    </p>
</div>
"""
        # Plain text fallback
        import re as _re
        plain_text = _re.sub(r'<[^>]+>', '', response_html)

        msg.attach(MIMEText(plain_text, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        try:
            smtp = aiosmtplib.SMTP(
                hostname=account["smtp_host"],
                port=account["smtp_port"],
                use_tls=account["smtp_use_tls"],
            )
            await smtp.connect()
            await smtp.login(account["username"], password)
            await smtp.send_message(msg)
            await smtp.quit()
            logger.info(
                f"Studio SMTP sent to {original_email['from_email']} "
                f"from {account['email_address']}",
                schema=schema,
            )
            return True
        except Exception as e:
            logger.error(f"Studio SMTP send failed: {e}", schema=schema)
            raise

    # ══════════════════════════════════════════════════════════════════════
    #  Email Management
    # ══════════════════════════════════════════════════════════════════════

    async def list_emails(
        self,
        schema: str,
        status: Optional[str] = None,
        classification: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """List inbox messages with optional filters."""
        async with get_tenant_db(schema_override=schema) as db:
            conditions = []
            params: list = []
            idx = 1

            if status:
                conditions.append(f"m.status = ${idx}")
                params.append(status)
                idx += 1
            if classification:
                conditions.append(f"m.classification = ${idx}")
                params.append(classification)
                idx += 1

            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            params.extend([limit, offset])

            rows = await db.fetch(f"""
                SELECT m.*,
                       a.email_address AS account_email,
                       a.display_name AS account_display_name,
                       mem.first_name AS member_first_name,
                       mem.last_name AS member_last_name
                FROM studio_inbox_messages m
                LEFT JOIN studio_email_accounts a ON a.id = m.account_id
                LEFT JOIN members mem ON mem.id = m.member_id
                {where}
                ORDER BY m.received_at DESC
                LIMIT ${idx} OFFSET ${idx + 1}
            """, *params)
            return [dict(r) for r in rows]

    async def get_email(self, schema: str, message_id: str) -> dict | None:
        """Get email detail with full thread (replies)."""
        async with get_tenant_db(schema_override=schema) as db:
            row = await db.fetchrow("""
                SELECT m.*,
                       a.email_address AS account_email,
                       a.display_name AS account_display_name,
                       mem.first_name AS member_first_name,
                       mem.last_name AS member_last_name,
                       mem.email AS member_email
                FROM studio_inbox_messages m
                LEFT JOIN studio_email_accounts a ON a.id = m.account_id
                LEFT JOIN members mem ON mem.id = m.member_id
                WHERE m.id = $1
            """, message_id)

            if not row:
                return None

            email_dict = dict(row)

            # Fetch replies (AI and manual)
            replies = await db.fetch("""
                SELECT r.*, u.first_name AS reply_by_name
                FROM studio_inbox_replies r
                LEFT JOIN af_global.users u ON u.id = r.reply_by
                WHERE r.message_id = $1
                ORDER BY r.created_at ASC
            """, message_id)
            email_dict["replies"] = [dict(r) for r in replies]

            # Fetch related thread messages (by from_email or in_reply_to chain)
            thread = await db.fetch("""
                SELECT id, subject, from_email, status, received_at, classification
                FROM studio_inbox_messages
                WHERE from_email = $1 AND id != $2
                ORDER BY received_at DESC LIMIT 10
            """, email_dict["from_email"], message_id)
            email_dict["thread_history"] = [dict(t) for t in thread]

        return email_dict

    async def mark_as_resolved(self, schema: str, message_id: str, resolved_by: str) -> dict:
        """Team member marks an email as resolved."""
        async with get_tenant_db(schema_override=schema) as db:
            row = await db.fetchrow("""
                UPDATE studio_inbox_messages
                SET status = 'resolved', resolved_by = $2, resolved_at = NOW(), updated_at = NOW()
                WHERE id = $1
                RETURNING *
            """, message_id, resolved_by)
        return dict(row) if row else {}

    async def send_manual_reply(
        self, schema: str, message_id: str, reply_text: str, reply_by: str,
    ) -> dict:
        """Team member sends a manual reply via the studio's SMTP."""
        async with get_tenant_db(schema_override=schema) as db:
            email_row = await db.fetchrow(
                "SELECT * FROM studio_inbox_messages WHERE id = $1", message_id,
            )
        if not email_row:
            raise ValueError("Email not found")

        email_data = dict(email_row)

        # Send via SMTP
        reply_html = f"<p>{reply_text.replace(chr(10), '<br>')}</p>"
        await self._send_reply(
            schema, str(email_data["account_id"]), email_data, reply_html,
        )

        # Store reply
        async with get_tenant_db(schema_override=schema) as db:
            await db.execute("""
                INSERT INTO studio_inbox_replies
                    (message_id, reply_by, reply_type, body_text, body_html, sent_at)
                VALUES ($1, $2, 'manual', $3, $4, NOW())
            """, message_id, reply_by, reply_text, reply_html)

            # Update message status
            row = await db.fetchrow("""
                UPDATE studio_inbox_messages
                SET status = 'resolved', resolved_by = $2, resolved_at = NOW(), updated_at = NOW()
                WHERE id = $1
                RETURNING *
            """, message_id, reply_by)

        return dict(row) if row else {}

    async def reassign_email(
        self, schema: str, message_id: str, assigned_to: str,
    ) -> dict:
        """Assign an email to a specific team member."""
        async with get_tenant_db(schema_override=schema) as db:
            row = await db.fetchrow("""
                UPDATE studio_inbox_messages
                SET assigned_to = $2, status = 'in_progress', updated_at = NOW()
                WHERE id = $1
                RETURNING *
            """, message_id, assigned_to)
        return dict(row) if row else {}

    async def get_stats(self, schema: str) -> dict:
        """Unread count, AI resolved count, needs attention count, etc."""
        async with get_tenant_db(schema_override=schema) as db:
            stats = await db.fetchrow("""
                SELECT
                    COUNT(*) FILTER (WHERE status = 'new') AS unread_count,
                    COUNT(*) FILTER (WHERE status = 'ai_resolved') AS ai_resolved_count,
                    COUNT(*) FILTER (WHERE status = 'needs_attention') AS needs_attention_count,
                    COUNT(*) FILTER (WHERE status = 'in_progress') AS in_progress_count,
                    COUNT(*) FILTER (WHERE status = 'resolved') AS resolved_count,
                    COUNT(*) FILTER (WHERE status = 'spam') AS spam_count,
                    COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '7 days') AS total_this_week,
                    COUNT(*) FILTER (WHERE status = 'ai_resolved' AND created_at >= NOW() - INTERVAL '7 days') AS ai_resolved_this_week
                FROM studio_inbox_messages
            """)
        return dict(stats) if stats else {}

    # ══════════════════════════════════════════════════════════════════════
    #  Studio Context for AI
    # ══════════════════════════════════════════════════════════════════════

    async def _get_studio_context(self, schema: str) -> dict:
        """Fetch studio name, address, phone, upcoming classes, membership
        types with prices. Gives AI enough context to answer common Qs."""
        context: dict = {
            "studio_name": "Studio",
            "address": "",
            "phone": "",
            "email": "",
            "upcoming_classes": [],
            "membership_types": [],
        }

        async with get_tenant_db(schema_override=schema) as db:
            # Studio info from organization settings or studios table
            studio = await db.fetchrow("""
                SELECT name, address_line1, address_line2, city, state, zip_code,
                       phone, email
                FROM studios
                ORDER BY is_primary DESC NULLS LAST, created_at ASC
                LIMIT 1
            """)
            if studio:
                s = dict(studio)
                context["studio_name"] = s.get("name") or "Studio"
                addr_parts = [s.get("address_line1", "")]
                if s.get("address_line2"):
                    addr_parts.append(s["address_line2"])
                addr_parts.extend([
                    s.get("city", ""), s.get("state", ""), s.get("zip_code", ""),
                ])
                context["address"] = ", ".join(p for p in addr_parts if p)
                context["phone"] = s.get("phone", "")
                context["email"] = s.get("email", "")

            # Upcoming classes (next 7 days)
            classes = await db.fetch("""
                SELECT cs.name AS class_name,
                       cs.start_time,
                       cs.end_time,
                       cs.day_of_week,
                       i.first_name || ' ' || i.last_name AS instructor_name,
                       cs.capacity,
                       cs.spots_remaining
                FROM class_schedules cs
                LEFT JOIN instructors i ON i.id = cs.instructor_id
                WHERE cs.is_active = TRUE
                ORDER BY cs.day_of_week, cs.start_time
                LIMIT 30
            """)
            context["upcoming_classes"] = [dict(c) for c in classes]

            # Membership types with prices
            memberships = await db.fetch("""
                SELECT name, description, price, billing_interval,
                       class_credits, is_unlimited
                FROM membership_types
                WHERE is_active = TRUE
                ORDER BY price ASC
            """)
            context["membership_types"] = [dict(m) for m in memberships]

        return context

    async def _get_member_context(self, schema: str, member_id: str | None) -> dict | None:
        """If email is from a known member, get their membership + booking history."""
        if not member_id:
            return None

        async with get_tenant_db(schema_override=schema) as db:
            member = await db.fetchrow("""
                SELECT m.first_name, m.last_name, m.email, m.phone_enc,
                       m.status, m.created_at,
                       mt.name AS membership_name,
                       mm.start_date AS membership_start,
                       mm.end_date AS membership_end,
                       mm.status AS membership_status
                FROM members m
                LEFT JOIN member_memberships mm ON mm.member_id = m.id AND mm.status = 'active'
                LEFT JOIN membership_types mt ON mt.id = mm.membership_type_id
                WHERE m.id = $1
            """, member_id)

            if not member:
                return None

            ctx = dict(member)
            ctx["phone"] = decrypt_phone(ctx)
            ctx.pop("phone_enc", None)

            # Recent bookings
            bookings = await db.fetch("""
                SELECT cs.name AS class_name, b.class_date, b.status
                FROM bookings b
                LEFT JOIN class_schedules cs ON cs.id = b.class_schedule_id
                WHERE b.member_id = $1
                ORDER BY b.class_date DESC
                LIMIT 5
            """, member_id)
            ctx["recent_bookings"] = [dict(b) for b in bookings]

        return ctx

    # ══════════════════════════════════════════════════════════════════════
    #  Internal Helpers
    # ══════════════════════════════════════════════════════════════════════

    async def _get_credentials(self, schema: str, account_id: str) -> tuple[dict, str]:
        """Get account info + decrypted password."""
        async with get_tenant_db(schema_override=schema) as db:
            row = await db.fetchrow(
                "SELECT * FROM studio_email_accounts WHERE id = $1", account_id,
            )
            if not row:
                raise ValueError(f"Studio email account {account_id} not found")
            password = await decrypt_credential(db, row["password_enc"])
        return dict(row), password

    def _connect_imap(
        self, host: str, port: int, use_tls: bool, username: str, password: str,
    ) -> imaplib.IMAP4_SSL | imaplib.IMAP4:
        """Create and authenticate an IMAP connection (blocking)."""
        if use_tls:
            imap = imaplib.IMAP4_SSL(host, port)
        else:
            imap = imaplib.IMAP4(host, port)
        imap.login(username, password)
        return imap

    async def _count_ai_exchanges(self, schema: str, email_data: dict) -> int:
        """Count how many AI replies have been sent to this thread /
        from_email so we can cap at MAX_AI_EXCHANGES_PER_THREAD."""
        async with get_tenant_db(schema_override=schema) as db:
            row = await db.fetchrow("""
                SELECT COUNT(*) AS cnt
                FROM studio_inbox_replies r
                JOIN studio_inbox_messages m ON m.id = r.message_id
                WHERE m.from_email = $1
                  AND r.reply_type = 'ai'
            """, email_data["from_email"])
        return row["cnt"] if row else 0

    def _format_studio_context(self, ctx: dict) -> str:
        """Format studio context into a readable string for the AI prompt."""
        lines = []
        lines.append(f"Studio Name: {ctx.get('studio_name', 'Studio')}")
        if ctx.get("address"):
            lines.append(f"Address: {ctx['address']}")
        if ctx.get("phone"):
            lines.append(f"Phone: {ctx['phone']}")
        if ctx.get("email"):
            lines.append(f"Email: {ctx['email']}")

        if ctx.get("membership_types"):
            lines.append("\nMembership Options:")
            for mt in ctx["membership_types"]:
                price = mt.get("price", "N/A")
                interval = mt.get("billing_interval", "month")
                name = mt.get("name", "Membership")
                desc = mt.get("description", "")
                unlimited = " (unlimited classes)" if mt.get("is_unlimited") else ""
                credits = f" ({mt['class_credits']} classes)" if mt.get("class_credits") else ""
                lines.append(f"  - {name}: ${price}/{interval}{unlimited}{credits}")
                if desc:
                    lines.append(f"    {desc}")

        if ctx.get("upcoming_classes"):
            lines.append("\nClass Schedule:")
            days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            for c in ctx["upcoming_classes"]:
                dow = days[c["day_of_week"]] if isinstance(c.get("day_of_week"), int) and 0 <= c["day_of_week"] < 7 else str(c.get("day_of_week", ""))
                start = c.get("start_time", "")
                instructor = c.get("instructor_name", "")
                name = c.get("class_name", "Class")
                lines.append(f"  - {dow} {start}: {name} with {instructor}")

        return "\n".join(lines)

    def _format_member_context(self, ctx: dict) -> str:
        """Format member context for the AI prompt."""
        if not ctx:
            return ""
        lines = []
        lines.append(f"Name: {ctx.get('first_name', '')} {ctx.get('last_name', '')}")
        lines.append(f"Status: {ctx.get('status', 'unknown')}")
        if ctx.get("membership_name"):
            lines.append(f"Current Membership: {ctx['membership_name']} ({ctx.get('membership_status', 'unknown')})")
        if ctx.get("recent_bookings"):
            lines.append("Recent Bookings:")
            for b in ctx["recent_bookings"]:
                lines.append(f"  - {b.get('class_name', 'Class')} on {b.get('class_date', 'N/A')} ({b.get('status', '')})")
        return "\n".join(lines)

    # ── Active accounts across all tenants (for polling task) ────────────

    @staticmethod
    async def get_all_active_accounts() -> list[dict]:
        """Return all tenant schemas that have active studio email accounts,
        with their account IDs.  Used by the polling Celery task."""
        from app.db.session import get_global_db
        async with get_global_db() as db:
            schemas = await db.fetch(
                "SELECT schema_name FROM af_global.organizations WHERE status IN ('active', 'trial')"
            )

        results = []
        for row in schemas:
            schema = row["schema_name"]
            try:
                async with get_tenant_db(schema_override=schema) as db:
                    accounts = await db.fetch("""
                        SELECT id FROM studio_email_accounts
                        WHERE is_active = TRUE
                    """)
                    for acc in accounts:
                        results.append({
                            "schema": schema,
                            "account_id": str(acc["id"]),
                        })
            except Exception:
                # Table may not exist yet for this tenant
                continue

        return results
