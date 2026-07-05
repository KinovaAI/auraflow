"""AuraFlow — POS Service

Point-of-sale transactions, refunds, and reporting.
"""
import uuid
from datetime import date
from decimal import Decimal

from app.core.logging import logger
from app.db.session import get_tenant_db


class POSService:

    async def create_transaction(
        self,
        items: list[dict],
        payment_method: str,
        member_id: str | None = None,
        created_by: str | None = None,
        stripe_payment_id: str | None = None,
        notes: str | None = None,
        gift_card_code: str | None = None,
    ) -> dict:
        """Create a POS sale atomically: transaction + line items + inventory decrement.

        When payment_method='gift_card', `gift_card_code` is required and the
        card's balance must cover the full sale total — partial / split-tender
        is not supported in this v1. The gift-card debit + redemption row
        run on the same connection as the sale itself so a rollback walks
        them all back together.
        """
        if payment_method == "gift_card" and not gift_card_code:
            raise ValueError("gift_card_code required when payment_method='gift_card'")

        txn_id = str(uuid.uuid4())

        async with get_tenant_db() as db:
            # Load all products in one query
            product_ids = [item["product_id"] for item in items]
            placeholders = ", ".join(f"${i+1}" for i in range(len(product_ids)))
            products = await db.fetch(
                f"""
                SELECT p.*, i.quantity_on_hand
                FROM products p
                LEFT JOIN inventory i ON i.product_id = p.id
                WHERE p.id IN ({placeholders}) AND p.active = TRUE
                """,
                *product_ids,
            )
            product_map = {str(p["id"]): p for p in products}

            # Validate all products exist
            for item in items:
                if item["product_id"] not in product_map:
                    raise ValueError(f"Product not found or inactive: {item['product_id']}")

            # Calculate totals
            subtotal_cents = 0
            tax_cents = 0
            line_items_data = []

            for item in items:
                product = product_map[item["product_id"]]
                qty = item["quantity"]
                unit_price = product["price_cents"]
                line_subtotal = unit_price * qty
                line_tax = round(float(line_subtotal) * float(product["tax_rate"]))
                line_total = line_subtotal + line_tax

                subtotal_cents += line_subtotal
                tax_cents += line_tax

                line_items_data.append({
                    "id": str(uuid.uuid4()),
                    "product_id": item["product_id"],
                    "quantity": qty,
                    "unit_price_cents": unit_price,
                    "tax_cents": line_tax,
                    "total_cents": line_total,
                })

            total_cents = subtotal_cents + tax_cents
            status = "pending" if payment_method in ("card", "stripe", "send_payment_link") else "completed"

            # Atomic block — gift-card debit, txn insert, line items, and
            # inventory decrement all roll back together on any failure.
            async with db.transaction():
              # Pre-validate gift card balance covers the full total. We
              # don't support split-tender at POS yet; if the card has
              # insufficient balance the staff member should pick a
              # different payment method or top up the card first.
              gift_card_redemption = None
              if payment_method == "gift_card":
                  if not member_id:
                      raise ValueError("Gift card payments require a member_id (which gift card holder is paying)")
                  from app.services.payments.gift_card_service import GiftCardService
                  gc_svc = GiftCardService()
                  bal = await gc_svc.check_balance(gift_card_code)
                  if bal["balance_cents"] < total_cents:
                      raise ValueError(
                          f"Gift card balance ${bal['balance_cents']/100:.2f} is less "
                          f"than sale total ${total_cents/100:.2f}"
                      )
                  gift_card_redemption = await gc_svc.apply_to_transaction(
                      code=gift_card_code,
                      transaction_amount_cents=total_cents,
                      member_id=member_id,
                      db=db,
                      transaction_id=txn_id,
                  )

              # Insert transaction
              await db.execute(
                  """
                  INSERT INTO pos_transactions
                      (id, member_id, subtotal_cents, tax_cents, total_cents,
                       payment_method, stripe_payment_id, status, notes, created_by)
                  VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                  """,
                  txn_id, member_id, subtotal_cents, tax_cents, total_cents,
                  payment_method, stripe_payment_id, status, notes, created_by,
              )

              # Insert line items and decrement inventory
              for li in line_items_data:
                await db.execute(
                    """
                    INSERT INTO pos_line_items
                        (id, transaction_id, product_id, quantity,
                         unit_price_cents, tax_cents, total_cents)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    li["id"], txn_id, li["product_id"], li["quantity"],
                    li["unit_price_cents"], li["tax_cents"], li["total_cents"],
                )

                # Decrement inventory
                await db.execute(
                    """
                    UPDATE inventory
                    SET quantity_on_hand = GREATEST(0, quantity_on_hand - $2),
                        updated_at = NOW()
                    WHERE product_id = $1
                    """,
                    li["product_id"], li["quantity"],
                )

                # Record inventory transaction
                await db.execute(
                    """
                    INSERT INTO inventory_transactions
                        (id, product_id, quantity_change, reason, reference_id, created_by)
                    VALUES ($1, $2, $3, 'sale', $4, $5)
                    """,
                    str(uuid.uuid4()), li["product_id"],
                    -li["quantity"], txn_id, created_by,
                )

            # Fetch full transaction with line items
            txn_row = await db.fetchrow(
                "SELECT * FROM pos_transactions WHERE id = $1", txn_id
            )
            li_rows = await db.fetch(
                """
                SELECT pli.*, p.name AS product_name, p.sku
                FROM pos_line_items pli
                JOIN products p ON p.id = pli.product_id
                WHERE pli.transaction_id = $1
                """,
                txn_id,
            )

        logger.info(
            "POS sale",
            txn_id=txn_id,
            total=total_cents,
            items=len(items),
            method=payment_method,
        )
        result = _txn_to_dict(txn_row)
        result["line_items"] = [_line_item_to_dict(r) for r in li_rows]
        return result

    async def get_transaction(self, transaction_id: str) -> dict | None:
        """Get a POS transaction with line items."""
        async with get_tenant_db() as db:
            txn = await db.fetchrow(
                """
                SELECT pt.*, m.first_name AS member_first_name, m.last_name AS member_last_name
                FROM pos_transactions pt
                LEFT JOIN members m ON m.id = pt.member_id
                WHERE pt.id = $1
                """,
                transaction_id,
            )
            if not txn:
                return None
            items = await db.fetch(
                """
                SELECT pli.*, p.name AS product_name, p.sku
                FROM pos_line_items pli
                JOIN products p ON p.id = pli.product_id
                WHERE pli.transaction_id = $1
                """,
                transaction_id,
            )
        result = _txn_to_dict(txn)
        result["line_items"] = [_line_item_to_dict(r) for r in items]
        return result

    async def list_transactions(
        self,
        member_id: str | None = None,
        status: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """List POS transactions with optional filters."""
        async with get_tenant_db() as db:
            conditions = []
            params = []
            idx = 1

            if member_id:
                conditions.append(f"pt.member_id = ${idx}")
                params.append(member_id)
                idx += 1

            if status:
                conditions.append(f"pt.status = ${idx}")
                params.append(status)
                idx += 1

            if date_from:
                conditions.append(f"pt.created_at >= ${idx}")
                params.append(date_from)
                idx += 1

            if date_to:
                conditions.append(f"pt.created_at < ${idx}::date + INTERVAL '1 day'")
                params.append(date_to)
                idx += 1

            where = "WHERE " + " AND ".join(conditions) if conditions else ""

            params.extend([limit, offset])
            rows = await db.fetch(
                f"""
                SELECT pt.*, m.first_name AS member_first_name, m.last_name AS member_last_name
                FROM pos_transactions pt
                LEFT JOIN members m ON m.id = pt.member_id
                {where}
                ORDER BY pt.created_at DESC
                LIMIT ${idx} OFFSET ${idx + 1}
                """,
                *params,
            )
        return [_txn_to_dict(r) for r in rows]

    async def refund_transaction(
        self, transaction_id: str, reason: str = "requested_by_customer"
    ) -> dict:
        """Full refund: update status + restore inventory."""
        async with get_tenant_db() as db:
            txn = await db.fetchrow(
                "SELECT * FROM pos_transactions WHERE id = $1", transaction_id
            )
            if not txn:
                raise ValueError("Transaction not found")
            if txn["status"] in ("refunded", "voided"):
                raise ValueError(f"Transaction already {txn['status']}")

            # Update status
            await db.execute(
                """
                UPDATE pos_transactions
                SET status = 'refunded', notes = COALESCE(notes || E'\\n', '') || $2,
                    updated_at = NOW()
                WHERE id = $1
                """,
                transaction_id, f"Refund: {reason}",
            )

            # Restore inventory for each line item
            items = await db.fetch(
                "SELECT * FROM pos_line_items WHERE transaction_id = $1",
                transaction_id,
            )
            for item in items:
                await db.execute(
                    """
                    UPDATE inventory
                    SET quantity_on_hand = quantity_on_hand + $2, updated_at = NOW()
                    WHERE product_id = $1
                    """,
                    str(item["product_id"]), item["quantity"],
                )
                await db.execute(
                    """
                    INSERT INTO inventory_transactions
                        (id, product_id, quantity_change, reason, reference_id, notes)
                    VALUES ($1, $2, $3, 'adjustment', $4, 'Refund')
                    """,
                    str(uuid.uuid4()), str(item["product_id"]),
                    item["quantity"], transaction_id,
                )

            row = await db.fetchrow(
                "SELECT * FROM pos_transactions WHERE id = $1", transaction_id
            )

        logger.info("POS refund", txn_id=transaction_id, reason=reason)
        return _txn_to_dict(row)

    async def get_daily_summary(self, target_date: date) -> dict:
        """Daily cash drawer summary by payment method + top products."""
        async with get_tenant_db() as db:
            by_method = await db.fetch(
                """
                SELECT payment_method,
                       COUNT(*) AS transaction_count,
                       COALESCE(SUM(subtotal_cents), 0) AS subtotal,
                       COALESCE(SUM(tax_cents), 0) AS tax,
                       COALESCE(SUM(total_cents), 0) AS total
                FROM pos_transactions
                WHERE created_at::DATE = $1 AND status = 'completed'
                GROUP BY payment_method
                """,
                target_date,
            )
            top_products = await db.fetch(
                """
                SELECT p.name, SUM(pli.quantity) AS units_sold,
                       SUM(pli.total_cents) AS revenue
                FROM pos_line_items pli
                JOIN pos_transactions pt ON pt.id = pli.transaction_id
                JOIN products p ON p.id = pli.product_id
                WHERE pt.created_at::DATE = $1 AND pt.status = 'completed'
                GROUP BY p.name
                ORDER BY units_sold DESC
                LIMIT 10
                """,
                target_date,
            )

        grand_total = sum(r["total"] for r in by_method)
        return {
            "date": target_date.isoformat(),
            "by_method": [dict(r) for r in by_method],
            "grand_total_cents": grand_total,
            "top_products": [dict(r) for r in top_products],
        }

    async def get_sales_report(self, date_from: date, date_to: date) -> dict:
        """Revenue breakdown by category and product for date range."""
        async with get_tenant_db() as db:
            by_category = await db.fetch(
                """
                SELECT p.category,
                       COUNT(DISTINCT pt.id) AS transaction_count,
                       SUM(pli.quantity) AS units_sold,
                       SUM(pli.total_cents) AS revenue
                FROM pos_line_items pli
                JOIN pos_transactions pt ON pt.id = pli.transaction_id
                JOIN products p ON p.id = pli.product_id
                WHERE pt.created_at >= $1 AND pt.created_at < $2::date + INTERVAL '1 day'
                  AND pt.status = 'completed'
                GROUP BY p.category
                ORDER BY revenue DESC
                """,
                date_from, date_to,
            )
            by_product = await db.fetch(
                """
                SELECT p.name, p.category, p.sku,
                       SUM(pli.quantity) AS units_sold,
                       SUM(pli.total_cents) AS revenue
                FROM pos_line_items pli
                JOIN pos_transactions pt ON pt.id = pli.transaction_id
                JOIN products p ON p.id = pli.product_id
                WHERE pt.created_at >= $1 AND pt.created_at < $2::date + INTERVAL '1 day'
                  AND pt.status = 'completed'
                GROUP BY p.name, p.category, p.sku
                ORDER BY revenue DESC
                """,
                date_from, date_to,
            )
        return {
            "period_start": date_from.isoformat(),
            "period_end": date_to.isoformat(),
            "by_category": [dict(r) for r in by_category],
            "by_product": [dict(r) for r in by_product],
        }

    async def get_inventory_report(self) -> dict:
        """Current inventory value report."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT p.name, p.category, p.cost_cents, i.quantity_on_hand,
                       (p.cost_cents * i.quantity_on_hand) AS inventory_value_cents
                FROM inventory i
                JOIN products p ON p.id = i.product_id
                WHERE p.active = TRUE
                ORDER BY inventory_value_cents DESC
                """
            )
        items = [dict(r) for r in rows]
        total_value = sum(r.get("inventory_value_cents", 0) for r in items)
        return {
            "total_inventory_value_cents": total_value,
            "items": items,
        }


# ── Serialization ─────────────────────────────────────────────────────────────

def _txn_to_dict(row) -> dict:
    d = dict(row)
    for k in ("id", "member_id", "created_by"):
        if d.get(k):
            d[k] = str(d[k])
    for k in ("created_at", "updated_at"):
        if d.get(k):
            d[k] = d[k].isoformat()
    return d


def _line_item_to_dict(row) -> dict:
    d = dict(row)
    for k in ("id", "transaction_id", "product_id"):
        if d.get(k):
            d[k] = str(d[k])
    if d.get("created_at"):
        d["created_at"] = d["created_at"].isoformat()
    return d
