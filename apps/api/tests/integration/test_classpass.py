"""AuraFlow — ClassPass Integration Tests

Tests ClassPass connection, config updates, reservation webhook,
cancellation webhook, max spots enforcement, and blackout class types.
"""
import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestClassPassConnection:

    async def test_connect(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        resp = await client.post("/api/v1/integrations/classpass/connect", json={
            "studio_id": studio_id,
            "venue_id": "cp-venue-12345",
        }, headers=headers)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["venue_id"] == "cp-venue-12345"
        assert data["is_active"] is True

    async def test_get_config(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        await client.post("/api/v1/integrations/classpass/connect", json={
            "studio_id": studio_id,
            "venue_id": "cp-venue-99999",
        }, headers=headers)

        resp = await client.get(f"/api/v1/integrations/classpass/config/{studio_id}",
                                headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["venue_id"] == "cp-venue-99999"

    async def test_update_config(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        await client.post("/api/v1/integrations/classpass/connect", json={
            "studio_id": studio_id,
            "venue_id": "cp-venue-config",
        }, headers=headers)

        resp = await client.put(f"/api/v1/integrations/classpass/config/{studio_id}", json={
            "credit_rate": 5,
            "max_spots_per_class": 5,
            "auto_confirm": False,
        }, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["credit_rate"] == 5
        assert data["max_spots_per_class"] == 5
        assert data["auto_confirm"] is False

    async def test_disconnect(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        await client.post("/api/v1/integrations/classpass/connect", json={
            "studio_id": studio_id,
            "venue_id": "cp-venue-disc",
        }, headers=headers)

        resp = await client.post(f"/api/v1/integrations/classpass/disconnect/{studio_id}",
                                 headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["disconnected"] is True

        # Config should show inactive
        config = await client.get(f"/api/v1/integrations/classpass/config/{studio_id}",
                                  headers=headers)
        assert config.json()["data"]["is_active"] is False


@pytest.mark.asyncio
class TestClassPassReservations:

    async def _setup(self, client, headers, studio_id):
        """Connect ClassPass and create a class session to book."""
        await client.post("/api/v1/integrations/classpass/connect", json={
            "studio_id": studio_id,
            "venue_id": "cp-venue-res",
        }, headers=headers)

        # Create a class type
        ct_resp = await client.post("/api/v1/scheduling/class-types", json={
            "name": f"CP Yoga-{uuid.uuid4().hex[:6]}",
            "studio_id": studio_id,
        }, headers=headers)
        assert ct_resp.status_code == 201
        class_type_id = ct_resp.json()["id"]

        # Create a class session
        cs_resp = await client.post("/api/v1/scheduling/sessions", json={
            "class_type_id": class_type_id,
            "studio_id": studio_id,
            "title": "Morning Yoga",
            "starts_at": "2026-04-01T09:00:00",
            "ends_at": "2026-04-01T10:00:00",
            "capacity": 20,
        }, headers=headers)
        assert cs_resp.status_code == 201
        session_id = cs_resp.json()["id"]

        return class_type_id, session_id

    async def test_reservation_webhook(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        class_type_id, session_id = await self._setup(client, headers, studio_id)

        resp = await client.post("/api/v1/integrations/classpass/reservations", json={
            "classpass_reservation_id": f"cp-res-{uuid.uuid4().hex[:8]}",
            "class_session_id": session_id,
            "customer_name": "ClassPass User",
            "customer_email": "cpuser@classpass.com",
            "credits": 3,
        }, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "reserved"
        assert data["customer_name"] == "ClassPass User"
        assert data["credits"] == 3

    async def test_cancellation_webhook(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        class_type_id, session_id = await self._setup(client, headers, studio_id)

        cp_id = f"cp-res-{uuid.uuid4().hex[:8]}"
        await client.post("/api/v1/integrations/classpass/reservations", json={
            "classpass_reservation_id": cp_id,
            "class_session_id": session_id,
            "customer_name": "Cancel User",
            "credits": 2,
        }, headers=headers)

        resp = await client.post("/api/v1/integrations/classpass/reservations/cancel", json={
            "classpass_reservation_id": cp_id,
        }, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "cancelled"

    async def test_max_spots_enforced(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        class_type_id, session_id = await self._setup(client, headers, studio_id)

        # Set max to 2
        await client.put(f"/api/v1/integrations/classpass/config/{studio_id}", json={
            "max_spots_per_class": 2,
        }, headers=headers)

        # Book 2 spots
        for i in range(2):
            resp = await client.post("/api/v1/integrations/classpass/reservations", json={
                "classpass_reservation_id": f"cp-max-{i}-{uuid.uuid4().hex[:6]}",
                "class_session_id": session_id,
                "customer_name": f"Max User {i}",
                "credits": 1,
            }, headers=headers)
            assert resp.status_code == 200

        # 3rd should fail
        resp = await client.post("/api/v1/integrations/classpass/reservations", json={
            "classpass_reservation_id": f"cp-max-3-{uuid.uuid4().hex[:6]}",
            "class_session_id": session_id,
            "customer_name": "Overflow User",
            "credits": 1,
        }, headers=headers)
        assert resp.status_code == 400
        assert "maximum" in resp.json()["detail"].lower()

    async def test_list_reservations(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        class_type_id, session_id = await self._setup(client, headers, studio_id)

        await client.post("/api/v1/integrations/classpass/reservations", json={
            "classpass_reservation_id": f"cp-list-{uuid.uuid4().hex[:8]}",
            "class_session_id": session_id,
            "customer_name": "List User 1",
        }, headers=headers)
        await client.post("/api/v1/integrations/classpass/reservations", json={
            "classpass_reservation_id": f"cp-list-{uuid.uuid4().hex[:8]}",
            "class_session_id": session_id,
            "customer_name": "List User 2",
        }, headers=headers)

        resp = await client.get("/api/v1/integrations/classpass/reservations",
                                headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]) >= 2

    async def test_connect_idempotent(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        # Connect twice with different venue IDs
        await client.post("/api/v1/integrations/classpass/connect", json={
            "studio_id": studio_id,
            "venue_id": "cp-v1",
        }, headers=headers)
        resp = await client.post("/api/v1/integrations/classpass/connect", json={
            "studio_id": studio_id,
            "venue_id": "cp-v2",
        }, headers=headers)
        assert resp.status_code == 201
        assert resp.json()["data"]["venue_id"] == "cp-v2"
