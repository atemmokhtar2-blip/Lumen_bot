"""Telegram Mini App secrets intake — validated initData, encrypted inbox.

POST /v1/telegram/secrets
  body: { init_data, kind: bot|github, secret, purpose? }
  auth: Telegram WebApp HMAC (not API key) — user proven by initData.
"""
from __future__ import annotations

import logging
import os

from aiohttp import web

logger = logging.getLogger("lumen_api.secrets")

_MAX_BODY = 8192



# One-shot initData anti-replay (hash of init_data string, TTL aligned with max_age)
_INIT_USED: dict[str, float] = {}
_INIT_USED_TTL = 600.0


def _init_data_replay_ok(init_data: str) -> bool:
    import hashlib, time
    h = hashlib.sha256(init_data.encode("utf-8")).hexdigest()
    now = time.time()
    # purge expired
    dead = [k for k, exp in _INIT_USED.items() if exp < now]
    for k in dead:
        _INIT_USED.pop(k, None)
    if h in _INIT_USED:
        return False
    _INIT_USED[h] = now + _INIT_USED_TTL
    return True

async def submit_telegram_secret(request: web.Request) -> web.Response:
    try:
        raw = await request.read()
    except Exception:
        return web.json_response({"ok": False, "error": "body_read_failed"}, status=400)
    if len(raw) > _MAX_BODY:
        return web.json_response({"ok": False, "error": "payload_too_large"}, status=413)
    try:
        import json
        data = json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        return web.json_response({"ok": False, "error": "invalid_json"}, status=400)

    init_data = str(data.get("init_data") or data.get("initData") or "").strip()
    kind = str(data.get("kind") or "bot").strip().lower()
    secret = str(data.get("secret") or "").strip()
    purpose = str(data.get("purpose") or "").strip()[:40]

    if kind not in {"bot", "github", "pat"}:
        return web.json_response({"ok": False, "error": "invalid_kind"}, status=400)
    if not secret:
        return web.json_response({"ok": False, "error": "secret_required"}, status=400)

    from lumen.platform.telegram_webapp import (
        validate_init_data,
        looks_like_bot_token,
        looks_like_github_pat,
    )

    # Secrets are high-value: reject initData older than 5 minutes (default WebApp TTL is longer)
    auth = validate_init_data(init_data, max_age_sec=int(__import__("os").getenv("TELEGRAM_SECRETS_MAX_AGE_SEC") or "300"))
    if not auth.ok or auth.user is None:
        logger.warning("webapp auth failed reason=%s", auth.reason)
        return web.json_response(
            {"ok": False, "error": "unauthorized", "detail": auth.reason},
            status=401,
        )
    if not _init_data_replay_ok(init_data):
        logger.warning("webapp initData replay uid=%s", auth.user.id)
        return web.json_response(
            {"ok": False, "error": "replay", "detail": "init_data_already_used"},
            status=401,
        )

    if kind == "bot" and not looks_like_bot_token(secret):
        return web.json_response({"ok": False, "error": "invalid_bot_token_format"}, status=400)
    if kind in {"github", "pat"} and not looks_like_github_pat(secret):
        return web.json_response({"ok": False, "error": "invalid_github_pat_format"}, status=400)

    from lumen.platform.secret_inbox import put_secret

    ok = put_secret(
        user_id=auth.user.id,
        kind=kind,
        plaintext=secret,
        purpose=purpose,
        meta={"via": "webapp", "username": auth.user.username},
    )
    if not ok:
        return web.json_response({"ok": False, "error": "store_failed"}, status=500)

    # Never echo the secret
    return web.json_response(
        {
            "ok": True,
            "kind": "github" if kind == "pat" else kind,
            "user_id": auth.user.id,
            "message": "secret_stored_encrypted",
            "hint_ar": "تم حفظ السر مشفراً. ارجع للدردشة واضغط «متابعة» أو أرسل أي رسالة قصيرة.",
        }
    )


async def secret_status(request: web.Request) -> web.Response:
    """Check if a pending secret exists (no plaintext). Auth via initData."""
    try:
        import json
        data = await request.json()
    except Exception:
        data = {}
    init_data = str(data.get("init_data") or data.get("initData") or "").strip()
    kind = str(data.get("kind") or "bot").strip().lower()
    from lumen.platform.telegram_webapp import validate_init_data
    auth = validate_init_data(init_data, max_age_sec=int(__import__("os").getenv("TELEGRAM_SECRETS_MAX_AGE_SEC") or "300"))
    if not auth.ok or auth.user is None:
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
    from lumen.platform.secret_inbox import peek_meta
    meta = peek_meta(user_id=auth.user.id, kind=kind)
    return web.json_response({"ok": True, "pending": meta is not None, "meta": meta})
