"""AuraFlow — Square POS Service  # noqa: D400

Wraps Square's Terminal API (server-to-server) + Devices API (pairing
codes) + post-checkout Cards API save. Used by:
  - The POS dispatcher path in billing_dispatcher.create_pos_charge
  - The webhook handler that completes a terminal.checkout.updated event
  - The /pos/square/devices/* endpoints for studio device pairing

Key invariants (HARD rules from Don, do NOT relax):
  - ALWAYS save card on file. There is no toggle. The webhook handler
    runs `save_card_from_payment` after a successful checkout — no
    customer prompt at the hardware, no staff override. See
    feedback_always_save_card.
  - Staff NEVER apply discounts. The amount passed in is fixed at the
    membership_type / drop_in_price source. The endpoint validates the
    amount against the source row's price before reaching this service.
    See feedback_no_staff_discounts.
  - 1% Square app_fee applies to every POS charge — same math as
    billing_dispatcher._square_app_fee.

Pattern: every method takes a `merchant_access_token` for the studio's
OAuth-connected Square account. Tokens come from
square_oauth_service.get_merchant_access_token (cached) — this service
never reaches into the DB itself.
"""
import base64
import hashlib
import hmac
from typing import Optional

from app.core.config import settings
from app.core.logging import logger
from app.services.payments.square_service import _client, _idem, _raise_on_errors


# ── Signed-state helpers (CRITICAL: prevent /pos/deeplink-return hijack) ──
#
# Square POS callbacks are public — Square can't authenticate to us, so the
# /pos/deeplink-return endpoint must accept anonymous traffic. To stop an
# attacker from forging a callback for a known checkout_id, we sign the
# checkout_id with APP_SECRET via HMAC-SHA256 and append the truncated digest
# to the state field Square preserves and returns. Verification rejects any
# state without a matching signature.

def _sign_checkout_state(checkout_id: str) -> str:
    """Return '<checkout_id>.<base64url_hmac_truncated>' for use as the
    Square POS API `state` value. The signature is HMAC-SHA256 of the
    checkout_id keyed by APP_SECRET, truncated to 16 bytes (128 bits) —
    plenty of forgery resistance, keeps the URL compact."""
    if not settings.APP_SECRET:
        raise RuntimeError("APP_SECRET not configured — cannot sign deeplink state")
    key = settings.APP_SECRET.encode("utf-8")
    raw = hmac.new(key, checkout_id.encode("utf-8"), hashlib.sha256).digest()[:16]
    sig = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    return f"{checkout_id}.{sig}"


def verify_checkout_state(state: str) -> Optional[str]:
    """Verify a signed state from Square POS. Returns checkout_id on
    success, None on tamper / missing / unparseable. Constant-time compare."""
    if not state or "." not in state or not settings.APP_SECRET:
        return None
    try:
        checkout_id, sig = state.rsplit(".", 1)
    except ValueError:
        return None
    key = settings.APP_SECRET.encode("utf-8")
    expected_raw = hmac.new(key, checkout_id.encode("utf-8"), hashlib.sha256).digest()[:16]
    expected = base64.urlsafe_b64encode(expected_raw).rstrip(b"=").decode("ascii")
    if hmac.compare_digest(expected, sig):
        return checkout_id
    return None


class SquarePOSService:
    """Stateless Terminal API + Devices API + Cards API wrapper."""

    # ── Device pairing ─────────────────────────────────────────────────

    async def create_device_code(
        self,
        merchant_access_token: str,
        name: str,
        merchant_location_id: Optional[str] = None,
    ) -> dict:
        """Generate a one-time pairing code (e.g. "ABC123") that the
        studio enters on a Square POS phone app or Terminal device.
        The code expires after 5 minutes per Square's hard limit.
        Returns {"code": str, "pair_by": ISO8601, "device_code_id": str,
        "status": "UNPAIRED"}."""
        client = _client(merchant_access_token)
        body: dict = {
            "name": name[:100],
            "product_type": "TERMINAL_API",
        }
        if merchant_location_id:
            body["location_id"] = merchant_location_id
        resp = await client.devices.codes.create(
            idempotency_key=_idem(),
            device_code=body,
        )
        _raise_on_errors(getattr(resp, "errors", None))
        dc = resp.device_code
        return {
            "device_code_id": dc.id,
            "code": dc.code,
            "name": dc.name,
            "pair_by": getattr(dc, "pair_by", None),
            "status": dc.status,
            "device_id": getattr(dc, "device_id", None),
        }

    async def get_device_code(
        self,
        merchant_access_token: str,
        device_code_id: str,
    ) -> dict:
        """Poll a device code until status becomes PAIRED (and device_id
        is populated)."""
        client = _client(merchant_access_token)
        resp = await client.devices.codes.get(id=device_code_id)
        _raise_on_errors(getattr(resp, "errors", None))
        dc = resp.device_code
        return {
            "device_code_id": dc.id,
            "code": dc.code,
            "status": dc.status,
            "device_id": getattr(dc, "device_id", None),
            "name": dc.name,
        }

    async def list_devices(self, merchant_access_token: str) -> list[dict]:
        """List all devices the merchant has paired (active + inactive).
        Returns rows with id, attributes (type, manufacturer, model),
        components (last_seen status), status."""
        client = _client(merchant_access_token)
        pager = await client.devices.list()
        out: list[dict] = []
        async for d in pager:
            out.append({
                "device_id": d.id,
                "type": getattr(getattr(d, "attributes", None), "type", None),
                "name": getattr(getattr(d, "attributes", None), "merchant_token", None)
                        or getattr(getattr(d, "attributes", None), "model", None)
                        or "Square device",
                "status": getattr(d, "status", None),
            })
        return out

    # ── Terminal checkout ──────────────────────────────────────────────

    async def create_terminal_checkout(
        self,
        merchant_access_token: str,
        device_id: str,
        amount_cents: int,
        reference_id: str,
        customer_id: Optional[str] = None,
        note: Optional[str] = None,
        app_fee_cents: Optional[int] = None,
        tip_settings: Optional[dict] = None,
        skip_receipt_screen: bool = False,
    ) -> dict:
        """Create a checkout against a paired Terminal device. The
        device beeps and the customer interacts; the webhook
        terminal.checkout.updated fires when the checkout transitions
        to a terminal state (COMPLETED / CANCELED / FAILED).

        NOTE: We do NOT set payment_options.save_card here — saving
        happens post-completion via save_card_from_payment() (no
        hardware prompt). Customer consent is captured implicitly via
        the studio's enrollment terms.
        """
        client = _client(merchant_access_token)
        device_options: dict = {"device_id": device_id}
        if skip_receipt_screen:
            device_options["skip_receipt_screen"] = True
        if tip_settings:
            device_options["tip_settings"] = tip_settings

        checkout_body: dict = {
            "amount_money": {"amount": amount_cents, "currency": "USD"},
            "device_options": device_options,
            "reference_id": reference_id[:40],
        }
        if customer_id:
            checkout_body["customer_id"] = customer_id
        if note:
            checkout_body["note"] = note[:500]
        if app_fee_cents:
            checkout_body["app_fee_money"] = {
                "amount": app_fee_cents, "currency": "USD",
            }

        # Deterministic idempotency key from reference_id so a retry of
        # the SAME logical operation gets deduped by Square (rather
        # than treated as a fresh checkout). 36-char Square limit.
        idem_key = f"af-pos-{reference_id}"[:64]
        resp = await client.terminal.checkouts.create(
            idempotency_key=idem_key,
            checkout=checkout_body,
        )
        _raise_on_errors(getattr(resp, "errors", None))
        ck = resp.checkout
        return {
            "checkout_id": ck.id,
            "status": ck.status,
            "amount_cents": ck.amount_money.amount,
            "device_id": device_id,
            "reference_id": getattr(ck, "reference_id", None),
        }

    async def get_terminal_checkout(
        self,
        merchant_access_token: str,
        checkout_id: str,
    ) -> dict:
        client = _client(merchant_access_token)
        resp = await client.terminal.checkouts.get(checkout_id=checkout_id)
        _raise_on_errors(getattr(resp, "errors", None))
        ck = resp.checkout
        return {
            "checkout_id": ck.id,
            "status": ck.status,
            "amount_cents": ck.amount_money.amount if ck.amount_money else None,
            "payment_ids": list(getattr(ck, "payment_ids", None) or []),
            "cancel_reason": getattr(ck, "cancel_reason", None),
            "reference_id": getattr(ck, "reference_id", None),
            "device_id": getattr(getattr(ck, "device_options", None), "device_id", None),
        }

    async def cancel_terminal_checkout(
        self,
        merchant_access_token: str,
        checkout_id: str,
    ) -> dict:
        """Best-effort cancel. If the checkout already completed or was
        already cancelled, Square returns the current state — we don't
        raise on that (idempotent semantics)."""
        client = _client(merchant_access_token)
        try:
            resp = await client.terminal.checkouts.cancel(checkout_id=checkout_id)
            _raise_on_errors(getattr(resp, "errors", None))
            ck = resp.checkout
            return {
                "checkout_id": ck.id,
                "status": ck.status,
                "cancelled": ck.status in ("CANCELED", "CANCEL_REQUESTED"),
            }
        except Exception as e:
            logger.warning(
                "Terminal checkout cancel raised — treating as best-effort",
                checkout_id=checkout_id, error=str(e),
            )
            return {"checkout_id": checkout_id, "status": "UNKNOWN", "cancelled": False}

    # ── Card-on-file save (no hardware prompt) ─────────────────────────

    async def save_card_from_payment(
        self,
        merchant_access_token: str,
        payment_id: str,
        customer_id: str,
        cardholder_name: Optional[str] = None,
    ) -> Optional[dict]:
        """Save the card used in `payment_id` to `customer_id` via the
        Cards API. Square accepts payment_id as the `source_id` —
        because the card was already authorized in that payment, no
        hardware prompt is required to save it.

        Returns the saved card details OR None if the payment didn't
        have a saveable card (e.g. gift card, foreign card with
        restrictions). Failure here doesn't fail the parent flow —
        the payment already completed and money already moved.
        """
        client = _client(merchant_access_token)
        body: dict = {
            "customer_id": customer_id,
        }
        if cardholder_name:
            body["cardholder_name"] = cardholder_name[:100]
        try:
            resp = await client.cards.create(
                idempotency_key=_idem(),
                source_id=payment_id,
                card=body,
            )
            _raise_on_errors(getattr(resp, "errors", None))
            card = resp.card
            return {
                "card_id": card.id,
                "card_brand": getattr(card, "card_brand", None),
                "last_4": getattr(card, "last_4", None),
                "exp_month": getattr(card, "exp_month", None),
                "exp_year": getattr(card, "exp_year", None),
            }
        except Exception as e:
            logger.warning(
                "save_card_from_payment failed (non-fatal)",
                payment_id=payment_id, customer_id=customer_id, error=str(e),
            )
            return None

    # ── Deep-link URL (POS app fallback) ───────────────────────────────

    @staticmethod
    def build_pos_deeplink(
        amount_cents: int,
        callback_url: str,
        client_id: str,
        currency_code: str = "USD",
        platform: str = "ios",
        version: str = "1.3",
        notes: Optional[str] = None,
        state: Optional[str] = None,
    ) -> str:
        """Build a URL that opens the Square POS app on a phone. iOS
        uses square-commerce-v1://; Android wraps in intent://. Square
        POS captures payment, then deep-links back to callback_url.

        Encoding rules learned the hard way:
          1. JSON must be COMPACT (no spaces) — Square POS doesn't
             decode `+` back to space when parsing the data param, so
             any spaces in the URL-encoded JSON arrive as literal `+`
             characters and corrupt the JSON. separators=(',', ':')
             strips all whitespace.
          2. Use quote() not urlencode() — urlencode uses quote_plus
             which encodes space as `+`. quote with safe="" uses %20
             for any remaining space, which Square POS handles.
        """
        import json
        import urllib.parse as _u
        data = {
            "amount_money": {"amount": amount_cents, "currency_code": currency_code},
            "callback_url": callback_url,
            "client_id": client_id,
            "version": version,
            "options": {
                "supported_tender_types": ["CREDIT_CARD"],
            },
        }
        if notes:
            data["notes"] = notes[:500]
        # `state` is preserved and returned by Square POS on the
        # callback. Used to carry our checkout_id since the callback
        # URL itself must EXACTLY match the one registered in the
        # Square Developer Console (no appended query strings allowed).
        if state:
            data["state"] = state[:1024]
        # Compact JSON + %20-style encoding
        json_str = json.dumps(data, separators=(",", ":"))
        qs = "data=" + _u.quote(json_str, safe="")
        if platform == "android":
            return (
                f"intent://payment/create?{qs}"
                f"#Intent;package=com.squareup;scheme=square-commerce-v1;end"
            )
        return f"square-commerce-v1://payment/create?{qs}"


square_pos_service = SquarePOSService()
