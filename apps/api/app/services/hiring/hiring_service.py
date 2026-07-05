"""AuraFlow — Hiring / Applicant-Tracking Service

Job applications submitted from a studio's branded site (api-key), the
in-app review pipeline, and the one-click "hire" automation that creates the
instructor/staff record in the right location.

Operates within the tenant context already set by the caller:
- public submit/upload  → set by api-key auth (get_api_key_context)
- internal review/hire   → set from the staff JWT's org

The hire automation mirrors InstructorService.create_instructor so a hired
applicant ends up identical to a manually-created instructor/staff member.
"""
import json
import uuid
from datetime import date

from app.core.logging import logger
from app.core.security import hash_password
from app.db.session import get_tenant_db, get_global_db
from app.services.permissions import PermissionService


# Columns accepted from a public application submission.
_APPLICATION_COLS = [
    "first_name", "last_name", "email", "phone",
    "address_line1", "address_line2", "city", "state", "postal_code",
    "position_type", "position_title", "employment_type", "availability",
    "earliest_start_date", "desired_pay_text",
    "authorized_to_work", "over_18",
    "years_experience", "experience_seniors", "experience_injuries",
    "experience_pain", "specialties", "work_history",
    "certifications", "yoga_alliance_number", "yoga_alliance_level",
    "cpr_first_aid", "liability_insurance",
    "references", "cover_letter", "hear_about_us", "attestation",
]

# JSONB columns — serialized on write.
_JSON_COLS = {"work_history", "certifications", "references"}

# DATE columns — ISO strings from the API must become date objects for asyncpg.
_DATE_COLS = {"earliest_start_date"}


def _to_date(v):
    """Coerce an ISO date string to a datetime.date (asyncpg needs a date, not str)."""
    if isinstance(v, str):
        return date.fromisoformat(v)
    return v

_VALID_STATUSES = {
    "new", "reviewed", "shortlisted", "interviewed", "offer", "hired", "rejected",
}

MAX_DOCUMENT_BYTES = 10 * 1024 * 1024  # 10 MB
_ALLOWED_DOC_TYPES = {"resume", "certification", "insurance", "yoga_alliance", "other"}
_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg", "image/png",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _app_to_dict(row) -> dict:
    if row is None:
        return None
    d = dict(row)
    # asyncpg returns JSONB as a raw string here — parse to real arrays so the
    # API returns lists (the frontend does .map/.length on them).
    for k in _JSON_COLS:
        v = d.get(k)
        if isinstance(v, str):
            try:
                d[k] = json.loads(v)
            except (ValueError, TypeError):
                d[k] = []
    for k in ("created_at", "updated_at", "reviewed_at", "hired_at"):
        if d.get(k) is not None:
            d[k] = d[k].isoformat()
    if d.get("earliest_start_date") is not None:
        d["earliest_start_date"] = d["earliest_start_date"].isoformat()
    for k in ("id", "assigned_reviewer_id", "reviewed_by", "hired_user_id", "hired_studio_id"):
        if d.get(k) is not None:
            d[k] = str(d[k])
    return d


async def _write_event(db, application_id, event_type, *, from_status=None,
                       to_status=None, note=None, actor_user_id=None) -> None:
    await db.execute(
        """
        INSERT INTO job_application_events
            (id, application_id, event_type, from_status, to_status, note, actor_user_id)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        str(uuid.uuid4()), application_id, event_type, from_status, to_status,
        note, actor_user_id,
    )


# ── Public: submit + documents ─────────────────────────────────────────────

async def create_application(data: dict) -> dict:
    """Insert a new job application (public submission). Returns the row."""
    app_id = str(uuid.uuid4())
    cols = ["id"]
    vals = [app_id]
    for c in _APPLICATION_COLS:
        if c in data and data[c] is not None:
            cols.append(c)
            v = data[c]
            if c in _JSON_COLS:
                v = json.dumps(v)
            elif c in _DATE_COLS:
                v = _to_date(v)
            vals.append(v)
    placeholders = ", ".join(f"${i + 1}" for i in range(len(vals)))
    collist = ", ".join(f'"{c}"' if c == "references" else c for c in cols)
    async with get_tenant_db() as db:
        async with db.transaction():
            await db.execute(
                f"INSERT INTO job_applications ({collist}) VALUES ({placeholders})",
                *vals,
            )
            await _write_event(db, app_id, "created", to_status="new")
            row = await db.fetchrow("SELECT * FROM job_applications WHERE id = $1", app_id)
    logger.info("Job application submitted", application_id=app_id,
                position=data.get("position_type"))
    return _app_to_dict(row)


async def add_document(application_id: str, doc_type: str, filename: str,
                       content_type: str, file_data: bytes) -> dict:
    """Attach an uploaded document (resume/cert/etc.) to an application.

    Raises ValueError on validation failure (bad type / too big / unknown app).
    """
    if doc_type not in _ALLOWED_DOC_TYPES:
        raise ValueError(f"Invalid doc_type. Allowed: {sorted(_ALLOWED_DOC_TYPES)}")
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise ValueError("Unsupported file type. Allowed: PDF, JPG, PNG, DOC, DOCX.")
    if not file_data:
        raise ValueError("Empty file.")
    if len(file_data) > MAX_DOCUMENT_BYTES:
        raise ValueError(f"File too large (max {MAX_DOCUMENT_BYTES // (1024 * 1024)} MB).")

    doc_id = str(uuid.uuid4())
    async with get_tenant_db() as db:
        exists = await db.fetchval(
            "SELECT 1 FROM job_applications WHERE id = $1", application_id,
        )
        if not exists:
            raise ValueError("Application not found.")
        async with db.transaction():
            await db.execute(
                """
                INSERT INTO job_application_documents
                    (id, application_id, doc_type, filename, content_type, file_data, size_bytes)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                doc_id, application_id, doc_type, filename, content_type,
                file_data, len(file_data),
            )
            await _write_event(db, application_id, "document_uploaded",
                               note=f"{doc_type}: {filename}")
    return {
        "id": doc_id, "application_id": application_id, "doc_type": doc_type,
        "filename": filename, "content_type": content_type, "size_bytes": len(file_data),
    }


# ── Internal: list / detail / documents ────────────────────────────────────

async def list_applications(status: str | None = None, q: str | None = None,
                            reviewer_id: str | None = None,
                            limit: int = 50, offset: int = 0) -> list[dict]:
    where = []
    params: list = []
    if status:
        params.append(status)
        where.append(f"status = ${len(params)}")
    if reviewer_id:
        params.append(reviewer_id)
        where.append(f"assigned_reviewer_id = ${len(params)}")
    if q:
        params.append(f"%{q.lower()}%")
        i = len(params)
        where.append(f"(lower(first_name) LIKE ${i} OR lower(last_name) LIKE ${i} "
                     f"OR lower(email) LIKE ${i} OR lower(coalesce(position_title,'')) LIKE ${i})")
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    params.append(limit)
    params.append(offset)
    async with get_tenant_db() as db:
        rows = await db.fetch(
            f"""
            SELECT id, first_name, last_name, email, phone, position_type,
                   position_title, status, rating, assigned_reviewer_id,
                   reviewed_at, hired_at, created_at,
                   (SELECT COUNT(*) FROM job_application_documents d
                    WHERE d.application_id = job_applications.id) AS document_count
            FROM job_applications
            {clause}
            ORDER BY created_at DESC
            LIMIT ${len(params) - 1} OFFSET ${len(params)}
            """,
            *params,
        )
    return [_app_to_dict(r) for r in rows]


async def get_application(application_id: str) -> dict | None:
    async with get_tenant_db() as db:
        row = await db.fetchrow(
            "SELECT * FROM job_applications WHERE id = $1", application_id,
        )
        if not row:
            return None
        docs = await db.fetch(
            """SELECT id, doc_type, filename, content_type, size_bytes, uploaded_at
               FROM job_application_documents WHERE application_id = $1
               ORDER BY uploaded_at""",
            application_id,
        )
        events = await db.fetch(
            """SELECT id, event_type, from_status, to_status, note, actor_user_id, created_at
               FROM job_application_events WHERE application_id = $1
               ORDER BY created_at""",
            application_id,
        )
    result = _app_to_dict(row)
    result["documents"] = [
        {
            "id": str(d["id"]), "doc_type": d["doc_type"], "filename": d["filename"],
            "content_type": d["content_type"], "size_bytes": d["size_bytes"],
            "uploaded_at": d["uploaded_at"].isoformat(),
        }
        for d in docs
    ]
    result["events"] = [
        {
            "id": str(e["id"]), "event_type": e["event_type"],
            "from_status": e["from_status"], "to_status": e["to_status"],
            "note": e["note"],
            "actor_user_id": str(e["actor_user_id"]) if e["actor_user_id"] else None,
            "created_at": e["created_at"].isoformat(),
        }
        for e in events
    ]
    return result


async def get_document(application_id: str, doc_id: str):
    """Return (file_data: bytes, filename, content_type) or None."""
    async with get_tenant_db() as db:
        row = await db.fetchrow(
            """SELECT filename, content_type, file_data
               FROM job_application_documents
               WHERE id = $1 AND application_id = $2""",
            doc_id, application_id,
        )
    if not row:
        return None
    return bytes(row["file_data"]), row["filename"], row["content_type"]


# ── Internal: update / notes ───────────────────────────────────────────────

async def update_application(application_id: str, actor_user_id: str | None, *,
                             status: str | None = None, rating: int | None = None,
                             assigned_reviewer_id: str | None = None,
                             rejection_reason: str | None = None) -> dict | None:
    if status is not None and status not in _VALID_STATUSES:
        raise ValueError(f"Invalid status. Allowed: {sorted(_VALID_STATUSES)}")

    async with get_tenant_db() as db:
        current = await db.fetchrow(
            "SELECT status, rating FROM job_applications WHERE id = $1", application_id,
        )
        if not current:
            return None

        sets = ["updated_at = NOW()"]
        params: list = []

        if status is not None and status != current["status"]:
            params.append(status)
            sets.append(f"status = ${len(params)}")
            # First move away from 'new' stamps reviewed_by/at.
            if current["status"] == "new":
                params.append(actor_user_id)
                sets.append(f"reviewed_by = ${len(params)}")
                sets.append("reviewed_at = NOW()")
        if rating is not None:
            params.append(rating)
            sets.append(f"rating = ${len(params)}")
        if assigned_reviewer_id is not None:
            params.append(assigned_reviewer_id)
            sets.append(f"assigned_reviewer_id = ${len(params)}")
        if rejection_reason is not None:
            params.append(rejection_reason)
            sets.append(f"rejection_reason = ${len(params)}")

        params.append(application_id)
        async with db.transaction():
            await db.execute(
                f"UPDATE job_applications SET {', '.join(sets)} WHERE id = ${len(params)}",
                *params,
            )
            if status is not None and status != current["status"]:
                await _write_event(db, application_id, "status_changed",
                                   from_status=current["status"], to_status=status,
                                   actor_user_id=actor_user_id)
            if rating is not None and rating != current["rating"]:
                await _write_event(db, application_id, "rated",
                                   note=f"rating={rating}", actor_user_id=actor_user_id)
            row = await db.fetchrow("SELECT * FROM job_applications WHERE id = $1", application_id)
    return _app_to_dict(row)


async def add_note(application_id: str, actor_user_id: str | None, note: str) -> dict | None:
    async with get_tenant_db() as db:
        exists = await db.fetchval(
            "SELECT 1 FROM job_applications WHERE id = $1", application_id,
        )
        if not exists:
            return None
        await _write_event(db, application_id, "note", note=note, actor_user_id=actor_user_id)
    return {"application_id": application_id, "note": note}


# ── Internal: hire automation ──────────────────────────────────────────────

async def hire_applicant(application_id: str, actor_user_id: str | None,
                         org_id: str, org_slug: str, *,
                         role: str, studio_id: str | None,
                         pay_rate_cents: int | None = None,
                         pay_type: str = "per_class",
                         tax_classification: str = "1099",
                         title: str | None = None, department: str | None = None,
                         hire_date: str | None = None) -> dict:
    """Create the staff/instructor record from an application and mark it hired.

    Mirrors InstructorService.create_instructor + studio assignment so a hired
    applicant is identical to a manually created one. Returns
    {user_id, instructor_id?, role, studio_id}.
    """
    if role not in ("instructor", "front_desk", "admin"):
        raise ValueError("role must be instructor, front_desk, or admin")

    async with get_tenant_db() as tdb:
        app = await tdb.fetchrow(
            "SELECT * FROM job_applications WHERE id = $1", application_id,
        )
    if not app:
        raise ValueError("Application not found.")
    if app["status"] == "hired" and app["hired_user_id"]:
        raise ValueError("Applicant already hired.")

    email = (app["email"] or "").strip().lower()
    if not email:
        raise ValueError("Application has no email; cannot create an account.")
    first_name = app["first_name"]
    last_name = app["last_name"]

    # 1–3. Global user + org membership + default permissions.
    pw_hash = hash_password("example-studio")
    async with get_global_db() as gdb:
        async with gdb.transaction():
            existing = await gdb.fetchrow(
                "SELECT id FROM af_global.users WHERE email = $1", email,
            )
            if existing:
                user_id = str(existing["id"])
            else:
                user_id = str(uuid.uuid4())
                await gdb.execute(
                    """
                    INSERT INTO af_global.users
                        (id, email, password_hash, first_name, last_name,
                         is_active, force_password_reset)
                    VALUES ($1, $2, $3, $4, $5, TRUE, TRUE)
                    """,
                    user_id, email, pw_hash, first_name, last_name,
                )
            await gdb.execute(
                """
                INSERT INTO af_global.organization_users
                    (id, organization_id, user_id, role, is_active, joined_at,
                     title, department, hire_date)
                VALUES ($1, $2, $3, $4, TRUE, NOW(), $5, $6, $7)
                ON CONFLICT (organization_id, user_id)
                DO UPDATE SET role = EXCLUDED.role, is_active = TRUE,
                              title = COALESCE(EXCLUDED.title, organization_users.title),
                              department = COALESCE(EXCLUDED.department, organization_users.department),
                              hire_date = COALESCE(EXCLUDED.hire_date, organization_users.hire_date)
                """,
                str(uuid.uuid4()), org_id, user_id, role, title, department,
                _to_date(hire_date),
            )
    await PermissionService().initialize_default_permissions(org_id, user_id, role)

    # 4. Instructor record (instructors only).
    instructor_id = None
    async with get_tenant_db() as tdb:
        async with tdb.transaction():
            if role == "instructor":
                from app.services.members.phone_hash import hash_phone
                instructor_id = str(uuid.uuid4())
                display_name = f"{first_name} {last_name}".strip()
                certs = app["certifications"] or []
                if isinstance(certs, str):
                    certs = json.loads(certs)
                cert_names = [c.get("name") for c in certs if isinstance(c, dict) and c.get("name")]
                await tdb.execute(
                    """
                    INSERT INTO instructors
                        (id, user_id, display_name, email, phone, phone_hash,
                         specialties, certifications, pay_rate_cents, pay_type,
                         tax_classification)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    """,
                    instructor_id, user_id, display_name, app["email"], app["phone"],
                    hash_phone(app["phone"]), list(app["specialties"] or []),
                    cert_names, pay_rate_cents, pay_type, tax_classification,
                )

            # 5. Studio assignment (per-location role).
            if studio_id:
                is_first = await tdb.fetchval(
                    "SELECT COUNT(*) = 0 FROM studio_user_roles WHERE user_id = $1", user_id,
                )
                await tdb.execute(
                    """
                    INSERT INTO studio_user_roles (id, studio_id, user_id, role, is_primary)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (studio_id, user_id)
                    DO UPDATE SET role = EXCLUDED.role
                    """,
                    str(uuid.uuid4()), studio_id, user_id, role, bool(is_first),
                )

            # 6. Mark application hired + event.
            await tdb.execute(
                """
                UPDATE job_applications
                   SET status = 'hired', hired_user_id = $1, hired_studio_id = $2,
                       hired_role = $3, hired_at = NOW(), updated_at = NOW()
                 WHERE id = $4
                """,
                user_id, studio_id, role, application_id,
            )
            await _write_event(tdb, application_id, "hired",
                               from_status=app["status"], to_status="hired",
                               note=f"Hired as {role}", actor_user_id=actor_user_id)

    logger.info("Applicant hired", application_id=application_id, user_id=user_id, role=role)
    return {
        "user_id": user_id,
        "instructor_id": instructor_id,
        "role": role,
        "studio_id": studio_id,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
    }
