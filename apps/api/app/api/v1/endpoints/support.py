"""AuraFlow — Support Contact Form

Public endpoint for contact/support form submissions.
No authentication required. Rate limited to prevent abuse.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings
from app.core.logging import logger

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

SUPPORT_EMAIL = "alerts@example.com"

VALID_SUBJECTS = {"General", "Billing", "Technical", "Partnership"}


# ── Schemas ─────────────────────────────────────────────────────────────────

class ContactRequest(BaseModel):
    name: str
    email: EmailStr
    subject: str
    message: str
    org_slug: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) < 2:
            raise ValueError("Name must be at least 2 characters")
        if len(v) > 200:
            raise ValueError("Name must be 200 characters or fewer")
        return v

    @field_validator("subject")
    @classmethod
    def subject_valid(cls, v: str) -> str:
        if v not in VALID_SUBJECTS:
            raise ValueError(f"Subject must be one of: {', '.join(sorted(VALID_SUBJECTS))}")
        return v

    @field_validator("message")
    @classmethod
    def message_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) < 10:
            raise ValueError("Message must be at least 10 characters")
        if len(v) > 5000:
            raise ValueError("Message must be 5000 characters or fewer")
        return v


class ContactResponse(BaseModel):
    message: str


# ── Endpoint ────────────────────────────────────────────────────────────────

@router.post(
    "/contact",
    response_model=ContactResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a contact/support form",
)
@limiter.limit("5/hour")
async def submit_contact_form(request: Request, body: ContactRequest):
    """
    Public contact form submission. Sends an email to the AuraFlow support
    inbox with the form contents. Rate limited to 5 submissions per hour
    per IP address.
    """
    org_line = f"<p><strong>Organization:</strong> {body.org_slug}</p>" if body.org_slug else ""

    html_content = f"""
    <h2>New Contact Form Submission</h2>
    <p><strong>From:</strong> {body.name} &lt;{body.email}&gt;</p>
    <p><strong>Subject Category:</strong> {body.subject}</p>
    {org_line}
    <hr />
    <p>{body.message.replace(chr(10), '<br />')}</p>
    <hr />
    <p style="color: #999; font-size: 12px;">
        Sent from the AuraFlow contact form.
    </p>
    """

    plain_content = (
        f"New Contact Form Submission\n\n"
        f"From: {body.name} <{body.email}>\n"
        f"Subject Category: {body.subject}\n"
        f"{'Organization: ' + body.org_slug + chr(10) if body.org_slug else ''}\n"
        f"{body.message}\n"
    )

    email_subject = f"[AuraFlow Contact] {body.subject} — {body.name}"

    # Send via Purelymail SMTP (no SendGrid — Don's standing rule).
    sent = False
    try:
        from app.services.email.smtp_sender import is_smtp_configured, send_smtp_email
        if is_smtp_configured():
            sent = await send_smtp_email(
                to_email=SUPPORT_EMAIL,
                subject=email_subject,
                html_content=html_content,
                plain_content=plain_content,
                extra_headers={"Reply-To": f"{body.name} <{body.email}>"},
            )
        else:
            logger.warning(
                    "Contact form received but no email provider configured",
                    from_email=body.email,
                    subject=body.subject,
                )
    except Exception as e:
        logger.error("Contact form email send failed", error=str(e))

    if not sent:
        # Log the submission even if email failed so it's not lost
        logger.warning(
            "Contact form submission could not be emailed — logged only",
            name=body.name,
            email=body.email,
            subject=body.subject,
            message_preview=body.message[:200],
            org_slug=body.org_slug,
        )

    return ContactResponse(
        message="Thank you for contacting us. We'll get back to you soon."
    )
