"""Self-host managed-billing settings (open-core / self-host side).

Admin-facing proxy so a self-hosted operator can connect + check managed billing
without the broker API key ever reaching the browser (it stays server-side in
AURAFLOW_BROKER_API_KEY). Only meaningful when AURAFLOW_BILLING_MODE=managed.
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.config import settings
from app.core.logging import logger
from app.api.v1.dependencies.rbac import require_permission
from app.services.payments.broker_client import broker_client, BrokerClientError

router = APIRouter()


def _managed_enabled() -> bool:
    return settings.AURAFLOW_BILLING_MODE == "managed"


@router.get("/managed-billing/status", dependencies=[Depends(require_permission("payments.view_connect_status"))])
async def managed_billing_status():
    if not _managed_enabled():
        return {"data": {"enabled": False, "mode": settings.AURAFLOW_BILLING_MODE}}
    try:
        status = await broker_client.status()
    except BrokerClientError as e:
        raise HTTPException(status_code=502, detail={"error": str(e)})
    return {"data": {"enabled": True, "mode": "managed", **status}}


@router.get("/managed-billing/connect", dependencies=[Depends(require_permission("payments.setup_connect"))])
async def managed_billing_connect(return_url: str = Query(...)):
    if not _managed_enabled():
        raise HTTPException(status_code=400, detail={"error": "Managed billing is not enabled on this instance."})
    try:
        url = await broker_client.connect_url(return_url)
    except BrokerClientError as e:
        raise HTTPException(status_code=502, detail={"error": str(e)})
    return {"data": {"authorize_url": url}}
