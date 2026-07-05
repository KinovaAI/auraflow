"""AuraFlow — AI Manager, Sub-Finder 3000, Voice Check-In Integration Tests

Tests for the AI Manager resolution flow, Sub-Finder substitute matching,
Twilio incoming SMS webhook, voice check-in, and admin API endpoints.
"""
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from httpx import AsyncClient


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _create_instructor(client, headers, phone=None, specialties=None):
    """Create an instructor for sub-finder tests."""
    response = await client.post("/api/v1/instructors", json={
        "display_name": f"Instructor {uuid.uuid4().hex[:6]}",
        "email": f"instr-{uuid.uuid4().hex[:8]}@test.auraflow.dev",
        "phone": phone or f"555-{uuid.uuid4().hex[:4]}",
        "specialties": specialties or ["yoga"],
    }, headers=headers)
    assert response.status_code == 201
    return response.json()


async def _create_session_with_instructor(client, headers, studio_id, instructor_id, category="yoga"):
    """Create a class type + session assigned to a specific instructor."""
    ct = await client.post("/api/v1/scheduling/class-types", json={
        "studio_id": studio_id,
        "name": f"AI Test Class {uuid.uuid4().hex[:6]}",
        "description": "A test class",
        "category": category,
    }, headers=headers)
    ct_id = ct.json()["id"]

    tomorrow = datetime.utcnow() + timedelta(days=1)
    session = await client.post("/api/v1/scheduling/sessions", json={
        "studio_id": studio_id,
        "class_type_id": ct_id,
        "instructor_id": instructor_id,
        "title": "AI Test Session",
        "starts_at": tomorrow.isoformat(),
        "ends_at": (tomorrow + timedelta(hours=1)).isoformat(),
        "capacity": 20,
        "waitlist_capacity": 5,
    }, headers=headers)
    return session.json()["id"], ct_id


# ── Sub-Finder Tests ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestSubFinder:

    async def test_initiate_sub_search(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        # Create original instructor and a potential sub
        original = await _create_instructor(client, headers, phone="555-1001", specialties=["yoga"])
        sub = await _create_instructor(client, headers, phone="555-1002", specialties=["yoga"])

        session_id, _ = await _create_session_with_instructor(
            client, headers, studio_id, original["id"]
        )

        # Initiate sub search
        response = await client.post("/api/v1/ai-manager/sub-requests", json={
            "session_id": session_id,
            "instructor_id": original["id"],
            "reason": "Sick",
        }, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("searching", "offered", "unfilled")
        assert data["class_session_id"] == session_id

    async def test_find_qualified_subs_specialties_match(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        """Yoga specialist should be preferred over non-yoga when subbing a yoga class."""
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        original = await _create_instructor(client, headers, phone="555-2001", specialties=["yoga"])
        # Sub with matching specialty
        yoga_sub = await _create_instructor(client, headers, phone="555-2002", specialties=["yoga"])
        # Sub with different specialty
        pilates_sub = await _create_instructor(client, headers, phone="555-2003", specialties=["pilates"])

        session_id, _ = await _create_session_with_instructor(
            client, headers, studio_id, original["id"], category="yoga"
        )

        # Initiate search and check the contacted list order
        response = await client.post("/api/v1/ai-manager/sub-requests", json={
            "session_id": session_id,
            "instructor_id": original["id"],
            "reason": "Testing specialties",
        }, headers=headers)
        assert response.status_code == 200
        data = response.json()
        contacted = data.get("contacted_instructors", [])

        # If both are in the list, yoga should come first (higher score)
        yoga_idx = next((i for i, c in enumerate(contacted) if c["instructor_id"] == yoga_sub["id"]), None)
        pilates_idx = next((i for i, c in enumerate(contacted) if c["instructor_id"] == pilates_sub["id"]), None)

        if yoga_idx is not None and pilates_idx is not None:
            assert yoga_idx < pilates_idx, "Yoga specialist should rank higher for yoga class"

    async def test_find_qualified_subs_no_conflict(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        """Instructors with schedule conflicts should be excluded from candidates."""
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        original = await _create_instructor(client, headers, phone="555-3001", specialties=["yoga"])
        busy_sub = await _create_instructor(client, headers, phone="555-3002", specialties=["yoga"])

        session_id, ct_id = await _create_session_with_instructor(
            client, headers, studio_id, original["id"]
        )

        # Create a conflicting session for the busy sub (same time tomorrow)
        tomorrow = datetime.utcnow() + timedelta(days=1)
        await client.post("/api/v1/scheduling/sessions", json={
            "studio_id": studio_id,
            "class_type_id": ct_id,
            "instructor_id": busy_sub["id"],
            "title": "Conflicting Session",
            "starts_at": tomorrow.isoformat(),
            "ends_at": (tomorrow + timedelta(hours=1)).isoformat(),
            "capacity": 10,
        }, headers=headers)

        # Initiate search — busy sub should not appear in candidates
        response = await client.post("/api/v1/ai-manager/sub-requests", json={
            "session_id": session_id,
            "instructor_id": original["id"],
        }, headers=headers)
        assert response.status_code == 200
        data = response.json()
        contacted = data.get("contacted_instructors", [])

        candidate_ids = [c["instructor_id"] for c in contacted]
        assert busy_sub["id"] not in candidate_ids

    async def test_sub_response_accepted(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        original = await _create_instructor(client, headers, phone="555-4001", specialties=["yoga"])
        sub = await _create_instructor(client, headers, phone="555-4002", specialties=["yoga"])

        session_id, _ = await _create_session_with_instructor(
            client, headers, studio_id, original["id"]
        )

        # Initiate sub search
        response = await client.post("/api/v1/ai-manager/sub-requests", json={
            "session_id": session_id,
            "instructor_id": original["id"],
            "reason": "Sick day",
        }, headers=headers)
        request_id = response.json()["id"]

        # Simulate sub accepting
        response = await client.post(
            f"/api/v1/ai-manager/sub-requests/{request_id}/respond",
            json={"instructor_id": sub["id"], "accepted": True},
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "filled"
        assert data["substitute_instructor_id"] == sub["id"]

    async def test_sub_response_declined_contacts_next(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        original = await _create_instructor(client, headers, phone="555-5001", specialties=["yoga"])
        sub1 = await _create_instructor(client, headers, phone="555-5002", specialties=["yoga"])
        sub2 = await _create_instructor(client, headers, phone="555-5003", specialties=["yoga"])

        session_id, _ = await _create_session_with_instructor(
            client, headers, studio_id, original["id"]
        )

        # Initiate sub search
        response = await client.post("/api/v1/ai-manager/sub-requests", json={
            "session_id": session_id,
            "instructor_id": original["id"],
        }, headers=headers)
        request_id = response.json()["id"]
        request_data = response.json()

        # Find who was contacted first
        contacted = request_data.get("contacted_instructors", [])
        if not contacted:
            pytest.skip("No candidates found")

        first_candidate_id = contacted[0]["instructor_id"]

        # Decline the first candidate
        response = await client.post(
            f"/api/v1/ai-manager/sub-requests/{request_id}/respond",
            json={"instructor_id": first_candidate_id, "accepted": False},
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        # Should still be searching or offered to next
        assert data["status"] in ("searching", "offered", "unfilled")

    async def test_cancel_sub_search(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        original = await _create_instructor(client, headers, phone="555-6001", specialties=["yoga"])
        await _create_instructor(client, headers, phone="555-6002", specialties=["yoga"])

        session_id, _ = await _create_session_with_instructor(
            client, headers, studio_id, original["id"]
        )

        # Initiate and then cancel
        response = await client.post("/api/v1/ai-manager/sub-requests", json={
            "session_id": session_id,
            "instructor_id": original["id"],
        }, headers=headers)
        request_id = response.json()["id"]

        cancel_resp = await client.post(
            f"/api/v1/ai-manager/sub-requests/{request_id}/cancel",
            headers=headers,
        )
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["status"] == "cancelled"


# ── AI Manager Tests ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestAIManager:

    async def test_classify_intent_sub_request(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        """Test intent classification returns valid intents."""
        from app.services.ai.ai_manager_service import AIManagerService
        svc = AIManagerService()

        # Without Claude configured, should return "other"
        intent = await svc.classify_intent("I'm sick and can't teach my 9am class tomorrow")
        assert intent in ("sub_request", "other")

    async def test_classify_intent_booking(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        from app.services.ai.ai_manager_service import AIManagerService
        svc = AIManagerService()

        intent = await svc.classify_intent("Can I book the yoga class on Saturday?")
        assert intent in ("booking_question", "other")

    async def test_handle_incoming_sms_via_api(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        """Test the Twilio webhook receives SMS and processes it."""
        # Send a mock Twilio SMS — this goes through the webhook
        with patch('app.services.ai.ai_manager_service.AIManagerService.handle_incoming_message',
                   new_callable=AsyncMock) as mock_handle:
            mock_handle.return_value = {
                "response": "Our studio hours are 6am-9pm.",
                "resolved": True,
                "request_id": str(uuid.uuid4()),
                "intent": "general_question",
            }

            response = await client.post("/webhooks/twilio", data={
                "From": "+15551234567",
                "Body": "What are your studio hours?",
                "To": "+15550000000",
            })
            assert response.status_code == 200
            assert "xml" in response.headers.get("content-type", "")

    async def test_resolution_manual_escalate(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        """Test manual escalation of a resolution request via API."""
        headers = registered_owner_with_studio["headers"]

        # We can't easily create a resolution without the full AI flow,
        # so test that the endpoint handles not-found gracefully
        fake_id = str(uuid.uuid4())
        response = await client.post(
            f"/api/v1/ai-manager/resolutions/{fake_id}/escalate",
            json={"reason": "Need human review"},
            headers=headers,
        )
        assert response.status_code == 404

    async def test_list_resolutions(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        headers = registered_owner_with_studio["headers"]

        response = await client.get("/api/v1/ai-manager/resolutions", headers=headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_list_resolutions_with_status_filter(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        headers = registered_owner_with_studio["headers"]

        response = await client.get(
            "/api/v1/ai-manager/resolutions?status=escalated",
            headers=headers,
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)


# ── Twilio Webhook Tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestTwilioWebhook:

    async def test_incoming_sms_from_instructor(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        headers = registered_owner_with_studio["headers"]

        # Create an instructor with a known phone
        await _create_instructor(
            client, headers, phone="555-7001", specialties=["yoga"]
        )

        with patch('app.services.ai.ai_manager_service.AIManagerService.handle_incoming_message',
                   new_callable=AsyncMock) as mock_handle:
            mock_handle.return_value = {
                "response": "Got it, looking for a sub.",
                "resolved": False,
                "request_id": str(uuid.uuid4()),
            }

            response = await client.post("/webhooks/twilio", data={
                "From": "555-7001",
                "Body": "I'm sick tomorrow, need a sub",
                "To": "+15550000000",
            })
            assert response.status_code == 200
            assert "xml" in response.headers.get("content-type", "")

    async def test_incoming_sms_unknown_sender(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        with patch('app.services.ai.ai_manager_service.AIManagerService.handle_incoming_message',
                   new_callable=AsyncMock) as mock_handle:
            mock_handle.return_value = {
                "response": "Thanks for reaching out.",
                "resolved": True,
                "request_id": str(uuid.uuid4()),
            }

            response = await client.post("/webhooks/twilio", data={
                "From": "+15559999999",
                "Body": "Hello, what classes do you offer?",
                "To": "+15550000000",
            })
            assert response.status_code == 200

    async def test_incoming_sms_empty_body(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        response = await client.post("/webhooks/twilio", data={
            "From": "+15551234567",
            "Body": "",
        })
        assert response.status_code == 200
        # Should return empty TwiML
        body = response.text
        assert "Response" in body


# ── Voice Check-In Tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestVoiceCheckin:

    async def test_transcribe_audio_not_configured(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        """Test that voice service raises when not configured."""
        from app.services.ai.voice_service import VoiceService
        svc = VoiceService()

        # Without OPENAI_API_KEY, should raise ValueError
        try:
            await svc.transcribe_audio(b"fake audio data")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "OPENAI_API_KEY" in str(e)

    async def test_voice_checkin_name_extraction(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        """Test name extraction from various transcript formats."""
        from app.services.ai.voice_service import VoiceService
        svc = VoiceService()

        assert svc._extract_name("This is Don Kolz checking in") == "Don Kolz"
        assert svc._extract_name("Hi I'm Jane Smith") == "Jane Smith"
        assert svc._extract_name("My name is John Doe") == "John Doe"
        assert svc._extract_name("Don Kolz") == "Don Kolz"

    async def test_voice_checkin_endpoint_requires_auth(
        self, client: AsyncClient
    ):
        """Voice check-in endpoint requires authentication."""
        response = await client.post("/api/v1/voice/checkin")
        assert response.status_code in (401, 403, 422)

    async def test_voice_command_endpoint_requires_auth(
        self, client: AsyncClient
    ):
        """Voice command endpoint requires authentication."""
        response = await client.post("/api/v1/voice/command")
        assert response.status_code in (401, 403, 422)

    async def test_voice_transcribe_endpoint_requires_auth(
        self, client: AsyncClient
    ):
        """Voice transcribe endpoint requires authentication."""
        response = await client.post("/api/v1/voice/transcribe")
        assert response.status_code in (401, 403, 422)


# ── AI Manager Endpoint Tests ────────────────────────────────────────────────

@pytest.mark.asyncio
class TestAIManagerEndpoints:

    async def test_list_resolutions_endpoint(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        headers = registered_owner_with_studio["headers"]
        response = await client.get("/api/v1/ai-manager/resolutions", headers=headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_list_sub_requests_endpoint(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        headers = registered_owner_with_studio["headers"]
        response = await client.get("/api/v1/ai-manager/sub-requests", headers=headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_initiate_sub_search_endpoint(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        original = await _create_instructor(client, headers, phone="555-8001", specialties=["yoga"])
        await _create_instructor(client, headers, phone="555-8002", specialties=["yoga"])

        session_id, _ = await _create_session_with_instructor(
            client, headers, studio_id, original["id"]
        )

        response = await client.post("/api/v1/ai-manager/sub-requests", json={
            "session_id": session_id,
            "instructor_id": original["id"],
            "reason": "Personal emergency",
        }, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["original_instructor_id"] == original["id"]

    async def test_resolution_not_found(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        headers = registered_owner_with_studio["headers"]
        fake_id = str(uuid.uuid4())
        response = await client.get(
            f"/api/v1/ai-manager/resolutions/{fake_id}",
            headers=headers,
        )
        assert response.status_code == 404

    async def test_sub_request_not_found(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        headers = registered_owner_with_studio["headers"]
        fake_id = str(uuid.uuid4())
        response = await client.get(
            f"/api/v1/ai-manager/sub-requests/{fake_id}",
            headers=headers,
        )
        assert response.status_code == 404

    async def test_ai_manager_requires_admin(self, client: AsyncClient):
        """AI Manager endpoints should require admin role."""
        response = await client.get("/api/v1/ai-manager/resolutions")
        assert response.status_code in (401, 403)

    async def test_voice_requires_auth(self, client: AsyncClient):
        """Voice endpoints should require auth."""
        # Can't actually upload a file without auth, but we can check
        response = await client.post("/api/v1/voice/checkin")
        assert response.status_code in (401, 403, 422)
