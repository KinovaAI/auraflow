"""AuraFlow — Platform Infrastructure Endpoints

DB monitoring, backups, traffic monitoring, and security/intrusion detection.
All endpoints require platform admin access.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.v1.dependencies.rbac import require_platform_admin
from app.services.platform.db_monitor_service import DBMonitorService
from app.services.platform.backup_service import BackupService
from app.services.platform.traffic_monitor_service import TrafficMonitorService
from app.services.platform.security_service import SecurityService
from app.services.platform.audit_service import audit_service

router = APIRouter()

db_svc = DBMonitorService()
backup_svc = BackupService()
traffic_svc = TrafficMonitorService()
security_svc = SecurityService()


# ── Schemas ──────────────────────────────────────────────────────────

class UpdateSchedule(BaseModel):
    cron_expression: Optional[str] = None
    retention_days: Optional[int] = None
    is_active: Optional[bool] = None


class RestoreConfirm(BaseModel):
    token: str


# ── Database Monitoring ──────────────────────────────────────────────

@router.get("/db/health")
async def db_health(admin=Depends(require_platform_admin())):
    return {"data": await db_svc.get_health()}


@router.get("/db/performance")
async def db_performance(admin=Depends(require_platform_admin())):
    return {"data": await db_svc.get_performance()}


@router.get("/db/tables")
async def db_tables(admin=Depends(require_platform_admin())):
    return {"data": await db_svc.get_table_sizes()}


@router.get("/db/connections")
async def db_connections(admin=Depends(require_platform_admin())):
    return {"data": await db_svc.get_active_connections()}


@router.get("/db/slow-queries")
async def db_slow_queries(admin=Depends(require_platform_admin())):
    return {"data": await db_svc.get_slow_queries()}


@router.post("/db/integrity-check")
async def db_integrity_check(admin=Depends(require_platform_admin())):
    return {"data": await db_svc.run_integrity_check()}


# ── Backups ──────────────────────────────────────────────────────────

@router.get("/backups")
async def list_backups(
    backup_type: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    admin=Depends(require_platform_admin()),
):
    return {"data": await backup_svc.list_backups(backup_type, limit)}


@router.post("/backups/database")
async def trigger_db_backup(admin=Depends(require_platform_admin())):
    try:
        result = await backup_svc.trigger_database_backup("manual")
        return {"data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/backups/files")
async def trigger_files_backup(admin=Depends(require_platform_admin())):
    try:
        result = await backup_svc.trigger_files_backup("manual")
        return {"data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/backups/status")
async def backup_status(admin=Depends(require_platform_admin())):
    """Get backup system status: last backup, next scheduled, B2 connection, total size."""
    return {"data": await backup_svc.get_status()}


@router.post("/backups/trigger")
async def trigger_backup(
    backup_type: str = Query("database", regex="^(database|files)$"),
    admin=Depends(require_platform_admin()),
):
    """Trigger a manual backup (database or files)."""
    try:
        if backup_type == "database":
            result = await backup_svc.trigger_database_backup("manual")
        else:
            result = await backup_svc.trigger_files_backup("manual")
        return {"data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/backups/{backup_id}")
async def delete_backup(
    backup_id: str,
    admin=Depends(require_platform_admin()),
):
    """Delete a specific backup from B2 storage and database."""
    deleted = await backup_svc.delete_backup(backup_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Backup not found")
    return {"data": {"deleted": True}}


@router.get("/backups/{backup_id}/download")
async def download_backup(
    backup_id: str,
    admin=Depends(require_platform_admin()),
):
    url = await backup_svc.get_download_url(backup_id)
    if not url:
        raise HTTPException(status_code=404, detail="Backup not found or not completed")
    return {"data": {"download_url": url}}


@router.post("/backups/{backup_id}/restore")
async def request_restore(
    backup_id: str,
    admin=Depends(require_platform_admin()),
):
    token = await backup_svc.request_restore(backup_id)
    return {"data": {"token": token, "expires_in_seconds": 300}}


@router.post("/backups/restore/confirm")
async def confirm_restore(
    body: RestoreConfirm,
    admin=Depends(require_platform_admin()),
):
    try:
        result = await backup_svc.confirm_restore(body.token)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Backup Schedules ────────────────────────────────────────────────

@router.get("/backup-schedules")
async def list_schedules(admin=Depends(require_platform_admin())):
    return {"data": await backup_svc.list_schedules()}


@router.put("/backup-schedules/{schedule_id}")
async def update_schedule(
    schedule_id: str,
    body: UpdateSchedule,
    admin=Depends(require_platform_admin()),
):
    result = await backup_svc.update_schedule(
        schedule_id,
        cron=body.cron_expression,
        retention_days=body.retention_days,
        is_active=body.is_active,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"data": result}


# ── Traffic Monitoring ───────────────────────────────────────────────

@router.get("/traffic/overview")
async def traffic_overview(
    hours: int = Query(24, le=168),
    admin=Depends(require_platform_admin()),
):
    return {"data": await traffic_svc.get_traffic_overview(hours)}


@router.get("/traffic/active-users")
async def active_users(admin=Depends(require_platform_admin())):
    return {"data": await traffic_svc.get_active_users()}


@router.get("/traffic/top-endpoints")
async def top_endpoints(
    hours: int = Query(24, le=168),
    admin=Depends(require_platform_admin()),
):
    return {"data": await traffic_svc.get_top_endpoints(hours)}


@router.get("/traffic/geo")
async def geo_breakdown(
    hours: int = Query(24, le=168),
    admin=Depends(require_platform_admin()),
):
    return {"data": await traffic_svc.get_geo_breakdown(hours)}


# ── Security / Intrusion Detection ───────────────────────────────────

@router.get("/security/events")
async def security_events(
    event_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    acknowledged: Optional[bool] = Query(None),
    limit: int = Query(100, le=500),
    admin=Depends(require_platform_admin()),
):
    return {"data": await security_svc.list_events(event_type, severity, acknowledged, limit)}


@router.get("/security/summary")
async def security_summary(
    hours: int = Query(24, le=168),
    admin=Depends(require_platform_admin()),
):
    return {"data": await security_svc.get_summary(hours)}


@router.put("/security/events/{event_id}/acknowledge")
async def acknowledge_event(
    event_id: str,
    admin=Depends(require_platform_admin()),
):
    user_id = admin.get("user_id", "") if isinstance(admin, dict) else getattr(admin, "user_id", "")
    result = await security_svc.acknowledge_event(event_id, str(user_id))
    if not result:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"data": result}


@router.post("/security/scan")
async def trigger_security_scan(admin=Depends(require_platform_admin())):
    return {"data": await security_svc.run_security_scan()}


# ── Audit Log ──────────────────────────────────────────────────────────

@router.get("/audit-log")
async def list_audit_log(
    action: Optional[str] = Query(None, description="Filter by action"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    user_id: Optional[str] = Query(None, description="Filter by acting user"),
    hours: int = Query(168, le=8760, description="Look-back window in hours"),
    limit: int = Query(100, le=500),
    admin=Depends(require_platform_admin()),
):
    """Query the global audit log — all admin actions, logins, security events."""
    rows = await audit_service.query(
        action=action,
        resource_type=resource_type,
        user_id=user_id,
        hours=hours,
        limit=limit,
    )
    # Serialize UUID/datetime for JSON
    import json
    from datetime import datetime as _dt
    from uuid import UUID as _UUID

    def _ser(obj):
        if isinstance(obj, (_dt,)):
            return obj.isoformat()
        if isinstance(obj, _UUID):
            return str(obj)
        return obj

    return {"data": [
        {k: _ser(v) for k, v in row.items()} for row in rows
    ]}
