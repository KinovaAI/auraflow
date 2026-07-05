"""AuraFlow — TOTP / MFA Service

Provides TOTP (Time-based One-Time Password) helpers for two-factor
authentication, plus backup-code generation and verification.
"""
import secrets
import string

import bcrypt
import pyotp

from app.core.config import settings


def generate_secret() -> str:
    """Generate a base32-encoded TOTP secret."""
    return pyotp.random_base32()


def generate_provisioning_uri(email: str, secret: str) -> str:
    """Return an otpauth:// URI suitable for QR code generation."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name=settings.PLATFORM_NAME)


def verify_totp(secret: str, code: str) -> bool:
    """Verify a TOTP code with 1-step window tolerance (30s each side)."""
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


def generate_backup_codes(count: int = 8) -> list[str]:
    """Generate a list of 8-char alphanumeric backup codes."""
    alphabet = string.ascii_uppercase + string.digits
    return [
        "".join(secrets.choice(alphabet) for _ in range(8))
        for _ in range(count)
    ]


def hash_backup_codes(codes: list[str]) -> list[str]:
    """Return bcrypt hashes of the given backup codes."""
    return [
        bcrypt.hashpw(code.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        for code in codes
    ]


def verify_backup_code(
    code: str, hashed_codes: list[str]
) -> tuple[bool, list[str]]:
    """Check *code* against *hashed_codes*.

    Returns ``(matched, remaining_hashed_codes)`` — the matched hash is
    removed from the list so each backup code can only be used once.
    """
    for i, h in enumerate(hashed_codes):
        try:
            if bcrypt.checkpw(code.encode("utf-8"), h.encode("utf-8")):
                remaining = hashed_codes[:i] + hashed_codes[i + 1 :]
                return True, remaining
        except (ValueError, TypeError):
            continue
    return False, hashed_codes
