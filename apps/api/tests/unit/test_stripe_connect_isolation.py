"""AuraFlow — Stripe Connect cross-tenant isolation contract.

THE RULE these tests pin (load-bearing for white-label payment safety):
    The `stripe_account_id` parameter passed to any Stripe API call MUST
    be derived server-side from the authenticated request's tenant
    context. NEVER from request body, query, header, or path.

If a future refactor accidentally reintroduces a path where a client
can choose which connected account to charge, these tests fail.

What we explicitly test:
  1. The chokepoint helper (resolve_stripe_account_for_org) only takes
     org_id — no parameter that could be hijacked client-side.
  2. The connect_account module's sanity assert refuses to load if
     anyone adds a parameter to the helper signatures (defense in depth
     for the test above — the import would fail, the test framework
     would crash, the CI would go red).
  3. Two different orgs hash-resolve to two different account_ids.
  4. The cache returns the same value for repeated calls (and
     invalidate_cache properly drops the entry).
  5. resolve_connect_status reflects the org's stripe_charges_enabled
     and stripe_payouts_enabled flags.

These are mock-based — no real Stripe, no real Postgres. The integration
test that exercises a real Stripe Connect call against a test connected
account lives in tests/integration/test_stripe_connect_integration.py
(separate file, requires STRIPE_SECRET_KEY in env, gated by a marker).
"""
import os
os.environ.setdefault("DATABASE_URL", "postgresql://test/test")
os.environ.setdefault("APP_SECRET", "test-secret-not-for-production-use-only")

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── 1. Chokepoint signature lock ────────────────────────────────────────────

def test_resolve_stripe_account_only_takes_org_id():
    """If someone adds a parameter to this helper, the rule has been broken
    or a refactor needs explicit review. Pin the signature."""
    from app.services.payments.connect_account import resolve_stripe_account_for_org
    sig = inspect.signature(resolve_stripe_account_for_org)
    params = list(sig.parameters)
    assert params == ["org_id"], (
        f"connect_account.resolve_stripe_account_for_org signature drift: {params}. "
        "Adding parameters here is a security red flag — "
        "see app/services/payments/connect_account.py module docstring."
    )


def test_resolve_connect_status_only_takes_org_id():
    from app.services.payments.connect_account import resolve_connect_status
    sig = inspect.signature(resolve_connect_status)
    assert list(sig.parameters) == ["org_id"]


def test_module_sanity_assert_runs_at_import():
    """The connect_account module runs _module_sanity() at import time.
    If signatures drift, import would crash. The mere fact that we can
    import the module is the proof."""
    import app.services.payments.connect_account  # must import without raising
    assert app.services.payments.connect_account is not None


# ── 2. Cross-tenant account separation ──────────────────────────────────────

@pytest.mark.asyncio
async def test_different_orgs_resolve_to_different_accounts():
    """The whole point of the chokepoint: tenant-A's lookup returns
    tenant-A's stripe_account_id, never tenant-B's."""
    from app.services.payments import connect_account

    connect_account.invalidate_all()

    rows = {
        "org-a-id": {"stripe_account_id": "acct_test_AAA"},
        "org-b-id": {"stripe_account_id": "acct_test_BBB"},
    }

    async def fake_fetchrow(_query, key):
        return rows.get(key)

    fake_db = MagicMock()
    fake_db.fetchrow = AsyncMock(side_effect=fake_fetchrow)
    fake_cm = MagicMock()
    fake_cm.__aenter__ = AsyncMock(return_value=fake_db)
    fake_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.payments.connect_account.get_global_db", return_value=fake_cm):
        a = await connect_account.resolve_stripe_account_for_org("org-a-id")
        b = await connect_account.resolve_stripe_account_for_org("org-b-id")

    assert a == "acct_test_AAA"
    assert b == "acct_test_BBB"
    assert a != b


@pytest.mark.asyncio
async def test_unknown_org_returns_none():
    from app.services.payments import connect_account
    connect_account.invalidate_all()

    fake_db = MagicMock()
    fake_db.fetchrow = AsyncMock(return_value=None)
    fake_cm = MagicMock()
    fake_cm.__aenter__ = AsyncMock(return_value=fake_db)
    fake_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.payments.connect_account.get_global_db", return_value=fake_cm):
        result = await connect_account.resolve_stripe_account_for_org("ghost-org")

    assert result is None


# ── 3. Cache behavior ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cache_avoids_second_db_call():
    from app.services.payments import connect_account
    connect_account.invalidate_all()

    call_count = {"n": 0}

    async def counting_fetchrow(_q, _k):
        call_count["n"] += 1
        return {"stripe_account_id": "acct_test_CACHE"}

    fake_db = MagicMock()
    fake_db.fetchrow = AsyncMock(side_effect=counting_fetchrow)
    fake_cm = MagicMock()
    fake_cm.__aenter__ = AsyncMock(return_value=fake_db)
    fake_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.payments.connect_account.get_global_db", return_value=fake_cm):
        first = await connect_account.resolve_stripe_account_for_org("cache-org")
        second = await connect_account.resolve_stripe_account_for_org("cache-org")

    assert first == second == "acct_test_CACHE"
    assert call_count["n"] == 1, "Cache should have prevented the second DB call"


@pytest.mark.asyncio
async def test_invalidate_cache_forces_refetch():
    from app.services.payments import connect_account
    connect_account.invalidate_all()

    responses = iter([
        {"stripe_account_id": "acct_test_FIRST"},
        {"stripe_account_id": "acct_test_SECOND"},
    ])

    async def two_responses(_q, _k):
        return next(responses)

    fake_db = MagicMock()
    fake_db.fetchrow = AsyncMock(side_effect=two_responses)
    fake_cm = MagicMock()
    fake_cm.__aenter__ = AsyncMock(return_value=fake_db)
    fake_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.payments.connect_account.get_global_db", return_value=fake_cm):
        first = await connect_account.resolve_stripe_account_for_org("invalidate-org")
        connect_account.invalidate_cache("invalidate-org")
        second = await connect_account.resolve_stripe_account_for_org("invalidate-org")

    assert first == "acct_test_FIRST"
    assert second == "acct_test_SECOND"


# ── 4. Connect status reflects org flags ────────────────────────────────────

@pytest.mark.asyncio
async def test_connect_status_ready_for_charges():
    from app.services.payments import connect_account
    connect_account.invalidate_all()

    fake_db = MagicMock()
    fake_db.fetchrow = AsyncMock(return_value={
        "stripe_account_id": "acct_test_ENABLED",
        "stripe_charges_enabled": True,
        "stripe_payouts_enabled": True,
    })
    fake_cm = MagicMock()
    fake_cm.__aenter__ = AsyncMock(return_value=fake_db)
    fake_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.payments.connect_account.get_global_db", return_value=fake_cm):
        status = await connect_account.resolve_connect_status("ready-org")

    assert status["ready_for_charges"] is True
    assert status["charges_enabled"] is True
    assert status["payouts_enabled"] is True
    assert status["stripe_account_id"] == "acct_test_ENABLED"


@pytest.mark.asyncio
async def test_connect_status_not_ready_when_charges_disabled():
    from app.services.payments import connect_account
    connect_account.invalidate_all()

    fake_db = MagicMock()
    fake_db.fetchrow = AsyncMock(return_value={
        "stripe_account_id": "acct_test_BLOCKED",
        "stripe_charges_enabled": False,  # Stripe blocked us
        "stripe_payouts_enabled": True,
    })
    fake_cm = MagicMock()
    fake_cm.__aenter__ = AsyncMock(return_value=fake_db)
    fake_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.payments.connect_account.get_global_db", return_value=fake_cm):
        status = await connect_account.resolve_connect_status("blocked-org")

    assert status["ready_for_charges"] is False
    assert status["charges_enabled"] is False


@pytest.mark.asyncio
async def test_connect_status_not_ready_when_no_account():
    from app.services.payments import connect_account
    connect_account.invalidate_all()

    fake_db = MagicMock()
    fake_db.fetchrow = AsyncMock(return_value={
        "stripe_account_id": None,
        "stripe_charges_enabled": False,
        "stripe_payouts_enabled": False,
    })
    fake_cm = MagicMock()
    fake_cm.__aenter__ = AsyncMock(return_value=fake_db)
    fake_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.payments.connect_account.get_global_db", return_value=fake_cm):
        status = await connect_account.resolve_connect_status("no-account-org")

    assert status["ready_for_charges"] is False
    assert status["stripe_account_id"] is None
