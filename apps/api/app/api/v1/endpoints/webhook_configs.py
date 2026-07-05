"""AuraFlow — Webhook Configuration Endpoints

Admin/owner endpoints for managing outbound webhook configs and
viewing delivery history with manual retry support.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.v1.dependencies.auth import get_current_user
from app.api.v1.dependencies.rbac import require_permission
from app.services.webhooks.webhook_delivery_service import WebhookDeliveryService

router = APIRouter()
svc = WebhookDeliveryService()


# ── Schemas ──────────────────────────────────────────────────────────────


class WebhookConfigCreate(BaseModel):
    url: str
    events: list[str]
    secret: Optional[str] = None


class WebhookConfigUpdate(BaseModel):
    url: Optional[str] = None
    events: Optional[list[str]] = None
    secret: Optional[str] = None
    is_active: Optional[bool] = None


# ── Config Endpoints ─────────────────────────────────────────────────────


@router.get("")
async def list_webhook_configs(
    _=Depends(require_permission("settings.manage_webhooks")),
):
    """List all webhook configurations for the current tenant."""
    configs = await svc.list_configs()
    return {"data": configs}


@router.post("", status_code=201)
async def create_webhook_config(
    request: WebhookConfigCreate,
    user=Depends(get_current_user),
    _=Depends(require_permission("settings.manage_webhooks")),
):
    """Create a new webhook configuration."""
    config = await svc.create_config(
        url=request.url,
        events=request.events,
        secret=request.secret,
        created_by=user.get("sub"),
    )
    return {"data": config}


@router.put("/{config_id}")
async def update_webhook_config(
    config_id: str,
    request: WebhookConfigUpdate,
    _=Depends(require_permission("settings.manage_webhooks")),
):
    """Update a webhook configuration."""
    config = await svc.update_config(
        config_id, request.model_dump(exclude_unset=True)
    )
    if not config:
        raise HTTPException(status_code=404, detail="Webhook config not found")
    return {"data": config}


@router.delete("/{config_id}", status_code=204)
async def delete_webhook_config(
    config_id: str,
    _=Depends(require_permission("settings.manage_webhooks")),
):
    """Delete a webhook configuration and all its deliveries."""
    deleted = await svc.delete_config(config_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Webhook config not found")


# ── Delivery Endpoints ───────────────────────────────────────────────────


@router.get("/deliveries")
async def list_webhook_deliveries(
    config_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    _=Depends(require_permission("settings.manage_webhooks")),
):
    """List webhook deliveries with optional config/status filters."""
    deliveries = await svc.list_deliveries(
        config_id=config_id,
        status=status,
        limit=limit,
    )
    return {"data": deliveries}


@router.post("/deliveries/{delivery_id}/retry")
async def retry_webhook_delivery(
    delivery_id: str,
    _=Depends(require_permission("settings.manage_webhooks")),
):
    """Manually retry a failed or dead-letter webhook delivery."""
    delivery = await svc.retry_delivery(delivery_id)
    if not delivery:
        raise HTTPException(status_code=404, detail="Webhook delivery not found")
    return {"data": delivery}
