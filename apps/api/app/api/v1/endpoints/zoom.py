"""AuraFlow — Zoom Integration Endpoints

Connect/disconnect Zoom S2S OAuth, test connection, manage settings.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.v1.dependencies.auth import get_current_user
from app.core.tenant_context import get_organization_id
from app.api.v1.dependencies.rbac import require_permission
from app.services.integrations.zoom_service import ZoomService

router = APIRouter()
zoom_svc = ZoomService()


# ── Schemas ──────────────────────────────────────────────────────────────────

class ZoomConnectRequest(BaseModel):
    account_id: str
    client_id: str
    client_secret: str
    webhook_secret: Optional[str] = None


class ZoomTestRequest(BaseModel):
    account_id: str
    client_id: str
    client_secret: str


class ZoomSettingsUpdate(BaseModel):
    auto_record: Optional[bool] = None
    auto_publish: Optional[bool] = None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/connect")
async def connect_zoom(body: ZoomConnectRequest, rbac=Depends(require_permission("communications.connect_zoom"))):
    """Connect Zoom S2S OAuth credentials."""
    org_id = get_organization_id()
    await zoom_svc.connect(
        org_id,
        account_id=body.account_id,
        client_id=body.client_id,
        client_secret=body.client_secret,
        webhook_secret=body.webhook_secret,
    )
    return {"data": {"connected": True}}


@router.post("/test")
async def test_zoom(body: ZoomTestRequest, rbac=Depends(require_permission("communications.test_zoom"))):
    """Test Zoom credentials without saving."""
    result = await zoom_svc.test_connection(
        account_id=body.account_id,
        client_id=body.client_id,
        client_secret=body.client_secret,
    )
    return {"data": result}


@router.get("/status")
async def zoom_status(rbac=Depends(require_permission("communications.view_status"))):
    """Get Zoom connection status."""
    org_id = get_organization_id()
    status = await zoom_svc.get_connection_status(org_id)
    return {"data": status}


@router.delete("/disconnect")
async def disconnect_zoom(rbac=Depends(require_permission("communications.disconnect_zoom"))):
    """Disconnect Zoom integration."""
    org_id = get_organization_id()
    await zoom_svc.disconnect(org_id)
    return {"data": {"connected": False}}


@router.put("/settings")
async def update_zoom_settings(
    body: ZoomSettingsUpdate, rbac=Depends(require_permission("communications.configure_zoom"))
):
    """Update Zoom org-level settings (auto_record, auto_publish)."""
    org_id = get_organization_id()
    result = await zoom_svc.update_settings(
        org_id,
        auto_record=body.auto_record,
        auto_publish=body.auto_publish,
    )
    return {"data": result}
