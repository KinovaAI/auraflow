"""AuraFlow — AI Manager Endpoints

Admin-facing endpoints for viewing and managing AI resolution requests
and Sub-Finder 3000 substitute searches.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.v1.dependencies.rbac import require_permission
from app.services.ai.ai_manager_service import AIManagerService
from app.services.ai.sub_finder_service import SubFinderService

router = APIRouter()
_ai_mgr = AIManagerService()
_sub_finder = SubFinderService()


# ── Request Schemas ──────────────────────────────────────────────────────────

class InitiateSubSearchRequest(BaseModel):
    session_id: str
    instructor_id: str
    reason: str | None = None


class EscalateRequest(BaseModel):
    reason: str | None = None


class ResolveRequest(BaseModel):
    resolution: str | None = None


class SubResponseRequest(BaseModel):
    instructor_id: str
    accepted: bool


# ── Resolution Requests ─────────────────────────────────────────────────────

@router.get("/resolutions")
async def list_resolutions(
    status: str | None = Query(None),
    limit: int = Query(50, le=200),
    _user=Depends(require_permission("ai.view_resolutions")),
):
    return await _ai_mgr.list_resolutions(status=status, limit=limit)


@router.get("/resolutions/{request_id}")
async def get_resolution(
    request_id: str,
    _user=Depends(require_permission("ai.view_resolutions")),
):
    result = await _ai_mgr.get_resolution(request_id)
    if not result:
        raise HTTPException(status_code=404, detail="Resolution not found")
    return result


@router.post("/resolutions/{request_id}/escalate")
async def escalate_resolution(
    request_id: str,
    body: EscalateRequest,
    _user=Depends(require_permission("ai.manage_resolutions")),
):
    result = await _ai_mgr.escalate(request_id, reason=body.reason)
    if not result:
        raise HTTPException(status_code=404, detail="Resolution not found")
    return result


@router.post("/resolutions/{request_id}/resolve")
async def resolve_resolution(
    request_id: str,
    body: ResolveRequest,
    _user=Depends(require_permission("ai.manage_resolutions")),
):
    result = await _ai_mgr.resolve_manually(request_id, resolution=body.resolution)
    if not result:
        raise HTTPException(status_code=404, detail="Resolution not found")
    return result


# ── Sub-Finder Requests ─────────────────────────────────────────────────────

@router.get("/sub-requests")
async def list_sub_requests(
    status: str | None = Query(None),
    limit: int = Query(50, le=200),
    _user=Depends(require_permission("office_management.view_requests")),
):
    return await _sub_finder.list_requests(status=status, limit=limit)


@router.get("/sub-requests/{request_id}")
async def get_sub_request(
    request_id: str,
    _user=Depends(require_permission("office_management.view_requests")),
):
    result = await _sub_finder.get_request(request_id)
    if not result:
        raise HTTPException(status_code=404, detail="Sub request not found")
    return result


@router.post("/sub-requests")
async def initiate_sub_search(
    body: InitiateSubSearchRequest,
    _user=Depends(require_permission("office_management.manage_requests")),
):
    try:
        result = await _sub_finder.initiate_sub_search(
            session_id=body.session_id,
            instructor_id=body.instructor_id,
            reason=body.reason,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sub-requests/{request_id}/cancel")
async def cancel_sub_search(
    request_id: str,
    _user=Depends(require_permission("office_management.manage_requests")),
):
    try:
        result = await _sub_finder.cancel_request(request_id)
        if not result:
            raise HTTPException(status_code=404, detail="Sub request not found")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sub-requests/{request_id}/respond")
async def handle_sub_response(
    request_id: str,
    body: SubResponseRequest,
    _user=Depends(require_permission("office_management.manage_requests")),
):
    """Manually record a substitute's response (for admin override)."""
    try:
        result = await _sub_finder.handle_sub_response(
            request_id=request_id,
            instructor_id=body.instructor_id,
            accepted=body.accepted,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
