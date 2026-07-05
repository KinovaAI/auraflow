"""AuraFlow — Per-Tenant Studio Social Media Endpoints

Connect Facebook/Instagram, manage posts with AI generation,
message inbox with AI responses, engagement stats.
All endpoints require owner or admin role.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.v1.dependencies.rbac import require_permission
from app.services.social.studio_social_service import StudioSocialService

router = APIRouter()
svc = StudioSocialService()


# ── Request Models ───────────────────────────────────────────────────────

class ConnectFacebook(BaseModel):
    access_token: str
    page_id: str


class ConnectInstagram(BaseModel):
    instagram_business_id: str


class DisconnectAccount(BaseModel):
    account_id: str


class CreatePost(BaseModel):
    content: str
    platform: str = "facebook"
    media_urls: Optional[list[str]] = None
    scheduled_at: Optional[str] = None


class RespondToMessage(BaseModel):
    response: str


# ── Account Management ──────────────────────────────────────────────────

@router.post("/connect/facebook")
async def connect_facebook(
    body: ConnectFacebook,
    rbac=Depends(require_permission("communications.connect_facebook")),
):
    """Connect a Facebook Page via OAuth access token."""
    schema = f"af_tenant_{rbac["org_slug"]}"
    try:
        result = await svc.connect_facebook(schema, body.access_token, body.page_id)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(status_code=409, detail="Account already connected")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/connect/instagram")
async def connect_instagram(
    body: ConnectInstagram,
    rbac=Depends(require_permission("communications.connect_instagram")),
):
    """Connect Instagram Business account (requires Facebook Page)."""
    schema = f"af_tenant_{rbac["org_slug"]}"
    try:
        result = await svc.connect_instagram(schema, body.instagram_business_id)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/status")
async def get_status(rbac=Depends(require_permission("communications.view_status"))):
    """Get connection status for Facebook and Instagram."""
    schema = f"af_tenant_{rbac["org_slug"]}"
    result = await svc.get_status(schema)
    return {"data": result}


@router.post("/disconnect")
async def disconnect(
    body: DisconnectAccount,
    rbac=Depends(require_permission("communications.disconnect_social")),
):
    """Disconnect a social media account."""
    schema = f"af_tenant_{rbac["org_slug"]}"
    success = await svc.disconnect(schema, body.account_id)
    if not success:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"data": {"disconnected": True}}


# ── Posts ────────────────────────────────────────────────────────────────

@router.get("/posts")
async def list_posts(
    status: Optional[str] = Query(None),
    limit: int = Query(20, le=100),
    rbac=Depends(require_permission("communications.view_social_posts")),
):
    """List social media posts."""
    return {"data": await svc.list_posts(f"af_tenant_{rbac["org_slug"]}", status, limit)}


@router.post("/posts")
async def create_post(
    body: CreatePost,
    rbac=Depends(require_permission("communications.create_social_post")),
):
    """Create a draft or scheduled post."""
    schema = f"af_tenant_{rbac["org_slug"]}"
    try:
        result = await svc.create_post(
            schema, body.content, body.platform,
            body.media_urls, body.scheduled_at,
        )
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/posts/generate")
async def generate_ai_post(rbac=Depends(require_permission("communications.create_social_post"))):
    """Generate AI post content based on today's schedule and studio context."""
    schema = f"af_tenant_{rbac["org_slug"]}"
    result = await svc.generate_ai_post(schema)
    return {"data": result}


@router.post("/posts/{post_id}/publish")
async def publish_post(
    post_id: str,
    rbac=Depends(require_permission("communications.publish_social_post")),
):
    """Publish a draft post to Facebook or Instagram."""
    schema = f"af_tenant_{rbac["org_slug"]}"
    try:
        result = await svc.publish_post(schema, post_id)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/posts/{post_id}", status_code=204)
async def delete_post(
    post_id: str,
    rbac=Depends(require_permission("communications.delete_social_post")),
):
    """Delete a non-published post."""
    deleted = await svc.delete_post(f"af_tenant_{rbac["org_slug"]}", post_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Post not found or already published")


# ── Messages ────────────────────────────────────────────────────────────

@router.get("/messages")
async def list_messages(
    status: Optional[str] = Query(None),
    limit: int = Query(20, le=100),
    rbac=Depends(require_permission("communications.view_messages")),
):
    """List social media messages, DMs, and comments."""
    return {"data": await svc.list_messages(f"af_tenant_{rbac["org_slug"]}", status, limit)}


@router.post("/messages/{message_id}/respond")
async def respond_to_message(
    message_id: str,
    body: RespondToMessage,
    rbac=Depends(require_permission("communications.manage_messages")),
):
    """Send a manual response to a message/comment."""
    schema = f"af_tenant_{rbac["org_slug"]}"
    try:
        result = await svc.respond_to_message(schema, message_id, body.response)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/messages/{message_id}/ai-respond")
async def ai_respond_to_message(
    message_id: str,
    rbac=Depends(require_permission("communications.manage_messages")),
):
    """Trigger AI response for a message/comment."""
    schema = f"af_tenant_{rbac["org_slug"]}"
    try:
        result = await svc.handle_message_with_ai(schema, message_id)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Stats ────────────────────────────────────────────────────────────────

@router.get("/stats")
async def get_engagement_stats(
    rbac=Depends(require_permission("communications.view_stats")),
):
    """Get engagement stats: likes, comments, shares, message counts."""
    result = await svc.get_engagement_stats(f"af_tenant_{rbac["org_slug"]}")
    return {"data": result}
