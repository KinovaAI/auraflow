"""Deterministic phone-number hashing for indexed search.

Why this exists
---------------
Member phone numbers are at-rest-encrypted as `phone_enc` (Fernet — AES-CBC
+ HMAC-SHA256). Fernet output is non-deterministic, so `WHERE phone_enc =
$1` cannot match. Once HIPAA Phase C drops plaintext `members.phone`, every
"find member by their phone number" lookup breaks — most critically the
TCPA STOP/START opt-out path in webhooks.py.

This module exposes a deterministic HMAC-SHA256 keyed by a separate secret
(`PHONE_HASH_PEPPER`) so we can index `phone_hash` and resolve a member
from an inbound Twilio webhook without ever decrypting every row.

Why HMAC, not plain SHA-256
---------------------------
The phone-number space is small (~10¹⁰ US numbers). Plain SHA-256 reverses
to a phone in seconds via a precomputed table. HMAC with a secret pepper
makes any precomputed table attacker-specific and useless without the
pepper, which lives in the SOPS vault (separate from the DB backups).

Worst case (pepper leaked AND DB leaked): an attacker with a known phone
list can check membership (oracle attack). Mitigation: keep pepper in
SOPS, never co-locate with DB backups; rotate by re-backfilling.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from functools import lru_cache

import phonenumbers

_PEPPER_ENV = "PHONE_HASH_PEPPER"


@lru_cache(maxsize=1)
def _pepper() -> bytes:
    raw = os.environ.get(_PEPPER_ENV, "").strip()
    if not raw:
        raise RuntimeError(
            f"{_PEPPER_ENV} is not set. Cannot compute phone hashes. "
            "Set in /etc/auraflow-secrets/env.sops.yaml + restart api."
        )
    return base64.b64decode(raw)


def normalize_phone(raw: str | None, default_region: str = "US") -> str | None:
    """Convert any phone-number variant to E.164 (`+15551234567`).
    Returns None for unparseable / empty input.

    Handles `(555) 123-4567`, `+1-555-123-4567`, `15551234567`,
    international, etc. via Google libphonenumber.
    """
    if not raw or not raw.strip():
        return None
    try:
        parsed = phonenumbers.parse(raw, default_region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def hash_phone(raw: str | None, default_region: str = "US") -> str | None:
    """Deterministic HMAC-SHA256(pepper, normalize_phone(raw)) → 64 hex chars.
    Returns None if input is empty or unparseable. Same input → same output."""
    norm = normalize_phone(raw, default_region)
    if norm is None:
        return None
    return hmac.new(_pepper(), norm.encode("utf-8"), hashlib.sha256).hexdigest()
