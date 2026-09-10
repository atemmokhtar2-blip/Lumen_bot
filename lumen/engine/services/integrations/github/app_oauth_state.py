"""Signed OAuth/install state for GitHub App ↔ Telegram user binding.

state = base64url(payload_json) + "." + base64url(hmac_sha256)
payload = {uid, nonce, exp, v}
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from typing import Any

logger = logging.getLogger("lumen.github.app_oauth_state")

_STATE_TTL_SEC = int(os.getenv("GITHUB_APP_STATE_TTL_SEC") or str(15 * 60))
_VERSION = 1


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _hmac_key() -> bytes:
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


def sign_install_state(telegram_user_id: int, *, ttl_sec: int | None = None) -> str:
    """Create state binding this Telegram user for the install redirect."""
    uid = int(telegram_user_id or 0)
    if uid <= 0:
        raise ValueError("telegram_user_id_required")
    ttl = int(ttl_sec if ttl_sec is not None else _STATE_TTL_SEC)
    ttl = max(60, min(3600, ttl))
    payload = {
        "v": _VERSION,
        "uid": uid,
        "nonce": secrets.token_hex(12),
        "exp": int(time.time()) + ttl,
    }
    body = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    sig = _b64url(hmac.new(_hmac_key(), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_install_state(state: str) -> dict[str, Any]:
    """Verify and return payload; raises ValueError on any failure."""
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
    return {"uid": uid, "nonce": str(payload.get("nonce") or ""), "exp": exp}


def build_telegram_install_url(telegram_user_id: int) -> str:
    """Full GitHub App install URL with signed state for this user."""
    from lumen.engine.services.integrations.github.app_auth import install_url

    state = sign_install_state(int(telegram_user_id))
    return install_url(state=state)


__all__ = [
    "sign_install_state",
    "verify_install_state",
    "build_telegram_install_url",
]
