"""AuraFlow — Analytics Integration Tests

Tests analytics endpoints with seeded data: revenue, attendance,
memberships, utilization, and dashboard KPIs.
"""
import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestDashboardKPIs:

    async def test_dashboard_kpis_empty(self, client: AsyncClient, registered_owner_with_studio):
        """Dashboard KPIs should work even with no data."""
        headers = registered_owner_with_studio["headers"]
        resp = await client.get("/api/v1/analytics/dashboard?days=30", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "revenue" in data
        assert "active_members" in data
        assert "active_memberships" in data
        assert "attendance" in data
        assert data["revenue"] == 0
        assert data["period_days"] == 30

    async def test_dashboard_kpis_with_data(self, client: AsyncClient, registered_owner_with_studio):
        """Dashboard should reflect transactions."""
        headers = registered_owner_with_studio["headers"]

        # Seed a member + transaction
        member_resp = await client.post("/api/v1/members", json={
            "first_name": "KPI",
            "last_name": f"Test-{uuid.uuid4().hex[:6]}",
            "email": f"kpi-{uuid.uuid4().hex[:8]}@test.auraflow.dev",
        }, headers=headers)
        member = member_resp.json()

        await client.post("/api/v1/payments/transactions", json={
            "member_id": member["id"],
            "amount_cents": 15000,
            "description": "KPI test",
        }, headers=headers)

        resp = await client.get("/api/v1/analytics/dashboard?days=30", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["revenue"] >= 15000
        assert data["transaction_count"] >= 1
        assert data["active_members"] >= 1


@pytest.mark.asyncio
class TestRevenueReports:

    async def _seed_transaction(self, client, headers, amount=5000):
        member_resp = await client.post("/api/v1/members", json={
            "first_name": "Rev",
            "last_name": f"Test-{uuid.uuid4().hex[:6]}",
            "email": f"rev-{uuid.uuid4().hex[:8]}@test.auraflow.dev",
        }, headers=headers)
        member = member_resp.json()
        await client.post("/api/v1/payments/transactions", json={
            "member_id": member["id"],
            "amount_cents": amount,
            "type": "payment",
            "description": "Analytics test",
        }, headers=headers)

    async def test_revenue_over_time(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        await self._seed_transaction(client, headers, amount=8000)

        resp = await client.get(
            "/api/v1/analytics/revenue/over-time?days=30&group_by=day",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)
        if data:
            assert "period" in data[0]
            assert "revenue" in data[0]

    async def test_revenue_by_type(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        await self._seed_transaction(client, headers)

        resp = await client.get("/api/v1/analytics/revenue/by-type?days=30", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)
        if data:
            assert "type" in data[0]
            assert "revenue" in data[0]


@pytest.mark.asyncio
class TestAttendanceReports:

    async def test_attendance_over_time_empty(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        resp = await client.get(
            "/api/v1/analytics/attendance/over-time?days=30",
            headers=headers,
        )
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)

    async def test_attendance_by_class_type_empty(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        resp = await client.get(
            "/api/v1/analytics/attendance/by-class-type?days=30",
            headers=headers,
        )
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)


@pytest.mark.asyncio
class TestMembershipReports:

    async def test_membership_summary(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        resp = await client.get("/api/v1/analytics/memberships/summary", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "active" in data
        assert "total" in data

    async def test_membership_by_type(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        resp = await client.get("/api/v1/analytics/memberships/by-type", headers=headers)
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)

    async def test_churn_rate(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        resp = await client.get("/api/v1/analytics/memberships/churn?days=30", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "churn_rate_percent" in data
        assert "currently_active" in data


@pytest.mark.asyncio
class TestUtilizationReports:

    async def test_room_utilization(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        resp = await client.get("/api/v1/analytics/utilization/rooms?days=30", headers=headers)
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)


@pytest.mark.asyncio
class TestInstructorReports:

    async def test_instructor_summary(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        resp = await client.get("/api/v1/analytics/instructors?days=30", headers=headers)
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)
