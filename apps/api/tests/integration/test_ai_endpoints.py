"""AuraFlow — AI Endpoint Integration Tests

Tests AI endpoints. When ANTHROPIC_API_KEY is not set, the service
returns a placeholder message instead of calling Claude.
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestAIGeneration:

    async def test_generate_class_description(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        resp = await client.post("/api/v1/ai/generate/class-description", json={
            "class_name": "Vinyasa Flow",
            "class_type": "yoga",
            "level": "all levels",
            "duration_minutes": 60,
        }, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "description" in data
        assert len(data["description"]) > 0

    async def test_generate_marketing_email(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        resp = await client.post("/api/v1/ai/generate/marketing-email", json={
            "subject_context": "Spring promotion — 20% off all memberships",
            "audience": "inactive members",
        }, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "subject" in data or "raw" in data

    async def test_generate_social_post(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        resp = await client.post("/api/v1/ai/generate/social-post", json={
            "topic": "New yoga workshop this weekend",
            "platform": "instagram",
        }, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "post" in data


@pytest.mark.asyncio
class TestAIAnalysis:

    async def test_churn_risk_analysis(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        resp = await client.post("/api/v1/ai/analyze/churn-risk", json={
            "total_visits": 3,
            "last_visit_at": "2025-12-01",
            "membership_status": "active",
            "joined_at": "2025-06-01",
            "lifetime_revenue_cents": 15000,
            "recent_cancellations": 2,
            "days_since_visit": 90,
        }, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "analysis" in data

    async def test_schedule_suggestions(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        resp = await client.post("/api/v1/ai/analyze/schedule", json={
            "current_schedule_summary": "Mon/Wed/Fri: Vinyasa 9am (20 cap), Tue/Thu: Yin 6pm (15 cap)",
            "attendance_data": "Vinyasa avg 18/20, Yin avg 8/15",
            "studio_context": "Small yoga studio in Fresno, CA",
        }, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "suggestions" in data
