"""AuraFlow — Time Clock & Payroll Endpoints

Clock in/out, timesheets, approval, and payroll compilation.
"""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.v1.dependencies.auth import get_current_user
from app.api.v1.dependencies.rbac import require_permission
from app.services.scheduling.time_clock_service import TimeClockService

router = APIRouter()
svc = TimeClockService()


# ── Schemas ──────────────────────────────────────────────────────────────────

class ClockInRequest(BaseModel):
    instructor_id: str
    shift_type: str = "regular"
    notes: Optional[str] = None


class ClockOutRequest(BaseModel):
    instructor_id: str
    break_minutes: int = 0
    notes: Optional[str] = None


class ApproveRequest(BaseModel):
    pass


class RejectRequest(BaseModel):
    reason: Optional[str] = None


class CompilePayrollRequest(BaseModel):
    period_start: date
    period_end: date


# ── Clock Operations ────────────────────────────────────────────────────────

@router.post("/clock-in", status_code=201)
async def clock_in(
    body: ClockInRequest,
    user=Depends(get_current_user),
    rbac=Depends(require_permission("payroll.clock_in")),
):
    """Clock in an instructor. Instructors can only clock themselves in."""
    if rbac.get("org_role") == "instructor":
        # Instructors can only clock in/out for their own instructor record
        from app.db.session import get_tenant_db
        async with get_tenant_db() as db:
            own = await db.fetchrow(
                "SELECT id FROM instructors WHERE user_id = $1", rbac["user_id"]
            )
        if not own or str(own["id"]) != body.instructor_id:
            raise HTTPException(status_code=403, detail="Instructors can only clock in for themselves")
    try:
        entry = await svc.clock_in(body.instructor_id, body.shift_type, body.notes)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"data": entry}


@router.post("/clock-out")
async def clock_out(
    body: ClockOutRequest,
    user=Depends(get_current_user),
    rbac=Depends(require_permission("payroll.clock_out")),
):
    """Clock out an instructor. Instructors can only clock themselves out."""
    if rbac.get("org_role") == "instructor":
        from app.db.session import get_tenant_db
        async with get_tenant_db() as db:
            own = await db.fetchrow(
                "SELECT id FROM instructors WHERE user_id = $1", rbac["user_id"]
            )
        if not own or str(own["id"]) != body.instructor_id:
            raise HTTPException(status_code=403, detail="Instructors can only clock out for themselves")
    try:
        entry = await svc.clock_out(body.instructor_id, body.break_minutes, body.notes)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"data": entry}


@router.get("/status/{instructor_id}")
async def clock_status(
    instructor_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("payroll.view_clock_status")),
):
    """Get current clock-in status for an instructor."""
    status = await svc.get_status(instructor_id)
    return {"data": status}


# ── Timesheets ───────────────────────────────────────────────────────────────

@router.get("/my-timesheet")
async def my_timesheet(
    instructor_id: str = Query(...),
    start: date = Query(default=None),
    end: date = Query(default=None),
    user=Depends(get_current_user),
    _=Depends(require_permission("payroll.view_own_timesheet")),
):
    """Get timesheet for a specific instructor."""
    if not start:
        start = date.today() - timedelta(days=7)
    if not end:
        end = date.today()
    entries = await svc.get_timesheet(instructor_id, start, end)
    return {"data": entries}


@router.get("/timesheets")
async def all_timesheets(
    start: date = Query(default=None),
    end: date = Query(default=None),
    user=Depends(get_current_user),
    _=Depends(require_permission("payroll.view_timesheets")),
):
    """Get all timesheets (admin view)."""
    if not start:
        start = date.today() - timedelta(days=7)
    if not end:
        end = date.today()
    entries = await svc.get_all_timesheets(start, end)
    return {"data": entries}


# ── Approval ─────────────────────────────────────────────────────────────────

@router.put("/entries/{entry_id}/approve")
async def approve_entry(
    entry_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("payroll.approve_entries")),
):
    """Approve a time entry."""
    entry = await svc.approve_entry(entry_id, user["sub"])
    if not entry:
        raise HTTPException(status_code=404, detail="Time entry not found")
    return {"data": entry}


@router.put("/entries/{entry_id}/reject")
async def reject_entry(
    entry_id: str,
    body: RejectRequest,
    user=Depends(get_current_user),
    _=Depends(require_permission("payroll.reject_entries")),
):
    """Reject a time entry."""
    entry = await svc.reject_entry(entry_id, user["sub"], body.reason)
    if not entry:
        raise HTTPException(status_code=404, detail="Time entry not found")
    return {"data": entry}


# ── Payroll ──────────────────────────────────────────────────────────────────

@router.post("/payroll/compile", status_code=201)
async def compile_payroll(
    body: CompilePayrollRequest,
    user=Depends(get_current_user),
    _=Depends(require_permission("payroll.compile")),
):
    """Compile payroll for a date range."""
    try:
        run = await svc.compile_payroll(body.period_start, body.period_end, user["sub"])
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": run}


@router.get("/payroll")
async def list_payroll_runs(
    user=Depends(get_current_user),
    _=Depends(require_permission("payroll.view_runs")),
):
    """List all payroll runs."""
    runs = await svc.list_payroll_runs()
    return {"data": runs}


@router.get("/payroll/{run_id}")
async def get_payroll_run(
    run_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("payroll.view_runs")),
):
    """Get payroll run with line items."""
    run = await svc.get_payroll_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Payroll run not found")
    return {"data": run}


@router.put("/payroll/{run_id}/finalize")
async def finalize_payroll(
    run_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("payroll.finalize")),
):
    """Finalize a payroll run."""
    run = await svc.finalize_payroll(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Payroll run not found")
    return {"data": run}
