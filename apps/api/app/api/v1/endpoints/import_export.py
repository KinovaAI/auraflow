"""AuraFlow — Import/Export Endpoints

CSV import with dry-run preview and actual import.
Supports flexible column mapping for exports from any studio platform.
Includes Stripe connector import for migrating payment data.
"""
from typing import Optional

from fastapi import APIRouter, Body, Depends, File, Form, UploadFile, HTTPException

from app.api.v1.dependencies.rbac import require_permission
from app.services.import_export.momoyoga_importer import MomoYogaImporter
from app.services.import_export.stripe_connector_importer import StripeConnectorImporter
from app.services.import_export.ai_importer import AIImporter

router = APIRouter()
importer = MomoYogaImporter()
stripe_importer = StripeConnectorImporter()
ai_importer = AIImporter()

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB
ALLOWED_CSV_CONTENT_TYPES = {"text/csv", "application/csv", "application/vnd.ms-excel"}
ALLOWED_CSV_EXTENSIONS = {".csv"}


def _validate_csv_file(file: UploadFile):
    """Validate that uploaded file is a CSV by extension and content type."""
    import os
    filename = file.filename or ""
    _, ext = os.path.splitext(filename.lower())
    if ext not in ALLOWED_CSV_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file extension '{ext}'. Only .csv files are accepted.",
        )
    content_type = (file.content_type or "").lower()
    if content_type and content_type not in ALLOWED_CSV_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid content type '{file.content_type}'. Expected a CSV file (text/csv).",
        )


async def _check_file_size(file: UploadFile):
    """Raise 413 if uploaded file exceeds MAX_UPLOAD_SIZE.

    Checks Content-Length header first, then verifies actual size by reading
    the file, since UploadFile.size is unreliable before full upload.
    Also validates that the file is a CSV.
    """
    _validate_csv_file(file)
    # Fast check via header hint
    if file.size and file.size > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 50MB.")
    # Verify actual size by reading; rewind after
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 50MB.")
    await file.seek(0)


@router.post("/csv/dry-run")
async def csv_dry_run(
    members_file: Optional[UploadFile] = File(None),
    classes_file: Optional[UploadFile] = File(None),
    memberships_file: Optional[UploadFile] = File(None),
    instructors_file: Optional[UploadFile] = File(None),
    schedule_file: Optional[UploadFile] = File(None),
    rbac=Depends(require_permission("import.preview")),
):
    """Preview a CSV import without making changes."""
    for f in [members_file, classes_file, memberships_file, instructors_file, schedule_file]:
        if f:
            await _check_file_size(f)

    members_csv = None
    classes_csv = None
    memberships_csv = None
    instructors_csv = None
    schedule_csv = None

    if members_file:
        members_csv = (await members_file.read()).decode("utf-8-sig")
    if classes_file:
        classes_csv = (await classes_file.read()).decode("utf-8-sig")
    if memberships_file:
        memberships_csv = (await memberships_file.read()).decode("utf-8-sig")
    if instructors_file:
        instructors_csv = (await instructors_file.read()).decode("utf-8-sig")
    if schedule_file:
        schedule_csv = (await schedule_file.read()).decode("utf-8-sig")

    if not any([members_csv, classes_csv, memberships_csv, instructors_csv, schedule_csv]):
        raise HTTPException(status_code=400, detail="At least one CSV file is required")

    result = await importer.dry_run(
        members_csv=members_csv,
        classes_csv=classes_csv,
        memberships_csv=memberships_csv,
        instructors_csv=instructors_csv,
        schedule_csv=schedule_csv,
    )
    return {"data": result}


@router.post("/csv/import/members")
async def import_members(
    file: UploadFile = File(...),
    studio_id: str = Form(...),
    rbac=Depends(require_permission("import.execute_members")),
):
    """Import members from a CSV file."""
    await _check_file_size(file)
    csv_content = (await file.read()).decode("utf-8-sig")
    result = await importer.import_members(csv_content, studio_id)
    return {"data": result}


@router.post("/csv/import/class-types")
async def import_class_types(
    file: UploadFile = File(...),
    studio_id: str = Form(...),
    rbac=Depends(require_permission("import.execute")),
):
    """Import class types from a CSV file."""
    await _check_file_size(file)
    csv_content = (await file.read()).decode("utf-8-sig")
    result = await importer.import_class_types(csv_content, studio_id)
    return {"data": result}


@router.post("/csv/import/instructors")
async def import_instructors(
    file: UploadFile = File(...),
    rbac=Depends(require_permission("import.execute_instructors")),
):
    """Import instructors from a CSV file."""
    await _check_file_size(file)
    csv_content = (await file.read()).decode("utf-8-sig")
    result = await importer.import_instructors(csv_content)
    return {"data": result}


@router.post("/csv/import/memberships")
async def import_memberships(
    file: UploadFile = File(...),
    studio_id: str = Form(...),
    rbac=Depends(require_permission("import.execute_memberships")),
):
    """Import memberships from a CSV file. Creates types + assigns to members."""
    await _check_file_size(file)
    csv_content = (await file.read()).decode("utf-8-sig")
    result = await importer.import_memberships(csv_content, studio_id)
    return {"data": result}


@router.post("/csv/import/attendance")
async def import_attendance(
    file: UploadFile = File(...),
    studio_id: str = Form(...),
    rbac=Depends(require_permission("import.execute")),
):
    """Import class attendance history from a CSV file."""
    await _check_file_size(file)
    csv_content = (await file.read()).decode("utf-8-sig")
    result = await importer.import_attendance_history(csv_content, studio_id)
    return {"data": result}


@router.post("/csv/import/schedule")
async def import_schedule(
    file: UploadFile = File(...),
    studio_id: str = Form(...),
    expand_weeks: int = Form(4),
    rbac=Depends(require_permission("import.execute_schedule")),
):
    """Import every class row as a recurring weekly series with future sessions."""
    await _check_file_size(file)
    csv_content = (await file.read()).decode("utf-8-sig")
    result = await importer.import_schedule(csv_content, studio_id, expand_weeks)
    return {"data": result}


# ── Stripe Connector Import ──────────────────────────────────────────────────


@router.post("/stripe/dry-run/auto-sync")
async def stripe_dry_run_auto_sync(
    rbac=Depends(require_permission("import.preview_stripe")),
):
    """Preview auto-sync: match Stripe customers to AuraFlow members by email."""
    from app.core.tenant_context import get_organization_id
    org_id = get_organization_id()
    result = await stripe_importer.dry_run_auto_sync(org_id)
    return {"data": result}


@router.post("/stripe/dry-run/csv")
async def stripe_dry_run_csv(
    file: UploadFile = File(...),
    rbac=Depends(require_permission("import.preview_stripe")),
):
    """Preview CSV-based Stripe customer mapping."""
    await _check_file_size(file)
    csv_content = (await file.read()).decode("utf-8-sig")
    from app.core.tenant_context import get_organization_id
    org_id = get_organization_id()
    result = await stripe_importer.dry_run_csv(csv_content, org_id)
    return {"data": result}


@router.post("/stripe/import/auto-sync")
async def stripe_import_auto_sync(
    import_subscriptions: bool = Body(False, embed=True),
    rbac=Depends(require_permission("import.execute_stripe")),
):
    """Auto-sync Stripe customers to AuraFlow members by email match."""
    from app.core.tenant_context import get_organization_id
    org_id = get_organization_id()
    result = await stripe_importer.auto_sync_import(
        org_id, import_subscriptions=import_subscriptions
    )
    return {"data": result}


@router.post("/stripe/import/csv")
async def stripe_import_csv(
    file: UploadFile = File(...),
    import_subscriptions: bool = Form(False),
    rbac=Depends(require_permission("import.execute_stripe")),
):
    """Import Stripe customer mappings from a CSV file."""
    await _check_file_size(file)
    csv_content = (await file.read()).decode("utf-8-sig")
    from app.core.tenant_context import get_organization_id
    org_id = get_organization_id()

    # First do a dry-run to get validated matches
    preview = await stripe_importer.dry_run_csv(csv_content, org_id)
    if preview.get("error"):
        raise HTTPException(status_code=400, detail=preview["error"])

    if not preview["matches"]:
        return {"data": {
            "linked": 0,
            "subscriptions_linked": 0,
            "already_linked": preview.get("already_linked", 0),
            "errors": preview.get("errors", []),
            "total": 0,
        }}

    result = await stripe_importer.import_stripe_customers(
        org_id=org_id,
        matches=preview["matches"],
        import_subscriptions=import_subscriptions,
    )
    result["already_linked"] = preview.get("already_linked", 0)
    return {"data": result}


# ── AI-Powered Import ────────────────────────────────────────────────────────

# In-memory store for import context (per-request; for chat follow-ups)
_ai_import_contexts: dict[str, dict] = {}


@router.post("/ai/upload")
async def ai_import_upload(
    files: list[UploadFile] = File(...),
    rbac=Depends(require_permission("import.ai_analyze")),
):
    """Upload CSV files and get AI analysis with column mappings."""
    if not files:
        raise HTTPException(status_code=400, detail="At least one CSV file is required")

    file_contents = {}
    for f in files:
        _validate_csv_file(f)
        await _check_file_size(f)
        content = (await f.read()).decode("utf-8-sig")
        file_contents[f.filename or f"file_{len(file_contents)}"] = content

    analysis = await ai_importer.analyze_csv_files(file_contents)
    return {"data": analysis}


@router.post("/ai/preview")
async def ai_import_preview(
    files: list[UploadFile] = File(...),
    column_mappings: str = Form(...),
    membership_type_mappings: str = Form(...),
    rbac=Depends(require_permission("import.ai_preview")),
):
    """Get detailed preview with applied mappings before importing."""
    import json

    try:
        mappings = json.loads(column_mappings)
        type_mappings = json.loads(membership_type_mappings)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in mappings")

    file_contents = {}
    for f in files:
        _validate_csv_file(f)
        await _check_file_size(f)
        content = (await f.read()).decode("utf-8-sig")
        file_contents[f.filename or f"file_{len(file_contents)}"] = content

    preview = await ai_importer.preview_import(file_contents, mappings, type_mappings)
    return {"data": preview}


@router.post("/ai/execute")
async def ai_import_execute(
    files: list[UploadFile] = File(...),
    column_mappings: str = Form(...),
    membership_type_mappings: str = Form(...),
    studio_id: str = Form(...),
    rbac=Depends(require_permission("import.ai_execute")),
):
    """Execute the AI-powered import."""
    import json

    try:
        mappings = json.loads(column_mappings)
        type_mappings = json.loads(membership_type_mappings)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in mappings")

    file_contents = {}
    for f in files:
        _validate_csv_file(f)
        await _check_file_size(f)
        content = (await f.read()).decode("utf-8-sig")
        file_contents[f.filename or f"file_{len(file_contents)}"] = content

    result = await ai_importer.execute_import(
        file_contents, mappings, type_mappings, studio_id
    )

    # Store context for chat follow-ups (keyed by org)
    from app.core.tenant_context import get_organization_id
    org_id = get_organization_id()
    _ai_import_contexts[org_id] = {
        "result": result,
        "membership_type_mappings": type_mappings,
        "studio_id": studio_id,
        "files_imported": list(file_contents.keys()),
    }

    return {"data": result}


@router.post("/ai/chat")
async def ai_import_chat(
    message: str = Body(..., embed=True),
    rbac=Depends(require_permission("import.ai_interact")),
):
    """Chat with AI about the import results."""
    from app.core.tenant_context import get_organization_id
    org_id = get_organization_id()

    context = _ai_import_contexts.get(org_id, {})
    if not context:
        # Provide minimal context if no import was done in this session
        context = {"note": "No import has been executed in this session."}

    response = await ai_importer.chat_interaction(message, context)
    return {"data": {"response": response}}


@router.get("/ai/status")
async def ai_import_status(
    rbac=Depends(require_permission("import.view_status")),
):
    """Get the last AI import results for this organization."""
    from app.core.tenant_context import get_organization_id
    org_id = get_organization_id()

    context = _ai_import_contexts.get(org_id)
    if not context:
        return {"data": {"status": "no_import", "result": None}}

    return {"data": {"status": "complete", "result": context.get("result")}}
