"""AuraFlow — Webhook Endpoints

Stripe, Mux, Zoom, SendGrid, and Twilio webhook receivers. These run without
auth — verification is done via webhook signatures.
"""
import hashlib
import hmac
import json
from urllib.parse import urlencode

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import PlainTextResponse

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_tenant_db, get_global_db
from app.services.payments.webhook_handler import StripeWebhookHandler
from app.services.payments.square_webhook_handler import (
    verify_signature as verify_square_signature,
    handle_event as handle_square_event,
)
from app.services.integrations.zoom_service import ZoomService

stripe_router = APIRouter()
square_router = APIRouter()
mux_router = APIRouter()
zoom_router = APIRouter()
sendgrid_router = APIRouter()
twilio_router = APIRouter()


def _verify_twilio_signature(request: Request, form_params: dict) -> bool:
    """Verify Twilio webhook request signature using X-Twilio-Signature header.

    Uses HMAC-SHA1 per Twilio's spec:
    https://www.twilio.com/docs/usage/security#validating-requests
    """
    auth_token = settings.TWILIO_AUTH_TOKEN
    if not auth_token:
        logger.warning("TWILIO_AUTH_TOKEN not configured — rejecting webhook")
        return False

    signature = request.headers.get("X-Twilio-Signature", "")
    if not signature:
        return False

    # Build the URL from the request
    url = str(request.url)

    # Sort form params and concatenate key+value
    sorted_params = sorted(form_params.items())
    data_string = url + "".join(k + v for k, v in sorted_params)

    # HMAC-SHA1 with auth token
    expected = hmac.new(
        auth_token.encode("utf-8"),
        data_string.encode("utf-8"),
        hashlib.sha1,
    ).digest()

    import base64
    expected_b64 = base64.b64encode(expected).decode("utf-8")

    return hmac.compare_digest(expected_b64, signature)

webhook_handler = StripeWebhookHandler()
zoom_svc = ZoomService()


@stripe_router.post("")
async def stripe_webhook(request: Request):
    """
    Receive Stripe webhook events.
    Verifies the signature, then routes to the appropriate handler.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = await webhook_handler.verify_signature(payload, sig_header)
    except ValueError as e:
        logger.warning("Stripe webhook verification failed", error=str(e))
        raise HTTPException(status_code=400, detail="Invalid payload")
    except Exception as e:
        logger.warning("Stripe webhook signature error", error=str(e))
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        result = await webhook_handler.handle_event(event)
        return result
    except Exception as e:
        event_type = event.get("type", "unknown")
        event_id = event.get("id", "unknown")
        logger.error("Stripe webhook handler crashed", event_type=event_type, event_id=event_id, error=str(e))
        # Tenant-scoped alert: resolve which studio owns this event and
        # email THEIR owner — never a global ops address. Webhooks for
        # tenant A should not page tenant B's operator. If we can't
        # resolve the tenant (corrupt event, missing metadata), just
        # log; Stripe will keep retrying and ops can spot the pattern
        # in logs.
        try:
            data_obj = event.get("data", {}).get("object", {})
            schema = await webhook_handler._resolve_schema(data_obj, event=event)
            owner_email = None
            if schema:
                async with get_global_db() as gdb:
                    row = await gdb.fetchrow(
                        """
                        SELECT u.email
                        FROM af_global.organization_users ou
                        JOIN af_global.users u ON u.id = ou.user_id
                        JOIN af_global.organizations o ON o.id = ou.organization_id
                        WHERE o.schema_name = $1
                          AND ou.role = 'owner'
                          AND ou.is_active = TRUE
                        LIMIT 1
                        """,
                        schema,
                    )
                    if row:
                        owner_email = row["email"]
            if owner_email:
                from app.services.email.smtp_sender import is_smtp_configured, send_smtp_email
                if is_smtp_configured():
                    await send_smtp_email(
                        to_email=owner_email,
                        subject=f"Stripe webhook failed to process — {event_type}",
                        html_content=(
                            f"<h2 style=\"color: red;\">Stripe Webhook Error</h2>"
                            f"<p>A Stripe webhook event for your studio failed to process.</p>"
                            f"<p><strong>Event:</strong> {event_type}<br>"
                            f"<strong>Event ID:</strong> {event_id}<br>"
                            f"<strong>Error:</strong> {str(e)}</p>"
                            f"<p>Stripe will retry automatically. If this keeps happening, "
                            f"reply to this email and we'll investigate.</p>"
                            f"<p>— AuraFlow</p>"
                        ),
                    )
            else:
                logger.warning(
                    "Webhook crash alert: could not resolve tenant owner — skipping email",
                    event_id=event_id, schema=schema,
                )
        except Exception:
            pass  # Don't let alert failure mask the original error
        raise


@square_router.post("")
async def square_webhook(request: Request):
    """Receive Square webhook events.

    Square signs each delivery with HMAC-SHA256 of
    (notification_url + raw body). We rebuild notification_url from
    settings (NOT request.url, to avoid Host-header spoofing). Returns
    quickly per Square's spec — handler logic logs but does not raise.
    """
    body = await request.body()
    signature = (
        request.headers.get("x-square-hmacsha256-signature")
        or request.headers.get("x-square-signature")
        or ""
    )
    notification_url = (
        settings.SQUARE_WEBHOOK_NOTIFICATION_URL
        or "https://api.auraflow.fit/webhooks/square"
    )

    if not verify_square_signature(notification_url, body, signature):
        logger.warning(
            "Square webhook signature verification failed",
            sig_header_present=bool(signature),
        )
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid payload")

    try:
        result = await handle_square_event(event)
        return result
    except Exception as e:
        logger.error(
            "Square webhook handler crashed",
            event_type=event.get("type", "unknown"),
            event_id=event.get("event_id") or event.get("id"),
            error=str(e),
        )
        # Always return 200 so Square doesn't retry on our internal
        # bugs (we have logs to diagnose). Match the Stripe handler's
        # convention of internal-error visibility without retry storms.
        return {"status": "logged"}


@mux_router.post("")
async def mux_webhook(request: Request):
    """Mux video webhook — stub for Phase 2."""
    payload = await request.json()
    logger.info("Mux webhook received", event_type=payload.get("type"))
    return {"status": "ok"}


@zoom_router.post("")
async def zoom_webhook(request: Request):
    """
    Receive Zoom webhook events.
    Handles URL validation challenge and verifies signatures.
    """
    payload_bytes = await request.body()

    try:
        event = __import__("json").loads(payload_bytes)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Handle Zoom URL validation challenge
    if event.get("event") == "endpoint.url_validation":
        plain_token = event.get("payload", {}).get("plainToken", "")
        # Zoom requires HMAC-SHA256 with the webhook secret, not plain SHA256
        if not settings.ZOOM_WEBHOOK_SECRET:
            raise HTTPException(status_code=500, detail="Zoom webhook secret not configured")
        hash_value = hmac.new(
            settings.ZOOM_WEBHOOK_SECRET.encode(),
            plain_token.encode(),
            hashlib.sha256,
        ).hexdigest()
        return {
            "plainToken": plain_token,
            "encryptedToken": hash_value,
        }

    # Route by account_id in the payload
    account_id = event.get("payload", {}).get("account_id", "")
    if not account_id:
        logger.warning("Zoom webhook missing account_id")
        return {"status": "ok"}

    org_id = await zoom_svc.find_org_by_account_id(account_id)
    if not org_id:
        logger.warning("Zoom webhook — unknown account", account_id=account_id)
        return {"status": "ok"}

    # Verify signature if webhook secret is configured
    creds = await zoom_svc.get_credentials(org_id)
    if creds and creds.get("webhook_secret"):
        signature = request.headers.get("x-zm-signature", "")
        timestamp = request.headers.get("x-zm-request-timestamp", "")
        message = f"v0:{timestamp}:{payload_bytes.decode()}"
        expected = "v0=" + hmac.new(
            creds["webhook_secret"].encode(), message.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            logger.warning("Zoom webhook signature mismatch")
            raise HTTPException(status_code=401, detail="Invalid signature")

    result = await zoom_svc.handle_webhook(org_id, event)
    return result


# ── SendGrid Event Webhooks ──────────────────────────────────────────────

@sendgrid_router.post("")
async def sendgrid_webhook(request: Request):
    """
    Receive SendGrid event webhooks.
    Updates communication_log and email_campaign_sends status based on events.
    Events: delivered, open, click, bounce, spam_report, unsubscribe, dropped.
    """
    # Verify SendGrid webhook signature if secret is configured
    webhook_secret = settings.SENDGRID_INBOUND_WEBHOOK_SECRET
    if webhook_secret:
        signature = request.headers.get("X-Twilio-Email-Event-Webhook-Signature", "")
        timestamp = request.headers.get("X-Twilio-Email-Event-Webhook-Timestamp", "")
        body = await request.body()
        if not signature or not timestamp:
            logger.warning("SendGrid event webhook missing signature headers")
            raise HTTPException(status_code=403, detail="Missing signature headers")
        # Verify HMAC: HMAC-SHA256 of timestamp + body using the webhook secret
        import base64
        signed_payload = timestamp.encode() + body
        expected = hmac.new(
            base64.b64decode(webhook_secret),
            signed_payload,
            hashlib.sha256,
        ).digest()
        try:
            provided = base64.b64decode(signature)
        except Exception:
            raise HTTPException(status_code=403, detail="Invalid signature encoding")
        if not hmac.compare_digest(expected, provided):
            logger.warning("SendGrid event webhook signature verification failed")
            raise HTTPException(status_code=403, detail="Invalid webhook signature")
        # Parse the body we already read
        try:
            events = json.loads(body)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")
    else:
        logger.warning("SENDGRID_INBOUND_WEBHOOK_SECRET not configured — skipping signature verification (dev mode)")
        try:
            events = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")

    if not isinstance(events, list):
        return {"status": "ok", "processed": 0}

    processed = 0
    for event in events:
        event_type = event.get("event")
        sg_message_id = event.get("sg_message_id", "").split(".")[0]  # strip suffix
        email = event.get("email")

        if not event_type or not sg_message_id:
            continue

        # Map SendGrid event types to our statuses
        status_map = {
            "delivered": "delivered",
            "open": "opened",
            "click": "clicked",
            "bounce": "bounced",
            "dropped": "failed",
            "spam_report": "bounced",
            "unsubscribe": "unsubscribed",
        }
        new_status = status_map.get(event_type)
        if not new_status:
            continue

        try:
            # Try to resolve tenant directly from custom args embedded at send time
            target_schema = None
            auraflow_schema = event.get("auraflow_schema")
            if auraflow_schema:
                # Validate schema exists and is active
                async with get_global_db() as db:
                    valid = await db.fetchrow(
                        "SELECT 1 FROM af_global.organizations WHERE schema_name = $1 AND status IN ('active', 'trial')",
                        auraflow_schema,
                    )
                if valid:
                    target_schema = auraflow_schema

            if target_schema:
                schemas_to_check = [target_schema]
            else:
                # Fallback: scan all tenant schemas (legacy emails without custom args)
                async with get_global_db() as db:
                    rows = await db.fetch(
                        "SELECT schema_name FROM af_global.organizations WHERE status IN ('active', 'trial')"
                    )
                schemas_to_check = [r["schema_name"] for r in rows]

            for schema in schemas_to_check:
                async with get_tenant_db(schema_override=schema) as db:
                    # Update communication_log
                    updated = await db.fetchrow(
                        """
                        UPDATE communication_log
                        SET status = $1
                        WHERE provider_id = $2 AND channel = 'email'
                        RETURNING id, member_id
                        """,
                        new_status, sg_message_id,
                    )

                    if updated:
                        # Update campaign sends if applicable
                        await db.execute(
                            """
                            UPDATE email_campaign_sends
                            SET status = $1,
                                opened_at = CASE WHEN $1 = 'opened' AND opened_at IS NULL THEN NOW() ELSE opened_at END,
                                clicked_at = CASE WHEN $1 = 'clicked' AND clicked_at IS NULL THEN NOW() ELSE clicked_at END
                            WHERE sendgrid_message_id = $2
                            """,
                            new_status, sg_message_id,
                        )

                        # Handle unsubscribe — opt member out of email
                        if event_type == "unsubscribe" and updated.get("member_id"):
                            await db.execute(
                                """
                                UPDATE members
                                SET email_opt_in = FALSE, email_opt_out_at = NOW()
                                WHERE id = $1
                                """,
                                str(updated["member_id"]),
                            )
                            logger.info(
                                "Member unsubscribed via SendGrid",
                                member_id=str(updated["member_id"]),
                            )

                        processed += 1
                        break  # Found the tenant, no need to check others

        except Exception as e:
            logger.warning(
                "SendGrid webhook event processing failed",
                event_type=event_type,
                error=str(e),
            )

    logger.info("SendGrid webhook processed", events_count=len(events), processed=processed)
    return {"status": "ok", "processed": processed}


# ── SendGrid Inbound Parse (incoming email) ──────────────────────────

@sendgrid_router.post("/inbound")
async def sendgrid_inbound_parse(request: Request):
    """
    Receive incoming emails via SendGrid Inbound Parse.
    Extracts email fields from multipart form data and queues for AI processing.
    """
    # Verify SendGrid inbound parse webhook signature if secret is configured
    webhook_secret = settings.SENDGRID_INBOUND_WEBHOOK_SECRET
    if webhook_secret:
        signature = request.headers.get("X-Twilio-Email-Event-Webhook-Signature", "")
        timestamp = request.headers.get("X-Twilio-Email-Event-Webhook-Timestamp", "")
        body = await request.body()
        if not signature or not timestamp:
            logger.warning("SendGrid inbound webhook missing signature headers")
            raise HTTPException(status_code=403, detail="Missing signature headers")
        import base64
        signed_payload = timestamp.encode() + body
        expected = hmac.new(
            base64.b64decode(webhook_secret),
            signed_payload,
            hashlib.sha256,
        ).digest()
        try:
            provided = base64.b64decode(signature)
        except Exception:
            raise HTTPException(status_code=403, detail="Invalid signature encoding")
        if not hmac.compare_digest(expected, provided):
            logger.warning("SendGrid inbound webhook signature verification failed")
            raise HTTPException(status_code=403, detail="Invalid webhook signature")
    else:
        logger.warning("SENDGRID_INBOUND_WEBHOOK_SECRET not configured — skipping signature verification (dev mode)")

    try:
        form = await request.form()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid form data")

    from_email = form.get("from", "")
    to_email = form.get("to", "")
    subject = form.get("subject", "")
    text = form.get("text", "")
    html = form.get("html", "")

    # Extract email address from "Name <email>" format
    if "<" in from_email and ">" in from_email:
        from_name = from_email.split("<")[0].strip().strip('"')
        from_addr = from_email.split("<")[1].split(">")[0]
    else:
        from_name = None
        from_addr = from_email

    if not from_addr:
        return {"status": "ok", "message": "No sender email"}

    # Generate a unique message ID if not provided
    headers_raw = form.get("headers", "")
    message_id = None
    for line in str(headers_raw).split("\n"):
        if line.lower().startswith("message-id:"):
            message_id = line.split(":", 1)[1].strip().strip("<>")
            break

    # ── Check if this is a reply to an engagement autopilot campaign ──
    try:
        from app.services.ai.engagement_autopilot import EngagementAutopilot
        from app.db.session import get_global_db
        engagement_svc = EngagementAutopilot()

        async with get_global_db() as gdb:
            tenant_schemas = await gdb.fetch(
                "SELECT schema_name FROM af_global.organizations WHERE status IN ('active', 'trial')"
            )

        reply_body = str(text) if text else ""
        for t_row in tenant_schemas:
            t_schema = t_row["schema_name"]
            campaign_id = await engagement_svc.match_reply_to_campaign(
                t_schema, from_addr, str(subject)
            )
            if campaign_id:
                from app.workers.tasks.engagement_autopilot import handle_engagement_reply
                handle_engagement_reply.delay(t_schema, campaign_id, reply_body)
                logger.info(
                    "Engagement reply matched and queued",
                    from_email=from_addr,
                    campaign_id=campaign_id,
                    schema=t_schema,
                )
                return {"status": "ok", "routed_to": "engagement_autopilot", "campaign_id": campaign_id}
    except Exception as e:
        logger.warning("Engagement reply matching failed (non-fatal)", error=str(e))

    # No further routing in the open build — the platform sales inbox is a
    # commercial-only feature. Acknowledge receipt.
    logger.info("SendGrid inbound email received", from_email=from_addr, subject=subject)
    return {"status": "ok"}


# ── Twilio Incoming SMS ────────────────────────────────────────────────

# TCPA compliance keywords
_STOP_KEYWORDS = {"STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"}
_HELP_KEYWORDS = {"HELP", "INFO"}
_START_KEYWORDS = {"START", "YES", "UNSTOP"}


@twilio_router.post("")
async def twilio_incoming_sms(request: Request):
    """
    Receive incoming SMS via Twilio webhook.
    Verifies signature, handles TCPA compliance (STOP/HELP),
    identifies the sender (instructor or member), routes to AI Manager,
    and returns a TwiML response.
    """
    form = await request.form()
    form_params = {k: str(v) for k, v in form.items()}
    from_phone = form_params.get("From", "")
    body = form_params.get("Body", "")
    to_phone = form_params.get("To", "")

    # Verify Twilio signature
    if not _verify_twilio_signature(request, form_params):
        logger.warning("Twilio webhook signature verification failed", from_phone=from_phone)
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    if not body or not from_phone:
        return PlainTextResponse(
            '<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
            media_type="application/xml",
        )

    logger.info("Twilio SMS received", from_phone=from_phone, body_preview=body[:100])

    # Resolve tenant by Twilio phone number → organization mapping
    schema = None
    async with get_global_db() as db:
        org = await db.fetchrow(
            """
            SELECT schema_name FROM af_global.organizations
            WHERE twilio_phone_number = $1 AND status IN ('active', 'trial')
            """,
            to_phone,
        )
        if not org:
            # Fallback: first active org (for single-tenant / dev)
            org = await db.fetchrow(
                "SELECT schema_name FROM af_global.organizations WHERE status IN ('active', 'trial') LIMIT 1"
            )
        if org:
            schema = org["schema_name"]

    if not schema:
        logger.warning("Twilio SMS: no active tenant found", to_phone=to_phone)
        return PlainTextResponse(
            '<?xml version="1.0" encoding="UTF-8"?><Response>'
            '<Message>Sorry, this service is not currently available.</Message>'
            '</Response>',
            media_type="application/xml",
        )

    # ── TCPA Compliance: Handle STOP / HELP / START keywords ─────────
    body_upper = body.strip().upper()

    if body_upper in _STOP_KEYWORDS:
        await _handle_sms_opt_out(from_phone, schema)
        return PlainTextResponse(
            '<?xml version="1.0" encoding="UTF-8"?><Response>'
            '<Message>You have been unsubscribed and will no longer receive SMS messages. '
            'Reply START to re-subscribe.</Message></Response>',
            media_type="application/xml",
        )

    if body_upper in _HELP_KEYWORDS:
        return PlainTextResponse(
            '<?xml version="1.0" encoding="UTF-8"?><Response>'
            '<Message>Reply STOP to unsubscribe from SMS messages. '
            'For support, contact your studio directly or visit our website.</Message></Response>',
            media_type="application/xml",
        )

    if body_upper in _START_KEYWORDS:
        # Re-subscribe: check if this is a standalone START (not a sub-finder YES)
        resubscribed = await _handle_sms_opt_in(from_phone, schema)
        if resubscribed:
            return PlainTextResponse(
                '<?xml version="1.0" encoding="UTF-8"?><Response>'
                '<Message>You have been re-subscribed to SMS messages.</Message></Response>',
                media_type="application/xml",
            )

    # ── Identify the sender ──────────────────────────────────────────────
    sender_type, sender_id, sender_name = await _identify_sender(from_phone, schema)

    # Check if this is a response to an active sub-finder request
    if sender_type == "instructor" and body_upper in ("YES", "NO"):
        from app.services.ai.sub_finder_service import SubFinderService
        sub_svc = SubFinderService()

        async with get_tenant_db(schema_override=schema) as _db:
            active_request = await sub_svc.find_active_request_for_instructor(from_phone)

        if active_request:
            accepted = body_upper == "YES"
            async with get_tenant_db(schema_override=schema) as _db:
                result = await sub_svc.handle_sub_response(
                    active_request["id"], sender_id, accepted
                )

            reply = "Thanks! You're confirmed to cover the class." if accepted else "No problem. We'll find someone else."
            return PlainTextResponse(
                f'<?xml version="1.0" encoding="UTF-8"?><Response>'
                f'<Message>{reply}</Message></Response>',
                media_type="application/xml",
            )

    # Route to AI Manager
    from app.services.ai.ai_manager_service import AIManagerService
    ai_mgr = AIManagerService()

    async with get_tenant_db(schema_override=schema) as _db:
        result = await ai_mgr.handle_incoming_message(
            channel="sms",
            from_identifier=from_phone,
            body=body,
            sender_type=sender_type,
            sender_id=sender_id,
            sender_phone=from_phone,
        )

    # Route through AI Office Manager (async, non-blocking)
    try:
        from app.workers.tasks.office_manager import process_inbound_office_sms
        process_inbound_office_sms.delay(schema, from_phone, body)
    except Exception:
        pass  # Office Manager processing is best-effort; don't break the webhook

    # Build TwiML response
    response_text = result.get("response", "")
    if response_text:
        # Truncate for SMS
        if len(response_text) > 1500:
            response_text = response_text[:1497] + "..."
        return PlainTextResponse(
            f'<?xml version="1.0" encoding="UTF-8"?><Response>'
            f'<Message>{_escape_xml(response_text)}</Message></Response>',
            media_type="application/xml",
        )

    return PlainTextResponse(
        '<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml",
    )


# ── Twilio Delivery Status Callback ─────────────────────────────────────

@twilio_router.post("/status")
async def twilio_delivery_status(request: Request):
    """
    Receive SMS delivery status callbacks from Twilio.
    Updates sms_messages and communication_log with delivery status.
    Twilio status values: queued, sent, delivered, undelivered, failed.
    """
    form = await request.form()
    form_params = {k: str(v) for k, v in form.items()}

    # Verify signature
    if not _verify_twilio_signature(request, form_params):
        logger.warning("Twilio status webhook signature verification failed")
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    message_sid = form_params.get("MessageSid", "")
    message_status = form_params.get("MessageStatus", "")
    error_code = form_params.get("ErrorCode")
    error_message = form_params.get("ErrorMessage")

    if not message_sid or not message_status:
        return PlainTextResponse("ok")

    # Map Twilio status to our status
    status_map = {
        "queued": "queued",
        "sent": "sent",
        "delivered": "delivered",
        "undelivered": "failed",
        "failed": "failed",
    }
    our_status = status_map.get(message_status, message_status)

    logger.info(
        "Twilio delivery status",
        message_sid=message_sid,
        status=message_status,
        error_code=error_code,
    )

    # Update across tenant schemas (SMS could belong to any tenant)
    async with get_global_db() as db:
        schemas = await db.fetch(
            "SELECT schema_name FROM af_global.organizations WHERE status IN ('active', 'trial')"
        )

    for schema_row in schemas:
        schema = schema_row["schema_name"]
        try:
            async with get_tenant_db(schema_override=schema) as db:
                # Update sms_messages
                updated = await db.fetchrow(
                    """
                    UPDATE sms_messages
                    SET status = $1,
                        error_message = COALESCE($2, error_message)
                    WHERE twilio_sid = $3
                    RETURNING id, member_id
                    """,
                    our_status,
                    error_message if error_code else None,
                    message_sid,
                )
                if updated:
                    # Also update communication_log
                    await db.execute(
                        """
                        UPDATE communication_log
                        SET status = $1
                        WHERE provider_id = $2 AND channel = 'sms'
                        """,
                        our_status, message_sid,
                    )
                    break  # Found the tenant
        except Exception as e:
            logger.warning(
                "Twilio status update failed for schema",
                schema=schema,
                error=str(e),
            )

    return PlainTextResponse("ok")


async def _identify_sender(from_phone: str, schema: str) -> tuple[str | None, str | None, str | None]:
    """Identify if the SMS sender is an instructor or member."""
    # Normalize phone (strip +1 prefix for matching)
    normalized = from_phone.lstrip("+").lstrip("1") if from_phone.startswith("+1") else from_phone
    # phone_hash is HMAC(normalized E.164), drives the post-Phase-C lookup
    from app.services.members.phone_hash import hash_phone
    phash = hash_phone(from_phone)

    async with get_tenant_db(schema_override=schema) as db:
        # Check instructors first. instructors.phone is NOT in the Phase C
        # drop scope, so plain match is still fine; phone_hash branch is
        # available once instructor backfill completes.
        instructor = await db.fetchrow(
            """
            SELECT id, display_name FROM instructors
            WHERE (phone_hash = $3 OR phone = $1 OR phone = $2)
            AND is_active = TRUE
            """,
            from_phone, normalized, phash,
        )
        if instructor:
            return "instructor", str(instructor["id"]), instructor["display_name"]

        # Check members — phone_hash only. The plaintext phone column is
        # being dropped in Phase C, so referencing it here would SQL-error
        # post-drop. Any member who hasn't been phone_hash-backfilled will
        # show as unknown sender (logged in communication_log either way).
        member = await db.fetchrow(
            """
            SELECT id, first_name, last_name FROM members
            WHERE phone_hash = $1
            AND is_active = TRUE
            """,
            phash,
        )
        if member:
            name = f"{member['first_name'] or ''} {member['last_name'] or ''}".strip()
            return "member", str(member["id"]), name

    return None, None, None


async def _handle_sms_opt_out(from_phone: str, schema: str) -> None:
    """TCPA compliance: opt out member/instructor from SMS when they text STOP.

    Uses phone_hash (deterministic HMAC-SHA256, populated on every member
    write) so the lookup survives Phase C plaintext-phone drop. Falls back
    to plaintext phone WHERE during the bake window — once plaintext is
    dropped, only the hash branch matters.
    """
    from app.services.members.phone_hash import hash_phone, normalize_phone
    norm = normalize_phone(from_phone)
    phash = hash_phone(from_phone)
    legacy_normalized = from_phone.lstrip("+").lstrip("1") if from_phone.startswith("+1") else from_phone

    async with get_tenant_db(schema_override=schema) as db:
        # Opt out members — phone_hash only. The plaintext phone column is
        # dropped in Phase C, so a `OR phone = $...` fallback would SQL-error
        # post-drop. All active members are backfilled by the Phase C
        # consistency scan; unhashable junk phones can't be opted-out by
        # this path anyway (they were never reachable by SMS).
        await db.execute(
            """
            UPDATE members
            SET sms_opt_in = FALSE, sms_opt_out_at = NOW()
            WHERE sms_opt_in = TRUE
              AND phone_hash = $1
            """,
            phash,
        )
        # Log the opt-out in communication_log
        import uuid
        await db.execute(
            """
            INSERT INTO communication_log
                (id, channel, type, recipient, body_preview, status)
            VALUES ($1, 'sms', 'opt_out', $2, 'STOP received — member opted out', 'delivered')
            """,
            str(uuid.uuid4()), from_phone,
        )

    logger.info("SMS opt-out processed", phone=from_phone, schema=schema)


async def _handle_sms_opt_in(from_phone: str, schema: str) -> bool:
    """TCPA compliance: re-subscribe member when they text START.

    Same phone_hash + legacy-plaintext fallback shape as _handle_sms_opt_out.
    """
    from app.services.members.phone_hash import hash_phone, normalize_phone
    norm = normalize_phone(from_phone)
    phash = hash_phone(from_phone)
    legacy_normalized = from_phone.lstrip("+").lstrip("1") if from_phone.startswith("+1") else from_phone

    async with get_tenant_db(schema_override=schema) as db:
        # phone_hash only — see _handle_sms_opt_out for rationale.
        result = await db.execute(
            """
            UPDATE members
            SET sms_opt_in = TRUE, sms_opt_out_at = NULL
            WHERE sms_opt_in = FALSE
              AND phone_hash = $1
            """,
            phash,
        )
        resubscribed = "UPDATE 0" not in result

        if resubscribed:
            import uuid
            await db.execute(
                """
                INSERT INTO communication_log
                    (id, channel, type, recipient, body_preview, status)
                VALUES ($1, 'sms', 'opt_in', $2, 'START received — member re-subscribed', 'delivered')
                """,
                str(uuid.uuid4()), from_phone,
            )
            logger.info("SMS opt-in processed", phone=from_phone, schema=schema)

    return resubscribed


def _escape_xml(text: str) -> str:
    """Escape special XML characters."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;"))


# ── Twilio Voice Webhooks ────────────────────────────────────────────────

voice_router = APIRouter()

_voice_call_svc = None


def _get_voice_call_svc():
    """Lazy-load VoiceCallService to avoid circular imports."""
    global _voice_call_svc
    if _voice_call_svc is None:
        from app.services.ai.voice_call_service import VoiceCallService
        _voice_call_svc = VoiceCallService()
    return _voice_call_svc


@voice_router.post("/waitlist-twiml")
async def voice_waitlist_twiml(request: Request):
    """Serve TwiML when Twilio connects a waitlist confirmation call.

    Twilio fetches this URL to get the interactive voice menu.
    Query params: booking_id, member_name, class_title.
    """
    params = dict(request.query_params)
    booking_id = params.get("booking_id", "")
    member_name = params.get("member_name", "")
    class_title = params.get("class_title", "")

    if not booking_id:
        raise HTTPException(status_code=400, detail="Missing booking_id")

    svc = _get_voice_call_svc()
    twiml = svc._generate_waitlist_twiml(
        member_name=member_name,
        class_title=class_title,
        booking_id=booking_id,
    )
    return PlainTextResponse(twiml, media_type="application/xml")


@voice_router.post("/payment-twiml")
async def voice_payment_twiml(request: Request):
    """Serve TwiML when Twilio connects a payment recovery call.

    Query params: transaction_id, member_name, amount.
    """
    params = dict(request.query_params)
    transaction_id = params.get("transaction_id", "")
    member_name = params.get("member_name", "")
    amount = params.get("amount", "")

    if not transaction_id:
        raise HTTPException(status_code=400, detail="Missing transaction_id")

    svc = _get_voice_call_svc()
    twiml = svc._generate_payment_twiml(
        member_name=member_name,
        amount=amount,
        transaction_id=transaction_id,
    )
    return PlainTextResponse(twiml, media_type="application/xml")


@voice_router.post("/gather")
async def voice_gather(request: Request):
    """Receive DTMF digit input from Twilio <Gather>.

    Routes to the appropriate handler based on the `type` query param
    (waitlist or payment).
    """
    form = await request.form()
    form_params = {k: str(v) for k, v in form.items()}
    params = dict(request.query_params)

    # Verify Twilio signature
    if not _verify_twilio_signature(request, form_params):
        logger.warning("Voice gather webhook signature verification failed")
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    digits = form_params.get("Digits", "")
    call_type = params.get("type", "")

    svc = _get_voice_call_svc()

    if call_type == "waitlist":
        booking_id = params.get("booking_id", "")
        if not booking_id:
            raise HTTPException(status_code=400, detail="Missing booking_id")

        logger.info(
            "Voice gather: waitlist",
            booking_id=booking_id,
            digits=digits,
        )
        twiml = await svc.handle_waitlist_gather(booking_id=booking_id, digits=digits)
        return PlainTextResponse(twiml, media_type="application/xml")

    elif call_type == "payment":
        transaction_id = params.get("transaction_id", "")
        if not transaction_id:
            raise HTTPException(status_code=400, detail="Missing transaction_id")

        logger.info(
            "Voice gather: payment recovery",
            transaction_id=transaction_id,
            digits=digits,
        )
        twiml = await svc.handle_payment_gather(
            transaction_id=transaction_id, digits=digits,
        )
        return PlainTextResponse(twiml, media_type="application/xml")

    else:
        logger.warning("Voice gather: unknown type", call_type=call_type)
        raise HTTPException(status_code=400, detail=f"Unknown gather type: {call_type}")


@voice_router.post("/status")
async def voice_call_status(request: Request):
    """Receive call status updates from Twilio.

    Handles: initiated, ringing, in-progress, completed, busy,
    no-answer, canceled, failed.
    """
    form = await request.form()
    form_params = {k: str(v) for k, v in form.items()}

    # Verify Twilio signature
    if not _verify_twilio_signature(request, form_params):
        logger.warning("Voice status webhook signature verification failed")
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    call_sid = form_params.get("CallSid", "")
    call_status = form_params.get("CallStatus", "")

    if not call_sid or not call_status:
        return PlainTextResponse("ok")

    logger.info(
        "Voice call status received",
        call_sid=call_sid,
        call_status=call_status,
    )

    svc = _get_voice_call_svc()
    await svc.handle_call_status(call_sid=call_sid, call_status=call_status)

    return PlainTextResponse("ok")
