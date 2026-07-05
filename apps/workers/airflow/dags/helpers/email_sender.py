"""AuraFlow Airflow — Email Sender

Sends payout report emails via SendGrid HTTP API.
Falls back to logging if SendGrid is not configured.
"""
import logging
import os

import requests

logger = logging.getLogger("auraflow.airflow.email")

SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")
FROM_EMAIL = os.environ.get("SENDGRID_FROM_EMAIL", "hello@example.com")
FROM_NAME = os.environ.get("SENDGRID_FROM_NAME", "AuraFlow")


def send_payout_email(to_email: str, subject: str, html_content: str) -> bool:
    """Send an email via SendGrid. Returns True on success."""
    if not SENDGRID_API_KEY:
        logger.warning("SendGrid not configured — skipping email to %s", to_email)
        return False

    resp = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={
            "Authorization": f"Bearer {SENDGRID_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {"email": FROM_EMAIL, "name": FROM_NAME},
            "subject": subject,
            "content": [{"type": "text/html", "value": html_content}],
        },
        timeout=15,
    )

    if resp.status_code in (200, 202):
        logger.info("Payout email sent to %s: %s", to_email, subject)
        return True
    else:
        logger.error(
            "SendGrid error %s: %s", resp.status_code, resp.text[:200]
        )
        return False
