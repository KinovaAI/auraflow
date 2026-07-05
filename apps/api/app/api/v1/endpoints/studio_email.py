"""AuraFlow — Studio Email Inbox Endpoints

Per-tenant email inbox: connect IMAP/SMTP, list/manage inbox, AI first
responder, manual replies, assignment.  All endpoints require owner,
admin, or front_desk role.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.v1.dependencies.rbac import require_permission
from app.services.email.studio_inbox_service import StudioInboxService

router = APIRouter()
svc = StudioInboxService()


# ── Request Models ───────────────────────────────────────────────────────

class ConnectEmailAccount(BaseModel):
    email_address: str
    display_name: str = "Studio"
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    imap_use_tls: bool = True
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    smtp_use_tls: bool = True
    username: str = ""
    password: str


class ManualReply(BaseModel):
    body: str


class AssignEmail(BaseModel):
    assigned_to: str  # user_id


# ── Account Management ──────────────────────────────────────────────────

@router.post("/connect")
async def connect_email(
    body: ConnectEmailAccount,
    rbac=Depends(require_permission("communications.connect_email")),
):
    """Connect a studio email account (IMAP/SMTP credentials)."""
    schema = f"af_tenant_{rbac['org_slug']}"
    data = body.model_dump()
    if not data.get("username"):
        data["username"] = data["email_address"]
    try:
        account = await svc.connect_email_account(schema, data)
        return {"data": account}
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(status_code=409, detail="Email account already connected")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/status")
async def email_status(
    rbac=Depends(require_permission("communications.view_status")),
):
    """Get connection status for the studio email account."""
    schema = f"af_tenant_{rbac['org_slug']}"
    status = await svc.get_account_status(schema)
    return {"data": status}


@router.post("/test")
async def test_email_connection(
    rbac=Depends(require_permission("communications.test_email")),
):
    """Test the connected email account's IMAP/SMTP."""
    schema = f"af_tenant_{rbac['org_slug']}"
    status = await svc.get_account_status(schema)
    if not status.get("connected"):
        raise HTTPException(status_code=404, detail="No email account connected")
    result = await svc.test_connection(schema, str(status["id"]))
    return {"data": result}


@router.post("/disconnect")
async def disconnect_email(
    rbac=Depends(require_permission("communications.disconnect_email")),
):
    """Disconnect the studio email account."""
    schema = f"af_tenant_{rbac['org_slug']}"
    status = await svc.get_account_status(schema)
    if not status.get("connected"):
        raise HTTPException(status_code=404, detail="No email account connected")
    ok = await svc.disconnect_email_account(schema, str(status["id"]))
    if not ok:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"status": "disconnected"}


# ── Inbox ────────────────────────────────────────────────────────────────

@router.get("/inbox")
async def list_inbox(
    status: Optional[str] = Query(None),
    classification: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    rbac=Depends(require_permission("communications.view_inbox")),
):
    """List studio inbox emails with optional filters."""
    schema = f"af_tenant_{rbac['org_slug']}"
    emails = await svc.list_emails(schema, status, classification, limit, offset)
    return {"data": emails}


@router.get("/inbox/{message_id}")
async def get_inbox_email(
    message_id: str,
    rbac=Depends(require_permission("communications.view_inbox")),
):
    """Get email detail with full thread."""
    schema = f"af_tenant_{rbac['org_slug']}"
    email = await svc.get_email(schema, message_id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    return {"data": email}


@router.post("/inbox/{message_id}/reply")
async def reply_to_email(
    message_id: str,
    body: ManualReply,
    rbac=Depends(require_permission("communications.reply_inbox")),
):
    """Send a manual reply to an inbox email."""
    schema = f"af_tenant_{rbac['org_slug']}"
    user_id = rbac["user_id"]
    try:
        result = await svc.send_manual_reply(schema, message_id, body.body, user_id)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/inbox/{message_id}/resolve")
async def resolve_email(
    message_id: str,
    rbac=Depends(require_permission("communications.manage_inbox")),
):
    """Mark an email as resolved."""
    schema = f"af_tenant_{rbac['org_slug']}"
    user_id = rbac["user_id"]
    result = await svc.mark_as_resolved(schema, message_id, user_id)
    if not result:
        raise HTTPException(status_code=404, detail="Email not found")
    return {"data": result}


@router.post("/inbox/{message_id}/assign")
async def assign_email(
    message_id: str,
    body: AssignEmail,
    rbac=Depends(require_permission("communications.manage_inbox")),
):
    """Assign an email to a team member."""
    schema = f"af_tenant_{rbac['org_slug']}"
    result = await svc.reassign_email(schema, message_id, body.assigned_to)
    if not result:
        raise HTTPException(status_code=404, detail="Email not found")
    return {"data": result}


class ReclassifyEmail(BaseModel):
    classification: str


@router.post("/inbox/{message_id}/reclassify")
async def reclassify_email(
    message_id: str,
    body: ReclassifyEmail,
    rbac=Depends(require_permission("communications.manage_inbox")),
):
    """Override AI classification for an email."""
    valid = ["spam", "general_question", "booking_inquiry", "pricing_question",
             "schedule_question", "engagement_reply", "complaint", "feedback", "cancellation"]
    if body.classification not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid classification. Must be one of: {', '.join(valid)}")
    schema = f"af_tenant_{rbac['org_slug']}"
    from app.db.session import get_tenant_db
    async with get_tenant_db(schema_override=schema) as db:
        row = await db.fetchrow(
            """UPDATE studio_inbox_messages
               SET classification = $1, status = CASE WHEN $1 = 'spam' THEN 'spam' ELSE 'needs_attention' END,
                   updated_at = NOW()
               WHERE id = $2
               RETURNING id, classification, status""",
            body.classification, message_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Email not found")
    return {"data": dict(row)}


# ── Stats ────────────────────────────────────────────────────────────────

@router.get("/stats")
async def inbox_stats(
    rbac=Depends(require_permission("communications.view_stats")),
):
    """Inbox stats: unread, AI resolved, needs attention, total this week."""
    schema = f"af_tenant_{rbac['org_slug']}"
    stats = await svc.get_stats(schema)
    return {"data": stats}


@router.get("/team")
async def get_team_members(
    rbac=Depends(require_permission("communications.view_team")),
):
    """Get team members for email assignment."""
    from app.db.session import get_global_db
    org_slug = rbac["org_slug"]
    async with get_global_db() as db:
        rows = await db.fetch(
            """
            SELECT u.id, u.first_name, u.last_name, u.email, ou.role
            FROM af_global.organization_users ou
            JOIN af_global.users u ON u.id = ou.user_id
            JOIN af_global.organizations o ON o.id = ou.organization_id
            WHERE o.slug = $1 AND ou.is_active = TRUE
              AND ou.role IN ('owner', 'admin', 'instructor', 'front_desk')
            ORDER BY ou.role, u.first_name
            """,
            org_slug,
        )
    return {"data": [dict(r) for r in rows]}
