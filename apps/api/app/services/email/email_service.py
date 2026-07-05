"""AuraFlow — Email Service

SendGrid transactional email sending with communication log tracking.
Gracefully degrades when SendGrid is not configured.
CAN-SPAM compliant: includes List-Unsubscribe headers and physical address footer.
"""
import asyncio
import hashlib
import hmac
import uuid
from datetime import datetime
from typing import Optional

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_tenant_db

# ── CAN-SPAM email types that require unsubscribe headers ─────────────────
_MARKETING_EMAIL_TYPES = {
    "marketing", "campaign", "newsletter", "promotion",
    "welcome_sequence", "milestone", "churn_prevention",
    "membership_welcome", "waitlist_promotion", "post_class",
    "no_show_followup", "reminder", "engagement_autopilot",
}


def generate_unsubscribe_token(member_id: str) -> str:
    """Generate an HMAC-SHA256 token for one-click unsubscribe links."""
    return hmac.new(
        settings.APP_SECRET.encode(),
        member_id.encode(),
        hashlib.sha256,
    ).hexdigest()


def verify_unsubscribe_token(member_id: str, token: str) -> bool:
    """Verify an HMAC unsubscribe token (constant-time comparison)."""
    expected = generate_unsubscribe_token(member_id)
    return hmac.compare_digest(expected, token)


def _build_unsubscribe_url(member_id: str) -> str:
    token = generate_unsubscribe_token(member_id)
    base = settings.API_URL.rstrip("/")
    return f"{base}/api/v1/email/unsubscribe/{member_id}/{token}"


def _append_canspam_footer(html_content: str, member_id: Optional[str] = None) -> str:
    """Append CAN-SPAM required physical address, website link, and unsubscribe to HTML."""
    # Try to get org-specific info from tenant context
    org_name = getattr(settings, "PLATFORM_NAME", "AuraFlow")
    org_address = getattr(settings, "ORG_ADDRESS", None) or "Address on file"
    org_website = ""

    try:
        from app.core.tenant_context import get_tenant_context
        ctx = get_tenant_context()
        if ctx and ctx.organization_id:
            import asyncio
            async def _get_org_info():
                from app.db.session import get_global_db
                async with get_global_db() as db:
                    row = await db.fetchrow(
                        "SELECT name, website_url, address FROM af_global.organizations WHERE id = $1",
                        ctx.organization_id,
                    )
                    return row
            try:
                loop = asyncio.get_running_loop()
                # Can't await in sync context — use cached values or skip
            except RuntimeError:
                row = asyncio.run(_get_org_info())
                if row:
                    org_name = row.get("name") or org_name
                    if row.get("address"):
                        org_address = row["address"]
                    if row.get("website_url"):
                        org_website = row["website_url"]
    except Exception:
        pass

    unsubscribe_line = ""
    if member_id:
        unsub_url = _build_unsubscribe_url(member_id)
        unsubscribe_line = (
            f'<a href="{unsub_url}" style="color:#999;text-decoration:underline;">'
            f"Unsubscribe</a> | "
        )

    website_line = ""
    if org_website:
        website_line = f'<a href="{org_website}" style="color:#999;text-decoration:underline;">{org_website}</a> | '

    footer = (
        f'<div style="margin-top:32px;padding-top:16px;border-top:1px solid #eee;'
        f'font-size:11px;color:#999;text-align:center;">'
        f"{unsubscribe_line}"
        f"{website_line}"
        f"{org_name} | {org_address}"
        f"</div>"
    )

    # Insert before closing </body> if present, otherwise append
    if "</body>" in html_content.lower():
        idx = html_content.lower().rfind("</body>")
        return html_content[:idx] + footer + html_content[idx:]
    return html_content + footer


class EmailService:

    async def _get_credentials(self) -> tuple[Optional[str], str, str]:
        """Resolve email credentials: tenant org first, then platform config, then env vars.

        Priority:
        1. Studio's own SMTP inbox (Purelymail etc.) — preferred, no daily limits
        2. Studio's own SendGrid credentials — fallback if SMTP not configured
        3. Platform-level SendGrid config (af_global.platform_config)
        4. Environment variables (SENDGRID_API_KEY / SMTP fallback)
        """
        try:
            from app.core.tenant_context import get_tenant_context
            from app.db.session import get_global_db
            from app.utils.encryption import decrypt_credential
            ctx = get_tenant_context()
            if ctx:
                # Look up org info
                async with get_global_db() as db:
                    row = await db.fetchrow(
                        """
                        SELECT sendgrid_api_key_encrypted, sendgrid_from_email, sendgrid_from_name, name
                        FROM af_global.organizations WHERE id = $1
                        """,
                        ctx.organization_id,
                    )
                    if not row and ctx.schema_name:
                        row = await db.fetchrow(
                            """
                            SELECT sendgrid_api_key_encrypted, sendgrid_from_email, sendgrid_from_name, name
                            FROM af_global.organizations WHERE schema_name = $1
                            """,
                            ctx.schema_name,
                        )

                # 1. Try studio's own SMTP inbox first (no daily limits)
                if ctx.schema_name:
                    from app.db.session import get_tenant_db
                    async with get_tenant_db(schema_override=ctx.schema_name) as tdb:
                        inbox = await tdb.fetchrow(
                            "SELECT email_address, display_name, smtp_host, smtp_port, smtp_use_tls, username, password_enc FROM studio_email_accounts WHERE is_active = TRUE LIMIT 1"
                        )
                    if inbox and inbox["smtp_host"]:
                        org_name = inbox["display_name"] or (row["name"] if row else "Studio")
                        self._use_smtp = True
                        self._smtp_config = {
                            "host": inbox["smtp_host"],
                            "port": inbox["smtp_port"],
                            "use_tls": inbox["smtp_use_tls"],
                            "username": inbox["username"],
                            "password_enc": inbox["password_enc"],
                            "from_email": inbox["email_address"],
                            "from_name": org_name,
                        }
                        # Also stash org's SendGrid key as fallback if SMTP fails
                        if row and row["sendgrid_api_key_encrypted"]:
                            async with get_global_db() as db:
                                self._sendgrid_fallback_key = await decrypt_credential(db, row["sendgrid_api_key_encrypted"])
                            self._sendgrid_fallback_from = row["sendgrid_from_email"] or inbox["email_address"]
                            self._sendgrid_fallback_name = row["sendgrid_from_name"] or org_name
                        return None, inbox["email_address"], org_name

                # 2. Studio's own SendGrid (if no SMTP configured)
                if row and row["sendgrid_api_key_encrypted"]:
                    async with get_global_db() as db:
                        key = await decrypt_credential(db, row["sendgrid_api_key_encrypted"])
                    from_email = row["sendgrid_from_email"] or settings.SENDGRID_FROM_EMAIL
                    from_name = row["sendgrid_from_name"] or row["name"] or settings.SENDGRID_FROM_NAME
                    return key, from_email, from_name
        except Exception:
            pass

        # If we're in a tenant context, NEVER fall back to platform email.
        # Studio email failure is the studio's problem — not AuraFlow's to fix
        # by sending from AuraFlow's own email accounts. Log at error level
        # (not warning) with structured org context so ops alerts can fire
        # — booking confirmations / cancellations silently disappearing has
        # been a real source of customer complaints.
        try:
            from app.core.tenant_context import get_tenant_context
            ctx = get_tenant_context()
            if ctx:
                logger.error(
                    "Studio email not configured — message dropped",
                    organization_id=ctx.organization_id,
                    schema_name=ctx.schema_name,
                    slug=ctx.slug,
                )
                return None, "", ""
        except Exception:
            pass

        # Platform-level only (no tenant context = platform admin emails, support, etc.)
        try:
            from app.services.platform.platform_config_service import PlatformConfigService
            svc = PlatformConfigService()
            key = await svc.get_raw_sendgrid_api_key()
            from_email, from_name = await svc.get_raw_sendgrid_from()
            return key, from_email, from_name
        except Exception:
            pass

        return settings.SENDGRID_API_KEY, settings.SENDGRID_FROM_EMAIL, settings.SENDGRID_FROM_NAME

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        member_id: Optional[str] = None,
        email_type: str = "transactional",
        plain_content: Optional[str] = None,
        attachments: Optional[list[dict]] = None,
    ) -> dict:
        """
        Send an email via SendGrid and log it.
        Returns the log entry. If SendGrid is not configured, logs as 'skipped'.
        """
        provider_id = None
        status = "sent"

        self._is_tenant_email = False
        self._use_smtp = False
        api_key, from_email, from_name = await self._get_credentials()
        # If we found a studio SMTP, this is a tenant email
        if getattr(self, '_use_smtp', False):
            self._is_tenant_email = True

        # ── CAN-SPAM: append physical-address footer to all emails ────
        html_content = _append_canspam_footer(html_content, member_id)

        # ── CAN-SPAM: build unsubscribe headers for marketing emails ──
        is_marketing = email_type in _MARKETING_EMAIL_TYPES
        unsub_url = _build_unsubscribe_url(member_id) if (is_marketing and member_id) else None

        # Send via studio SMTP if configured. Wrapped in
        # purelymail_smtp_breaker: 10-failure threshold + 120s reset so
        # a flap doesn't trip it, but a sustained outage stops the bleed.
        if getattr(self, "_use_smtp", False) and hasattr(self, "_smtp_config"):
            try:
                import aiosmtplib
                from email.mime.multipart import MIMEMultipart
                from email.mime.text import MIMEText
                from app.utils.encryption import decrypt_credential
                from app.db.session import get_global_db
                from app.core.circuit_breakers import purelymail_smtp_breaker

                cfg = self._smtp_config
                async with get_global_db() as db:
                    password = await decrypt_credential(db, cfg["password_enc"])

                # When we have attachments we need a 'mixed' outer container
                # with an 'alternative' inner for the html/plain bodies.
                if attachments:
                    from email.mime.base import MIMEBase
                    from email.mime.application import MIMEApplication
                    from email import encoders as _enc
                    msg = MIMEMultipart("mixed")
                    body_alt = MIMEMultipart("alternative")
                    if plain_content:
                        body_alt.attach(MIMEText(plain_content, "plain"))
                    body_alt.attach(MIMEText(html_content, "html"))
                    msg.attach(body_alt)
                    for a in attachments:
                        a_content = a.get("content")
                        a_mime = a.get("mime_type") or "application/octet-stream"
                        a_name = a.get("filename") or "attachment"
                        if not a_content:
                            continue
                        maintype, _, subtype = a_mime.partition("/")
                        part = MIMEBase(maintype or "application", subtype or "octet-stream")
                        part.set_payload(a_content)
                        _enc.encode_base64(part)
                        part.add_header("Content-Disposition", f'attachment; filename="{a_name}"')
                        msg.attach(part)
                else:
                    msg = MIMEMultipart("alternative")
                    if plain_content:
                        msg.attach(MIMEText(plain_content, "plain"))
                    msg.attach(MIMEText(html_content, "html"))
                msg["From"] = f"{cfg['from_name']} <{cfg['from_email']}>"
                msg["To"] = to_email
                msg["Subject"] = subject

                async def _do_smtp_send():
                    port = cfg["port"]
                    if port == 465:
                        smtp = aiosmtplib.SMTP(hostname=cfg["host"], port=port, use_tls=True)
                    else:
                        smtp = aiosmtplib.SMTP(hostname=cfg["host"], port=port, start_tls=True)
                    await smtp.connect()
                    await smtp.login(cfg["username"], password)
                    await smtp.send_message(msg)
                    await smtp.quit()

                await purelymail_smtp_breaker.call_async(_do_smtp_send)

                provider_id = f"smtp:{cfg['host']}"
                self._use_smtp = False
                self._smtp_config = None
            except Exception as e:
                logger.error("Studio SMTP send failed — NO FALLBACK (no SendGrid, per standing rule)", error=str(e), to=to_email)
                self._use_smtp = False
                self._smtp_config = None
                status = "failed"

        # SendGrid path REMOVED entirely — Don's standing rule
        # (feedback_never_sendgrid_for_studio): NEVER use SendGrid, ever.
        # Studio emails MUST go through the studio's own Purelymail SMTP.
        # Platform-level emails fall through to platform SMTP below.
        if not provider_id:
            # No studio SMTP or SendGrid sent the email
            # Only use platform SMTP for non-tenant emails (platform admin, support)
            is_tenant = False
            try:
                from app.core.tenant_context import get_tenant_context
                is_tenant = bool(get_tenant_context())
            except Exception:
                pass

            if is_tenant:
                # Studio email failed — do NOT fall back to platform resources
                logger.warning("Tenant email not sent — studio email systems unavailable", to=to_email, subject=subject)
                status = "failed"
            else:
                from app.services.email.smtp_sender import is_smtp_configured, send_smtp_email
                if is_smtp_configured():
                    ok = await send_smtp_email(
                        to_email=to_email,
                        subject=subject,
                        html_content=html_content,
                        plain_content=plain_content,
                        extra_headers=(
                            {"List-Unsubscribe": f"<{unsub_url}>",
                             "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
                            if unsub_url else None
                        ),
                    )
                    status = "sent" if ok else "failed"
                else:
                    logger.info("Email skipped (no email configured)", to=to_email, subject=subject)
                    status = "skipped"

        # Log to communication_log
        log_entry = await self._log_communication(
            member_id=member_id,
            channel="email",
            comm_type=email_type,
            recipient=to_email,
            subject=subject,
            body_preview=html_content[:500] if html_content else None,
            provider_id=provider_id,
            status=status,
        )
        return log_entry

    # ── Convenience Methods ───────────────────────────────────────────────────

    async def _get_studio_name(self) -> str:
        """Get the studio/org name from tenant context."""
        try:
            from app.core.tenant_context import get_tenant_context
            from app.db.session import get_global_db
            ctx = get_tenant_context()
            if ctx:
                async with get_global_db() as db:
                    row = await db.fetchrow(
                        "SELECT name FROM af_global.organizations WHERE id = $1",
                        ctx.organization_id,
                    )
                    if not row and ctx.schema_name:
                        row = await db.fetchrow(
                            "SELECT name FROM af_global.organizations WHERE schema_name = $1",
                            ctx.schema_name,
                        )
                    if row:
                        return row["name"]
        except Exception:
            pass
        return "the studio"

    async def send_booking_confirmation(
        self,
        member_id: str,
        to_email: str,
        member_name: str,
        class_title: str,
        session_date: str,
        session_time: str,
        studio_name: str = "",
    ) -> dict:
        if not studio_name:
            studio_name = await self._get_studio_name()
        subject = f"Booking Confirmed: {class_title}"
        html = f"""
        <h2>Your booking is confirmed!</h2>
        <p>Hi {member_name},</p>
        <p>You're booked for <strong>{class_title}</strong> on {session_date} at {session_time}.</p>
        <p>See you at {studio_name}!</p>
        <p style="color: #666; font-size: 12px;">— {studio_name}</p>
        """
        return await self.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html,
            member_id=member_id,
            email_type="booking_confirmation",
        )

    async def send_booking_cancellation(
        self,
        member_id: str,
        to_email: str,
        member_name: str,
        class_title: str,
        session_date: str,
    ) -> dict:
        studio_name = await self._get_studio_name()
        subject = f"Booking Cancelled: {class_title}"
        html = f"""
        <h2>Booking Cancelled</h2>
        <p>Hi {member_name},</p>
        <p>Your booking for <strong>{class_title}</strong> on {session_date} has been cancelled.</p>
        <p style="color: #666; font-size: 12px;">— {studio_name}</p>
        """
        return await self.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html,
            member_id=member_id,
            email_type="booking_cancellation",
        )

    async def send_waitlist_promotion(
        self,
        member_id: str,
        to_email: str,
        member_name: str,
        class_title: str,
        session_date: str,
        session_time: str,
    ) -> dict:
        studio_name = await self._get_studio_name()
        subject = f"You're In! {class_title}"
        html = f"""
        <h2>Great news — you got a spot!</h2>
        <p>Hi {member_name},</p>
        <p>A spot opened up in <strong>{class_title}</strong> on {session_date} at {session_time}
        and you've been moved from the waitlist to confirmed.</p>
        <p style="color: #666; font-size: 12px;">— {studio_name}</p>
        """
        return await self.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html,
            member_id=member_id,
            email_type="waitlist_promotion",
        )

    async def send_membership_welcome(
        self,
        member_id: str,
        to_email: str,
        member_name: str,
        membership_name: str,
        studio_name: str = "",
    ) -> dict:
        if not studio_name:
            studio_name = await self._get_studio_name()
        subject = f"Welcome to {membership_name}!"
        html = f"""
        <h2>Welcome!</h2>
        <p>Hi {member_name},</p>
        <p>Your <strong>{membership_name}</strong> membership is now active at {studio_name}.</p>
        <p>We're excited to have you! Log in to book your first class.</p>
        <p style="color: #666; font-size: 12px;">— {studio_name}</p>
        """
        return await self.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html,
            member_id=member_id,
            email_type="membership_welcome",
        )

    async def send_online_membership_welcome(
        self,
        member_id: str,
        to_email: str,
        member_name: str,
        membership_name: str,
        studio_name: str = "",
        trial_end_display: Optional[str] = None,
        price_display: Optional[str] = None,
        zoom_url: Optional[str] = None,
        zoom_meeting_id: Optional[str] = None,
        zoom_password: Optional[str] = None,
        schedule: Optional[list[dict]] = None,
    ) -> dict:
        """Welcome email for a self-serve online membership signup.

        Unlike the generic membership welcome, this delivers the three things
        an online member needs on day one: their trial/billing terms, the
        standing Zoom link they join every class with, and the upcoming class
        schedule. All fields are optional so it degrades gracefully (e.g. a
        plan with no standing Zoom link still sends a clean welcome).
        """
        if not studio_name:
            studio_name = await self._get_studio_name()

        # Trial / billing terms
        if trial_end_display and price_display:
            billing_block = (
                f"<p>Your free trial is active now and runs through "
                f"<strong>{trial_end_display}</strong>. After that your card on "
                f"file is automatically charged <strong>{price_display}</strong> "
                f"and your membership continues — no action needed. Cancel anytime "
                f"before then and you won't be charged.</p>"
            )
        elif price_display:
            billing_block = (
                f"<p>Your <strong>{membership_name}</strong> membership is active. "
                f"Your card on file is billed <strong>{price_display}</strong> each "
                f"period.</p>"
            )
        else:
            billing_block = ""

        # Standing Zoom link
        if zoom_url:
            zoom_meta = ""
            if zoom_meeting_id:
                zoom_meta += f"<br>Meeting ID: <strong>{zoom_meeting_id}</strong>"
            if zoom_password:
                zoom_meta += f"<br>Passcode: <strong>{zoom_password}</strong>"
            zoom_block = (
                f'<div style="margin:16px 0;padding:16px;background:#f5f7f2;'
                f'border-radius:8px;">'
                f"<p style=\"margin:0 0 8px;\"><strong>Your class link</strong></p>"
                f'<p style="margin:0 0 12px;">Use this same link to join every '
                f"online class:</p>"
                f'<p style="margin:0 0 8px;"><a href="{zoom_url}" '
                f'style="display:inline-block;padding:10px 20px;background:#7a8b6f;'
                f'color:#fff;text-decoration:none;border-radius:6px;font-weight:600;">'
                f"Join Class on Zoom</a></p>"
                f'<p style="margin:0;color:#555;font-size:13px;">{zoom_url}{zoom_meta}</p>'
                f"</div>"
            )
        else:
            zoom_block = ""

        # Upcoming schedule
        if schedule:
            rows_html = "".join(
                f'<tr><td style="padding:6px 12px 6px 0;">{s.get("when", "")}</td>'
                f'<td style="padding:6px 0;">{s.get("title", "")}</td></tr>'
                for s in schedule
            )
            schedule_block = (
                f'<p style="margin:16px 0 8px;"><strong>This week\'s classes</strong></p>'
                f'<table style="border-collapse:collapse;font-size:14px;">{rows_html}</table>'
                f'<p style="font-size:13px;color:#555;">Full schedule and bookings are '
                f"in your member portal.</p>"
            )
        else:
            schedule_block = ""

        subject = f"Welcome to {membership_name} — you're all set"
        html = f"""
        <h2>Welcome, {member_name}!</h2>
        <p>Your <strong>{membership_name}</strong> membership at {studio_name} is
        active. Here's everything you need to get started.</p>
        {billing_block}
        {zoom_block}
        {schedule_block}
        <p style="color: #666; font-size: 12px;">— {studio_name}</p>
        """
        return await self.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html,
            member_id=member_id,
            email_type="membership_welcome",
        )

    async def send_payment_failed(
        self,
        member_id: str,
        to_email: str,
        member_name: str,
        membership_name: str,
        amount_display: str,
    ) -> dict:
        studio_name = await self._get_studio_name()
        subject = "Action Required: Payment Failed"
        html = f"""
        <h2>Payment Failed</h2>
        <p>Hi {member_name},</p>
        <p>We were unable to process your payment of <strong>{amount_display}</strong>
        for your <strong>{membership_name}</strong> membership.</p>
        <p>Please update your payment method to keep your membership active.</p>
        <p style="color: #666; font-size: 12px;">— {studio_name}</p>
        """
        return await self.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html,
            member_id=member_id,
            email_type="payment_failed",
        )

    async def send_payment_receipt(
        self,
        member_id: str,
        to_email: str,
        member_name: str,
        amount_display: str,
        description: str,
    ) -> dict:
        studio_name = await self._get_studio_name()
        subject = f"Payment Receipt — {amount_display}"
        html = f"""
        <h2>Payment Receipt</h2>
        <p>Hi {member_name},</p>
        <p>We received your payment of <strong>{amount_display}</strong>.</p>
        <p><strong>Description:</strong> {description}</p>
        <p>Thank you!</p>
        <p style="color: #666; font-size: 12px;">— {studio_name}</p>
        """
        return await self.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html,
            member_id=member_id,
            email_type="payment_receipt",
        )

    # ── Communication Log ─────────────────────────────────────────────────────

    async def _log_communication(
        self,
        member_id: Optional[str],
        channel: str,
        comm_type: str,
        recipient: str,
        subject: Optional[str],
        body_preview: Optional[str] = None,
        provider_id: Optional[str] = None,
        status: str = "sent",
        metadata: Optional[dict] = None,
    ) -> dict:
        log_id = str(uuid.uuid4())
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                INSERT INTO communication_log
                    (id, member_id, channel, type, recipient, subject,
                     body_preview, provider_id, status, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb)
                RETURNING *
                """,
                log_id, member_id, channel, comm_type, recipient,
                subject, body_preview, provider_id, status,
                str(metadata) if metadata else None,
            )
            return dict(row)

    async def list_communications(
        self,
        member_id: Optional[str] = None,
        channel: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """List communication log entries."""
        async with get_tenant_db() as db:
            conditions = []
            params = []
            idx = 1
            if member_id:
                conditions.append(f"member_id = ${idx}")
                params.append(member_id)
                idx += 1
            if channel:
                conditions.append(f"channel = ${idx}")
                params.append(channel)
                idx += 1

            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            params.append(limit)
            rows = await db.fetch(
                f"""
                SELECT * FROM communication_log
                {where}
                ORDER BY created_at DESC
                LIMIT ${idx}
                """,
                *params,
            )
            return [dict(r) for r in rows]
