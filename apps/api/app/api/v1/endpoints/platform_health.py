"""AuraFlow — Platform System Health (Admin Endpoints)

System health overview: database, server (OS), Redis, Celery status.
"""
from fastapi import APIRouter, Depends

from app.api.v1.dependencies.rbac import require_platform_admin
from app.services.platform.system_health_service import SystemHealthService

router = APIRouter()
health_svc = SystemHealthService()


@router.get("/system", dependencies=[Depends(require_platform_admin())])
async def system_health():
    return {"data": await health_svc.get_system_health()}


@router.get("/queries", dependencies=[Depends(require_platform_admin())])
async def active_queries():
    return {"data": await health_svc.get_active_queries()}
