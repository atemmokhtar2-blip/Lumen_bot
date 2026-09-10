"""Phase 1 wiring: credentials resolver + App install path (no live GitHub)."""
from __future__ import annotations

import time


def test_resolve_github_app_credentials_mints_token(monkeypatch):
    from lumen.engine.services.integrations.connections import token_store as ts
    from lumen.engine.services.integrations.connections.credentials import (
        is_github_connected,
        resolve_github_credentials,
        resolve_github_token,
    )

    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("TBE_TOKEN_SECRET", "phase1-test-secret-key-32b-min")

    uid = 424242
    ts.save_connection_profile(
        uid,
        {
            "login": "octocat",
            "account_login": "octocat",
            "connected": True,
            "auth_kind": "github_app",
            "installation_id": "778899",
            "account_type": "User",
            "repo_selection": "selected",
            "connected_at": time.time(),
        },
    )

    # Even without Redis, is_github_connected may be False — force profile via monkeypatch
    monkeypatch.setattr(
        "lumen.engine.services.integrations.connections.credentials._profile_for",
        lambda user_id: {
            "login": "octocat",
            "account_login": "octocat",
            "connected": True,
            "auth_kind": "github_app",
            "installation_id": "778899",
            "account_type": "User",
            "repo_selection": "selected",
        },
    )

    calls = {"n": 0}

    def _fake_mint(iid):
        calls["n"] += 1
        assert str(iid) == "778899"
        return "ghs_TEST_INSTALLATION_TOKEN_PHASE1"

    monkeypatch.setattr(
        "lumen.engine.services.integrations.github.app_auth.get_installation_token",
        _fake_mint,
    )

    assert is_github_connected(uid) is True
    creds = resolve_github_credentials(uid)
    assert creds is not None
    assert creds.auth_kind == "github_app"
    assert creds.installation_id == "778899"
    assert creds.token == "ghs_TEST_INSTALLATION_TOKEN_PHASE1"
    assert creds.login == "octocat"
    assert "token" not in creds.public_dict()
    assert resolve_github_token(uid) == "ghs_TEST_INSTALLATION_TOKEN_PHASE1"
    assert calls["n"] >= 1


def test_resolve_pat_does_not_call_app_mint(monkeypatch):
    from lumen.engine.services.integrations.connections.credentials import (
        resolve_github_credentials,
    )

    monkeypatch.setattr(
        "lumen.engine.services.integrations.connections.credentials._profile_for",
        lambda user_id: {
            "login": "alice",
            "connected": True,
            "auth_kind": "pat",
            "installation_id": "",
        },
    )
    monkeypatch.setattr(
        "lumen.engine.services.integrations.connections.token_store.load_github_token",
        lambda uid: "TEST_ONLY_PAT_NOT_A_SECRET",
    )

    def _boom(_iid):
        raise AssertionError("App mint must not run for PAT auth_kind")

    monkeypatch.setattr(
        "lumen.engine.services.integrations.github.app_auth.get_installation_token",
        _boom,
    )

    creds = resolve_github_credentials(7)
    assert creds is not None
    assert creds.auth_kind == "pat"
    assert creds.token == "TEST_ONLY_PAT_NOT_A_SECRET"


def test_provider_token_for_user_uses_credentials(monkeypatch):
    from lumen.engine.services.integrations.connections import github_provider as gp

    monkeypatch.setattr(
        "lumen.engine.services.integrations.connections.credentials.resolve_github_token",
        lambda uid: f"tok-for-{uid}",
    )
    assert gp._token_for_user(99) == "tok-for-99"


def test_read_github_token_delegates_to_credentials(monkeypatch):
    monkeypatch.setattr(
        "lumen.engine.services.integrations.connections.credentials.resolve_github_token",
        lambda uid: "delegated-token",
    )
    from lumen.bot.ui.github_connection_store import read_github_token

    assert read_github_token(1) == "delegated-token"
