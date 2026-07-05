"""AuraFlow — GDPR & CCPA Compliance Endpoints

Provides member-facing endpoints for GDPR data deletion requests,
data portability (export), and CCPA opt-out.
All endpoints are portal-accessible (require_permission gated).
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from app.api.v1.dependencies.rbac import require_permission
from app.services.members.data_deletion_service import DataDeletionService
from app.db.session import get_tenant_db

router = APIRouter()
svc = DataDeletionService()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fmt(dt):
    if dt and hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt) if dt else None


async def _get_member_id(user_id: str) -> str:
    """Resolve member_id from user_id in the tenant schema."""
    async with get_tenant_db() as db:
        row = await db.fetchrow(
            "SELECT id FROM members WHERE user_id = $1", user_id
        )
    if not row:
        raise HTTPException(status_code=404, detail="Member profile not found")
    return str(row["id"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class DeletionRequestResponse(BaseModel):
    id: str
    member_id: str
    status: str
    requested_at: Optional[str] = None
    scheduled_deletion_at: Optional[str] = None
    cancelled_at: Optional[str] = None
    completed_at: Optional[str] = None
    message: Optional[str] = None


class OptOutRequest(BaseModel):
    marketing_opt_out: bool = True


# ── Deletion Request ────────────────────────────────────────────────────────

@router.post("/deletion-request", response_model=DeletionRequestResponse, status_code=201)
async def request_deletion(
    rbac: dict = Depends(require_permission("privacy.request_deletion")),
):
    """Request deletion of own member data (GDPR right to be forgotten).
    Creates a request with a 30-day grace period before execution."""
    member_id = await _get_member_id(rbac["user_id"])
    result = await svc.request_deletion(member_id)
    return DeletionRequestResponse(
        id=str(result["id"]),
        member_id=str(result["member_id"]),
        status=result["status"],
        requested_at=_fmt(result.get("requested_at")),
        scheduled_deletion_at=_fmt(result.get("scheduled_deletion_at")),
        cancelled_at=_fmt(result.get("cancelled_at")),
        completed_at=_fmt(result.get("completed_at")),
        message=result.get("message"),
    )


@router.get("/deletion-request/status", response_model=Optional[DeletionRequestResponse])
async def get_deletion_status(
    rbac: dict = Depends(require_permission("privacy.view_deletion_status")),
):
    """Check status of own pending deletion request."""
    member_id = await _get_member_id(rbac["user_id"])
    result = await svc.get_deletion_request_status(member_id)
    if not result:
        return None
    return DeletionRequestResponse(
        id=str(result["id"]),
        member_id=str(result["member_id"]),
        status=result["status"],
        requested_at=_fmt(result.get("requested_at")),
        scheduled_deletion_at=_fmt(result.get("scheduled_deletion_at")),
        cancelled_at=_fmt(result.get("cancelled_at")),
        completed_at=_fmt(result.get("completed_at")),
    )


@router.post("/deletion-request/cancel", response_model=DeletionRequestResponse)
async def cancel_deletion(
    rbac: dict = Depends(require_permission("privacy.cancel_deletion")),
):
    """Cancel own pending deletion request."""
    member_id = await _get_member_id(rbac["user_id"])

    # Find the pending request
    pending = await svc.get_deletion_request_status(member_id)
    if not pending or pending["status"] != "pending":
        raise HTTPException(
            status_code=404,
            detail="No pending deletion request found",
        )

    result = await svc.cancel_deletion_request(str(pending["id"]))
    if not result:
        raise HTTPException(
            status_code=400,
            detail="Could not cancel deletion request",
        )

    return DeletionRequestResponse(
        id=str(result["id"]),
        member_id=str(result["member_id"]),
        status=result["status"],
        requested_at=_fmt(result.get("requested_at")),
        scheduled_deletion_at=_fmt(result.get("scheduled_deletion_at")),
        cancelled_at=_fmt(result.get("cancelled_at")),
        completed_at=_fmt(result.get("completed_at")),
    )


# ── Data Export ──────────────────────────────────────────────────────────────

@router.post("/data-export")
async def export_data(
    rbac: dict = Depends(require_permission("privacy.export_data")),
):
    """Export all own data as JSON (GDPR data portability, Article 20)."""
    member_id = await _get_member_id(rbac["user_id"])
    data = await svc.export_member_data(member_id)
    if not data:
        raise HTTPException(status_code=404, detail="No data found")
    return {"data": data}


@router.get("/export/{member_id}")
async def staff_export_member_data(
    member_id: str,
    rbac: dict = Depends(require_permission("privacy.export_member")),
):
    """Staff-initiated data export for a member. Used to fulfil HIPAA
    right-to-access requests (§164.524) and GDPR Article 15 subject
    access requests that arrive via email or phone. Returns the full
    dataset as a downloadable JSON file.
    """
    from fastapi.responses import JSONResponse
    import json as _json

    data = await svc.export_member_data(member_id)
    if not data:
        raise HTTPException(status_code=404, detail="Member not found")

    payload = _json.dumps(data, indent=2, default=str)
    filename = f"member-{member_id}-export-{datetime.utcnow().strftime('%Y%m%d')}.json"
    return Response(
        content=payload,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # Audit header so NGINX access logs capture who did the export
            "X-AuraFlow-Export-By": rbac.get("user_id", "unknown"),
        },
    )


# ── CCPA Opt-Out ─────────────────────────────────────────────────────────────

@router.post("/opt-out")
async def ccpa_opt_out(
    body: OptOutRequest,
    rbac: dict = Depends(require_permission("privacy.manage_preferences")),
):
    """CCPA 'Do Not Sell My Personal Information' opt-out.
    Sets marketing_opt_out on the member profile."""
    member_id = await _get_member_id(rbac["user_id"])

    async with get_tenant_db() as db:
        await db.execute(
            """
            UPDATE members
            SET email_opt_in = NOT $2,
                sms_opt_in = NOT $2,
                updated_at = NOW()
            WHERE id = $1
            """,
            member_id, body.marketing_opt_out,
        )

    return {
        "message": "Marketing opt-out preference updated",
        "marketing_opt_out": body.marketing_opt_out,
    }
