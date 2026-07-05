"""AuraFlow — Retail & POS Integration Tests"""
import uuid
from datetime import date

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestProducts:

    async def _create_product(self, client, headers, **overrides):
        data = {
            "name": f"Product-{uuid.uuid4().hex[:6]}",
            "price_cents": 999,
            "cost_cents": 400,
            "category": "retail",
            "tax_rate": 0.0875,
            "sku": f"SKU-{uuid.uuid4().hex[:8]}",
            **overrides,
        }
        resp = await client.post("/api/v1/retail/products", json=data, headers=headers)
        assert resp.status_code == 201
        return resp.json()["data"]

    async def test_create_product_with_inventory(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        product = await self._create_product(client, headers, name="Yoga Mat")

        assert product["name"] == "Yoga Mat"
        assert product["price_cents"] == 999
        assert product["active"] is True
        # Should have inventory row with qty=0
        assert product["quantity_on_hand"] == 0
        assert product["reorder_point"] == 5

    async def test_list_products(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        await self._create_product(client, headers, category="retail")
        await self._create_product(client, headers, category="beverages")

        resp = await client.get("/api/v1/retail/products", headers=headers)
        assert resp.status_code == 200
        products = resp.json()["data"]
        assert len(products) >= 2

    async def test_list_products_filter_category(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        await self._create_product(client, headers, category="beverages", name="Green Juice")

        resp = await client.get("/api/v1/retail/products?category=beverages", headers=headers)
        assert resp.status_code == 200
        products = resp.json()["data"]
        assert all(p["category"] == "beverages" for p in products)

    async def test_sku_lookup(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        sku = f"BARCODE-{uuid.uuid4().hex[:6]}"
        product = await self._create_product(client, headers, sku=sku)

        resp = await client.get(f"/api/v1/retail/products/sku/{sku}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == product["id"]

    async def test_update_product(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        product = await self._create_product(client, headers)

        resp = await client.put(
            f"/api/v1/retail/products/{product['id']}",
            json={"name": "Updated Name", "price_cents": 1299},
            headers=headers,
        )
        assert resp.status_code == 200
        updated = resp.json()["data"]
        assert updated["name"] == "Updated Name"
        assert updated["price_cents"] == 1299

    async def test_soft_delete_product(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        product = await self._create_product(client, headers)

        resp = await client.delete(f"/api/v1/retail/products/{product['id']}", headers=headers)
        assert resp.status_code == 204

        # Shouldn't show in active-only list
        resp = await client.get("/api/v1/retail/products?active_only=true", headers=headers)
        ids = [p["id"] for p in resp.json()["data"]]
        assert product["id"] not in ids

    async def test_search_products(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        unique = uuid.uuid4().hex[:8]
        await self._create_product(client, headers, name=f"Special-{unique}")

        resp = await client.get(f"/api/v1/retail/products?search={unique}", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]) >= 1


@pytest.mark.asyncio
class TestInventory:

    async def _create_product(self, client, headers, **overrides):
        data = {
            "name": f"InvProd-{uuid.uuid4().hex[:6]}",
            "price_cents": 500,
            "cost_cents": 200,
            "category": "retail",
            **overrides,
        }
        resp = await client.post("/api/v1/retail/products", json=data, headers=headers)
        assert resp.status_code == 201
        return resp.json()["data"]

    async def test_restock(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        product = await self._create_product(client, headers)

        resp = await client.post("/api/v1/retail/inventory/adjust", json={
            "product_id": product["id"],
            "quantity_change": 25,
            "reason": "restock",
            "notes": "Initial stock",
        }, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["quantity_on_hand"] == 25

    async def test_adjustment_negative(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        product = await self._create_product(client, headers)

        # Restock first
        await client.post("/api/v1/retail/inventory/adjust", json={
            "product_id": product["id"],
            "quantity_change": 10,
            "reason": "restock",
        }, headers=headers)

        # Remove some
        resp = await client.post("/api/v1/retail/inventory/adjust", json={
            "product_id": product["id"],
            "quantity_change": -3,
            "reason": "shrinkage",
            "notes": "Damaged",
        }, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["quantity_on_hand"] == 7

    async def test_low_stock_alert(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        product = await self._create_product(client, headers)
        # Product starts at 0 qty, reorder_point defaults to 5 => already low stock

        resp = await client.get("/api/v1/retail/inventory/alerts/low-stock", headers=headers)
        assert resp.status_code == 200
        ids = [i["product_id"] for i in resp.json()["data"]]
        assert product["id"] in ids

    async def test_inventory_history(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        product = await self._create_product(client, headers)

        # Make 2 adjustments
        await client.post("/api/v1/retail/inventory/adjust", json={
            "product_id": product["id"],
            "quantity_change": 20,
            "reason": "restock",
        }, headers=headers)
        await client.post("/api/v1/retail/inventory/adjust", json={
            "product_id": product["id"],
            "quantity_change": -5,
            "reason": "adjustment",
        }, headers=headers)

        resp = await client.get(
            f"/api/v1/retail/inventory/{product['id']}/history",
            headers=headers,
        )
        assert resp.status_code == 200
        history = resp.json()["data"]
        assert len(history) >= 2


@pytest.mark.asyncio
class TestPOS:

    async def _create_stocked_product(self, client, headers, qty=10, **overrides):
        """Create a product and stock it."""
        data = {
            "name": f"POSProd-{uuid.uuid4().hex[:6]}",
            "price_cents": 1000,
            "cost_cents": 500,
            "category": "retail",
            "tax_rate": 0.0875,
            **overrides,
        }
        resp = await client.post("/api/v1/retail/products", json=data, headers=headers)
        assert resp.status_code == 201
        product = resp.json()["data"]

        # Stock it
        await client.post("/api/v1/retail/inventory/adjust", json={
            "product_id": product["id"],
            "quantity_change": qty,
            "reason": "opening_count",
        }, headers=headers)

        return product

    async def test_cash_sale(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        product = await self._create_stocked_product(client, headers, qty=10)

        resp = await client.post("/api/v1/retail/transactions", json={
            "items": [{"product_id": product["id"], "quantity": 2}],
            "payment_method": "cash",
        }, headers=headers)
        assert resp.status_code == 201
        txn = resp.json()["data"]
        assert txn["status"] == "completed"
        assert txn["payment_method"] == "cash"
        assert txn["subtotal_cents"] == 2000  # 2 x $10
        assert txn["total_cents"] > txn["subtotal_cents"]  # tax added
        assert len(txn["line_items"]) == 1

        # Verify inventory decremented
        inv_resp = await client.get("/api/v1/retail/inventory", headers=headers)
        for item in inv_resp.json()["data"]:
            if item["product_id"] == product["id"]:
                assert item["quantity_on_hand"] == 8  # 10 - 2
                break

    async def test_multi_item_sale(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        p1 = await self._create_stocked_product(client, headers, qty=5, price_cents=500)
        p2 = await self._create_stocked_product(client, headers, qty=5, price_cents=800)

        resp = await client.post("/api/v1/retail/transactions", json={
            "items": [
                {"product_id": p1["id"], "quantity": 2},
                {"product_id": p2["id"], "quantity": 1},
            ],
            "payment_method": "cash",
        }, headers=headers)
        assert resp.status_code == 201
        txn = resp.json()["data"]
        assert txn["subtotal_cents"] == 1800  # 2*500 + 1*800
        assert len(txn["line_items"]) == 2

    async def test_tax_calculation(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        product = await self._create_stocked_product(
            client, headers, qty=5, price_cents=1000, tax_rate=0.10
        )

        resp = await client.post("/api/v1/retail/transactions", json={
            "items": [{"product_id": product["id"], "quantity": 1}],
            "payment_method": "cash",
        }, headers=headers)
        assert resp.status_code == 201
        txn = resp.json()["data"]
        assert txn["subtotal_cents"] == 1000
        assert txn["tax_cents"] == 100  # 10% of 1000
        assert txn["total_cents"] == 1100

    async def test_comp_sale(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        product = await self._create_stocked_product(client, headers, qty=5)

        resp = await client.post("/api/v1/retail/transactions", json={
            "items": [{"product_id": product["id"], "quantity": 1}],
            "payment_method": "comp",
        }, headers=headers)
        assert resp.status_code == 201
        assert resp.json()["data"]["payment_method"] == "comp"
        assert resp.json()["data"]["status"] == "completed"

    async def test_refund_restores_inventory(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        product = await self._create_stocked_product(client, headers, qty=10)

        # Make a sale
        sale_resp = await client.post("/api/v1/retail/transactions", json={
            "items": [{"product_id": product["id"], "quantity": 3}],
            "payment_method": "cash",
        }, headers=headers)
        txn_id = sale_resp.json()["data"]["id"]

        # Refund
        resp = await client.post(
            f"/api/v1/retail/transactions/{txn_id}/refund",
            json={"reason": "customer_return"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "refunded"

        # Verify inventory restored
        inv_resp = await client.get("/api/v1/retail/inventory", headers=headers)
        for item in inv_resp.json()["data"]:
            if item["product_id"] == product["id"]:
                assert item["quantity_on_hand"] == 10  # restored to original
                break

    async def test_double_refund_rejected(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        product = await self._create_stocked_product(client, headers, qty=5)

        sale_resp = await client.post("/api/v1/retail/transactions", json={
            "items": [{"product_id": product["id"], "quantity": 1}],
            "payment_method": "cash",
        }, headers=headers)
        txn_id = sale_resp.json()["data"]["id"]

        # First refund
        resp = await client.post(
            f"/api/v1/retail/transactions/{txn_id}/refund",
            json={"reason": "test"},
            headers=headers,
        )
        assert resp.status_code == 200

        # Second refund should fail
        resp = await client.post(
            f"/api/v1/retail/transactions/{txn_id}/refund",
            json={"reason": "test"},
            headers=headers,
        )
        assert resp.status_code == 400

    async def test_list_transactions(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        product = await self._create_stocked_product(client, headers, qty=20)

        # Make 2 sales
        await client.post("/api/v1/retail/transactions", json={
            "items": [{"product_id": product["id"], "quantity": 1}],
            "payment_method": "cash",
        }, headers=headers)
        await client.post("/api/v1/retail/transactions", json={
            "items": [{"product_id": product["id"], "quantity": 1}],
            "payment_method": "comp",
        }, headers=headers)

        resp = await client.get("/api/v1/retail/transactions", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]) >= 2

    async def test_daily_summary(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        product = await self._create_stocked_product(client, headers, qty=20, tax_rate=0.0)

        # Make a cash sale
        await client.post("/api/v1/retail/transactions", json={
            "items": [{"product_id": product["id"], "quantity": 2}],
            "payment_method": "cash",
        }, headers=headers)

        today = date.today().isoformat()
        resp = await client.get(f"/api/v1/retail/reports/daily?target_date={today}", headers=headers)
        assert resp.status_code == 200
        summary = resp.json()["data"]
        assert summary["grand_total_cents"] > 0
        assert len(summary["by_method"]) >= 1

    async def test_sales_report(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        product = await self._create_stocked_product(client, headers, qty=10, tax_rate=0.0)

        await client.post("/api/v1/retail/transactions", json={
            "items": [{"product_id": product["id"], "quantity": 1}],
            "payment_method": "cash",
        }, headers=headers)

        today = date.today().isoformat()
        resp = await client.get(
            f"/api/v1/retail/reports/sales?date_from={today}&date_to={today}",
            headers=headers,
        )
        assert resp.status_code == 200
        report = resp.json()["data"]
        assert len(report["by_category"]) >= 1
        assert len(report["by_product"]) >= 1
