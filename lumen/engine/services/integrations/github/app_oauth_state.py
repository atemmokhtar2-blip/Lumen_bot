"""Signed OAuth/install state for GitHub App ↔ Telegram user binding.

state = base64url(payload_json) + "." + base64url(hmac_sha256)
payload = {uid, nonce, exp, v}

Security:
  - HMAC with TBE_TOKEN_SECRET
  - TTL (default 15m)
  - Single-use nonce consumed at verify (Redis preferred; in-process fallback)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time
from typing import Any
from lumen.platform.redis_client import connect_redis_url
from lumen.engine.services.integrations.github.util import github_redis as _redis

logger = logging.getLogger("lumen.github.app_oauth_state")

_STATE_TTL_SEC = int(os.getenv("GITHUB_APP_STATE_TTL_SEC") or str(15 * 60))
_VERSION = 1
_NONCE_PREFIX = "lumen:ghapp:state_nonce:"
_INSTALL_USER_PREFIX = "lumen:ghapp:install_user:"
_USER_INSTALL_PREFIX = "lumen:ghapp:user_install:"

_lock = threading.Lock()
_local_nonces: dict[str, float] = {}  # nonce -> exp


from lumen.engine.services.integrations.github.util import b64url as _b64url, b64url_decode as _b64url_decode


def _hmac_key() -> bytes:
    try:
        from lumen.platform.secrets_provider import get_secret
        raw = (
            (get_secret("TBE_TOKEN_SECRET", "") or "").strip()
            or (get_secret("GITHUB_APP_CLIENT_SECRET", "") or "").strip()
        )
    except Exception:
        raw = ""
    if not raw:
        raw = (
            (os.getenv("TBE_TOKEN_SECRET") or "").strip()
            or (os.getenv("GITHUB_APP_CLIENT_SECRET") or "").strip()
            or (os.getenv("SECRET_INBOX_KEY") or "").strip()
        )
    if len(raw) < 16:
        env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "production").strip().lower()
        if env in {"dev", "development", "local", "test"}:
            raw = (os.getenv("TELEGRAM_BOT_TOKEN") or "dev-github-app-state") + "|ghapp-state"
        else:
            raise RuntimeError("TBE_TOKEN_SECRET required to sign GitHub App state")
    return hashlib.sha256(b"lumen-ghapp-state-v1|" + raw.encode("utf-8")).digest()




def _reserve_nonce(nonce: str, exp: int) -> None:
    """Mark nonce as issued (not yet consumed)."""
    ttl = max(30, int(exp - time.time()))
    r = _redis()
    if r is not None:
        try:
            # value=pending until consumed
            r.set(f"{_NONCE_PREFIX}{nonce}", "pending", ex=ttl, nx=True)
            return
        except Exception:
            logger.debug("nonce reserve redis failed", exc_info=True)
    try:
        from lumen.platform.prod_security_gate import is_production_runtime
        if is_production_runtime():
            raise RuntimeError("oauth_state_nonce_requires_redis")
    except RuntimeError:
        raise
    except Exception:
        pass
    with _lock:
        _local_nonces[nonce] = float(exp)


def _consume_nonce(nonce: str) -> bool:
    """Return True if nonce was valid and not previously used."""
    if not nonce:
        return False
    r = _redis()
    if r is not None:
        try:
            key = f"{_NONCE_PREFIX}{nonce}"
            # GETDEL if available, else GET+DELETE
            try:
                val = r.getdel(key)
            except Exception:
                val = r.get(key)
                if val is not None:
                    r.delete(key)
            return val is not None
        except Exception:
            logger.debug("nonce consume redis failed", exc_info=True)
    try:
        from lumen.platform.prod_security_gate import is_production_runtime
        if is_production_runtime():
            return False  # redis path already failed
    except Exception:
        pass
    with _lock:
        exp = _local_nonces.pop(nonce, None)
        if exp is None:
            return False
        return float(exp) >= time.time()


def sign_install_state(telegram_user_id: int, *, ttl_sec: int | None = None) -> str:
    """Create state binding this Telegram user for the install redirect."""
    uid = int(telegram_user_id or 0)
    if uid <= 0:
        raise ValueError("telegram_user_id_required")
    ttl = int(ttl_sec if ttl_sec is not None else _STATE_TTL_SEC)
    ttl = max(60, min(3600, ttl))
    nonce = secrets.token_hex(16)
    exp = int(time.time()) + ttl
    payload = {
        "v": _VERSION,
        "uid": uid,
        "nonce": nonce,
        "exp": exp,
    }
    body = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    sig = _b64url(hmac.new(_hmac_key(), body.encode("ascii"), hashlib.sha256).digest())
    _reserve_nonce(nonce, exp)
    return f"{body}.{sig}"


def verify_install_state(state: str, *, consume: bool = True) -> dict[str, Any]:
    """Verify and return payload; raises ValueError on any failure.

    When consume=True (default), nonce is single-use — replay fails.
    """
    raw = (state or "").strip()
    if not raw or raw.count(".") != 1:
        raise ValueError("state_malformed")
    body, sig = raw.split(".", 1)
    if not body or not sig:
        raise ValueError("state_malformed")
    expect = _b64url(hmac.new(_hmac_key(), body.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(expect, sig):
        raise ValueError("state_bad_signature")
    try:
        payload = json.loads(_b64url_decode(body).decode("utf-8"))
    except Exception as exc:
        raise ValueError("state_bad_payload") from exc
    if not isinstance(payload, dict):
        raise ValueError("state_bad_payload")
    if int(payload.get("v") or 0) != _VERSION:
        raise ValueError("state_version")
    try:
        uid = int(payload.get("uid") or 0)
        exp = int(payload.get("exp") or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("state_bad_fields") from exc
    if uid <= 0:
        raise ValueError("state_bad_uid")
    if exp < int(time.time()):
        raise ValueError("state_expired")
    nonce = str(payload.get("nonce") or "")
    if consume:
        if not _consume_nonce(nonce):
            raise ValueError("state_replay")
    return {"uid": uid, "nonce": nonce, "exp": exp}


def bind_installation_to_user(installation_id: int | str, telegram_user_id: int) -> None:
    """Index installation_id → telegram uid (for webhooks uninstall)."""
    try:
        iid = str(int(installation_id))
    except (TypeError, ValueError):
        return
    uid = int(telegram_user_id or 0)
    if uid <= 0 or not iid:
        return
    r = _redis()
    if r is None:
        return
    try:
        # 90 days — connection may be long-lived
        r.set(f"{_INSTALL_USER_PREFIX}{iid}", str(uid), ex=90 * 24 * 3600)
        r.set(f"{_USER_INSTALL_PREFIX}{uid}", iid, ex=90 * 24 * 3600)
    except Exception:
        logger.debug("bind installation index failed", exc_info=True)


def lookup_user_for_installation(installation_id: int | str) -> int | None:
    try:
        iid = str(int(installation_id))
    except (TypeError, ValueError):
        return None
    r = _redis()
    if r is None:
        return None
    try:
        raw = r.get(f"{_INSTALL_USER_PREFIX}{iid}")
        if raw:
            return int(raw)
    except Exception:
        logger.debug("lookup installation user failed", exc_info=True)
    return None


def clear_installation_index(installation_id: int | str | None = None, *, user_id: int | None = None) -> None:
    r = _redis()
    if r is None:
        return
    try:
        if installation_id is not None:
            iid = str(int(installation_id))
            uid_s = r.get(f"{_INSTALL_USER_PREFIX}{iid}")
            r.delete(f"{_INSTALL_USER_PREFIX}{iid}")
            if uid_s:
                r.delete(f"{_USER_INSTALL_PREFIX}{uid_s}")
        if user_id is not None:
            uid = int(user_id)
            iid = r.get(f"{_USER_INSTALL_PREFIX}{uid}")
            r.delete(f"{_USER_INSTALL_PREFIX}{uid}")
            if iid:
                r.delete(f"{_INSTALL_USER_PREFIX}{iid}")
    except Exception:
        logger.debug("clear installation index failed", exc_info=True)


def build_telegram_install_url(telegram_user_id: int) -> str:
    """Full GitHub App install URL with signed state for this user."""
    from lumen.engine.services.integrations.github.app_auth import install_url

    state = sign_install_state(int(telegram_user_id))
    return install_url(state=state)


def telegram_return_url(*, bot_username: str = "", start_payload: str = "gh_connected") -> str:
    bot = (bot_username or os.getenv("TELEGRAM_BOT_USERNAME") or os.getenv("BOT_USERNAME") or "").strip().lstrip("@")
    if not bot:
        return ""
    payload = (start_payload or "gh_connected").strip()[:64]
    return f"https://t.me/{bot}?start={payload}"


__all__ = [
    "sign_install_state",
    "verify_install_state",
    "build_telegram_install_url",
    "bind_installation_to_user",
    "lookup_user_for_installation",
    "clear_installation_index",
    "telegram_return_url",
]
