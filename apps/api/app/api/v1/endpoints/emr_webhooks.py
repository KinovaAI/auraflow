"""AuraFlow — EMR Inbound Webhook Endpoints

Receives patient creation/update notifications from EMR systems.
- FHIR R4: Subscription notifications (JSON)
- HL7v2: HTTP-bridged ADT messages
"""
import hashlib
import hmac
import json

from fastapi import APIRouter, HTTPException, Request

from app.core.logging import logger
from app.db.session import get_global_db
from app.services.integrations.emr import emr_service
from app.services.integrations.emr.fhir_client import FhirClient

emr_router = APIRouter()


async def _resolve_org(request: Request) -> tuple[str, str]:
    """Resolve org_id and schema from the X-Auraflow-Org header or query param."""
    org_slug = (
        request.headers.get("X-Auraflow-Org")
        or request.query_params.get("org")
    )
    if not org_slug:
        raise HTTPException(status_code=400, detail="Missing X-Auraflow-Org header")

    async with get_global_db() as db:
        row = await db.fetchrow(
            "SELECT id, slug FROM af_global.organizations WHERE slug = $1 AND emr_sync_enabled = TRUE",
            org_slug,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Organization not found or EMR not enabled")

    return str(row["id"]), f"af_tenant_{row['slug']}"


async def _verify_webhook_signature(request: Request, org_id: str) -> bool:
    """Verify HMAC-SHA256 webhook signature if a secret is configured."""
    async with get_global_db() as db:
        row = await db.fetchrow(
            "SELECT emr_webhook_secret FROM af_global.organizations WHERE id = $1",
            org_id,
        )

    secret = row["emr_webhook_secret"] if row else None
    if not secret:
        return True  # No secret configured, skip verification

    signature = request.headers.get("X-Webhook-Signature", "")
    body = await request.body()
    expected = hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(signature, expected)


@emr_router.post("/fhir")
async def fhir_webhook(request: Request):
    """Receive FHIR Subscription notifications.

    Expects a FHIR Bundle with Patient resource entries.
    Creates/updates AuraFlow members from incoming patient data.
    """
    org_id, schema = await _resolve_org(request)

    if not await _verify_webhook_signature(request, org_id):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    body = await request.json()
    resource_type = body.get("resourceType", "")

    processed = 0

    if resource_type == "Bundle":
        # Subscription notification bundle
        for entry in body.get("entry", []):
            resource = entry.get("resource", {})
            if resource.get("resourceType") == "Patient":
                patient_data = FhirClient._parse_patient_resource(None, resource)
                result = await emr_service.sync_patient_to_auraflow(
                    org_id, schema, patient_data
                )
                if result:
                    processed += 1

    elif resource_type == "Patient":
        # Direct Patient resource notification
        patient_data = FhirClient._parse_patient_resource(None, body)
        result = await emr_service.sync_patient_to_auraflow(
            org_id, schema, patient_data
        )
        if result:
            processed += 1

    logger.info("FHIR webhook processed", org_id=org_id, processed=processed)
    return {"status": "ok", "processed": processed}


@emr_router.post("/hl7")
async def hl7_webhook(request: Request):
    """Receive HL7v2 ADT messages via HTTP bridge.

    Parses ADT^A04 (Register) and ADT^A08 (Update) messages
    to create/update AuraFlow members.
    """
    org_id, schema = await _resolve_org(request)

    if not await _verify_webhook_signature(request, org_id):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    body = await request.body()
    message = body.decode("utf-8").strip("\x0b\x1c\x0d")

    segments = message.split("\r")
    if not segments:
        raise HTTPException(status_code=400, detail="Empty HL7 message")

    # Parse MSH
    msh = segments[0].split("|")
    if len(msh) < 9:
        raise HTTPException(status_code=400, detail="Invalid MSH segment")

    msg_type = msh[8]  # e.g., ADT^A04
    if "^" in msg_type:
        msg_type_parts = msg_type.split("^")
        message_type = msg_type_parts[0]
        trigger = msg_type_parts[1] if len(msg_type_parts) > 1 else ""
    else:
        message_type = msg_type
        trigger = ""

    if message_type != "ADT" or trigger not in ("A04", "A08"):
        # Only handle patient register and update
        return {"status": "ignored", "message_type": msg_type}

    # Parse PID segment
    patient_data = {}
    for seg in segments:
        if seg.startswith("PID"):
            fields = seg.split("|")
            if len(fields) > 5:
                # PID-3: Patient ID
                patient_data["emr_patient_id"] = fields[2] or fields[3]

                # PID-5: Patient Name (last^first)
                name_parts = fields[5].split("^") if len(fields) > 5 else []
                patient_data["last_name"] = name_parts[0] if name_parts else ""
                patient_data["first_name"] = name_parts[1] if len(name_parts) > 1 else ""

                # PID-7: DOB
                if len(fields) > 7 and fields[7]:
                    dob = fields[7]
                    if len(dob) >= 8:
                        patient_data["date_of_birth"] = f"{dob[:4]}-{dob[4:6]}-{dob[6:8]}"

                # PID-8: Gender
                if len(fields) > 8:
                    gender_map = {"M": "male", "F": "female", "O": "non_binary"}
                    patient_data["gender"] = gender_map.get(fields[8])

                # PID-11: Address
                if len(fields) > 11 and fields[11]:
                    addr_parts = fields[11].split("^")
                    patient_data["address_line1"] = addr_parts[0] if addr_parts else None
                    patient_data["city"] = addr_parts[2] if len(addr_parts) > 2 else None
                    patient_data["state"] = addr_parts[3] if len(addr_parts) > 3 else None
                    patient_data["postal_code"] = addr_parts[4] if len(addr_parts) > 4 else None

                # PID-13: Phone/Email
                if len(fields) > 13 and fields[13]:
                    contact = fields[13]
                    if "~" in contact:
                        parts = contact.split("~")
                        patient_data["phone"] = parts[0]
                        # Email in repeat
                        for part in parts[1:]:
                            if "@" in part:
                                # Extract email from component
                                comps = part.split("^")
                                for c in comps:
                                    if "@" in c:
                                        patient_data["email"] = c
                                        break
                    else:
                        patient_data["phone"] = contact
            break

    if not patient_data.get("emr_patient_id"):
        raise HTTPException(status_code=400, detail="No patient ID in PID segment")

    result = await emr_service.sync_patient_to_auraflow(org_id, schema, patient_data)

    logger.info(
        "HL7 webhook processed",
        org_id=org_id,
        trigger=trigger,
        emr_patient_id=patient_data.get("emr_patient_id"),
        member_id=result,
    )
    return {"status": "ok", "member_id": result}
