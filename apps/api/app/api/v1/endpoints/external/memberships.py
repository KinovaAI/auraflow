"""AuraFlow — External Memberships Endpoints

API-key-authenticated membership type listing, assignment, cancel, and freeze.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.v1.dependencies.api_key_auth import get_api_key_context, require_api_scope
from app.services.memberships.membership_service import MembershipService
from app.db.session import get_tenant_db
from app.services.external.csv_export import export_csv

router = APIRouter()
_svc = MembershipService()


# ── Schemas ──────────────────────────────────────────────────────────────────

class MemberMembershipAssign(BaseModel):
    member_id: str
    membership_type_id: str
    starts_at: Optional[str] = None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fmt(dt):
    if dt and hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt) if dt else None


def _type_dict(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "description": row.get("description"),
        "type": row.get("type"),
        "access_scope": row.get("access_scope"),
        "class_count": row.get("class_count"),
        "price_cents": row.get("price_cents"),
        "billing_period": row.get("billing_period"),
        "duration_days": row.get("duration_days"),
        "auto_renew": row.get("auto_renew"),
        "is_public": row.get("is_public"),
    }


def _mm_dict(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "member_id": str(row["member_id"]),
        "membership_type_id": str(row["membership_type_id"]),
        "type_name": row.get("type_name"),
        "membership_type": row.get("membership_type"),
        "status": row.get("status"),
        "starts_at": _fmt(row.get("starts_at")),
        "ends_at": _fmt(row.get("ends_at")),
        "classes_remaining": row.get("classes_remaining"),
        "frozen_at": _fmt(row.get("frozen_at")),
        "frozen_until": _fmt(row.get("frozen_until")),
        "cancelled_at": _fmt(row.get("cancelled_at")),
        "cancellation_reason": row.get("cancellation_reason"),
        "created_at": _fmt(row.get("created_at")),
        # Joined member info (from list_all_memberships)
        "member_first_name": row.get("member_first_name"),
        "member_last_name": row.get("member_last_name"),
    }


async def _fire_webhook(event: str, payload: dict) -> None:
    try:
        from app.services.webhooks.webhook_delivery_service import WebhookDeliveryService
        await WebhookDeliveryService().fire_event(event, payload)
    except Exception:
        pass


# ── CSV Export ───────────────────────────────────────────────────────────────

_MM_CSV_COLS = [
    ("id", "ID"),
    ("member_id", "Member ID"),
    ("member_first_name", "First Name"),
    ("member_last_name", "Last Name"),
    ("type_name", "Membership Type"),
    ("status", "Status"),
    ("starts_at", "Starts At"),
    ("ends_at", "Ends At"),
    ("classes_remaining", "Classes Remaining"),
    ("created_at", "Created At"),
]


@router.get(
    "/memberships/export.csv",
    dependencies=[Depends(require_api_scope("memberships:read"))],
    summary="Export memberships as CSV",
)
async def export_memberships_csv(
    ctx: dict = Depends(get_api_key_context),
):
    rows = await _svc.list_all_memberships(active_only=False, limit=10000)
    return export_csv([_mm_dict(r) for r in rows], _MM_CSV_COLS, "memberships.csv")


# ── Membership Types ─────────────────────────────────────────────────────────

@router.get(
    "/membership-types",
    dependencies=[Depends(require_api_scope("memberships:read"))],
    summary="List available membership types",
)
async def list_membership_types(
    ctx: dict = Depends(get_api_key_context),
):
    async with get_tenant_db() as db:
        rows = await db.fetch(
            "SELECT * FROM membership_types WHERE is_active = TRUE AND is_public = TRUE ORDER BY sort_order, name"
        )
    return [_type_dict(dict(r)) for r in rows]


# ── Member Memberships ──────────────────────────────────────────────────────

@router.get(
    "/member-memberships",
    dependencies=[Depends(require_api_scope("memberships:read"))],
    summary="List member memberships",
)
async def list_member_memberships(
    ctx: dict = Depends(get_api_key_context),
    member_id: Optional[str] = Query(None),
):
    if member_id:
        rows = await _svc.get_member_memberships(member_id, active_only=False)
    else:
        rows = await _svc.list_all_memberships(active_only=False)
    return [_mm_dict(r) for r in rows]


@router.post(
    "/member-memberships",
    dependencies=[Depends(require_api_scope("memberships:write"))],
    status_code=201,
    summary="Assign membership to a member",
)
async def assign_membership(
    body: MemberMembershipAssign,
    ctx: dict = Depends(get_api_key_context),
):
    try:
        row = await _svc.assign_membership(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    result = _mm_dict(row)
    await _fire_webhook("membership.assigned", result)
    return result


@router.put(
    "/member-memberships/{membership_id}/cancel",
    dependencies=[Depends(require_api_scope("memberships:write"))],
    summary="Cancel a membership",
)
async def cancel_membership(
    membership_id: str,
    ctx: dict = Depends(get_api_key_context),
):
    row = await _svc.cancel_membership(membership_id, reason="Cancelled via API")
    if not row:
        raise HTTPException(status_code=404, detail="Membership not found or already cancelled")
    result = _mm_dict(row)
    await _fire_webhook("membership.cancelled", result)
    return result


@router.put(
    "/member-memberships/{membership_id}/freeze",
    dependencies=[Depends(require_api_scope("memberships:write"))],
    summary="Freeze a membership",
)
async def freeze_membership(
    membership_id: str,
    ctx: dict = Depends(get_api_key_context),
):
    try:
        row = await _svc.freeze_membership(membership_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not row:
        raise HTTPException(status_code=404, detail="Membership not found")
    result = _mm_dict(row)
    await _fire_webhook("membership.frozen", result)
    return result
