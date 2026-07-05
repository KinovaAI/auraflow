"""AuraFlow — New-hire Onboarding Packet Service

Creates the per-hire packet (seeded from the CA form catalog), serves it over
a single public token, and records each signed document (PDF stored). Forms
auto-fill from the tenant's employer_profile + the employee's data.
"""
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from app.core.logging import logger
from app.db.session import get_tenant_db, get_global_db
from app.utils.encryption import encrypt_credential, decrypt_credential
from app.services.hiring import onboarding_forms, employer_service

PACKET_TOKEN_TTL_DAYS = 21


# ── Creation (during hire) ──────────────────────────────────────────────────

async def create_packet(user_id: str, application_id: str | None,
                        prefill: dict) -> dict:
    """Create an onboarding packet seeded with the standard CA documents.
    Runs in the tenant context set by the hire request. Returns {id, token}."""
    packet_id = str(uuid.uuid4())
    token = secrets.token_hex(32)
    expires = datetime.now(timezone.utc) + timedelta(days=PACKET_TOKEN_TTL_DAYS)
    async with get_tenant_db() as db:
        async with db.transaction():
            await db.execute(
                """
                INSERT INTO onboarding_packets
                    (id, user_id, application_id, first_name, last_name, email,
                     signing_token, signing_token_expires_at, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'pending')
                """,
                packet_id, user_id, application_id,
                prefill.get("first_name"), prefill.get("last_name"),
                prefill.get("email"), token, expires,
            )
            for i, spec in enumerate(onboarding_forms.CATALOG):
                await db.execute(
                    """
                    INSERT INTO onboarding_documents
                        (id, packet_id, user_id, doc_type, kind, title, sort_order, status)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending')
                    """,
                    str(uuid.uuid4()), packet_id, user_id, spec["doc_type"],
                    spec["kind"], spec["title"], i,
                )
    logger.info("Onboarding packet created", packet_id=packet_id, user_id=user_id)
    return {"id": packet_id, "token": token, "status": "pending"}


# ── Token resolution (public) ───────────────────────────────────────────────

async def _resolve_tenant_for_token(token: str) -> tuple[str, str, str] | None:
    async with get_global_db() as gdb:
        orgs = await gdb.fetch(
            "SELECT id, slug, schema_name FROM af_global.organizations WHERE status = 'active'"
        )
        for org in orgs:
            hit = await gdb.fetchval(
                f"SELECT 1 FROM {org['schema_name']}.onboarding_packets "
                f"WHERE signing_token = $1 LIMIT 1",
                token,
            )
            if hit:
                return (str(org["id"]), org["schema_name"], org["slug"])
    return None


async def _with_tenant_for_token(token: str, fn):
    from app.core.tenant_context import set_tenant_context, clear_tenant_context
    resolved = await _resolve_tenant_for_token(token)
    if not resolved:
        return None
    org_id, schema_name, slug = resolved
    set_tenant_context(organization_id=org_id, schema_name=schema_name, slug=slug)
    try:
        return await fn(org_id, slug)
    finally:
        clear_tenant_context()


async def _employee_ctx(db, packet) -> dict:
    """Build the employee data used to prefill forms (name + address)."""
    ee = {
        "first_name": packet["first_name"], "last_name": packet["last_name"],
        "email": packet["email"],
    }
    if packet["application_id"]:
        app = await db.fetchrow(
            """SELECT address_line1, address_line2, city, state, postal_code
               FROM job_applications WHERE id = $1""",
            packet["application_id"],
        )
        if app:
            ee.update({k: app[k] for k in ("address_line1", "address_line2", "city", "state", "postal_code")})
    return ee


async def get_packet_for_signing(token: str) -> dict | None:
    """Public: the packet + its documents (status) + prefill context."""
    async def _inner(org_id, slug):
        async with get_tenant_db() as db:
            packet = await db.fetchrow(
                """SELECT * FROM onboarding_packets
                   WHERE signing_token = $1 AND signing_token_expires_at > NOW()""",
                token,
            )
            if not packet:
                return None
            docs = await db.fetch(
                """SELECT id, doc_type, kind, title, sort_order, status
                   FROM onboarding_documents WHERE packet_id = $1 ORDER BY sort_order""",
                packet["id"],
            )
            employee = await _employee_ctx(db, packet)
            employer = await employer_service.get_profile()
        return {
            "status": packet["status"],
            "employer_name": (employer or {}).get("legal_name") or (employer or {}).get("dba_name") or slug,
            "employee": {"first_name": employee.get("first_name"), "last_name": employee.get("last_name")},
            "documents": [
                {"id": str(d["id"]), "doc_type": d["doc_type"], "kind": d["kind"],
                 "title": d["title"], "status": d["status"], "sort_order": d["sort_order"],
                 "collects_ssn": onboarding_forms.CATALOG_BY_TYPE.get(d["doc_type"], {}).get("collects_ssn", False),
                 "body_text": onboarding_forms.CATALOG_BY_TYPE.get(d["doc_type"], {}).get("body_text")}
                for d in docs
            ],
        }
    return await _with_tenant_for_token(token, _inner)


async def sign_document(token: str, doc_id: str, *, form_data: dict,
                       signature_text: str, ssn: str | None = None,
                       signed_ip: str | None = None) -> dict | None:
    """Public: complete one document — render + store its signed PDF."""
    if not signature_text or not signature_text.strip():
        raise ValueError("Signature is required.")

    async def _inner(org_id, slug):
        async with get_tenant_db() as db:
            packet = await db.fetchrow(
                """SELECT * FROM onboarding_packets
                   WHERE signing_token = $1 AND signing_token_expires_at > NOW()""",
                token,
            )
            if not packet:
                return None
            doc = await db.fetchrow(
                "SELECT * FROM onboarding_documents WHERE id = $1 AND packet_id = $2",
                doc_id, packet["id"],
            )
            if not doc:
                return None
            spec = onboarding_forms.CATALOG_BY_TYPE.get(doc["doc_type"])
            if not spec:
                raise ValueError("Unknown document type.")

            ssn_enc = None
            form = dict(form_data or {})
            form["signature_text"] = signature_text.strip()
            if spec.get("collects_ssn"):
                digits = "".join(c for c in (ssn or "") if c.isdigit())
                if len(digits) != 9:
                    raise ValueError("A valid 9-digit SSN is required for this form.")
                ssn_enc = await encrypt_credential(db, digits)
                form["ssn"] = digits

            employee = await _employee_ctx(db, packet)
            employer = await employer_service.get_profile()
            pdf = await onboarding_forms.render_pdf(
                doc["doc_type"],
                {"employer": employer, "employee": employee, "form": form, "hire": {}},
            )
            form.pop("ssn", None)  # never persist plaintext SSN in form_data

            async with db.transaction():
                await db.execute(
                    """UPDATE onboarding_documents
                       SET form_data = $1, ssn_encrypted = $2, signature_text = $3,
                           signed_at = NOW(), signed_ip = $4, status = 'completed',
                           signed_pdf = $5, updated_at = NOW()
                       WHERE id = $6""",
                    json.dumps(form), ssn_enc, signature_text.strip(),
                    signed_ip, pdf, doc_id,
                )
                remaining = await db.fetchval(
                    "SELECT COUNT(*) FROM onboarding_documents WHERE packet_id = $1 AND status != 'completed'",
                    packet["id"],
                )
                if remaining == 0:
                    await db.execute(
                        "UPDATE onboarding_packets SET status = 'completed', signing_token = NULL, updated_at = NOW() WHERE id = $1",
                        packet["id"],
                    )
            return {"status": "completed", "packet_complete": remaining == 0}
    return await _with_tenant_for_token(token, _inner)


# ── Internal (hiring.view / view_w4) ────────────────────────────────────────

async def get_packet_for_employee(user_id: str) -> dict | None:
    async with get_tenant_db() as db:
        packet = await db.fetchrow(
            "SELECT * FROM onboarding_packets WHERE user_id = $1 ORDER BY created_at DESC LIMIT 1",
            user_id,
        )
        if not packet:
            return None
        docs = await db.fetch(
            """SELECT id, doc_type, kind, title, status, signed_at, (signed_pdf IS NOT NULL) AS has_pdf
               FROM onboarding_documents WHERE packet_id = $1 ORDER BY sort_order""",
            packet["id"],
        )
    return {
        "id": str(packet["id"]), "status": packet["status"],
        "documents": [
            {"id": str(d["id"]), "doc_type": d["doc_type"], "kind": d["kind"],
             "title": d["title"], "status": d["status"],
             "signed_at": d["signed_at"].isoformat() if d["signed_at"] else None,
             "has_pdf": d["has_pdf"]}
            for d in docs
        ],
    }


async def get_document_ssn(doc_id: str) -> str | None:
    """Decrypt a document's SSN (gated by hiring.view_w4 at the endpoint)."""
    async with get_tenant_db() as db:
        row = await db.fetchrow("SELECT ssn_encrypted FROM onboarding_documents WHERE id = $1", doc_id)
        if not row or row["ssn_encrypted"] is None:
            return None
        return await decrypt_credential(db, row["ssn_encrypted"])


async def get_employee_ssn(user_id: str) -> str | None:
    """Decrypt the employee's SSN from their most recent completed SSN-bearing
    onboarding document (W-4/DE-4/I-9). Gated by hiring.view_w4 at the caller."""
    async with get_tenant_db() as db:
        row = await db.fetchrow(
            """SELECT ssn_encrypted FROM onboarding_documents
               WHERE user_id = $1 AND ssn_encrypted IS NOT NULL
               ORDER BY signed_at DESC NULLS LAST LIMIT 1""",
            user_id,
        )
        if not row or row["ssn_encrypted"] is None:
            return None
        return await decrypt_credential(db, row["ssn_encrypted"])


async def get_document_pdf(doc_id: str):
    async with get_tenant_db() as db:
        row = await db.fetchrow(
            "SELECT doc_type, signed_pdf FROM onboarding_documents WHERE id = $1 AND signed_pdf IS NOT NULL",
            doc_id,
        )
    if not row or not row["signed_pdf"]:
        return None
    return bytes(row["signed_pdf"]), f"{row['doc_type']}.pdf"
