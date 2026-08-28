"""HMAC-signed Telegram callback_data (production standard 2025–2026).

Threat model Telegram does NOT solve for you:
  - Users can copy any callback_data from a button and resend it.
  - Plain strings like ``lumen:ui:dash_stop:0`` can be forged offline.
  - Stale buttons from old messages remain clickable forever.

World-class pattern (HMAC-SHA256 + uid bind + expiry + short MAC):
  payload = action|arg|uid|exp_unix
  mac     = HMAC-SHA256(secret, payload)[:10]  # 80-bit truncated
  wire    = base64url(payload) + "." + base64url(mac)   # ≤ 64 bytes

Reject when:
  - MAC fails (timing-safe)
  - exp < now
  - uid in token != effective_user.id
  - action not in closed catalog (checked by caller)

Secret: CALLBACK_HMAC_SECRET env, else derived from TELEGRAM_BOT_TOKEN.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import time
from typing import Optional

logger = logging.getLogger("lumen_bot.ui.signed_callback")

_PREFIX = "L1."  # versioned scheme; reject unknown versions
_MAC_LEN = 10  # bytes kept from HMAC (80-bit)
_DEFAULT_TTL_SEC = 6 * 3600  # 6h — buttons expire; user hits /start for fresh UI


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _secret() -> bytes:
    raw = (os.getenv("CALLBACK_HMAC_SECRET") or "").strip()
    if raw:
        return raw.encode("utf-8")
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        # Fail closed in production-like envs would break local tests — use fixed weak only in tests
        return b"lumen-dev-callback-secret-not-for-prod"
    # Derive a dedicated key so the bot token is never used raw as HMAC key material pattern
    return hmac.new(b"lumen-callback-v1", token.encode("utf-8"), hashlib.sha256).digest()


def encode_signed(
    action: str,
    arg: str = "",
    *,
    user_id: int,
    ttl_sec: int = _DEFAULT_TTL_SEC,
) -> str:
    """Build ≤64-byte signed callback_data bound to ``user_id``."""
    action = (action or "").strip().lower()[:24]
    arg = (arg or "").strip()[:16]
    exp = int(time.time()) + max(60, int(ttl_sec))
    # Compact plaintext — no JSON (saves bytes under 64 limit)
    plain = f"{action}|{arg}|{int(user_id)}|{exp}".encode("utf-8")
    mac = hmac.new(_secret(), plain, hashlib.sha256).digest()[:_MAC_LEN]
    wire = _PREFIX + _b64u(plain) + "." + _b64u(mac)
    if len(wire.encode("utf-8")) > 64:
        # Extreme truncation fallback — still signed
        action = action[:12]
        arg = arg[:8]
        plain = f"{action}|{arg}|{int(user_id)}|{exp}".encode("utf-8")
        mac = hmac.new(_secret(), plain, hashlib.sha256).digest()[:_MAC_LEN]
        wire = _PREFIX + _b64u(plain) + "." + _b64u(mac)
    if len(wire.encode("utf-8")) > 64:
        raise ValueError(f"signed_callback_too_long:{len(wire)}")
    return wire


def decode_signed(data: str, *, user_id: int) -> Optional[tuple[str, str]]:
    """Verify MAC + expiry + uid binding. Returns (action, arg) or None."""
    raw = (data or "").strip()
    if not raw.startswith(_PREFIX):
        return None
    body = raw[len(_PREFIX) :]
    if "." not in body:
        return None
    p_b64, m_b64 = body.rsplit(".", 1)
    try:
        plain = _b64u_decode(p_b64)
        mac_got = _b64u_decode(m_b64)
    except Exception:
        return None
    mac_exp = hmac.new(_secret(), plain, hashlib.sha256).digest()[:_MAC_LEN]
    if not hmac.compare_digest(mac_got, mac_exp):
        logger.warning("callback MAC fail uid=%s", user_id)
        return None
    try:
        text = plain.decode("utf-8")
        parts = text.split("|")
        if len(parts) != 4:
            return None
        action, arg, uid_s, exp_s = parts
        token_uid = int(uid_s)
        exp = int(exp_s)
    except Exception:
        return None
    if token_uid != int(user_id):
        logger.warning(
            "callback uid mismatch token_uid=%s clicker=%s action=%s",
            token_uid,
            user_id,
            action,
        )
        return None
    if exp < int(time.time()):
        logger.info("callback expired uid=%s action=%s", user_id, action)
        return None
    return action.strip().lower(), (arg or "").strip()
