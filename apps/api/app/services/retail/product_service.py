"""AuraFlow — Product Service

CRUD operations for retail products with inventory integration.
"""
import uuid

from app.core.logging import logger
from app.db.session import get_tenant_db


class ProductService:

    async def list_products(
        self,
        category: str | None = None,
        active_only: bool = True,
        search: str | None = None,
    ) -> list[dict]:
        """List products with optional filters, joined with inventory for stock level."""
        async with get_tenant_db() as db:
            conditions = []
            params = []
            idx = 1

            if active_only:
                conditions.append(f"p.active = TRUE")

            if category:
                conditions.append(f"p.category = ${idx}")
                params.append(category)
                idx += 1

            if search:
                conditions.append(f"(p.name ILIKE ${idx} OR p.sku ILIKE ${idx})")
                params.append(f"%{search}%")
                idx += 1

            where = "WHERE " + " AND ".join(conditions) if conditions else ""

            rows = await db.fetch(
                f"""
                SELECT p.*, i.quantity_on_hand, i.reorder_point, i.reorder_quantity
                FROM products p
                LEFT JOIN inventory i ON i.product_id = p.id
                {where}
                ORDER BY p.category, p.name
                """,
                *params,
            )
        return [_product_to_dict(r) for r in rows]

    async def get_product(self, product_id: str) -> dict | None:
        """Get a single product with inventory data."""
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                SELECT p.*, i.quantity_on_hand, i.reorder_point, i.reorder_quantity
                FROM products p
                LEFT JOIN inventory i ON i.product_id = p.id
                WHERE p.id = $1
                """,
                product_id,
            )
        return _product_to_dict(row) if row else None

    async def get_by_sku(self, sku: str) -> dict | None:
        """Lookup product by SKU (case-insensitive)."""
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                SELECT p.*, i.quantity_on_hand, i.reorder_point, i.reorder_quantity
                FROM products p
                LEFT JOIN inventory i ON i.product_id = p.id
                WHERE LOWER(p.sku) = LOWER($1) AND p.active = TRUE
                """,
                sku,
            )
        return _product_to_dict(row) if row else None

    async def create_product(self, data: dict) -> dict:
        """Create a product and its default inventory row atomically."""
        product_id = str(uuid.uuid4())
        inventory_id = str(uuid.uuid4())

        async with get_tenant_db() as db:
            await db.execute(
                """
                INSERT INTO products (id, studio_id, name, description, sku,
                    price_cents, cost_cents, category, tax_rate, image_url)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                product_id,
                data.get("studio_id"),
                data["name"],
                data.get("description"),
                data.get("sku"),
                data.get("price_cents", 0),
                data.get("cost_cents", 0),
                data.get("category", "retail"),
                data.get("tax_rate", 0.0),
                data.get("image_url"),
            )
            await db.execute(
                """
                INSERT INTO inventory (id, product_id, reorder_point, reorder_quantity)
                VALUES ($1, $2, $3, $4)
                """,
                inventory_id,
                product_id,
                data.get("reorder_point", 5),
                data.get("reorder_quantity", 20),
            )
            row = await db.fetchrow(
                """
                SELECT p.*, i.quantity_on_hand, i.reorder_point, i.reorder_quantity
                FROM products p
                LEFT JOIN inventory i ON i.product_id = p.id
                WHERE p.id = $1
                """,
                product_id,
            )

        logger.info("Product created", product_id=product_id, name=data["name"])
        return _product_to_dict(row)

    async def update_product(self, product_id: str, data: dict) -> dict | None:
        """Update product fields (PATCH-style)."""
        allowed = {
            "name", "description", "sku", "price_cents", "cost_cents",
            "category", "tax_rate", "image_url", "active",
        }
        updates = {k: v for k, v in data.items() if k in allowed and v is not None}
        if not updates:
            return await self.get_product(product_id)

        set_clauses = []
        params = [product_id]
        idx = 2
        for key, val in updates.items():
            set_clauses.append(f"{key} = ${idx}")
            params.append(val)
            idx += 1
        set_clauses.append("updated_at = NOW()")

        async with get_tenant_db() as db:
            await db.execute(
                f"UPDATE products SET {', '.join(set_clauses)} WHERE id = $1",
                *params,
            )
            row = await db.fetchrow(
                """
                SELECT p.*, i.quantity_on_hand, i.reorder_point, i.reorder_quantity
                FROM products p
                LEFT JOIN inventory i ON i.product_id = p.id
                WHERE p.id = $1
                """,
                product_id,
            )
        return _product_to_dict(row) if row else None

    async def delete_product(self, product_id: str) -> bool:
        """Soft-delete a product (set active=FALSE)."""
        async with get_tenant_db() as db:
            result = await db.execute(
                "UPDATE products SET active = FALSE, updated_at = NOW() WHERE id = $1",
                product_id,
            )
        return "UPDATE 1" in result


# ── Serialization ─────────────────────────────────────────────────────────────

def _product_to_dict(row) -> dict:
    d = dict(row)
    for k in ("id", "studio_id"):
        if d.get(k):
            d[k] = str(d[k])
    for k in ("created_at", "updated_at"):
        if d.get(k):
            d[k] = d[k].isoformat()
    if d.get("tax_rate") is not None:
        d["tax_rate"] = float(d["tax_rate"])
    return d
