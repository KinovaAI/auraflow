"""AuraFlow — Admin Data CRUD Endpoints

Tenant-scoped admin endpoints (audit_log, communication_log, video_views)
and platform-scoped endpoints (announcements, ai_agent_log, backup_schedules).
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, field_validator

from app.api.v1.dependencies.rbac import require_permission, require_platform_admin
from app.db.session import get_tenant_db, get_global_db

router = APIRouter()
platform_router = APIRouter()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _serialize(row) -> dict:
    """Convert asyncpg Record to dict, datetime fields to ISO strings."""
    out = {}
    for k, v in dict(row).items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def _cutoff(days: int) -> datetime:
    """Return a UTC datetime `days` ago from now."""
    return datetime.now(timezone.utc) - timedelta(days=days)


# ══════════════════════════════════════════════════════════════════════════════
# TENANT-SCOPED ENDPOINTS  (router — uses get_tenant_db + require_permission)
# ══════════════════════════════════════════════════════════════════════════════


# ── 1. Audit Log (READ ONLY) ────────────────────────────────────────────────

@router.get("/audit-log")
async def list_audit_log(
    action: Optional[str] = Query(None, description="Filter by action (e.g. create, update, delete)"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type (e.g. member, booking)"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    days: int = Query(30, ge=1, le=365, description="Look-back window in days"),
    limit: int = Query(50, ge=1, le=500, description="Max rows to return"),
    rbac=Depends(require_permission("audit.view")),
):
    """Query the tenant audit log with optional filters."""
    cutoff = _cutoff(days)

    # Build dynamic WHERE clauses
    conditions = ["created_at >= $1"]
    params: list = [cutoff]
    idx = 2

    if action:
        conditions.append(f"action = ${idx}")
        params.append(action)
        idx += 1
    if entity_type:
        conditions.append(f"entity_type = ${idx}")
        params.append(entity_type)
        idx += 1
    if user_id:
        conditions.append(f"user_id = ${idx}::uuid")
        params.append(user_id)
        idx += 1

    where = " AND ".join(conditions)

    try:
        async with get_tenant_db() as db:
            rows = await db.fetch(
                f"""
                SELECT id, user_id, action, entity_type, entity_id,
                       old_values, new_values, ip_address, created_at
                FROM audit_log
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT ${idx}
                """,
                *params, limit,
            )
    except Exception:
        # audit_log table may not exist in tenant schema yet
        rows = []

    return {"data": [_serialize(r) for r in rows]}


# ── 2. Communication Log (READ ONLY) ────────────────────────────────────────

@router.get("/communication-log")
async def list_communication_log(
    channel: Optional[str] = Query(None, description="Filter by channel (email, sms, push)"),
    member_id: Optional[str] = Query(None, description="Filter by member ID"),
    status: Optional[str] = Query(None, description="Filter by status (sent, failed, pending)"),
    days: int = Query(30, ge=1, le=365, description="Look-back window in days"),
    limit: int = Query(50, ge=1, le=500, description="Max rows to return"),
    rbac=Depends(require_permission("communications.view_log")),
):
    """Query the tenant communication log with optional filters."""
    cutoff = _cutoff(days)

    conditions = ["created_at >= $1"]
    params: list = [cutoff]
    idx = 2

    if channel:
        conditions.append(f"channel = ${idx}")
        params.append(channel)
        idx += 1
    if member_id:
        conditions.append(f"member_id = ${idx}::uuid")
        params.append(member_id)
        idx += 1
    if status:
        conditions.append(f"status = ${idx}")
        params.append(status)
        idx += 1

    where = " AND ".join(conditions)

    async with get_tenant_db() as db:
        rows = await db.fetch(
            f"""
            SELECT id, member_id, channel, type, recipient, subject,
                   body_preview, provider_id, status, created_at
            FROM communication_log
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT ${idx}
            """,
            *params, limit,
        )

    return {"data": [_serialize(r) for r in rows]}


# ── 3. Video Views (READ + Analytics) ───────────────────────────────────────

@router.get("/video-views")
async def list_video_views(
    video_id: Optional[str] = Query(None, description="Filter by video ID"),
    member_id: Optional[str] = Query(None, description="Filter by member ID"),
    days: int = Query(30, ge=1, le=365, description="Look-back window in days"),
    limit: int = Query(50, ge=1, le=500, description="Max rows to return"),
    rbac=Depends(require_permission("analytics.view_video")),
):
    """Query video view records with optional filters."""
    cutoff = _cutoff(days)

    conditions = ["created_at >= $1"]
    params: list = [cutoff]
    idx = 2

    if video_id:
        conditions.append(f"video_id = ${idx}::uuid")
        params.append(video_id)
        idx += 1
    if member_id:
        conditions.append(f"member_id = ${idx}::uuid")
        params.append(member_id)
        idx += 1

    where = " AND ".join(conditions)

    async with get_tenant_db() as db:
        rows = await db.fetch(
            f"""
            SELECT id, video_id, member_id, watched_seconds,
                   completed, created_at
            FROM video_views
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT ${idx}
            """,
            *params, limit,
        )

    return {"data": [_serialize(r) for r in rows]}


@router.get("/video-views/stats")
async def video_views_stats(
    video_id: Optional[str] = Query(None, description="Scope stats to a single video"),
    days: int = Query(30, ge=1, le=365, description="Look-back window in days"),
    rbac=Depends(require_permission("analytics.view_video")),
):
    """Aggregate video view statistics: total views, unique viewers,
    average watch time, and completion rate."""
    cutoff = _cutoff(days)

    conditions = ["created_at >= $1"]
    params: list = [cutoff]
    idx = 2

    if video_id:
        conditions.append(f"video_id = ${idx}::uuid")
        params.append(video_id)
        idx += 1

    where = " AND ".join(conditions)

    async with get_tenant_db() as db:
        row = await db.fetchrow(
            f"""
            SELECT
                COUNT(*)::int                          AS total_views,
                COUNT(DISTINCT member_id)::int         AS unique_viewers,
                COALESCE(AVG(watched_seconds), 0)::int AS avg_watch_seconds,
                CASE
                    WHEN COUNT(*) = 0 THEN 0
                    ELSE ROUND(
                        COUNT(*) FILTER (WHERE completed = TRUE)::numeric
                        / COUNT(*)::numeric * 100, 1
                    )
                END                                    AS completion_rate_pct
            FROM video_views
            WHERE {where}
            """,
            *params,
        )

    return {"data": _serialize(row)}


# ══════════════════════════════════════════════════════════════════════════════
# PLATFORM-SCOPED ENDPOINTS  (platform_router — uses get_global_db)
# ══════════════════════════════════════════════════════════════════════════════


# ── 4. Platform Announcements (FULL CRUD) ────────────────────────────────────

class AnnouncementCreate(BaseModel):
    title: str
    body: Optional[str] = None
    type: str = "info"
    is_active: bool = True
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v):
        allowed = ("info", "warning", "critical")
        if v not in allowed:
            raise ValueError(f"type must be one of: {', '.join(allowed)}")
        return v


class AnnouncementUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    type: Optional[str] = None
    is_active: Optional[bool] = None
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v):
        if v is not None:
            allowed = ("info", "warning", "critical")
            if v not in allowed:
                raise ValueError(f"type must be one of: {', '.join(allowed)}")
        return v


@platform_router.get("/announcements")
async def list_announcements(
    active_only: bool = Query(True, description="Only return active announcements"),
    admin=Depends(require_platform_admin()),
):
    """List platform announcements."""
    async with get_global_db() as db:
        if active_only:
            rows = await db.fetch("""
                SELECT id, title, body, type, is_active, starts_at, ends_at,
                       created_by, created_at
                FROM af_global.platform_announcements
                WHERE is_active = TRUE
                ORDER BY created_at DESC
            """)
        else:
            rows = await db.fetch("""
                SELECT id, title, body, type, is_active, starts_at, ends_at,
                       created_by, created_at
                FROM af_global.platform_announcements
                ORDER BY created_at DESC
            """)

    return {"data": [_serialize(r) for r in rows]}


@platform_router.post("/announcements", status_code=201)
async def create_announcement(
    body: AnnouncementCreate,
    admin=Depends(require_platform_admin()),
):
    """Create a new platform announcement."""
    created_by = admin.get("sub") if isinstance(admin, dict) else None

    async with get_global_db() as db:
        row = await db.fetchrow("""
            INSERT INTO af_global.platform_announcements
                (title, body, type, is_active, starts_at, ends_at, created_by)
            VALUES ($1, $2, $3, $4, $5::timestamptz, $6::timestamptz, $7::uuid)
            RETURNING id, title, body, type, is_active, starts_at, ends_at,
                      created_by, created_at
        """,
            body.title, body.body, body.type, body.is_active,
            body.starts_at, body.ends_at, created_by,
        )

    return {"data": _serialize(row)}


@platform_router.put("/announcements/{announcement_id}")
async def update_announcement(
    announcement_id: str,
    body: AnnouncementUpdate,
    admin=Depends(require_platform_admin()),
):
    """Update an existing platform announcement."""
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Build dynamic SET clause
    set_parts = []
    params: list = []
    idx = 1
    for field, value in updates.items():
        if field in ("starts_at", "ends_at"):
            set_parts.append(f"{field} = ${idx}::timestamptz")
        else:
            set_parts.append(f"{field} = ${idx}")
        params.append(value)
        idx += 1

    set_clause = ", ".join(set_parts)
    params.append(announcement_id)

    async with get_global_db() as db:
        row = await db.fetchrow(
            f"""
            UPDATE af_global.platform_announcements
            SET {set_clause}
            WHERE id = ${idx}::uuid
            RETURNING id, title, body, type, is_active, starts_at, ends_at,
                      created_by, created_at
            """,
            *params,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Announcement not found")
    return {"data": _serialize(row)}


@platform_router.delete("/announcements/{announcement_id}", status_code=204)
async def delete_announcement(
    announcement_id: str,
    admin=Depends(require_platform_admin()),
):
    """Delete a platform announcement."""
    async with get_global_db() as db:
        result = await db.execute("""
            DELETE FROM af_global.platform_announcements
            WHERE id = $1::uuid
        """, announcement_id)

    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Announcement not found")
    return Response(status_code=204)


# ── 5. Platform AI Agent Log (READ ONLY) ────────────────────────────────────

@platform_router.get("/ai-agent-log")
async def list_ai_agent_log(
    agent_type: Optional[str] = Query(None, description="Filter by agent type"),
    status: Optional[str] = Query(None, description="Filter by status (success, error, timeout)"),
    days: int = Query(7, ge=1, le=365, description="Look-back window in days"),
    limit: int = Query(50, ge=1, le=500, description="Max rows to return"),
    admin=Depends(require_platform_admin()),
):
    """Query platform AI agent execution logs."""
    cutoff = _cutoff(days)

    conditions = ["created_at >= $1"]
    params: list = [cutoff]
    idx = 2

    if agent_type:
        conditions.append(f"agent_type = ${idx}")
        params.append(agent_type)
        idx += 1
    if status:
        conditions.append(f"status = ${idx}")
        params.append(status)
        idx += 1

    where = " AND ".join(conditions)

    async with get_global_db() as db:
        rows = await db.fetch(
            f"""
            SELECT id, agent_type, action, details,
                   status, related_id, created_at
            FROM af_global.platform_ai_agent_log
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT ${idx}
            """,
            *params, limit,
        )

    return {"data": [_serialize(r) for r in rows]}


# ── 6. Platform Backup Schedules (FULL CRUD) ────────────────────────────────

class BackupScheduleCreate(BaseModel):
    backup_type: str
    cron_expression: str
    retention_days: int = 30
    is_active: bool = True

    @field_validator("backup_type")
    @classmethod
    def validate_backup_type(cls, v):
        allowed = ("database", "files")
        if v not in allowed:
            raise ValueError(f"backup_type must be one of: {', '.join(allowed)}")
        return v


class BackupScheduleUpdate(BaseModel):
    backup_type: Optional[str] = None
    cron_expression: Optional[str] = None
    retention_days: Optional[int] = None
    is_active: Optional[bool] = None

    @field_validator("backup_type")
    @classmethod
    def validate_backup_type(cls, v):
        if v is not None:
            allowed = ("database", "files")
            if v not in allowed:
                raise ValueError(f"backup_type must be one of: {', '.join(allowed)}")
        return v


@platform_router.get("/backup-schedules")
async def list_backup_schedules(
    admin=Depends(require_platform_admin()),
):
    """List all platform backup schedules."""
    async with get_global_db() as db:
        rows = await db.fetch("""
            SELECT id, backup_type, cron_expression,
                   retention_days, is_active, last_run_at, next_run_at,
                   created_at
            FROM af_global.platform_backup_schedule
            ORDER BY created_at DESC
        """)

    return {"data": [_serialize(r) for r in rows]}


@platform_router.post("/backup-schedules", status_code=201)
async def create_backup_schedule(
    body: BackupScheduleCreate,
    admin=Depends(require_platform_admin()),
):
    """Create a new backup schedule."""
    async with get_global_db() as db:
        row = await db.fetchrow("""
            INSERT INTO af_global.platform_backup_schedule
                (backup_type, cron_expression,
                 retention_days, is_active)
            VALUES ($1, $2, $3, $4)
            RETURNING id, backup_type, cron_expression,
                      retention_days, is_active, last_run_at, next_run_at,
                      created_at
        """,
            body.backup_type, body.cron_expression,
            body.retention_days, body.is_active,
        )

    return {"data": _serialize(row)}


@platform_router.put("/backup-schedules/{schedule_id}")
async def update_backup_schedule(
    schedule_id: str,
    body: BackupScheduleUpdate,
    admin=Depends(require_platform_admin()),
):
    """Update an existing backup schedule."""
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_parts = []
    params: list = []
    idx = 1
    for field, value in updates.items():
        set_parts.append(f"{field} = ${idx}")
        params.append(value)
        idx += 1

    set_clause = ", ".join(set_parts)
    params.append(schedule_id)

    async with get_global_db() as db:
        row = await db.fetchrow(
            f"""
            UPDATE af_global.platform_backup_schedule
            SET {set_clause}
            WHERE id = ${idx}::uuid
            RETURNING id, backup_type, cron_expression,
                      retention_days, is_active, last_run_at, next_run_at,
                      created_at
            """,
            *params,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"data": _serialize(row)}


@platform_router.delete("/backup-schedules/{schedule_id}", status_code=204)
async def delete_backup_schedule(
    schedule_id: str,
    admin=Depends(require_platform_admin()),
):
    """Delete a backup schedule."""
    async with get_global_db() as db:
        result = await db.execute("""
            DELETE FROM af_global.platform_backup_schedule
            WHERE id = $1::uuid
        """, schedule_id)

    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Schedule not found")
    return Response(status_code=204)
