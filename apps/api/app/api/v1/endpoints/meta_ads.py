"""AuraFlow — Meta/Facebook Ads Endpoints

AI-powered Facebook & Instagram Ads management. Studio owners set budget,
location, and interests — the AI handles everything else.
All endpoints gated by role + feature flag.
"""
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.api.v1.dependencies.auth import get_current_user
from app.api.v1.dependencies.rbac import require_permission
from app.core.redis import get_redis
from app.core.tenant_context import get_organization_id
from app.services.ads.meta_ads_service import MetaAdsService
from app.services.ads.ai_meta_ads_controller import AIMetaAdsController
from app.services.feature_flags import require_feature

router = APIRouter()

meta_svc = MetaAdsService()
ai_controller = AIMetaAdsController()


# ── Schemas ──────────────────────────────────────────────────────────────────

class ConnectRequest(BaseModel):
    ad_account_id: str


class ConfigUpdate(BaseModel):
    max_monthly_spend_cents: Optional[int] = None
    target_latitude: Optional[float] = None
    target_longitude: Optional[float] = None
    target_radius_miles: Optional[int] = None
    target_age_min: Optional[int] = None
    target_age_max: Optional[int] = None
    target_genders: Optional[list[str]] = None
    target_interests: Optional[list[str]] = None
    class_focus: Optional[list[str]] = None
    brand_voice: Optional[str] = None
    excluded_interests: Optional[list[str]] = None
    approval_threshold_cents: Optional[int] = None
    meta_pixel_id: Optional[str] = None
    default_page_id: Optional[str] = None
    instagram_account_id: Optional[str] = None


# ── Connection ───────────────────────────────────────────────────────────────

@router.get(
    "/connect/status",
    dependencies=[require_feature("marketing.meta_ads")],
)
async def get_connection_status(
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.view_ads")),
):
    """Check if Meta Ads is connected for this organization."""
    org_id = get_organization_id()
    status = await meta_svc.get_connection_status(org_id)
    return {"data": status}


@router.get(
    "/connect/oauth",
    dependencies=[require_feature("marketing.meta_ads")],
)
async def get_oauth_url(
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.manage_ads")),
):
    """Get the Facebook Login consent URL for Meta Ads authorization."""
    org_id = get_organization_id()
    # Generate CSRF token and store org_id mapping in Redis
    csrf_token = secrets.token_urlsafe(32)
    redis = await get_redis()
    if redis:
        await redis.set(f"oauth_csrf:{csrf_token}", org_id, ex=600)
    url = await meta_svc.get_oauth_url(csrf_token)
    return {"data": {"url": url}}


@router.get("/connect/oauth/callback")
async def oauth_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
):
    """Handle OAuth callback from Facebook. Redirects to frontend."""
    # Validate CSRF token and retrieve org_id from Redis
    redis = await get_redis()
    if not redis:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    org_id = await redis.get(f"oauth_csrf:{state}")
    if not org_id:
        raise HTTPException(status_code=403, detail="Invalid or expired OAuth state token")
    await redis.delete(f"oauth_csrf:{state}")
    org_id = org_id.decode() if isinstance(org_id, bytes) else org_id
    try:
        await meta_svc.handle_oauth_callback(org_id, code)
        from app.core.config import settings
        return {"data": {"success": True, "redirect": f"{settings.APP_URL}/dashboard/marketing?tab=facebook-ads&connected=true"}}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/connect",
    dependencies=[require_feature("marketing.meta_ads")],
)
async def set_ad_account_id(
    body: ConnectRequest,
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.manage_ads")),
):
    """Store the Meta Ad Account ID after OAuth connection."""
    org_id = get_organization_id()
    await meta_svc.set_ad_account_id(org_id, body.ad_account_id)
    return {"data": {"ad_account_id": body.ad_account_id}}


@router.delete(
    "/connect",
    dependencies=[require_feature("marketing.meta_ads")],
)
async def disconnect(
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.manage_ads")),
):
    """Disconnect Meta Ads — pauses all campaigns and clears credentials."""
    org_id = get_organization_id()
    await meta_svc.disconnect(org_id)
    return {"data": {"disconnected": True}}


# ── Configuration ────────────────────────────────────────────────────────────

@router.get(
    "/config",
    dependencies=[require_feature("marketing.meta_ads")],
)
async def get_config(
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.view_ads")),
):
    """Get current Meta Ads configuration."""
    org_id = get_organization_id()
    config = await meta_svc.get_config(org_id)
    return {"data": config}


@router.put(
    "/config",
    dependencies=[require_feature("marketing.meta_ads")],
)
async def update_config(
    body: ConfigUpdate,
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.manage_ads")),
):
    """Update Meta Ads configuration (budget, targeting, preferences)."""
    config = await meta_svc.save_config(body.model_dump(exclude_none=True))
    return {"data": config}


@router.post(
    "/config/enable",
    dependencies=[require_feature("marketing.meta_ads")],
)
async def enable_meta_ads(
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.manage_ads")),
):
    """Enable Meta Ads — triggers AI initial campaign setup."""
    org_id = get_organization_id()

    # Verify connected
    status = await meta_svc.get_connection_status(org_id)
    if not status.get("connected"):
        raise HTTPException(status_code=400, detail="Meta Ads not connected — complete Facebook Login first")
    if not status.get("ad_account_id"):
        raise HTTPException(status_code=400, detail="Meta Ad Account ID not set")

    # Mark as active
    await meta_svc.save_config({"is_active": True})

    # Run initial AI setup
    result = await ai_controller.initial_campaign_setup(org_id)
    return {"data": {"enabled": True, "setup": result}}


@router.post(
    "/config/disable",
    dependencies=[require_feature("marketing.meta_ads")],
)
async def disable_meta_ads(
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.manage_ads")),
):
    """Kill switch — pause all campaigns and disable AI management."""
    org_id = get_organization_id()
    paused = await meta_svc.pause_all_campaigns(org_id)
    await meta_svc.save_config({"is_active": False})
    return {"data": {"disabled": True, "campaigns_paused": paused}}


# ── Dashboard ────────────────────────────────────────────────────────────────

@router.get(
    "/campaigns",
    dependencies=[require_feature("marketing.meta_ads")],
)
async def list_campaigns(
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.view_ads")),
):
    """List all Meta Ads campaigns with latest metrics."""
    campaigns = await meta_svc.list_campaigns()
    return {"data": campaigns}


@router.get(
    "/performance/summary",
    dependencies=[require_feature("marketing.meta_ads")],
)
async def get_performance_summary(
    days: int = Query(30, le=365),
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.view_ads")),
):
    """Get aggregate performance summary."""
    summary = await meta_svc.get_performance_summary(days=days)
    return {"data": summary}


@router.get(
    "/performance/daily",
    dependencies=[require_feature("marketing.meta_ads")],
)
async def get_daily_performance(
    days: int = Query(30, le=365),
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.view_ads")),
):
    """Get daily performance time series for charts."""
    daily = await meta_svc.get_daily_performance(days=days)
    return {"data": daily}


@router.get(
    "/budget",
    dependencies=[require_feature("marketing.meta_ads")],
)
async def get_budget_status(
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.view_ads")),
):
    """Get current budget utilization and remaining budget."""
    org_id = get_organization_id()
    budget = await meta_svc.check_budget_remaining(org_id)
    return {"data": budget}


# ── AI Actions ───────────────────────────────────────────────────────────────

@router.get(
    "/actions",
    dependencies=[require_feature("marketing.meta_ads")],
)
async def list_actions(
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.view_ads")),
):
    """Get AI action audit trail."""
    actions = await meta_svc.list_ai_actions(status=status, limit=limit)
    return {"data": actions}


@router.get(
    "/actions/pending",
    dependencies=[require_feature("marketing.meta_ads")],
)
async def list_pending_actions(
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.view_ads")),
):
    """Get AI actions awaiting human approval."""
    actions = await meta_svc.list_ai_actions(status="proposed")
    return {"data": actions}


@router.post(
    "/actions/{action_id}/approve",
    dependencies=[require_feature("marketing.meta_ads")],
)
async def approve_action(
    action_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.manage_ads")),
):
    """Approve a pending AI action."""
    try:
        result = await meta_svc.approve_action(action_id)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/actions/{action_id}/reject",
    dependencies=[require_feature("marketing.meta_ads")],
)
async def reject_action(
    action_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.manage_ads")),
):
    """Reject a pending AI action."""
    try:
        result = await meta_svc.reject_action(action_id)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Manual Controls ──────────────────────────────────────────────────────────

@router.post(
    "/campaigns/{campaign_id}/pause",
    dependencies=[require_feature("marketing.meta_ads")],
)
async def pause_campaign(
    campaign_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.manage_ads")),
):
    """Manually pause a specific campaign."""
    org_id = get_organization_id()
    result = await meta_svc.update_campaign_status(org_id, campaign_id, "PAUSED")
    return {"data": result}


@router.post(
    "/campaigns/{campaign_id}/enable",
    dependencies=[require_feature("marketing.meta_ads")],
)
async def enable_campaign(
    campaign_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.manage_ads")),
):
    """Manually enable a specific campaign."""
    org_id = get_organization_id()
    result = await meta_svc.update_campaign_status(org_id, campaign_id, "ACTIVE")
    return {"data": result}


@router.post(
    "/optimize/trigger",
    dependencies=[require_feature("marketing.meta_ads")],
)
async def trigger_optimization(
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.manage_ads")),
):
    """Manually trigger an AI optimization cycle."""
    org_id = get_organization_id()
    result = await ai_controller.run_optimization_cycle(org_id)
    return {"data": result}


@router.get(
    "/report",
    dependencies=[require_feature("marketing.meta_ads")],
)
async def get_report(
    days: int = Query(30, le=365),
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.view_ads")),
):
    """Get an AI-generated performance report."""
    org_id = get_organization_id()
    result = await ai_controller.generate_performance_report(org_id, days=days)
    return {"data": result}
