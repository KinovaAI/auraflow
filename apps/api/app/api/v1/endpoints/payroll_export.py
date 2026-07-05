"""AuraFlow — Payroll Export & Integration Endpoints

CSV export, Gusto OAuth connect/disconnect, QuickBooks OAuth,
employee mapping, and payroll push.
"""
import io
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, RedirectResponse
from pydantic import BaseModel

from app.api.v1.dependencies.auth import get_current_user
from app.api.v1.dependencies.rbac import require_permission
from app.core.config import settings
from app.core.redis import get_redis
from app.core.tenant_context import get_organization_id
from app.services.integrations.payroll_csv_service import PayrollCSVService
from app.services.integrations.gusto_service import GustoService
from app.services.integrations.quickbooks_service import QuickBooksService
from app.services.integrations.payroll_mapping_service import PayrollMappingService

router = APIRouter()
csv_svc = PayrollCSVService()
gusto_svc = GustoService()
qb_svc = QuickBooksService()
mapping_svc = PayrollMappingService()


# ── Schemas ──────────────────────────────────────────────────────────────────

class EmployeeMappingRequest(BaseModel):
    instructor_id: str
    external_employee_id: str
    external_employee_name: Optional[str] = None


# ── CSV Export ───────────────────────────────────────────────────────────────

@router.get("/csv/{run_id}")
async def export_csv(
    run_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("payroll.export_csv")),
):
    """Download payroll run as CSV."""
    try:
        csv_content, filename = await csv_svc.export_payroll_csv(run_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return StreamingResponse(
        io.StringIO(csv_content),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Combined Status ──────────────────────────────────────────────────────────

@router.get("/status")
async def integration_status(
    user=Depends(get_current_user),
    _=Depends(require_permission("payroll.view_export_status")),
):
    """Get connection status for all payroll providers."""
    org_id = get_organization_id()
    gusto = await gusto_svc.get_connection_status(org_id)
    qb = await qb_svc.get_connection_status(org_id)
    return {
        "data": {
            "gusto": gusto,
            "quickbooks": qb,
        }
    }


# ── Gusto OAuth ──────────────────────────────────────────────────────────────

@router.get("/gusto/authorize")
async def gusto_authorize(
    user=Depends(get_current_user),
    _=Depends(require_permission("payroll.connect_gusto")),
):
    """Get Gusto OAuth2 authorization URL."""
    org_id = get_organization_id()
    # Generate CSRF token and store org_id mapping in Redis
    csrf_token = secrets.token_urlsafe(32)
    redis = await get_redis()
    if redis:
        await redis.set(f"oauth_csrf:{csrf_token}", org_id, ex=600)
    url = gusto_svc.get_authorize_url(csrf_token)
    return {"data": {"authorize_url": url}}


@router.get("/gusto/callback")
async def gusto_callback(
    code: str = Query(...),
    state: str = Query(...),
):
    """OAuth callback from Gusto. state = CSRF token mapped to org_id in Redis."""
    # Validate CSRF token and retrieve org_id from Redis
    redis = await get_redis()
    if not redis:
        return RedirectResponse(
            url=f"{settings.APP_URL}/dashboard/integrations?gusto=error&detail=Service+temporarily+unavailable"
        )
    org_id = await redis.get(f"oauth_csrf:{state}")
    if not org_id:
        return RedirectResponse(
            url=f"{settings.APP_URL}/dashboard/integrations?gusto=error&detail=Invalid+or+expired+OAuth+state+token"
        )
    await redis.delete(f"oauth_csrf:{state}")
    org_id = org_id.decode() if isinstance(org_id, bytes) else org_id
    try:
        await gusto_svc.handle_callback(org_id=org_id, code=code)
    except Exception as e:
        return RedirectResponse(
            url=f"{settings.APP_URL}/dashboard/integrations?gusto=error&detail={str(e)[:100]}"
        )
    return RedirectResponse(
        url=f"{settings.APP_URL}/dashboard/integrations?gusto=connected"
    )


@router.delete("/gusto/disconnect")
async def gusto_disconnect(
    user=Depends(get_current_user),
    _=Depends(require_permission("payroll.disconnect_gusto")),
):
    """Disconnect Gusto integration."""
    org_id = get_organization_id()
    await gusto_svc.disconnect(org_id)
    return {"data": {"connected": False}}


@router.get("/gusto/employees")
async def gusto_employees(
    user=Depends(get_current_user),
    _=Depends(require_permission("payroll.view_gusto")),
):
    """List employees from Gusto for mapping."""
    org_id = get_organization_id()
    try:
        employees = await gusto_svc.list_employees(org_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": employees}


@router.post("/gusto/push/{run_id}")
async def gusto_push(
    run_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("payroll.push_gusto")),
):
    """Push finalized payroll to Gusto."""
    org_id = get_organization_id()
    try:
        result = await gusto_svc.push_payroll(org_id, run_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": result}


# ── QuickBooks OAuth ─────────────────────────────────────────────────────────

@router.get("/quickbooks/authorize")
async def qb_authorize(
    user=Depends(get_current_user),
    _=Depends(require_permission("payroll.connect_quickbooks")),
):
    """Get QuickBooks OAuth2 authorization URL."""
    org_id = get_organization_id()
    # Generate CSRF token and store org_id mapping in Redis
    csrf_token = secrets.token_urlsafe(32)
    redis = await get_redis()
    if redis:
        await redis.set(f"oauth_csrf:{csrf_token}", org_id, ex=600)
    url = qb_svc.get_authorize_url(csrf_token)
    return {"data": {"authorize_url": url}}


@router.get("/quickbooks/callback")
async def qb_callback(
    code: str = Query(...),
    state: str = Query(...),
    realmId: str = Query(...),
):
    """OAuth callback from QuickBooks. state = CSRF token mapped to org_id in Redis."""
    # Validate CSRF token and retrieve org_id from Redis
    redis = await get_redis()
    if not redis:
        return RedirectResponse(
            url=f"{settings.APP_URL}/dashboard/integrations?quickbooks=error&detail=Service+temporarily+unavailable"
        )
    org_id = await redis.get(f"oauth_csrf:{state}")
    if not org_id:
        return RedirectResponse(
            url=f"{settings.APP_URL}/dashboard/integrations?quickbooks=error&detail=Invalid+or+expired+OAuth+state+token"
        )
    await redis.delete(f"oauth_csrf:{state}")
    org_id = org_id.decode() if isinstance(org_id, bytes) else org_id
    try:
        await qb_svc.handle_callback(org_id=org_id, code=code, realm_id=realmId)
    except Exception as e:
        return RedirectResponse(
            url=f"{settings.APP_URL}/dashboard/integrations?quickbooks=error&detail={str(e)[:100]}"
        )
    return RedirectResponse(
        url=f"{settings.APP_URL}/dashboard/integrations?quickbooks=connected"
    )


@router.delete("/quickbooks/disconnect")
async def qb_disconnect(
    user=Depends(get_current_user),
    _=Depends(require_permission("payroll.disconnect_quickbooks")),
):
    """Disconnect QuickBooks integration."""
    org_id = get_organization_id()
    await qb_svc.disconnect(org_id)
    return {"data": {"connected": False}}


@router.get("/quickbooks/employees")
async def qb_employees(
    user=Depends(get_current_user),
    _=Depends(require_permission("payroll.view_quickbooks")),
):
    """List employees from QuickBooks for mapping."""
    org_id = get_organization_id()
    try:
        employees = await qb_svc.list_employees(org_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": employees}


@router.post("/quickbooks/push/{run_id}")
async def qb_push(
    run_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("payroll.push_quickbooks")),
):
    """Push finalized payroll as time activities to QuickBooks."""
    org_id = get_organization_id()
    try:
        result = await qb_svc.push_time_activities(org_id, run_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": result}


# ── Employee Mapping ─────────────────────────────────────────────────────────

@router.get("/mappings/{provider}")
async def list_mappings(
    provider: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("payroll.view_mappings")),
):
    """List employee mappings for a provider."""
    if provider not in ("gusto", "quickbooks"):
        raise HTTPException(status_code=400, detail="Invalid provider")
    mappings = await mapping_svc.list_mappings(provider)
    return {"data": mappings}


@router.post("/mappings/{provider}", status_code=201)
async def create_mapping(
    provider: str,
    body: EmployeeMappingRequest,
    user=Depends(get_current_user),
    _=Depends(require_permission("payroll.manage_mappings")),
):
    """Create or update an employee mapping."""
    if provider not in ("gusto", "quickbooks"):
        raise HTTPException(status_code=400, detail="Invalid provider")
    mapping = await mapping_svc.upsert_mapping(
        body.instructor_id,
        provider,
        body.external_employee_id,
        body.external_employee_name,
    )
    return {"data": mapping}


@router.delete("/mappings/{provider}/{instructor_id}")
async def delete_mapping(
    provider: str,
    instructor_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("payroll.manage_mappings")),
):
    """Delete an employee mapping."""
    if provider not in ("gusto", "quickbooks"):
        raise HTTPException(status_code=400, detail="Invalid provider")
    await mapping_svc.delete_mapping(instructor_id, provider)
    return {"data": {"deleted": True}}
