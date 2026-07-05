"""AuraFlow — Twilio Voice Auto-Call Service

Outbound voice calls for two scenarios:
1. Waitlist promotion — when a spot opens, call the promoted member to confirm
   (press 1 to confirm, press 2 to decline). 60-second timeout escalates to
   the next waitlisted member.
2. Failed payment recovery — call members with failed payments and offer to
   send a payment-update SMS link (press 1).

Uses Twilio REST API to initiate calls with TwiML callback URLs.
Gracefully degrades when Twilio credentials are not configured.
"""
import asyncio
import uuid
from datetime import datetime, timezone
from xml.sax.saxutils import escape as xml_escape

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_tenant_db, get_global_db
from app.services.members.phi_helpers import decrypt_phone


class VoiceCallService:

    # ── Configuration Check ────────────────────────────────────────────────

    def _is_configured(self) -> bool:
        """Return True if Twilio Voice credentials are present."""
        return bool(
            settings.TWILIO_ACCOUNT_SID
            and settings.TWILIO_AUTH_TOKEN
            and settings.TWILIO_PHONE_NUMBER
        )

    def _get_twilio_client(self):
        """Lazy-import and instantiate the Twilio REST client."""
        from twilio.rest import Client
        return Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

    # ── Waitlist Auto-Call ─────────────────────────────────────────────────

    async def initiate_waitlist_call(
        self,
        member_id: str,
        session_id: str,
        booking_id: str,
        schema_override: str | None = None,
    ) -> dict:
        """Place an outbound call to a promoted waitlist member.

        The member has 60 seconds to press 1 (confirm) or 2 (decline).
        If Twilio is not configured, logs a warning and returns a stub.
        """
        call_id = str(uuid.uuid4())
        db_kwargs = {"schema_override": schema_override} if schema_override else {}

        # Fetch member + session info for the voice prompt
        from app.services.members.phi_helpers import decrypt_phone
        async with get_tenant_db(**db_kwargs) as db:
            member = await db.fetchrow(
                "SELECT id, first_name, last_name, phone_enc FROM members WHERE id = $1",
                member_id,
            )
            if not member:
                raise ValueError(f"Member {member_id} not found")
            to_phone = decrypt_phone(member)
            if not to_phone:
                raise ValueError(f"Member {member_id} has no phone number on file")

            session = await db.fetchrow(
                """
                SELECT cs.id, cs.title, cs.starts_at,
                       ct.name AS class_type_name
                FROM class_sessions cs
                LEFT JOIN class_types ct ON ct.id = cs.class_type_id
                WHERE cs.id = $1
                """,
                session_id,
            )
            if not session:
                raise ValueError(f"Class session {session_id} not found")

        member_name = f"{member['first_name'] or ''} {member['last_name'] or ''}".strip()
        class_title = session["title"] or session["class_type_name"] or "your class"

        if not self._is_configured():
            logger.warning(
                "Voice call skipped — Twilio not configured",
                member_id=member_id,
                booking_id=booking_id,
            )
            return {
                "call_id": call_id,
                "status": "skipped",
                "reason": "twilio_not_configured",
            }

        # Build the TwiML callback URL — Twilio will GET/POST this when the
        # call connects to serve the interactive voice menu.
        twiml_url = (
            f"{settings.API_URL}/webhooks/twilio/voice/waitlist-twiml"
            f"?booking_id={booking_id}"
            f"&member_name={_url_encode(member_name)}"
            f"&class_title={_url_encode(class_title)}"
        )
        status_url = f"{settings.API_URL}/webhooks/twilio/voice/status"

        # Place the call via Twilio REST API
        twilio_sid = None
        call_status = "initiated"
        error_message = None

        try:
            client = self._get_twilio_client()
            call = await asyncio.to_thread(
                lambda: client.calls.create(
                    to=to_phone,
                    from_=settings.TWILIO_PHONE_NUMBER,
                    url=twiml_url,
                    status_callback=status_url,
                    status_callback_event=["initiated", "ringing", "answered", "completed"],
                    timeout=60,  # ring for 60 seconds max
                    machine_detection="Enable",  # detect voicemail
                )
            )
            twilio_sid = call.sid
            logger.info(
                "Waitlist voice call initiated",
                call_sid=twilio_sid,
                member_id=member_id,
                booking_id=booking_id,
            )
        except Exception as e:
            call_status = "failed"
            error_message = str(e)
            logger.error(
                "Waitlist voice call failed",
                member_id=member_id,
                booking_id=booking_id,
                error=str(e),
            )

        # Persist call record
        async with get_tenant_db(**db_kwargs) as db:
            await db.execute(
                """
                INSERT INTO voice_calls
                    (id, member_id, call_type, twilio_sid, to_phone,
                     status, reference_id, reference_type, error_message)
                VALUES ($1, $2, 'waitlist', $3, $4, $5, $6, 'booking', $7)
                """,
                call_id, member_id, twilio_sid, to_phone,
                call_status, booking_id, error_message,
            )

        # If the call failed to even place, escalate to next person now
        if call_status == "failed":
            await self._escalate_waitlist(booking_id, schema_override=schema_override)

        return {
            "call_id": call_id,
            "twilio_sid": twilio_sid,
            "status": call_status,
            "to_phone": to_phone,
            "member_name": member_name,
            "class_title": class_title,
        }

    # ── Payment Recovery Auto-Call ─────────────────────────────────────────

    async def initiate_payment_recovery_call(
        self,
        member_id: str,
        transaction_id: str,
        schema_override: str | None = None,
    ) -> dict:
        """Place an outbound call for failed-payment recovery.

        The member can press 1 to receive an SMS with a payment-update link.
        """
        call_id = str(uuid.uuid4())
        db_kwargs = {"schema_override": schema_override} if schema_override else {}

        from app.services.members.phi_helpers import decrypt_phone
        async with get_tenant_db(**db_kwargs) as db:
            member = await db.fetchrow(
                "SELECT id, first_name, last_name, phone_enc FROM members WHERE id = $1",
                member_id,
            )
            if not member:
                raise ValueError(f"Member {member_id} not found")
            to_phone = decrypt_phone(member)
            if not to_phone:
                raise ValueError(f"Member {member_id} has no phone number on file")

            txn = await db.fetchrow(
                "SELECT id, amount_cents, currency, status FROM transactions WHERE id = $1",
                transaction_id,
            )
            if not txn:
                raise ValueError(f"Transaction {transaction_id} not found")

        member_name = f"{member['first_name'] or ''} {member['last_name'] or ''}".strip()
        amount_cents = txn["amount_cents"] or 0
        amount_str = f"${amount_cents / 100:.2f}"

        if not self._is_configured():
            logger.warning(
                "Payment recovery call skipped — Twilio not configured",
                member_id=member_id,
                transaction_id=transaction_id,
            )
            return {
                "call_id": call_id,
                "status": "skipped",
                "reason": "twilio_not_configured",
            }

        twiml_url = (
            f"{settings.API_URL}/webhooks/twilio/voice/payment-twiml"
            f"?transaction_id={transaction_id}"
            f"&member_name={_url_encode(member_name)}"
            f"&amount={_url_encode(amount_str)}"
        )
        status_url = f"{settings.API_URL}/webhooks/twilio/voice/status"

        twilio_sid = None
        call_status = "initiated"
        error_message = None

        try:
            client = self._get_twilio_client()
            call = await asyncio.to_thread(
                lambda: client.calls.create(
                    to=to_phone,
                    from_=settings.TWILIO_PHONE_NUMBER,
                    url=twiml_url,
                    status_callback=status_url,
                    status_callback_event=["initiated", "ringing", "answered", "completed"],
                    timeout=60,
                    machine_detection="Enable",
                )
            )
            twilio_sid = call.sid
            logger.info(
                "Payment recovery call initiated",
                call_sid=twilio_sid,
                member_id=member_id,
                transaction_id=transaction_id,
            )
        except Exception as e:
            call_status = "failed"
            error_message = str(e)
            logger.error(
                "Payment recovery call failed",
                member_id=member_id,
                transaction_id=transaction_id,
                error=str(e),
            )

        async with get_tenant_db(**db_kwargs) as db:
            await db.execute(
                """
                INSERT INTO voice_calls
                    (id, member_id, call_type, twilio_sid, to_phone,
                     status, reference_id, reference_type, error_message)
                VALUES ($1, $2, 'payment_recovery', $3, $4, $5, $6, 'transaction', $7)
                """,
                call_id, member_id, twilio_sid, to_phone,
                call_status, transaction_id, error_message,
            )

        return {
            "call_id": call_id,
            "twilio_sid": twilio_sid,
            "status": call_status,
            "to_phone": to_phone,
            "member_name": member_name,
            "amount": amount_str,
        }

    # ── Gather Handlers (called by webhook endpoints) ──────────────────────

    async def handle_waitlist_gather(
        self,
        booking_id: str,
        digits: str,
        schema_override: str | None = None,
    ) -> str:
        """Process DTMF digits from the waitlist confirmation call.

        Returns TwiML XML string for the next voice response.
        """
        db_kwargs = {"schema_override": schema_override} if schema_override else {}

        if digits == "1":
            # Member confirmed — finalize the booking
            async with get_tenant_db(**db_kwargs) as db:
                updated = await db.fetchrow(
                    """
                    UPDATE bookings
                    SET status = 'booked',
                        waitlist_position = NULL
                    WHERE id = $1 AND status IN ('waitlisted')
                    RETURNING id, member_id, class_session_id
                    """,
                    booking_id,
                )

                if updated:
                    # Log the voice confirmation
                    await db.execute(
                        """
                        UPDATE voice_calls
                        SET status = 'completed', digits_pressed = '1',
                            completed_at = NOW()
                        WHERE reference_id = $1 AND reference_type = 'booking'
                          AND call_type = 'waitlist'
                        """,
                        booking_id,
                    )
                    logger.info(
                        "Waitlist call: member confirmed",
                        booking_id=booking_id,
                        member_id=str(updated["member_id"]),
                    )

            return _twiml_say(
                "Great! Your spot is confirmed. We look forward to seeing you in class. Goodbye!"
            )

        elif digits == "2":
            # Member declined — mark booking as declined and escalate
            async with get_tenant_db(**db_kwargs) as db:
                updated = await db.fetchrow(
                    """
                    UPDATE bookings
                    SET status = 'cancelled',
                        waitlist_position = NULL
                    WHERE id = $1 AND status IN ('waitlisted', 'booked')
                    RETURNING id, member_id, class_session_id
                    """,
                    booking_id,
                )

                if updated:
                    await db.execute(
                        """
                        UPDATE voice_calls
                        SET status = 'completed', digits_pressed = '2',
                            completed_at = NOW()
                        WHERE reference_id = $1 AND reference_type = 'booking'
                          AND call_type = 'waitlist'
                        """,
                        booking_id,
                    )
                    logger.info(
                        "Waitlist call: member declined",
                        booking_id=booking_id,
                        member_id=str(updated["member_id"]),
                    )

            # Promote the next person in line
            await self._escalate_waitlist(booking_id, schema_override=schema_override)

            return _twiml_say(
                "No problem. We have released your spot. Goodbye!"
            )

        else:
            # Invalid input — re-prompt once
            return self._generate_waitlist_twiml(
                member_name="",  # skip name on re-prompt
                class_title="",
                booking_id=booking_id,
                is_retry=True,
            )

    async def handle_payment_gather(
        self,
        transaction_id: str,
        digits: str,
        member_id: str | None = None,
        schema_override: str | None = None,
    ) -> str:
        """Process DTMF digits from the payment recovery call.

        Returns TwiML XML string.
        """
        db_kwargs = {"schema_override": schema_override} if schema_override else {}

        if digits == "1":
            # Member wants an SMS with the payment link
            async with get_tenant_db(**db_kwargs) as db:
                # Resolve member from voice_calls record if not passed
                if not member_id:
                    vc = await db.fetchrow(
                        """
                        SELECT member_id FROM voice_calls
                        WHERE reference_id = $1 AND reference_type = 'transaction'
                          AND call_type = 'payment_recovery'
                        ORDER BY created_at DESC LIMIT 1
                        """,
                        transaction_id,
                    )
                    member_id = str(vc["member_id"]) if vc else None

                if member_id:
                    from app.services.members.phi_helpers import decrypt_phone
                    member = await db.fetchrow(
                        "SELECT phone_enc FROM members WHERE id = $1", member_id
                    )
                    member_phone = decrypt_phone(member) if member else None
                    if member_phone:
                        payment_link = (
                            f"{settings.APP_URL}/billing/update-payment"
                            f"?txn={transaction_id}"
                        )
                        # Send the SMS via SmsService
                        try:
                            from app.services.marketing.campaign_service import SmsService
                            sms = SmsService()
                            await sms.send_sms(
                                to_phone=member_phone,
                                body=(
                                    f"AuraFlow: Update your payment method here: {payment_link}\n"
                                    f"This link expires in 24 hours."
                                ),
                                member_id=member_id,
                                sms_type="transactional",
                            )
                            logger.info(
                                "Payment recovery SMS sent",
                                member_id=member_id,
                                transaction_id=transaction_id,
                            )
                        except Exception as e:
                            logger.error(
                                "Payment recovery SMS failed",
                                member_id=member_id,
                                error=str(e),
                            )

                # Update call record
                await db.execute(
                    """
                    UPDATE voice_calls
                    SET status = 'completed', digits_pressed = '1',
                        completed_at = NOW()
                    WHERE reference_id = $1 AND reference_type = 'transaction'
                      AND call_type = 'payment_recovery'
                    """,
                    transaction_id,
                )

            return _twiml_say(
                "We have sent you a text message with a link to update your payment method. "
                "Thank you, and have a great day. Goodbye!"
            )

        else:
            # Any other key or no response — end gracefully
            async with get_tenant_db(**db_kwargs) as db:
                await db.execute(
                    """
                    UPDATE voice_calls
                    SET status = 'completed', digits_pressed = $1,
                        completed_at = NOW()
                    WHERE reference_id = $2 AND reference_type = 'transaction'
                      AND call_type = 'payment_recovery'
                    """,
                    digits, transaction_id,
                )

            return _twiml_say(
                "No problem. You can update your payment method anytime by logging "
                "into your account. Goodbye!"
            )

    # ── Call Status Handler ────────────────────────────────────────────────

    async def handle_call_status(
        self,
        call_sid: str,
        call_status: str,
        schema_override: str | None = None,
    ) -> None:
        """Process Twilio call status callbacks.

        Key statuses: initiated, ringing, in-progress, completed,
        busy, no-answer, canceled, failed.
        """
        logger.info("Voice call status update", call_sid=call_sid, status=call_status)

        # Map Twilio call statuses to our internal statuses
        status_map = {
            "initiated": "initiated",
            "ringing": "ringing",
            "in-progress": "in_progress",
            "completed": "completed",
            "busy": "no_answer",
            "no-answer": "no_answer",
            "canceled": "cancelled",
            "failed": "failed",
        }
        our_status = status_map.get(call_status, call_status)

        # Search across tenant schemas (call could belong to any org)
        async with get_global_db() as db:
            schemas = await db.fetch(
                "SELECT schema_name FROM af_global.organizations "
                "WHERE status IN ('active', 'trial')"
            )

        for schema_row in schemas:
            schema = schema_row["schema_name"]
            try:
                async with get_tenant_db(schema_override=schema) as db:
                    updated = await db.fetchrow(
                        """
                        UPDATE voice_calls
                        SET status = $1
                        WHERE twilio_sid = $2
                        RETURNING id, call_type, reference_id, reference_type, member_id
                        """,
                        our_status, call_sid,
                    )

                    if updated:
                        # If no-answer or failed on a waitlist call, escalate
                        if (
                            our_status in ("no_answer", "failed", "cancelled")
                            and updated["call_type"] == "waitlist"
                            and updated["reference_type"] == "booking"
                        ):
                            booking_id = str(updated["reference_id"])
                            # Mark booking as cancelled (timeout)
                            await db.execute(
                                """
                                UPDATE bookings
                                SET status = 'cancelled',
                                    waitlist_position = NULL
                                WHERE id = $1
                                  AND status IN ('waitlisted')
                                """,
                                booking_id,
                            )
                            logger.info(
                                "Waitlist call no-answer — escalating",
                                call_sid=call_sid,
                                booking_id=booking_id,
                            )
                            await self._escalate_waitlist(
                                booking_id, schema_override=schema,
                            )

                        break  # Found the tenant, stop searching
            except Exception as e:
                logger.warning(
                    "Voice call status update failed for schema",
                    schema=schema,
                    call_sid=call_sid,
                    error=str(e),
                )

    # ── TwiML Generators ──────────────────────────────────────────────────

    def _generate_waitlist_twiml(
        self,
        member_name: str,
        class_title: str,
        booking_id: str,
        is_retry: bool = False,
    ) -> str:
        """Generate TwiML for waitlist confirmation call.

        Uses <Gather> to collect a single keypress with a 15-second timeout.
        """
        gather_url = (
            f"{settings.API_URL}/webhooks/twilio/voice/gather"
            f"?type=waitlist&booking_id={booking_id}"
        )

        if is_retry:
            prompt = (
                "Sorry, we didn't get that. "
                "Press 1 to confirm your spot, or press 2 to decline."
            )
        else:
            greeting = f"Hello {xml_escape(member_name)}. " if member_name else "Hello. "
            prompt = (
                f"{greeting}Great news! A spot has opened up in "
                f"{xml_escape(class_title)}. "
                "Press 1 to confirm your spot, or press 2 to decline. "
                "You have 15 seconds to respond."
            )

        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            f'<Gather numDigits="1" timeout="15" action="{xml_escape(gather_url)}" method="POST">'
            f"<Say voice=\"alice\">{prompt}</Say>"
            "</Gather>"
            "<Say voice=\"alice\">"
            "We did not receive your response. Your spot has been released. Goodbye!"
            "</Say>"
            "</Response>"
        )
        return twiml

    def _generate_payment_twiml(
        self,
        member_name: str,
        amount: str,
        transaction_id: str,
    ) -> str:
        """Generate TwiML for payment recovery call.

        Offers to send an SMS with a payment update link.
        """
        gather_url = (
            f"{settings.API_URL}/webhooks/twilio/voice/gather"
            f"?type=payment&transaction_id={transaction_id}"
        )

        greeting = f"Hello {xml_escape(member_name)}. " if member_name else "Hello. "
        prompt = (
            f"{greeting}This is AuraFlow calling about a recent payment of "
            f"{xml_escape(amount)} that could not be processed. "
            "Press 1 to receive a text message with a link to update your payment method. "
            "Or simply hang up to handle this later."
        )

        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            f'<Gather numDigits="1" timeout="15" action="{xml_escape(gather_url)}" method="POST">'
            f"<Say voice=\"alice\">{prompt}</Say>"
            "</Gather>"
            "<Say voice=\"alice\">"
            "No response received. You can update your payment method anytime "
            "by logging into your account. Goodbye!"
            "</Say>"
            "</Response>"
        )
        return twiml

    # ── Waitlist Escalation ────────────────────────────────────────────────

    async def _escalate_waitlist(
        self,
        declined_booking_id: str,
        schema_override: str | None = None,
    ) -> None:
        """When a waitlisted member declines or doesn't answer, promote
        the next person and initiate a call to them.

        Falls back to SMS if the next member has no phone or the call fails.
        """
        db_kwargs = {"schema_override": schema_override} if schema_override else {}

        async with get_tenant_db(**db_kwargs) as db:
            # Find the session from the declined booking
            declined = await db.fetchrow(
                "SELECT class_session_id FROM bookings WHERE id = $1",
                declined_booking_id,
            )
            if not declined:
                return

            session_id = str(declined["class_session_id"])

            # Get the next waitlisted member (FIFO or by position)
            next_booking = await db.fetchrow(
                """
                SELECT b.id AS booking_id, b.member_id,
                       m.first_name, m.last_name, m.phone_enc, m.email
                FROM bookings b
                JOIN members m ON m.id = b.member_id
                WHERE b.class_session_id = $1
                  AND b.status = 'waitlisted'
                ORDER BY b.waitlist_position ASC NULLS LAST, b.booked_at ASC
                LIMIT 1
                """,
                session_id,
            )

            if not next_booking:
                logger.info(
                    "Waitlist escalation: no more waitlisted members",
                    session_id=session_id,
                )
                return

            next_booking_id = str(next_booking["booking_id"])
            next_member_id = str(next_booking["member_id"])
            member_name = (
                f"{next_booking['first_name'] or ''} {next_booking['last_name'] or ''}".strip()
            )

            # Mark booking as waitlisted (awaiting voice confirmation)
            await db.execute(
                """
                UPDATE bookings
                SET status = 'waitlisted'
                WHERE id = $1
                """,
                next_booking_id,
            )

        logger.info(
            "Waitlist escalation: calling next member",
            session_id=session_id,
            booking_id=next_booking_id,
            member_id=next_member_id,
        )

        # Attempt to call the next member
        next_member_phone = decrypt_phone(next_booking)
        if next_member_phone:
            try:
                await self.initiate_waitlist_call(
                    member_id=next_member_id,
                    session_id=session_id,
                    booking_id=next_booking_id,
                    schema_override=schema_override,
                )
                return
            except Exception as e:
                logger.warning(
                    "Waitlist escalation call failed, falling back to SMS",
                    member_id=next_member_id,
                    error=str(e),
                )

        # Fallback: send SMS notification
        try:
            from app.services.marketing.campaign_service import SmsService
            sms = SmsService()

            session_info = None
            async with get_tenant_db(**db_kwargs) as db:
                session_info = await db.fetchrow(
                    "SELECT title, starts_at FROM class_sessions WHERE id = $1",
                    session_id,
                )

            class_title = session_info["title"] if session_info else "your class"
            confirm_link = (
                f"{settings.APP_URL}/bookings/{next_booking_id}/confirm"
            )

            await sms.send_sms(
                to_phone=next_member_phone or "",
                body=(
                    f"AuraFlow: A spot opened up in {class_title}! "
                    f"Confirm your spot here: {confirm_link}\n"
                    f"This offer expires in 30 minutes."
                ),
                member_id=next_member_id,
                sms_type="transactional",
            )
            logger.info(
                "Waitlist escalation SMS sent",
                member_id=next_member_id,
                booking_id=next_booking_id,
            )
        except Exception as e:
            logger.error(
                "Waitlist escalation SMS also failed",
                member_id=next_member_id,
                error=str(e),
            )


# ── Module-level helpers ───────────────────────────────────────────────────

def _url_encode(value: str) -> str:
    """URL-encode a string for use in query parameters."""
    from urllib.parse import quote
    return quote(value, safe="")


def _twiml_say(message: str) -> str:
    """Wrap a message in a minimal TwiML <Response><Say> envelope."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"<Say voice=\"alice\">{xml_escape(message)}</Say>"
        "</Response>"
    )
