"""AuraFlow — AI Usage & Billing Endpoints

Studio owner usage reporting + platform admin billing management.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.v1.dependencies.auth import get_current_user
from app.api.v1.dependencies.rbac import require_permission, require_platform_admin
from app.core.tenant_context import require_tenant_context
from app.services.ai.token_tracking_service import TokenTrackingService
from app.services.payments.stripe_service import StripeService

router = APIRouter()
tracker = TokenTrackingService()
stripe_svc = StripeService()


# ── Schemas ──────────────────────────────────────────────────────────────────

class UpdateTokenRate(BaseModel):
    rate_cents_per_1k: float
    free_tier: int = 50000


# ── Studio Owner Endpoints ───────────────────────────────────────────────────

@router.get(
    "/usage/current",
    dependencies=[Depends(require_permission("billing.view_billing"))],
)
async def get_current_usage(user: dict = Depends(get_current_user)):
    """Get AI token usage for the current billing period."""
    ctx = require_tenant_context()
    data = await tracker.get_org_usage_current_period(ctx.organization_id)
    return {"data": data}


@router.get(
    "/usage/by-service",
    dependencies=[Depends(require_permission("billing.view_billing"))],
)
async def get_usage_by_service(
    days: int = Query(30, ge=1, le=365),
    user: dict = Depends(get_current_user),
):
    """Get AI token usage broken down by service."""
    ctx = require_tenant_context()
    data = await tracker.get_org_usage_by_service(ctx.organization_id, days)
    return {"data": data}


@router.get(
    "/usage/daily",
    dependencies=[Depends(require_permission("billing.view_billing"))],
)
async def get_daily_usage(
    days: int = Query(30, ge=1, le=365),
    user: dict = Depends(get_current_user),
):
    """Get daily AI token usage for charts."""
    ctx = require_tenant_context()
    data = await tracker.get_org_usage_daily(ctx.organization_id, days)
    return {"data": data}


# ── Platform Admin Endpoints ─────────────────────────────────────────────────

@router.get(
    "/billing/settings",
    dependencies=[Depends(require_platform_admin())],
)
async def get_billing_settings():
    """Get current AI billing configuration."""
    data = await tracker.get_billing_settings()
    return {"data": data}


@router.post(
    "/billing/setup-meter",
    dependencies=[Depends(require_platform_admin())],
)
async def setup_stripe_meter():
    """One-time setup: create Stripe Billing Meter for AI tokens."""
    try:
        result = await stripe_svc.setup_ai_token_meter()
        return {"data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put(
    "/billing/token-rate",
    dependencies=[Depends(require_platform_admin())],
)
async def update_token_rate(body: UpdateTokenRate):
    """Update the AI token billing rate and free tier."""
    try:
        result = await stripe_svc.update_ai_token_rate(
            rate_cents_per_1k=body.rate_cents_per_1k,
            free_tier=body.free_tier,
        )
        return {"data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/billing/add-to-subscription/{org_id}",
    dependencies=[Depends(require_platform_admin())],
)
async def add_to_subscription(org_id: str):
    """Add AI token metered billing to an organization's subscription."""
    try:
        result = await stripe_svc.add_ai_usage_to_subscription(org_id)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/billing/all-orgs-usage",
    dependencies=[Depends(require_platform_admin())],
)
async def get_all_orgs_usage():
    """Get AI token usage summary across all organizations."""
    data = await tracker.get_all_orgs_usage()
    return {"data": data}
