"""AuraFlow — Video Library Endpoints

BYOA (Bring Your Own Account) video library. Studios connect their own
YouTube channel or Mux account. AuraFlow never hosts or pays for video.
"""
import secrets
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.api.v1.dependencies.rbac import require_permission
from app.core.redis import get_redis
from app.core.tenant_context import get_organization_id
from app.services.video.video_service import VideoService
from app.services.video.youtube_service import YouTubeService
from app.services.video.mux_service import MuxService
from app.core.config import settings

router = APIRouter()

video_svc = VideoService()
youtube_svc = YouTubeService()
mux_svc = MuxService()


# ── Schemas ──────────────────────────────────────────────────────────────────

class YouTubeConnectRequest(BaseModel):
    api_key: str
    channel_id: str

class MuxConnectRequest(BaseModel):
    token_id: str
    token_secret: str

class UpdateVideoRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[str] = None
    visibility: Optional[str] = None
    is_published: Optional[bool] = None
    tags: Optional[list[str]] = None
    sort_order: Optional[int] = None
    membership_type_ids: Optional[list[str]] = None

class CategoryRequest(BaseModel):
    name: str
    description: Optional[str] = None
    slug: Optional[str] = None

class UpdateCategoryRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    slug: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None

class RecordViewRequest(BaseModel):
    watched_seconds: int = 0
    completed: bool = False

class MuxUploadRequest(BaseModel):
    cors_origin: Optional[str] = None


def _serialize(row: dict) -> dict:
    """Convert datetime fields to ISO strings."""
    out = {}
    for k, v in row.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


# ── Provider Connection ──────────────────────────────────────────────────────

@router.get("/connect/status")
async def get_connection_status(rbac=Depends(require_permission("video.view_library"))):
    """Get which video providers are connected."""
    org_id = get_organization_id()
    return {"data": await video_svc.get_connection_status(org_id)}


@router.post("/connect/youtube/test")
async def test_youtube_connection(body: YouTubeConnectRequest, rbac=Depends(require_permission("video.test_youtube"))):
    """Test YouTube credentials without saving."""
    result = await youtube_svc.test_connection(body.api_key, body.channel_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"data": result}


@router.post("/connect/youtube")
async def connect_youtube(body: YouTubeConnectRequest, rbac=Depends(require_permission("video.connect_youtube"))):
    """Save YouTube API key and channel ID."""
    # Validate first
    result = await youtube_svc.test_connection(body.api_key, body.channel_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])

    org_id = get_organization_id()
    await youtube_svc.save_credentials(org_id, body.api_key, body.channel_id)
    return {"data": {"connected": True, **result}}


@router.delete("/connect/youtube")
async def disconnect_youtube(rbac=Depends(require_permission("video.disconnect_youtube"))):
    """Remove YouTube credentials."""
    org_id = get_organization_id()
    await youtube_svc.remove_credentials(org_id)
    return {"data": {"disconnected": True}}


@router.post("/connect/mux/test")
async def test_mux_connection(body: MuxConnectRequest, rbac=Depends(require_permission("video.test_mux"))):
    """Test Mux credentials without saving."""
    result = await mux_svc.test_connection(body.token_id, body.token_secret)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"data": result}


@router.post("/connect/mux")
async def connect_mux(body: MuxConnectRequest, rbac=Depends(require_permission("video.connect_mux"))):
    """Save Mux access token and secret."""
    result = await mux_svc.test_connection(body.token_id, body.token_secret)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])

    org_id = get_organization_id()
    await mux_svc.save_credentials(org_id, body.token_id, body.token_secret)
    return {"data": {"connected": True, **result}}


@router.delete("/connect/mux")
async def disconnect_mux(rbac=Depends(require_permission("video.disconnect_mux"))):
    """Remove Mux credentials."""
    org_id = get_organization_id()
    await mux_svc.remove_credentials(org_id)
    return {"data": {"disconnected": True}}


# ── Video Library (Admin) ────────────────────────────────────────────────────

@router.get("/library")
async def list_videos(
    category_id: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    rbac=Depends(require_permission("video.view_library")),
):
    """List all videos in the library (admin view)."""
    videos = await video_svc.list_videos(
        category_id=category_id,
        source=source,
        search=search,
        limit=limit,
        offset=offset,
    )
    return {"data": [_serialize(v) for v in videos]}


@router.get("/library/{video_id}")
async def get_video(video_id: str, rbac=Depends(require_permission("video.view_library"))):
    """Get a single video with full details."""
    video = await video_svc.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return {"data": _serialize(video)}


@router.put("/library/{video_id}")
async def update_video(video_id: str, body: UpdateVideoRequest, rbac=Depends(require_permission("video.edit_video"))):
    """Update video metadata, visibility, or access rules."""
    data = body.model_dump(exclude_none=True)
    video = await video_svc.update_video(video_id, data)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return {"data": _serialize(video)}


@router.delete("/library/{video_id}")
async def delete_video(video_id: str, rbac=Depends(require_permission("video.delete_video"))):
    """Soft-delete a video (hides it)."""
    deleted = await video_svc.delete_video(video_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Video not found")
    return {"data": {"deleted": True}}


# ── Sync ─────────────────────────────────────────────────────────────────────

@router.post("/sync")
async def sync_all(rbac=Depends(require_permission("video.sync_videos"))):
    """Sync videos from all connected providers."""
    org_id = get_organization_id()
    results = await video_svc.sync_all(org_id)
    return {"data": results}


@router.post("/sync/youtube")
async def sync_youtube(rbac=Depends(require_permission("video.sync_videos"))):
    """Sync videos from YouTube."""
    org_id = get_organization_id()
    result = await youtube_svc.sync_videos(org_id)
    return {"data": result}


@router.post("/sync/mux")
async def sync_mux(rbac=Depends(require_permission("video.sync_videos"))):
    """Sync videos from Mux."""
    org_id = get_organization_id()
    result = await mux_svc.sync_assets(org_id)
    return {"data": result}


# ── Categories ───────────────────────────────────────────────────────────────

@router.get("/categories")
async def list_categories(rbac=Depends(require_permission("video.view_categories"))):
    """List video categories."""
    categories = await video_svc.list_categories()
    return {"data": [_serialize(c) for c in categories]}


@router.post("/categories")
async def create_category(body: CategoryRequest, rbac=Depends(require_permission("video.create_category"))):
    """Create a video category."""
    category = await video_svc.create_category(body.name, body.description, body.slug)
    return {"data": _serialize(category)}


@router.put("/categories/{category_id}")
async def update_category(
    category_id: str,
    body: UpdateCategoryRequest,
    rbac=Depends(require_permission("video.edit_category")),
):
    """Update a video category."""
    data = body.model_dump(exclude_none=True)
    category = await video_svc.update_category(category_id, data)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"data": _serialize(category)}


@router.delete("/categories/{category_id}")
async def delete_category(category_id: str, rbac=Depends(require_permission("video.delete_category"))):
    """Soft-delete a video category."""
    deleted = await video_svc.delete_category(category_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"data": {"deleted": True}}


# ── Mux Upload ───────────────────────────────────────────────────────────────

@router.post("/upload/mux")
async def create_mux_upload(body: MuxUploadRequest, rbac=Depends(require_permission("video.upload"))):
    """Get a Mux direct upload URL. The studio uploads directly to Mux."""
    org_id = get_organization_id()
    creds = await mux_svc.get_credentials(org_id)
    if not creds:
        raise HTTPException(status_code=400, detail="Mux not connected")

    result = await mux_svc.create_upload_url(
        creds["token_id"], creds["token_secret"], body.cors_origin
    )
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "Upload URL creation failed"))
    return {"data": result}


# ── YouTube OAuth + Upload ────────────────────────────────────────────────────

@router.get("/connect/youtube/oauth")
async def youtube_oauth_start(rbac=Depends(require_permission("video.start_youtube_oauth"))):
    """Get the Google OAuth URL for YouTube upload authorization."""
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=501, detail="Google OAuth not configured on this server")
    org_id = get_organization_id()
    # Generate CSRF token and store org_id mapping in Redis
    csrf_token = secrets.token_urlsafe(32)
    redis = await get_redis()
    if redis:
        await redis.set(f"oauth_csrf:{csrf_token}", org_id, ex=600)
    url = youtube_svc.get_oauth_url(csrf_token)
    return {"data": {"oauth_url": url}}


@router.get("/connect/youtube/oauth/callback")
async def youtube_oauth_callback(code: str = Query(...), state: str = Query(...)):
    """Handle Google OAuth callback — exchanges code for tokens."""
    # Validate CSRF token and retrieve org_id from Redis
    redis = await get_redis()
    if not redis:
        return RedirectResponse(
            url=f"{settings.APP_URL}/dashboard/video?youtube_oauth=error&message=Service+temporarily+unavailable",
        )
    org_id = await redis.get(f"oauth_csrf:{state}")
    if not org_id:
        return RedirectResponse(
            url=f"{settings.APP_URL}/dashboard/video?youtube_oauth=error&message=Invalid+or+expired+OAuth+state+token",
        )
    await redis.delete(f"oauth_csrf:{state}")
    org_id = org_id.decode() if isinstance(org_id, bytes) else org_id
    try:
        await youtube_svc.handle_oauth_callback(org_id, code)
    except ValueError as e:
        return RedirectResponse(
            url=f"{settings.APP_URL}/dashboard/video?youtube_oauth=error&message={str(e)}",
        )
    return RedirectResponse(
        url=f"{settings.APP_URL}/dashboard/video?youtube_oauth=success",
    )


@router.get("/connect/youtube/oauth/status")
async def youtube_oauth_status(rbac=Depends(require_permission("video.view_youtube_oauth_status"))):
    """Check if YouTube upload authorization is set up."""
    org_id = get_organization_id()
    refresh_token = await youtube_svc.get_oauth_credentials(org_id)
    return {"data": {"upload_authorized": refresh_token is not None}}


@router.post("/upload/youtube")
async def upload_to_youtube(
    file: UploadFile = File(...),
    title: str = Form(...),
    description: str = Form(""),
    privacy: str = Form("unlisted"),
    rbac=Depends(require_permission("video.upload")),
):
    """Upload a video file to the org's YouTube channel."""
    org_id = get_organization_id()

    content = await file.read()
    if len(content) > 128 * 1024 * 1024 * 1024:  # 128 GB max
        raise HTTPException(status_code=413, detail="File too large")

    try:
        result = await youtube_svc.upload_video(
            org_id=org_id,
            file_content=content,
            title=title,
            description=description,
            privacy=privacy,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"data": result}


# ── Member-Facing Browse ─────────────────────────────────────────────────────

@router.get("/browse")
async def browse_videos(
    category_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    rbac=Depends(require_permission("video.browse")),
):
    """Browse published videos the current user has access to."""
    # For staff roles, show all published videos; for members, filter by membership
    if rbac["role"] in ("owner", "admin", "instructor", "front_desk", "platform_admin"):
        videos = await video_svc.list_videos(
            category_id=category_id,
            published_only=True,
            limit=limit,
            offset=offset,
        )
    else:
        # Members see only videos matching their active memberships
        videos = await video_svc.get_accessible_videos(
            member_id=rbac["user_id"],
            category_id=category_id,
            limit=limit,
            offset=offset,
        )
    return {"data": [_serialize(v) for v in videos]}


@router.get("/browse/{video_id}")
async def browse_video(
    video_id: str,
    rbac=Depends(require_permission("video.browse")),
):
    """Get a single video for playback (checks access)."""
    if rbac["role"] in ("owner", "admin", "instructor", "front_desk", "platform_admin"):
        video = await video_svc.get_video(video_id)
    else:
        video = await video_svc.get_accessible_video(video_id, rbac["user_id"])

    if not video:
        raise HTTPException(status_code=404, detail="Video not found or access denied")
    return {"data": _serialize(video)}


@router.post("/browse/{video_id}/view")
async def record_view(
    video_id: str,
    body: RecordViewRequest,
    rbac=Depends(require_permission("video.record_view")),
):
    """Record a video view event."""
    import asyncpg
    try:
        await video_svc.record_view(video_id, rbac["user_id"], body.watched_seconds, body.completed)
    except asyncpg.ForeignKeyViolationError:
        raise HTTPException(status_code=404, detail="Video not found")
    return {"data": {"recorded": True}}


# ── Analytics ────────────────────────────────────────────────────────────────

@router.get("/stats")
async def get_library_stats(rbac=Depends(require_permission("video.view_stats"))):
    """Get library-level video statistics."""
    stats = await video_svc.get_library_stats()
    return {"data": _serialize(stats)}


@router.get("/stats/{video_id}")
async def get_video_stats(video_id: str, rbac=Depends(require_permission("video.view_stats"))):
    """Get statistics for a specific video."""
    stats = await video_svc.get_video_stats(video_id)
    return {"data": stats}
