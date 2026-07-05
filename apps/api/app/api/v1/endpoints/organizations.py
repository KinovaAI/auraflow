"""
AuraFlow — Organization Management Endpoints

CRUD for organizations (studios/tenants).
Provisioning, settings, and member management.
"""
from typing import Optional
from pydantic import BaseModel, field_validator

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.dependencies.auth import get_current_user
from app.api.v1.dependencies.rbac import require_permission, require_platform_admin
from app.core.logging import logger
from app.db.session import get_global_db

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────

class CreateOrganizationRequest(BaseModel):
    name: str
    slug: str
    timezone: str = "America/Los_Angeles"
    plan_id: str = "trial"

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v):
        import re
        if not re.match(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$", v) or len(v) < 3:
            raise ValueError("Slug must be lowercase alphanumeric with hyphens, min 3 chars")
        return v


class UpdateOrganizationRequest(BaseModel):
    name: Optional[str] = None
    timezone: Optional[str] = None
    primary_color: Optional[str] = None
    logo_url: Optional[str] = None
    custom_domain: Optional[str] = None
    plan_id: Optional[str] = None


class OrganizationResponse(BaseModel):
    id: str
    slug: str
    name: str
    schema_name: str
    status: str
    plan_id: Optional[str] = None
    timezone: str
    country: str
    currency: str
    primary_color: Optional[str] = None
    logo_url: Optional[str] = None
    custom_domain: Optional[str] = None
    stripe_account_id: Optional[str] = None


class OrganizationMemberResponse(BaseModel):
    user_id: str
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: str
    is_active: bool


class FeatureFlagResponse(BaseModel):
    flag_key: str
    is_enabled: bool
    config: Optional[dict] = None
    is_overridden: bool = False


class ToggleFeatureFlagRequest(BaseModel):
    is_enabled: bool


class ApplyCouponRequest(BaseModel):
    coupon_code: str


class DiscountResponse(BaseModel):
    discount_coupon_code: Optional[str] = None
    discount_percent: Optional[int] = None
    custom_price_cents: Optional[int] = None
    has_discount: bool = False


class CancelAccountRequest(BaseModel):
    reason: Optional[str] = None
    feedback: Optional[str] = None


class CancelAccountResponse(BaseModel):
    status: str
    message: str
    cancellation_effective_at: Optional[str] = None


class ChangePlanRequest(BaseModel):
    plan_id: str

    @field_validator("plan_id")
    @classmethod
    def validate_plan_id(cls, v):
        if v not in ("starter", "growth", "scale", "enterprise"):
            raise ValueError("Invalid plan. Must be one of: starter, growth, scale, enterprise")
        return v


class PlanResponse(BaseModel):
    id: str
    name: str
    price_cents: int
    price_display: str
    interval: str
    tagline: str
    features: list[str]
    limits: dict
    popular: bool = False


class CurrentBillingResponse(BaseModel):
    plan_id: str
    plan_name: str
    plan_price_cents: int
    plan_price_display: str
    status: str
    has_stripe_subscription: bool
    trial_ends_at: Optional[str] = None
    subscription_status: Optional[str] = None
    current_period_end: Optional[str] = None
    cancel_at_period_end: Optional[bool] = None


class PlanChangePreviewResponse(BaseModel):
    current_plan_id: str
    new_plan_id: str
    direction: str
    new_price_cents: int
    new_price_display: str
    proration_amount_cents: Optional[int] = None
    immediate_charge: bool


class PlanChangeResponse(BaseModel):
    previous_plan_id: str
    new_plan_id: str
    direction: str
    new_price_display: str
    subscription_id: Optional[str] = None
    message: str


class CustomDomainRequest(BaseModel):
    domain: str


class CustomDomainResponse(BaseModel):
    id: Optional[str] = None
    custom_domain: Optional[str] = None
    custom_domain_status: Optional[str] = None
    custom_domain_verified_at: Optional[str] = None
    message: Optional[str] = None


def _fmt_dt(dt):
    if dt and hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt) if dt else None


# ── Coupon / Discount Management (must be before /{org_slug} catch-all) ──────

@router.post("/apply-coupon")
async def apply_coupon(
    body: ApplyCouponRequest,
    rbac: dict = Depends(require_permission("billing.apply_coupon")),
):
    """Apply a coupon code to the organization's subscription."""
    from app.core.tenant_context import get_organization_id
    from app.services.billing.discount_service import DiscountService

    org_id = get_organization_id()
    svc = DiscountService()

    try:
        result = await svc.apply_coupon(org_id, body.coupon_code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return result


@router.get("/discount", response_model=DiscountResponse)
async def get_discount(
    rbac: dict = Depends(require_permission("billing.view_discount")),
):
    """View the current discount for the organization."""
    from app.core.tenant_context import get_organization_id
    from app.services.billing.discount_service import DiscountService

    org_id = get_organization_id()
    svc = DiscountService()

    try:
        result = await svc.get_org_discount(org_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return DiscountResponse(**result)


# ── Billing / Plan Management (must be before /{org_slug} catch-all) ─────────

@router.get("/billing/plans", response_model=list[PlanResponse])
async def get_available_plans(
    rbac: dict = Depends(require_permission("billing.view_plans")),
):
    """List all available subscription plans with pricing and features."""
    from app.services.billing.plan_service import PlanService

    svc = PlanService()
    plans = await svc.get_available_plans_async()
    return [PlanResponse(**p) for p in plans]


@router.get("/billing/current", response_model=CurrentBillingResponse)
async def get_current_billing(
    rbac: dict = Depends(require_permission("billing.view_billing")),
):
    """Get the current plan, subscription status, and billing info."""
    from app.core.tenant_context import get_organization_id
    from app.services.billing.plan_service import PlanService

    org_id = get_organization_id()
    svc = PlanService()

    try:
        billing = await svc.get_current_billing(org_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return CurrentBillingResponse(**billing)


@router.get("/billing/preview-change/{plan_id}", response_model=PlanChangePreviewResponse)
async def preview_plan_change(
    plan_id: str,
    rbac: dict = Depends(require_permission("billing.change_plan")),
):
    """Preview what a plan change would cost, including proration details."""
    from app.core.tenant_context import get_organization_id
    from app.services.billing.plan_service import PlanService

    org_id = get_organization_id()
    svc = PlanService()

    try:
        preview = await svc.preview_plan_change(org_id, plan_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return PlanChangePreviewResponse(**preview)


@router.post("/billing/change-plan", response_model=PlanChangeResponse)
async def change_plan(
    body: ChangePlanRequest,
    rbac: dict = Depends(require_permission("billing.change_plan")),
):
    """Change the organization's subscription plan. Prorates via Stripe."""
    from app.core.tenant_context import get_organization_id
    from app.services.billing.plan_service import PlanService

    org_id = get_organization_id()
    svc = PlanService()

    try:
        result = await svc.change_plan(org_id, body.plan_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    logger.info(
        "Plan changed via API",
        org_id=org_id,
        new_plan=body.plan_id,
        direction=result["direction"],
        user_id=rbac["user_id"],
    )

    return PlanChangeResponse(**result)


# ── Feature Flags (must be before /{org_slug} catch-all) ─────────────────────

@router.get("/features", response_model=list[FeatureFlagResponse])
async def get_feature_flags(
    rbac: dict = Depends(require_permission("settings.view_features")),
):
    """List all available feature flags and their current state for the org."""
    from app.core.tenant_context import get_organization_id
    from app.services.feature_flags import FeatureFlagService

    org_id = get_organization_id()

    async with get_global_db() as db:
        rows = await db.fetch("""
            SELECT
                COALESCE(org_flags.flag_key, defaults.flag_key) AS flag_key,
                COALESCE(org_flags.is_enabled, defaults.is_enabled) AS is_enabled,
                COALESCE(org_flags.config, defaults.config) AS config,
                (org_flags.id IS NOT NULL) AS is_overridden
            FROM af_global.feature_flags defaults
            FULL OUTER JOIN (
                SELECT * FROM af_global.feature_flags WHERE organization_id = $1
            ) org_flags ON org_flags.flag_key = defaults.flag_key
            WHERE defaults.organization_id IS NULL
               OR org_flags.organization_id = $1
            ORDER BY flag_key
        """, org_id)

    import json
    return [
        FeatureFlagResponse(
            flag_key=r["flag_key"],
            is_enabled=r["is_enabled"],
            config=json.loads(r["config"]) if r["config"] and isinstance(r["config"], str) else (r["config"] if isinstance(r["config"], dict) else None),
            is_overridden=r["is_overridden"],
        )
        for r in rows
    ]


@router.put("/features/{flag_key}")
async def toggle_feature_flag(
    flag_key: str,
    body: ToggleFeatureFlagRequest,
    rbac: dict = Depends(require_permission("settings.manage_features")),
):
    """Toggle a feature flag for the current organization."""
    from app.core.tenant_context import get_organization_id
    from app.services.feature_flags import FeatureFlagService

    org_id = get_organization_id()
    svc = FeatureFlagService()
    await svc.set_flag(flag_key, body.is_enabled, organization_id=org_id)

    return {
        "flag_key": flag_key,
        "is_enabled": body.is_enabled,
        "message": f"Feature flag '{flag_key}' {'enabled' if body.is_enabled else 'disabled'}",
    }


# ── Custom Domain (must be before /{org_slug} catch-all) ─────────────────────

@router.post("/custom-domain", response_model=CustomDomainResponse)
async def submit_custom_domain(
    body: CustomDomainRequest,
    rbac: dict = Depends(require_permission("settings.add_custom_domain")),
):
    """Submit a custom domain for the organization."""
    from app.core.tenant_context import get_organization_id
    from app.services.platform.custom_domain_service import CustomDomainService

    org_id = get_organization_id()
    domain_svc = CustomDomainService()

    try:
        result = await domain_svc.request_custom_domain(org_id, body.domain)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return CustomDomainResponse(
        id=str(result.get("id", "")),
        custom_domain=result.get("custom_domain"),
        custom_domain_status=result.get("custom_domain_status"),
        custom_domain_verified_at=_fmt_dt(result.get("custom_domain_verified_at")),
    )


@router.get("/custom-domain", response_model=CustomDomainResponse)
async def get_custom_domain_status(
    rbac: dict = Depends(require_permission("settings.view_custom_domain")),
):
    """Check the current custom domain status."""
    from app.core.tenant_context import get_organization_id
    from app.services.platform.custom_domain_service import CustomDomainService

    org_id = get_organization_id()
    domain_svc = CustomDomainService()
    result = await domain_svc.get_domain_status(org_id)

    if not result:
        raise HTTPException(status_code=404, detail="Organization not found")

    return CustomDomainResponse(
        id=str(result.get("id", "")),
        custom_domain=result.get("custom_domain"),
        custom_domain_status=result.get("custom_domain_status"),
        custom_domain_verified_at=_fmt_dt(result.get("custom_domain_verified_at")),
    )


@router.post("/custom-domain/verify", response_model=CustomDomainResponse)
async def verify_custom_domain(
    rbac: dict = Depends(require_permission("settings.manage_custom_domain")),
):
    """Trigger DNS verification for the custom domain."""
    from app.core.tenant_context import get_organization_id
    from app.services.platform.custom_domain_service import CustomDomainService

    org_id = get_organization_id()
    domain_svc = CustomDomainService()

    try:
        result = await domain_svc.verify_domain(org_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return CustomDomainResponse(
        id=str(result.get("id", "")),
        custom_domain=result.get("custom_domain"),
        custom_domain_status=result.get("custom_domain_status"),
        custom_domain_verified_at=_fmt_dt(result.get("custom_domain_verified_at")),
        message=result.get("message"),
    )


@router.delete("/custom-domain", status_code=204)
async def remove_custom_domain(
    rbac: dict = Depends(require_permission("settings.delete_custom_domain")),
):
    """Remove the custom domain configuration."""
    from app.core.tenant_context import get_organization_id
    from app.services.platform.custom_domain_service import CustomDomainService

    org_id = get_organization_id()
    domain_svc = CustomDomainService()
    removed = await domain_svc.remove_custom_domain(org_id)

    if not removed:
        raise HTTPException(status_code=404, detail="Organization not found")


# ── Billing Invoices (platform invoices for the org) ─────────────────────────

@router.get("/billing/invoices")
async def list_billing_invoices(
    limit: int = 24,
    rbac: dict = Depends(require_permission("billing.view_invoices")),
):
    """List Stripe invoices for the organization's platform subscription.

    These are the invoices for what the studio pays AuraFlow, not member
    payment transactions.
    """
    from app.core.tenant_context import get_organization_id
    from app.services.payments.stripe_service import StripeService

    org_id = get_organization_id()
    stripe_svc = StripeService()

    try:
        invoices = await stripe_svc.list_org_invoices(org_id, limit=limit)
    except Exception as e:
        logger.error("Failed to fetch billing invoices", org_id=org_id, error=str(e))
        raise HTTPException(status_code=502, detail="Could not retrieve invoices from Stripe")

    return {"data": invoices}


# ── Account Cancellation (must be before /{org_slug} catch-all) ──────────────

@router.post("/cancel", response_model=CancelAccountResponse)
async def cancel_account(
    body: CancelAccountRequest,
    rbac: dict = Depends(require_permission("billing.cancel")),
):
    """Cancel the organization's subscription at end of billing period.

    Only the owner can cancel. This does NOT delete data — it cancels
    billing and marks the org as 'cancelling'. Data is retained for 30 days.
    """
    from datetime import datetime, timezone, timedelta
    import asyncio
    from app.core.tenant_context import get_organization_id
    from app.services.payments.stripe_service import StripeService, _configure_stripe
    from app.services.platform.audit_service import audit_service

    org_id = get_organization_id()
    user_id = rbac["user_id"]

    # Fetch org details
    async with get_global_db() as db:
        org = await db.fetchrow(
            """
            SELECT id, name, slug, status, stripe_subscription_id, stripe_customer_id
            FROM af_global.organizations WHERE id = $1
            """,
            org_id,
        )

    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    if org["status"] == "cancelling":
        raise HTTPException(status_code=409, detail="Cancellation already in progress")
    if org["status"] == "cancelled":
        raise HTTPException(status_code=409, detail="Account is already cancelled")

    # Cancel Stripe subscription at period end (if one exists)
    cancellation_effective_at = None
    if org["stripe_subscription_id"]:
        try:
            import stripe as stripe_lib
            stripe_svc = StripeService()
            await stripe_svc.cancel_subscription(
                org["stripe_subscription_id"],
                at_period_end=True,
            )
            # Get the period end from Stripe
            _configure_stripe()
            sub = await asyncio.to_thread(
                lambda: stripe_lib.Subscription.retrieve(org["stripe_subscription_id"])
            )
            if sub.current_period_end:
                cancellation_effective_at = datetime.fromtimestamp(
                    sub.current_period_end, tz=timezone.utc
                )
        except Exception as e:
            logger.error("Failed to cancel Stripe subscription", org_id=org_id, error=str(e))
            raise HTTPException(
                status_code=502,
                detail="Failed to cancel subscription with payment provider",
            )
    else:
        # No Stripe subscription — set effective date to 30 days from now
        cancellation_effective_at = datetime.now(timezone.utc) + timedelta(days=30)

    # Update org status and record cancellation details
    async with get_global_db() as db:
        await db.execute(
            """
            UPDATE af_global.organizations
            SET status = 'cancelling',
                cancellation_reason = $2,
                cancellation_feedback = $3,
                cancellation_requested_at = NOW(),
                cancellation_effective_at = $4,
                updated_at = NOW()
            WHERE id = $1
            """,
            org_id,
            body.reason,
            body.feedback,
            cancellation_effective_at,
        )

    # Invalidate tenant cache
    from app.core.redis import get_redis
    redis = await get_redis()
    if redis:
        await redis.delete(f"tenant:{org['slug']}")

    # Audit log
    await audit_service.log(
        user_id=user_id,
        action="org.cancellation_requested",
        resource_type="organization",
        resource_id=org_id,
        organization_id=org_id,
        metadata={
            "reason": body.reason,
            "feedback": body.feedback,
            "effective_at": cancellation_effective_at.isoformat() if cancellation_effective_at else None,
        },
    )

    # Send confirmation email to owner
    await _send_cancellation_email(
        org_id=org_id,
        user_id=user_id,
        org_name=org["name"],
        effective_date=cancellation_effective_at,
    )

    logger.info(
        "Account cancellation requested",
        org_id=org_id,
        org_slug=org["slug"],
        user_id=user_id,
        reason=body.reason,
    )

    return CancelAccountResponse(
        status="cancelling",
        message="Your subscription has been cancelled. Your account will remain active until the end of your billing period.",
        cancellation_effective_at=cancellation_effective_at.isoformat() if cancellation_effective_at else None,
    )


@router.post("/reactivate", response_model=CancelAccountResponse)
async def reactivate_account(
    rbac: dict = Depends(require_permission("billing.reactivate")),
):
    """Reactivate a cancelling account before the cancellation takes effect."""
    import asyncio
    from app.core.tenant_context import get_organization_id
    from app.services.payments.stripe_service import _configure_stripe
    from app.services.platform.audit_service import audit_service

    org_id = get_organization_id()
    user_id = rbac["user_id"]

    async with get_global_db() as db:
        org = await db.fetchrow(
            """
            SELECT id, name, slug, status, stripe_subscription_id
            FROM af_global.organizations WHERE id = $1
            """,
            org_id,
        )

    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    if org["status"] != "cancelling":
        raise HTTPException(
            status_code=409,
            detail="Account is not in cancelling state",
        )

    # Reactivate Stripe subscription if exists
    if org["stripe_subscription_id"]:
        try:
            import stripe as stripe_lib
            _configure_stripe()
            await asyncio.to_thread(
                lambda: stripe_lib.Subscription.modify(
                    org["stripe_subscription_id"],
                    cancel_at_period_end=False,
                )
            )
        except Exception as e:
            logger.error("Failed to reactivate Stripe subscription", org_id=org_id, error=str(e))
            raise HTTPException(
                status_code=502,
                detail="Failed to reactivate subscription with payment provider",
            )

    # Restore org status
    async with get_global_db() as db:
        await db.execute(
            """
            UPDATE af_global.organizations
            SET status = 'active',
                cancellation_reason = NULL,
                cancellation_feedback = NULL,
                cancellation_requested_at = NULL,
                cancellation_effective_at = NULL,
                updated_at = NOW()
            WHERE id = $1
            """,
            org_id,
        )

    # Invalidate tenant cache
    from app.core.redis import get_redis
    redis = await get_redis()
    if redis:
        await redis.delete(f"tenant:{org['slug']}")

    # Audit log
    await audit_service.log(
        user_id=user_id,
        action="org.cancellation_reverted",
        resource_type="organization",
        resource_id=org_id,
        organization_id=org_id,
    )

    logger.info("Account reactivated", org_id=org_id, org_slug=org["slug"], user_id=user_id)

    return CancelAccountResponse(
        status="active",
        message="Your account has been reactivated. Your subscription will continue as normal.",
    )


@router.get("/cancellation-status")
async def get_cancellation_status(
    rbac: dict = Depends(require_permission("settings.view_cancellation_status")),
):
    """Get the current cancellation status of the organization."""
    from app.core.tenant_context import get_organization_id

    org_id = get_organization_id()

    async with get_global_db() as db:
        row = await db.fetchrow(
            """
            SELECT status, cancellation_reason, cancellation_feedback,
                   cancellation_requested_at, cancellation_effective_at
            FROM af_global.organizations WHERE id = $1
            """,
            org_id,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Organization not found")

    return {
        "status": row["status"],
        "cancellation_reason": row["cancellation_reason"],
        "cancellation_feedback": row["cancellation_feedback"],
        "cancellation_requested_at": _fmt_dt(row["cancellation_requested_at"]),
        "cancellation_effective_at": _fmt_dt(row["cancellation_effective_at"]),
    }


async def _send_cancellation_email(
    org_id: str,
    user_id: str,
    org_name: str,
    effective_date,
) -> None:
    """Send account cancellation confirmation email to the owner."""
    from app.core.config import settings

    if not settings.SENDGRID_API_KEY:
        logger.warning("SendGrid not configured — cancellation email not sent")
        return

    # Get owner email
    async with get_global_db() as db:
        user = await db.fetchrow(
            "SELECT email, first_name FROM af_global.users WHERE id = $1",
            user_id,
        )

    if not user:
        return

    first_name = user["first_name"] or "there"
    effective_str = effective_date.strftime("%B %d, %Y") if effective_date else "the end of your billing period"

    subject = f"Your {org_name} account cancellation confirmation"
    html = f"""
    <p>Hey {first_name},</p>
    <p>We've received your request to cancel your <strong>{org_name}</strong> account on AuraFlow.</p>
    <p>Here's what you need to know:</p>
    <ul>
        <li>Your account will remain fully functional until <strong>{effective_str}</strong></li>
        <li>Your data will be retained for 30 days after cancellation</li>
        <li>You can reactivate anytime before the cancellation date from your settings</li>
    </ul>
    <p>If you change your mind, just visit your account settings and click "Reactivate Account".</p>
    <p>We'd love to have you back anytime.</p>
    <p>-- The AuraFlow Team</p>
    """

    from app.services.email.smtp_sender import is_smtp_configured, send_smtp_email
    if is_smtp_configured():
        ok = await send_smtp_email(
            to_email=user["email"], subject=subject, html_content=html,
        )
        if ok:
            logger.info("Cancellation email sent (SMTP)", email=user["email"], org_name=org_name)
        else:
            logger.error("Failed to send cancellation email via SMTP", email=user["email"])
    else:
        logger.error("SMTP not configured — cancellation email NOT sent", email=user["email"])


# ── List User's Organizations ────────────────────────────────────────────────

@router.get("", response_model=list[OrganizationResponse])
async def list_organizations(current_user: dict = Depends(get_current_user)):
    """List all organizations the current user belongs to."""
    user_id = current_user.get("sub")

    async with get_global_db() as db:
        rows = await db.fetch(
            """
            SELECT o.id, o.slug, o.name, o.schema_name, o.status, o.plan_id,
                   o.timezone, o.country, o.currency, o.primary_color,
                   o.logo_url, o.custom_domain, o.stripe_account_id
            FROM af_global.organizations o
            JOIN af_global.organization_users ou ON o.id = ou.organization_id
            WHERE ou.user_id = $1 AND ou.is_active = TRUE
            ORDER BY ou.joined_at ASC NULLS LAST
            """,
            user_id
        )

    return [
        OrganizationResponse(
            id=str(r["id"]),
            slug=r["slug"],
            name=r["name"],
            schema_name=r["schema_name"],
            status=r["status"],
            plan_id=r["plan_id"],
            timezone=r["timezone"],
            country=r["country"],
            currency=r["currency"],
            primary_color=r["primary_color"],
            logo_url=r["logo_url"],
            custom_domain=r["custom_domain"],
            stripe_account_id=r["stripe_account_id"],
        )
        for r in rows
    ]


# ── Get Organization Details ─────────────────────────────────────────────────

@router.get("/{org_slug}", response_model=OrganizationResponse)
async def get_organization(
    org_slug: str,
    current_user: dict = Depends(get_current_user),
):
    """Get details of an organization the user belongs to."""
    user_id = current_user.get("sub")

    async with get_global_db() as db:
        row = await db.fetchrow(
            """
            SELECT o.id, o.slug, o.name, o.schema_name, o.status, o.plan_id,
                   o.timezone, o.country, o.currency, o.primary_color,
                   o.logo_url, o.custom_domain, o.stripe_account_id
            FROM af_global.organizations o
            JOIN af_global.organization_users ou ON o.id = ou.organization_id
            WHERE o.slug = $1 AND ou.user_id = $2 AND ou.is_active = TRUE
            """,
            org_slug, user_id
        )

    if not row:
        raise HTTPException(status_code=404, detail="Organization not found")

    return OrganizationResponse(
        id=str(row["id"]),
        slug=row["slug"],
        name=row["name"],
        schema_name=row["schema_name"],
        status=row["status"],
        plan_id=row["plan_id"],
        timezone=row["timezone"],
        country=row["country"],
        currency=row["currency"],
        primary_color=row["primary_color"],
        logo_url=row["logo_url"],
        custom_domain=row["custom_domain"],
        stripe_account_id=row["stripe_account_id"],
    )


# ── Create Organization (provision new tenant) ──────────────────────────────

@router.post("", response_model=OrganizationResponse, status_code=201)
async def create_organization(
    request: CreateOrganizationRequest,
    current_user: dict = Depends(get_current_user),
):
    """Create a new organization and provision its tenant schema."""
    user_id = current_user.get("sub")

    # Check slug availability
    async with get_global_db() as db:
        existing = await db.fetchval(
            "SELECT 1 FROM af_global.organizations WHERE slug = $1",
            request.slug
        )
    if existing:
        raise HTTPException(status_code=409, detail="Organization slug already taken")

    # Fetch user info for provisioning
    async with get_global_db() as db:
        user = await db.fetchrow(
            "SELECT email, first_name, last_name FROM af_global.users WHERE id = $1",
            user_id
        )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    from app.services.tenant_provisioning import TenantProvisioningService
    provisioner = TenantProvisioningService()
    result = await provisioner.provision(
        organization_name=request.name,
        slug=request.slug,
        owner_email=user["email"],
        owner_first_name=user["first_name"] or "",
        owner_last_name=user["last_name"] or "",
        plan_id=request.plan_id,
        timezone=request.timezone,
    )

    logger.info(
        "Organization created",
        org_id=result["organization_id"],
        slug=request.slug,
        user_id=user_id,
    )

    # Fetch and return the full org record
    async with get_global_db() as db:
        row = await db.fetchrow(
            """
            SELECT id, slug, name, schema_name, status, plan_id,
                   timezone, country, currency, primary_color,
                   logo_url, custom_domain, stripe_account_id
            FROM af_global.organizations WHERE slug = $1
            """,
            request.slug
        )

    return OrganizationResponse(
        id=str(row["id"]),
        slug=row["slug"],
        name=row["name"],
        schema_name=row["schema_name"],
        status=row["status"],
        plan_id=row["plan_id"],
        timezone=row["timezone"],
        country=row["country"],
        currency=row["currency"],
        primary_color=row["primary_color"],
        logo_url=row["logo_url"],
        custom_domain=row["custom_domain"],
        stripe_account_id=row["stripe_account_id"],
    )


# ── Update Organization ─────────────────────────────────────────────────────

@router.put("/{org_slug}", response_model=OrganizationResponse)
async def update_organization(
    org_slug: str,
    request: UpdateOrganizationRequest,
    rbac: dict = Depends(require_permission("settings.edit_organization")),
):
    """Update organization settings. Requires owner or admin role."""
    _ORG_UPDATE_COLS = {"name", "timezone", "primary_color", "logo_url", "custom_domain", "plan_id"}
    updates = {k: v for k, v in request.model_dump().items() if v is not None and k in _ORG_UPDATE_COLS}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clauses = []
    params = []
    for i, (col, val) in enumerate(updates.items(), start=1):
        set_clauses.append(f"{col} = ${i}")
        params.append(val)

    params.append(org_slug)
    query = f"""
        UPDATE af_global.organizations
        SET {', '.join(set_clauses)}, updated_at = NOW()
        WHERE slug = ${len(params)}
    """

    async with get_global_db() as db:
        result = await db.execute(query, *params)

    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Organization not found")

    # Invalidate tenant cache
    from app.core.redis import get_redis
    redis = await get_redis()
    if redis:
        await redis.delete(f"tenant:{org_slug}")

    logger.info("Organization updated", slug=org_slug, fields=list(updates.keys()))
    return await get_organization(org_slug, {"sub": rbac["user_id"]})


# ── Deactivate Organization ─────────────────────────────────────────────────

@router.delete("/{org_slug}", status_code=204)
async def deactivate_organization(
    org_slug: str,
    rbac: dict = Depends(require_permission("settings.delete_organization")),
):
    """Soft-delete (cancel) an organization. Owner only."""
    from app.services.tenant_provisioning import TenantProvisioningService
    provisioner = TenantProvisioningService()
    await provisioner.deprovision(org_slug, hard_delete=False)
    logger.info("Organization deactivated", slug=org_slug, user_id=rbac["user_id"])


# ── List Organization Members ────────────────────────────────────────────────

@router.get("/{org_slug}/members", response_model=list[OrganizationMemberResponse])
async def list_organization_members(
    org_slug: str,
    rbac: dict = Depends(require_permission("staff.view")),
):
    """List all members of an organization."""
    async with get_global_db() as db:
        rows = await db.fetch(
            """
            SELECT u.id as user_id, u.email, u.first_name, u.last_name,
                   ou.role, ou.is_active
            FROM af_global.organization_users ou
            JOIN af_global.users u ON u.id = ou.user_id
            JOIN af_global.organizations o ON o.id = ou.organization_id
            WHERE o.slug = $1
            ORDER BY ou.role, u.last_name, u.first_name
            """,
            org_slug
        )

    return [
        OrganizationMemberResponse(
            user_id=str(r["user_id"]),
            email=r["email"],
            first_name=r["first_name"],
            last_name=r["last_name"],
            role=r["role"],
            is_active=r["is_active"],
        )
        for r in rows
    ]


# ── Invite Helpers ──────────────────────────────────────────────────────────

async def _send_staff_invite_email(
    to_email: str,
    first_name: str,
    org_name: str,
    org_slug: str,
    role: str,
    existing_user: bool,
) -> None:
    """Send staff invite email. Existing users get a 'you've been added' email,
    new users get an invite link with a registration token."""
    from app.core.config import settings

    if not settings.SENDGRID_API_KEY:
        logger.warning("SendGrid not configured — invite email not sent", email=to_email)
        return

    role_label = role.replace("_", " ").title()

    if existing_user:
        # User already has an account — just notify them
        login_url = f"{settings.APP_URL}/login"
        subject = f"You've been added to {org_name}"
        html = f"""
        <p>Hey {first_name},</p>
        <p>You've been added to <strong>{org_name}</strong> as a <strong>{role_label}</strong> on AuraFlow.</p>
        <p><a href="{login_url}" style="
            display: inline-block; padding: 12px 24px;
            background-color: #4F46E5; color: #ffffff;
            text-decoration: none; border-radius: 6px;
            font-weight: 600;">Log In</a></p>
        <p>— The AuraFlow Team</p>
        """
    else:
        # New user — generate invite token and send signup link
        import hashlib, secrets, json
        from app.core.redis import get_redis

        raw_token = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        invite_data = json.dumps({
            "org_slug": org_slug,
            "org_name": org_name,
            "role": role,
            "email": to_email,
        })

        redis = await get_redis()
        if redis:
            await redis.setex(f"invite:{token_hash}", 604800, invite_data)  # 7 days

        invite_url = f"{settings.APP_URL}/signup?invite={raw_token}"
        subject = f"You're invited to join {org_name}"
        html = f"""
        <p>Hey there,</p>
        <p>You've been invited to join <strong>{org_name}</strong> as a <strong>{role_label}</strong> on AuraFlow.</p>
        <p><a href="{invite_url}" style="
            display: inline-block; padding: 12px 24px;
            background-color: #4F46E5; color: #ffffff;
            text-decoration: none; border-radius: 6px;
            font-weight: 600;">Accept Invite</a></p>
        <p>This invitation expires in 7 days.</p>
        <p>— The AuraFlow Team</p>
        """

    from app.services.email.smtp_sender import is_smtp_configured, send_smtp_email
    if is_smtp_configured():
        ok = await send_smtp_email(
            to_email=to_email, subject=subject, html_content=html,
        )
        if ok:
            logger.info("Invite email sent (SMTP)", email=to_email, org=org_slug, existing=existing_user)
        else:
            logger.error("Failed to send invite email via SMTP", email=to_email)
    else:
        logger.error("SMTP not configured — invite email NOT sent", email=to_email)


# ── Invite Member ───────────────────────────────────────────────────────────

class InviteMemberRequest(BaseModel):
    email: str
    role: str = "member"

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        if v not in ("admin", "instructor", "front_desk", "member"):
            raise ValueError("Invalid role. Cannot invite as owner.")
        return v


@router.post("/{org_slug}/members", status_code=201)
async def invite_member(
    org_slug: str,
    request: InviteMemberRequest,
    rbac: dict = Depends(require_permission("staff.invite")),
):
    """Invite a user to the organization. Creates user if they don't exist."""
    import uuid

    async with get_global_db() as db:
        org = await db.fetchrow(
            "SELECT id, name FROM af_global.organizations WHERE slug = $1",
            org_slug
        )
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    org_id = str(org["id"])
    org_name = org["name"]
    existing_user = False

    async with get_global_db() as db:
        user = await db.fetchrow(
            "SELECT id, first_name, password_hash FROM af_global.users WHERE email = $1",
            request.email.lower()
        )

        if user:
            user_id = str(user["id"])
            existing_user = bool(user["password_hash"])
            user_first_name = user["first_name"] or "there"
        else:
            user_id = str(uuid.uuid4())
            user_first_name = "there"
            await db.execute(
                """
                INSERT INTO af_global.users (id, email)
                VALUES ($1, $2)
                """,
                user_id, request.email.lower()
            )

        # Add to org (or update if already exists)
        await db.execute(
            """
            INSERT INTO af_global.organization_users
                (organization_id, user_id, role, invited_by, invited_at, is_active)
            VALUES ($1, $2, $3, $4, NOW(), TRUE)
            ON CONFLICT (organization_id, user_id)
            DO UPDATE SET role = EXCLUDED.role, is_active = TRUE, invited_at = NOW()
            """,
            org_id, user_id, request.role, rbac["user_id"]
        )

    # Seed default permissions for the new staff member
    from app.services.permissions import permission_service
    await permission_service.initialize_default_permissions(
        org_id, user_id, request.role,
    )

    # Send invite email
    try:
        await _send_staff_invite_email(
            to_email=request.email.lower(),
            first_name=user_first_name,
            org_name=org_name,
            org_slug=org_slug,
            role=request.role,
            existing_user=existing_user,
        )
    except Exception as e:
        logger.error("Failed to send invite email", email=request.email, error=str(e))

    logger.info(
        "Member invited",
        org=org_slug,
        email=request.email,
        role=request.role,
        invited_by=rbac["user_id"],
    )

    return {"message": f"Invited {request.email} as {request.role}"}


# ── Remove Member ───────────────────────────────────────────────────────────

@router.delete("/{org_slug}/members/{user_id}", status_code=204)
async def remove_member(
    org_slug: str,
    user_id: str,
    rbac: dict = Depends(require_permission("members.remove")),
):
    """Remove a member from the organization (soft-deactivate)."""
    # Prevent removing yourself as owner
    if user_id == rbac["user_id"]:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")

    async with get_global_db() as db:
        result = await db.execute(
            """
            UPDATE af_global.organization_users ou
            SET is_active = FALSE
            FROM af_global.organizations o
            WHERE o.id = ou.organization_id
              AND o.slug = $1
              AND ou.user_id = $2
            """,
            org_slug, user_id
        )

    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Member not found in organization")

    logger.info("Member removed", org=org_slug, user_id=user_id, removed_by=rbac["user_id"])
