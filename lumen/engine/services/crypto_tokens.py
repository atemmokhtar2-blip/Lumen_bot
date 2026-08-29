"""At-rest token/secret sealing for hosted bots (2026).

Wire formats (newest first):
  enc3:  AES-256-GCM with AAD  (preferred)
  enc2:  Fernet                (legacy readable)
  enc1:  XOR+HMAC              (legacy readable, never written)

Environment:
  TBE_TOKEN_SECRET   required in production (min 16 chars)
  Never derive from TELEGRAM_BOT_TOKEN (platform token).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets

logger = logging.getLogger("tbe.crypto_tokens")

_ENC3 = "enc3:"
_ENC2 = "enc2:"
_ENC1 = "enc1:"


def _raw_secret_material() -> bytes:
    raw = (
        (os.getenv("TBE_TOKEN_SECRET") or "").strip()
        or (os.getenv("PLATFORM_ADMIN_TOKEN") or "").strip()
        or (os.getenv("SECRET_KEY") or "").strip()
    )
    env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "").strip().lower()
    if not raw:
        if env in {"production", "prod", "staging"}:
            raise RuntimeError(
                "TBE_TOKEN_SECRET is required in production for sealing bot tokens at rest"
            )
        raw = "tbe-dev-insecure-token-key"
        logger.warning("using insecure default TBE token seal key (dev only)")
    if len(raw) < 16 and env in {"production", "prod", "staging"}:
        raise RuntimeError("TBE_TOKEN_SECRET too short (min 16 chars in production)")
    return raw.encode("utf-8")


def _aes_key() -> bytes:
    return hashlib.sha256(b"tbe-aesgcm-v1|" + _raw_secret_material()).digest()


def _fernet_key() -> bytes:
    digest = hashlib.sha256(_raw_secret_material()).digest()
    return base64.urlsafe_b64encode(digest)


def _fernet():
    from cryptography.fernet import Fernet
    return Fernet(_fernet_key())


def seal_token(token: str, *, aad: bytes = b"bot_token") -> str:
    """Seal a bot token for at-rest storage (enc3: AES-256-GCM)."""
    token = (token or "").strip()
    if not token:
        return ""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = secrets.token_bytes(12)
        ct = AESGCM(_aes_key()).encrypt(nonce, token.encode("utf-8"), aad)
        blob = base64.urlsafe_b64encode(nonce + ct).decode("ascii").rstrip("=")
        return _ENC3 + blob
    except Exception as exc:
        env = (os.getenv("ENVIRONMENT") or "").strip().lower()
        if env in {"production", "prod", "staging"}:
            raise RuntimeError(f"token_seal_failed:{type(exc).__name__}") from exc
        logger.warning("AES-GCM seal failed (%s); Fernet fallback (dev)", type(exc).__name__)
        try:
            sealed = _fernet().encrypt(token.encode("utf-8")).decode("ascii")
            return _ENC2 + sealed
        except Exception:
            return _legacy_xor_seal(token)


def unseal_token(blob: str, *, aad: bytes = b"bot_token") -> str:
    """Unseal enc3/enc2/enc1. Never return untagged plaintext as secret."""
    blob = (blob or "").strip()
    if not blob:
        return ""
    if blob.startswith(_ENC3):
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            raw = blob[len(_ENC3):]
            pad = "=" * (-len(raw) % 4)
            data = base64.urlsafe_b64decode(raw + pad)
            if len(data) < 12 + 16:
                return ""
            nonce, ct = data[:12], data[12:]
            return AESGCM(_aes_key()).decrypt(nonce, ct, aad).decode("utf-8")
        except Exception as e:
            logger.warning("enc3 unseal failed: %s", type(e).__name__)
            return ""
    if blob.startswith(_ENC2):
        try:
            return _fernet().decrypt(blob[len(_ENC2):].encode("ascii")).decode("utf-8")
        except Exception as e:
            logger.warning("enc2 unseal failed: %s", type(e).__name__)
            return ""
    if blob.startswith(_ENC1):
        return _legacy_xor_unseal(blob)
    # Untagged value is NOT accepted as a sealed secret (prevents plaintext persistence)
    logger.warning("rejecting untagged token blob (len=%s)", len(blob))
    return ""


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
        raw = base64.urlsafe_b64decode(blob[len(_ENC1):].encode("ascii"))
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
