"""AuraFlow — Marketing Endpoints

Email campaign management, audience preview, campaign sending/stats,
SMS ad-hoc sending, SMS campaigns, and SMS templates.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.v1.dependencies.auth import get_current_user
from app.api.v1.dependencies.rbac import require_permission
from app.services.marketing.campaign_service import CampaignService, SmsService
from app.services.marketing.sms_campaign_service import SmsCampaignService, SmsTemplateService

router = APIRouter()

# Keep stub routers for webhook module compatibility
stripe_router = APIRouter()
mux_router = APIRouter()

campaign_svc = CampaignService()
sms_svc = SmsService()
sms_campaign_svc = SmsCampaignService()
sms_template_svc = SmsTemplateService()


# ── Schemas ──────────────────────────────────────────────────────────────────

class CampaignCreate(BaseModel):
    name: str
    subject: str
    html_content: Optional[str] = None
    audience_filter: Optional[dict] = None


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    subject: Optional[str] = None
    html_content: Optional[str] = None
    audience_filter: Optional[str] = None


class AudiencePreview(BaseModel):
    tags: Optional[list[str]] = None
    membership_type_ids: Optional[list[str]] = None


class SmsSend(BaseModel):
    to_phone: str
    body: str
    member_id: Optional[str] = None
    sms_type: str = "transactional"


class SmsCampaignCreate(BaseModel):
    name: str
    body: str
    template_id: Optional[str] = None
    audience_filter: Optional[dict] = None
    scheduled_at: Optional[str] = None


class SmsCampaignUpdate(BaseModel):
    name: Optional[str] = None
    body: Optional[str] = None
    audience_filter: Optional[dict] = None


class SmsTemplateCreate(BaseModel):
    name: str
    slug: str
    body: str
    description: Optional[str] = None
    category: str = "general"


class SmsTemplateUpdate(BaseModel):
    name: Optional[str] = None
    body: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None


# ── Campaign CRUD ────────────────────────────────────────────────────────────

@router.post("/campaigns", status_code=201)
async def create_campaign(
    body: CampaignCreate,
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.create_campaign")),
):
    import json
    data = body.model_dump()
    if data.get("audience_filter"):
        data["audience_filter"] = json.dumps(data["audience_filter"])
    data["created_by"] = user.get("user_id")
    campaign = await campaign_svc.create_campaign(data)
    return {"data": campaign}


@router.get("/campaigns")
async def list_campaigns(
    status: Optional[str] = Query(None),
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.view_campaigns")),
):
    campaigns = await campaign_svc.list_campaigns(status=status)
    return {"data": campaigns}


@router.post("/campaigns/preview-audience")
async def preview_audience(
    body: AudiencePreview,
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.view_campaigns")),
):
    result = await campaign_svc.preview_audience(body.model_dump(exclude_none=True))
    return {"data": result}


# ── Single Campaign (must come AFTER fixed paths) ────────────────────────────

@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.view_campaigns")),
):
    campaign = await campaign_svc.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {"data": campaign}


@router.put("/campaigns/{campaign_id}")
async def update_campaign(
    campaign_id: str,
    body: CampaignUpdate,
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.edit_campaign")),
):
    data = body.model_dump(exclude_none=True)
    campaign = await campaign_svc.update_campaign(campaign_id, data)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found or not in draft status")
    return {"data": campaign}


@router.delete("/campaigns/{campaign_id}")
async def delete_campaign(
    campaign_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.delete_campaign")),
):
    deleted = await campaign_svc.delete_campaign(campaign_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Campaign not found or not in draft status")
    return {"data": {"deleted": True}}


@router.post("/campaigns/{campaign_id}/send")
async def send_campaign(
    campaign_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.send_campaign")),
):
    try:
        result = await campaign_svc.send_campaign(campaign_id)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/campaigns/{campaign_id}/stats")
async def get_campaign_stats(
    campaign_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.view_campaigns")),
):
    stats = await campaign_svc.get_campaign_stats(campaign_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {"data": stats}


# ── SMS ──────────────────────────────────────────────────────────────────────

@router.post("/sms/send", status_code=201)
async def send_sms(
    body: SmsSend,
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.send_sms")),
):
    result = await sms_svc.send_sms(
        to_phone=body.to_phone,
        body=body.body,
        member_id=body.member_id,
        sms_type=body.sms_type,
    )
    return {"data": result}


@router.get("/sms")
async def list_sms(
    member_id: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.view_sms")),
):
    messages = await sms_svc.list_sms(member_id=member_id, limit=limit)
    return {"data": messages}


@router.get("/sms/stats")
async def sms_stats(
    days: int = Query(30, ge=1, le=365),
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.view_sms")),
):
    """Aggregate SMS stats (all types + campaign-level)."""
    return {"data": await sms_campaign_svc.get_sms_stats(days)}


# ── SMS Templates ────────────────────────────────────────────────────────────

@router.get("/sms/templates")
async def list_sms_templates(
    category: Optional[str] = Query(None),
    active_only: bool = Query(True),
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.view_sms_templates")),
):
    return {"data": await sms_template_svc.list_templates(category=category, active_only=active_only)}


@router.post("/sms/templates", status_code=201)
async def create_sms_template(
    body: SmsTemplateCreate,
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.create_sms_template")),
):
    data = body.model_dump()
    data["created_by"] = user.get("user_id")
    template = await sms_template_svc.create_template(data)
    return {"data": template}


@router.get("/sms/templates/{template_id}")
async def get_sms_template(
    template_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.view_sms_templates")),
):
    template = await sms_template_svc.get_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"data": template}


@router.put("/sms/templates/{template_id}")
async def update_sms_template(
    template_id: str,
    body: SmsTemplateUpdate,
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.edit_sms_template")),
):
    template = await sms_template_svc.update_template(template_id, body.model_dump(exclude_none=True))
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"data": template}


@router.delete("/sms/templates/{template_id}")
async def delete_sms_template(
    template_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.delete_sms_template")),
):
    deleted = await sms_template_svc.delete_template(template_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"data": {"deleted": True}}


# ── SMS Campaigns ────────────────────────────────────────────────────────────

@router.get("/sms/campaigns")
async def list_sms_campaigns(
    status: Optional[str] = Query(None),
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.view_sms_campaigns")),
):
    campaigns = await sms_campaign_svc.list_campaigns(status=status)
    return {"data": campaigns}


@router.post("/sms/campaigns", status_code=201)
async def create_sms_campaign(
    body: SmsCampaignCreate,
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.create_sms_campaign")),
):
    data = body.model_dump()
    data["created_by"] = user.get("user_id")
    campaign = await sms_campaign_svc.create_campaign(data)
    return {"data": campaign}


@router.post("/sms/campaigns/preview-audience")
async def preview_sms_audience(
    body: AudiencePreview,
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.view_sms_campaigns")),
):
    """Preview audience count for SMS (phone + sms_opt_in required)."""
    result = await sms_campaign_svc.preview_audience(body.model_dump(exclude_none=True))
    return {"data": result}


@router.get("/sms/campaigns/{campaign_id}")
async def get_sms_campaign(
    campaign_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.view_sms_campaigns")),
):
    campaign = await sms_campaign_svc.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="SMS campaign not found")
    return {"data": campaign}


@router.put("/sms/campaigns/{campaign_id}")
async def update_sms_campaign(
    campaign_id: str,
    body: SmsCampaignUpdate,
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.edit_sms_campaign")),
):
    import json
    data = body.model_dump(exclude_none=True)
    if "audience_filter" in data and isinstance(data["audience_filter"], dict):
        data["audience_filter"] = json.dumps(data["audience_filter"])
    campaign = await sms_campaign_svc.update_campaign(campaign_id, data)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found or not in draft status")
    return {"data": campaign}


@router.delete("/sms/campaigns/{campaign_id}")
async def delete_sms_campaign(
    campaign_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.delete_sms_campaign")),
):
    deleted = await sms_campaign_svc.delete_campaign(campaign_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Campaign not found or not in draft status")
    return {"data": {"deleted": True}}


@router.post("/sms/campaigns/{campaign_id}/schedule")
async def schedule_sms_campaign(
    campaign_id: str,
    scheduled_at: str = Query(..., description="ISO 8601 datetime for scheduled send"),
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.schedule_sms_campaign")),
):
    campaign = await sms_campaign_svc.schedule_campaign(campaign_id, scheduled_at)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found or not in draft status")
    return {"data": campaign}


@router.post("/sms/campaigns/{campaign_id}/send")
async def send_sms_campaign(
    campaign_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.send_sms_campaign")),
):
    try:
        result = await sms_campaign_svc.send_campaign(campaign_id)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sms/campaigns/{campaign_id}/cancel")
async def cancel_sms_campaign(
    campaign_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.cancel_sms_campaign")),
):
    campaign = await sms_campaign_svc.cancel_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found or cannot be cancelled")
    return {"data": campaign}


@router.get("/sms/campaigns/{campaign_id}/stats")
async def get_sms_campaign_stats(
    campaign_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.view_sms_campaigns")),
):
    stats = await sms_campaign_svc.get_campaign_stats(campaign_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {"data": stats}


@router.post("/sms/campaigns/{campaign_id}/retry")
async def retry_sms_campaign(
    campaign_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("marketing.send_sms_campaign")),
):
    """Retry all failed sends for an SMS campaign."""
    try:
        result = await sms_campaign_svc.retry_failed_sends(campaign_id)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
