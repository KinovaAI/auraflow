"""AuraFlow — Accounting (per-tenant bookkeeping) endpoints.

The migrated LLC accounting module: bank-authoritative books per studio.
  - settings      : LLC identity + encrypted Mercury key (masked on read).
  - transactions  : the ledger (bank-imported + manual); categorize / reconcile.
  - members       : K-1 partners.
  - sync          : pull Mercury bank txns + Stripe/Square payouts, reconcile.
  - reconcile     : match payouts ↔ bank deposits; report what doesn't tie out.
  - reports       : P&L, Schedule C, K-1.
  - export        : TurboTax .txf + accountant PDF.

Tenant-scoped via get_tenant_db() (search_path = caller's tenant schema). Owner
role bypasses every permission; staff need the specific accounting.* grant.
"""
import io
from datetime import date as _date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.v1.dependencies.rbac import require_permission
from app.core.tenant_context import get_organization_id, get_tenant_context
from app.db.session import get_tenant_db
from app.services.accounting import (
    settings_service,
    reports as reports_service,
    export_service,
    income_sync,
    mercury_service,
    payout_service,
    reconciliation,
    categorize,
    fees,
    draws,
)

router = APIRouter()


def _schema() -> str:
    ctx = get_tenant_context()
    if not ctx or not getattr(ctx, "schema_name", None):
        raise HTTPException(status_code=400, detail="No tenant context")
    return ctx.schema_name


# ── Schemas ──────────────────────────────────────────────────────────────────

class SettingsPatch(BaseModel):
    llc_name: Optional[str] = None
    llc_ein: Optional[str] = None
    llc_state: Optional[str] = None
    llc_tax_class: Optional[str] = None
    mercury_api_key: Optional[str] = None


class MemberPayload(BaseModel):
    name: str
    email: Optional[str] = None
    ownership_pct: float = 0
    capital_cents: int = 0
    tin: Optional[str] = None


class MemberPatch(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    ownership_pct: Optional[float] = None
    capital_cents: Optional[int] = None
    tin: Optional[str] = None


class TxnCreate(BaseModel):
    txn_date: str
    description: str
    type: str  # income | expense | distribution | transfer
    category: Optional[str] = None
    amount_cents: int
    member_id: Optional[str] = None
    notes: Optional[str] = None


class TxnPatch(BaseModel):
    category: Optional[str] = None
    type: Optional[str] = None
    member_id: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None


# ── Settings ─────────────────────────────────────────────────────────────────

@router.get("/settings")
async def get_settings(rbac: dict = Depends(require_permission("accounting.view"))):
    async with get_tenant_db() as db:
        await settings_service.ensure_seeded(db, _schema())
        return await settings_service.get_settings(db)


@router.put("/settings")
async def update_settings(
    patch: SettingsPatch,
    rbac: dict = Depends(require_permission("accounting.manage_settings")),
):
    async with get_tenant_db() as db:
        await settings_service.ensure_seeded(db, _schema())
        return await settings_service.update_settings(
            db, patch.model_dump(exclude_unset=True)
        )


# ── Categories ───────────────────────────────────────────────────────────────

@router.get("/categories")
async def list_categories(rbac: dict = Depends(require_permission("accounting.view"))):
    async with get_tenant_db() as db:
        await settings_service.ensure_seeded(db, _schema())
        rows = await db.fetch(
            "SELECT code, label, kind, schedule_c_line, txf_ref, is_custom "
            "FROM acct_categories ORDER BY kind, sort_order, label"
        )
        return [dict(r) for r in rows]


# ── Members (K-1 partners) ───────────────────────────────────────────────────

@router.get("/members")
async def list_members(rbac: dict = Depends(require_permission("accounting.view"))):
    async with get_tenant_db() as db:
        return await settings_service.list_members(db)


@router.post("/members")
async def create_member(
    payload: MemberPayload,
    rbac: dict = Depends(require_permission("accounting.manage_members")),
):
    async with get_tenant_db() as db:
        return await settings_service.create_member(db, payload.model_dump())


@router.put("/members/{member_id}")
async def update_member(
    member_id: str,
    patch: MemberPatch,
    rbac: dict = Depends(require_permission("accounting.manage_members")),
):
    async with get_tenant_db() as db:
        updated = await settings_service.update_member(
            db, member_id, patch.model_dump(exclude_unset=True)
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Member not found")
        return updated


@router.delete("/members/{member_id}")
async def delete_member(
    member_id: str,
    rbac: dict = Depends(require_permission("accounting.manage_members")),
):
    async with get_tenant_db() as db:
        if not await settings_service.delete_member(db, member_id):
            raise HTTPException(status_code=404, detail="Member not found")
        return {"deleted": True}


# ── Owner draw schedule (configures how owner payouts split) ──────────────────

class OwnerDrawPayload(BaseModel):
    owner_pattern: str          # matches the payout description (e.g. an owner's name)
    monthly_cents: int          # fixed monthly draw
    effective_from: str         # YYYY-MM-DD
    effective_to: Optional[str] = None


@router.get("/owner-draws")
async def list_owner_draws(rbac: dict = Depends(require_permission("accounting.view"))):
    async with get_tenant_db() as db:
        rows = await db.fetch(
            "SELECT id, owner_pattern, monthly_cents, effective_from, effective_to, "
            "is_active FROM acct_owner_draws ORDER BY owner_pattern, effective_from"
        )
        return [dict(r) for r in rows]


@router.post("/owner-draws")
async def create_owner_draw(
    payload: OwnerDrawPayload,
    rbac: dict = Depends(require_permission("accounting.manage_settings")),
):
    try:
        ef = _date.fromisoformat(payload.effective_from)
        et = _date.fromisoformat(payload.effective_to) if payload.effective_to else None
    except ValueError:
        raise HTTPException(status_code=400, detail="dates must be YYYY-MM-DD")
    async with get_tenant_db() as db:
        row = await db.fetchrow(
            """
            INSERT INTO acct_owner_draws
                (owner_pattern, monthly_cents, effective_from, effective_to)
            VALUES ($1, $2, $3, $4)
            RETURNING id, owner_pattern, monthly_cents, effective_from, effective_to, is_active
            """,
            payload.owner_pattern.strip(), abs(payload.monthly_cents), ef, et,
        )
        return dict(row)


@router.delete("/owner-draws/{draw_id}")
async def delete_owner_draw(
    draw_id: str,
    rbac: dict = Depends(require_permission("accounting.manage_settings")),
):
    async with get_tenant_db() as db:
        status = await db.execute("DELETE FROM acct_owner_draws WHERE id = $1", draw_id)
        if not status.endswith(" 1"):
            raise HTTPException(status_code=404, detail="Draw rule not found")
        return {"deleted": True}


# ── Transactions (the ledger) ────────────────────────────────────────────────

@router.get("/transactions")
async def list_transactions(
    rbac: dict = Depends(require_permission("accounting.view")),
    year: Optional[int] = Query(None),
    type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = Query(500, le=2000),
    offset: int = Query(0, ge=0),
):
    where, params = [], []
    def add(cond, val):
        params.append(val)
        where.append(cond.format(n=len(params)))
    if year:
        add("EXTRACT(YEAR FROM txn_date) = ${n}", year)
    if type:
        add("type = ${n}", type)
    if status:
        add("status = ${n}", status)
    if source:
        add("source = ${n}", source)
    else:
        # Default ledger = the actual books (bank + manual). AuraFlow sales are
        # itemized detail behind the card deposits — shown only when explicitly
        # filtered to source='auraflow' — so they don't read as double entries.
        where.append("source <> 'auraflow'")
    if category:
        add("category = ${n}", category)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    params.extend([limit, offset])
    async with get_tenant_db() as db:
        rows = await db.fetch(
            f"""
            SELECT id, txn_date, description, type, category, amount_cents, source,
                   external_id, auraflow_txn_id, payout_id, member_id, status, notes
            FROM acct_transactions{clause}
            ORDER BY txn_date DESC, created_at DESC
            LIMIT ${len(params) - 1} OFFSET ${len(params)}
            """,
            *params,
        )
        return [dict(r) for r in rows]


@router.post("/transactions")
async def create_transaction(
    payload: TxnCreate,
    rbac: dict = Depends(require_permission("accounting.manage_transactions")),
):
    try:
        txn_date = _date.fromisoformat(payload.txn_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="txn_date must be YYYY-MM-DD")
    async with get_tenant_db() as db:
        row = await db.fetchrow(
            """
            INSERT INTO acct_transactions
                (txn_date, description, type, category, amount_cents, source,
                 member_id, notes, status, created_by)
            VALUES ($1, $2, $3, $4, $5, 'manual', $6, $7, 'reconciled', $8)
            RETURNING id, txn_date, description, type, category, amount_cents,
                      source, member_id, status, notes
            """,
            txn_date, payload.description, payload.type, payload.category,
            abs(payload.amount_cents), payload.member_id, payload.notes,
            rbac.get("user_id"),
        )
        return dict(row)


@router.put("/transactions/{txn_id}")
async def update_transaction(
    txn_id: str,
    patch: TxnPatch,
    rbac: dict = Depends(require_permission("accounting.manage_transactions")),
):
    data = patch.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    sets, params = [], []
    for field in ("category", "type", "member_id", "notes", "status"):
        if field in data:
            params.append(data[field])
            sets.append(f"{field} = ${len(params)}")
    sets.append("updated_at = NOW()")
    params.append(txn_id)
    async with get_tenant_db() as db:
        row = await db.fetchrow(
            f"UPDATE acct_transactions SET {', '.join(sets)} "
            f"WHERE id = ${len(params)} RETURNING id, txn_date, description, type, "
            "category, amount_cents, source, member_id, status, notes",
            *params,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Transaction not found")
        return dict(row)


@router.delete("/transactions/{txn_id}")
async def delete_transaction(
    txn_id: str,
    rbac: dict = Depends(require_permission("accounting.manage_transactions")),
):
    async with get_tenant_db() as db:
        # Only manual rows are deletable — bank/auraflow rows are the record of truth.
        status = await db.execute(
            "DELETE FROM acct_transactions WHERE id = $1 AND source = 'manual'", txn_id
        )
        if not status.endswith(" 1"):
            raise HTTPException(
                status_code=400,
                detail="Only manually-entered transactions can be deleted",
            )
        return {"deleted": True}


# ── Sync + reconcile ─────────────────────────────────────────────────────────

@router.post("/sync")
async def sync_now(rbac: dict = Depends(require_permission("accounting.sync"))):
    """On-demand full refresh: Mercury bank import → Stripe/Square payout sync →
    reconcile. Same pass the 6-hourly Celery beat runs."""
    org_id = get_organization_id()
    async with get_tenant_db() as db:
        await settings_service.ensure_seeded(db, _schema())
        income = await income_sync.sync_income(db)
        fee = await fees.sync_fees(db, org_id)
        bank = await mercury_service.sync_tenant(db)
        cats = await categorize.categorize_bank(db)
        dr = await draws.apply_draws(db)
        payouts = await payout_service.sync_payouts(db, org_id)
        recon = await reconciliation.reconcile(db)
    return {"income": income, "fees": fee, "bank": bank, "categorize": cats,
            "draws": dr, "payouts": payouts, "reconciliation": recon}


@router.post("/reconcile")
async def reconcile_now(rbac: dict = Depends(require_permission("accounting.reconcile"))):
    """Re-run reconciliation only (no external API calls) and return what does
    and doesn't tie out to the bank."""
    async with get_tenant_db() as db:
        return await reconciliation.reconcile(db)


@router.get("/payouts")
async def list_payouts(
    rbac: dict = Depends(require_permission("accounting.view")),
    reconciled: Optional[bool] = Query(None),
):
    where, params = [], []
    if reconciled is not None:
        params.append(reconciled)
        where.append(f"reconciled = ${len(params)}")
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    async with get_tenant_db() as db:
        rows = await db.fetch(
            f"""
            SELECT id, provider, provider_payout_id, payout_date, gross_cents,
                   fee_cents, net_cents, status, bank_txn_id, reconciled,
                   discrepancy_cents
            FROM acct_payouts{clause}
            ORDER BY payout_date DESC NULLS LAST
            """,
            *params,
        )
        return [dict(r) for r in rows]


# ── Reports ──────────────────────────────────────────────────────────────────

@router.get("/reports/summary")
async def report_summary(
    rbac: dict = Depends(require_permission("accounting.view")),
    year: Optional[int] = Query(None),
):
    async with get_tenant_db() as db:
        return await reports_service.summary(db, year)


@router.get("/reports/schedule-c")
async def report_schedule_c(
    rbac: dict = Depends(require_permission("accounting.view")),
    year: Optional[int] = Query(None),
):
    async with get_tenant_db() as db:
        return await reports_service.schedule_c(db, year)


@router.get("/reports/member-allocation")
async def report_member_allocation(
    rbac: dict = Depends(require_permission("accounting.view")),
    year: Optional[int] = Query(None),
):
    async with get_tenant_db() as db:
        return await reports_service.member_allocation(db, year)


# ── Export ───────────────────────────────────────────────────────────────────

@router.get("/export/txf")
async def export_txf(
    rbac: dict = Depends(require_permission("accounting.export")),
    year: int = Query(...),
):
    async with get_tenant_db() as db:
        txf = await export_service.build_txf(db, year)
    return StreamingResponse(
        io.BytesIO(txf.encode("utf-8")),
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="schedule-c-{year}.txf"'},
    )


@router.get("/export/pdf")
async def export_pdf(
    rbac: dict = Depends(require_permission("accounting.export")),
    year: int = Query(...),
):
    async with get_tenant_db() as db:
        pdf = await export_service.build_pdf(db, year)
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="accounting-{year}.pdf"'},
    )
