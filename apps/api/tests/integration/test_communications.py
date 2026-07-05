"""AuraFlow — Communications Integration Tests

Tests for communication preferences, booking email/SMS triggers,
SendGrid webhook processing, and communications settings endpoints.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestCommunicationPreferences:

    async def _create_member(self, client, headers, phone=None):
        data = {
            "first_name": "Comms",
            "last_name": f"Test-{uuid.uuid4().hex[:6]}",
            "email": f"comms-{uuid.uuid4().hex[:8]}@test.auraflow.dev",
        }
        if phone:
            data["phone"] = phone
        resp = await client.post("/api/v1/members", json=data, headers=headers)
        assert resp.status_code == 201
        return resp.json()

    async def test_member_has_default_opt_in(self, client: AsyncClient, registered_owner_with_studio):
        """New members should have email_opt_in=True and sms_opt_in=True by default."""
        headers = registered_owner_with_studio["headers"]
        member = await self._create_member(client, headers)

        resp = await client.get(f"/api/v1/members/{member['id']}", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("email_opt_in") is True
        assert data.get("sms_opt_in") is True

    async def test_update_member_opt_out(self, client: AsyncClient, registered_owner_with_studio):
        """Should be able to set email_opt_in and sms_opt_in to False."""
        headers = registered_owner_with_studio["headers"]
        member = await self._create_member(client, headers)

        resp = await client.put(f"/api/v1/members/{member['id']}", json={
            "email_opt_in": False,
            "sms_opt_in": False,
        }, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("email_opt_in") is False
        assert data.get("sms_opt_in") is False


@pytest.mark.asyncio
class TestBookingNotifications:

    async def _setup_booking(self, client, headers, studio_id):
        """Create class type, session, and member for booking tests."""
        # Class type
        ct_resp = await client.post("/api/v1/scheduling/class-types", json={
            "studio_id": studio_id,
            "name": f"Email Test Class-{uuid.uuid4().hex[:4]}",
            "duration_minutes": 60,
        }, headers=headers)
        assert ct_resp.status_code == 201
        class_type = ct_resp.json()

        # Session
        session_resp = await client.post("/api/v1/scheduling/sessions", json={
            "studio_id": studio_id,
            "class_type_id": class_type["id"],
            "title": "Notify Test Session",
            "starts_at": "2026-04-01T10:00:00Z",
            "ends_at": "2026-04-01T11:00:00Z",
            "capacity": 20,
        }, headers=headers)
        assert session_resp.status_code == 201
        session = session_resp.json()

        # Member
        member_resp = await client.post("/api/v1/members", json={
            "first_name": "Notify",
            "last_name": f"Test-{uuid.uuid4().hex[:4]}",
            "email": f"notify-{uuid.uuid4().hex[:6]}@test.auraflow.dev",
            "phone": "+15551234567",
        }, headers=headers)
        assert member_resp.status_code == 201
        member = member_resp.json()

        return session, member

    @patch("app.services.scheduling.booking_service.EmailService.send_booking_confirmation")
    @patch("app.services.scheduling.booking_service.SmsService.send_booking_confirmation")
    async def test_booking_sends_confirmation(
        self, mock_sms, mock_email,
        client: AsyncClient, registered_owner_with_studio
    ):
        """Booking a class should trigger email and SMS confirmations."""
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        session, member = await self._setup_booking(client, headers, studio_id)

        mock_email.return_value = {"id": "test", "status": "sent"}
        mock_sms.return_value = {"id": "test", "status": "sent"}

        resp = await client.post("/api/v1/scheduling/bookings", json={
            "member_id": member["id"],
            "class_session_id": session["id"],
        }, headers=headers)
        assert resp.status_code == 201
        assert resp.json()["status"] == "confirmed"

        # Email and SMS should have been called
        mock_email.assert_called_once()
        mock_sms.assert_called_once()

        # Verify the member_id was passed
        assert mock_email.call_args.kwargs["member_id"] == member["id"]

    @patch("app.services.scheduling.booking_service.EmailService.send_booking_cancellation")
    @patch("app.services.scheduling.booking_service.SmsService.send_booking_cancellation")
    async def test_cancel_sends_notification(
        self, mock_sms, mock_email,
        client: AsyncClient, registered_owner_with_studio
    ):
        """Cancelling a booking should send cancellation notifications."""
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        session, member = await self._setup_booking(client, headers, studio_id)

        mock_email.return_value = {"id": "test", "status": "sent"}
        mock_sms.return_value = {"id": "test", "status": "sent"}

        # Book first (also mocking confirmation calls)
        with patch("app.services.scheduling.booking_service.EmailService.send_booking_confirmation"):
            with patch("app.services.scheduling.booking_service.SmsService.send_booking_confirmation"):
                book_resp = await client.post("/api/v1/scheduling/bookings", json={
                    "member_id": member["id"],
                    "class_session_id": session["id"],
                }, headers=headers)
        booking_id = book_resp.json()["id"]

        # Cancel
        resp = await client.delete(
            f"/api/v1/scheduling/bookings/{booking_id}",
            headers=headers,
        )
        assert resp.status_code == 204

        mock_email.assert_called_once()
        mock_sms.assert_called_once()


@pytest.mark.asyncio
class TestSendGridWebhook:

    async def test_sendgrid_webhook_endpoint_exists(self, client: AsyncClient):
        """POST /webhooks/sendgrid should accept events."""
        resp = await client.post("/webhooks/sendgrid", json=[])
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_sendgrid_webhook_processes_delivered(self, client: AsyncClient, registered_owner_with_studio):
        """SendGrid delivered event should update communication_log status."""
        # Send a batch of events — even with no matching records, endpoint shouldn't error
        events = [
            {
                "event": "delivered",
                "sg_message_id": "fake_message_id.filter123",
                "email": "test@example.com",
                "timestamp": 1709000000,
            },
        ]
        resp = await client.post("/webhooks/sendgrid", json=events)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        # No matching record, so processed should be 0
        assert data["processed"] == 0

    async def test_sendgrid_webhook_invalid_json(self, client: AsyncClient):
        """Invalid JSON should return 400."""
        resp = await client.post(
            "/webhooks/sendgrid",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400


@pytest.mark.asyncio
class TestCommunicationsSettings:

    async def test_get_communications_status(self, client: AsyncClient, registered_owner_with_studio):
        """GET /integrations/communications/status returns connection status."""
        headers = registered_owner_with_studio["headers"]
        resp = await client.get("/api/v1/integrations/communications/status", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "sendgrid_connected" in data
        assert "twilio_connected" in data
        assert data["sendgrid_connected"] is False
        assert data["twilio_connected"] is False

    async def test_connect_sendgrid(self, client: AsyncClient, registered_owner_with_studio):
        """POST /integrations/communications/sendgrid/connect stores encrypted credentials."""
        headers = registered_owner_with_studio["headers"]
        resp = await client.post("/api/v1/integrations/communications/sendgrid/connect", json={
            "api_key": "SG.test-key-12345",
            "from_email": "studio@test.com",
            "from_name": "Test Studio",
        }, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "connected"

        # Verify status shows connected
        status_resp = await client.get("/api/v1/integrations/communications/status", headers=headers)
        data = status_resp.json()
        assert data["sendgrid_connected"] is True
        assert data["sendgrid_from_email"] == "studio@test.com"

    async def test_disconnect_sendgrid(self, client: AsyncClient, registered_owner_with_studio):
        """DELETE /integrations/communications/sendgrid/disconnect clears credentials."""
        headers = registered_owner_with_studio["headers"]
        # Connect first
        await client.post("/api/v1/integrations/communications/sendgrid/connect", json={
            "api_key": "SG.test-key-disconnect",
        }, headers=headers)

        # Disconnect
        resp = await client.delete(
            "/api/v1/integrations/communications/sendgrid/disconnect",
            headers=headers,
        )
        assert resp.status_code == 200

        # Verify disconnected
        status_resp = await client.get("/api/v1/integrations/communications/status", headers=headers)
        assert status_resp.json()["sendgrid_connected"] is False

    async def test_connect_twilio(self, client: AsyncClient, registered_owner_with_studio):
        """POST /integrations/communications/twilio/connect stores encrypted credentials."""
        headers = registered_owner_with_studio["headers"]
        resp = await client.post("/api/v1/integrations/communications/twilio/connect", json={
            "account_sid": "ACtest12345",
            "auth_token": "test-auth-token",
            "phone_number": "+15551234567",
        }, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "connected"

        # Verify status
        status_resp = await client.get("/api/v1/integrations/communications/status", headers=headers)
        data = status_resp.json()
        assert data["twilio_connected"] is True
        assert data["twilio_phone_number"] == "+15551234567"

    async def test_disconnect_twilio(self, client: AsyncClient, registered_owner_with_studio):
        """DELETE /integrations/communications/twilio/disconnect clears credentials."""
        headers = registered_owner_with_studio["headers"]
        await client.post("/api/v1/integrations/communications/twilio/connect", json={
            "account_sid": "ACtest-disconnect",
            "auth_token": "test-token",
            "phone_number": "+15559876543",
        }, headers=headers)

        resp = await client.delete(
            "/api/v1/integrations/communications/twilio/disconnect",
            headers=headers,
        )
        assert resp.status_code == 200

        status_resp = await client.get("/api/v1/integrations/communications/status", headers=headers)
        assert status_resp.json()["twilio_connected"] is False
