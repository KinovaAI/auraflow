"""AuraFlow — Retail & POS Endpoints

Products, inventory management, POS transactions, and reports.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.v1.dependencies.auth import get_current_user
from app.api.v1.dependencies.rbac import require_permission
from app.services.retail.product_service import ProductService
from app.services.retail.inventory_service import InventoryService
from app.services.retail.pos_service import POSService

router = APIRouter()
product_svc = ProductService()
inventory_svc = InventoryService()
pos_svc = POSService()


# ── Schemas ──────────────────────────────────────────────────────────────────

class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = None
    sku: Optional[str] = None
    price_cents: int
    cost_cents: int = 0
    category: str = "retail"
    tax_rate: float = 0.0
    image_url: Optional[str] = None
    studio_id: Optional[str] = None
    reorder_point: int = 5
    reorder_quantity: int = 20


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sku: Optional[str] = None
    price_cents: Optional[int] = None
    cost_cents: Optional[int] = None
    category: Optional[str] = None
    tax_rate: Optional[float] = None
    image_url: Optional[str] = None
    active: Optional[bool] = None


class InventoryAdjustRequest(BaseModel):
    product_id: str
    quantity_change: int
    reason: str
    notes: Optional[str] = None


class CartItem(BaseModel):
    product_id: str
    quantity: int = 1


class CreateTransactionRequest(BaseModel):
    items: list[CartItem]
    payment_method: str  # required — card / stripe / cash / venmo / check / comp / gift_card / send_payment_link
    member_id: Optional[str] = None
    stripe_payment_id: Optional[str] = None
    notes: Optional[str] = None
    gift_card_code: Optional[str] = None  # required when payment_method='gift_card'


class RefundRequest(BaseModel):
    reason: str = "requested_by_customer"


# ── Products ─────────────────────────────────────────────────────────────────

@router.get("/products")
async def list_products(
    category: Optional[str] = Query(None),
    active_only: bool = Query(True),
    search: Optional[str] = Query(None),
    user=Depends(get_current_user),
    _=Depends(require_permission("retail.view_products")),
):
    """List all products with optional filters."""
    products = await product_svc.list_products(category, active_only, search)
    return {"data": products}


@router.get("/products/sku/{sku}")
async def get_product_by_sku(
    sku: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("retail.view_products")),
):
    """Lookup product by SKU / barcode."""
    product = await product_svc.get_by_sku(sku)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"data": product}


@router.get("/products/{product_id}")
async def get_product(
    product_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("retail.view_products")),
):
    """Get a single product."""
    product = await product_svc.get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"data": product}


@router.post("/products", status_code=201)
async def create_product(
    body: ProductCreate,
    user=Depends(get_current_user),
    _=Depends(require_permission("retail.create_product")),
):
    """Create a new product with default inventory."""
    product = await product_svc.create_product(body.model_dump())
    return {"data": product}


@router.put("/products/{product_id}")
async def update_product(
    product_id: str,
    body: ProductUpdate,
    user=Depends(get_current_user),
    _=Depends(require_permission("retail.edit_product")),
):
    """Update a product."""
    product = await product_svc.update_product(product_id, body.model_dump(exclude_unset=True))
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"data": product}


@router.delete("/products/{product_id}", status_code=204)
async def delete_product(
    product_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("retail.delete_product")),
):
    """Soft-delete a product."""
    deleted = await product_svc.delete_product(product_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Product not found")


# ── Inventory ────────────────────────────────────────────────────────────────

@router.get("/inventory")
async def list_inventory(
    low_stock_only: bool = Query(False),
    user=Depends(get_current_user),
    _=Depends(require_permission("retail.view_inventory")),
):
    """List all inventory levels."""
    items = await inventory_svc.list_inventory(low_stock_only)
    return {"data": items}


@router.get("/inventory/alerts/low-stock")
async def low_stock_alerts(
    user=Depends(get_current_user),
    _=Depends(require_permission("retail.view_inventory")),
):
    """Get products below reorder point."""
    alerts = await inventory_svc.get_low_stock_alerts()
    return {"data": alerts}


@router.post("/inventory/adjust")
async def adjust_inventory(
    body: InventoryAdjustRequest,
    user=Depends(get_current_user),
    _=Depends(require_permission("retail.adjust_inventory")),
):
    """Adjust stock level for a product."""
    try:
        result = await inventory_svc.adjust_stock(
            body.product_id, body.quantity_change, body.reason,
            body.notes, user["sub"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": result}


@router.get("/inventory/{product_id}/history")
async def inventory_history(
    product_id: str,
    limit: int = Query(50, le=200),
    user=Depends(get_current_user),
    _=Depends(require_permission("retail.view_inventory")),
):
    """Get inventory transaction history for a product."""
    history = await inventory_svc.get_transaction_history(product_id, limit)
    return {"data": history}


# ── POS Transactions ─────────────────────────────────────────────────────────

@router.post("/transactions", status_code=201)
async def create_transaction(
    body: CreateTransactionRequest,
    user=Depends(get_current_user),
    _=Depends(require_permission("retail.record_transaction")),
):
    """Create a POS sale. For Stripe payments, creates a checkout session."""
    try:
        txn = await pos_svc.create_transaction(
            items=[item.model_dump() for item in body.items],
            payment_method=body.payment_method,
            member_id=body.member_id,
            created_by=user["sub"],
            stripe_payment_id=body.stripe_payment_id,
            notes=body.notes,
            gift_card_code=body.gift_card_code,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # send_payment_link: create a Square hosted payment link and email it.
    # card / stripe: handled on the frontend by opening the POSChargeModal
    # which fires Square Terminal API against a paired phone or device.
    # New POS sales go through Square ONLY — Stripe lives only to keep
    # existing Your Studio recurring memberships running until they migrate
    # via /portal/memberships/switch-to-square. No new Stripe checkouts.
    if body.payment_method == "send_payment_link" and txn["total_cents"] > 0:
        try:
            from app.core.tenant_context import get_organization_id, require_tenant_context
            from app.core.config import settings
            from app.services.payments.square_oauth_service import square_oauth_service
            from app.services.payments.square_service import _client as _sq_client, _idem
            from app.db.session import get_tenant_db, get_global_db

            org_id = get_organization_id()
            ctx = require_tenant_context()
            dashboard_url = f"{settings.APP_URL}/{ctx.slug}/dashboard/pos"

            access_token = await square_oauth_service.get_merchant_access_token(org_id)
            if not access_token:
                raise RuntimeError(
                    "Square is not connected for this studio. Connect Square "
                    "in Settings → Billing before taking card payments."
                )

            async with get_global_db() as gdb:
                loc_row = await gdb.fetchrow(
                    "SELECT square_location_id FROM af_global.organizations WHERE id=$1",
                    org_id,
                )
            location_id = loc_row and loc_row["square_location_id"]
            if not location_id:
                raise RuntimeError("Square location not configured on this org")

            sq_line_items = []
            for li in txn.get("line_items", []):
                qty = li["quantity"] or 1
                unit_total = li["unit_price_cents"] + (li["tax_cents"] // qty if qty else 0)
                sq_line_items.append({
                    "name": (li.get("product_name") or "Retail Item")[:255],
                    "quantity": str(qty),
                    "base_price_money": {"amount": unit_total, "currency": "USD"},
                })

            pre_populated: dict = {}
            if body.member_id:
                async with get_tenant_db() as db:
                    member_row = await db.fetchrow(
                        "SELECT email FROM members WHERE id = $1",
                        body.member_id,
                    )
                if member_row and member_row.get("email"):
                    pre_populated["buyer_email"] = member_row["email"]

            client = _sq_client(access_token)
            from app.services.payments.billing_dispatcher import _square_app_fee
            order_total_cents = sum(int(li["base_price_money"]["amount"]) * int(li["quantity"]) for li in sq_line_items)
            app_fee_cents = _square_app_fee(order_total_cents)
            resp = await client.checkout.payment_links.create(
                idempotency_key=_idem(),
                description=f"POS sale: {txn['id'][:8]}",
                order={
                    "location_id": location_id,
                    "line_items": sq_line_items,
                    "reference_id": txn["id"][:40],
                    "metadata": {
                        "auraflow_pos_transaction_id": txn["id"],
                        "auraflow_org_schema": ctx.schema_name,
                    },
                },
                checkout_options={
                    "redirect_url": f"{dashboard_url}?pos_paid=1&txn={txn['id']}",
                    "app_fee_money": {"amount": app_fee_cents, "currency": "USD"},
                },
                pre_populated_data=pre_populated or None,
            )
            if getattr(resp, "errors", None):
                raise RuntimeError(f"Square payment link error: {resp.errors}")
            pl = resp.payment_link
            txn["checkout_url"] = pl.url
            session_url = pl.url

            # Email payment link to member if send_payment_link method
            if body.payment_method == "send_payment_link" and body.member_id:
                try:
                    from app.services.email.email_service import EmailService
                    email_svc = EmailService()
                    async with get_tenant_db() as db:
                        member = await db.fetchrow(
                            "SELECT first_name, last_name, email FROM members WHERE id = $1",
                            body.member_id,
                        )
                    if member and member["email"]:
                        # Build item list for email
                        item_lines = "".join(
                            f"<tr><td style='padding:4px 12px;'>{li.get('product_name','Item')} x{li['quantity']}</td>"
                            f"<td style='padding:4px 12px; text-align:right;'>${li['total_cents']/100:.2f}</td></tr>"
                            for li in txn.get("line_items", [])
                        )
                        total_display = f"${txn['total_cents']/100:.2f}"

                        # Get studio name
                        async with get_global_db() as gdb:
                            org_row = await gdb.fetchrow("SELECT name FROM af_global.organizations WHERE id = $1", org_id)
                        studio_name = org_row["name"] if org_row else "the studio"

                        html = f"""
                        <h2>Payment Request from {studio_name}</h2>
                        <p>Hi {member['first_name']},</p>
                        <p>Here's your order from <strong>{studio_name}</strong>:</p>
                        <table style="margin:16px 0; border-collapse:collapse; width:100%;">
                          {item_lines}
                          <tr style="border-top:1px solid #ddd; font-weight:600;">
                            <td style="padding:8px 12px;">Total</td>
                            <td style="padding:8px 12px; text-align:right;">{total_display}</td>
                          </tr>
                        </table>
                        <p style="margin:24px 0;">
                          <a href="{session_url}" style="background-color:#4f46e5; color:white; padding:12px 24px; border-radius:6px; text-decoration:none; font-weight:600;">
                            Pay {total_display}
                          </a>
                        </p>
                        <p style="color:#666; font-size:13px;">If the button doesn't work, copy and paste this link:<br/>
                        <a href="{session_url}">{session_url}</a></p>
                        <p>— {studio_name}</p>
                        """
                        await email_svc.send_email(
                            to_email=member["email"],
                            subject=f"Payment Request from {studio_name} — {total_display}",
                            html_content=html,
                            member_id=body.member_id,
                            email_type="payment_request",
                        )
                        txn["payment_link_emailed"] = True
                        from app.core.logging import logger
                        logger.info("POS payment link emailed", txn_id=txn["id"], email=member["email"])
                except Exception as email_err:
                    from app.core.logging import logger
                    logger.warning("POS payment link email failed", error=str(email_err))

        except Exception as e:
            from app.core.logging import logger
            logger.warning("POS Stripe checkout failed", error=str(e), txn_id=txn["id"])

    return {"data": txn}


@router.get("/transactions")
async def list_transactions(
    member_id: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    user=Depends(get_current_user),
    _=Depends(require_permission("retail.view_transactions")),
):
    """List POS transactions."""
    txns = await pos_svc.list_transactions(member_id, date_from, date_to, limit, offset)
    return {"data": txns}


@router.get("/transactions/pending")
async def list_pending_transactions(
    user=Depends(get_current_user),
    _=Depends(require_permission("retail.view_transactions")),
):
    """List all pending POS transactions."""
    txns = await pos_svc.list_transactions(status="pending")
    return {"data": txns}


@router.get("/transactions/{transaction_id}")
async def get_transaction(
    transaction_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("retail.view_transactions")),
):
    """Get POS transaction with line items."""
    txn = await pos_svc.get_transaction(transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"data": txn}


@router.post("/transactions/{transaction_id}/refund")
async def refund_transaction(
    transaction_id: str,
    body: RefundRequest,
    user=Depends(get_current_user),
    _=Depends(require_permission("retail.refund_transaction")),
):
    """Refund a POS transaction and restore inventory."""
    try:
        txn = await pos_svc.refund_transaction(transaction_id, body.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": txn}


# ── Reports ──────────────────────────────────────────────────────────────────

@router.get("/reports/daily")
async def daily_summary(
    target_date: date = Query(default=None),
    user=Depends(get_current_user),
    _=Depends(require_permission("retail.view_reports")),
):
    """Get daily POS summary by payment method."""
    if not target_date:
        target_date = date.today()
    summary = await pos_svc.get_daily_summary(target_date)
    return {"data": summary}


@router.get("/reports/sales")
async def sales_report(
    date_from: date = Query(...),
    date_to: date = Query(...),
    user=Depends(get_current_user),
    _=Depends(require_permission("retail.view_reports")),
):
    """Get sales report by category and product."""
    report = await pos_svc.get_sales_report(date_from, date_to)
    return {"data": report}


@router.post("/transactions/{transaction_id}/resend-link")
async def resend_payment_link(
    transaction_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("retail.resend_payment_link")),
):
    """Resend the payment link for a pending POS transaction."""
    txn = await pos_svc.get_transaction(transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if txn["status"] != "pending":
        raise HTTPException(status_code=400, detail="Transaction is not pending")
    if not txn.get("member_id"):
        raise HTTPException(status_code=400, detail="No member associated with this transaction")

    from app.core.tenant_context import get_organization_id, require_tenant_context
    from app.services.payments.stripe_service import _get_org_stripe_key, _stripe_key_for_org
    from app.services.email.email_service import EmailService
    from app.db.session import get_tenant_db, get_global_db
    from app.core.config import settings
    import stripe as _stripe
    import asyncio

    org_id = get_organization_id()
    ctx = require_tenant_context()
    direct_key = await _get_org_stripe_key(org_id)
    api_key = _stripe_key_for_org(direct_key)

    # Get member
    async with get_tenant_db() as db:
        member = await db.fetchrow(
            "SELECT first_name, last_name, email, stripe_customer_id FROM members WHERE id = $1",
            txn["member_id"],
        )
    if not member or not member["email"]:
        raise HTTPException(status_code=400, detail="Member has no email on file")

    # Build line items
    line_items = []
    for li in txn.get("line_items", []):
        line_items.append({
            "price_data": {
                "currency": "usd",
                "unit_amount": li["unit_price_cents"] + (li["tax_cents"] // li["quantity"] if li["quantity"] else 0),
                "product_data": {"name": li.get("product_name", "Retail Item")},
            },
            "quantity": li["quantity"],
        })

    dashboard_url = f"{settings.APP_URL}/{ctx.slug}/dashboard/pos"
    checkout_params = {
        "api_key": api_key,
        "mode": "payment",
        "line_items": line_items,
        "success_url": f"{dashboard_url}?pos_paid=1&txn={txn['id']}",
        "cancel_url": f"{dashboard_url}?pos_cancelled=1&txn={txn['id']}",
        "metadata": {
            "auraflow_pos_transaction_id": txn["id"],
            "auraflow_org_schema": ctx.schema_name,
        },
    }
    if member.get("stripe_customer_id"):
        checkout_params["customer"] = member["stripe_customer_id"]

    session = await asyncio.to_thread(
        lambda: _stripe.checkout.Session.create(**checkout_params)
    )

    # Email the link
    async with get_global_db() as gdb:
        org = await gdb.fetchrow("SELECT name FROM af_global.organizations WHERE id = $1", org_id)
    studio_name = org["name"] if org else "the studio"

    item_lines = "".join(
        f"<tr><td style='padding:4px 12px;'>{li.get('product_name','Item')} x{li['quantity']}</td>"
        f"<td style='padding:4px 12px; text-align:right;'>${li['total_cents']/100:.2f}</td></tr>"
        for li in txn.get("line_items", [])
    )
    total_display = f"${txn['total_cents']/100:.2f}"

    html = f"""
    <h2>Payment Request from {studio_name}</h2>
    <p>Hi {member['first_name']},</p>
    <p>Here's your order from <strong>{studio_name}</strong>:</p>
    <table style="margin:16px 0; border-collapse:collapse; width:100%;">
      {item_lines}
      <tr style="border-top:1px solid #ddd; font-weight:600;">
        <td style="padding:8px 12px;">Total</td>
        <td style="padding:8px 12px; text-align:right;">{total_display}</td>
      </tr>
    </table>
    <p style="margin:24px 0;">
      <a href="{session_url}" style="background-color:#4f46e5; color:white; padding:12px 24px; border-radius:6px; text-decoration:none; font-weight:600;">
        Pay {total_display}
      </a>
    </p>
    <p>— {studio_name}</p>
    """
    email_svc = EmailService()
    await email_svc.send_email(
        to_email=member["email"],
        subject=f"Payment Request from {studio_name} — {total_display}",
        html_content=html,
        member_id=txn["member_id"],
        email_type="payment_request",
    )

    return {"data": {"payment_url": session.url, "emailed": True}}


@router.post("/transactions/{transaction_id}/checkout")
async def create_in_person_checkout(
    transaction_id: str,
    user=Depends(get_current_user),
    _=Depends(require_permission("retail.checkout_transaction")),
):
    """Create a Stripe Checkout URL for completing a pending transaction in person."""
    txn = await pos_svc.get_transaction(transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if txn["status"] != "pending":
        raise HTTPException(status_code=400, detail="Transaction is not pending")

    from app.core.tenant_context import get_organization_id, require_tenant_context
    from app.services.payments.stripe_service import _get_org_stripe_key, _stripe_key_for_org
    from app.core.config import settings
    import stripe as _stripe
    import asyncio

    org_id = get_organization_id()
    ctx = require_tenant_context()
    direct_key = await _get_org_stripe_key(org_id)
    api_key = _stripe_key_for_org(direct_key)

    line_items = []
    for li in txn.get("line_items", []):
        line_items.append({
            "price_data": {
                "currency": "usd",
                "unit_amount": li["unit_price_cents"] + (li["tax_cents"] // li["quantity"] if li["quantity"] else 0),
                "product_data": {"name": li.get("product_name", "Retail Item")},
            },
            "quantity": li["quantity"],
        })

    dashboard_url = f"{settings.APP_URL}/{ctx.slug}/dashboard/pos"
    checkout_params = {
        "api_key": api_key,
        "mode": "payment",
        "line_items": line_items,
        "success_url": f"{dashboard_url}?pos_paid=1&txn={txn['id']}",
        "cancel_url": f"{dashboard_url}?pos_cancelled=1&txn={txn['id']}",
        "metadata": {
            "auraflow_pos_transaction_id": txn["id"],
            "auraflow_org_schema": ctx.schema_name,
        },
    }

    if txn.get("member_id"):
        from app.db.session import get_tenant_db
        async with get_tenant_db() as db:
            member = await db.fetchrow(
                "SELECT stripe_customer_id FROM members WHERE id = $1", txn["member_id"]
            )
        if member and member.get("stripe_customer_id"):
            checkout_params["customer"] = member["stripe_customer_id"]

    session = await asyncio.to_thread(
        lambda: _stripe.checkout.Session.create(**checkout_params)
    )

    return {"data": {"checkout_url": session.url}}


@router.get("/reports/inventory")
async def inventory_report(
    user=Depends(get_current_user),
    _=Depends(require_permission("retail.view_reports")),
):
    """Get current inventory value report."""
    report = await pos_svc.get_inventory_report()
    return {"data": report}
