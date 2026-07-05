"""AuraFlow — External Payments & POS Endpoints

API-key-authenticated transactions, payment intents, and product listing.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator

from app.api.v1.dependencies.api_key_auth import get_api_key_context, require_api_scope
from app.core.config import settings
from app.services.retail.pos_service import POSService
from app.services.retail.product_service import ProductService
from app.services.payments.stripe_service import StripeService
from app.db.session import get_tenant_db
from app.services.external.csv_export import export_csv

router = APIRouter()
_pos_svc = POSService()
_product_svc = ProductService()
_stripe_svc = StripeService()


# ── Schemas ──────────────────────────────────────────────────────────────────

class PaymentIntentCreate(BaseModel):
    amount_cents: int
    member_id: str
    description: str = "External sale"


class RecordSaleItem(BaseModel):
    product_id: str
    quantity: int = 1


class RecordSale(BaseModel):
    items: list[RecordSaleItem]
    payment_method: str = "card"
    member_id: Optional[str] = None
    stripe_payment_id: Optional[str] = None
    notes: Optional[str] = None


class RecordTransactionExternal(BaseModel):
    """Flat transaction recorded by an integration (wellness-emr / bioalign)
    for a service rendered outside auraflow's POS — typically billing for an
    FMS, gait screen, or other clinical assessment. Mirrors the internal
    POST /api/v1/payments/transactions but with api-key auth + an
    external_reference field for cross-system idempotency."""
    member_id: str = Field(..., min_length=1, max_length=64,
                           description="UUID or stable opaque id for the member.")
    amount_cents: int = Field(..., gt=0, le=100_000_00,
                              description="Positive cents, capped at $100k per single txn.")
    type: str = Field("payment", min_length=1, max_length=50)
    description: Optional[str] = Field(None, max_length=500)
    external_reference: Optional[str] = Field(
        None, min_length=1, max_length=128,
        description="Caller-supplied dedup key. Required for idempotent retries.",
    )
    membership_id: Optional[str] = Field(None, min_length=1, max_length=64)
    booking_id: Optional[str] = Field(None, min_length=1, max_length=64)

    @field_validator("external_reference")
    @classmethod
    def _ext_ref_not_blank(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("external_reference cannot be blank if provided")
        return v


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fmt(dt):
    if dt and hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt) if dt else None


def _txn_dict(row: dict) -> dict:
    return {
        "id": str(row.get("id", "")),
        "member_id": str(row["member_id"]) if row.get("member_id") else None,
        "subtotal_cents": row.get("subtotal_cents"),
        "tax_cents": row.get("tax_cents"),
        "total_cents": row.get("total_cents"),
        "payment_method": row.get("payment_method"),
        "status": row.get("status"),
        "notes": row.get("notes"),
        "created_at": _fmt(row.get("created_at")),
        "member_first_name": row.get("member_first_name"),
        "member_last_name": row.get("member_last_name"),
        "line_items": row.get("line_items"),
    }


# ── CSV Export ───────────────────────────────────────────────────────────────

_TXN_CSV_COLS = [
    ("id", "ID"),
    ("member_id", "Member ID"),
    ("member_first_name", "First Name"),
    ("member_last_name", "Last Name"),
    ("subtotal_cents", "Subtotal (cents)"),
    ("tax_cents", "Tax (cents)"),
    ("total_cents", "Total (cents)"),
    ("payment_method", "Payment Method"),
    ("status", "Status"),
    ("created_at", "Created At"),
]

_PRODUCT_CSV_COLS = [
    ("id", "ID"),
    ("name", "Name"),
    ("sku", "SKU"),
    ("category", "Category"),
    ("price_cents", "Price (cents)"),
    ("cost_cents", "Cost (cents)"),
    ("quantity_on_hand", "Stock"),
    ("active", "Active"),
]


@router.get(
    "/transactions/export.csv",
    dependencies=[Depends(require_api_scope("payments:read"))],
    summary="Export transactions as CSV",
)
async def export_transactions_csv(
    ctx: dict = Depends(get_api_key_context),
    member_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    df = date.fromisoformat(date_from) if date_from else None
    dt = date.fromisoformat(date_to) if date_to else None
    rows = await _pos_svc.list_transactions(
        member_id=member_id, date_from=df, date_to=dt, limit=10000,
    )
    return export_csv(rows, _TXN_CSV_COLS, "transactions.csv")


@router.get(
    "/products/export.csv",
    dependencies=[Depends(require_api_scope("payments:read"))],
    summary="Export products as CSV",
)
async def export_products_csv(
    ctx: dict = Depends(get_api_key_context),
):
    rows = await _product_svc.list_products(active_only=False)
    return export_csv(rows, _PRODUCT_CSV_COLS, "products.csv")


# ── Transactions ─────────────────────────────────────────────────────────────

@router.post(
    "/transactions",
    dependencies=[Depends(require_api_scope("payments:write"))],
    summary="Record a flat transaction (integration billing)",
    responses={
        200: {"description": "Idempotent retry — existing row returned"},
        201: {"description": "New transaction created"},
    },
)
async def record_external_transaction(
    body: RecordTransactionExternal,
    response: Response,
    ctx: dict = Depends(get_api_key_context),
):
    """Record a single flat transaction in the tenant's transactions table.

    Use case: a sibling product (wellness-emr, bioalign-pro) rendered a
    paid service (FMS, gait screen, etc.) and needs to bill the auraflow
    member for it.

    Idempotent on `external_reference` — re-sending the same one returns
    the original transaction row with HTTP 200; first creation returns 201.
    Same fee math as the internal POST /api/v1/payments/transactions; same
    `transactions` table.
    """
    data = body.model_dump(exclude_none=True)
    fee = int(data["amount_cents"] * settings.STRIPE_PLATFORM_FEE_PERCENT / 100)
    data["fee_cents"] = fee
    data["net_amount_cents"] = data["amount_cents"] - fee
    data["status"] = "completed"

    # Stash external_reference in metadata for cross-system idempotency.
    # We DON'T include api_key_id in the publicly-returned metadata (it
    # identifies which key created the txn — leaks api-key fingerprinting
    # to consumers). Server-side audit lives in stripe_service logs.
    if body.external_reference:
        data["metadata"] = {
            "external_reference": body.external_reference,
            "source": "integration",
        }
    data.pop("external_reference", None)

    # Detect whether the service returned an existing row or a new one
    # by checking the create timestamp before/after.
    pre_count_marker = data.get("metadata", {}).get("external_reference")
    txn = await _stripe_svc.record_transaction(data)

    # If the returned row's external_reference matches what we just sent
    # AND the row was created BEFORE this request, it was an idempotent
    # hit. Compare on `created_at` < now-5s as a rough heuristic; fallback
    # to 201 if we can't tell.
    is_idempotent_hit = False
    if pre_count_marker:
        from datetime import datetime as _dt, timezone as _tz
        created_at = txn.get("created_at")
        if created_at and isinstance(created_at, _dt):
            now = _dt.now(_tz.utc)
            if (now - created_at).total_seconds() > 5:
                is_idempotent_hit = True
    response.status_code = 200 if is_idempotent_hit else 201

    return {"data": _txn_dict_full(txn)}


def _txn_dict_full(row: dict) -> dict:
    """Serialize a transactions-table row (datetimes → ISO, UUIDs → str,
    metadata jsonb → dict). Strips api_key_id from metadata if present
    (server-side audit only — don't fingerprint api keys to consumers)."""
    import json as _json
    out = {}
    for k, v in row.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif hasattr(v, "hex") and not isinstance(v, (bytes, bytearray)):
            out[k] = str(v)
        elif k == "metadata":
            if isinstance(v, str):
                try:
                    parsed = _json.loads(v)
                except (ValueError, TypeError):
                    parsed = {}
            elif isinstance(v, dict):
                parsed = dict(v)
            elif v is None:
                parsed = {}
            else:
                parsed = {}
            parsed.pop("api_key_id", None)  # never expose
            out[k] = parsed
        else:
            out[k] = v
    return out


@router.get(
    "/transactions",
    dependencies=[Depends(require_api_scope("payments:read"))],
    summary="List POS transactions",
)
async def list_transactions(
    ctx: dict = Depends(get_api_key_context),
    member_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, le=500),
    offset: int = Query(0),
):
    df = date.fromisoformat(date_from) if date_from else None
    dt_val = date.fromisoformat(date_to) if date_to else None
    rows = await _pos_svc.list_transactions(
        member_id=member_id, date_from=df, date_to=dt_val, limit=limit, offset=offset,
    )
    return [_txn_dict(r) for r in rows]


# ── POS Payment Intent ───────────────────────────────────────────────────────

@router.post(
    "/pos/payment-intent",
    dependencies=[Depends(require_api_scope("payments:write"))],
    status_code=201,
    summary="Create a Stripe payment intent for external website sales",
)
async def create_payment_intent(
    body: PaymentIntentCreate,
    ctx: dict = Depends(get_api_key_context),
):
    # Look up member for Stripe customer
    async with get_tenant_db() as db:
        member = await db.fetchrow(
            "SELECT id, first_name, last_name, email FROM members WHERE id = $1",
            body.member_id,
        )
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    name = f"{member['first_name']} {member['last_name']}"
    customer_id = await _stripe_svc.get_or_create_customer(
        member_id=body.member_id,
        email=member["email"],
        name=name,
    )

    result = await _stripe_svc.create_payment_intent(
        amount_cents=body.amount_cents,
        customer_id=customer_id,
        description=body.description,
        metadata={"source": "external_api", "member_id": body.member_id},
    )
    return result


# ── Record Completed POS Sale ────────────────────────────────────────────────

@router.post(
    "/pos/record-sale",
    dependencies=[Depends(require_api_scope("payments:write"))],
    status_code=201,
    summary="Record a completed POS transaction",
)
async def record_sale(
    body: RecordSale,
    ctx: dict = Depends(get_api_key_context),
):
    try:
        result = await _pos_svc.create_transaction(
            items=[{"product_id": i.product_id, "quantity": i.quantity} for i in body.items],
            payment_method=body.payment_method,
            member_id=body.member_id,
            stripe_payment_id=body.stripe_payment_id,
            notes=body.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return result


# ── Products ─────────────────────────────────────────────────────────────────

@router.get(
    "/products",
    dependencies=[Depends(require_api_scope("payments:read"))],
    summary="List products for sale",
)
async def list_products(
    ctx: dict = Depends(get_api_key_context),
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    rows = await _product_svc.list_products(
        category=category, active_only=True, search=search,
    )
    return rows
