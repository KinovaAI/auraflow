"""AuraFlow — Member Integration Tests"""
import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestMembers:

    async def _create_member(self, client, headers, **overrides):
        data = {
            "first_name": "Test",
            "last_name": f"Member-{uuid.uuid4().hex[:6]}",
            "email": f"member-{uuid.uuid4().hex[:8]}@test.auraflow.dev",
            **overrides,
        }
        resp = await client.post("/api/v1/members", json=data, headers=headers)
        assert resp.status_code == 201
        return resp.json()

    async def test_create_member(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        response = await client.post("/api/v1/members", json={
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane@example.com",
            "phone": "559-555-1234",
            "source": "website",
            "referral_source": "Google",
        }, headers=headers)
        assert response.status_code == 201
        data = response.json()
        assert data["first_name"] == "Jane"
        assert data["last_name"] == "Doe"
        assert data["source"] == "website"
        assert data["is_active"] is True

    async def test_list_members(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        await self._create_member(client, headers, first_name="Alice")
        await self._create_member(client, headers, first_name="Bob")

        response = await client.get("/api/v1/members", headers=headers)
        assert response.status_code == 200
        assert len(response.json()) >= 2

    async def test_search_members(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        await self._create_member(client, headers, first_name="UniqueSearchName")

        response = await client.get(
            "/api/v1/members?search=UniqueSearch",
            headers=headers,
        )
        assert response.status_code == 200
        results = response.json()
        assert any(m["first_name"] == "UniqueSearchName" for m in results)

    async def test_get_member(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        member = await self._create_member(client, headers)
        member_id = member["id"]

        response = await client.get(f"/api/v1/members/{member_id}", headers=headers)
        assert response.status_code == 200
        assert response.json()["id"] == member_id

    async def test_update_member(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        member = await self._create_member(client, headers)
        member_id = member["id"]

        response = await client.put(f"/api/v1/members/{member_id}", json={
            "phone": "559-555-9999",
            "city": "Fresno",
        }, headers=headers)
        assert response.status_code == 200
        assert response.json()["phone"] == "559-555-9999"
        assert response.json()["city"] == "Fresno"

    async def test_deactivate_member(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        member = await self._create_member(client, headers)
        member_id = member["id"]

        response = await client.delete(f"/api/v1/members/{member_id}", headers=headers)
        assert response.status_code == 204

    async def test_member_not_found(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        response = await client.get(
            "/api/v1/members/00000000-0000-0000-0000-000000000000",
            headers=headers,
        )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestMemberNotes:

    async def test_add_and_list_notes(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        # Create member
        member = await client.post("/api/v1/members", json={
            "first_name": "Notes",
            "last_name": "Test",
            "email": f"notes-{uuid.uuid4().hex[:6]}@test.auraflow.dev",
        }, headers=headers)
        member_id = member.json()["id"]

        # Add notes
        r1 = await client.post(f"/api/v1/members/{member_id}/notes", json={
            "note": "Prefers morning classes",
            "is_pinned": True,
        }, headers=headers)
        assert r1.status_code == 201

        r2 = await client.post(f"/api/v1/members/{member_id}/notes", json={
            "note": "Called about billing",
        }, headers=headers)
        assert r2.status_code == 201

        # List notes
        response = await client.get(f"/api/v1/members/{member_id}/notes", headers=headers)
        assert response.status_code == 200
        notes = response.json()
        assert len(notes) == 2
        # Pinned should come first
        assert notes[0]["is_pinned"] is True

    async def test_delete_note(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        member = await client.post("/api/v1/members", json={
            "first_name": "Del",
            "last_name": "Note",
            "email": f"del-{uuid.uuid4().hex[:6]}@test.auraflow.dev",
        }, headers=headers)
        member_id = member.json()["id"]

        note = await client.post(f"/api/v1/members/{member_id}/notes", json={
            "note": "To be deleted",
        }, headers=headers)
        note_id = note.json()["id"]

        response = await client.delete(
            f"/api/v1/members/{member_id}/notes/{note_id}",
            headers=headers,
        )
        assert response.status_code == 204


@pytest.mark.asyncio
class TestMemberHealthData:

    async def test_set_and_get_health_data(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        member = await client.post("/api/v1/members", json={
            "first_name": "Health",
            "last_name": "Test",
            "email": f"health-{uuid.uuid4().hex[:6]}@test.auraflow.dev",
        }, headers=headers)
        member_id = member.json()["id"]

        # Set health data
        response = await client.put(f"/api/v1/members/{member_id}/health-data", json={
            "health_data": "No known allergies",
            "injuries": "Previous knee surgery - 2024",
            "conditions": "None",
            "medications": "None",
        }, headers=headers)
        assert response.status_code == 200

        # Get health data
        response = await client.get(
            f"/api/v1/members/{member_id}/health-data",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["health_data"] == "No known allergies"
        assert data["injuries"] == "Previous knee surgery - 2024"
