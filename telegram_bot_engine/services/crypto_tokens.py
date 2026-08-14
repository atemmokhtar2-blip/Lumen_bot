"""At-rest token/secret sealing for hosted bots.

Uses Fernet (AES-128-CBC + HMAC) from the ``cryptography`` package when available.
Legacy ``enc1:`` XOR seals remain readable for migration only — new writes use ``enc2:``.

Environment:
  TBE_TOKEN_SECRET   preferred key material (required in production)
  PLATFORM_ADMIN_TOKEN / SECRET_KEY / TELEGRAM_BOT_TOKEN  fallbacks (dev only)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os

logger = logging.getLogger("tbe.crypto_tokens")

_ENC2 = "enc2:"
_ENC1 = "enc1:"


def _raw_secret_material() -> bytes:
    raw = (
        (os.getenv("TBE_TOKEN_SECRET") or "").strip()
        or (os.getenv("PLATFORM_ADMIN_TOKEN") or "").strip()
        or (os.getenv("SECRET_KEY") or "").strip()
        or (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    )
    env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "").strip().lower()
    if not raw:
        if env in {"production", "prod", "staging"}:
            raise RuntimeError(
                "TBE_TOKEN_SECRET is required in production for sealing bot tokens at rest"
            )
        raw = "tbe-dev-insecure-token-key"
        logger.warning("using insecure default TBE token seal key (dev only)")
    return raw.encode("utf-8")


def _fernet_key() -> bytes:
    """Derive a url-safe 32-byte Fernet key from platform secret material."""
    digest = hashlib.sha256(_raw_secret_material()).digest()
    return base64.urlsafe_b64encode(digest)


def _fernet():
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:
        raise RuntimeError(
            "cryptography package required for secure token sealing — pip install cryptography"
        ) from exc
    return Fernet(_fernet_key())


def seal_token(token: str) -> str:
    """Seal a bot token for at-rest storage (enc2: Fernet)."""
    token = (token or "").strip()
    if not token:
        return ""
    try:
        f = _fernet()
        sealed = f.encrypt(token.encode("utf-8")).decode("ascii")
        return _ENC2 + sealed
    except RuntimeError:
        # cryptography missing — fail closed in production, legacy path in dev
        env = (os.getenv("ENVIRONMENT") or "").strip().lower()
        if env in {"production", "prod", "staging"}:
            raise
        return _legacy_xor_seal(token)


def unseal_token(blob: str) -> str:
    """Unseal enc2 (Fernet) or legacy enc1 (XOR+HMAC). Plaintext returned as-is."""
    blob = (blob or "").strip()
    if not blob:
        return ""
    if blob.startswith(_ENC2):
        try:
            f = _fernet()
            return f.decrypt(blob[len(_ENC2) :].encode("ascii")).decode("utf-8")
        except Exception as e:
            logger.warning("enc2 unseal failed: %s", type(e).__name__)
            return ""
    if blob.startswith(_ENC1):
        return _legacy_xor_unseal(blob)
    # Untagged plaintext (legacy files)
    return blob


def _legacy_xor_seal(token: str) -> str:
    key = hashlib.sha256(_raw_secret_material()).digest()
    data = token.encode("utf-8")
    out = bytearray()
    for i, b in enumerate(data):
        block = hashlib.sha256(key + i.to_bytes(4, "big")).digest()
        out.append(b ^ block[i % 32])
    tag = hmac.new(key, bytes(out), hashlib.sha256).digest()[:16]
    return _ENC1 + base64.urlsafe_b64encode(tag + bytes(out)).decode("ascii")


def _legacy_xor_unseal(blob: str) -> str:
    try:
        key = hashlib.sha256(_raw_secret_material()).digest()
        raw = base64.urlsafe_b64decode(blob[len(_ENC1) :].encode("ascii"))
        tag, data = raw[:16], raw[16:]
        expect = hmac.new(key, data, hashlib.sha256).digest()[:16]
        if not hmac.compare_digest(tag, expect):
            return ""
        out = bytearray()
        for i, b in enumerate(data):
            block = hashlib.sha256(key + i.to_bytes(4, "big")).digest()
            out.append(b ^ block[i % 32])
        return out.decode("utf-8")
    except Exception:
        return ""
