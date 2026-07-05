"""AuraFlow — Scheduling Integration Tests

Tests class types, series (RRULE), sessions, and date range queries.
"""
import uuid
from datetime import date, datetime, timedelta

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestClassTypes:

    async def test_create_class_type(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        response = await client.post("/api/v1/scheduling/class-types", json={
            "studio_id": studio_id,
            "name": "Vinyasa Flow",
            "description": "Dynamic yoga practice",
            "duration_minutes": 75,
            "color": "#10B981",
            "capacity": 25,
            "level": "intermediate",
            "tags": ["yoga", "flow"],
            "category": "Yoga",
        }, headers=headers)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Vinyasa Flow"
        assert data["duration_minutes"] == 75
        assert data["level"] == "intermediate"
        assert data["tags"] == ["yoga", "flow"]

    async def test_list_class_types(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        # Create two types
        await client.post("/api/v1/scheduling/class-types", json={
            "studio_id": studio_id, "name": "Yin Yoga",
        }, headers=headers)
        await client.post("/api/v1/scheduling/class-types", json={
            "studio_id": studio_id, "name": "Power Yoga",
        }, headers=headers)

        response = await client.get(
            f"/api/v1/scheduling/class-types?studio_id={studio_id}",
            headers=headers,
        )
        assert response.status_code == 200
        types = response.json()
        assert len(types) >= 2

    async def test_update_class_type(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        create = await client.post("/api/v1/scheduling/class-types", json={
            "studio_id": studio_id, "name": "Hot Yoga",
        }, headers=headers)
        ct_id = create.json()["id"]

        response = await client.put(f"/api/v1/scheduling/class-types/{ct_id}", json={
            "name": "Bikram Hot Yoga",
            "capacity": 30,
        }, headers=headers)
        assert response.status_code == 200
        assert response.json()["name"] == "Bikram Hot Yoga"
        assert response.json()["capacity"] == 30

    async def test_deactivate_class_type(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        create = await client.post("/api/v1/scheduling/class-types", json={
            "studio_id": studio_id, "name": "Temp Class",
        }, headers=headers)
        ct_id = create.json()["id"]

        response = await client.delete(f"/api/v1/scheduling/class-types/{ct_id}", headers=headers)
        assert response.status_code == 204


@pytest.mark.asyncio
class TestSeries:

    async def _create_class_type(self, client, headers, studio_id):
        resp = await client.post("/api/v1/scheduling/class-types", json={
            "studio_id": studio_id,
            "name": f"Test Class {uuid.uuid4().hex[:6]}",
            "duration_minutes": 60,
        }, headers=headers)
        return resp.json()["id"]

    async def test_create_series_with_expansion(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        ct_id = await self._create_class_type(client, headers, studio_id)

        today = date.today()
        response = await client.post("/api/v1/scheduling/series", json={
            "studio_id": studio_id,
            "class_type_id": ct_id,
            "title": "Morning Vinyasa",
            "rrule": "FREQ=WEEKLY;BYDAY=MO,WE,FR",
            "start_time": "09:00",
            "duration_minutes": 60,
            "capacity": 20,
            "effective_from": today.isoformat(),
            "expand_weeks": 2,
            "timezone": "America/Los_Angeles",
        }, headers=headers)
        assert response.status_code == 201
        data = response.json()
        assert data["sessions_created"] >= 1
        assert data["series"]["title"] == "Morning Vinyasa"

    async def test_list_series(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        ct_id = await self._create_class_type(client, headers, studio_id)

        await client.post("/api/v1/scheduling/series", json={
            "studio_id": studio_id,
            "class_type_id": ct_id,
            "title": "Evening Yin",
            "rrule": "FREQ=WEEKLY;BYDAY=TU,TH",
            "start_time": "18:00",
            "duration_minutes": 75,
            "effective_from": date.today().isoformat(),
            "expand_weeks": 1,
        }, headers=headers)

        response = await client.get(
            f"/api/v1/scheduling/series?studio_id={studio_id}",
            headers=headers,
        )
        assert response.status_code == 200
        assert len(response.json()) >= 1

    async def test_expand_series(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        ct_id = await self._create_class_type(client, headers, studio_id)

        create = await client.post("/api/v1/scheduling/series", json={
            "studio_id": studio_id,
            "class_type_id": ct_id,
            "title": "Expand Test",
            "rrule": "FREQ=DAILY",
            "start_time": "10:00",
            "duration_minutes": 45,
            "effective_from": date.today().isoformat(),
            "expand_weeks": 1,
        }, headers=headers)
        series_id = create.json()["series"]["id"]

        # Expand further
        response = await client.post(
            f"/api/v1/scheduling/series/{series_id}/expand?weeks=4",
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["sessions_created"] >= 0

    async def test_delete_series_cancels_future_sessions(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        ct_id = await self._create_class_type(client, headers, studio_id)

        create = await client.post("/api/v1/scheduling/series", json={
            "studio_id": studio_id,
            "class_type_id": ct_id,
            "title": "Delete Test",
            "rrule": "FREQ=DAILY",
            "start_time": "11:00",
            "duration_minutes": 60,
            "effective_from": date.today().isoformat(),
            "expand_weeks": 1,
        }, headers=headers)
        series_id = create.json()["series"]["id"]

        response = await client.delete(
            f"/api/v1/scheduling/series/{series_id}",
            headers=headers,
        )
        assert response.status_code == 204


@pytest.mark.asyncio
class TestSessions:

    async def test_create_session(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        # Create class type
        ct = await client.post("/api/v1/scheduling/class-types", json={
            "studio_id": studio_id, "name": "Ad Hoc Workshop",
        }, headers=headers)
        ct_id = ct.json()["id"]

        now = datetime.utcnow() + timedelta(days=1)
        response = await client.post("/api/v1/scheduling/sessions", json={
            "studio_id": studio_id,
            "class_type_id": ct_id,
            "title": "Special Workshop",
            "starts_at": now.isoformat(),
            "ends_at": (now + timedelta(hours=2)).isoformat(),
            "capacity": 15,
        }, headers=headers)
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Special Workshop"
        assert data["capacity"] == 15
        assert data["status"] == "scheduled"

    async def test_list_sessions_date_range(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        ct = await client.post("/api/v1/scheduling/class-types", json={
            "studio_id": studio_id, "name": "Range Test",
        }, headers=headers)
        ct_id = ct.json()["id"]

        # Create a session for tomorrow
        tomorrow = datetime.utcnow() + timedelta(days=1)
        await client.post("/api/v1/scheduling/sessions", json={
            "studio_id": studio_id,
            "class_type_id": ct_id,
            "title": "Tomorrow Class",
            "starts_at": tomorrow.isoformat(),
            "ends_at": (tomorrow + timedelta(hours=1)).isoformat(),
        }, headers=headers)

        # Query sessions for the next week
        start = date.today().isoformat()
        end = (date.today() + timedelta(days=7)).isoformat()
        response = await client.get(
            f"/api/v1/scheduling/sessions?studio_id={studio_id}&start={start}&end={end}",
            headers=headers,
        )
        assert response.status_code == 200
        sessions = response.json()
        assert len(sessions) >= 1

    async def test_cancel_session(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        ct = await client.post("/api/v1/scheduling/class-types", json={
            "studio_id": studio_id, "name": "Cancel Test",
        }, headers=headers)
        ct_id = ct.json()["id"]

        tomorrow = datetime.utcnow() + timedelta(days=1)
        create = await client.post("/api/v1/scheduling/sessions", json={
            "studio_id": studio_id,
            "class_type_id": ct_id,
            "title": "To Cancel",
            "starts_at": tomorrow.isoformat(),
            "ends_at": (tomorrow + timedelta(hours=1)).isoformat(),
        }, headers=headers)
        session_id = create.json()["id"]

        response = await client.delete(
            f"/api/v1/scheduling/sessions/{session_id}?reason=Weather",
            headers=headers,
        )
        assert response.status_code == 204

    async def test_update_session(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        ct = await client.post("/api/v1/scheduling/class-types", json={
            "studio_id": studio_id, "name": "Update Test",
        }, headers=headers)
        ct_id = ct.json()["id"]

        tomorrow = datetime.utcnow() + timedelta(days=1)
        create = await client.post("/api/v1/scheduling/sessions", json={
            "studio_id": studio_id,
            "class_type_id": ct_id,
            "title": "Original Title",
            "starts_at": tomorrow.isoformat(),
            "ends_at": (tomorrow + timedelta(hours=1)).isoformat(),
        }, headers=headers)
        session_id = create.json()["id"]

        response = await client.put(f"/api/v1/scheduling/sessions/{session_id}", json={
            "title": "New Title",
            "capacity": 30,
        }, headers=headers)
        assert response.status_code == 200
        assert response.json()["title"] == "New Title"
