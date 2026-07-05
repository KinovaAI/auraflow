"""AuraFlow — Mailchimp Integration Endpoints

Connect/disconnect Mailchimp, check status, and trigger bulk syncs.
All endpoints require JWT auth with owner or admin role.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.v1.dependencies.auth import get_current_user
from app.api.v1.dependencies.rbac import require_permission
from app.core.logging import logger
from app.services.integrations.mailchimp_service import mailchimp_service

router = APIRouter(prefix="/mailchimp")


# ── Schemas ──────────────────────────────────────────────────────────────────

class MailchimpConnect(BaseModel):
    api_key: str
    list_id: str


class MailchimpStatusResponse(BaseModel):
    connected: bool
    list_id: Optional[str] = None
    list_name: Optional[str] = None
    member_count: Optional[int] = None
    connected_at: Optional[str] = None
    error: Optional[str] = None


class MailchimpSyncResponse(BaseModel):
    synced: int
    total: int


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/connect", response_model=MailchimpStatusResponse)
async def connect_mailchimp(
    body: MailchimpConnect,
    user=Depends(require_permission("integrations.connect_mailchimp")),
):
    """Connect the organization's Mailchimp account."""
    org_slug = user.get("org_slug")
    if not org_slug:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No organization context")
    from app.db.session import get_global_db
    async with get_global_db() as db:
        org_id = await db.fetchval(
            "SELECT id FROM af_global.organizations WHERE slug = $1", org_slug
        )
    if not org_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organization not found")
    org_id = str(org_id)

    try:
        result = await mailchimp_service.connect(org_id, body.api_key, body.list_id)
        return MailchimpStatusResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Mailchimp connect error", org_id=org_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to connect to Mailchimp",
        )


@router.get("/status", response_model=MailchimpStatusResponse)
async def get_mailchimp_status(
    user=Depends(require_permission("integrations.view_mailchimp")),
):
    """Check Mailchimp connection status."""
    org_slug = user.get("org_slug")
    if not org_slug:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No organization context")
    from app.db.session import get_global_db
    async with get_global_db() as db:
        org_id = await db.fetchval(
            "SELECT id FROM af_global.organizations WHERE slug = $1", org_slug
        )
    if not org_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organization not found")
    org_id = str(org_id)

    result = await mailchimp_service.get_status(org_id)
    return MailchimpStatusResponse(**result)


@router.post("/sync-all", response_model=MailchimpSyncResponse)
async def sync_all_members(
    user=Depends(require_permission("integrations.sync_mailchimp")),
):
    """Trigger a bulk sync of all active members to Mailchimp."""
    org_slug = user.get("org_slug")
    if not org_slug:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No organization context")
    from app.db.session import get_global_db
    async with get_global_db() as db:
        org_id = await db.fetchval(
            "SELECT id FROM af_global.organizations WHERE slug = $1", org_slug
        )
    if not org_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organization not found")
    org_id = str(org_id)

    schema_name = f"af_tenant_{org_slug}"

    try:
        from app.workers.tasks.mailchimp_sync import mailchimp_bulk_sync
        mailchimp_bulk_sync.delay(schema_name)
        logger.info("Mailchimp bulk sync triggered", org_id=org_id, schema=schema_name)
        return MailchimpSyncResponse(synced=0, total=0)
    except Exception as e:
        logger.error("Mailchimp bulk sync trigger failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to trigger bulk sync",
        )


@router.post("/disconnect")
async def disconnect_mailchimp(
    user=Depends(require_permission("integrations.disconnect_mailchimp")),
):
    """Disconnect Mailchimp from the organization."""
    org_slug = user.get("org_slug")
    if not org_slug:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No organization context")
    from app.db.session import get_global_db
    async with get_global_db() as db:
        org_id = await db.fetchval(
            "SELECT id FROM af_global.organizations WHERE slug = $1", org_slug
        )
    if not org_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organization not found")
    org_id = str(org_id)

    await mailchimp_service.disconnect(org_id)
    return {"disconnected": True}
