"""Durable encrypted GitHub PAT + connection profile + repo list cache.

Redis primary (multi-worker). secret_inbox is mirror only.

Responsibility split
--------------------
* token_store  — credentials + profile + repo list cache (connection layer)
* bind_repo    — clone/workspace (active_repo plane)
* hosting      — runtime only when workspace is ready
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
_PROFILE_PREFIX = "lumen:conn:gh:profile:"
_REPO_CACHE_PREFIX = "lumen:conn:gh:repos:"
_DEFAULT_TTL = 30 * 24 * 3600  # 30 days — connection survives long absences
_REPO_CACHE_TTL = 6 * 3600  # 6h list cache; auto-refresh on open when stale


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
    meta = dict(meta or {})
    payload = json.dumps(
        {"ciphertext": cipher, "meta": meta, "saved_at": time.time()},
        ensure_ascii=False,
    )
    r = _redis()
    if r is not None:
        try:
            r.set(f"{_KEY_PREFIX}{uid}", payload, ex=_DEFAULT_TTL)
        except Exception:
            logger.exception("redis save github token failed uid=%s", uid)
            r = None
    # Non-secret profile (login) — independent of ciphertext
    save_connection_profile(
        uid,
        {
            "login": str(meta.get("login") or "")[:80],
            "provider": "github",
            "connected": True,
            "connected_at": time.time(),
        },
    )
    try:
        from lumen.platform.secret_inbox import put_secret

        put_secret(
            user_id=uid,
            kind="github",
            plaintext=tok,
            purpose="connection",
            ttl_sec=_DEFAULT_TTL,
            meta={"provider": "github", **meta},
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
            r.delete(
                f"{_KEY_PREFIX}{uid}",
                f"{_PROFILE_PREFIX}{uid}",
                f"{_REPO_CACHE_PREFIX}{uid}",
            )
        except Exception:
            pass


def save_connection_profile(user_id: int, profile: dict[str, Any]) -> None:
    """Non-secret durable profile (login, connected flags). Survives UI navigation."""
    uid = int(user_id or 0)
    if uid <= 0:
        return
    data = {
        "login": str(profile.get("login") or "")[:80],
        "provider": "github",
        "connected": bool(profile.get("connected", True)),
        "connected_at": float(profile.get("connected_at") or time.time()),
        "updated_at": time.time(),
    }
    r = _redis()
    if r is not None:
        try:
            r.set(f"{_PROFILE_PREFIX}{uid}", json.dumps(data, ensure_ascii=False), ex=_DEFAULT_TTL)
        except Exception:
            logger.debug("save_connection_profile redis failed", exc_info=True)


def load_connection_profile(user_id: int) -> dict[str, Any] | None:
    uid = int(user_id or 0)
    if uid <= 0:
        return None
    r = _redis()
    if r is not None:
        try:
            raw = r.get(f"{_PROFILE_PREFIX}{uid}")
            if raw:
                return dict(json.loads(raw))
        except Exception:
            logger.debug("load_connection_profile failed", exc_info=True)
    # Infer from token presence
    if load_github_token(uid):
        return {"login": "", "provider": "github", "connected": True, "connected_at": 0}
    return None


def cache_repo_page(
    user_id: int,
    page: int,
    resources: list[dict[str, Any]],
    *,
    fingerprint: str = "",
) -> None:
    uid = int(user_id or 0)
    if uid <= 0:
        return
    r = _redis()
    if r is None:
        return
    try:
        payload = json.dumps(
            {
                "page": int(page),
                "items": resources,
                "cached_at": time.time(),
                "fingerprint": fingerprint
                or hashlib.sha1(
                    ",".join(str(x.get("resource_id") or "") for x in resources).encode()
                ).hexdigest()[:16],
            },
            ensure_ascii=False,
        )
        r.set(f"{_REPO_CACHE_PREFIX}{uid}", payload, ex=_REPO_CACHE_TTL)
    except Exception:
        logger.debug("repo page cache write failed", exc_info=True)


def load_repo_cache(user_id: int) -> dict[str, Any] | None:
    uid = int(user_id or 0)
    if uid <= 0:
        return None
    r = _redis()
    if r is None:
        return None
    try:
        raw = r.get(f"{_REPO_CACHE_PREFIX}{uid}")
        if not raw:
            return None
        return dict(json.loads(raw))
    except Exception:
        logger.debug("repo cache load failed", exc_info=True)
        return None


def repo_cache_is_stale(user_id: int, *, max_age_sec: float = 300.0) -> bool:
    cache = load_repo_cache(user_id)
    if not cache:
        return True
    age = time.time() - float(cache.get("cached_at") or 0)
    return age > float(max_age_sec)


def resolve_cached_repo(user_id: int, resource_id: str) -> dict[str, Any] | None:
    uid = int(user_id or 0)
    rid = str(resource_id or "").strip()
    if uid <= 0 or not rid:
        return None
    cache = load_repo_cache(uid)
    if not cache:
        return None
    try:
        for item in cache.get("items") or []:
            if str(item.get("resource_id") or item.get("id") or "") == rid:
                return dict(item)
    except Exception:
        logger.debug("repo cache resolve failed", exc_info=True)
    return None
