"""HMAC-signed Telegram callback_data — always ≤ 64 bytes.

Wire format (v2, binary → base64url):
  packed = action\\x1f arg\\x1f uid_str\\x1f exp_str
  mac    = HMAC-SHA256(secret, packed)[:6]   # 48-bit
  wire   = "L2." + b64url(packed + mac)      # single blob, ≤ 64

Bound to user_id; expires; timing-safe verify.
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

_PREFIX = "L2."
_MAC_LEN = 8  # 64-bit; still fits Telegram 64-byte callback limit
_DEFAULT_TTL_SEC = 6 * 3600
_SEP = "\x1f"


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _secret() -> bytes:
    """Derive HMAC key. Prefer dedicated CALLBACK_HMAC_SECRET.

    Production without an explicit secret or bot token fails closed —
    never falls back to a public constant (callback forgery risk).
    """
    raw = (os.getenv("CALLBACK_HMAC_SECRET") or "").strip()
    if raw:
        return hashlib.sha256(raw.encode("utf-8")).digest()
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if token:
        return hmac.new(b"lumen-callback-v2", token.encode("utf-8"), hashlib.sha256).digest()
    env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "production").strip().lower()
    if env in {"dev", "development", "local", "test"}:
        # Deterministic only for local unit tests — not a production key
        return hashlib.sha256(b"lumen-dev-callback-only").digest()
    raise RuntimeError(
        "CALLBACK_HMAC_SECRET or TELEGRAM_BOT_TOKEN required for signed callbacks in production"
    )


# Short aliases keep the packed blob small under the 64-byte Telegram limit
_ACTION_SHORT: dict[str, str] = {
    "home": "h",
    "open_generate": "og",
    "open_dashboard": "od",
    "open_billing": "ob",
    "open_help": "oh",
    "confirm_generate": "cg",
    "cancel_generate": "xg",
    "await_generate_text": "ag",
    "pick_type": "pt",
    "fill_slot": "fs",
    "skip_need": "sn",
    "to_confirm": "tc",
    "resume_slots": "rs",
    "post_trial": "ptr",
    "post_host": "ph",
    "post_zip": "pz",
    "post_preview": "pp",
    "dash_status": "ds",
    "dash_stop": "dx",
    "dash_diagnose": "dd",
    "dash_trial": "dt",
    "dash_logs": "dl",
    "host_restart": "hr",
    "ask_gh_token": "agt",
    "ask_bot_token": "abt",
    "repo_sec": "rsx",
    "hitl_confirm": "hc",
    "hitl_reject": "hj",
}
_SHORT_ACTION: dict[str, str] = {v: k for k, v in _ACTION_SHORT.items()}


def _shorten_action(action: str) -> str:
    a = (action or "").strip().lower()
    return _ACTION_SHORT.get(a, a[:10])


def _expand_action(short: str) -> str:
    s = (short or "").strip().lower()
    return _SHORT_ACTION.get(s, s)


def encode_signed(
    action: str,
    arg: str = "",
    *,
    user_id: int,
    ttl_sec: int = _DEFAULT_TTL_SEC,
) -> str:
    """Build signed callback_data guaranteed ≤ 64 UTF-8 bytes."""
    act = _shorten_action(action)
    arg = (arg or "").strip()[:12]
    exp = int(time.time()) + max(60, int(ttl_sec))
    # Compact text fields — no base64 of each field
    packed = f"{act}{_SEP}{arg}{_SEP}{int(user_id)}{_SEP}{exp}".encode("utf-8")
    mac = hmac.new(_secret(), packed, hashlib.sha256).digest()[:_MAC_LEN]
    blob = packed + mac
    wire = _PREFIX + _b64u(blob)
    # Hard clamp: if still over 64, drop arg then shorten action
    if len(wire.encode("utf-8")) > 64:
        packed = f"{act}{_SEP}{_SEP}{int(user_id)}{_SEP}{exp}".encode("utf-8")
        mac = hmac.new(_secret(), packed, hashlib.sha256).digest()[:_MAC_LEN]
        wire = _PREFIX + _b64u(packed + mac)
    if len(wire.encode("utf-8")) > 64:
        # Extreme: action 4 chars only
        act = act[:4]
        packed = f"{act}{_SEP}{_SEP}{int(user_id)}{_SEP}{exp}".encode("utf-8")
        mac = hmac.new(_secret(), packed, hashlib.sha256).digest()[:_MAC_LEN]
        wire = _PREFIX + _b64u(packed + mac)
    if len(wire.encode("utf-8")) > 64:
        raise ValueError(f"signed_callback_too_long:{len(wire)}")
    return wire


def decode_signed(data: str, *, user_id: int) -> Optional[tuple[str, str]]:
    """Verify MAC + expiry + uid. Returns (action, arg) or None."""
    raw = (data or "").strip()
    if not raw.startswith(_PREFIX):
        # Legacy unsigned / v1 — reject (force fresh /start)
        return None
    try:
        blob = _b64u_decode(raw[len(_PREFIX) :])
    except Exception:
        return None
    if len(blob) <= _MAC_LEN:
        return None
    packed, mac_got = blob[:-_MAC_LEN], blob[-_MAC_LEN:]
    mac_exp = hmac.new(_secret(), packed, hashlib.sha256).digest()[:_MAC_LEN]
    if not hmac.compare_digest(mac_got, mac_exp):
        logger.warning("callback MAC fail uid=%s", user_id)
        return None
    try:
        text = packed.decode("utf-8")
        parts = text.split(_SEP)
        if len(parts) != 4:
            return None
        act_s, arg, uid_s, exp_s = parts
        token_uid = int(uid_s)
        exp = int(exp_s)
    except Exception:
        return None
    if token_uid != int(user_id):
        logger.warning(
            "callback uid mismatch token_uid=%s clicker=%s",
            token_uid,
            user_id,
        )
        return None
    if exp < int(time.time()):
        logger.info("callback expired uid=%s", user_id)
        return None
    return _expand_action(act_s), (arg or "").strip()
