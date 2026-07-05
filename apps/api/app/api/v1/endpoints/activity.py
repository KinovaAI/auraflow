"""AuraFlow — Activity Feed Endpoints

Org-wide activity feed (admin/owner) and per-member timelines.
"""
from fastapi import APIRouter, Depends, Query

from app.api.v1.dependencies.auth import get_current_user
from app.api.v1.dependencies.rbac import require_permission
from app.services.activity.activity_service import ActivityService

router = APIRouter()
svc = ActivityService()


@router.get("/feed")
async def get_org_feed(
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    rbac: dict = Depends(require_permission("analytics.view_activity")),
):
    """Org-wide activity feed. Restricted to owners and admins."""
    activities = await svc.get_org_feed(limit=limit, offset=offset)
    return {"data": activities}


@router.get("/member/{member_id}")
async def get_member_timeline(
    member_id: str,
    limit: int = Query(50, le=200),
    current_user: dict = Depends(get_current_user),
):
    """Activity timeline for a specific member."""
    activities = await svc.get_member_timeline(member_id, limit=limit)
    return {"data": activities}
