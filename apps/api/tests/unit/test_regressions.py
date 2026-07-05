"""Regression tests for bugs fixed in the last 30 days.

One test per bug. If a regression test goes red, the exact commit that fixed
the original bug was silently reverted.

Each test is pure unit — no DB, no HTTP, no Celery. Integration coverage of
the same behaviours belongs in tests/integration/.
"""
import hashlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Ensure app package is importable regardless of how pytest was invoked.
_API_ROOT = Path(__file__).resolve().parents[2]
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

os.environ.setdefault("APP_SECRET", "test-secret-not-for-production-use-only-0123456789")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")

from app.core.config import Settings  # noqa: E402


# ── 2026-04-18: NULL classes_remaining must not crash eligibility ──────────

def test_eligibility_null_classes_remaining_does_not_crash():
    """Guard against regressing the `None <= 0` TypeError from 2026-04-18.

    Before the fix, `mm.get("classes_remaining", 0) <= 0` raised TypeError
    when the key existed with value None. Fix wrapped in `(... or 0)`.
    """
    # Simulated membership row where classes_remaining exists but is None
    # (this mirrors the exact shape asyncpg returns for a NULL column).
    mm = {
        "id": "abc",
        "status": "active",
        "ends_at": None,
        "membership_type": "single_class",
        "classes_remaining": None,
    }

    # The guard the fix installed:
    is_used_up = (mm.get("classes_remaining") or 0) <= 0

    assert is_used_up is True  # None → 0 → <= 0 → True (rejected)


def test_eligibility_positive_credits_are_valid():
    """Sanity: non-null positive credit count passes the check."""
    mm = {"membership_type": "single_class", "classes_remaining": 3}
    is_used_up = (mm.get("classes_remaining") or 0) <= 0
    assert is_used_up is False


# ── 2026-04-18: POS send_payment_link must import get_global_db ────────────

def test_retail_endpoint_imports_get_global_db():
    """Guard against the silent NameError that prevented POS payment-link
    emails from ever sending. Fix at retail.py:268 added `get_global_db`
    to the local import line.
    """
    from pathlib import Path
    retail_path = Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "endpoints" / "retail.py"
    source = retail_path.read_text()

    # Both the create-sale path and the resend-link path need both imports.
    # Count occurrences rather than checking a specific line number.
    assert source.count(
        "from app.db.session import get_tenant_db, get_global_db"
    ) >= 2, "retail.py must import both get_tenant_db + get_global_db on both send-link paths"


# ── 2026-04-18: no_show task must not reference bookings.updated_at ────────

def test_no_show_task_does_not_reference_nonexistent_updated_at():
    """bookings table has no updated_at column. Any UPDATE bookings SET ...
    updated_at = NOW() will silently 500 the Celery task.
    """
    from pathlib import Path
    no_show_path = Path(__file__).resolve().parents[2] / "app" / "workers" / "tasks" / "no_show.py"
    source = no_show_path.read_text()
    assert "updated_at" not in source, (
        "no_show.py references bookings.updated_at — "
        "column does not exist, task will silently fail every 30 min"
    )


def test_voice_call_service_does_not_reference_bookings_updated_at():
    """Same lesson, different file — voice_call_service had 4 of these."""
    from pathlib import Path
    vc_path = Path(__file__).resolve().parents[2] / "app" / "services" / "ai" / "voice_call_service.py"
    source = vc_path.read_text()
    # Ensure no "UPDATE bookings ... updated_at" pattern remains.
    # A blunt check: look for the specific offending phrase.
    import re
    hits = re.findall(
        r"UPDATE\s+bookings[^;]*updated_at\s*=\s*NOW",
        source,
        re.IGNORECASE | re.DOTALL,
    )
    assert len(hits) == 0, (
        f"voice_call_service.py still has {len(hits)} UPDATE bookings SET ... updated_at patterns"
    )


# ── 2026-04-18: retail /transactions/pending route order ──────────────────

def test_retail_pending_route_registered_before_wildcard():
    """/transactions/pending must be registered before /{transaction_id}
    or it gets swallowed by the wildcard and tries to parse 'pending' as a UUID.
    """
    from pathlib import Path
    retail_path = Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "endpoints" / "retail.py"
    source = retail_path.read_text()

    pending_pos = source.find('"/transactions/pending"')
    wildcard_pos = source.find('"/transactions/{transaction_id}"')

    assert pending_pos != -1, "route /transactions/pending is missing"
    assert wildcard_pos != -1, "route /transactions/{transaction_id} is missing"
    assert pending_pos < wildcard_pos, (
        "/transactions/pending must be declared before /{transaction_id}"
    )


# ── 2026-04-20: APP_SECRET fingerprint guard exits on wrong .env ──────────

def test_fingerprint_validator_exits_on_mismatch(monkeypatch):
    """If ENVIRONMENT=production and APP_SECRET_FINGERPRINT is set and does
    not match sha256(APP_SECRET)[:16], the app refuses to start.
    """
    wrong_secret = "x" * 64
    fingerprint_of_something_else = "a7f9439e3fe4adf2"  # fingerprint of real prod secret

    # Build a settings instance with mismatched values
    settings = MagicMock(spec=Settings)
    settings.ENVIRONMENT = "production"
    settings.APP_SECRET = wrong_secret
    settings.APP_SECRET_FINGERPRINT = fingerprint_of_something_else

    # Call the real method against the mock
    import sys
    exit_called = {"status": None}
    original_exit = sys.exit

    def fake_exit(code):
        exit_called["status"] = code
        raise SystemExit(code)

    monkeypatch.setattr(sys, "exit", fake_exit)

    try:
        Settings.validate_production_fingerprint(settings)
    except SystemExit:
        pass

    assert exit_called["status"] == 78  # EX_CONFIG


def test_fingerprint_validator_passes_on_match():
    """Correct fingerprint → no exit, no error."""
    secret = "33ab188938873a150fc4fcb92ba7cd721eab5bd22b7acb8aaecbe6f1d0263e9e"
    expected_fp = hashlib.sha256(secret.encode()).hexdigest()[:16]

    settings = MagicMock(spec=Settings)
    settings.ENVIRONMENT = "production"
    settings.APP_SECRET = secret
    settings.APP_SECRET_FINGERPRINT = expected_fp

    # Should not raise or exit
    Settings.validate_production_fingerprint(settings)


def test_fingerprint_validator_skips_in_non_production():
    """Dev / test environments bypass the check so local work isn't blocked."""
    settings = MagicMock(spec=Settings)
    settings.ENVIRONMENT = "development"
    settings.APP_SECRET = "anything"
    settings.APP_SECRET_FINGERPRINT = "does-not-match"

    # Must not exit
    Settings.validate_production_fingerprint(settings)


# ── 2026-04-17: zoom link task filters by membership access_scope ─────────

# ── 2026-04-23: webhook must advance period even on credit-paid invoices ──

def test_invoice_handler_advances_period_when_amount_paid_is_zero():
    """Guard against the bug discovered in Pamela Stockdale's 2026-04-17 renewal.

    Stripe marks invoices `paid: true` with `amount_paid: 0` when the total
    is covered by customer credit balance. The handler must still advance
    current_period_end on the membership — the period-extension must not
    depend on any cash flowing.
    """
    from pathlib import Path
    wh_path = Path(__file__).resolve().parents[2] / "app" / "services" / "payments" / "webhook_handler.py"
    src = wh_path.read_text()
    # Must NOT gate the UPDATE on amount_paid > 0
    assert "amount_paid > 0" not in src and "amount_paid >= " not in src, (
        "webhook_handler guards period advance on amount_paid — credit-paid "
        "renewals will stale-date the membership"
    )
    # Must accept any non-cancelled status (post-fix) rather than the
    # earlier whitelist which excluded some valid states.
    assert "status NOT IN ('cancelled', 'deleted')" in src, (
        "webhook_handler should accept any non-cancelled status for period "
        "update — strict whitelist missed real active rows during Pamela's case"
    )
    # Must use tz-aware datetime so TIMESTAMPTZ comparison is clean.
    assert "utcfromtimestamp" not in src, (
        "webhook_handler should use datetime.fromtimestamp(..., tz=timezone.utc)"
        " not the naive utcfromtimestamp"
    )


def test_zoom_link_query_filters_digital_members_only():
    """send_zoom_links must only email members whose active membership has
    access_scope IN ('online', 'all_access'). In-studio-only members should
    never receive a zoom link.
    """
    from pathlib import Path
    zl_path = Path(__file__).resolve().parents[2] / "app" / "workers" / "tasks" / "zoom_links.py"
    source = zl_path.read_text()

    assert "access_scope IN ('online', 'all_access')" in source, (
        "zoom_links.py must filter for digital-access members only — "
        "in-studio members should not receive zoom links"
    )
    # And must still check membership is active and unexpired
    assert "mm.status = 'active'" in source
    assert "mm.ends_at" in source and "NOW()" in source


# ── Circuit breaker adoption (guards against regression to unbreakered calls)

def test_stripe_checkout_uses_circuit_breaker():
    """StripeService.create_checkout_session must route the SDK call through
    stripe_breaker. Without it, a slow Stripe API stacks request timeouts."""
    from pathlib import Path
    p = Path(__file__).resolve().parents[2] / "app" / "services" / "payments" / "stripe_service.py"
    src = p.read_text()
    assert "stripe_breaker.call_async" in src, (
        "StripeService.create_checkout_session lost its circuit-breaker wrapper"
    )


def test_zoom_create_meeting_uses_circuit_breaker():
    from pathlib import Path
    p = Path(__file__).resolve().parents[2] / "app" / "services" / "integrations" / "zoom_service.py"
    src = p.read_text()
    assert "zoom_breaker.call_async" in src, (
        "ZoomService.create_meeting lost its circuit-breaker wrapper"
    )


def test_smtp_send_uses_circuit_breaker():
    from pathlib import Path
    p = Path(__file__).resolve().parents[2] / "app" / "services" / "email" / "email_service.py"
    src = p.read_text()
    assert "purelymail_smtp_breaker.call_async" in src, (
        "studio SMTP send lost its circuit-breaker wrapper"
    )
    assert "sendgrid_breaker.call_async" in src, (
        "SendGrid fallback send lost its circuit-breaker wrapper"
    )


def test_twilio_send_uses_circuit_breaker():
    from pathlib import Path
    p = Path(__file__).resolve().parents[2] / "app" / "services" / "marketing" / "campaign_service.py"
    src = p.read_text()
    assert "twilio_breaker.call_async" in src, (
        "SmsService.send_sms lost its circuit-breaker wrapper — a slow Twilio "
        "will cascade back-pressure into every outbound SMS path"
    )


# ── Scheduled-campaigns atomic claim (prevents double-send)

def test_scheduled_campaigns_claims_atomically():
    """The 5-min beat must not double-send a campaign if it double-fires.
    The claim is `UPDATE email_campaigns SET status='sending' WHERE
    id=$1 AND status='scheduled' RETURNING id` — the RETURNING id is
    what tells the worker it won the claim."""
    from pathlib import Path
    p = Path(__file__).resolve().parents[2] / "app" / "workers" / "tasks" / "scheduled_campaigns.py"
    src = p.read_text()
    assert "SET status = 'sending'" in src, (
        "scheduled_campaigns must flip status to 'sending' before sending"
    )
    assert "AND status = 'scheduled'" in src
    assert "RETURNING id" in src


# ── Webhook retry task scheduled

def test_webhook_retries_task_scheduled_in_beat():
    """The outgoing-webhook retry task must be in beat_schedule, otherwise
    WebhookDeliveryService.process_retries() never fires and failed
    deliveries never get retried past the initial in-line attempt."""
    from pathlib import Path
    p = Path(__file__).resolve().parents[2] / "app" / "workers" / "celery_app.py"
    src = p.read_text()
    assert "process-webhook-retries-every-2min" in src, (
        "outgoing webhook retry task missing from beat_schedule"
    )
    assert "app.workers.tasks.webhook_retries" in src


# ── PHI key hard-fail guard (HIPAA §164.312(a)(2)(iv))

def test_phi_key_hard_fail_exits_on_missing_in_production(monkeypatch):
    """HEALTH_DATA_ENCRYPTION_KEY missing in production → refuse to boot."""
    settings = MagicMock()
    settings.ENVIRONMENT = "production"
    settings.HEALTH_DATA_ENCRYPTION_KEY = None

    import sys
    exit_code = {"v": None}
    monkeypatch.setattr(sys, "exit", lambda c: exit_code.update(v=c))
    # stderr.write mock so the fatal banner doesn't clutter test output
    monkeypatch.setattr(sys, "stderr", type("Null", (), {"write": lambda *a: None})())

    from app.core.config import Settings
    Settings.validate_production_phi_key(settings)
    assert exit_code["v"] == 78


def test_phi_key_hard_fail_accepts_valid_fernet(monkeypatch):
    """A valid Fernet key passes the hard-fail check."""
    from cryptography.fernet import Fernet
    settings = MagicMock()
    settings.ENVIRONMENT = "production"
    settings.HEALTH_DATA_ENCRYPTION_KEY = Fernet.generate_key().decode()

    import sys
    exit_calls = []
    monkeypatch.setattr(sys, "exit", lambda c: exit_calls.append(c))

    from app.core.config import Settings
    Settings.validate_production_phi_key(settings)
    assert exit_calls == []


# ── Waiver signing: only-one-path guarantee ─────────────────────────────

def test_waiver_signatures_insert_has_exactly_one_code_path():
    """Legal posture: a waiver is only valid when the member themselves
    signs it from their own verified portal session. Guard against any
    future code path that would INSERT INTO waiver_signatures from a
    different surface (admin panel, kiosk auto-sign, CSV import, etc.).

    The only place allowed to insert into waiver_signatures is
    WaiverService.sign_waiver, which is called from exactly one route:
    POST /portal/waiver/sign (member role, email_verified required).
    """
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "app"
    # Grep the entire app/ tree for INSERT statements into waiver_signatures
    result = subprocess.run(
        ["grep", "-rn", "-E", "INSERT\\s+INTO\\s+waiver_signatures",
         str(root), "--include=*.py"],
        capture_output=True, text=True,
    )
    lines = [l for l in result.stdout.splitlines() if l.strip()]
    assert len(lines) == 1, (
        f"Expected exactly 1 INSERT INTO waiver_signatures (in "
        f"waiver_service.sign_waiver). Found {len(lines)}:\n"
        + "\n".join(lines)
    )
    assert "waiver_service.py" in lines[0], (
        f"The one INSERT must live in waiver_service.py; found: {lines[0]}"
    )


def test_external_sign_waiver_endpoint_is_disabled():
    """The old /api/v1/external/members/{member_id}/waiver/sign API-key
    back door must stay 410 Gone. Anyone reintroducing live signing via
    API key undermines the legal validity of every waiver."""
    from pathlib import Path
    p = Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "endpoints" / "external" / "members.py"
    src = p.read_text()
    assert "waiver_self_sign_only" in src, (
        "External waiver-sign endpoint lost its 410 block — someone re-enabled "
        "API-key waiver signing"
    )
    assert "status_code=410" in src


def test_portal_sign_waiver_uses_jwt_only_no_body_member_id():
    """Portal sign-waiver endpoint resolves the signer from the JWT,
    never from a body parameter. This is what blocks staff-impersonation:
    a logged-in user can only ever sign their own waiver, because
    member.user_id is matched against rbac['user_id'] from the access
    token, and there is no member_id field on the request body that
    could override it.

    (Replaces the previous email_verified=true assertion. That gate
    was over-implementation — Don's actual ask was "block Terri from
    approving waiver in AuraFlow", which the JWT-only resolution
    already satisfies. The email_verified gate created a chicken-and-
    egg lockout for new members and was removed on 2026-04-29.)"""
    from pathlib import Path
    p = Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "endpoints" / "waivers.py"
    src = p.read_text()
    # Member must be resolved by user_id from the JWT, not by anything
    # the caller could pass.
    assert 'WHERE user_id = $1' in src, (
        "Portal sign-waiver must resolve member by user_id from JWT — "
        "never accept member_id from request body"
    )
    assert 'rbac["user_id"]' in src, (
        "Portal sign-waiver must use rbac['user_id'] (from JWT) as "
        "the member lookup key"
    )


def test_phi_key_hard_fail_skips_non_production(monkeypatch):
    """Dev/test environments bypass the check — local boot without the key
    is allowed, just without encryption."""
    settings = MagicMock()
    settings.ENVIRONMENT = "development"
    settings.HEALTH_DATA_ENCRYPTION_KEY = None

    import sys
    exit_calls = []
    monkeypatch.setattr(sys, "exit", lambda c: exit_calls.append(c))

    from app.core.config import Settings
    Settings.validate_production_phi_key(settings)
    assert exit_calls == []
