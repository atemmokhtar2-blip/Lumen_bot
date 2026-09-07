"""Phase 2: bind selected GitHub repo → platform active_repo plane."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]


def test_bind_repo_module_exists():
    from lumen.engine.services.integrations.connections.bind_repo import (
        BindRepoResult,
        apply_bind_to_user_data,
        bind_github_repo,
    )

    assert callable(bind_github_repo)
    assert callable(apply_bind_to_user_data)


def test_bind_fails_without_url_or_token(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("TBE_TOKEN_SECRET", "unit-test-secret-key-32b!!")
    from lumen.engine.services.integrations.connections.bind_repo import bind_github_repo
    from lumen.engine.services.integrations.connections import token_store

    monkeypatch.setattr(token_store, "resolve_cached_repo", lambda *a, **k: None)
    monkeypatch.setattr(token_store, "load_github_token", lambda *a, **k: None)
    r = bind_github_repo(1, "99", slots={})
    assert r.ok is False


def test_bind_success_platform_shape(monkeypatch, tmp_path):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("TBE_TOKEN_SECRET", "unit-test-secret-key-32b!!")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))

    from lumen.engine.services.integrations.connections.bind_repo import (
        apply_bind_to_user_data,
        bind_github_repo,
    )
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

    class EP:
        path = "bot.py"

    class FakeContract:
        is_telegram_bot = True
        architecture_style = "telegram_bot"
        frameworks = ["python-telegram-bot"]
        entry_points = [EP()]
        dependencies = []

        def to_user_summary(self):
            return "demo bot"

    class FakeSandbox:
        def new_clone_dir(self, label="clone"):
            d = tmp_path / label
            d.mkdir(parents=True, exist_ok=True)
            return d

        def register_clone(self, *a, **k):
            return None

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
        lambda c: {"is_telegram_bot": True, "architecture_style": "telegram_bot"},
    )
    monkeypatch.setattr(
        "lumen.engine.services.user_sandbox.get_user_sandbox",
        lambda *a, **k: FakeSandbox(),
    )
    monkeypatch.setattr(
        "lumen.engine.services.repo_understanding.llm_explain.gather_repo_dossier",
        lambda *a, **k: {"root": str(tmp_path), "tree": "", "facts": {"files": 1}, "key_files": {}},
        raising=False,
    )

    r = bind_github_repo(42, "1001", slots={}, run_understand=True)
    assert r.ok is True
    assert r.active_repo.get("path")
    assert r.active_repo.get("url") == "https://github.com/acme/demo"
    assert r.active_repo.get("source") == "github_connection"
    assert r.active_repo.get("bound_for_grok") is True
    assert r.active_repo.get("contract")
    assert r.is_runnable is True

    ud: dict = {}
    apply_bind_to_user_data(ud, r, user=None)
    assert ud["active_repo"]["path"]
    assert ud["last_project_path"]
    assert ud["last_clone_url"] == "https://github.com/acme/demo"
    assert "pending_run" in ud
    assert ud["pending_run"]["project_path"] == r.path


def test_conn_gh_select_wired_to_platform_ui():
    src = (ROOT / "lumen/bot/ui/callback_router.py").read_text(encoding="utf-8")
    assert "apply_bind_to_user_data" in src
    assert "section_keyboard" in src
    assert "pending_run" in (ROOT / "lumen/engine/services/integrations/connections/bind_repo.py").read_text()
    assert "120.0" in src
