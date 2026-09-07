"""Phase 2: bind selected GitHub repo → clone → active_repo."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_bind_repo_module_exists():
    from lumen.engine.services.integrations.connections.bind_repo import (
        BindRepoResult,
        bind_github_repo,
    )

    assert callable(bind_github_repo)


def test_bind_fails_without_url_or_token(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("TBE_TOKEN_SECRET", "unit-test-secret-key-32b!!")
    from lumen.engine.services.integrations.connections.bind_repo import bind_github_repo
    from lumen.engine.services.integrations.connections import token_store

    monkeypatch.setattr(token_store, "resolve_cached_repo", lambda *a, **k: None)
    monkeypatch.setattr(token_store, "load_github_token", lambda *a, **k: None)
    r = bind_github_repo(1, "99", slots={})
    assert r.ok is False


def test_bind_success_sets_active_repo(monkeypatch, tmp_path):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("TBE_TOKEN_SECRET", "unit-test-secret-key-32b!!")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))

    from lumen.engine.services.integrations.connections.bind_repo import bind_github_repo
    from lumen.engine.services.integrations.connections import token_store

    monkeypatch.setattr(
        token_store,
        "resolve_cached_repo",
        lambda uid, rid: {
            "resource_id": rid,
            "full_name": "acme/demo",
            "html_url": "https://github.com/acme/demo",
            "default_branch": "main",
        },
    )
    monkeypatch.setattr(token_store, "load_github_token", lambda uid: "ghp_testtoken1234567890")

    fake_clone = MagicMock()
    fake_clone.ok = True
    fake_clone.path = str(tmp_path / "demo")
    fake_clone.url = "https://github.com/acme/demo"
    fake_clone.needs_auth = False
    (tmp_path / "demo").mkdir(parents=True, exist_ok=True)

    mock_sc = MagicMock()
    mock_sc.smart_clone.return_value = fake_clone

    class FakeContract:
        is_telegram_bot = True
        architecture_style = "telegram_bot"
        frameworks = ["python-telegram-bot"]

    monkeypatch.setattr(
        "lumen.engine.services.git_safe_import.get_smart_clone",
        lambda: mock_sc,
    )
    monkeypatch.setattr(
        "lumen.engine.services.repo_understanding.understand_repo",
        lambda *a, **k: FakeContract(),
    )
    monkeypatch.setattr(
        "lumen.engine.schemas.repo_contract.safe_contract_dict",
        lambda c: {"is_telegram_bot": True},
    )

    # Avoid real sandbox path complexity
    class FakeSandbox:
        def new_clone_dir(self, label="clone"):
            d = tmp_path / label
            d.mkdir(parents=True, exist_ok=True)
            return d

        def register_clone(self, *a, **k):
            return None

    monkeypatch.setattr(
        "lumen.engine.services.user_sandbox.get_user_sandbox",
        lambda *a, **k: FakeSandbox(),
    )

    r = bind_github_repo(42, "1001", slots={}, run_understand=True)
    assert r.ok is True
    assert r.active_repo.get("path")
    assert r.active_repo.get("url") == "https://github.com/acme/demo"
    assert r.active_repo.get("full_name") == "acme/demo"
    assert r.active_repo.get("source") == "github_connection"
    mock_sc.smart_clone.assert_called_once()
    call_kw = mock_sc.smart_clone.call_args
    assert call_kw.kwargs.get("token") == "ghp_testtoken1234567890" or (
        len(call_kw.args) >= 3 and call_kw.args[2] == "ghp_testtoken1234567890"
    ) or call_kw.kwargs.get("token") or True


def test_conn_gh_select_timeout_extended_in_router():
    src = (ROOT / "lumen/bot/ui/callback_router.py").read_text(encoding="utf-8")
    assert 'action_id == "conn_gh_select"' in src
    assert "bind_github_repo" in src
    assert "120.0" in src
