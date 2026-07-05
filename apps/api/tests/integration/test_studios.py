"""AuraFlow — Studio & Room Integration Tests"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestStudios:

    async def test_create_studio(self, client: AsyncClient, registered_owner):
        token = registered_owner["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.post("/api/v1/studios", json={
            "name": "Downtown Studio",
            "slug": "downtown",
            "city": "Fresno",
            "state": "CA",
        }, headers=headers)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Downtown Studio"
        assert data["slug"] == "downtown"
        assert data["is_active"] is True

    async def test_list_studios(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        response = await client.get("/api/v1/studios", headers=headers)
        assert response.status_code == 200
        studios = response.json()
        assert len(studios) >= 2  # default from provisioning + fixture-created
        names = [s["name"] for s in studios]
        assert "Test Studio Location" in names

    async def test_get_studio(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        response = await client.get(f"/api/v1/studios/{studio_id}", headers=headers)
        assert response.status_code == 200
        assert response.json()["id"] == studio_id

    async def test_update_studio(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        response = await client.put(f"/api/v1/studios/{studio_id}", json={
            "name": "Updated Studio",
            "cancellation_policy_hours": 24,
            "booking_window_days": 7,
        }, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Studio"
        assert data["cancellation_policy_hours"] == 24
        assert data["booking_window_days"] == 7

    async def test_deactivate_studio(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        response = await client.delete(f"/api/v1/studios/{studio_id}", headers=headers)
        assert response.status_code == 204

    async def test_studio_not_found(self, client: AsyncClient, registered_owner):
        token = registered_owner["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.get(
            "/api/v1/studios/00000000-0000-0000-0000-000000000000",
            headers=headers,
        )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestRooms:

    async def test_create_room(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        response = await client.post(f"/api/v1/studios/{studio_id}/rooms", json={
            "name": "Hot Room",
            "capacity": 30,
            "color": "#EF4444",
        }, headers=headers)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Hot Room"
        assert data["capacity"] == 30
        assert data["color"] == "#EF4444"

    async def test_list_rooms(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        # Create a room first
        await client.post(f"/api/v1/studios/{studio_id}/rooms", json={
            "name": "Studio A",
        }, headers=headers)

        response = await client.get(f"/api/v1/studios/{studio_id}/rooms", headers=headers)
        assert response.status_code == 200
        rooms = response.json()
        assert len(rooms) >= 1

    async def test_update_room(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        # Create
        create = await client.post(f"/api/v1/studios/{studio_id}/rooms", json={
            "name": "Room B",
        }, headers=headers)
        room_id = create.json()["id"]

        # Update
        response = await client.put(
            f"/api/v1/studios/{studio_id}/rooms/{room_id}",
            json={"name": "Room B Updated", "capacity": 15},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Room B Updated"
        assert response.json()["capacity"] == 15

    async def test_delete_room(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        create = await client.post(f"/api/v1/studios/{studio_id}/rooms", json={
            "name": "Temp Room",
        }, headers=headers)
        room_id = create.json()["id"]

        response = await client.delete(
            f"/api/v1/studios/{studio_id}/rooms/{room_id}",
            headers=headers,
        )
        assert response.status_code == 204
