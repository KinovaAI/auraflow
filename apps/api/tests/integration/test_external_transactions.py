"""AuraFlow — External transactions integration tests.

Exercises POST /api/v1/external/transactions — the api-key-authed endpoint
used by sibling products (wellness-emr, bioalign-pro) to record billing
for services rendered outside auraflow's POS (FMS, gait screen, etc).
"""
import uuid

import pytest
from httpx import AsyncClient


async def _create_member(client: AsyncClient, headers: dict) -> dict:
    resp = await client.post("/api/v1/members", json={
        "first_name": "Ext",
        "last_name": f"Member-{uuid.uuid4().hex[:6]}",
        "email": f"ext-{uuid.uuid4().hex[:8]}@test.auraflow.dev",
    }, headers=headers)
    assert resp.status_code == 201
    return resp.json()


async def _mint_api_key(client: AsyncClient, jwt_headers: dict) -> dict:
    """Create an api_key for the current tenant. Raw key returned once."""
    resp = await client.post("/api/v1/external/api-keys", json={
        "name": f"test-{uuid.uuid4().hex[:6]}",
        "scopes": ["payments:write", "payments:read", "members:read"],
    }, headers=jwt_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


@pytest.mark.asyncio
class TestExternalTransactions:

    async def test_record_external_transaction(self, client: AsyncClient, registered_owner_with_studio):
        jwt_headers = registered_owner_with_studio["headers"]
        member = await _create_member(client, jwt_headers)
        api_key = await _mint_api_key(client, jwt_headers)
        ak_headers = {"Authorization": f"Bearer {api_key['raw_key']}"}

        ext_ref = f"req_{uuid.uuid4().hex[:16]}"
        resp = await client.post("/api/v1/external/transactions", json={
            "member_id": member["id"],
            "amount_cents": 5000,
            "type": "payment",
            "description": "FMS — wellness-emr integration test",
            "external_reference": ext_ref,
        }, headers=ak_headers)
        assert resp.status_code == 201, resp.text
        txn = resp.json()["data"]
        assert txn["amount_cents"] == 5000
        assert txn["type"] == "payment"
        assert txn["status"] == "completed"
        assert txn["member_id"] == member["id"]
        # Fee = STRIPE_PLATFORM_FEE_PERCENT % of amount; net = amount − fee.
        # Don't pin the percent — it's env-configured.
        assert 0 <= txn["fee_cents"] <= txn["amount_cents"]
        assert txn["net_amount_cents"] == txn["amount_cents"] - txn["fee_cents"]
        assert txn["metadata"]["external_reference"] == ext_ref
        assert txn["metadata"]["source"] == "integration"

    async def test_record_is_idempotent_on_external_reference(self, client: AsyncClient, registered_owner_with_studio):
        jwt_headers = registered_owner_with_studio["headers"]
        member = await _create_member(client, jwt_headers)
        api_key = await _mint_api_key(client, jwt_headers)
        ak_headers = {"Authorization": f"Bearer {api_key['raw_key']}"}

        ext_ref = f"req_{uuid.uuid4().hex[:16]}"
        body = {
            "member_id": member["id"],
            "amount_cents": 4000,
            "description": "Gait screen",
            "external_reference": ext_ref,
        }
        first = await client.post("/api/v1/external/transactions", json=body, headers=ak_headers)
        assert first.status_code == 201, first.text
        first_id = first.json()["data"]["id"]

        # Re-send with same external_reference — should return the same row.
        # Within the 5-second freshness heuristic the second call may also
        # return 201 (the heuristic flips to 200 once the original row is
        # >5s old). What matters: same id, no duplicate insert.
        second = await client.post("/api/v1/external/transactions", json=body, headers=ak_headers)
        assert second.status_code in (200, 201), second.text
        assert second.json()["data"]["id"] == first_id

    async def test_requires_api_key(self, client: AsyncClient):
        resp = await client.post("/api/v1/external/transactions", json={
            "member_id": str(uuid.uuid4()),
            "amount_cents": 1000,
        })
        assert resp.status_code in (401, 403)

    async def test_validates_amount_cents_must_be_positive(self, client: AsyncClient, registered_owner_with_studio):
        jwt_headers = registered_owner_with_studio["headers"]
        member = await _create_member(client, jwt_headers)
        api_key = await _mint_api_key(client, jwt_headers)
        ak_headers = {"Authorization": f"Bearer {api_key['raw_key']}"}

        for bad_amount in (0, -100, -5000):
            resp = await client.post("/api/v1/external/transactions", json={
                "member_id": member["id"], "amount_cents": bad_amount,
            }, headers=ak_headers)
            assert resp.status_code == 422, f"amount_cents={bad_amount} should 422, got {resp.status_code}"

    async def test_validates_amount_cents_capped(self, client: AsyncClient, registered_owner_with_studio):
        jwt_headers = registered_owner_with_studio["headers"]
        member = await _create_member(client, jwt_headers)
        api_key = await _mint_api_key(client, jwt_headers)
        ak_headers = {"Authorization": f"Bearer {api_key['raw_key']}"}

        # Per-txn cap is $100k = 10_000_000 cents
        resp = await client.post("/api/v1/external/transactions", json={
            "member_id": member["id"], "amount_cents": 10_000_001,
        }, headers=ak_headers)
        assert resp.status_code == 422

    async def test_blank_external_reference_rejected(self, client: AsyncClient, registered_owner_with_studio):
        jwt_headers = registered_owner_with_studio["headers"]
        member = await _create_member(client, jwt_headers)
        api_key = await _mint_api_key(client, jwt_headers)
        ak_headers = {"Authorization": f"Bearer {api_key['raw_key']}"}

        resp = await client.post("/api/v1/external/transactions", json={
            "member_id": member["id"], "amount_cents": 1000,
            "external_reference": "   ",  # whitespace-only
        }, headers=ak_headers)
        assert resp.status_code == 422

    async def test_response_metadata_does_not_leak_api_key_id(self, client: AsyncClient, registered_owner_with_studio):
        jwt_headers = registered_owner_with_studio["headers"]
        member = await _create_member(client, jwt_headers)
        api_key = await _mint_api_key(client, jwt_headers)
        ak_headers = {"Authorization": f"Bearer {api_key['raw_key']}"}

        resp = await client.post("/api/v1/external/transactions", json={
            "member_id": member["id"], "amount_cents": 1500,
            "external_reference": f"req_{uuid.uuid4().hex[:16]}",
        }, headers=ak_headers)
        assert resp.status_code == 201
        meta = resp.json()["data"]["metadata"]
        assert "api_key_id" not in meta, "api_key_id must not be exposed to clients"
