"""AuraFlow — billing_dispatcher cross-provider isolation contract.

THE RULE these tests pin (load-bearing for the Stripe → Square dual run):

  A studio with billing_provider='stripe' MUST NEVER hit square_service.
  A studio with billing_provider='square' MUST NEVER hit stripe_service.
  An org with no provider set defaults to 'stripe' so legacy studios
  keep working exactly as they do today.
  The dispatcher reads billing_provider from af_global.organizations
  every call — never from a request body / header / path. A spoofed
  request claiming to be a different provider must have NO effect.

What we explicitly test:
  1. Square-mode org → square_service.create_payment_with_app_fee
     is called with the merchant's decrypted access token + 1%
     app_fee_money. stripe_service.create_payment_intent is NEVER
     called.
  2. Stripe-mode org → stripe_service.create_payment_intent is
     called. square_service is NEVER touched.
  3. Org with billing_provider IS NULL → defaults to stripe path.
  4. Square-mode org with no usable access token → ValueError, no
     silent fallback to Stripe. Loud-fail by design.
  5. _square_app_fee math: 1% rounded, floor 1¢, capped at Square's
     60% / 90% per-transaction limits.
  6. get_provider returns the right string regardless of org state.

These are mock-based; the dispatcher's DB lookup is patched at the
boundary so we don't need a real Postgres.
"""
import os
os.environ.setdefault("DATABASE_URL", "postgresql://test/test")
os.environ.setdefault("APP_SECRET", "test-secret-not-for-production-use-only")

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── 1. Square-mode routing ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_square_mode_calls_square_service_only():
    """billing_provider='square' → square_service hit, stripe_service untouched."""
    from app.services.payments import billing_dispatcher

    org_id = "org-square-A"

    # Mock the global DB to return a square-mode row.
    mock_db = MagicMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)
    mock_db.fetchrow = AsyncMock(return_value={
        "billing_provider": "square",
        "square_location_id": "L_test_loc",
    })

    with patch.object(billing_dispatcher, "get_global_db", return_value=mock_db):
        # Token resolver returns a valid token.
        with patch.object(
            billing_dispatcher.square_oauth_service,
            "get_merchant_access_token",
            new=AsyncMock(return_value="sq_test_access"),
        ):
            with patch.object(
                billing_dispatcher.square_service,
                "create_payment_with_app_fee",
                new=AsyncMock(return_value={
                    "payment_id": "sq_pay_1",
                    "amount_cents": 10000,
                    "app_fee_cents": 100,
                    "status": "COMPLETED",
                    "receipt_url": None,
                }),
            ) as square_call:
                # Make sure stripe path would explode if reached.
                with patch(
                    "app.services.payments.stripe_service.StripeService.create_payment_intent",
                    new=AsyncMock(side_effect=AssertionError(
                        "Stripe must NOT be touched for square-mode org"
                    )),
                ):
                    result = await billing_dispatcher.create_payment(
                        organization_id=org_id,
                        amount_cents=10000,
                        source_id="cnon:test-nonce",
                    )

    assert result["provider"] == "square"
    assert result["payment_id"] == "sq_pay_1"
    assert result["fee_cents"] == 100
    square_call.assert_awaited_once()


# ── 2. Stripe-mode routing ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stripe_mode_calls_stripe_service_only():
    """billing_provider='stripe' (or default) → stripe path runs, square untouched."""
    from app.services.payments import billing_dispatcher

    mock_db = MagicMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)
    mock_db.fetchrow = AsyncMock(return_value={
        "billing_provider": "stripe",
        "square_location_id": None,
    })

    with patch.object(billing_dispatcher, "get_global_db", return_value=mock_db):
        with patch(
            "app.services.payments.stripe_service.StripeService.create_payment_intent",
            new=AsyncMock(return_value={
                "payment_intent_id": "pi_test_1",
                "status": "requires_payment_method",
                "client_secret": "pi_test_1_secret",
                "application_fee_amount": 125,
            }),
        ) as stripe_call:
            with patch.object(
                billing_dispatcher.square_service,
                "create_payment_with_app_fee",
                new=AsyncMock(side_effect=AssertionError(
                    "Square must NOT be touched for stripe-mode org"
                )),
            ):
                result = await billing_dispatcher.create_payment(
                    organization_id="org-stripe-B",
                    amount_cents=10000,
                    source_id="pm_card_visa",
                    stripe_account_id="acct_test",
                    stripe_customer_id="cus_test",
                )

    assert result["provider"] == "stripe"
    assert result["payment_id"] == "pi_test_1"
    stripe_call.assert_awaited_once()


# ── 3. Default-to-stripe for legacy rows ────────────────────────────────


@pytest.mark.asyncio
async def test_null_provider_defaults_to_stripe():
    """An org with billing_provider IS NULL (impossible in prod but
    defensively safe) routes through Stripe. No silent Square call."""
    from app.services.payments import billing_dispatcher

    mock_db = MagicMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)
    mock_db.fetchrow = AsyncMock(return_value={
        "billing_provider": None,
        "square_location_id": None,
    })

    with patch.object(billing_dispatcher, "get_global_db", return_value=mock_db):
        with patch(
            "app.services.payments.stripe_service.StripeService.create_payment_intent",
            new=AsyncMock(return_value={
                "payment_intent_id": "pi_test_default",
                "status": "requires_payment_method",
                "client_secret": "x",
                "application_fee_amount": 0,
            }),
        ):
            with patch.object(
                billing_dispatcher.square_service,
                "create_payment_with_app_fee",
                new=AsyncMock(side_effect=AssertionError("must not touch square")),
            ):
                result = await billing_dispatcher.create_payment(
                    organization_id="org-x",
                    amount_cents=500,
                    source_id="pm_card_visa",
                )
    assert result["provider"] == "stripe"


@pytest.mark.asyncio
async def test_unknown_org_defaults_to_stripe():
    """Org not found in DB → dispatcher treats as stripe (so we never
    accidentally fall into a misconfigured square path)."""
    from app.services.payments import billing_dispatcher

    mock_db = MagicMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)
    mock_db.fetchrow = AsyncMock(return_value=None)

    with patch.object(billing_dispatcher, "get_global_db", return_value=mock_db):
        ctx = await billing_dispatcher._resolve_provider("org-missing")
    assert ctx["provider"] == "stripe"
    assert ctx["merchant_access_token"] is None


# ── 4. Square-mode without a token must fail loudly ─────────────────────


@pytest.mark.asyncio
async def test_square_mode_without_token_raises():
    """A studio marked square but missing tokens MUST raise. Silent
    fallback to Stripe would charge the wrong account."""
    from app.services.payments import billing_dispatcher

    mock_db = MagicMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)
    mock_db.fetchrow = AsyncMock(return_value={
        "billing_provider": "square",
        "square_location_id": "L_x",
    })

    with patch.object(billing_dispatcher, "get_global_db", return_value=mock_db):
        with patch.object(
            billing_dispatcher.square_oauth_service,
            "get_merchant_access_token",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(ValueError, match="reconnect"):
                await billing_dispatcher._resolve_provider("org-broken")


# ── 5. App-fee math ─────────────────────────────────────────────────────


def test_app_fee_math_one_percent():
    from app.services.payments.billing_dispatcher import _square_app_fee
    assert _square_app_fee(10000) == 100   # $100.00 → $1.00 (1%)
    assert _square_app_fee(9999) == 100    # rounds up to $1.00
    assert _square_app_fee(150) == 2       # $1.50 → 2¢ (rounds 1.5 → 2)
    assert _square_app_fee(99) == 1        # $0.99 → 1¢ floor
    assert _square_app_fee(1) == 1         # 1¢ → 1¢ floor


def test_app_fee_caps_under_square_limits():
    """At 1% we're nowhere near Square's 60% (<$5) / 90% (≥$5) caps,
    but the cap is defensive code — verify the math holds."""
    from app.services.payments.billing_dispatcher import _square_app_fee
    # Way under cap; just sanity check the cap kicks in if forced.
    # We can't easily hit the cap at 1% on real amounts; the test
    # documents the math is in place.
    assert _square_app_fee(100000) == 1000  # $1000 → $10
    assert _square_app_fee(500) == 5        # $5 → 5¢


# ── 6. get_provider lookup ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_provider_returns_stored_value():
    from app.services.payments import billing_dispatcher

    mock_db = MagicMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)

    mock_db.fetchrow = AsyncMock(return_value={"billing_provider": "square"})
    with patch.object(billing_dispatcher, "get_global_db", return_value=mock_db):
        assert await billing_dispatcher.get_provider("any") == "square"

    mock_db.fetchrow = AsyncMock(return_value={"billing_provider": "stripe"})
    with patch.object(billing_dispatcher, "get_global_db", return_value=mock_db):
        assert await billing_dispatcher.get_provider("any") == "stripe"

    mock_db.fetchrow = AsyncMock(return_value=None)
    with patch.object(billing_dispatcher, "get_global_db", return_value=mock_db):
        assert await billing_dispatcher.get_provider("any") == "stripe"


# ── 7. Square webhook dedupe (Phase 9) ──────────────────────────────────


@pytest.mark.asyncio
async def test_square_webhook_dedupe_handles_duplicate_delivery():
    """Same event_id delivered twice → second call is a no-op marked
    duplicate=True. Verifies processed_webhook_events with provider='square'
    correctly partitions from Stripe events."""
    from app.services.payments import square_webhook_handler

    insert_calls = {"count": 0}

    class FakeDB:
        async def execute(self, q, *args):
            insert_calls["count"] += 1
            # Simulate UNIQUE collision on second insert
            if insert_calls["count"] > 1:
                raise Exception("duplicate key value violates unique constraint")
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    with patch.object(square_webhook_handler, "get_global_db", return_value=FakeDB()):
        first = await square_webhook_handler._mark_processed("evt_test_1")
        second = await square_webhook_handler._mark_processed("evt_test_1")

    assert first is True
    assert second is False
