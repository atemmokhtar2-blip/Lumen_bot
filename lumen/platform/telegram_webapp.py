"""Telegram Mini App (WebApp) initData validation — official algorithm.

Spec: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

  secret_key = HMAC_SHA256(key="WebAppData", msg=bot_token)
  data_check_string = "\\n".join(sorted(f"{k}={v}" for k,v in fields if k != "hash"))
  calculated = HMAC_SHA256(key=secret_key, msg=data_check_string).hex()
  accept iff hmac.compare_digest(calculated, hash) and auth_date is fresh.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl

logger = logging.getLogger("lumen.telegram_webapp")

_MAX_AGE_SEC = int(os.getenv("TELEGRAM_WEBAPP_MAX_AGE_SEC") or "86400")  # 24h


@dataclass(frozen=True)
class WebAppUser:
    id: int
    username: str = ""
    first_name: str = ""
    last_name: str = ""
    language_code: str = ""
    is_premium: bool = False


@dataclass(frozen=True)
class WebAppAuth:
    ok: bool
    user: WebAppUser | None = None
    auth_date: int = 0
    query_id: str = ""
    reason: str = ""
    raw: dict[str, str] | None = None


def _bot_token() -> str:
    return (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()


def validate_init_data(
    init_data: str,
    *,
    bot_token: str | None = None,
    max_age_sec: int | None = None,
) -> WebAppAuth:
    """Validate Telegram WebApp initData. Fail-closed on any defect."""
    raw = (init_data or "").strip()
    if not raw:
        return WebAppAuth(ok=False, reason="empty_init_data")

    token = (bot_token if bot_token is not None else _bot_token()).strip()
    if not token:
        return WebAppAuth(ok=False, reason="bot_token_missing")

    try:
        pairs = dict(parse_qsl(raw, keep_blank_values=True))
    except Exception:
        return WebAppAuth(ok=False, reason="parse_error")

    recv_hash = (pairs.get("hash") or "").strip()
    if not recv_hash or len(recv_hash) != 64:
        return WebAppAuth(ok=False, reason="hash_missing")

    # Exclude both hash and signature (Bot API 8.0 third-party / dual-sign fields)
    check_parts = [
        f"{k}={v}"
        for k, v in sorted(pairs.items())
        if k not in {"hash", "signature"}
    ]
    data_check_string = "\n".join(check_parts)

    secret_key = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
    calc = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, recv_hash):
        return WebAppAuth(ok=False, reason="hash_mismatch")

    try:
        auth_date = int(pairs.get("auth_date") or "0")
    except ValueError:
        return WebAppAuth(ok=False, reason="auth_date_invalid")

    age_limit = int(max_age_sec if max_age_sec is not None else _MAX_AGE_SEC)
    now = int(time.time())
    if auth_date <= 0 or (now - auth_date) > age_limit or auth_date > now + 60:
        return WebAppAuth(ok=False, reason="auth_date_stale")

    user: WebAppUser | None = None
    user_raw = pairs.get("user") or ""
    if user_raw:
        try:
            u = json.loads(user_raw)
            uid = int(u.get("id") or 0)
            if uid <= 0:
                return WebAppAuth(ok=False, reason="user_id_invalid")
            user = WebAppUser(
                id=uid,
                username=str(u.get("username") or ""),
                first_name=str(u.get("first_name") or ""),
                last_name=str(u.get("last_name") or ""),
                language_code=str(u.get("language_code") or ""),
                is_premium=bool(u.get("is_premium")),
            )
        except Exception:
            return WebAppAuth(ok=False, reason="user_parse_error")
    else:
        return WebAppAuth(ok=False, reason="user_missing")

    return WebAppAuth(
        ok=True,
        user=user,
        auth_date=auth_date,
        query_id=str(pairs.get("query_id") or ""),
        reason="ok",
        raw={k: v for k, v in pairs.items() if k != "hash"},
    )


def looks_like_bot_token(value: str) -> bool:
    import re
    return bool(re.match(r"^\d{6,12}:[A-Za-z0-9_-]{30,}$", (value or "").strip()))


def looks_like_github_pat(value: str) -> bool:
    v = (value or "").strip()
    if v.startswith("ghp_") and len(v) >= 40:
        return True
    if v.startswith("github_pat_") and len(v) >= 50:
        return True
    return False
