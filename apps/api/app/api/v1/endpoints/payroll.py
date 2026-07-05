"""AuraFlow — Instructor Payroll / Compensation Endpoints

Payroll report, mark-as-paid, and history for instructor compensation.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.v1.dependencies.auth import get_current_user
from app.api.v1.dependencies.rbac import require_permission
from app.services.scheduling.payroll_service import PayrollService

router = APIRouter()

svc = PayrollService()


# ── Schemas ──────────────────────────────────────────────────────────────────

class MarkPaidRequest(BaseModel):
    instructor_id: str
    month: str  # YYYY-MM


class GuestWorkshopBreakdown(BaseModel):
    title: Optional[str] = None
    type: Optional[str] = None
    revenue_cents: int
    pay_cents: int


class PayrollLineResponse(BaseModel):
    instructor_id: str
    instructor_name: str
    tax_classification: str
    pay_type: str
    pay_rate_cents: int
    group_classes_count: int
    group_revenue_cents: int
    group_class_pay_cents: int
    private_sessions_count: int
    private_session_revenue_cents: int
    private_session_pay_cents: int
    workshops_count: int
    workshop_revenue_cents: int
    workshop_pay_cents: int
    training_pay_cents: int
    total_owed_cents: int
    paid_at: Optional[str] = None
    # Guest-instructor extras — present only when is_guest_instructor=True.
    # Surface what Kim (and other 1099 guest instructors) is owed for the
    # month, broken down by workshop. Mark-paid for guests is handled in
    # the 1099 report / accounting tooling, not via /payroll/mark-paid
    # (the FK there points at the instructors table).
    is_guest_instructor: bool = False
    guest_share_percent: Optional[int] = None
    guest_tax_id_on_file: Optional[bool] = None
    guest_workshops: Optional[list[GuestWorkshopBreakdown]] = None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/report", response_model=list[PayrollLineResponse])
async def get_payroll_report(
    month: str = Query(..., description="YYYY-MM"),
    instructor_id: Optional[str] = Query(None),
    rbac: dict = Depends(require_permission("payroll.view_report")),
):
    """Get payroll report for a month, optionally filtered to one instructor."""
    report = await svc.get_payroll_report(month, instructor_id)
    return report


@router.post("/mark-paid")
async def mark_paid(
    request: MarkPaidRequest,
    rbac: dict = Depends(require_permission("payroll.mark_paid")),
):
    """Mark an instructor as paid for a given period."""
    user_id = rbac.get("user_id", "unknown")
    result = await svc.mark_paid(request.instructor_id, request.month, user_id)
    return result


@router.delete("/runs/{run_id}")
async def delete_payroll_run(
    run_id: str,
    rbac: dict = Depends(require_permission("payroll.delete_run")),
):
    """Delete a draft payroll run (cannot delete finalized runs)."""
    from app.db.session import get_tenant_db
    async with get_tenant_db() as db:
        row = await db.fetchrow("SELECT status FROM payroll_runs WHERE id = $1", run_id)
        if not row:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Payroll run not found")
        if row["status"] not in ("draft", "compiled"):
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Can only delete draft/compiled runs")
        await db.execute("DELETE FROM payroll_line_items WHERE payroll_run_id = $1", run_id)
        await db.execute("DELETE FROM payroll_runs WHERE id = $1", run_id)
    return {"deleted": True}


@router.get("/history")
async def get_payroll_history(
    instructor_id: Optional[str] = Query(None),
    limit: int = Query(12),
    rbac: dict = Depends(require_permission("payroll.view_history")),
):
    """Get past payroll records."""
    records = await svc.get_payroll_history(instructor_id, limit)
    # Serialize dates
    for r in records:
        for k in ("period_start", "period_end", "paid_at"):
            if r.get(k) is not None:
                r[k] = str(r[k])
    return records
