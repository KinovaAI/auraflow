"""AuraFlow — Hiring / Applicant-Tracking (internal staff endpoints)

Staff-facing review pipeline, the hire action, and the restricted W-4 viewer.
Gated by the hiring.* permission family. Tenant context is set by middleware
from the staff JWT.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.v1.dependencies.rbac import require_permission
from app.core.logging import logger
from app.db.session import get_global_db
from app.services.hiring import hiring_service, employer_service, onboarding_service, de34_service

router = APIRouter()


async def _org_id(org_slug: str) -> str:
    async with get_global_db() as db:
        row = await db.fetchrow(
            "SELECT id FROM af_global.organizations WHERE slug = $1", org_slug,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Organization not found")
    return str(row["id"])


# ── Schemas ────────────────────────────────────────────────────────────────

class UpdateApplicationRequest(BaseModel):
    status: Optional[str] = None
    rating: Optional[int] = Field(None, ge=0, le=5)
    assigned_reviewer_id: Optional[str] = None
    rejection_reason: Optional[str] = None


class NoteRequest(BaseModel):
    note: str = Field(..., min_length=1, max_length=4000)


class EmployerProfileRequest(BaseModel):
    legal_name: Optional[str] = None
    dba_name: Optional[str] = None
    ein: Optional[str] = None
    edd_account_number: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = Field(None, max_length=2)
    postal_code: Optional[str] = None
    phone: Optional[str] = None
    wc_carrier_name: Optional[str] = None
    wc_policy_number: Optional[str] = None
    wc_carrier_phone: Optional[str] = None
    wc_policy_effective: Optional[str] = None
    pay_schedule: Optional[str] = None
    regular_payday: Optional[str] = None
    overtime_basis: Optional[str] = None
    sick_leave_policy: Optional[str] = None


class HireRequest(BaseModel):
    role: str  # instructor | front_desk | admin
    studio_id: Optional[str] = None
    pay_rate_cents: Optional[int] = Field(None, ge=0)
    pay_type: str = "per_class"
    tax_classification: str = "1099"
    title: Optional[str] = None
    department: Optional[str] = None
    hire_date: Optional[str] = None  # ISO date
    send_w4_email: bool = True


# ── Employer profile (per-tenant onboarding settings) ────────────────────────

@router.get("/employer-profile", dependencies=[Depends(require_permission("hiring.view", "hiring.manage_employer"))])
async def get_employer_profile():
    return {"data": await employer_service.get_profile()}


@router.put("/employer-profile")
async def update_employer_profile(
    body: EmployerProfileRequest,
    rbac: dict = Depends(require_permission("hiring.manage_employer")),
):
    profile = await employer_service.upsert_profile(body.model_dump(exclude_none=True))
    return {"data": profile}


# ── Pipeline review ──────────────────────────────────────────────────────────

@router.get("", dependencies=[Depends(require_permission("hiring.view"))])
async def list_applications(
    status: Optional[str] = None,
    q: Optional[str] = None,
    reviewer_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    rows = await hiring_service.list_applications(
        status=status, q=q, reviewer_id=reviewer_id,
        limit=min(limit, 200), offset=offset,
    )
    return {"data": rows, "count": len(rows)}


@router.get("/{application_id}", dependencies=[Depends(require_permission("hiring.view"))])
async def get_application(application_id: str):
    app = await hiring_service.get_application(application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return {"data": app}


@router.patch("/{application_id}")
async def update_application(
    application_id: str,
    body: UpdateApplicationRequest,
    rbac: dict = Depends(require_permission("hiring.manage")),
):
    try:
        app = await hiring_service.update_application(
            application_id, rbac["user_id"],
            status=body.status, rating=body.rating,
            assigned_reviewer_id=body.assigned_reviewer_id,
            rejection_reason=body.rejection_reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return {"data": app}


@router.post("/{application_id}/notes")
async def add_note(
    application_id: str,
    body: NoteRequest,
    rbac: dict = Depends(require_permission("hiring.manage")),
):
    res = await hiring_service.add_note(application_id, rbac["user_id"], body.note)
    if not res:
        raise HTTPException(status_code=404, detail="Application not found")
    return {"data": res}


@router.get(
    "/{application_id}/documents/{doc_id}",
    dependencies=[Depends(require_permission("hiring.view"))],
)
async def download_document(application_id: str, doc_id: str):
    res = await hiring_service.get_document(application_id, doc_id)
    if not res:
        raise HTTPException(status_code=404, detail="Document not found")
    data, filename, content_type = res
    return Response(
        content=data, media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# ── Hire ─────────────────────────────────────────────────────────────────────

@router.post("/{application_id}/hire")
async def hire_applicant(
    application_id: str,
    body: HireRequest,
    rbac: dict = Depends(require_permission("hiring.hire")),
):
    org_id = await _org_id(rbac["org_slug"])
    try:
        result = await hiring_service.hire_applicant(
            application_id, rbac["user_id"], org_id, rbac["org_slug"],
            role=body.role, studio_id=body.studio_id,
            pay_rate_cents=body.pay_rate_cents, pay_type=body.pay_type,
            tax_classification=body.tax_classification,
            title=body.title, department=body.department, hire_date=body.hire_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Create the onboarding packet (W-4, DE-4, I-9 §1, DLSE-NTE + CA notices),
    # prefilled from the application, + optional email of the single link.
    app = await hiring_service.get_application(application_id)
    packet = await onboarding_service.create_packet(
        result["user_id"], application_id,
        prefill={
            "first_name": app.get("first_name"), "last_name": app.get("last_name"),
            "email": result["email"],
        },
    )
    result["onboarding_token"] = packet["token"]
    result["onboarding_status"] = packet["status"]

    if body.send_w4_email:
        try:
            await _email_onboarding_link(result["email"], result["first_name"], packet["token"])
            result["onboarding_email_sent"] = True
        except Exception as e:  # email failure must not fail the hire
            logger.warning("Onboarding email send failed", error=str(e), user_id=result["user_id"])
            result["onboarding_email_sent"] = False

    return {"data": result}


async def _email_onboarding_link(to_email: str, first_name: str, token: str) -> None:
    """Email the new hire their onboarding-packet link via the studio's SMTP."""
    from app.services.email.email_service import EmailService
    base = "https://your-domain.com"
    url = f"{base}/onboarding/{token}"
    html = (
        f"<p>Welcome aboard, {first_name}!</p>"
        f"<p>Please complete your new-hire paperwork (tax forms, I-9, and required "
        f"notices) to finish onboarding:</p>"
        f'<p><a href="{url}" style="display:inline-block;padding:12px 24px;'
        f'background:#7a8b6f;color:#fff;text-decoration:none;border-radius:6px;'
        f'font-weight:600;">Complete Your Paperwork</a></p>'
        f"<p>This secure link expires in 21 days.</p>"
    )
    await EmailService().send_email(
        to_email=to_email, subject="Complete your new-hire paperwork",
        html_content=html,
    )


# ── DE-34 new-hire report ─────────────────────────────────────────────────────

@router.get("/de34/pending", dependencies=[Depends(require_permission("hiring.view"))])
async def list_de34_pending(rbac: dict = Depends(require_permission("hiring.view"))):
    org_id = await _org_id(rbac["org_slug"])
    return {"data": await de34_service.list_pending(org_id)}


@router.post("/employees/{user_id}/de34/mark-filed")
async def mark_de34_filed(user_id: str, rbac: dict = Depends(require_permission("hiring.manage"))):
    return {"data": await de34_service.mark_filed(user_id, rbac["user_id"])}


@router.get(
    "/employees/{user_id}/de34.pdf",
    summary="Generate the DE-34 new-hire report (contains SSN)",
)
async def get_de34_pdf(user_id: str, rbac: dict = Depends(require_permission("hiring.view_w4"))):
    org_id = await _org_id(rbac["org_slug"])
    try:
        res = await de34_service.generate_pdf(user_id, org_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    data, filename = res
    return Response(
        content=data, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# ── Onboarding packet viewer (restricted) ─────────────────────────────────────

@router.get(
    "/employees/{user_id}/onboarding",
    dependencies=[Depends(require_permission("hiring.view"))],
)
async def get_employee_onboarding(user_id: str):
    packet = await onboarding_service.get_packet_for_employee(user_id)
    if not packet:
        raise HTTPException(status_code=404, detail="No onboarding packet on file")
    return {"data": packet}


@router.get(
    "/employees/{user_id}/onboarding/documents/{doc_id}.pdf",
    dependencies=[Depends(require_permission("hiring.view_w4"))],
)
async def get_onboarding_document_pdf(user_id: str, doc_id: str):
    res = await onboarding_service.get_document_pdf(doc_id)
    if not res:
        raise HTTPException(status_code=404, detail="No signed document on file")
    data, filename = res
    return Response(
        content=data, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
