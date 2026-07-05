"""AuraFlow — Workshop Contract Endpoints

ADMIN endpoints (under /api/v1/contracts) require owner/admin/front_desk JWT.
PUBLIC endpoints (under /api/v1/external/contracts) are token-only — no JWT.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from app.api.v1.dependencies.auth import get_current_user
from app.api.v1.dependencies.rbac import require_permission
from app.core.config import settings
from app.core.logging import logger
from app.services.contracts import contract_service
from app.services.email.email_service import EmailService

router = APIRouter()
external_router = APIRouter()
email_svc = EmailService()


# ── Schemas ──

class CompensationInput(BaseModel):
    option: str = Field(..., description="flat_fee | per_participant | revenue_share | hybrid")
    flat_fee_cents: Optional[int] = None
    flat_fee_payable_per: Optional[str] = None  # 'session' | 'workshop'
    per_participant_cents: Optional[int] = None
    revenue_share_percent_to_instructor: Optional[int] = None
    hybrid_description: Optional[str] = None
    expense_reimbursements: Optional[str] = None
    payment_method: Optional[str] = None
    payment_timing_business_days: Optional[int] = None
    instructor_supplied_materials: Optional[str] = None
    studio_supplied_materials: Optional[str] = None


class PrepareContractIn(BaseModel):
    course_id: str
    compensation: CompensationInput


class VoidContractIn(BaseModel):
    reason: str


class SignContractIn(BaseModel):
    instructor_data: dict
    signature_image_data_url: str
    instructor_photo_data_url: str | None = None
    workshop_flyer_data_url: str | None = None


# ── ADMIN: prepare ────────────────────────────────────────────────────────────

@router.post("/contracts/prepare")
async def prepare_contract(
    body: PrepareContractIn,
    background: BackgroundTasks,
    user=Depends(get_current_user),
    _=Depends(require_permission("contracts.prepare")),
):
    """Studio admin creates a contract for a workshop. Sends the signing-link
    email to the guest instructor in the background and returns the contract row."""
    try:
        contract = await contract_service.prepare_contract_for_workshop(
            course_id=body.course_id,
            compensation_input=body.compensation.model_dump(exclude_none=True),
            prepared_by_user_id=str(user.get("id")),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    background.add_task(_send_signing_email, contract)
    return {"data": contract,
            "signing_url": contract_service.signing_url(contract["signing_token"])}


@router.post("/contracts/{contract_id}/void")
async def void_contract(
    contract_id: str,
    body: VoidContractIn,
    user=Depends(get_current_user),
    _=Depends(require_permission("contracts.manage")),
):
    try:
        out = await contract_service.void_contract(contract_id, str(user.get("id")), body.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": out}


@router.get("/contracts/{contract_id}")
async def get_contract(
    contract_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("contracts.view")),
):
    row = await contract_service.get_contract_admin(contract_id)
    if not row:
        raise HTTPException(status_code=404, detail="contract not found")
    return {"data": row}


@router.get("/contracts/{contract_id}/pdf")
async def download_contract_pdf(
    contract_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("contracts.view")),
):
    out = await contract_service.get_contract_pdf(contract_id)
    if out is None:
        raise HTTPException(status_code=404, detail="signed PDF not available")
    pdf_bytes, filename = out
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/contracts/by-course/{course_id}")
async def list_contracts_for_course(
    course_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("contracts.view")),
):
    rows = await contract_service.list_contracts_for_course(course_id)
    return {"data": rows}


# ── PUBLIC: token-only, mounted at /api/v1/external/contracts ────────────────

@external_router.get("/contracts/{token}")
async def public_get_for_signing(token: str):
    """Public endpoint — the unguessable token IS the auth. Returns prefilled
    data + the instructor field schema + studio acknowledgment string."""
    if not token or len(token) != 64:
        raise HTTPException(status_code=404, detail="contract not found")
    out = await contract_service.get_contract_for_signing(token)
    if out is None:
        raise HTTPException(status_code=404, detail="contract not found, expired, or already signed")
    return {"data": out}


@external_router.post("/contracts/{token}/sign")
async def public_sign(
    token: str,
    body: SignContractIn,
    request: Request,
    background: BackgroundTasks,
):
    """Public endpoint — instructor submits filled fields + drawn signature."""
    if not token or len(token) != 64:
        raise HTTPException(status_code=404, detail="contract not found")
    # Capture IP + UA for ESIGN audit trail. Trust X-Forwarded-For from Traefik.
    fwd = request.headers.get("x-forwarded-for") or ""
    signed_ip = fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")
    signed_user_agent = (request.headers.get("user-agent") or "")[:500]

    try:
        result = await contract_service.sign_contract(
            token=token,
            instructor_data=body.instructor_data,
            signature_image_data_url=body.signature_image_data_url,
            signed_ip=signed_ip,
            signed_user_agent=signed_user_agent,
            instructor_photo_data_url=body.instructor_photo_data_url,
            workshop_flyer_data_url=body.workshop_flyer_data_url,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    background.add_task(_send_signed_receipts, result["id"])
    return {"data": result}





class WorkshopSessionIn(BaseModel):
    starts_at: str  # ISO 8601
    ends_at: str
    location: Optional[str] = None
    is_virtual: bool = False
    title: Optional[str] = None


class CreateGuestWorkshopIn(BaseModel):
    workshop_name: str
    # Sessions: new shape. Pass one entry for a single-day workshop or
    # multiple entries for a multi-session workshop / teacher training.
    sessions: Optional[list[WorkshopSessionIn]] = None
    # Override the duplicate guard — set to True only when intentionally
    # creating a second workshop for the same guest at the same start time.
    allow_duplicate: bool = False
    # Back-compat: old single-session shape — used if sessions is omitted.
    workshop_starts_at: Optional[str] = None
    workshop_ends_at: Optional[str] = None
    workshop_cost_cents: int
    instructor_share_percent: int = Field(60, ge=0, le=100)
    location: Optional[str] = None
    capacity: Optional[int] = None
    min_enrollment: Optional[int] = None
    # Pick existing OR create new — exactly one of these must apply
    guest_instructor_id: Optional[str] = None
    new_guest_name: Optional[str] = None
    new_guest_email: Optional[str] = None
    new_guest_phone: Optional[str] = None


@router.post("/contracts/create-guest-workshop")
async def create_guest_workshop_endpoint(
    body: CreateGuestWorkshopIn,
    background: BackgroundTasks,
    user=Depends(get_current_user),
    _=Depends(require_permission("contracts.create_guest_workshop")),
):
    """Single-shot: creates the workshop (course + course_session), creates
    or reuses the guest_instructor, prepares the contract, and emails the
    signing link to the guest in the background."""
    from datetime import datetime as _dt
    def _parse(dt_str: str):
        return _dt.fromisoformat(dt_str.replace("Z", "+00:00"))
    try:
        if body.sessions:
            sessions = [
                {
                    "starts_at": _parse(s.starts_at),
                    "ends_at": _parse(s.ends_at),
                    "location": s.location,
                    "is_virtual": s.is_virtual,
                    "title": s.title,
                }
                for s in body.sessions
            ]
        elif body.workshop_starts_at and body.workshop_ends_at:
            sessions = [
                {
                    "starts_at": _parse(body.workshop_starts_at),
                    "ends_at": _parse(body.workshop_ends_at),
                    "location": None,
                    "is_virtual": False,
                    "title": None,
                }
            ]
        else:
            raise HTTPException(
                status_code=400,
                detail="must provide either sessions[] or workshop_starts_at + workshop_ends_at",
            )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="invalid datetime format (use ISO 8601)")
    try:
        result = await contract_service.create_guest_workshop(
            workshop_name=body.workshop_name,
            sessions=sessions,
            allow_duplicate=body.allow_duplicate,
            workshop_cost_cents=body.workshop_cost_cents,
            instructor_share_percent=body.instructor_share_percent,
            location=body.location,
            capacity=body.capacity,
            min_enrollment=body.min_enrollment,
            guest_instructor_id=body.guest_instructor_id,
            new_guest_name=body.new_guest_name,
            new_guest_email=body.new_guest_email,
            new_guest_phone=body.new_guest_phone,
            prepared_by_user_id=str(user.get("id")) if user else None,
        )
    except ValueError as e:
        msg = str(e)
        # Duplicate-guard violation → 409 Conflict so the UI can show a confirm prompt.
        if "already exists" in msg and "allow_duplicate" in msg:
            raise HTTPException(status_code=409, detail=msg)
        raise HTTPException(status_code=400, detail=msg)

    # Fire the signing-link email in background (already wired in prepare flow,
    # but our composite create() returns the contract dict which already triggered
    # the email via prepare_contract_for_workshop only if we'd called the
    # endpoint version — call it here to match the existing pattern)
    background.add_task(_send_signing_email, result["contract"])
    return {
        "data": result,
        "signing_url": contract_service.signing_url(result["contract"]["signing_token"]),
    }


# ── Email helpers (background tasks) ────────────────────────────────────────

async def _send_signing_email(contract: dict) -> None:
    """Sent right after prepare. Goes to the guest instructor's email
    (from guest_instructors row, which prefilled_data['guest_known_contact']
    surfaced)."""
    try:
        import json as _json
        pf = contract.get("prefilled_data") or {}
        if isinstance(pf, str):
            pf = _json.loads(pf) if pf else {}
        guest_email = (pf.get("guest_known_contact") or {}).get("email")
        guest_name = (pf.get("guest_known_contact") or {}).get("name") or "Instructor"
        workshop_title = (pf.get("workshop") or {}).get("title") or "your workshop"
        if not guest_email:
            logger.warning("contract.email_skipped — no email on guest_instructors",
                           contract_id=contract["id"])
            return
        url = contract_service.signing_url(contract["signing_token"])
        html = f"""
        <h2>Contract ready to sign — {workshop_title}</h2>
        <p>Hi {guest_name.split()[0] if guest_name else 'there'},</p>
        <p>Thank you for partnering with Your Studio on <strong>{workshop_title}</strong>.
        We've prepared your Guest Instructor Workshop Services Agreement and it's ready
        for your review and signature.</p>
        <p style="margin: 24px 0;">
          <a href="{url}" style="background:#2d6a4f;color:white;padding:12px 24px;
             border-radius:6px;text-decoration:none;font-weight:600;">
             Review &amp; Sign Contract
          </a>
        </p>
        <p>The link is unique to you — please don't share it. It expires 60 days from now.</p>
        <p>If you have questions before signing, just reply to this email or call us at
        (559) 915-3967.</p>
        <p>— the studio team</p>
        """
        await email_svc.send_email(
            to_email=guest_email,
            subject=f"Contract ready to sign — {workshop_title}",
            html_content=html,
            email_type="contract_signing_link",
        )
        await contract_service.mark_email_sent(contract["id"])
    except Exception as e:
        logger.error("contract.email_send_failed", contract_id=contract["id"], error=str(e))


async def _send_signed_receipts(contract_id: str) -> None:
    """After signing: email both parties a copy of the combined details +
    contract PDF as an attachment. EmailService.send_email gained
    attachments= support in this batch.

    Background-task wrapper: this runs OUTSIDE the request, so the
    TenantContext set by TenantMiddleware is gone. Resolve tenant from
    the contract id first."""
    from app.core.tenant_context import set_tenant_context, clear_tenant_context
    resolved = await contract_service._resolve_tenant_for_contract_id(contract_id)
    if not resolved:
        logger.error("contract.receipt_send_failed", contract_id=contract_id, error="could not resolve tenant for contract id")
        return
    org_id, schema_name, slug = resolved
    set_tenant_context(organization_id=org_id, schema_name=schema_name, slug=slug)
    try:
        await _send_signed_receipts_inner(contract_id)
    finally:
        clear_tenant_context()


async def _send_signed_receipts_inner(contract_id: str) -> None:
    try:
        contract = await contract_service.get_contract_admin(contract_id)
        if not contract or contract["status"] != "signed":
            return
        pdf_out = await contract_service.get_combined_pdf(contract_id)
        attachments = []
        if pdf_out:
            pdf_bytes, filename = pdf_out
            attachments.append({"filename": filename, "content": pdf_bytes, "mime_type": "application/pdf"})
        import json as _json
        pf = contract.get("prefilled_data") or {}
        if isinstance(pf, str):
            pf = _json.loads(pf) if pf else {}
        idata = contract.get("instructor_data") or {}
        if isinstance(idata, str):
            idata = _json.loads(idata) if idata else {}
        guest_email = (
            idata.get("email")
            or (pf.get("guest_known_contact") or {}).get("email")
        )
        guest_name = idata.get("legal_name") or "Instructor"
        workshop_title = (pf.get("workshop") or {}).get("title") or "your workshop"
        signed_at = contract.get("signed_at", "")
        eff = contract.get("effective_date", "")

        recipients = []
        if guest_email:
            recipients.append((guest_email,
                f"Hi {guest_name.split()[0] if guest_name else 'there'},",
                "Thank you for signing — your contract is officially executed. "
                "Your signed copy (including the workshop marketing details you "
                "supplied) is attached. Save it for your records.",
            ))
        studio_admin_email = settings.PLATFORM_ADMIN_ALERT_EMAIL
        if studio_admin_email:
            recipients.append((studio_admin_email,
            f"Hi,",
            f"{guest_name} just signed the contract for {workshop_title}. "
            f"The signed copy (with marketing details, photo, flyer, and ESIGN "
            f"audit trail) is attached. Also stored on the workshop_contracts "
            f"row for the AuraFlow dashboard.",
        ))

        for to_email, greeting, body in recipients:
            html = f"""
            <h2>Signed: {workshop_title}</h2>
            <p>{greeting}</p>
            <p>{body}</p>
            <table style="margin:16px 0;">
              <tr><td style="padding:4px 12px;color:#555;">Workshop:</td><td style="padding:4px 12px;"><strong>{workshop_title}</strong></td></tr>
              <tr><td style="padding:4px 12px;color:#555;">Effective Date:</td><td style="padding:4px 12px;">{eff}</td></tr>
              <tr><td style="padding:4px 12px;color:#555;">Signed at:</td><td style="padding:4px 12px;">{signed_at}</td></tr>
              <tr><td style="padding:4px 12px;color:#555;">Signed by:</td><td style="padding:4px 12px;">{guest_name}</td></tr>
            </table>
            <p>The full signed contract (with workshop marketing details, both signatures, and ESIGN audit trail) is attached as a PDF.</p>
            <p>— Your Studio</p>
            """
            await email_svc.send_email(
                to_email=to_email,
                subject=f"Signed contract — {workshop_title}",
                html_content=html,
                email_type="contract_signed_receipt",
                attachments=attachments,
            )
    except Exception as e:
        logger.error("contract.receipt_send_failed", contract_id=contract_id, error=str(e))
