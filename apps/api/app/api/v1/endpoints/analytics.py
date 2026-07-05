"""AuraFlow — Analytics & Reporting Endpoints

Revenue, attendance, membership health, utilization, and instructor reports.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query

from app.api.v1.dependencies.rbac import require_permission
from app.services.analytics.report_service import ReportService
from app.services.ai.revenue_forecast_service import RevenueForecastService

router = APIRouter()
report_svc = ReportService()
revenue_forecast_svc = RevenueForecastService()


def _parse_range(days: int) -> tuple[datetime, datetime]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    return start, end


# ── Dashboard KPIs ───────────────────────────────────────────────────────────

@router.get("/dashboard")
async def dashboard_kpis(
    days: int = Query(30, ge=1, le=365),
    rbac=Depends(require_permission("analytics.view_dashboard")),
):
    """Key performance indicators for the main dashboard."""
    return {"data": await report_svc.dashboard_kpis(days)}


# ── Revenue ──────────────────────────────────────────────────────────────────

@router.get("/revenue/over-time")
async def revenue_over_time(
    days: int = Query(30, ge=1, le=365),
    group_by: str = Query("day"),
    rbac=Depends(require_permission("analytics.view_revenue")),
):
    if group_by not in ("day", "week", "month"):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="group_by must be 'day', 'week', or 'month'")
    start, end = _parse_range(days)
    return {"data": await report_svc.revenue_over_time(start, end, group_by)}


@router.get("/revenue/by-type")
async def revenue_by_type(
    days: int = Query(30, ge=1, le=365),
    rbac=Depends(require_permission("analytics.view_revenue")),
):
    start, end = _parse_range(days)
    return {"data": await report_svc.revenue_by_type(start, end)}


@router.get("/revenue/by-instructor")
async def revenue_by_instructor(
    days: int = Query(30, ge=1, le=365),
    rbac=Depends(require_permission("analytics.view_revenue")),
):
    """Revenue attributed to each instructor with pay and profit estimates."""
    start, end = _parse_range(days)
    return {"data": await report_svc.revenue_by_instructor(start, end)}


# ── Attendance ───────────────────────────────────────────────────────────────

@router.get("/attendance/over-time")
async def attendance_over_time(
    days: int = Query(30, ge=1, le=365),
    group_by: str = Query("day"),
    rbac=Depends(require_permission("analytics.view_attendance")),
):
    start, end = _parse_range(days)
    return {"data": await report_svc.attendance_over_time(start, end, group_by)}


@router.get("/attendance/by-class-type")
async def attendance_by_class_type(
    days: int = Query(30, ge=1, le=365),
    rbac=Depends(require_permission("analytics.view_attendance")),
):
    start, end = _parse_range(days)
    return {"data": await report_svc.attendance_by_class_type(start, end)}


@router.get("/attendance/heatmap")
async def attendance_heatmap(
    days: int = Query(30, ge=1, le=365),
    rbac=Depends(require_permission("analytics.view_attendance")),
):
    """Attendance heatmap by day-of-week and hour-of-day."""
    start, end = _parse_range(days)
    return {"data": await report_svc.attendance_heatmap(start, end)}


# ── Memberships ──────────────────────────────────────────────────────────────

@router.get("/memberships/summary")
async def membership_summary(rbac=Depends(require_permission("analytics.view_memberships"))):
    return {"data": await report_svc.membership_summary()}


@router.get("/memberships/by-type")
async def membership_by_type(rbac=Depends(require_permission("analytics.view_memberships"))):
    return {"data": await report_svc.membership_by_type()}


@router.get("/memberships/churn")
async def membership_churn(
    days: int = Query(30, ge=1, le=365),
    rbac=Depends(require_permission("analytics.view_memberships")),
):
    return {"data": await report_svc.churn_rate(days)}


@router.get("/memberships/top-selling")
async def top_selling_memberships(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=50),
    rbac=Depends(require_permission("analytics.view_memberships")),
):
    """Most sold membership/pricing options."""
    start, end = _parse_range(days)
    return {"data": await report_svc.top_selling_memberships(start, end, limit)}


# ── Studio Health ────────────────────────────────────────────────────────────

@router.get("/studio-health")
async def studio_health(
    days: int = Query(30, ge=1, le=365),
    rbac=Depends(require_permission("analytics.view_dashboard")),
):
    """Comprehensive studio health metrics."""
    start, end = _parse_range(days)
    return {"data": await report_svc.studio_health(start, end)}


@router.get("/members/top-cancellers")
async def top_cancellers(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=50),
    rbac=Depends(require_permission("analytics.view_members")),
):
    """Members with the most cancellations/no-shows."""
    start, end = _parse_range(days)
    return {"data": await report_svc.top_cancellers(start, end, limit)}


@router.get("/members/new-over-time")
async def new_members_over_time(
    days: int = Query(30, ge=1, le=365),
    group_by: str = Query("day"),
    rbac=Depends(require_permission("analytics.view_members")),
):
    """New member signups over time."""
    if group_by not in ("day", "week", "month"):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="group_by must be 'day', 'week', or 'month'")
    start, end = _parse_range(days)
    return {"data": await report_svc.new_members_over_time(start, end, group_by)}


# ── Utilization ──────────────────────────────────────────────────────────────

@router.get("/utilization/rooms")
async def room_utilization(
    days: int = Query(30, ge=1, le=365),
    rbac=Depends(require_permission("analytics.view_rooms")),
):
    start, end = _parse_range(days)
    return {"data": await report_svc.room_utilization(start, end)}


# ── Instructors ──────────────────────────────────────────────────────────────

@router.get("/instructors")
async def instructor_summary(
    days: int = Query(30, ge=1, le=365),
    rbac=Depends(require_permission("analytics.view_instructors")),
):
    start, end = _parse_range(days)
    return {"data": await report_svc.instructor_summary(start, end)}


# ── Payout Report ────────────────────────────────────────────────────────────

@router.get("/payout-report")
async def payout_report(
    days: int = Query(30, ge=1, le=365),
    rbac=Depends(require_permission("analytics.view_payroll")),
):
    """Instructor payout breakdown with totals."""
    start, end = _parse_range(days)
    return {"data": await report_svc.payout_report(start, end)}


# ── Guest Instructor 1099 Report ─────────────────────────────────────────────


@router.get("/guest-instructor-1099")
async def guest_instructor_1099_report(
    year: int = Query(..., ge=2020, le=2099),
    rbac=Depends(require_permission("analytics.view_payroll")),
):
    """Per-guest workshop revenue + their share for the calendar year.

    Returns the data needed to issue 1099-NEC forms: guest name,
    address, decrypted tax ID, total payout, and a `needs_1099` flag
    set when a guest's annual payout crossed the $600 IRS threshold.
    """
    return {"data": await report_svc.guest_instructor_1099_report(year)}


@router.get("/guest-instructor-1099/csv")
async def guest_instructor_1099_csv(
    year: int = Query(..., ge=2020, le=2099),
    rbac=Depends(require_permission("analytics.export_payroll")),
):
    """Same data as /guest-instructor-1099 but as a CSV download —
    drops straight into accountant workflows. Each row is one guest
    with everything needed for a 1099-NEC."""
    import csv
    import io

    from fastapi.responses import StreamingResponse

    report = await report_svc.guest_instructor_1099_report(year)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "name", "tax_id", "address_line1", "city", "state", "postal_code",
        "email", "phone",
        "workshops_taught", "attendees_paid",
        "gross_revenue_$", "guest_payout_$", "studio_revenue_$",
        "revenue_share_pct", "needs_1099",
    ])
    for g in report["guests"]:
        w.writerow([
            g.get("name") or "",
            g.get("tax_id") or "",
            g.get("address_line1") or "",
            g.get("city") or "",
            g.get("state") or "",
            g.get("postal_code") or "",
            g.get("email") or "",
            g.get("phone") or "",
            g.get("workshops_taught") or 0,
            g.get("attendees_paid") or 0,
            f"{(g.get('gross_revenue_cents') or 0) / 100:.2f}",
            f"{(g.get('guest_payout_cents') or 0) / 100:.2f}",
            f"{(g.get('studio_revenue_cents') or 0) / 100:.2f}",
            g.get("revenue_share_percent_to_guest") or 60,
            "yes" if g.get("needs_1099") else "no",
        ])

    buf.seek(0)
    headers = {
        "Content-Disposition": f'attachment; filename="guest-instructor-1099-{year}.csv"',
    }
    return StreamingResponse(iter([buf.read()]), media_type="text/csv", headers=headers)


# ── AI Revenue Forecast ──────────────────────────────────────────────────────

@router.get("/revenue-forecast")
async def revenue_forecast(
    days: int = Query(90, ge=30, le=90),
    rbac=Depends(require_permission("analytics.view_revenue")),
):
    """AI-powered revenue forecast with 30/60/90-day projections.

    Analyzes 180 days of historical revenue, active memberships,
    acquisition rates, and churn to generate projections with a
    Claude-powered natural language summary.
    """
    from fastapi import HTTPException

    try:
        result = await revenue_forecast_svc.forecast(days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Revenue forecast failed: {str(e)}")
    return {"data": result}
