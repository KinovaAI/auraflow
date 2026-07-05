"""AuraFlow — External Job Application endpoints (api-key gated)

Used by a studio's branded careers page (your-domain.com/careers) to
submit applications and upload resumes without exposing internal auth.
Tenant scoping comes from the API key. New scopes: applications:read / write.
"""
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field, EmailStr

from app.api.v1.dependencies.api_key_auth import get_api_key_context, require_api_scope
from app.services.hiring import hiring_service

router = APIRouter()


# ── Schema describing the form (keeps the branded frontend in sync) ──────────

_SCHEMA = {
    "position_types": ["instructor", "front_desk", "admin", "other"],
    "employment_types": ["full_time", "part_time", "contract"],
    "document_types": ["resume", "certification", "insurance", "yoga_alliance", "other"],
    "max_document_mb": hiring_service.MAX_DOCUMENT_BYTES // (1024 * 1024),
    "fields": {
        "required": ["first_name", "last_name", "email", "position_type",
                     "authorized_to_work", "over_18", "attestation"],
        "experience": ["years_experience", "experience_seniors",
                       "experience_injuries", "experience_pain", "specialties",
                       "work_history"],
        "credentials": ["certifications", "yoga_alliance_number",
                        "yoga_alliance_level", "cpr_first_aid", "liability_insurance"],
    },
}


@router.get(
    "/job-application/schema",
    dependencies=[Depends(require_api_scope("applications:read"))],
    summary="Job application form schema (field + option lists)",
)
async def get_application_schema(ctx: dict = Depends(get_api_key_context)):
    return {"data": _SCHEMA}


# ── Submission ───────────────────────────────────────────────────────────────

class WorkHistoryItem(BaseModel):
    employer: Optional[str] = None
    title: Optional[str] = None
    dates: Optional[str] = None
    contact: Optional[str] = None


class CertificationItem(BaseModel):
    name: Optional[str] = None
    issuer: Optional[str] = None
    issued_on: Optional[str] = None
    expires_on: Optional[str] = None


class ReferenceItem(BaseModel):
    name: Optional[str] = None
    relationship: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class JobApplicationCreate(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=120)
    last_name: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    phone: Optional[str] = Field(None, max_length=40)
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    position_type: str = "instructor"
    position_title: Optional[str] = None
    employment_type: Optional[str] = None
    availability: Optional[str] = None
    earliest_start_date: Optional[str] = None
    desired_pay_text: Optional[str] = None
    authorized_to_work: bool = False
    over_18: bool = False
    years_experience: Optional[int] = Field(None, ge=0, le=80)
    experience_seniors: Optional[str] = None
    experience_injuries: Optional[str] = None
    experience_pain: Optional[str] = None
    specialties: list[str] = []
    work_history: list[WorkHistoryItem] = []
    certifications: list[CertificationItem] = []
    yoga_alliance_number: Optional[str] = None
    yoga_alliance_level: Optional[str] = None
    cpr_first_aid: bool = False
    liability_insurance: bool = False
    references: list[ReferenceItem] = []
    cover_letter: Optional[str] = None
    hear_about_us: Optional[str] = None
    attestation: bool = False


@router.post(
    "/job-applications",
    dependencies=[Depends(require_api_scope("applications:write"))],
    status_code=201,
    summary="Submit a job application",
)
async def submit_application(
    body: JobApplicationCreate,
    ctx: dict = Depends(get_api_key_context),
):
    if body.position_type not in _SCHEMA["position_types"]:
        raise HTTPException(status_code=422, detail="Invalid position_type")
    if not body.attestation:
        raise HTTPException(status_code=422, detail="Attestation is required")
    data = body.model_dump()
    data["work_history"] = [w.model_dump() for w in body.work_history]
    data["certifications"] = [c.model_dump() for c in body.certifications]
    data["references"] = [r.model_dump() for r in body.references]
    data["email"] = str(body.email).lower()
    app = await hiring_service.create_application(data)
    return {"data": {"id": app["id"], "status": app["status"]}}


@router.post(
    "/job-applications/{application_id}/documents",
    dependencies=[Depends(require_api_scope("applications:write"))],
    status_code=201,
    summary="Upload a document (resume, cert, insurance) to an application",
)
async def upload_document(
    application_id: str,
    doc_type: str = Form("resume"),
    file: UploadFile = File(...),
    ctx: dict = Depends(get_api_key_context),
):
    content = await file.read()
    try:
        meta = await hiring_service.add_document(
            application_id, doc_type, file.filename or "upload",
            file.content_type or "application/octet-stream", content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"data": meta}
