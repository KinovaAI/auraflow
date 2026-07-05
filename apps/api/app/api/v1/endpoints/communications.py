"""AuraFlow — Communications Settings Endpoints

Configure SendGrid and Twilio credentials for email/SMS sending.
Credentials are encrypted at rest using pgcrypto.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.v1.dependencies.auth import get_current_user
from app.api.v1.dependencies.rbac import require_permission
from app.core.config import settings
from app.core.logging import logger
from app.core.tenant_context import get_organization_id
from app.db.session import get_global_db
from app.utils.encryption import encrypt_credential, decrypt_credential

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────

class SendGridConnect(BaseModel):
    api_key: str
    from_email: Optional[str] = None
    from_name: Optional[str] = None


class TwilioConnect(BaseModel):
    account_sid: str
    auth_token: str
    phone_number: str


class CommunicationsStatusResponse(BaseModel):
    sendgrid_connected: bool
    sendgrid_from_email: Optional[str] = None
    sendgrid_from_name: Optional[str] = None
    sendgrid_connected_at: Optional[str] = None
    twilio_connected: bool
    twilio_phone_number: Optional[str] = None
    twilio_connected_at: Optional[str] = None


# ── Status ───────────────────────────────────────────────────────────────────

@router.get("/status")
async def get_communications_status(
    rbac=Depends(require_permission("communications.view_status")),
) -> CommunicationsStatusResponse:
    """Get SendGrid and Twilio connection status."""
    org_id = get_organization_id()
    async with get_global_db() as db:
        row = await db.fetchrow(
            """
            SELECT sendgrid_api_key_encrypted, sendgrid_from_email, sendgrid_from_name,
                   sendgrid_connected_at,
                   twilio_account_sid_encrypted, twilio_phone_number, twilio_connected_at
            FROM af_global.organizations WHERE id = $1
            """,
            org_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Organization not found")

    return CommunicationsStatusResponse(
        sendgrid_connected=row["sendgrid_api_key_encrypted"] is not None,
        sendgrid_from_email=row["sendgrid_from_email"],
        sendgrid_from_name=row["sendgrid_from_name"],
        sendgrid_connected_at=row["sendgrid_connected_at"].isoformat() if row["sendgrid_connected_at"] else None,
        twilio_connected=row["twilio_account_sid_encrypted"] is not None,
        twilio_phone_number=row["twilio_phone_number"],
        twilio_connected_at=row["twilio_connected_at"].isoformat() if row["twilio_connected_at"] else None,
    )


# ── SendGrid ─────────────────────────────────────────────────────────────────

@router.post("/sendgrid/connect")
async def connect_sendgrid(
    body: SendGridConnect,
    rbac=Depends(require_permission("communications.connect_email")),
):
    """Store encrypted SendGrid API key and enable email sending."""
    org_id = get_organization_id()
    async with get_global_db() as db:
        encrypted_key = await encrypt_credential(db, body.api_key)
        await db.execute(
            """
            UPDATE af_global.organizations
            SET sendgrid_api_key_encrypted = $1,
                sendgrid_from_email = $2,
                sendgrid_from_name = $3,
                sendgrid_connected_at = NOW()
            WHERE id = $4
            """,
            encrypted_key,
            body.from_email or "",
            body.from_name or "",
            org_id,
        )
    logger.info("SendGrid connected", org_id=org_id)
    return {"status": "connected"}


@router.post("/sendgrid/test")
async def test_sendgrid(
    body: SendGridConnect,
    user=Depends(get_current_user),
    rbac=Depends(require_permission("communications.test_email")),
):
    """Test a SendGrid API key by sending a test email to the current user."""
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail

        if not body.from_email:
            return {"success": False, "message": "From email is required"}
        message = Mail(
            from_email=(body.from_email, body.from_name or ""),
            to_emails=user.get("email", ""),
            subject="AuraFlow — SendGrid Test",
            html_content="<p>Your SendGrid integration is working!</p>",
        )
        sg = SendGridAPIClient(body.api_key)
        response = sg.send(message)
        if response.status_code in (200, 201, 202):
            return {"success": True, "message": f"Test email sent to {user.get('email')}"}
        return {"success": False, "message": f"SendGrid returned status {response.status_code}"}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.delete("/sendgrid/disconnect")
async def disconnect_sendgrid(
    rbac=Depends(require_permission("communications.disconnect_email")),
):
    """Remove SendGrid credentials."""
    org_id = get_organization_id()
    async with get_global_db() as db:
        await db.execute(
            """
            UPDATE af_global.organizations
            SET sendgrid_api_key_encrypted = NULL,
                sendgrid_from_email = NULL,
                sendgrid_from_name = NULL,
                sendgrid_connected_at = NULL,
                sendgrid_webhook_verified = FALSE
            WHERE id = $1
            """,
            org_id,
        )
    logger.info("SendGrid disconnected", org_id=org_id)
    return {"status": "disconnected"}


# ── Twilio ────────────────────────────────────────────────────────────────────

@router.post("/twilio/connect")
async def connect_twilio(
    body: TwilioConnect,
    rbac=Depends(require_permission("communications.connect_sms")),
):
    """Store encrypted Twilio credentials and enable SMS sending."""
    org_id = get_organization_id()
    async with get_global_db() as db:
        encrypted_sid = await encrypt_credential(db, body.account_sid)
        encrypted_token = await encrypt_credential(db, body.auth_token)
        await db.execute(
            """
            UPDATE af_global.organizations
            SET twilio_account_sid_encrypted = $1,
                twilio_auth_token_encrypted = $2,
                twilio_phone_number = $3,
                twilio_connected_at = NOW()
            WHERE id = $4
            """,
            encrypted_sid, encrypted_token, body.phone_number, org_id,
        )
    logger.info("Twilio connected", org_id=org_id)
    return {"status": "connected"}


@router.post("/twilio/test")
async def test_twilio(
    body: TwilioConnect,
    user=Depends(get_current_user),
    rbac=Depends(require_permission("communications.test_sms")),
):
    """Test Twilio credentials by sending a test SMS."""
    try:
        from twilio.rest import Client
        client = Client(body.account_sid, body.auth_token)
        # Send a test message to the configured number itself (or skip if no user phone)
        message = client.messages.create(
            body="AuraFlow — Your Twilio integration is working!",
            from_=body.phone_number,
            to=body.phone_number,  # Send to the studio's own number as a test
        )
        return {"success": True, "message": f"Test SMS sent (SID: {message.sid})"}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.delete("/twilio/disconnect")
async def disconnect_twilio(
    rbac=Depends(require_permission("communications.disconnect_sms")),
):
    """Remove Twilio credentials."""
    org_id = get_organization_id()
    async with get_global_db() as db:
        await db.execute(
            """
            UPDATE af_global.organizations
            SET twilio_account_sid_encrypted = NULL,
                twilio_auth_token_encrypted = NULL,
                twilio_phone_number = NULL,
                twilio_connected_at = NULL
            WHERE id = $1
            """,
            org_id,
        )
    logger.info("Twilio disconnected", org_id=org_id)
    return {"status": "disconnected"}
