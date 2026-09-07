"""Phase 1 connections: official GitHub client methods + UI catalog wiring."""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_github_client_has_official_list_user_repos():
    src = (ROOT / "lumen/engine/services/integrations/github/client.py").read_text(
        encoding="utf-8"
    )
    assert "def get_user" in src
    assert "def list_user_repos" in src
    assert "/user/repos" in src
    assert '"GET",\n                "/user"' in src or 'GET", "/user"' in src or '"/user"' in src


def test_connection_provider_registry_has_github():
    from lumen.engine.services.integrations.connections import get_provider, list_providers

    providers = list_providers()
    assert any(p.provider_id == "github" for p in providers)
    gh = get_provider("github")
    assert gh is not None
    assert gh.label_ar == "GitHub"


def test_catalog_and_signed_actions_for_connections():
    from lumen.engine.services.ui_state.catalog import is_known_action
    from lumen.bot.ui.signed_callback import encode_signed, decode_signed
    import os

    os.environ.setdefault("ENVIRONMENT", "development")
    os.environ.setdefault("CALLBACK_HMAC_SECRET", "test-secret-connections-phase1")

    for a in (
        "open_connections",
        "conn_github",
        "conn_gh_connect",
        "conn_gh_refresh",
        "conn_gh_page",
    ):
        assert is_known_action(a), a
        wire = encode_signed(a, "0", user_id=7)
        assert len(wire.encode("utf-8")) <= 64
        parsed = decode_signed(wire, user_id=7)
        assert parsed is not None and parsed[0] == a


def test_apply_open_connections_and_github():
    from lumen.engine.services.ui_state.controller import apply_action
    from lumen.engine.services.ui_state.models import EngineUiPhase, EngineUiState

    r = apply_action(EngineUiState(phase=EngineUiPhase.SETTINGS), "open_connections")
    assert r.ok
    assert r.state.phase == EngineUiPhase.CONNECTIONS

    r2 = apply_action(r.state, "conn_github")
    assert r2.ok
    assert r2.state.phase == EngineUiPhase.CONN_GITHUB

    labels = [b.text for row in r2.buttons for b in row]
    assert any("GitHub" in t or "ربط" in t or "رجوع" in t for t in labels)


def test_list_user_repos_parses_official_payload():
    from lumen.engine.services.integrations.github.client import GitHubClient

    client = GitHubClient.__new__(GitHubClient)
    client.token = "x"

    sample = [
        {
            "id": 42,
            "full_name": "acme/demo",
            "name": "demo",
            "private": True,
            "html_url": "https://github.com/acme/demo",
            "description": "x",
            "default_branch": "main",
            "language": "Python",
            "updated_at": "2026-01-01T00:00:00Z",
        }
    ]

    with patch.object(client, "request", return_value=sample):
        rows = client.list_user_repos(per_page=30, max_pages=1)
    assert len(rows) == 1
    assert rows[0]["full_name"] == "acme/demo"
    assert rows[0]["private"] is True
    assert rows[0]["id"] == 42


def test_secret_inbox_get_secret_source_exists():
    src = (ROOT / "lumen/platform/secret_inbox.py").read_text(encoding="utf-8")
    assert "def get_secret" in src


def test_conn_gh_select_in_catalog_and_signed():
    import os
    os.environ.setdefault("ENVIRONMENT", "development")
    os.environ.setdefault("CALLBACK_HMAC_SECRET", "test-secret-connections-phase1")
    from lumen.engine.services.ui_state.catalog import is_known_action
    from lumen.bot.ui.signed_callback import encode_signed, decode_signed

    assert is_known_action("conn_gh_select")
    wire = encode_signed("conn_gh_select", "12345", user_id=3)
    assert len(wire.encode("utf-8")) <= 64
    assert decode_signed(wire, user_id=3) == ("conn_gh_select", "12345")


def test_token_store_roundtrip_memory_fallback(tmp_path, monkeypatch):
    """Without Redis, save/load falls back to secret_inbox on disk."""
    import os
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("TBE_TOKEN_SECRET", "unit-test-secret-key-32b!!")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("JOB_REDIS_URL", raising=False)
    from lumen.engine.services.integrations.connections.token_store import (
        save_github_token,
        load_github_token,
    )

    assert save_github_token(99, "ghp_unitTestTokenValue1234567890")
    got = load_github_token(99)
    assert got == "ghp_unitTestTokenValue1234567890"


def test_list_user_repos_uses_page_param():
    from unittest.mock import patch
    from lumen.engine.services.integrations.github.client import GitHubClient

    client = GitHubClient.__new__(GitHubClient)
    client.token = "x"
    seen = {}

    def fake_request(method, path, **kwargs):
        seen["params"] = kwargs.get("params")
        return []

    with patch.object(client, "request", side_effect=fake_request):
        client.list_user_repos(page=3, per_page=10, max_pages=1)
    assert seen["params"]["page"] == 3
    assert seen["params"]["per_page"] == 10
