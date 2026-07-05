"""AuraFlow — Time Clock & Payroll Integration Tests"""
import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestClockOperations:

    async def _create_instructor(self, client, headers, **overrides):
        data = {
            "display_name": f"Instructor-{uuid.uuid4().hex[:6]}",
            "email": f"inst-{uuid.uuid4().hex[:8]}@test.auraflow.dev",
            "pay_rate_cents": 2500,
            "pay_type": "hourly",
            **overrides,
        }
        resp = await client.post("/api/v1/instructors", json=data, headers=headers)
        assert resp.status_code == 201
        return resp.json()

    async def test_clock_in(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        instructor = await self._create_instructor(client, headers)

        resp = await client.post("/api/v1/time-clock/clock-in", json={
            "instructor_id": instructor["id"],
            "shift_type": "regular",
        }, headers=headers)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["instructor_id"] == instructor["id"]
        assert data["shift_type"] == "regular"
        assert data["status"] == "pending"
        assert data["clock_out"] is None

    async def test_clock_out(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        instructor = await self._create_instructor(client, headers)

        # Clock in first
        await client.post("/api/v1/time-clock/clock-in", json={
            "instructor_id": instructor["id"],
        }, headers=headers)

        # Clock out
        resp = await client.post("/api/v1/time-clock/clock-out", json={
            "instructor_id": instructor["id"],
            "break_minutes": 15,
        }, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["clock_out"] is not None
        assert data["break_minutes"] == 15
        assert data["total_minutes"] is not None

    async def test_cannot_double_clock_in(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        instructor = await self._create_instructor(client, headers)

        # Clock in
        await client.post("/api/v1/time-clock/clock-in", json={
            "instructor_id": instructor["id"],
        }, headers=headers)

        # Try to clock in again
        resp = await client.post("/api/v1/time-clock/clock-in", json={
            "instructor_id": instructor["id"],
        }, headers=headers)
        assert resp.status_code == 409

    async def test_clock_status_clocked_in(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        instructor = await self._create_instructor(client, headers)

        # Clock in
        await client.post("/api/v1/time-clock/clock-in", json={
            "instructor_id": instructor["id"],
        }, headers=headers)

        resp = await client.get(
            f"/api/v1/time-clock/status/{instructor['id']}", headers=headers
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data is not None
        assert data["clock_out"] is None

    async def test_clock_status_clocked_out(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        instructor = await self._create_instructor(client, headers)

        # No clock-in — should return null
        resp = await client.get(
            f"/api/v1/time-clock/status/{instructor['id']}", headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"] is None


@pytest.mark.asyncio
class TestTimesheets:

    async def _setup_instructor_with_entry(self, client, headers):
        data = {
            "display_name": f"TS-{uuid.uuid4().hex[:6]}",
            "email": f"ts-{uuid.uuid4().hex[:8]}@test.auraflow.dev",
            "pay_rate_cents": 3000,
            "pay_type": "hourly",
        }
        resp = await client.post("/api/v1/instructors", json=data, headers=headers)
        assert resp.status_code == 201
        instructor = resp.json()

        # Clock in then out
        await client.post("/api/v1/time-clock/clock-in", json={
            "instructor_id": instructor["id"],
        }, headers=headers)
        await client.post("/api/v1/time-clock/clock-out", json={
            "instructor_id": instructor["id"],
        }, headers=headers)

        return instructor

    async def test_my_timesheet(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        instructor = await self._setup_instructor_with_entry(client, headers)

        today = date.today().isoformat()
        resp = await client.get(
            f"/api/v1/time-clock/my-timesheet?instructor_id={instructor['id']}&start={today}&end={today}",
            headers=headers,
        )
        assert resp.status_code == 200
        entries = resp.json()["data"]
        assert len(entries) >= 1
        assert entries[0]["instructor_id"] == instructor["id"]

    async def test_admin_timesheets(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        await self._setup_instructor_with_entry(client, headers)

        today = date.today().isoformat()
        resp = await client.get(
            f"/api/v1/time-clock/timesheets?start={today}&end={today}",
            headers=headers,
        )
        assert resp.status_code == 200
        entries = resp.json()["data"]
        assert len(entries) >= 1

    async def test_approve_entry(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        instructor = await self._setup_instructor_with_entry(client, headers)

        # Get the entry
        today = date.today().isoformat()
        ts_resp = await client.get(
            f"/api/v1/time-clock/my-timesheet?instructor_id={instructor['id']}&start={today}&end={today}",
            headers=headers,
        )
        entry_id = ts_resp.json()["data"][0]["id"]

        # Approve
        resp = await client.put(
            f"/api/v1/time-clock/entries/{entry_id}/approve",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "approved"


@pytest.mark.asyncio
class TestPayroll:

    async def _setup_approved_entry(self, client, headers):
        data = {
            "display_name": f"Pay-{uuid.uuid4().hex[:6]}",
            "email": f"pay-{uuid.uuid4().hex[:8]}@test.auraflow.dev",
            "pay_rate_cents": 2000,
            "pay_type": "hourly",
        }
        resp = await client.post("/api/v1/instructors", json=data, headers=headers)
        assert resp.status_code == 201
        instructor = resp.json()

        # Clock in & out
        await client.post("/api/v1/time-clock/clock-in", json={
            "instructor_id": instructor["id"],
        }, headers=headers)
        await client.post("/api/v1/time-clock/clock-out", json={
            "instructor_id": instructor["id"],
        }, headers=headers)

        # Get entry and approve it
        today = date.today().isoformat()
        ts_resp = await client.get(
            f"/api/v1/time-clock/my-timesheet?instructor_id={instructor['id']}&start={today}&end={today}",
            headers=headers,
        )
        entry_id = ts_resp.json()["data"][0]["id"]
        await client.put(f"/api/v1/time-clock/entries/{entry_id}/approve", headers=headers)

        return instructor

    async def test_compile_payroll(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        await self._setup_approved_entry(client, headers)

        today = date.today().isoformat()
        week_ago = (date.today() - timedelta(days=7)).isoformat()

        resp = await client.post("/api/v1/time-clock/payroll/compile", json={
            "period_start": week_ago,
            "period_end": today,
        }, headers=headers)
        assert resp.status_code == 201
        run = resp.json()["data"]
        assert run["status"] == "draft"
        assert run["period_start"] == week_ago
        assert run["period_end"] == today

    async def test_finalize_payroll(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        await self._setup_approved_entry(client, headers)

        today = date.today().isoformat()
        start = (date.today() - timedelta(days=14)).isoformat()

        # Compile
        compile_resp = await client.post("/api/v1/time-clock/payroll/compile", json={
            "period_start": start,
            "period_end": today,
        }, headers=headers)
        run_id = compile_resp.json()["data"]["id"]

        # Finalize
        resp = await client.put(
            f"/api/v1/time-clock/payroll/{run_id}/finalize",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "finalized"
