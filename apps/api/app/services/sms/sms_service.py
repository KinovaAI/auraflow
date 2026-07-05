"""AuraFlow — SMS Service (Twilio)

Send transactional SMS messages via Twilio.  When Twilio credentials are not
configured the methods log a warning and return ``None`` instead of raising.
"""
from __future__ import annotations

from typing import Optional

from app.core.config import settings
from app.core.logging import logger


def _get_client():
    """Return a Twilio REST client, or None if not configured."""
    if not all([
        settings.TWILIO_ACCOUNT_SID,
        settings.TWILIO_AUTH_TOKEN,
        settings.TWILIO_PHONE_NUMBER,
    ]):
        logger.warning("Twilio is not configured — SMS will not be sent")
        return None

    from twilio.rest import Client
    return Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)


def _normalize_phone(number: str) -> str:
    """Normalize a phone number to E.164 format (+1XXXXXXXXXX)."""
    import re
    digits = re.sub(r'\D', '', number)
    if len(digits) == 10:
        digits = '1' + digits
    if len(digits) == 11 and digits[0] == '1':
        return '+' + digits
    # Already has country code or international
    if number.startswith('+'):
        return number
    return '+' + digits


TWILIO_MESSAGING_SERVICE_SID = "MGda0df3b0aa366ef9acef3900170909ea"


def send_sms(to_number: str, message: str) -> Optional[str]:
    """Send an SMS via Twilio Messaging Service. Returns the message SID on success."""
    client = _get_client()
    if client is None:
        return None

    to_number = _normalize_phone(to_number)

    try:
        msg = client.messages.create(
            body=message,
            messaging_service_sid=TWILIO_MESSAGING_SERVICE_SID,
            to=to_number,
        )
        logger.info("SMS sent", to=to_number, sid=msg.sid)
        return msg.sid
    except Exception as exc:
        logger.error("Failed to send SMS", to=to_number, error=str(exc))
        return None


def send_booking_confirmation(
    to_number: str,
    class_name: str,
    date_str: str,
    time_str: str,
) -> Optional[str]:
    """Send a booking confirmation SMS."""
    message = (
        f"Booking confirmed! You're signed up for {class_name} "
        f"on {date_str} at {time_str}. See you there! — AuraFlow"
    )
    return send_sms(to_number, message)


def send_class_reminder(
    to_number: str,
    class_name: str,
    time_str: str,
) -> Optional[str]:
    """Send a class reminder SMS (typically 2 hours before)."""
    message = (
        f"Reminder: Your {class_name} class starts in 2 hours "
        f"at {time_str}. Don't forget your mat! — AuraFlow"
    )
    return send_sms(to_number, message)


def send_payment_failed(
    to_number: str,
    amount_str: str,
) -> Optional[str]:
    """Notify the member that a payment failed."""
    message = (
        f"AuraFlow: Your payment of {amount_str} could not be processed. "
        f"Please update your payment method in the member portal to avoid "
        f"interruption to your membership."
    )
    return send_sms(to_number, message)
