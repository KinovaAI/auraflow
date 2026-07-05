"""AuraFlow — Onboarding Checklist Endpoints

Provides checklist retrieval, manual step completion, and auto-detection
of completed steps by inspecting actual tenant data.
"""
from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.dependencies.auth import get_current_user
from app.api.v1.dependencies.rbac import require_permission
from app.services.onboarding.onboarding_service import OnboardingService

router = APIRouter()
svc = OnboardingService()


@router.get("/checklist")
async def get_checklist(
    user=Depends(get_current_user),
):
    """Get the full onboarding checklist with completion status."""
    steps = await svc.get_checklist()
    total = len(steps)
    completed = sum(1 for s in steps if s.get("is_completed"))
    return {
        "data": steps,
        "progress": {
            "total": total,
            "completed": completed,
            "percent": round((completed / total * 100) if total else 0),
        },
    }


@router.post("/checklist/{step_key}/complete")
async def complete_step(
    step_key: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("settings.manage_onboarding")),
):
    """Mark an onboarding step as completed."""
    step = await svc.complete_step(
        step_key=step_key,
        completed_by=user.get("sub"),
    )
    if not step:
        raise HTTPException(status_code=404, detail="Onboarding step not found")
    return {"data": step}


@router.post("/checklist/detect")
async def auto_detect_completions(
    _=Depends(require_permission("settings.manage_onboarding")),
):
    """Auto-detect which onboarding steps are already completed
    by inspecting actual data in the tenant schema."""
    newly_completed = await svc.auto_detect_completions()
    steps = await svc.get_checklist()
    total = len(steps)
    completed = sum(1 for s in steps if s.get("is_completed"))
    return {
        "data": steps,
        "newly_completed": newly_completed,
        "progress": {
            "total": total,
            "completed": completed,
            "percent": round((completed / total * 100) if total else 0),
        },
    }
