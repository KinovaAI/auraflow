"""AuraFlow — SMTP Email Sender

Fallback email transport using SMTP (e.g. Purelymail) when SendGrid is not configured.
Used by both EmailService and auth verification/reset flows.
"""
import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings
from app.core.logging import logger


def is_smtp_configured() -> bool:
    """Check if SMTP credentials are available."""
    return bool(settings.SMTP_USERNAME and settings.SMTP_PASSWORD)


async def send_smtp_email(
    to_email: str,
    subject: str,
    html_content: str,
    plain_content: str | None = None,
    from_email: str | None = None,
    from_name: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> bool:
    """
    Send an email via SMTP. Returns True on success, False on failure.
    """
    from_email = from_email or settings.SMTP_FROM_EMAIL
    from_name = from_name or settings.SMTP_FROM_NAME

    msg = MIMEMultipart("alternative")
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["Reply-To"] = from_email

    # CAN-SPAM: add List-Unsubscribe and other compliance headers
    if extra_headers:
        for hdr_name, hdr_value in extra_headers.items():
            msg[hdr_name] = hdr_value

    if plain_content:
        msg.attach(MIMEText(plain_content, "plain", "utf-8"))
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        smtp = aiosmtplib.SMTP(
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            use_tls=settings.SMTP_USE_TLS,
            start_tls=not settings.SMTP_USE_TLS,  # STARTTLS for port 587
        )
        await smtp.connect()
        await smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        await smtp.send_message(msg)
        await smtp.quit()
        logger.info("Email sent via SMTP", to=to_email, subject=subject)
        return True
    except Exception as e:
        logger.error("SMTP email send failed", to=to_email, error=str(e))
        return False
