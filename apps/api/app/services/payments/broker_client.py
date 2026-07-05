"""AuraFlow managed-billing broker CLIENT (open-core / self-host side).

When a self-hosted instance sets AURAFLOW_BILLING_MODE=managed, billing operations
are routed here — thin HTTPS calls to the operator's AuraFlow billing broker
(`AURAFLOW_BROKER_URL`) authenticated with `AURAFLOW_BROKER_API_KEY`. The 1%
platform fee is applied by the broker server-side; this client never sees Square
credentials.

In the default `self` mode this module is never used.
"""
from typing import Optional

import httpx

from app.core.config import settings
from app.core.logging import logger


class BrokerClientError(Exception):
    pass


class BrokerClient:
    def _base(self) -> str:
        if not settings.AURAFLOW_BROKER_URL or not settings.AURAFLOW_BROKER_API_KEY:
            raise BrokerClientError("Managed billing selected but AURAFLOW_BROKER_URL / "
                                    "AURAFLOW_BROKER_API_KEY are not configured")
        return settings.AURAFLOW_BROKER_URL.rstrip("/") + "/api/v1/broker"

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {settings.AURAFLOW_BROKER_API_KEY}"}

    async def _get(self, path: str, params: Optional[dict] = None) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as http:
            resp = await http.get(f"{self._base()}{path}", params=params or {}, headers=self._headers())
        if resp.status_code >= 400:
            raise BrokerClientError(f"Broker request failed ({resp.status_code})")
        return resp.json().get("data", {})

    async def status(self) -> dict:
        """Connection status for this self-host's broker client."""
        return await self._get("/me")

    async def connect_url(self, return_url: str) -> str:
        """Square authorize URL to connect this client's merchant account."""
        data = await self._get("/connect", {"return_url": return_url})
        return data.get("authorize_url")

    async def _post(self, path: str, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as http:
            resp = await http.post(f"{self._base()}{path}", json=payload, headers=self._headers())
        if resp.status_code >= 400:
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            detail = (body.get("detail") or {}).get("error") if isinstance(body.get("detail"), dict) else body.get("detail")
            logger.error("Broker call failed", path=path, status=resp.status_code, detail=detail)
            raise BrokerClientError(detail or f"Broker request failed ({resp.status_code})")
        return resp.json().get("data", {})

    async def ensure_customer(self, *, email: str, first_name: Optional[str] = None,
                              last_name: Optional[str] = None, phone: Optional[str] = None,
                              member_ref: Optional[str] = None) -> dict:
        return await self._post("/customers", {
            "email": email, "first_name": first_name, "last_name": last_name,
            "phone": phone, "member_ref": member_ref})

    async def save_card(self, *, customer_id: str, source_id: str,
                        cardholder_name: Optional[str] = None) -> dict:
        return await self._post("/cards", {
            "customer_id": customer_id, "source_id": source_id,
            "cardholder_name": cardholder_name})

    async def charge(self, *, customer_id: str, card_id: str, amount_cents: int,
                     description: str = "AuraFlow charge", member_ref: Optional[str] = None,
                     idempotency_key: Optional[str] = None) -> dict:
        return await self._post("/charge", {
            "customer_id": customer_id, "card_id": card_id, "amount_cents": amount_cents,
            "description": description, "member_ref": member_ref,
            "idempotency_key": idempotency_key})

    async def refund(self, *, payment_id: str, amount_cents: int,
                     reason: Optional[str] = None, idempotency_key: Optional[str] = None) -> dict:
        return await self._post("/refund", {
            "payment_id": payment_id, "amount_cents": amount_cents,
            "reason": reason, "idempotency_key": idempotency_key})


broker_client = BrokerClient()
