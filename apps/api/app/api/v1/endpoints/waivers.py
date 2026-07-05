"""AuraFlow — Waiver Management Endpoints

Staff endpoints for managing waiver templates + portal endpoints for members to sign.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.api.v1.dependencies.rbac import require_permission
from app.services.waivers.waiver_service import WaiverService

router = APIRouter()
svc = WaiverService()


# ── Schemas ──────────────────────────────────────────────────────────────────

class CreateTemplateRequest(BaseModel):
    title: str
    content: str
    require_resign: bool = False
    expiration_days: Optional[int] = None


class SignWaiverRequest(BaseModel):
    template_id: str
    signature_text: str


# ── Staff Endpoints (owner/admin) ────────────────────────────────────────────

@router.get("/waivers/templates")
async def list_templates(rbac: dict = Depends(require_permission("waivers.view_templates"))):
    templates = await svc.list_templates()
    return {"data": templates}


@router.get("/waivers/templates/active")
async def get_active_template(rbac: dict = Depends(require_permission("waivers.view_active_template"))):
    template = await svc.get_active_template()
    return {"data": template}


@router.post("/waivers/templates", status_code=201)
async def create_template(
    body: CreateTemplateRequest,
    rbac: dict = Depends(require_permission("waivers.create_template")),
):
    template = await svc.create_template(
        title=body.title,
        content=body.content,
        require_resign=body.require_resign,
        expiration_days=body.expiration_days,
        created_by=rbac.get("user_id"),
    )
    return {"data": template}


@router.get("/waivers/members/{member_id}/status")
async def get_member_waiver_status(
    member_id: str,
    rbac: dict = Depends(require_permission("waivers.view_status")),
):
    """Waiver-signed status for any member. Used by the front-desk UI
    to block selling memberships / booking classes for a member whose
    waiver isn't on file."""
    status = await svc.check_waiver_status(member_id)
    return {
        "data": {
            "signed": bool(status.get("signed")),
            "expired": bool(status.get("expired")),
            "needs_resign": bool(status.get("needs_resign")),
        }
    }


@router.get("/waivers/members/{member_id}/signatures")
async def get_member_signatures(
    member_id: str,
    rbac: dict = Depends(require_permission("waivers.view_signatures")),
):
    signatures = await svc.get_member_signatures(member_id)
    return {"data": signatures}


@router.get("/waivers/unsigned-members")
async def get_unsigned_members(rbac: dict = Depends(require_permission("waivers.view_unsigned"))):
    members = await svc.get_unsigned_members()
    return {"data": members}


# ── Portal Endpoints (member self-service) ───────────────────────────────────

@router.get("/portal/waiver")
async def get_waiver_status(rbac: dict = Depends(require_permission("waivers.view_for_signing"))):
    """Get active waiver template and member's signature status."""
    template = await svc.get_active_template()
    if not template:
        return {"data": {"template": None, "status": {"signed": True, "expired": False, "needs_resign": False}}}

    # Find the member_id from the portal service pattern
    from app.db.session import get_tenant_db
    async with get_tenant_db() as db:
        member = await db.fetchrow(
            "SELECT id FROM members WHERE user_id = $1 AND is_active = TRUE LIMIT 1",
            rbac["user_id"],
        )

    if not member:
        raise HTTPException(status_code=404, detail="Member profile not found")

    status = await svc.check_waiver_status(str(member["id"]))
    return {
        "data": {
            "template": {
                "id": str(template["id"]),
                "title": template["title"],
                "content": template["content"],
                "version": template["version"],
            },
            "status": {
                "signed": status["signed"],
                "expired": status["expired"],
                "needs_resign": status["needs_resign"],
                "signed_at": str(status["signature"]["signed_at"]) if status.get("signature") else None,
                "expires_at": str(status["signature"]["expires_at"]) if status.get("signature") and status["signature"].get("expires_at") else None,
            },
        }
    }


@router.post("/portal/waiver/sign")
async def sign_waiver(
    body: SignWaiverRequest,
    request: Request,
    rbac: dict = Depends(require_permission("waivers.sign")),
):
    """Sign the liability waiver.

    Legal constraint: a waiver signature is only valid when the member
    themselves signs it from their own portal session. The endpoint
    enforces this by:

      1. Authentication required (JWT) — rbac["user_id"] is the
         signer, derived from the access token, NOT any body parameter
         or staff API key. Staff cannot impersonate the signer.
      2. The members row is resolved from rbac["user_id"] only, so a
         staff user who happens to also be a member can ONLY sign
         their own waiver, never someone else's. There is no path to
         pass member_id from the request body.
      3. Audit log captures user_id + email + IP + UA for legal
         attribution.

    A previous version of this endpoint also required
    af_global.users.email_verified = TRUE — that gate was removed on
    2026-04-29 because it created a chicken-and-egg block for new
    members whose verification email had silently failed (platform
    SendGrid was returning 401). Don explicitly clarified that the
    legal requirement is "the right person signs from their own
    session," which the JWT already proves; a separate email_verified
    flag was over-implementation, not part of the original ask.
    """
    from app.db.session import get_tenant_db, get_global_db

    # Pull the user's email for audit trail only — no longer used to
    # block signing.
    async with get_global_db() as gdb:
        user = await gdb.fetchrow(
            "SELECT email FROM af_global.users WHERE id = $1",
            rbac["user_id"],
        )

    async with get_tenant_db() as db:
        member = await db.fetchrow(
            "SELECT id FROM members WHERE user_id = $1 AND is_active = TRUE LIMIT 1",
            rbac["user_id"],
        )

    if not member:
        raise HTTPException(status_code=404, detail="Member profile not found")

    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    try:
        signature = await svc.sign_waiver(
            member_id=str(member["id"]),
            template_id=body.template_id,
            signature_text=body.signature_text,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Audit trail — captures the authenticated user, IP, UA. This is
    # what proves the waiver is legally attributable to the right
    # person: the JWT-authenticated session means the platform
    # already verified ownership of the account at login time.
    try:
        from app.services.platform.audit_service import audit_service
        await audit_service.log(
            action="waiver.signed",
            user_id=rbac["user_id"],
            resource_type="waiver_signature",
            resource_id=str(signature["id"]),
            ip_address=ip_address,
            metadata={
                "member_id": str(member["id"]),
                "email": user["email"] if user else None,
                "user_agent": user_agent,
                "signature_text": body.signature_text,
            },
        )
    except Exception:
        # Audit failure must not undo a legitimate signature.
        pass

    return {"data": signature, "message": "Waiver signed successfully"}
