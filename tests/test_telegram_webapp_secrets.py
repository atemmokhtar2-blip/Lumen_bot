"""Prove Mini App initData validation + encrypted secret inbox + API shape."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlencode

import pytest


def _sign_init_data(bot_token: str, fields: dict[str, str]) -> str:
    """Build valid initData per Telegram WebApp algorithm."""
    pairs = dict(fields)
    pairs.setdefault("auth_date", str(int(time.time())))
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()) if k != "hash")
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret_key, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


def test_validate_init_data_accepts_good_signature(monkeypatch, tmp_path):
    token = "123456789:AAHfakeTokenForUnitTestsOnly_xxxxxxxxxxxx"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
    user = json.dumps({"id": 42, "username": "alice", "first_name": "A"})
    init = _sign_init_data(token, {"user": user, "query_id": "AAE"})
    from lumen.platform.telegram_webapp import validate_init_data

    auth = validate_init_data(init)
    assert auth.ok, auth.reason
    assert auth.user is not None
    assert auth.user.id == 42
    assert auth.user.username == "alice"


def test_validate_init_data_rejects_tamper(monkeypatch):
    token = "123456789:AAHfakeTokenForUnitTestsOnly_xxxxxxxxxxxx"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
    user = json.dumps({"id": 42, "username": "alice"})
    init = _sign_init_data(token, {"user": user})
    # Tamper user id after signing
    bad = init.replace("alice", "bob")
    from lumen.platform.telegram_webapp import validate_init_data

    auth = validate_init_data(bad)
    assert not auth.ok
    assert auth.reason in {"hash_mismatch", "user_parse_error", "parse_error"}


def test_validate_init_data_rejects_stale(monkeypatch):
    token = "123456789:AAHfakeTokenForUnitTestsOnly_xxxxxxxxxxxx"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
    user = json.dumps({"id": 7, "username": "x"})
    init = _sign_init_data(
        token, {"user": user, "auth_date": str(int(time.time()) - 999999)}
    )
    from lumen.platform.telegram_webapp import validate_init_data

    auth = validate_init_data(init, max_age_sec=60)
    assert not auth.ok
    assert auth.reason == "auth_date_stale"


def test_secret_inbox_put_consume_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("TBE_TOKEN_SECRET", "x" * 40)
    from lumen.platform import secret_inbox as si

    # reload path binding
    assert si.put_secret(user_id=99, kind="bot", plaintext="1234567890:AAHrealLookingTokenValue_abcdefghijkl")
    meta = si.peek_meta(user_id=99, kind="bot")
    assert meta is not None
    plain = si.consume_secret(user_id=99, kind="bot")
    assert plain.startswith("1234567890:")
    assert si.consume_secret(user_id=99, kind="bot") is None  # one-shot


def test_secret_inbox_never_stores_plaintext(monkeypatch, tmp_path):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("TBE_TOKEN_SECRET", "y" * 40)
    from lumen.platform import secret_inbox as si

    secret = "ghp_" + ("a" * 36)
    assert si.put_secret(user_id=1, kind="github", plaintext=secret)
    raw = (tmp_path / "secret_inbox" / "inbox.json").read_text(encoding="utf-8")
    assert secret not in raw
    assert "ciphertext" in raw


def test_api_route_rejects_without_init_data():
    from aiohttp.test_utils import make_mocked_request
    import asyncio
    from lumen.api.routes.secrets import submit_telegram_secret

    async def _run():
        req = make_mocked_request(
            "POST",
            "/v1/telegram/secrets",
            headers={"Content-Type": "application/json"},
        )
        # inject body
        async def read():
            return b'{"kind":"bot","secret":"123456:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}'
        req.read = read  # type: ignore
        resp = await submit_telegram_secret(req)
        assert resp.status == 401

    asyncio.run(_run())


def test_api_route_accepts_valid_webapp(monkeypatch, tmp_path):
    token = "123456789:AAHfakeTokenForUnitTestsOnly_xxxxxxxxxxxx"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("TBE_TOKEN_SECRET", "z" * 40)
    user = json.dumps({"id": 55, "username": "dev"})
    init = _sign_init_data(token, {"user": user})
    bot_token = "9876543210:AAHvalidFormatTokenValue_zzzzzzzzzzzzzz"

    from aiohttp.test_utils import make_mocked_request
    import asyncio
    import json as _json
    from lumen.api.routes.secrets import submit_telegram_secret

    async def _run():
        body = _json.dumps(
            {"init_data": init, "kind": "bot", "secret": bot_token, "purpose": "host"}
        ).encode()
        req = make_mocked_request(
            "POST",
            "/v1/telegram/secrets",
            headers={"Content-Type": "application/json"},
        )

        async def read():
            return body

        req.read = read  # type: ignore
        resp = await submit_telegram_secret(req)
        assert resp.status == 200, getattr(resp, "text", None)
        payload = _json.loads(resp.text)
        assert payload.get("ok") is True
        assert payload.get("user_id") == 55

    asyncio.run(_run())

    from lumen.platform.secret_inbox import consume_secret

    assert consume_secret(user_id=55, kind="bot") == bot_token


def test_secrets_page_exists():
    from pathlib import Path
    p = Path("web/app/secrets/page.tsx")
    assert p.is_file()
    src = p.read_text(encoding="utf-8")
    assert "initData" in src or "init_data" in src
    assert "/v1/telegram/secrets" in src
    assert "telegram-web-app.js" in src


def test_menu_button_url_requires_https(monkeypatch):
    from lumen.bot.ui.menu_button import secrets_menu_url
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("WEB_APP_URL", raising=False)
    assert secrets_menu_url() is None
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://insecure.example")
    assert secrets_menu_url() is None
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://app.example.com")
    assert secrets_menu_url() == "https://app.example.com/secrets?kind=bot"


def test_app_registers_secrets_routes():
    src = open("lumen/api/app.py", encoding="utf-8").read()
    assert "/v1/telegram/secrets" in src
    assert "secrets.submit_telegram_secret" in src
