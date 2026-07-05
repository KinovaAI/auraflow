"""Workshop contracts business logic.

Lifecycle: prepared → sent → viewed → signed (or → voided).
"""
from __future__ import annotations

import base64
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.core.logging import logger
from app.db.session import get_tenant_db
from app.services.contracts.templates import guest_workshop_v1


def _decode_data_url(data_url: str, *, max_size: int = 5_500_000) -> tuple[bytes, str]:
    """Parse a base64 data URL ('data:image/png;base64,XXX') into (bytes, mime).
    Raises ValueError if malformed or the payload exceeds max_size bytes."""
    if not data_url or not isinstance(data_url, str) or not data_url.startswith('data:') or ';base64,' not in data_url:
        raise ValueError('expected a base64 data: URL')
    header, payload = data_url.split(';base64,', 1)
    mime = header.removeprefix('data:') or 'application/octet-stream'
    try:
        blob = base64.b64decode(payload, validate=False)
    except Exception as exc:
        raise ValueError(f'malformed base64 payload: {exc}') from exc
    if len(blob) > max_size:
        raise ValueError(f'image too large ({len(blob)} bytes; max {max_size})')
    return blob, mime


def _shrink_image(blob: bytes, mime: str, *, max_dim: int = 900, quality: int = 78) -> tuple[bytes, str]:
    """Resize + recompress a photo so embedded contract PDFs stay small.

    Kim Bordagaray's 2026-06-10 contract embedded a 3.7 MB phone-camera
    JPEG as-is, producing a 5 MB signed PDF that some mail clients
    silently dropped. Headshots and workshop flyers don't need
    full-camera resolution in a contract — 900 px on the long edge at
    78% JPEG quality renders sharply on screen and at 300 DPI print
    while bringing typical embeds to ~50-150 KB.

    Skip-if-already-small: bytes ≤ 300 KB are returned untouched (avoids
    re-encoding an already-optimized asset).
    """
    if len(blob) <= 300_000 or not mime.startswith("image/"):
        return blob, mime
    try:
        from PIL import Image
        from io import BytesIO
        img = Image.open(BytesIO(blob))
        # Honor EXIF rotation so the photo isn't sideways after resize
        try:
            from PIL import ImageOps
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.LANCZOS)
        # Strip alpha/palette to keep JPEG happy
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        out = BytesIO()
        img.save(out, format="JPEG", quality=quality, optimize=True, progressive=True)
        shrunk = out.getvalue()
        # Only swap if we actually saved space
        if len(shrunk) < len(blob):
            return shrunk, "image/jpeg"
    except Exception as exc:
        logger.warning("Image shrink failed — embedding original", error=str(exc), original_size=len(blob))
    return blob, mime


SIGNING_TOKEN_TTL_DAYS = 60  # contracts expire 60d after prepare


# ── Public API ──────────────────────────────────────────────────────────────

async def prepare_contract_for_workshop(
    course_id: str,
    compensation_input: dict,
    prepared_by_user_id: str,
) -> dict:
    """Studio admin: build a contract for a workshop ready to email.

    course_id          — courses.id (must have type='workshop' and a guest_instructor_id)
    compensation_input — dict matching the comp section of guest_workshop_v1.prefill()
    prepared_by_user_id — for audit; stored on the row indirectly via app.audit_service later

    Returns: row dict (incl. signing_token + signing_url to send to the instructor)
    """
    async with get_tenant_db() as db:
        # 1. Load the workshop (course) + verify it's a workshop with a guest
        course = await db.fetchrow(
            "SELECT id, title, description, type, guest_instructor_id, location, "
            "       capacity, min_enrollment, price_cents, is_virtual, prerequisites, "
            "       starts_at, ends_at FROM courses WHERE id = $1",
            uuid.UUID(course_id),
        )
        if not course:
            raise ValueError(f"course not found: {course_id}")
        if course["type"] != "workshop":
            raise ValueError(f"course is not a workshop (type={course['type']})")
        if not course["guest_instructor_id"]:
            raise ValueError("workshop has no guest_instructor assigned")

        guest = await db.fetchrow(
            "SELECT id, name, email, phone, address_line1, city, state, postal_code "
            "FROM guest_instructors WHERE id = $1",
            course["guest_instructor_id"],
        )
        if not guest:
            raise ValueError(f"guest_instructor not found: {course['guest_instructor_id']}")

        sessions = await db.fetch(
            "SELECT starts_at, ends_at FROM course_sessions "
            "WHERE course_id = $1 ORDER BY starts_at",
            course["id"],
        )

        # 2. Refuse if there's already an active (non-voided) contract for this course
        existing = await db.fetchrow(
            "SELECT id, status FROM workshop_contracts "
            "WHERE course_id = $1 AND status != 'voided'",
            course["id"],
        )
        if existing:
            raise ValueError(
                f"an active contract already exists for this workshop "
                f"(id={existing['id']}, status={existing['status']}). "
                "Void it first if you need to re-prepare."
            )

        # 3. Build prefilled_data + effective_date (= workshop start date)
        eff_date = (course["starts_at"].date() if course["starts_at"] else date.today())
        prefilled = guest_workshop_v1.prefill(
            course=dict(course),
            sessions=[dict(s) for s in sessions],
            guest=dict(guest),
            comp=compensation_input,
        )

        # 4. Mint signing token, expiry
        token = secrets.token_hex(32)  # 64 hex chars
        expires = datetime.now(timezone.utc) + timedelta(days=SIGNING_TOKEN_TTL_DAYS)

        row = await db.fetchrow(
            """
            INSERT INTO workshop_contracts (
                course_id, guest_instructor_id, template_version, status,
                signing_token, signing_token_expires_at,
                effective_date, prefilled_data
            ) VALUES ($1, $2, $3, 'prepared', $4, $5, $6, $7::jsonb)
            RETURNING *
            """,
            course["id"], guest["id"], guest_workshop_v1.VERSION,
            token, expires, eff_date,
            __import__("json").dumps(prefilled, default=str),
        )

    logger.info(
        "workshop_contract.prepared",
        contract_id=str(row["id"]),
        course_id=str(course["id"]),
        guest_instructor_id=str(guest["id"]),
        prepared_by=prepared_by_user_id,
    )
    return _to_dict(row)




async def _resolve_tenant_for_token(token: str) -> tuple[str, str, str] | None:
    """Find which tenant schema has a workshop_contracts row matching this
    signing token. Returns (organization_id, schema_name, slug) or None.

    The signing_token is CHAR(64) random hex (secrets.token_hex(32)) — the
    space is large enough that collisions across tenants are astronomically
    unlikely. We iterate active orgs, run a single SELECT 1 against each
    tenant schema's workshop_contracts, return on first hit."""
    from app.db.session import get_global_db
    async with get_global_db() as gdb:
        orgs = await gdb.fetch(
            "SELECT id, slug, schema_name FROM af_global.organizations "
            "WHERE status = 'active'"
        )
        for org in orgs:
            row = await gdb.fetchval(
                f"SELECT 1 FROM {org['schema_name']}.workshop_contracts "
                f"WHERE signing_token = $1 LIMIT 1",
                token,
            )
            if row:
                return (str(org["id"]), org["schema_name"], org["slug"])
    return None


async def _resolve_tenant_for_contract_id(contract_id: str) -> tuple[str, str, str] | None:
    """Same as _resolve_tenant_for_token but keyed by workshop_contracts.id.
    Used by post-sign background tasks that only have the contract id."""
    from app.db.session import get_global_db
    async with get_global_db() as gdb:
        orgs = await gdb.fetch(
            "SELECT id, slug, schema_name FROM af_global.organizations "
            "WHERE status = 'active'"
        )
        for org in orgs:
            row = await gdb.fetchval(
                f"SELECT 1 FROM {org['schema_name']}.workshop_contracts "
                f"WHERE id = $1::uuid LIMIT 1",
                contract_id,
            )
            if row:
                return (str(org["id"]), org["schema_name"], org["slug"])
    return None


async def _with_tenant_for_contract_id(contract_id: str, fn):
    """Resolve tenant by contract id, set context, run fn, clear context."""
    from app.core.tenant_context import set_tenant_context, clear_tenant_context
    resolved = await _resolve_tenant_for_contract_id(contract_id)
    if not resolved:
        return None
    org_id, schema_name, slug = resolved
    set_tenant_context(organization_id=org_id, schema_name=schema_name, slug=slug)
    try:
        return await fn()
    finally:
        clear_tenant_context()


async def _with_tenant_for_token(token: str, fn):
    """Helper: resolve the tenant for a token, set tenant context, run fn,
    clear context. Returns whatever fn returns, or None if token unknown."""
    from app.core.tenant_context import set_tenant_context, clear_tenant_context
    resolved = await _resolve_tenant_for_token(token)
    if not resolved:
        return None
    org_id, schema_name, slug = resolved
    set_tenant_context(organization_id=org_id, schema_name=schema_name, slug=slug)
    try:
        return await fn()
    finally:
        clear_tenant_context()



async def get_contract_for_signing(token: str) -> dict | None:
    """PUBLIC (token-only): fetch the data needed to render the sign page.
    Marks first_viewed_at / last_viewed_at / view_count. Does NOT return PDF
    or any sensitive admin-only data.

    Public endpoint = no JWT = no TenantMiddleware. Resolve tenant by
    scanning org schemas for the token first."""
    return await _with_tenant_for_token(token, lambda: _get_contract_for_signing_inner(token))


async def _get_contract_for_signing_inner(token: str) -> dict | None:
    async with get_tenant_db() as db:
        row = await db.fetchrow(
            """
            UPDATE workshop_contracts
               SET first_viewed_at = COALESCE(first_viewed_at, NOW()),
                   last_viewed_at = NOW(),
                   view_count = view_count + 1,
                   status = CASE WHEN status = 'sent' THEN 'viewed' ELSE status END,
                   updated_at = NOW()
             WHERE signing_token = $1
               AND signing_token_expires_at > NOW()
               AND status IN ('sent', 'viewed')
            RETURNING *
            """,
            token,
        )
    if not row:
        return None
    # asyncpg returns JSONB as raw strings; parse so render_html sees a dict.
    import json as _json
    pf = row['prefilled_data']
    if isinstance(pf, str):
        pf = _json.loads(pf) if pf else {}
    contract_html = guest_workshop_v1.render_html(
        prefilled=pf,
        effective_date=row['effective_date'],
        studio_ack=guest_workshop_v1.studio_acknowledgment(row['created_at']),
    )
    return {
        "id": str(row["id"]),
        "status": row["status"],
        "template_version": row["template_version"],
        "effective_date": row["effective_date"].isoformat(),
        "prefilled_data": pf,
        "instructor_field_schema": guest_workshop_v1.INSTRUCTOR_FIELDS,
        "studio_acknowledgment": guest_workshop_v1.studio_acknowledgment(row["created_at"]),
        "contract_html": contract_html,
    }


async def sign_contract(
    token: str,
    instructor_data: dict,
    signature_image_data_url: str,
    signed_ip: str,
    signed_user_agent: str,
    instructor_photo_data_url: str | None = None,
    workshop_flyer_data_url: str | None = None,
) -> dict:
    """Public-endpoint wrapper: resolve tenant from the token first, then
    delegate to the inner implementation under that tenant context."""
    result = await _with_tenant_for_token(
        token,
        lambda: _sign_contract_inner(
            token, instructor_data, signature_image_data_url,
            signed_ip, signed_user_agent,
            instructor_photo_data_url, workshop_flyer_data_url,
        ),
    )
    if result is None:
        raise ValueError("contract not found, expired, or already signed")
    return result


async def _sign_contract_inner(
    token: str,
    instructor_data: dict,
    signature_image_data_url: str,
    signed_ip: str,
    signed_user_agent: str,
    instructor_photo_data_url: str | None = None,
    workshop_flyer_data_url: str | None = None,
) -> dict:
    """PUBLIC (token-only): instructor submits filled fields + signature +
    (per Don's design) instructor photo + workshop flyer + the marketing
    section. We:
      1. Validate required fields + signature.
      2. Decode the signature + the 2 marketing images.
      3. Open a transaction.
      4. Encrypt + write SSN/EIN to guest_instructors.tax_id_encrypted.
      5. Copy instructor photo to guest_instructors.photo_data + photo_mime.
      6. Copy workshop flyer to courses.flyer_image_data + flyer_image_mime.
      7. Overwrite courses.description with the guest-supplied
         workshop_description (the marketing copy).
      8. Render the COMBINED details+contract HTML → PDF with
         weasyprint and store it on signed_combined_pdf.
      9. Mark contract signed, persist all the audit data.
     10. Return the row (without bytea blobs) so the caller can fire
         the receipt emails (which now attach the combined PDF)."""
    # Validate required fields per the schema. Image fields ride in their
    # own top-level data-URL params, NOT in instructor_data, so they must be
    # checked against those args rather than the instructor_data dict.
    image_arg_for = {
        "instructor_photo": instructor_photo_data_url,
        "workshop_flyer":  workshop_flyer_data_url,
    }
    missing = []
    for f in guest_workshop_v1.INSTRUCTOR_FIELDS:
        if not f.get("required"):
            continue
        name = f["name"]
        if f.get("type") == "image":
            v = image_arg_for.get(name)
            if not v or not isinstance(v, str) or not v.startswith("data:image/"):
                missing.append(name)
        else:
            if not instructor_data.get(name):
                missing.append(name)
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")
    if not signature_image_data_url or not signature_image_data_url.startswith("data:image/"):
        raise ValueError("signature_image_data_url must be a data:image/* URL")

    # Decode signature
    sig_bytes, _ = _decode_data_url(signature_image_data_url, max_size=500_000)

    # Decode optional images, then shrink them so embedded PDFs stay
    # under a few hundred KB instead of 5 MB phone-camera uploads.
    photo_bytes, photo_mime = (None, None)
    if instructor_photo_data_url:
        photo_bytes, photo_mime = _decode_data_url(instructor_photo_data_url, max_size=15_000_000)
        photo_bytes, photo_mime = _shrink_image(photo_bytes, photo_mime, max_dim=900, quality=78)
        # Refresh the data URL so the PDF renderer embeds the shrunk version
        instructor_photo_data_url = (
            f"data:{photo_mime};base64,{base64.b64encode(photo_bytes).decode('ascii')}"
        )
    flyer_bytes, flyer_mime = (None, None)
    if workshop_flyer_data_url:
        flyer_bytes, flyer_mime = _decode_data_url(workshop_flyer_data_url, max_size=15_000_000)
        flyer_bytes, flyer_mime = _shrink_image(flyer_bytes, flyer_mime, max_dim=1400, quality=78)
        workshop_flyer_data_url = (
            f"data:{flyer_mime};base64,{base64.b64encode(flyer_bytes).decode('ascii')}"
        )

    # Defer imports
    from app.services.contracts.pdf_renderer import render_contract_pdf
    from app.utils.encryption import encrypt_credential

    async with get_tenant_db() as db:
        row = await db.fetchrow(
            """SELECT * FROM workshop_contracts
                WHERE signing_token = $1
                  AND signing_token_expires_at > NOW()
                  AND status IN ('sent', 'viewed')""",
            token,
        )
        if not row:
            raise ValueError("contract not found, expired, or already signed")

        signed_at = datetime.now(timezone.utc)

        # Encrypt + write SSN/EIN to guest_instructors (NOT this row)
        tax_id_raw = (instructor_data.get("tax_id") or "").strip()
        if tax_id_raw:
            tax_id_enc = await encrypt_credential(db, tax_id_raw)
            await db.execute(
                "UPDATE guest_instructors SET tax_id_encrypted = $1, updated_at = NOW() WHERE id = $2",
                tax_id_enc, row["guest_instructor_id"],
            )

        # Strip tax_id from JSONB persisted on the contract row.
        clean_data = {k: v for k, v in instructor_data.items() if k != "tax_id"}

        # Copy contact info corrections + photo to guest_instructors
        await db.execute(
            """UPDATE guest_instructors SET
                 name = COALESCE($1, name),
                 email = COALESCE($2, email),
                 phone = COALESCE($3, phone),
                 address_line1 = COALESCE($4, address_line1),
                 photo_data = COALESCE($5, photo_data),
                 photo_mime = COALESCE($6, photo_mime),
                 updated_at = NOW()
               WHERE id = $7""",
            clean_data.get("legal_name") or clean_data.get("printed_name"),
            clean_data.get("email"),
            clean_data.get("phone"),
            clean_data.get("address"),
            photo_bytes, photo_mime,
            row["guest_instructor_id"],
        )

        # Sync workshop description + flyer to courses (the marketing-facing copy)
        marketing_desc = (clean_data.get("workshop_description") or "").strip() or None
        await db.execute(
            """UPDATE courses SET
                 description = COALESCE($1, description),
                 flyer_image_data = COALESCE($2, flyer_image_data),
                 flyer_image_mime = COALESCE($3, flyer_image_mime),
                 updated_at = NOW()
               WHERE id = $4""",
            marketing_desc, flyer_bytes, flyer_mime, row["course_id"],
        )

        # Render combined details+contract PDF (this is the artifact we email).
        # asyncpg returns JSONB as a raw string unless a codec is registered;
        # parse defensively so render_html sees a dict.
        import json as _json
        prefilled = row["prefilled_data"]
        if isinstance(prefilled, str):
            prefilled = _json.loads(prefilled) if prefilled else {}
        studio_ack = guest_workshop_v1.studio_acknowledgment(row["created_at"])
        combined_html = guest_workshop_v1.render_html(
            prefilled=prefilled,
            instructor_data=clean_data,
            signature_image_data_url=signature_image_data_url,
            signed_at=signed_at,
            signed_ip=signed_ip,
            studio_ack=studio_ack,
            effective_date=row["effective_date"],
            instructor_photo_data_url=instructor_photo_data_url,
            workshop_flyer_data_url=workshop_flyer_data_url,
        )
        combined_pdf = await render_contract_pdf(combined_html)

        updated = await db.fetchrow(
            """UPDATE workshop_contracts SET
                 status = 'signed',
                 instructor_data = $1::jsonb,
                 signature_image = $2,
                 instructor_photo_data = $3,
                 instructor_photo_mime = $4,
                 workshop_flyer_data = $5,
                 workshop_flyer_mime = $6,
                 signed_at = $7,
                 signed_ip = $8,
                 signed_user_agent = $9,
                 signed_combined_pdf = $10,
                 signed_pdf = $10,
                 updated_at = NOW()
               WHERE id = $11
               RETURNING id, status, signed_at""",
            __import__("json").dumps(clean_data, default=str),
            sig_bytes,
            photo_bytes, photo_mime,
            flyer_bytes, flyer_mime,
            signed_at, signed_ip, signed_user_agent,
            combined_pdf,
            row["id"],
        )

    logger.info(
        "workshop_contract.signed",
        contract_id=str(updated["id"]),
        guest_instructor_id=str(row["guest_instructor_id"]),
        ip=signed_ip,
        photo_synced=photo_bytes is not None,
        flyer_synced=flyer_bytes is not None,
    )
    return {
        "id": str(updated["id"]),
        "status": updated["status"],
        "signed_at": updated["signed_at"].isoformat(),
    }


async def mark_email_sent(contract_id: str) -> None:
    """Called by the email-sender after the initial signing-link email is delivered."""
    async with get_tenant_db() as db:
        await db.execute(
            """UPDATE workshop_contracts
                  SET status = CASE WHEN status = 'prepared' THEN 'sent' ELSE status END,
                      email_sent_at = COALESCE(email_sent_at, NOW()),
                      updated_at = NOW()
                WHERE id = $1""",
            uuid.UUID(contract_id),
        )


async def void_contract(contract_id: str, voided_by_user_id: str, reason: str) -> dict:
    async with get_tenant_db() as db:
        row = await db.fetchrow(
            """UPDATE workshop_contracts SET
                 status = 'voided',
                 voided_at = NOW(),
                 voided_by = $1,
                 void_reason = $2,
                 signing_token = NULL,
                 updated_at = NOW()
               WHERE id = $3 AND status != 'signed'
               RETURNING id, status""",
            uuid.UUID(voided_by_user_id), reason[:500] if reason else None,
            uuid.UUID(contract_id),
        )
    if not row:
        raise ValueError("contract not found or already signed (signed contracts cannot be voided)")
    return {"id": str(row["id"]), "status": row["status"]}


async def get_contract_pdf(contract_id: str) -> tuple[bytes, str] | None:
    """Returns (pdf_bytes, filename) for the signed PDF, or None if unsigned."""
    async with get_tenant_db() as db:
        row = await db.fetchrow(
            """SELECT id, signed_pdf, signed_at,
                      prefilled_data->'workshop'->>'title' AS title,
                      effective_date
                 FROM workshop_contracts WHERE id = $1""",
            uuid.UUID(contract_id),
        )
    if not row or not row["signed_pdf"]:
        return None
    safe_title = "".join(c if c.isalnum() or c in "-_ " else "_" for c in (row["title"] or "workshop"))[:60].strip()
    return bytes(row["signed_pdf"]), f"contract_{safe_title}_{row['effective_date']}.pdf"


async def get_contract_admin(contract_id: str) -> dict | None:
    async with get_tenant_db() as db:
        row = await db.fetchrow(
            "SELECT * FROM workshop_contracts WHERE id = $1", uuid.UUID(contract_id),
        )
    return _to_dict(row) if row else None


async def list_contracts_for_course(course_id: str) -> list[dict]:
    async with get_tenant_db() as db:
        rows = await db.fetch(
            "SELECT * FROM workshop_contracts WHERE course_id = $1 ORDER BY created_at DESC",
            uuid.UUID(course_id),
        )
    return [_to_dict(r) for r in rows]


async def list_pending_reminders(min_age_days: int = 7) -> list[dict]:
    """Used by the celery beat task: contracts that were emailed >= 7d ago,
    not signed, no reminder yet."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=min_age_days)
    async with get_tenant_db() as db:
        rows = await db.fetch(
            """SELECT id, course_id, guest_instructor_id, signing_token, prefilled_data
                 FROM workshop_contracts
                WHERE status IN ('sent', 'viewed')
                  AND email_sent_at IS NOT NULL
                  AND email_sent_at <= $1
                  AND reminder_sent_at IS NULL
                  AND signing_token_expires_at > NOW()""",
            cutoff,
        )
    return [{"id": str(r["id"]),
             "course_id": str(r["course_id"]),
             "guest_instructor_id": str(r["guest_instructor_id"]),
             "signing_token": r["signing_token"],
             "prefilled_data": r["prefilled_data"]} for r in rows]


async def mark_reminder_sent(contract_id: str) -> None:
    async with get_tenant_db() as db:
        await db.execute(
            "UPDATE workshop_contracts SET reminder_sent_at = NOW(), updated_at = NOW() WHERE id = $1",
            uuid.UUID(contract_id),
        )


def _to_dict(row) -> dict:
    """Convert a workshop_contracts asyncpg.Record to a JSON-safe dict
    (drops bytea blobs, keeps everything else)."""
    if row is None:
        return None
    d = dict(row)
    d["id"] = str(d["id"])
    d["course_id"] = str(d["course_id"])
    d["guest_instructor_id"] = str(d["guest_instructor_id"])
    if d.get("voided_by"):
        d["voided_by"] = str(d["voided_by"])
    # Strip blobs
    d.pop("signature_image", None)
    d.pop("signed_pdf", None)
    # Convert datetimes to ISO
    for k in ("signing_token_expires_at", "signed_at", "email_sent_at",
              "first_viewed_at", "last_viewed_at", "reminder_sent_at",
              "voided_at", "created_at", "updated_at"):
        if d.get(k):
            d[k] = d[k].isoformat()
    if d.get("effective_date"):
        d["effective_date"] = d["effective_date"].isoformat()
    return d


def signing_url(token: str, base_url: str = "https://your-domain.com") -> str:
    return f"{base_url.rstrip('/')}/contracts/sign/{token}"



async def create_guest_workshop(
    *,
    workshop_name: str,
    sessions: list[dict],  # [{'starts_at': dt, 'ends_at': dt, 'location'?, 'is_virtual'?, 'title'?}, ...]
    workshop_cost_cents: int,
    instructor_share_percent: int,  # 0-100, share TO the instructor
    location: str | None,
    capacity: int | None,
    min_enrollment: int | None,
    # Either pick existing OR create new:
    guest_instructor_id: str | None = None,
    new_guest_name: str | None = None,
    new_guest_email: str | None = None,
    new_guest_phone: str | None = None,
    prepared_by_user_id: str | None = None,
    allow_duplicate: bool = False,
) -> dict:
    """One-shot endpoint backing the 'Create Guest Workshop' modal.
    Creates (or reuses) the guest_instructor row, creates a courses row
    (type='workshop'), creates one course_session for the date/time, and
    prepares the contract — all in a single transaction. Returns
    {course_id, guest_instructor_id, contract: {...}}."""
    if (instructor_share_percent < 0) or (instructor_share_percent > 100):
        raise ValueError("instructor_share_percent must be 0-100")
    if not (guest_instructor_id or new_guest_name):
        raise ValueError("must pass either guest_instructor_id or new_guest_name")

    # Duplicate guard: refuse if an active workshop for the same guest exists at
    # the same first-session start time. Caller must pass allow_duplicate=True
    # to override (e.g. genuinely-repeating series on the same date). Skipped
    # entirely when the guest is brand-new (no guest_instructor_id yet).
    if guest_instructor_id and sessions and not allow_duplicate:
        sorted_sessions_for_check = sorted(sessions, key=lambda s: s["starts_at"])
        first_start = sorted_sessions_for_check[0]["starts_at"]
        async with get_tenant_db() as db:
            existing = await db.fetchrow(
                """
                SELECT c.id AS course_id, c.title, wc.status AS contract_status
                FROM courses c
                LEFT JOIN workshop_contracts wc ON wc.course_id = c.id
                                              AND wc.status NOT IN ('voided')
                WHERE c.guest_instructor_id = $1
                  AND c.starts_at = $2
                  AND c.status NOT IN ('cancelled', 'completed')
                LIMIT 1
                """,
                uuid.UUID(guest_instructor_id), first_start,
            )
            if existing:
                raise ValueError(
                    f"a workshop for this guest instructor at this start time already "
                    f"exists (course={existing['course_id']}, contract status="
                    f"{existing['contract_status'] or 'no contract'}). Pass "
                    f"allow_duplicate=true to create anyway."
                )

    async with get_tenant_db() as db:
        # 1. Resolve / create guest_instructor
        if guest_instructor_id:
            guest = await db.fetchrow(
                "SELECT id, name, email, phone, revenue_share_percent_to_guest "
                "FROM guest_instructors WHERE id = $1 AND is_active = TRUE",
                uuid.UUID(guest_instructor_id),
            )
            if not guest:
                raise ValueError(f"guest_instructor not found: {guest_instructor_id}")
        else:
            existing = None
            if new_guest_email:
                existing = await db.fetchrow(
                    "SELECT id FROM guest_instructors WHERE LOWER(email) = LOWER($1) AND is_active = TRUE",
                    new_guest_email,
                )
            if existing:
                raise ValueError(
                    f"a guest instructor with email {new_guest_email} already exists "
                    f"(id={existing['id']}). Pick them from the dropdown instead."
                )
            guest = await db.fetchrow(
                """INSERT INTO guest_instructors
                     (name, email, phone, revenue_share_percent_to_guest, is_active)
                   VALUES ($1, $2, $3, $4, TRUE)
                   RETURNING id, name, email, phone, revenue_share_percent_to_guest""",
                new_guest_name.strip(),
                (new_guest_email or "").strip() or None,
                (new_guest_phone or "").strip() or None,
                instructor_share_percent,
            )

        # 2. Create the course (workshop). Course-level starts_at/ends_at
        #    span the full series: first session's start, last session's end.
        if not sessions:
            raise ValueError("at least one session is required")
        sorted_sessions = sorted(sessions, key=lambda s: s["starts_at"])
        first_session = sorted_sessions[0]
        last_session = sorted_sessions[-1]
        course = await db.fetchrow(
            """INSERT INTO courses
                 (title, type, instructor_id, guest_instructor_id, price_cents,
                  capacity, min_enrollment, location, starts_at, ends_at, status)
               VALUES ($1, 'workshop', NULL, $2, $3, $4, $5, $6, $7, $8, 'draft')
               RETURNING id, title, starts_at, ends_at""",
            workshop_name.strip(), guest["id"], workshop_cost_cents,
            capacity, min_enrollment, location,
            first_session["starts_at"], last_session["ends_at"],
        )

        # 3. Create one course_sessions row per session
        for idx, s in enumerate(sorted_sessions, start=1):
            await db.execute(
                """INSERT INTO course_sessions
                     (course_id, session_number, title, starts_at, ends_at,
                      location, is_virtual)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                course["id"], idx, s.get("title"),
                s["starts_at"], s["ends_at"],
                s.get("location") or location,
                bool(s.get("is_virtual")),
            )

    # 4. Prepare the contract — this also fires the email background task
    #    via the calling endpoint (we just return the contract dict here).
    studio_share = 100 - instructor_share_percent
    comp = {
        "option": "revenue_share",
        "revenue_share_percent_to_instructor": instructor_share_percent,
        "expense_reimbursements": "None",
        "payment_method": "Stripe Connect (direct deposit)",
        "payment_timing_business_days": 15,
        "studio_supplied_materials": "Workshop space, sound system, standard studio props (mats, blocks, straps, bolsters), cleaning and preparation of the space.",
    }
    contract = await prepare_contract_for_workshop(
        course_id=str(course["id"]),
        compensation_input=comp,
        prepared_by_user_id=prepared_by_user_id or "system",
    )

    return {
        "course_id": str(course["id"]),
        "course_title": course["title"],
        "guest_instructor_id": str(guest["id"]),
        "guest_instructor_name": guest["name"],
        "instructor_share_percent": instructor_share_percent,
        "studio_share_percent": studio_share,
        "contract": contract,
    }


async def get_combined_pdf(contract_id: str) -> tuple[bytes, str] | None:
    """Returns (combined_pdf_bytes, filename) for the signed combined-details
    PDF used in receipt emails. Falls back to signed_pdf if the combined
    column happens to be NULL."""
    async with get_tenant_db() as db:
        row = await db.fetchrow(
            """SELECT id, signed_combined_pdf, signed_pdf, signed_at,
                      prefilled_data->'workshop'->>'title' AS title,
                      effective_date
                 FROM workshop_contracts WHERE id = $1""",
            uuid.UUID(contract_id),
        )
    if not row:
        return None
    blob = row["signed_combined_pdf"] or row["signed_pdf"]
    if not blob:
        return None
    safe_title = "".join(c if c.isalnum() or c in "-_ " else "_" for c in (row["title"] or "workshop"))[:60].strip()
    return bytes(blob), f"workshop_contract_{safe_title}_{row['effective_date']}.pdf"
