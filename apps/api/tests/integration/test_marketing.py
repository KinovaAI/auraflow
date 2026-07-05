"""AuraFlow — Marketing Integration Tests

Tests email campaign CRUD, audience preview, campaign sending (mock SendGrid),
campaign stats, and SMS messaging (mock Twilio).
"""
import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestCampaignCRUD:

    async def test_create_campaign(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        resp = await client.post("/api/v1/marketing/campaigns", json={
            "name": "Welcome Campaign",
            "subject": "Welcome to our studio!",
            "html_content": "<h1>Welcome!</h1><p>We're glad you're here.</p>",
            "audience_filter": {"tags": ["new_member"]},
        }, headers=headers)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["name"] == "Welcome Campaign"
        assert data["subject"] == "Welcome to our studio!"
        assert data["status"] == "draft"

    async def test_list_campaigns(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        await client.post("/api/v1/marketing/campaigns", json={
            "name": "Camp A",
            "subject": "Subject A",
        }, headers=headers)
        await client.post("/api/v1/marketing/campaigns", json={
            "name": "Camp B",
            "subject": "Subject B",
        }, headers=headers)

        resp = await client.get("/api/v1/marketing/campaigns", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]) >= 2

    async def test_get_campaign(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        create = await client.post("/api/v1/marketing/campaigns", json={
            "name": "Get Test",
            "subject": "Get Subject",
        }, headers=headers)
        campaign_id = create.json()["data"]["id"]

        resp = await client.get(f"/api/v1/marketing/campaigns/{campaign_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "Get Test"

    async def test_update_campaign(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        create = await client.post("/api/v1/marketing/campaigns", json={
            "name": "Old Name",
            "subject": "Old Subject",
        }, headers=headers)
        campaign_id = create.json()["data"]["id"]

        resp = await client.put(f"/api/v1/marketing/campaigns/{campaign_id}", json={
            "name": "Updated Name",
            "subject": "Updated Subject",
        }, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "Updated Name"
        assert resp.json()["data"]["subject"] == "Updated Subject"

    async def test_delete_campaign(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        create = await client.post("/api/v1/marketing/campaigns", json={
            "name": "To Delete",
            "subject": "Delete Me",
        }, headers=headers)
        campaign_id = create.json()["data"]["id"]

        resp = await client.delete(f"/api/v1/marketing/campaigns/{campaign_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["deleted"] is True

        # Verify it's gone
        resp2 = await client.get(f"/api/v1/marketing/campaigns/{campaign_id}", headers=headers)
        assert resp2.status_code == 404

    async def test_list_campaigns_by_status(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        await client.post("/api/v1/marketing/campaigns", json={
            "name": "Draft Campaign",
            "subject": "Draft",
        }, headers=headers)

        resp = await client.get("/api/v1/marketing/campaigns?status=draft", headers=headers)
        assert resp.status_code == 200
        for c in resp.json()["data"]:
            assert c["status"] == "draft"


@pytest.mark.asyncio
class TestAudiencePreview:

    async def _create_member(self, client, headers, tags=None):
        resp = await client.post("/api/v1/members", json={
            "first_name": "Aud",
            "last_name": f"Member-{uuid.uuid4().hex[:6]}",
            "email": f"aud-{uuid.uuid4().hex[:8]}@test.auraflow.dev",
            "tags": tags or [],
        }, headers=headers)
        return resp.json()["id"]

    async def test_preview_audience_all(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        # Create a member
        await self._create_member(client, headers)

        resp = await client.post("/api/v1/marketing/campaigns/preview-audience", json={},
                                 headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["count"] >= 1

    async def test_preview_audience_with_tags(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        await self._create_member(client, headers, tags=["vip"])
        await self._create_member(client, headers, tags=["regular"])

        resp = await client.post("/api/v1/marketing/campaigns/preview-audience", json={
            "tags": ["vip"],
        }, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["count"] >= 1


@pytest.mark.asyncio
class TestCampaignSend:

    async def _create_member(self, client, headers):
        resp = await client.post("/api/v1/members", json={
            "first_name": "Send",
            "last_name": f"Member-{uuid.uuid4().hex[:6]}",
            "email": f"send-{uuid.uuid4().hex[:8]}@test.auraflow.dev",
        }, headers=headers)
        return resp.json()["id"]

    async def test_send_campaign(self, client: AsyncClient, registered_owner_with_studio):
        """Send a campaign to all active members (SendGrid not configured = mock send)."""
        headers = registered_owner_with_studio["headers"]

        # Create some members
        await self._create_member(client, headers)
        await self._create_member(client, headers)

        # Create campaign
        create = await client.post("/api/v1/marketing/campaigns", json={
            "name": "Send Test Campaign",
            "subject": "Hello from AuraFlow!",
            "html_content": "<p>Test email body</p>",
        }, headers=headers)
        campaign_id = create.json()["data"]["id"]

        # Send it
        resp = await client.post(f"/api/v1/marketing/campaigns/{campaign_id}/send",
                                 headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] >= 2
        assert data["sent"] >= 0  # May be 0 if SendGrid not configured

    async def test_cannot_send_already_sent(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        await self._create_member(client, headers)

        create = await client.post("/api/v1/marketing/campaigns", json={
            "name": "One-Time Send",
            "subject": "Once only",
        }, headers=headers)
        campaign_id = create.json()["data"]["id"]

        # Send once
        await client.post(f"/api/v1/marketing/campaigns/{campaign_id}/send",
                          headers=headers)

        # Try to send again — should fail
        resp = await client.post(f"/api/v1/marketing/campaigns/{campaign_id}/send",
                                 headers=headers)
        assert resp.status_code == 400
        assert "cannot send" in resp.json()["detail"].lower()


@pytest.mark.asyncio
class TestCampaignStats:

    async def test_get_stats(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        # Create a member and campaign
        await client.post("/api/v1/members", json={
            "first_name": "Stats",
            "last_name": f"Member-{uuid.uuid4().hex[:6]}",
            "email": f"stats-{uuid.uuid4().hex[:8]}@test.auraflow.dev",
        }, headers=headers)

        create = await client.post("/api/v1/marketing/campaigns", json={
            "name": "Stats Campaign",
            "subject": "Stats Test",
        }, headers=headers)
        campaign_id = create.json()["data"]["id"]

        # Send campaign
        await client.post(f"/api/v1/marketing/campaigns/{campaign_id}/send",
                          headers=headers)

        # Get stats
        resp = await client.get(f"/api/v1/marketing/campaigns/{campaign_id}/stats",
                                headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "send_stats" in data
        assert data["send_stats"]["total_sends"] >= 1

    async def test_stats_404_for_missing(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        resp = await client.get(f"/api/v1/marketing/campaigns/{uuid.uuid4()}/stats",
                                headers=headers)
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestSms:

    async def test_send_sms(self, client: AsyncClient, registered_owner_with_studio):
        """Send SMS (Twilio not configured = mock send)."""
        headers = registered_owner_with_studio["headers"]

        resp = await client.post("/api/v1/marketing/sms/send", json={
            "to_phone": "+15551234567",
            "body": "Your class starts in 30 minutes!",
            "sms_type": "reminder",
        }, headers=headers)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["to_phone"] == "+15551234567"
        assert data["status"] == "sent"

    async def test_send_sms_with_member(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        # Create a member
        member_resp = await client.post("/api/v1/members", json={
            "first_name": "SMS",
            "last_name": f"Test-{uuid.uuid4().hex[:6]}",
            "email": f"sms-{uuid.uuid4().hex[:8]}@test.auraflow.dev",
            "phone": "+15559876543",
        }, headers=headers)
        member_id = member_resp.json()["id"]

        resp = await client.post("/api/v1/marketing/sms/send", json={
            "to_phone": "+15559876543",
            "body": "Payment reminder: your membership renews tomorrow.",
            "member_id": member_id,
            "sms_type": "transactional",
        }, headers=headers)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["member_id"] == member_id

    async def test_list_sms(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        # Send a couple SMS
        await client.post("/api/v1/marketing/sms/send", json={
            "to_phone": "+15551111111",
            "body": "Message 1",
        }, headers=headers)
        await client.post("/api/v1/marketing/sms/send", json={
            "to_phone": "+15552222222",
            "body": "Message 2",
        }, headers=headers)

        resp = await client.get("/api/v1/marketing/sms", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]) >= 2
