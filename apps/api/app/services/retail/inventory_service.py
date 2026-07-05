"""AuraFlow — Inventory Service

Stock tracking, adjustments, alerts, and transaction history.
"""
import uuid

from app.core.logging import logger
from app.db.session import get_tenant_db


class InventoryService:

    async def list_inventory(self, low_stock_only: bool = False) -> list[dict]:
        """List all inventory with product info. Filter to low stock if requested."""
        async with get_tenant_db() as db:
            if low_stock_only:
                rows = await db.fetch(
                    """
                    SELECT i.*, p.name, p.sku, p.category, p.price_cents
                    FROM inventory i
                    JOIN products p ON p.id = i.product_id
                    WHERE p.active = TRUE AND i.quantity_on_hand <= i.reorder_point
                    ORDER BY i.quantity_on_hand ASC, p.name
                    """
                )
            else:
                rows = await db.fetch(
                    """
                    SELECT i.*, p.name, p.sku, p.category, p.price_cents
                    FROM inventory i
                    JOIN products p ON p.id = i.product_id
                    WHERE p.active = TRUE
                    ORDER BY (i.quantity_on_hand <= i.reorder_point) DESC, p.name
                    """
                )
        return [_inv_to_dict(r) for r in rows]

    async def adjust_stock(
        self,
        product_id: str,
        quantity_change: int,
        reason: str,
        notes: str | None = None,
        created_by: str | None = None,
        reference_id: str | None = None,
    ) -> dict:
        """Atomically adjust stock and record in ledger."""
        async with get_tenant_db() as db:
            # Verify product exists
            inv = await db.fetchrow(
                "SELECT quantity_on_hand FROM inventory WHERE product_id = $1",
                product_id,
            )
            if inv is None:
                raise ValueError(f"No inventory record for product {product_id}")

            new_qty = inv["quantity_on_hand"] + quantity_change
            if new_qty < 0:
                raise ValueError(
                    f"Insufficient stock: have {inv['quantity_on_hand']}, "
                    f"tried to adjust by {quantity_change}"
                )

            await db.execute(
                """
                UPDATE inventory
                SET quantity_on_hand = $2, updated_at = NOW()
                WHERE product_id = $1
                """,
                product_id, new_qty,
            )

            txn_id = str(uuid.uuid4())
            await db.execute(
                """
                INSERT INTO inventory_transactions
                    (id, product_id, quantity_change, reason, reference_id, notes, created_by)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                txn_id, product_id, quantity_change, reason,
                reference_id, notes, created_by,
            )

            row = await db.fetchrow(
                """
                SELECT i.*, p.name, p.sku, p.category, p.price_cents
                FROM inventory i
                JOIN products p ON p.id = i.product_id
                WHERE i.product_id = $1
                """,
                product_id,
            )

        logger.info(
            "Stock adjusted",
            product_id=product_id,
            change=quantity_change,
            reason=reason,
            new_qty=new_qty,
        )
        return _inv_to_dict(row)

    async def get_transaction_history(
        self, product_id: str, limit: int = 50
    ) -> list[dict]:
        """Get inventory transaction history for a product."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT it.*
                FROM inventory_transactions it
                WHERE it.product_id = $1
                ORDER BY it.created_at DESC
                LIMIT $2
                """,
                product_id, limit,
            )
        return [_inv_txn_to_dict(r) for r in rows]

    async def get_low_stock_alerts(self) -> list[dict]:
        """Get products below reorder point."""
        return await self.list_inventory(low_stock_only=True)


# ── Serialization ─────────────────────────────────────────────────────────────

def _inv_to_dict(row) -> dict:
    d = dict(row)
    for k in ("id", "product_id"):
        if d.get(k):
            d[k] = str(d[k])
    for k in ("created_at", "updated_at", "last_counted_at"):
        if d.get(k):
            d[k] = d[k].isoformat()
    return d


def _inv_txn_to_dict(row) -> dict:
    d = dict(row)
    for k in ("id", "product_id", "reference_id", "created_by"):
        if d.get(k):
            d[k] = str(d[k])
    if d.get("created_at"):
        d["created_at"] = d["created_at"].isoformat()
    return d
