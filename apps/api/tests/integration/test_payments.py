"""AuraFlow — Payment & Transaction Integration Tests

Tests transaction CRUD, revenue summary, refunds, failed payment tracking,
Stripe Checkout sessions, Customer Portal sessions, and webhook handling.
Stripe API calls are mocked since we don't want to call Stripe in tests.
"""
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestTransactions:

    async def _create_member(self, client, headers):
        resp = await client.post("/api/v1/members", json={
            "first_name": "Pay",
            "last_name": f"Member-{uuid.uuid4().hex[:6]}",
            "email": f"pay-{uuid.uuid4().hex[:8]}@test.auraflow.dev",
        }, headers=headers)
        assert resp.status_code == 201
        return resp.json()

    async def test_record_transaction(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        member = await self._create_member(client, headers)

        resp = await client.post("/api/v1/payments/transactions", json={
            "member_id": member["id"],
            "amount_cents": 5000,
            "type": "payment",
            "description": "Drop-in class",
        }, headers=headers)
        assert resp.status_code == 200
        txn = resp.json()["data"]
        assert txn["amount_cents"] == 5000
        assert txn["type"] == "payment"
        assert txn["status"] == "completed"
        assert txn["member_id"] == member["id"]
        # Fee should be calculated
        assert txn["fee_cents"] == 100  # 2% of 5000
        assert txn["net_amount_cents"] == 4900

    async def test_list_transactions(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        member = await self._create_member(client, headers)

        # Create two transactions
        for desc in ["Class A", "Class B"]:
            await client.post("/api/v1/payments/transactions", json={
                "member_id": member["id"],
                "amount_cents": 2500,
                "description": desc,
            }, headers=headers)

        resp = await client.get("/api/v1/payments/transactions", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]) >= 2

    async def test_list_transactions_by_member(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        member = await self._create_member(client, headers)

        await client.post("/api/v1/payments/transactions", json={
            "member_id": member["id"],
            "amount_cents": 3000,
            "description": "Filter test",
        }, headers=headers)

        resp = await client.get(
            f"/api/v1/payments/transactions?member_id={member['id']}",
            headers=headers,
        )
        assert resp.status_code == 200
        txns = resp.json()["data"]
        assert len(txns) >= 1
        assert all(t["member_id"] == member["id"] for t in txns)

    async def test_get_transaction(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        member = await self._create_member(client, headers)

        create_resp = await client.post("/api/v1/payments/transactions", json={
            "member_id": member["id"],
            "amount_cents": 7500,
            "description": "Private session",
        }, headers=headers)
        txn_id = create_resp.json()["data"]["id"]

        resp = await client.get(f"/api/v1/payments/transactions/{txn_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == txn_id
        assert resp.json()["data"]["amount_cents"] == 7500

    async def test_transaction_not_found(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/v1/payments/transactions/{fake_id}", headers=headers)
        assert resp.status_code == 404

    async def test_refund_transaction(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        member = await self._create_member(client, headers)

        create_resp = await client.post("/api/v1/payments/transactions", json={
            "member_id": member["id"],
            "amount_cents": 10000,
            "description": "10-class pack",
        }, headers=headers)
        txn_id = create_resp.json()["data"]["id"]

        # Full refund
        resp = await client.post(f"/api/v1/payments/transactions/{txn_id}/refund", json={
            "reason": "Customer request",
        }, headers=headers)
        assert resp.status_code == 200
        refunded = resp.json()["data"]
        assert refunded["status"] == "refunded"
        assert refunded["refund_amount_cents"] == 10000
        assert refunded["refund_reason"] == "Customer request"

    async def test_partial_refund(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        member = await self._create_member(client, headers)

        create_resp = await client.post("/api/v1/payments/transactions", json={
            "member_id": member["id"],
            "amount_cents": 8000,
            "description": "Partial refund test",
        }, headers=headers)
        txn_id = create_resp.json()["data"]["id"]

        resp = await client.post(f"/api/v1/payments/transactions/{txn_id}/refund", json={
            "amount_cents": 3000,
            "reason": "Partial refund",
        }, headers=headers)
        assert resp.status_code == 200
        refunded = resp.json()["data"]
        assert refunded["status"] == "partially_refunded"
        assert refunded["refund_amount_cents"] == 3000

    async def test_lifetime_revenue_updated(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        member = await self._create_member(client, headers)

        await client.post("/api/v1/payments/transactions", json={
            "member_id": member["id"],
            "amount_cents": 5000,
            "description": "Revenue check",
        }, headers=headers)

        # Check member's lifetime revenue
        resp = await client.get(f"/api/v1/members/{member['id']}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["lifetime_revenue_cents"] >= 5000


@pytest.mark.asyncio
class TestRevenueSummary:

    async def _create_member_and_transaction(self, client, headers, amount=5000):
        member_resp = await client.post("/api/v1/members", json={
            "first_name": "Rev",
            "last_name": f"Test-{uuid.uuid4().hex[:6]}",
            "email": f"rev-{uuid.uuid4().hex[:8]}@test.auraflow.dev",
        }, headers=headers)
        member = member_resp.json()
        await client.post("/api/v1/payments/transactions", json={
            "member_id": member["id"],
            "amount_cents": amount,
            "description": "Revenue test",
        }, headers=headers)
        return member

    async def test_revenue_summary(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        await self._create_member_and_transaction(client, headers, amount=10000)
        await self._create_member_and_transaction(client, headers, amount=5000)

        resp = await client.get("/api/v1/payments/revenue/summary?days=30", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_revenue"] >= 15000
        assert data["transaction_count"] >= 2
        assert data["total_fees"] >= 0
        assert data["net_revenue"] >= 0


@pytest.mark.asyncio
class TestFailedPayments:

    async def test_list_failed_payments_empty(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        resp = await client.get("/api/v1/payments/failed-payments", headers=headers)
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)


@pytest.mark.asyncio
class TestCommunicationLog:

    async def test_list_communications_empty(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        resp = await client.get("/api/v1/payments/communications", headers=headers)
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)

    async def test_communications_filter_by_member(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        fake_member = str(uuid.uuid4())
        resp = await client.get(
            f"/api/v1/payments/communications?member_id={fake_member}",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"] == []


@pytest.mark.asyncio
class TestConnectStatus:

    async def test_connect_status_not_connected(self, client: AsyncClient, registered_owner_with_studio):
        """Without Stripe keys, Connect status should show not connected."""
        headers = registered_owner_with_studio["headers"]
        resp = await client.get("/api/v1/payments/connect/status", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is False


@pytest.mark.asyncio
class TestCheckoutSession:

    async def _create_member_and_membership_type(self, client, headers, studio_id):
        """Helper: create a member and a public membership type."""
        member_resp = await client.post("/api/v1/members", json={
            "first_name": "Checkout",
            "last_name": f"Test-{uuid.uuid4().hex[:6]}",
            "email": f"checkout-{uuid.uuid4().hex[:8]}@test.auraflow.dev",
        }, headers=headers)
        assert member_resp.status_code == 201
        member = member_resp.json()

        type_resp = await client.post("/api/v1/memberships/types", json={
            "studio_id": studio_id,
            "name": "Unlimited Monthly",
            "type": "unlimited",
            "price_cents": 14900,
            "billing_period": "monthly",
        }, headers=headers)
        assert type_resp.status_code == 201
        mtype = type_resp.json()

        return member, mtype

    @patch("app.services.payments.stripe_service.StripeService.get_or_create_customer")
    @patch("stripe.checkout.Session.create")
    async def test_create_checkout_session(
        self, mock_checkout_create, mock_get_customer,
        client: AsyncClient, registered_owner_with_studio
    ):
        """POST /payments/checkout creates a Stripe Checkout session."""
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        member, mtype = await self._create_member_and_membership_type(client, headers, studio_id)

        mock_get_customer.return_value = "cus_test_12345"
        mock_session = MagicMock()
        mock_session.id = "cs_test_session_id"
        mock_session.url = "https://checkout.stripe.com/cs_test_session_id"
        mock_checkout_create.return_value = mock_session

        resp = await client.post("/api/v1/payments/checkout", json={
            "member_id": member["id"],
            "membership_type_id": mtype["id"],
            "success_url": "http://localhost/success",
            "cancel_url": "http://localhost/cancel",
        }, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["session_id"] == "cs_test_session_id"
        assert "checkout.stripe.com" in data["url"]

    async def test_checkout_invalid_membership_type(self, client: AsyncClient, registered_owner_with_studio):
        """Checkout with a nonexistent membership type returns 400."""
        headers = registered_owner_with_studio["headers"]
        member_resp = await client.post("/api/v1/members", json={
            "first_name": "Bad",
            "last_name": "Checkout",
            "email": f"badcheckout-{uuid.uuid4().hex[:8]}@test.auraflow.dev",
        }, headers=headers)
        member = member_resp.json()

        resp = await client.post("/api/v1/payments/checkout", json={
            "member_id": member["id"],
            "membership_type_id": str(uuid.uuid4()),
            "success_url": "http://localhost/success",
            "cancel_url": "http://localhost/cancel",
        }, headers=headers)
        assert resp.status_code == 400

    async def test_checkout_invalid_member(self, client: AsyncClient, registered_owner_with_studio):
        """Checkout with a nonexistent member returns 400."""
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        type_resp = await client.post("/api/v1/memberships/types", json={
            "studio_id": studio_id,
            "name": "Bad Member Test",
            "type": "unlimited",
            "price_cents": 14900,
            "billing_period": "monthly",
        }, headers=headers)
        mtype = type_resp.json()

        resp = await client.post("/api/v1/payments/checkout", json={
            "member_id": str(uuid.uuid4()),
            "membership_type_id": mtype["id"],
            "success_url": "http://localhost/success",
            "cancel_url": "http://localhost/cancel",
        }, headers=headers)
        assert resp.status_code == 400


@pytest.mark.asyncio
class TestCustomerPortal:

    @patch("stripe.billing_portal.Session.create")
    async def test_portal_no_stripe_customer(
        self, mock_portal_create,
        client: AsyncClient, registered_owner_with_studio
    ):
        """Portal session for member without stripe_customer_id returns 400."""
        headers = registered_owner_with_studio["headers"]
        member_resp = await client.post("/api/v1/members", json={
            "first_name": "Portal",
            "last_name": "Test",
            "email": f"portal-{uuid.uuid4().hex[:8]}@test.auraflow.dev",
        }, headers=headers)
        member = member_resp.json()

        resp = await client.post("/api/v1/payments/portal", json={
            "member_id": member["id"],
            "return_url": "http://localhost/dashboard",
        }, headers=headers)
        # Member has no stripe_customer_id, should fail
        assert resp.status_code == 400


@pytest.mark.asyncio
class TestWebhookCheckoutCompleted:

    async def _setup_member_and_type(self, client, headers, studio_id):
        """Create member and membership type for webhook tests."""
        member_resp = await client.post("/api/v1/members", json={
            "first_name": "Webhook",
            "last_name": f"Test-{uuid.uuid4().hex[:6]}",
            "email": f"webhook-{uuid.uuid4().hex[:8]}@test.auraflow.dev",
        }, headers=headers)
        member = member_resp.json()

        type_resp = await client.post("/api/v1/memberships/types", json={
            "studio_id": studio_id,
            "name": "Webhook Test Plan",
            "type": "unlimited",
            "price_cents": 9900,
            "billing_period": "monthly",
        }, headers=headers)
        mtype = type_resp.json()
        return member, mtype

    @patch("app.services.payments.webhook_handler.StripeWebhookHandler.verify_signature")
    @patch("app.services.email.email_service.EmailService.send_payment_receipt")
    async def test_checkout_completed_assigns_membership(
        self, mock_send_email, mock_verify,
        client: AsyncClient, registered_owner_with_studio
    ):
        """checkout.session.completed webhook assigns membership to member."""
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        member, mtype = await self._setup_member_and_type(client, headers, studio_id)

        mock_send_email.return_value = None

        # Build a fake Stripe checkout.session.completed event
        event = {
            "id": f"evt_{uuid.uuid4().hex[:16]}",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": f"cs_{uuid.uuid4().hex[:16]}",
                    "payment_intent": f"pi_{uuid.uuid4().hex[:16]}",
                    "subscription": f"sub_{uuid.uuid4().hex[:16]}",
                    "amount_total": 9900,
                    "metadata": {
                        "auraflow_member_id": member["id"],
                        "auraflow_membership_type_id": mtype["id"],
                        "auraflow_org_schema": "af_tenant_" + registered_owner_with_studio['org_slug'].replace("-", "_"),
                        "type_name": "Webhook Test Plan",
                    },
                },
            },
        }
        mock_verify.return_value = event

        resp = await client.post(
            "/webhooks/stripe",
            content=b"fake_payload",
            headers={"stripe-signature": "fake_sig"},
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["status"] == "processed"
        assert result["event"] == "checkout.session.completed"
        assert "membership_id" in result

        # Verify membership was actually created
        mm_resp = await client.get(
            f"/api/v1/memberships/member/{member['id']}",
            headers=headers,
        )
        assert mm_resp.status_code == 200
        memberships = mm_resp.json()
        assert len(memberships) >= 1
        active = [m for m in memberships if m["status"] == "active"]
        assert len(active) >= 1

        # Verify transaction was recorded
        txn_resp = await client.get(
            f"/api/v1/payments/transactions?member_id={member['id']}",
            headers=headers,
        )
        assert txn_resp.status_code == 200
        txns = txn_resp.json()["data"]
        assert len(txns) >= 1
        assert txns[0]["amount_cents"] == 9900
        assert txns[0]["status"] == "completed"

    @patch("app.services.payments.webhook_handler.StripeWebhookHandler.verify_signature")
    async def test_checkout_completed_missing_metadata_ignored(
        self, mock_verify,
        client: AsyncClient, registered_owner_with_studio
    ):
        """checkout.session.completed without metadata is ignored."""
        event = {
            "id": "evt_test_no_meta",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_no_meta",
                    "amount_total": 5000,
                    "metadata": {},
                },
            },
        }
        mock_verify.return_value = event

        resp = await client.post(
            "/webhooks/stripe",
            content=b"fake_payload",
            headers={"stripe-signature": "fake_sig"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    @patch("app.services.payments.webhook_handler.StripeWebhookHandler.verify_signature")
    async def test_unhandled_event_type_ignored(
        self, mock_verify,
        client: AsyncClient, registered_owner_with_studio
    ):
        """Unknown Stripe events are acknowledged but ignored."""
        event = {
            "id": "evt_test_unknown",
            "type": "some.random.event",
            "data": {"object": {}},
        }
        mock_verify.return_value = event

        resp = await client.post(
            "/webhooks/stripe",
            content=b"fake_payload",
            headers={"stripe-signature": "fake_sig"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"
