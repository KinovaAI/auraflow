"""Managed billing broker — key handling + the server-side-fee invariant.

The load-bearing property: a broker `charge` NEVER lets the caller set the app_fee.
It omits app_fee_cents so square_service applies the 1% itself — a self-hosted
client can't zero it out.
"""
import os
os.environ.setdefault("DATABASE_URL", "postgresql://test/test")
os.environ.setdefault("APP_SECRET", "test-secret-not-for-production-use-only")

from unittest.mock import AsyncMock, patch

import pytest


def test_key_prefix_and_hash():
    from app.services.broker import broker_service as bs
    k = bs._gen_key()
    assert k.startswith("af_broker_")
    import hashlib
    assert bs._hash_key(k) == hashlib.sha256(k.encode()).hexdigest()
    assert bs._hash_key(k) == bs._hash_key(k)  # deterministic


@pytest.mark.asyncio
async def test_resolve_rejects_non_broker_key():
    from app.services.broker.broker_service import broker_service
    # Wrong prefix returns None before any DB lookup.
    assert await broker_service.resolve_by_key("af_live_whatever") is None
    assert await broker_service.resolve_by_key(None) is None


@pytest.mark.asyncio
async def test_charge_rejects_nonpositive_amount():
    from app.services.broker.broker_service import broker_service, BrokerError
    with pytest.raises(BrokerError) as ei:
        await broker_service.charge("cid", customer_id="c", card_id="k",
                                    amount_cents=0, description="x")
    assert ei.value.status == 422


@pytest.mark.asyncio
async def test_charge_never_passes_app_fee():
    """The 1% is intrinsic — charge must NOT forward app_fee_cents to Square."""
    from app.services.broker.broker_service import broker_service

    captured = {}

    async def _fake_payment(**kwargs):
        captured.update(kwargs)
        return {"payment_id": "sq_1", "status": "COMPLETED",
                "amount_cents": kwargs["amount_cents"], "app_fee_cents": 140}

    with patch.object(broker_service, "_merchant_creds",
                      new=AsyncMock(return_value=("sq_token", "LOC123"))):
        with patch("app.services.broker.broker_service.square_service.create_payment_with_app_fee",
                   new=_fake_payment):
            res = await broker_service.charge(
                "cid", customer_id="cust", card_id="card", amount_cents=14000,
                description="Membership")

    assert res["payment_id"] == "sq_1"
    assert "app_fee_cents" not in captured   # caller/broker never sets the fee
    assert captured["amount_cents"] == 14000
    assert captured["merchant_location_id"] == "LOC123"
