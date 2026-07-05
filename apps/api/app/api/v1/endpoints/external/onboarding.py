"""AuraFlow — External Onboarding Packet endpoints (public, token-only)

The new hire opens /external/onboarding/{token} (no auth — the 64-hex token is
the credential), and completes each document (W-4, DE-4, I-9 §1, DLSE-NTE, and
the CA notice acknowledgments). Tenant is resolved from the token; SSN-bearing
forms encrypt the SSN; each signed document is rendered + stored as a PDF.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.services.hiring import onboarding_service

router = APIRouter()


class SignDocumentRequest(BaseModel):
    signature_text: str = Field(..., min_length=1, max_length=255)
    ssn: Optional[str] = Field(None, max_length=11)
    form_data: dict = {}


@router.get("/onboarding/{token}", summary="Fetch a new-hire onboarding packet")
async def get_packet(token: str):
    data = await onboarding_service.get_packet_for_signing(token)
    if data is None:
        raise HTTPException(status_code=404, detail="Invalid or expired link")
    return {"data": data}


@router.post("/onboarding/{token}/documents/{doc_id}/sign", summary="Sign one document")
async def sign_document(token: str, doc_id: str, body: SignDocumentRequest, request: Request):
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
        request.client.host if request.client else None
    )
    try:
        result = await onboarding_service.sign_document(
            token, doc_id, form_data=body.form_data,
            signature_text=body.signature_text, ssn=body.ssn, signed_ip=ip,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="Invalid or expired link")
    return {"data": result}
