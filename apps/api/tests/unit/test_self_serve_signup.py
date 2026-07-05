"""AuraFlow — self-serve online-membership signup contracts.

Pins the org-independence + safety guards on the public enroll path, and the
welcome email composition (trial terms + standing Zoom link + schedule). The
enroll flow's deep DB writes are exercised by integration; here we lock the
entry contract and the member-facing email, which are the easiest to regress.
"""
import os
os.environ.setdefault("DATABASE_URL", "postgresql://test/test")
os.environ.setdefault("APP_SECRET", "test-secret-not-for-production-use-only")

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_global_db(org_row):
    db = MagicMock()
    db.__aenter__ = AsyncMock(return_value=db)
    db.__aexit__ = AsyncMock(return_value=False)
    db.fetchrow = AsyncMock(return_value=org_row)
    return db


@pytest.mark.asyncio
async def test_unknown_org_slug_raises_404():
    """Resolves the studio by slug — an unknown slug is a clean 404, no signup."""
    from app.services.members import self_serve_service as svc

    with patch.object(svc, "get_global_db", return_value=_mock_global_db(None)):
        with pytest.raises(svc.SignupError) as ei:
            await svc.enroll_online_membership(
                org_slug="nope", membership_type_id="m1",
                first_name="A", last_name="B", email="a@b.co",
                password="password123", source_id="cnon:card",
            )
    assert ei.value.status == 404


@pytest.mark.asyncio
async def test_non_square_org_rejected_before_any_charge():
    """A Stripe-billing studio can't use the Square self-serve trial path —
    rejected up front (org-independent: decided by the org's own provider)."""
    from app.services.members import self_serve_service as svc

    org = {
        "id": "org-1", "slug": "studioX", "schema_name": "af_tenant_studiox",
        "status": "active", "billing_provider": "stripe",
        "name": "Studio X", "timezone": "America/Los_Angeles",
    }
    with patch.object(svc, "get_global_db", return_value=_mock_global_db(org)):
        with pytest.raises(svc.SignupError) as ei:
            await svc.enroll_online_membership(
                org_slug="studioX", membership_type_id="m1",
                first_name="A", last_name="B", email="a@b.co",
                password="password123", source_id="cnon:card",
            )
    assert ei.value.status == 400
    assert ei.value.code == "WRONG_PROVIDER"


@pytest.mark.asyncio
async def test_welcome_email_includes_trial_zoom_and_schedule():
    """The online-membership welcome delivers the three day-one essentials:
    trial/billing terms, the standing Zoom link, and the week's schedule."""
    from app.services.email.email_service import EmailService

    svc = EmailService()
    captured = {}

    async def _capture(**kwargs):
        captured.update(kwargs)
        return {"status": "sent"}

    with patch.object(svc, "_get_studio_name", new=AsyncMock(return_value="Demo Studio")):
        with patch.object(svc, "send_email", new=_capture):
            await svc.send_online_membership_welcome(
                member_id="mem-1", to_email="f@x.co", member_name="Pat",
                membership_name="Online Unlimited", studio_name="Demo Studio",
                trial_end_display="July 3, 2026", price_display="$300.00/month",
                zoom_url="https://zoom.us/j/123456789",
                zoom_meeting_id="123 456 789", zoom_password="yoga",
                schedule=[{"when": "Mon Jun 30, 9:00 AM", "title": "Chair Yoga"}],
            )

    html = captured["html_content"]
    assert "https://zoom.us/j/123456789" in html       # standing zoom link
    assert "July 3, 2026" in html and "$300.00/month" in html  # trial terms
    assert "Chair Yoga" in html                          # schedule
    assert captured["email_type"] == "membership_welcome"
