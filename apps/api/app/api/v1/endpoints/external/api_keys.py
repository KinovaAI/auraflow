"""AuraFlow — External API Key Management Endpoints

CRUD for API key lifecycle. Uses JWT auth (owner/admin only),
NOT API key auth, since these endpoints manage the keys themselves.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.v1.dependencies.auth import get_current_user
from app.api.v1.dependencies.rbac import require_permission
from app.services.external import api_key_service
from app.services.feature_flags import FeatureFlagService

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────

class APIKeyCreate(BaseModel):
    name: str
    scopes: list[str]
    rate_limit_rpm: int = 60


class APIKeyResponse(BaseModel):
    api_key: Optional[str] = None  # only on create
    key_id: Optional[str] = None
    key_prefix: str
    name: str
    scopes: list[str]
    rate_limit_rpm: int
    is_active: Optional[bool] = None
    created_at: str
    expires_at: Optional[str] = None
    last_used_at: Optional[str] = None
    revoked_at: Optional[str] = None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post(
    "/api-keys",
    status_code=201,
    summary="Create an API key",
)
async def create_api_key(
    body: APIKeyCreate,
    rbac: dict = Depends(require_permission("settings.manage_features")),
):
    """Create a new API key. The raw key is returned only once."""
    # Check feature flag — API access is only on Scale plan
    from app.core.tenant_context import get_organization_id
    org_id = get_organization_id()
    flags = FeatureFlagService()
    if not await flags.is_enabled("integrations.api", org_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API access requires the Scale plan. Upgrade your plan to enable API integrations.",
        )
    result = await api_key_service.create_key(
        name=body.name,
        scopes=body.scopes,
        rate_limit_rpm=body.rate_limit_rpm,
        created_by=UUID(rbac["user_id"]),
    )
    return {"data": result}


@router.get(
    "/api-keys",
    summary="List API keys",
)
async def list_api_keys(
    rbac: dict = Depends(require_permission("settings.manage_features")),
):
    """List all API keys for this organization (keys are never shown)."""
    keys = await api_key_service.list_keys()
    return {"data": keys}


@router.delete(
    "/api-keys/{key_id}",
    status_code=204,
    summary="Revoke an API key",
)
async def revoke_api_key(
    key_id: str,
    rbac: dict = Depends(require_permission("settings.manage_features")),
):
    """Revoke an API key permanently."""
    revoked = await api_key_service.revoke_key(UUID(key_id))
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found or already revoked",
        )
