"""API key crypto — memory-hard KDF (Argon2id preferred, scrypt fallback) + HMAC index.

Indexed field ``api_key_hash``: HMAC-SHA256(pepper, key) for O(1) lookup.
Optional ``api_key_argon`` / metadata: Argon2id PHC or scrypt$ record.

Progressive upgrade on successful legacy authenticate.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets

logger = logging.getLogger("lumen.api_key_crypto")


def _pepper() -> bytes:
    try:
        from lumen.platform.tenants import _key_pepper

        return _key_pepper()
    except Exception:
        raw = (os.getenv("API_KEY_PEPPER") or os.getenv("TBE_TOKEN_SECRET") or "").strip()
        if not raw:
            raise RuntimeError("API_KEY_PEPPER required for api key crypto")
        return raw.encode("utf-8")


def lookup_hmac(raw_key: str) -> str:
    return hmac.new(_pepper(), raw_key.encode("utf-8"), hashlib.sha256).hexdigest()


def legacy_sha256(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def hash_api_key(raw_key: str) -> str:
    """Value stored in api_key_hash index column."""
    key = (raw_key or "").strip()
    if not key:
        raise ValueError("empty_api_key")
    return lookup_hmac(key)


def _material(raw_key: str) -> str:
    return hmac.new(
        _pepper(), b"a2-material|" + raw_key.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def kdf_hash(raw_key: str) -> str:
    """Memory-hard verifier string (Argon2id if available, else scrypt)."""
    material = _material(raw_key)
    try:
        from argon2 import PasswordHasher

        ph = PasswordHasher(
            time_cost=int(os.getenv("API_KEY_ARGON2_TIME") or "2"),
            memory_cost=int(os.getenv("API_KEY_ARGON2_MEMORY") or "65536"),
            parallelism=int(os.getenv("API_KEY_ARGON2_PARALLELISM") or "2"),
            hash_len=32,
            salt_len=16,
        )
        return ph.hash(material)
    except ImportError:
        salt = secrets.token_bytes(16)
        dk = hashlib.scrypt(
            material.encode("utf-8"),
            salt=salt,
            n=int(os.getenv("API_KEY_SCRYPT_N") or str(2**14)),
            r=8,
            p=1,
            dklen=32,
        )
        return f"scrypt${salt.hex()}${dk.hex()}"


def kdf_verify(raw_key: str, stored: str) -> bool:
    stored = (stored or "").strip()
    if not stored:
        return False
    material = _material(raw_key)
    if stored.startswith("$argon2") or stored.startswith("argon2"):
        try:
            from argon2 import PasswordHasher
            from argon2.exceptions import VerifyMismatchError, InvalidHash

            try:
                return bool(PasswordHasher().verify(stored, material))
            except (VerifyMismatchError, InvalidHash, Exception):
                return False
        except ImportError:
            return False
    if stored.startswith("scrypt$"):
        try:
            _, salt_hex, dk_hex = stored.split("$", 2)
            salt = bytes.fromhex(salt_hex)
            expect = bytes.fromhex(dk_hex)
            got = hashlib.scrypt(
                material.encode("utf-8"),
                salt=salt,
                n=int(os.getenv("API_KEY_SCRYPT_N") or str(2**14)),
                r=8,
                p=1,
                dklen=32,
            )
            return hmac.compare_digest(got, expect)
        except Exception:
            return False
    return False


def verify_stored(
    raw_key: str,
    *,
    stored_hash: str,
    stored_kdf: str = "",
) -> tuple[bool, str | None]:
    """(ok, kdf_to_write_on_upgrade_or_None)."""
    key = (raw_key or "").strip()
    stored_hash = (stored_hash or "").strip()
    stored_kdf = (stored_kdf or "").strip()
    if not key or not stored_hash:
        return False, None

    lk = lookup_hmac(key)
    sha = legacy_sha256(key)
    if not (
        hmac.compare_digest(stored_hash, lk) or hmac.compare_digest(stored_hash, sha)
    ):
        return False, None

    if stored_kdf:
        if not kdf_verify(key, stored_kdf):
            return False, None
        return True, None

    try:
        return True, kdf_hash(key)
    except Exception:
        logger.exception("kdf_hash upgrade failed")
        return True, None


# Back-compat aliases
argon2_hash = kdf_hash
argon2_verify = kdf_verify

__all__ = [
    "hash_api_key",
    "lookup_hmac",
    "legacy_sha256",
    "kdf_hash",
    "kdf_verify",
    "verify_stored",
    "argon2_hash",
    "argon2_verify",
]
