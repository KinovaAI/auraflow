"""AuraFlow — Kiosk Device Admin Endpoints

Studio owner registers an iPad as a kiosk device; the server stores
the device + fingerprint and sets an httponly cookie on the iPad's
browser. Once registered, the iPad can only reach the in-house
check-in kiosk — enforced server-side by KioskDeviceMiddleware.

`POST /api/v1/kiosk-devices/register` MUST be called from the iPad
itself (in a non-kiosk Safari tab the owner opens once for setup),
because the (ip, user_agent) fingerprint is captured from the request
to enable cookie-less rebind later.

`GET /api/v1/kiosk-devices` lists all kiosk devices for the org.
`DELETE /api/v1/kiosk-devices/{id}` revokes a device (e.g. retiring
the iPad). Owner-only; instructors and front_desk cannot revoke.

Note: the middleware blocks kiosk devices from hitting these endpoints
themselves — register/list/revoke must come from a non-kiosk browser
(the owner's laptop), with the EXCEPTION of the initial register
call which the owner does once from the iPad before the lock kicks
in. To support that, the register endpoint is allow-listed in the
middleware? No — the device isn't registered yet, so no row exists,
so the middleware doesn't see it as a kiosk. The first register call
goes through cleanly.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.api.v1.dependencies.auth import get_current_user
from app.api.v1.dependencies.rbac import require_permission
from app.core.tenant_context import get_organization_id
from app.services.kiosk.kiosk_device_service import kiosk_device_service

router = APIRouter()


_KIOSK_COOKIE_NAME = "auraflow_kiosk_device"
_KIOSK_COOKIE_MAX_AGE = 10 * 365 * 24 * 3600  # 10 years


class KioskDeviceRegisterRequest(BaseModel):
    label: str = Field(..., min_length=1, max_length=120)


class KioskDeviceResponse(BaseModel):
    id: str
    label: str
    is_active: bool
    registered_at: str
    last_seen_at: Optional[str] = None
    revoked_at: Optional[str] = None


def _to_response(row: dict) -> KioskDeviceResponse:
    def _iso(v):
        return v.isoformat() if v is not None else None
    return KioskDeviceResponse(
        id=str(row["id"]),
        label=row["label"],
        is_active=row["is_active"],
        registered_at=_iso(row["registered_at"]),
        last_seen_at=_iso(row.get("last_seen_at")),
        revoked_at=_iso(row.get("revoked_at")),
    )


def _client_ip(request: Request) -> Optional[str]:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


@router.post(
    "/register",
    summary="Register the current device as a studio kiosk",
)
async def register_kiosk_device(
    body: KioskDeviceRegisterRequest,
    request: Request,
    response: Response,
    user=Depends(get_current_user),
    rbac: dict = Depends(require_permission("settings.manage_features")),
):
    """Register THIS device (the one making the request) as a kiosk.

    The owner taps "Register this iPad" while signed in on the iPad in
    Safari. We capture (ip, user_agent), store a hashed fingerprint,
    issue an httponly cookie, and from that point on the middleware
    locks the device to the check-in kiosk surface.

    Returns the device row (NOT the raw token — that lives only in
    the cookie). The next dashboard request the iPad makes will hit
    the middleware and get redirected.
    """
    org_id = get_organization_id()
    ip = _client_ip(request)
    ua = request.headers.get("user-agent")

    row = await kiosk_device_service.register(
        organization_id=org_id,
        label=body.label,
        ip_address=ip,
        user_agent=ua,
        registered_by_user_id=rbac["user_id"],
    )

    # Set the cookie on the iPad. HttpOnly so JS / clear-cookies via
    # JS can't reach it; Secure so it only travels over HTTPS.
    response.set_cookie(
        key=_KIOSK_COOKIE_NAME,
        value=row["device_token"],
        max_age=_KIOSK_COOKIE_MAX_AGE,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )

    return {
        "data": {
            **_to_response(row).model_dump(),
            "message": (
                "This device is now registered as a kiosk. Reload the "
                "page and the dashboard will redirect to /kiosk-locked. "
                "Clearing cookies will NOT escape the lock — the server "
                "will re-issue the cookie automatically."
            ),
        }
    }


@router.get(
    "",
    summary="List kiosk devices for the current org",
)
async def list_kiosk_devices(
    rbac: dict = Depends(require_permission("settings.manage_features")),
):
    org_id = get_organization_id()
    rows = await kiosk_device_service.list_for_org(org_id)
    return {"data": [_to_response(r).model_dump() for r in rows]}


@router.delete(
    "/{device_id}",
    summary="Revoke a kiosk device registration",
    status_code=204,
)
async def revoke_kiosk_device(
    device_id: str,
    rbac: dict = Depends(require_permission("settings.manage_features")),
):
    org_id = get_organization_id()
    changed = await kiosk_device_service.revoke(
        device_id=device_id,
        organization_id=org_id,
        revoked_by_user_id=rbac["user_id"],
    )
    if not changed:
        raise HTTPException(status_code=404, detail="Kiosk device not found")
