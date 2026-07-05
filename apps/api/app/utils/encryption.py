"""AuraFlow — Credential Encryption via pgcrypto

Encrypts/decrypts BYOA API keys at the database level using
pgp_sym_encrypt / pgp_sym_decrypt with APP_SECRET as the passphrase.
"""
from app.core.config import settings


async def encrypt_credential(db, plaintext: str) -> bytes:
    """Encrypt a credential string using pgcrypto."""
    row = await db.fetchrow(
        "SELECT pgp_sym_encrypt($1::text, $2::text) AS encrypted",
        plaintext, settings.APP_SECRET,
    )
    return row["encrypted"]


async def decrypt_credential(db, encrypted: bytes) -> str:
    """Decrypt a credential previously encrypted with encrypt_credential."""
    row = await db.fetchrow(
        "SELECT pgp_sym_decrypt($1::bytea, $2::text) AS decrypted",
        encrypted, settings.APP_SECRET,
    )
    return row["decrypted"]
