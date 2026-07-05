"""
AuraFlow — Health Check Tests
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestHealth:
    async def test_health(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["platform"] == "AuraFlow"
        assert "version" in data

    async def test_readiness(self, client: AsyncClient):
        resp = await client.get("/health/ready")
        # May be 200 or 503 depending on whether Docker services are up
        data = resp.json()
        assert "status" in data
        assert "checks" in data
        assert "database" in data["checks"]
        assert "redis" in data["checks"]
