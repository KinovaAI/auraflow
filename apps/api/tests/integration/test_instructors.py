"""AuraFlow — Instructor Integration Tests"""
import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestInstructors:

    async def test_create_instructor(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        response = await client.post("/api/v1/instructors", json={
            "user_id": str(uuid.uuid4()),
            "display_name": "Sarah Johnson",
            "bio": "Certified yoga instructor",
            "specialties": ["Vinyasa", "Yin"],
            "certifications": ["RYT-200"],
            "email": "sarah@example.com",
            "pay_rate_cents": 5000,
            "pay_type": "per_class",
            "tax_classification": "1099",
        }, headers=headers)
        assert response.status_code == 201
        data = response.json()
        assert data["display_name"] == "Sarah Johnson"
        assert data["specialties"] == ["Vinyasa", "Yin"]
        assert data["pay_rate_cents"] == 5000

    async def test_list_instructors(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        await client.post("/api/v1/instructors", json={
            "user_id": str(uuid.uuid4()),
            "display_name": "Instructor A",
        }, headers=headers)
        await client.post("/api/v1/instructors", json={
            "user_id": str(uuid.uuid4()),
            "display_name": "Instructor B",
        }, headers=headers)

        response = await client.get("/api/v1/instructors", headers=headers)
        assert response.status_code == 200
        assert len(response.json()) >= 2

    async def test_get_instructor(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        create = await client.post("/api/v1/instructors", json={
            "user_id": str(uuid.uuid4()),
            "display_name": "Get Test",
        }, headers=headers)
        instructor_id = create.json()["id"]

        response = await client.get(f"/api/v1/instructors/{instructor_id}", headers=headers)
        assert response.status_code == 200
        assert response.json()["display_name"] == "Get Test"

    async def test_update_instructor(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        create = await client.post("/api/v1/instructors", json={
            "user_id": str(uuid.uuid4()),
            "display_name": "Before Update",
        }, headers=headers)
        instructor_id = create.json()["id"]

        response = await client.put(f"/api/v1/instructors/{instructor_id}", json={
            "display_name": "After Update",
            "bio": "Updated bio",
        }, headers=headers)
        assert response.status_code == 200
        assert response.json()["display_name"] == "After Update"
        assert response.json()["bio"] == "Updated bio"

    async def test_deactivate_instructor(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        create = await client.post("/api/v1/instructors", json={
            "user_id": str(uuid.uuid4()),
            "display_name": "To Deactivate",
        }, headers=headers)
        instructor_id = create.json()["id"]

        response = await client.delete(f"/api/v1/instructors/{instructor_id}", headers=headers)
        assert response.status_code == 204

    async def test_instructor_not_found(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        response = await client.get(
            "/api/v1/instructors/00000000-0000-0000-0000-000000000000",
            headers=headers,
        )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestInstructorAvailability:

    async def test_set_and_get_availability(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        create = await client.post("/api/v1/instructors", json={
            "user_id": str(uuid.uuid4()),
            "display_name": "Avail Test",
        }, headers=headers)
        instructor_id = create.json()["id"]

        # Set availability
        response = await client.put(f"/api/v1/instructors/{instructor_id}/availability", json=[
            {"day_of_week": 0, "start_time": "09:00", "end_time": "12:00"},
            {"day_of_week": 0, "start_time": "14:00", "end_time": "17:00"},
            {"day_of_week": 2, "start_time": "09:00", "end_time": "15:00"},
        ], headers=headers)
        assert response.status_code == 200
        slots = response.json()
        assert len(slots) == 3

        # Get availability
        response = await client.get(
            f"/api/v1/instructors/{instructor_id}/availability",
            headers=headers,
        )
        assert response.status_code == 200
        assert len(response.json()) == 3

    async def test_replace_availability(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        create = await client.post("/api/v1/instructors", json={
            "user_id": str(uuid.uuid4()),
            "display_name": "Replace Avail",
        }, headers=headers)
        instructor_id = create.json()["id"]

        # Set initial
        await client.put(f"/api/v1/instructors/{instructor_id}/availability", json=[
            {"day_of_week": 0, "start_time": "09:00", "end_time": "12:00"},
        ], headers=headers)

        # Replace with new
        response = await client.put(f"/api/v1/instructors/{instructor_id}/availability", json=[
            {"day_of_week": 1, "start_time": "10:00", "end_time": "14:00"},
            {"day_of_week": 3, "start_time": "10:00", "end_time": "14:00"},
        ], headers=headers)
        assert response.status_code == 200
        slots = response.json()
        # Should have replaced: 2 new slots only
        assert len(slots) == 2


@pytest.mark.asyncio
class TestInstructorSchedule:

    async def test_get_schedule(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        # Create instructor
        create_inst = await client.post("/api/v1/instructors", json={
            "user_id": str(uuid.uuid4()),
            "display_name": "Schedule Test",
        }, headers=headers)
        instructor_id = create_inst.json()["id"]

        # Create class type
        ct = await client.post("/api/v1/scheduling/class-types", json={
            "studio_id": studio_id,
            "name": "Sched Class",
        }, headers=headers)
        ct_id = ct.json()["id"]

        # Create series with instructor
        today = date.today()
        await client.post("/api/v1/scheduling/series", json={
            "studio_id": studio_id,
            "class_type_id": ct_id,
            "instructor_id": instructor_id,
            "title": "Instructor Series",
            "rrule": "FREQ=DAILY",
            "start_time": "09:00",
            "duration_minutes": 60,
            "effective_from": today.isoformat(),
            "expand_weeks": 1,
        }, headers=headers)

        # Get schedule
        start = today.isoformat()
        end = (today + timedelta(days=7)).isoformat()
        response = await client.get(
            f"/api/v1/instructors/{instructor_id}/schedule?start={start}&end={end}",
            headers=headers,
        )
        assert response.status_code == 200
        sessions = response.json()
        assert len(sessions) >= 1
