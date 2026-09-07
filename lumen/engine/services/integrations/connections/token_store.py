"""Durable encrypted GitHub PAT store — Redis primary (multi-worker safe).

secret_inbox alone is a local file under OUTPUT_DIR; on Railway multi-replica
that does not share tokens across workers. Connection tokens must live in Redis
(same as session_store) with AES-GCM encryption at rest.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger("lumen.connections.token_store")

_KEY_PREFIX = "lumen:conn:gh:"
_REPO_CACHE_PREFIX = "lumen:conn:gh:repos:"
_DEFAULT_TTL = 30 * 24 * 3600  # 30 days


def _redis():
    try:
        from lumen.platform.runtime_config import redis_url as _ru

        url = (_ru() or "").strip()
    except Exception:
        url = (os.getenv("REDIS_URL") or os.getenv("JOB_REDIS_URL") or "").strip()
    if not url:
        return None
    try:
        import redis

        r = redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=float(os.getenv("REDIS_CONNECT_TIMEOUT") or "2"),
            socket_timeout=float(os.getenv("REDIS_SOCKET_TIMEOUT") or "3"),
        )
        r.ping()
        return r
    except Exception:
        logger.debug("connections token_store redis unavailable", exc_info=True)
        return None


def _aes_key() -> bytes:
    raw = (os.getenv("TBE_TOKEN_SECRET") or os.getenv("SECRET_INBOX_KEY") or "").strip()
    env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "production").strip().lower()
    if raw and len(raw) >= 16:
        return hashlib.sha256(raw.encode("utf-8")).digest()
    if env in {"dev", "development", "local", "test"}:
        tok = (os.getenv("TELEGRAM_BOT_TOKEN") or "dev").encode()
        return hashlib.sha256(b"lumen-conn-gh-v1" + tok).digest()
    raise RuntimeError("TBE_TOKEN_SECRET required for connection token store in production")


def _encrypt(plaintext: str, *, aad: bytes) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = _aes_key()
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), aad)
    return "gcm1." + base64.urlsafe_b64encode(nonce + ct).decode("ascii").rstrip("=")


def _decrypt(blob: str, *, aad: bytes) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not blob.startswith("gcm1."):
        raise ValueError("unsupported_cipher")
    raw = base64.urlsafe_b64decode(blob[5:] + "=" * (-len(blob[5:]) % 4))
    nonce, ct = raw[:12], raw[12:]
    pt = AESGCM(_aes_key()).decrypt(nonce, ct, aad)
    return pt.decode("utf-8")


def save_github_token(user_id: int, token: str, *, meta: dict[str, Any] | None = None) -> bool:
    uid = int(user_id or 0)
    tok = (token or "").strip()
    if uid <= 0 or not tok or len(tok) > 512:
        return False
    aad = f"gh|{uid}".encode("utf-8")
    try:
        cipher = _encrypt(tok, aad=aad)
    except Exception:
        logger.exception("encrypt github token failed uid=%s", uid)
        return False
    payload = json.dumps(
        {
            "ciphertext": cipher,
            "meta": dict(meta or {}),
            "saved_at": time.time(),
        },
        ensure_ascii=False,
    )
    r = _redis()
    if r is not None:
        try:
            r.set(f"{_KEY_PREFIX}{uid}", payload, ex=_DEFAULT_TTL)
        except Exception:
            logger.exception("redis save github token failed uid=%s", uid)
            r = None
    # Mirror to secret_inbox (best-effort, single-node / dev)
    try:
        from lumen.platform.secret_inbox import put_secret

        put_secret(
            user_id=uid,
            kind="github",
            plaintext=tok,
            purpose="connection",
            ttl_sec=_DEFAULT_TTL,
            meta={"provider": "github", **dict(meta or {})},
        )
    except Exception:
        logger.debug("secret_inbox mirror failed uid=%s", uid, exc_info=True)
    return True


def load_github_token(user_id: int) -> str | None:
    uid = int(user_id or 0)
    if uid <= 0:
        return None
    aad = f"gh|{uid}".encode("utf-8")
    r = _redis()
    if r is not None:
        try:
            raw = r.get(f"{_KEY_PREFIX}{uid}")
            if raw:
                data = json.loads(raw)
                return _decrypt(str(data.get("ciphertext") or ""), aad=aad)
        except Exception:
            logger.debug("redis load github token failed uid=%s", uid, exc_info=True)
    try:
        from lumen.platform.secret_inbox import get_secret

        return get_secret(user_id=uid, kind="github")
    except Exception:
        logger.debug("secret_inbox get_secret failed uid=%s", uid, exc_info=True)
        return None


def clear_github_token(user_id: int) -> None:
    uid = int(user_id or 0)
    if uid <= 0:
        return
    r = _redis()
    if r is not None:
        try:
            r.delete(f"{_KEY_PREFIX}{uid}", f"{_REPO_CACHE_PREFIX}{uid}")
        except Exception:
            pass


def cache_repo_page(user_id: int, page: int, resources: list[dict[str, Any]]) -> None:
    """Cache last listed repos so select can resolve full_name/url without re-fetch."""
    uid = int(user_id or 0)
    if uid <= 0:
        return
    r = _redis()
    if r is None:
        return
    try:
        payload = json.dumps({"page": int(page), "items": resources}, ensure_ascii=False)
        r.set(f"{_REPO_CACHE_PREFIX}{uid}", payload, ex=3600)
    except Exception:
        logger.debug("repo page cache write failed", exc_info=True)


def resolve_cached_repo(user_id: int, resource_id: str) -> dict[str, Any] | None:
    uid = int(user_id or 0)
    rid = str(resource_id or "").strip()
    if uid <= 0 or not rid:
        return None
    r = _redis()
    if r is None:
        return None
    try:
        raw = r.get(f"{_REPO_CACHE_PREFIX}{uid}")
        if not raw:
            return None
        data = json.loads(raw)
        for item in data.get("items") or []:
            if str(item.get("resource_id") or item.get("id") or "") == rid:
                return dict(item)
    except Exception:
        logger.debug("repo cache resolve failed", exc_info=True)
    return None
