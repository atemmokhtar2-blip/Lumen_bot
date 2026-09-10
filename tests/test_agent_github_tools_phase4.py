"""Agent git tools must resolve GitHub App credentials (not only PAT params)."""
from __future__ import annotations

from pathlib import Path

import pytest


def test_resolve_prefers_explicit_token(monkeypatch):
    from lumen.engine.services.tool_runtime import executor as ex

    monkeypatch.setattr(
        "lumen.engine.services.integrations.connections.credentials.resolve_github_token",
        lambda uid: "user-cred",
    )
    assert ex._resolve_github_token_for_tool(1, {"token": "explicit"}) == "explicit"


def test_resolve_uses_user_credentials(monkeypatch):
    from lumen.engine.services.tool_runtime import executor as ex

    monkeypatch.setattr(
        "lumen.engine.services.integrations.connections.credentials.resolve_github_token",
        lambda uid: f"app-or-pat-{uid}",
    )
    assert ex._resolve_github_token_for_tool(9, {}) == "app-or-pat-9"


def test_git_push_tool_needs_auth_when_no_token(monkeypatch, tmp_path):
    from lumen.engine.services.tool_runtime import executor as ex

    repo = tmp_path / "r"
    repo.mkdir()
    monkeypatch.setattr(ex, "_resolve_github_token_for_tool", lambda *a, **k: None)
    r = ex._tool_git_push({"path": str(repo)}, user_id=1, user_data={})
    assert r.ok is False
    assert r.needs_auth is True
    assert r.tool == "git_push"


def test_git_push_tool_calls_engine_with_resolved_token(monkeypatch, tmp_path):
    from lumen.engine.services.tool_runtime import executor as ex

    repo = tmp_path / "r"
    repo.mkdir()
    seen = {}

    class _R:
        ok = True
        message = "pushed"
        url = "https://github.com/o/r"
        needs_auth = False
        data = {}

    class _SG:
        def git_push(self, path, token=None, message="update", branch=None):
            seen["path"] = path
            seen["token"] = token
            seen["message"] = message
            return _R()

    monkeypatch.setattr(ex, "_resolve_github_token_for_tool", lambda *a, **k: "resolved-tok")
    monkeypatch.setattr(
        "lumen.engine.services.git_safe_import.get_smart_git",
        lambda: _SG(),
    )
    monkeypatch.setattr(
        "lumen.engine.services.integrations.github.activity_log.record",
        lambda *a, **k: seen.setdefault("logged", True),
    )
    r = ex._tool_git_push(
        {"path": str(repo), "message": "chore: x"},
        user_id=3,
        user_data={},
    )
    assert r.ok is True
    assert seen["token"] == "resolved-tok"
    assert seen.get("logged") is True


def test_clone_uses_resolver(monkeypatch, tmp_path):
    from lumen.engine.services.tool_runtime import executor as ex

    monkeypatch.setattr(ex, "_resolve_github_token_for_tool", lambda *a, **k: "t1")
    monkeypatch.setattr(
        "lumen.engine.services.secure_exec.validate_git_https_url",
        lambda u: u,
    )

    class _Res:
        ok = True
        path = str(tmp_path)
        url = "https://github.com/o/r"
        message = "ok"
        needs_auth = False
        stderr = ""
        strategy = "https"
        attempts = 1
        file_count = 1
        meta = {}

    class _SC:
        def extract_repo_url(self, t):
            return "https://github.com/o/r"

        def smart_clone(self, *a, **k):
            self.kwargs = k
            return _Res()

    sc = _SC()
    monkeypatch.setattr(ex, "_load_smart_clone", lambda: sc)
    monkeypatch.setattr(
        "lumen.engine.services.git_operations.smart_clone.normalize_and_validate_url",
        lambda c: ("https://github.com/o/r", None),
    )
    monkeypatch.setattr(
        "lumen.engine.services.user_sandbox.get_user_sandbox",
        lambda uid, root: type("S", (), {"new_clone_dir": lambda self, label="": tmp_path})(),
    )
    r = ex._tool_clone_repo({"url": "https://github.com/o/r"}, user_id=2)
    assert r.ok is True
    assert sc.kwargs.get("token") == "t1"
    assert sc.kwargs.get("user_id") == 2
