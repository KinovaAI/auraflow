"""AuraFlow — Notification Endpoints

List, read, and delete notifications for the authenticated user.
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.v1.dependencies.auth import get_current_user
from app.services.notifications.notification_service import NotificationService

router = APIRouter()
svc = NotificationService()


@router.get("")
async def list_notifications(
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    current_user: dict = Depends(get_current_user),
):
    """List notifications for the current user, newest first."""
    user_id = current_user["sub"]
    notifications = await svc.list_notifications(user_id, limit=limit, offset=offset)
    return {"data": notifications}


@router.get("/unread-count")
async def get_unread_count(
    current_user: dict = Depends(get_current_user),
):
    """Get the number of unread notifications for the current user."""
    user_id = current_user["sub"]
    count = await svc.get_unread_count(user_id)
    return {"data": {"count": count}}


@router.put("/read-all")
async def mark_all_read(
    current_user: dict = Depends(get_current_user),
):
    """Mark all of the current user's notifications as read."""
    user_id = current_user["sub"]
    count = await svc.mark_all_read(user_id)
    return {"marked": count}


@router.put("/{notification_id}/read")
async def mark_read(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Mark a single notification as read."""
    notification = await svc.mark_read(notification_id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"data": notification}


@router.delete("/{notification_id}", status_code=204)
async def delete_notification(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete a single notification."""
    deleted = await svc.delete(notification_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Notification not found")
