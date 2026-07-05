"""AuraFlow — Private Sessions Integration Tests

Tests service CRUD, instructor availability, slot computation,
booking lifecycle, double-booking prevention, and cancellation.
"""
import uuid
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestPrivateServices:

    async def _create_instructor(self, client, headers):
        resp = await client.post("/api/v1/instructors", json={
            "user_id": str(uuid.uuid4()),
            "display_name": f"Private Inst-{uuid.uuid4().hex[:6]}",
            "bio": "Private session specialist",
        }, headers=headers)
        assert resp.status_code == 201
        return resp.json()["id"]

    async def test_create_service(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        instructor_id = await self._create_instructor(client, headers)

        resp = await client.post("/api/v1/private-sessions/services", json={
            "instructor_id": instructor_id,
            "name": "Private Yoga",
            "description": "1-on-1 yoga session",
            "duration_minutes": 60,
            "price_cents": 8000,
            "buffer_after_minutes": 15,
        }, headers=headers)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["name"] == "Private Yoga"
        assert data["price_cents"] == 8000
        assert data["duration_minutes"] == 60

    async def test_list_services(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        instructor_id = await self._create_instructor(client, headers)

        await client.post("/api/v1/private-sessions/services", json={
            "instructor_id": instructor_id,
            "name": "Service A",
            "price_cents": 5000,
        }, headers=headers)
        await client.post("/api/v1/private-sessions/services", json={
            "instructor_id": instructor_id,
            "name": "Service B",
            "price_cents": 7000,
        }, headers=headers)

        resp = await client.get("/api/v1/private-sessions/services", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]) >= 2

    async def test_update_service(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        instructor_id = await self._create_instructor(client, headers)

        create = await client.post("/api/v1/private-sessions/services", json={
            "instructor_id": instructor_id,
            "name": "Old Name",
            "price_cents": 5000,
        }, headers=headers)
        svc_id = create.json()["data"]["id"]

        resp = await client.put(f"/api/v1/private-sessions/services/{svc_id}", json={
            "name": "Updated Service",
            "price_cents": 9000,
        }, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "Updated Service"
        assert resp.json()["data"]["price_cents"] == 9000

    async def test_deactivate_service(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        instructor_id = await self._create_instructor(client, headers)

        create = await client.post("/api/v1/private-sessions/services", json={
            "instructor_id": instructor_id,
            "name": "To Deactivate",
            "price_cents": 5000,
        }, headers=headers)
        svc_id = create.json()["data"]["id"]

        resp = await client.delete(f"/api/v1/private-sessions/services/{svc_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["deactivated"] is True


@pytest.mark.asyncio
class TestInstructorAvailability:

    async def _create_instructor(self, client, headers):
        resp = await client.post("/api/v1/instructors", json={
            "user_id": str(uuid.uuid4()),
            "display_name": f"Avail Test-{uuid.uuid4().hex[:6]}",
        }, headers=headers)
        assert resp.status_code == 201
        return resp.json()["id"]

    async def test_set_and_get_availability(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        instructor_id = await self._create_instructor(client, headers)

        # Set availability: Mon & Wed 9am-5pm
        resp = await client.post(f"/api/v1/private-sessions/availability/{instructor_id}", json={
            "slots": [
                {"day_of_week": 0, "start_time": "09:00", "end_time": "17:00"},
                {"day_of_week": 2, "start_time": "09:00", "end_time": "17:00"},
            ],
        }, headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2

        # Get availability
        resp2 = await client.get(f"/api/v1/private-sessions/availability/{instructor_id}", headers=headers)
        assert resp2.status_code == 200
        data = resp2.json()["data"]
        assert len(data) == 2
        days = [a["day_of_week"] for a in data]
        assert 0 in days
        assert 2 in days

    async def test_block_time(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        instructor_id = await self._create_instructor(client, headers)

        # Block a specific time
        resp = await client.post(f"/api/v1/private-sessions/availability/{instructor_id}/block", json={
            "date": "2026-03-10",
            "start_time": "12:00",
            "end_time": "14:00",
        }, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["is_blocked"] is True
        assert data["specific_date"] == "2026-03-10"


@pytest.mark.asyncio
class TestAvailableSlots:

    async def _setup(self, client, headers):
        """Create instructor, service, and set availability."""
        inst_resp = await client.post("/api/v1/instructors", json={
            "user_id": str(uuid.uuid4()),
            "display_name": f"Slots Test-{uuid.uuid4().hex[:6]}",
        }, headers=headers)
        assert inst_resp.status_code == 201
        instructor_id = inst_resp.json()["id"]

        svc_resp = await client.post("/api/v1/private-sessions/services", json={
            "instructor_id": instructor_id,
            "name": "60-Min Session",
            "duration_minutes": 60,
            "price_cents": 8000,
            "buffer_before_minutes": 0,
            "buffer_after_minutes": 15,
        }, headers=headers)
        service_id = svc_resp.json()["data"]["id"]

        # Set availability for all days 9am-5pm (Mon=0..Sun=6)
        slots = [{"day_of_week": d, "start_time": "09:00", "end_time": "17:00"} for d in range(7)]
        await client.post(f"/api/v1/private-sessions/availability/{instructor_id}", json={
            "slots": slots,
        }, headers=headers)

        return instructor_id, service_id

    async def test_get_available_slots(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        instructor_id, service_id = await self._setup(client, headers)

        # Pick a future date (use Monday)
        target = "2026-03-09"  # Monday
        resp = await client.get(
            f"/api/v1/private-sessions/slots?instructor_id={instructor_id}&service_id={service_id}&date={target}",
            headers=headers,
        )
        assert resp.status_code == 200
        slots = resp.json()["data"]
        # 9am-5pm with 60min+15min buffer = total 75min block, 15min intervals
        # Should have multiple slots
        assert len(slots) > 0
        # First slot should start at 9am
        assert slots[0]["start_time"] == "09:00:00"
        assert slots[0]["duration_minutes"] == 60


@pytest.mark.asyncio
class TestPrivateBookings:

    async def _setup(self, client, headers, studio_id):
        """Create instructor, member, service, availability, and return IDs."""
        inst_resp = await client.post("/api/v1/instructors", json={
            "user_id": str(uuid.uuid4()),
            "display_name": f"Book Inst-{uuid.uuid4().hex[:6]}",
        }, headers=headers)
        assert inst_resp.status_code == 201
        instructor_id = inst_resp.json()["id"]

        member_resp = await client.post("/api/v1/members", json={
            "first_name": "Book",
            "last_name": f"Member-{uuid.uuid4().hex[:6]}",
            "email": f"book-{uuid.uuid4().hex[:8]}@test.auraflow.dev",
        }, headers=headers)
        member_id = member_resp.json()["id"]

        svc_resp = await client.post("/api/v1/private-sessions/services", json={
            "instructor_id": instructor_id,
            "name": "Private Yoga",
            "duration_minutes": 60,
            "price_cents": 8000,
            "buffer_after_minutes": 15,
        }, headers=headers)
        service_id = svc_resp.json()["data"]["id"]

        # Set availability for all days
        slots = [{"day_of_week": d, "start_time": "09:00", "end_time": "17:00"} for d in range(7)]
        await client.post(f"/api/v1/private-sessions/availability/{instructor_id}", json={
            "slots": slots,
        }, headers=headers)

        return instructor_id, member_id, service_id

    async def test_book_session(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        instructor_id, member_id, service_id = await self._setup(client, headers, studio_id)

        resp = await client.post("/api/v1/private-sessions/bookings", json={
            "member_id": member_id,
            "instructor_id": instructor_id,
            "private_service_id": service_id,
            "starts_at": "2026-03-10T10:00:00",
        }, headers=headers)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["status"] == "pending"
        assert data["service_name"] == "Private Yoga"
        assert data["price_cents"] == 8000

    async def test_prevent_double_booking(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        instructor_id, member_id, service_id = await self._setup(client, headers, studio_id)

        # Book first session
        await client.post("/api/v1/private-sessions/bookings", json={
            "member_id": member_id,
            "instructor_id": instructor_id,
            "private_service_id": service_id,
            "starts_at": "2026-03-10T10:00:00",
        }, headers=headers)

        # Try to book overlapping session
        resp = await client.post("/api/v1/private-sessions/bookings", json={
            "member_id": member_id,
            "instructor_id": instructor_id,
            "private_service_id": service_id,
            "starts_at": "2026-03-10T10:30:00",  # overlaps with first (10:00-11:00+15min buffer)
        }, headers=headers)
        assert resp.status_code == 400
        assert "conflicts" in resp.json()["detail"].lower()

    async def test_confirm_booking(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        instructor_id, member_id, service_id = await self._setup(client, headers, studio_id)

        book = await client.post("/api/v1/private-sessions/bookings", json={
            "member_id": member_id,
            "instructor_id": instructor_id,
            "private_service_id": service_id,
            "starts_at": "2026-03-10T14:00:00",
        }, headers=headers)
        booking_id = book.json()["data"]["id"]

        resp = await client.post(f"/api/v1/private-sessions/bookings/{booking_id}/confirm", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "confirmed"

    async def test_cancel_booking(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        instructor_id, member_id, service_id = await self._setup(client, headers, studio_id)

        book = await client.post("/api/v1/private-sessions/bookings", json={
            "member_id": member_id,
            "instructor_id": instructor_id,
            "private_service_id": service_id,
            "starts_at": "2026-03-11T10:00:00",
        }, headers=headers)
        booking_id = book.json()["data"]["id"]

        resp = await client.post(f"/api/v1/private-sessions/bookings/{booking_id}/cancel", json={
            "reason": "Schedule change",
        }, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "cancelled"
        assert data["cancellation_reason"] == "Schedule change"

    async def test_complete_booking(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        instructor_id, member_id, service_id = await self._setup(client, headers, studio_id)

        book = await client.post("/api/v1/private-sessions/bookings", json={
            "member_id": member_id,
            "instructor_id": instructor_id,
            "private_service_id": service_id,
            "starts_at": "2026-03-12T10:00:00",
        }, headers=headers)
        booking_id = book.json()["data"]["id"]

        # Confirm first
        await client.post(f"/api/v1/private-sessions/bookings/{booking_id}/confirm", headers=headers)

        # Complete
        resp = await client.post(f"/api/v1/private-sessions/bookings/{booking_id}/complete", json={
            "instructor_notes": "Great session, work on hip flexibility",
        }, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "completed"
        assert data["instructor_notes"] == "Great session, work on hip flexibility"

    async def test_list_bookings(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        instructor_id, member_id, service_id = await self._setup(client, headers, studio_id)

        # Create two bookings
        await client.post("/api/v1/private-sessions/bookings", json={
            "member_id": member_id,
            "instructor_id": instructor_id,
            "private_service_id": service_id,
            "starts_at": "2026-03-13T09:00:00",
        }, headers=headers)
        await client.post("/api/v1/private-sessions/bookings", json={
            "member_id": member_id,
            "instructor_id": instructor_id,
            "private_service_id": service_id,
            "starts_at": "2026-03-13T14:00:00",
        }, headers=headers)

        resp = await client.get(
            f"/api/v1/private-sessions/bookings?instructor_id={instructor_id}",
            headers=headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]) >= 2

    async def test_cancelled_slot_becomes_available(self, client: AsyncClient, registered_owner_with_studio):
        """After cancelling a booking, the slot should be bookable again."""
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        instructor_id, member_id, service_id = await self._setup(client, headers, studio_id)

        # Book at 10am
        book = await client.post("/api/v1/private-sessions/bookings", json={
            "member_id": member_id,
            "instructor_id": instructor_id,
            "private_service_id": service_id,
            "starts_at": "2026-03-14T10:00:00",
        }, headers=headers)
        booking_id = book.json()["data"]["id"]

        # Cancel it
        await client.post(f"/api/v1/private-sessions/bookings/{booking_id}/cancel", json={}, headers=headers)

        # Should be able to rebook the same slot
        resp = await client.post("/api/v1/private-sessions/bookings", json={
            "member_id": member_id,
            "instructor_id": instructor_id,
            "private_service_id": service_id,
            "starts_at": "2026-03-14T10:00:00",
        }, headers=headers)
        assert resp.status_code == 201
