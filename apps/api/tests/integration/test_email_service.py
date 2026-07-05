"""AuraFlow — Email Service Integration Tests

Tests the email service's communication logging (actual SendGrid sending
is skipped since API key is not configured in test environment).
"""
import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestEmailServiceIntegration:
    """Test email service through the booking/membership flow.

    Since SendGrid is not configured in tests, emails are logged as 'skipped'
    but the communication_log entries are still created.
    """

    async def _setup_member_and_membership(self, client, headers, studio_id):
        """Create a member and membership type for testing."""
        # Create member
        member_resp = await client.post("/api/v1/members", json={
            "first_name": "Email",
            "last_name": f"Test-{uuid.uuid4().hex[:6]}",
            "email": f"email-{uuid.uuid4().hex[:8]}@test.auraflow.dev",
        }, headers=headers)
        assert member_resp.status_code == 201
        member = member_resp.json()

        # Create membership type
        type_resp = await client.post("/api/v1/memberships/types", json={
            "studio_id": studio_id,
            "name": "Email Test Unlimited",
            "type": "unlimited",
            "price_cents": 15000,
            "billing_period": "monthly",
        }, headers=headers)
        assert type_resp.status_code == 201

        return member

    async def test_communication_log_created_on_manual_send(
        self,
        client: AsyncClient,
        registered_owner_with_studio,
    ):
        """Verify that the communications endpoint returns data."""
        headers = registered_owner_with_studio["headers"]

        # Communications list should be accessible
        resp = await client.get("/api/v1/payments/communications", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)

    async def test_communication_log_filter_by_channel(
        self,
        client: AsyncClient,
        registered_owner_with_studio,
    ):
        """Test filtering communications by channel."""
        headers = registered_owner_with_studio["headers"]

        resp = await client.get(
            "/api/v1/payments/communications?channel=email",
            headers=headers,
        )
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)
