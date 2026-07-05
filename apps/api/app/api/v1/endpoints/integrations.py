"""AuraFlow — Integration Endpoints

ClassPass marketplace integration: connection, config, reservations, webhooks.
Google My Business (Business Profile): OAuth, review sync, location management.
"""
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.api.v1.dependencies.auth import get_current_user
from app.api.v1.dependencies.rbac import require_permission
from app.core.config import settings
from app.core.logging import logger
from app.core.redis import get_redis
from app.services.integrations.classpass_service import ClassPassService
from app.services.integrations.gmb_service import GmbService
from app.services.integrations.emr import emr_service

router = APIRouter()

# Keep stub routers for webhook module compatibility
stripe_router = APIRouter()
mux_router = APIRouter()

cp_svc = ClassPassService()
gmb_svc = GmbService()


# ── Schemas ──────────────────────────────────────────────────────────────────

class ClassPassConnect(BaseModel):
    studio_id: str
    venue_id: str


class ClassPassConfigUpdate(BaseModel):
    credit_rate: Optional[int] = None
    auto_confirm: Optional[bool] = None


class EmrConnect(BaseModel):
    protocol: str  # 'fhir_r4' or 'hl7v2'
    # FHIR fields
    base_url: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    token_url: Optional[str] = None
    # HL7v2 fields
    host: Optional[str] = None
    port: Optional[int] = None
    max_spots_per_class: Optional[int] = None
    blackout_class_types: Optional[list[str]] = None


class ClassPassReservation(BaseModel):
    classpass_reservation_id: str
    class_session_id: Optional[str] = None
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    credits: int = 0


class ClassPassCancellation(BaseModel):
    classpass_reservation_id: str


# ── ClassPass Connection ─────────────────────────────────────────────────────

@router.post("/classpass/connect", status_code=201)
async def connect_classpass(
    body: ClassPassConnect,
    user=Depends(get_current_user),
    _=Depends(require_permission("integrations.connect_classpass")),
):
    config = await cp_svc.connect(body.studio_id, body.venue_id)
    return {"data": config}


@router.get("/classpass/config/{studio_id}")
async def get_classpass_config(
    studio_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("integrations.view_classpass")),
):
    config = await cp_svc.get_config(studio_id)
    if not config:
        raise HTTPException(status_code=404, detail="ClassPass not configured for this studio")
    return {"data": config}


@router.put("/classpass/config/{studio_id}")
async def update_classpass_config(
    studio_id: str,
    body: ClassPassConfigUpdate,
    user=Depends(get_current_user),
    _=Depends(require_permission("integrations.configure_classpass")),
):
    data = body.model_dump(exclude_none=True)
    config = await cp_svc.update_config(studio_id, data)
    if not config:
        raise HTTPException(status_code=404, detail="ClassPass not configured for this studio")
    return {"data": config}


@router.post("/classpass/disconnect/{studio_id}")
async def disconnect_classpass(
    studio_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("integrations.disconnect_classpass")),
):
    disconnected = await cp_svc.disconnect(studio_id)
    if not disconnected:
        raise HTTPException(status_code=404, detail="ClassPass not configured for this studio")
    return {"data": {"disconnected": True}}


# ── Reservations ─────────────────────────────────────────────────────────────

@router.get("/classpass/reservations")
async def list_reservations(
    class_session_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    user=Depends(get_current_user),
    _=Depends(require_permission("integrations.view_classpass_data")),
):
    reservations = await cp_svc.list_reservations(
        class_session_id=class_session_id,
        status=status,
        limit=limit,
    )
    return {"data": reservations}


# ── Reservation Management ───────────────────────────────────────────────────

@router.post("/classpass/reservations")
async def create_reservation(
    body: ClassPassReservation,
    user=Depends(get_current_user),
    _=Depends(require_permission("integrations.manage_classpass_data")),
):
    try:
        reservation = await cp_svc.handle_reservation(body.model_dump())
        return {"data": reservation}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/classpass/reservations/cancel")
async def cancel_reservation(
    body: ClassPassCancellation,
    user=Depends(get_current_user),
    _=Depends(require_permission("integrations.manage_classpass_data")),
):
    reservation = await cp_svc.handle_cancellation(body.classpass_reservation_id)
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found or already cancelled")
    return {"data": reservation}


# ═══════════════════════════════════════════════════════════════════════════════
# Google My Business (Business Profile) Integration
# ═══════════════════════════════════════════════════════════════════════════════


class GmbReviewResponse(BaseModel):
    response_text: str


# ── GMB OAuth & Connection ──────────────────────────────────────────────────

@router.get("/gmb/connect")
async def gmb_connect(
    user=Depends(get_current_user),
    rbac=Depends(require_permission("integrations.connect_gmb")),
):
    """Generate the Google OAuth URL for connecting GMB."""
    org_id = await _resolve_org_id(rbac)
    # Generate CSRF token and store org_id mapping in Redis
    csrf_token = secrets.token_urlsafe(32)
    redis = await get_redis()
    if redis:
        await redis.set(f"oauth_csrf:{csrf_token}", org_id, ex=600)
    try:
        url = await gmb_svc.get_oauth_url(csrf_token)
        return {"data": {"oauth_url": url}}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/gmb/callback")
async def gmb_callback(
    code: str = Query(...),
    state: str = Query(...),
    error: Optional[str] = Query(None),
):
    """Handle the Google OAuth callback redirect.

    This is a public endpoint — Google redirects the browser here after consent.
    The `state` parameter carries a CSRF token that maps to the org_id in Redis.
    On success, redirects to the frontend integrations settings page.
    """
    if error:
        logger.warning("GMB OAuth callback error", error=error, state=state)
        return RedirectResponse(
            url=f"{settings.APP_URL}/settings/integrations?gmb_error={error}"
        )

    # Validate CSRF token and retrieve org_id from Redis
    redis = await get_redis()
    if not redis:
        return RedirectResponse(
            url=f"{settings.APP_URL}/settings/integrations?gmb_error=Service+temporarily+unavailable"
        )
    org_id = await redis.get(f"oauth_csrf:{state}")
    if not org_id:
        return RedirectResponse(
            url=f"{settings.APP_URL}/settings/integrations?gmb_error=Invalid+or+expired+OAuth+state+token"
        )
    await redis.delete(f"oauth_csrf:{state}")
    org_id = org_id.decode() if isinstance(org_id, bytes) else org_id
    try:
        await gmb_svc.handle_oauth_callback(org_id, code)
        return RedirectResponse(
            url=f"{settings.APP_URL}/settings/integrations?gmb_connected=true"
        )
    except ValueError as e:
        logger.error("GMB OAuth callback failed", org_id=org_id, error=str(e))
        return RedirectResponse(
            url=f"{settings.APP_URL}/settings/integrations?gmb_error={str(e)}"
        )


@router.get("/gmb/status")
async def gmb_status(
    user=Depends(get_current_user),
    rbac=Depends(require_permission("integrations.view_gmb")),
):
    """Check whether GMB is connected for this organization."""
    org_id = await _resolve_org_id(rbac)
    status = await gmb_svc.get_connection_status(org_id)
    return {"data": status}


@router.post("/gmb/disconnect")
async def gmb_disconnect(
    user=Depends(get_current_user),
    rbac=Depends(require_permission("integrations.disconnect_gmb")),
):
    """Disconnect GMB integration for this organization."""
    org_id = await _resolve_org_id(rbac)
    disconnected = await gmb_svc.disconnect(org_id)
    if not disconnected:
        raise HTTPException(status_code=404, detail="GMB not connected for this organization")
    return {"data": {"disconnected": True}}


# ── GMB Review Sync ─────────────────────────────────────────────────────────

@router.post("/gmb/sync-reviews")
async def gmb_sync_reviews(
    user=Depends(get_current_user),
    rbac=Depends(require_permission("integrations.sync_gmb")),
):
    """Trigger a full review sync from Google My Business."""
    org_id = await _resolve_org_id(rbac)
    try:
        result = await gmb_svc.sync_reviews(org_id)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/gmb/reviews")
async def gmb_list_reviews(
    limit: int = Query(50, le=200),
    user=Depends(get_current_user),
    rbac=Depends(require_permission("integrations.view_gmb")),
):
    """List locally synced GMB reviews."""
    org_id = await _resolve_org_id(rbac)
    reviews = await gmb_svc.get_gmb_reviews(org_id, limit=limit)
    return {"data": reviews}


@router.post("/gmb/reviews/{review_id}/respond")
async def gmb_respond_to_review(
    review_id: str,
    body: GmbReviewResponse,
    user=Depends(get_current_user),
    rbac=Depends(require_permission("integrations.respond_gmb")),
):
    """Post a response to a GMB review (pushes reply to Google)."""
    org_id = await _resolve_org_id(rbac)
    try:
        result = await gmb_svc.post_review_response(org_id, review_id, body.response_text)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── GMB Locations ───────────────────────────────────────────────────────────

@router.get("/gmb/locations")
async def gmb_list_locations(
    user=Depends(get_current_user),
    rbac=Depends(require_permission("integrations.view_gmb")),
):
    """List all GMB locations accessible via the connected account."""
    org_id = await _resolve_org_id(rbac)
    try:
        locations = await gmb_svc.list_locations(org_id)
        return {"data": locations}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/gmb/locations/{location_id}/set-primary")
async def gmb_set_primary_location(
    location_id: str,
    user=Depends(get_current_user),
    rbac=Depends(require_permission("integrations.manage_gmb")),
):
    """Set a specific GMB location as the primary for review sync."""
    org_id = await _resolve_org_id(rbac)
    try:
        result = await gmb_svc.set_primary_location(org_id, location_id)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── EMR Integration ─────────────────────────────────────────────────────────


@router.post("/emr/connect", status_code=201)
async def emr_connect(
    body: EmrConnect,
    user=Depends(get_current_user),
    rbac=Depends(require_permission("integrations.connect_emr")),
):
    """Connect to an EMR system (FHIR R4 or HL7v2)."""
    org_id = await _resolve_org_id(rbac)
    config = body.model_dump(exclude_none=True, exclude={"protocol"})
    try:
        result = await emr_service.connect(org_id, body.protocol, config)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/emr/status")
async def emr_status(
    user=Depends(get_current_user),
    rbac=Depends(require_permission("integrations.view_emr")),
):
    """Get EMR connection status."""
    org_id = await _resolve_org_id(rbac)
    return {"data": await emr_service.get_status(org_id)}


@router.post("/emr/test")
async def emr_test(
    user=Depends(get_current_user),
    rbac=Depends(require_permission("integrations.test_emr")),
):
    """Test EMR connection."""
    org_id = await _resolve_org_id(rbac)
    return {"data": await emr_service.test_connection(org_id)}


@router.post("/emr/disconnect")
async def emr_disconnect(
    user=Depends(get_current_user),
    rbac=Depends(require_permission("integrations.disconnect_emr")),
):
    """Disconnect EMR integration."""
    org_id = await _resolve_org_id(rbac)
    await emr_service.disconnect(org_id)
    return {"data": {"status": "disconnected"}}


@router.get("/emr/sync-log")
async def emr_sync_log(
    direction: Optional[str] = Query(None, regex="^(inbound|outbound)$"),
    limit: int = Query(50, le=200),
    user=Depends(get_current_user),
    rbac=Depends(require_permission("integrations.view_emr")),
):
    """View EMR sync history."""
    from app.core.tenant_context import get_tenant_context
    ctx = get_tenant_context()
    schema = ctx.schema_name if ctx else f"af_tenant_{rbac.get('org_slug', '')}"
    logs = await emr_service.get_sync_log(schema, limit=limit, direction=direction)
    return {"data": logs}


@router.post("/emr/sync-member/{member_id}")
async def emr_manual_sync_member(
    member_id: str,
    user=Depends(get_current_user),
    rbac=Depends(require_permission("integrations.sync_emr")),
):
    """Manually trigger EMR sync for a specific member."""
    from app.core.tenant_context import get_tenant_context
    ctx = get_tenant_context()
    schema = ctx.schema_name if ctx else f"af_tenant_{rbac.get('org_slug', '')}"
    result = await emr_service.sync_member_to_emr(schema, member_id)
    if result:
        return {"data": {"emr_patient_id": result, "status": "synced"}}
    raise HTTPException(status_code=400, detail="Sync failed or EMR not enabled")


# ── Helpers ─────────────────────────────────────────────────────────────────

async def _resolve_org_id(rbac: dict) -> str:
    """Resolve the organization ID from the RBAC context.

    The RBAC dependency returns org_slug; we need the UUID org_id for service calls.
    """
    org_slug = rbac.get("org_slug")
    if not org_slug:
        raise HTTPException(status_code=400, detail="No organization context")

    from app.core.tenant_context import get_tenant_context
    ctx = get_tenant_context()
    if ctx:
        return ctx.organization_id

    # Fallback: resolve from DB
    from app.db.session import get_global_db
    async with get_global_db() as db:
        row = await db.fetchrow(
            "SELECT id FROM af_global.organizations WHERE slug = $1",
            org_slug,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Organization not found")
    return str(row["id"])
