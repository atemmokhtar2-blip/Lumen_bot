"""Phase 2 hardened: single-use state, setup bind, install index."""
from __future__ import annotations

import sys
import time
import types
from pathlib import Path

import pytest


def _ensure_aiohttp_stub():
    if "aiohttp" in sys.modules and hasattr(sys.modules.get("aiohttp"), "web"):
        return

    class Response:
        def __init__(self, text="", content_type=None, charset=None, status=200, **kwargs):
            self.text = text
            self.status = status
            self.content_type = content_type

    def json_response(data, status=200):
        return Response(text=str(data), status=status)

    web = types.SimpleNamespace(Request=object, Response=Response, json_response=json_response)
    aio = types.ModuleType("aiohttp")
    aio.web = web
    sys.modules["aiohttp"] = aio


def test_sign_and_verify_install_state_single_use(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("TBE_TOKEN_SECRET", "phase2-state-secret-key-32chars!!")
    from lumen.engine.services.integrations.github.app_oauth_state import (
        sign_install_state,
        verify_install_state,
    )

    state = sign_install_state(42, ttl_sec=120)
    payload = verify_install_state(state, consume=True)
    assert payload["uid"] == 42
    with pytest.raises(ValueError, match="state_replay"):
        verify_install_state(state, consume=True)


def test_verify_rejects_tamper(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("TBE_TOKEN_SECRET", "phase2-state-secret-key-32chars!!")
    from lumen.engine.services.integrations.github.app_oauth_state import (
        sign_install_state,
        verify_install_state,
    )

    state = sign_install_state(7)
    body, sig = state.split(".", 1)
    bad = body + "." + ("A" * len(sig))
    with pytest.raises(ValueError, match="state_bad_signature"):
        verify_install_state(bad)


def test_verify_rejects_expired(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("TBE_TOKEN_SECRET", "phase2-state-secret-key-32chars!!")
    from lumen.engine.services.integrations.github import app_oauth_state as st

    state = st.sign_install_state(9, ttl_sec=60)
    payload = st.verify_install_state(state, consume=False)
    monkeypatch.setattr(time, "time", lambda: payload["exp"] + 10)
    with pytest.raises(ValueError, match="state_expired"):
        st.verify_install_state(state, consume=False)


def test_setup_callback_binds_installation(monkeypatch):
    import asyncio
    import importlib.util

    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("TBE_TOKEN_SECRET", "phase2-state-secret-key-32chars!!")
    _ensure_aiohttp_stub()

    from lumen.engine.services.integrations.github.app_oauth_state import sign_install_state

    state = sign_install_state(55)
    bound = {}

    def _fake_write(uid, installation_id, **kwargs):
        bound["uid"] = uid
        bound["installation_id"] = str(installation_id)
        bound["login"] = kwargs.get("login") or ""
        return True

    path = Path("lumen/api/routes/github_app.py")
    spec = importlib.util.spec_from_file_location("gh_app_route_test2", path)
    route = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(route)

    import lumen.bot.ui.github_connection_store as gcs
    monkeypatch.setattr(gcs, "write_github_app_connection", _fake_write)

    import lumen.engine.services.integrations.github.app_auth as aa
    monkeypatch.setattr(
        aa,
        "get_installation",
        lambda iid: {
            "account": {"login": "octocat", "type": "User"},
            "repository_selection": "selected",
        },
    )

    class _Req:
        class rel_url:
            query = {
                "installation_id": "12345",
                "setup_action": "install",
                "state": state,
            }

        headers = {}
        remote = "127.0.0.1"

    resp = asyncio.run(route.github_app_setup(_Req()))
    assert resp.status == 200
    assert bound["uid"] == 55
    assert bound["installation_id"] == "12345"
    assert bound["login"] == "octocat"
    assert "تم ربط" in resp.text or "GitHub" in resp.text


def test_installation_deleted_webhook_clears_binding(monkeypatch):
    import importlib.util

    _ensure_aiohttp_stub()
    # aiohttp.web.middleware decorator used at import of other modules — add noop
    import aiohttp
    if not hasattr(aiohttp.web, "middleware"):
        aiohttp.web.middleware = lambda f: f

    path = Path("lumen/api/routes/github_webhooks.py")
    spec = importlib.util.spec_from_file_location("gh_webhooks_test", path)
    wh = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(wh)

    cleared = {}

    monkeypatch.setattr(
        "lumen.engine.services.integrations.github.app_oauth_state.lookup_user_for_installation",
        lambda iid: 77,
    )
    monkeypatch.setattr(
        "lumen.engine.services.integrations.github.app_oauth_state.clear_installation_index",
        lambda *a, **k: cleared.setdefault("index", True),
    )
    monkeypatch.setattr(
        "lumen.engine.services.integrations.github.app_auth.clear_installation_token_cache",
        lambda *a, **k: cleared.setdefault("token", True),
    )
    monkeypatch.setattr(
        "lumen.bot.ui.github_connection_store.delete_github_connection",
        lambda uid: cleared.setdefault("uid", uid),
    )

    out = wh._handle_installation_event(
        "installation",
        "deleted",
        {"installation": {"id": 999, "account": {"login": "x"}}},
    )
    assert out["ok"] is True
    assert cleared.get("uid") == 77
    assert cleared.get("index")
    assert cleared.get("token")
