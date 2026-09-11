"""Env collection must not swallow bot tokens or Arabic chat as values."""
from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_resolve():
    path = Path("lumen/bot/project_path_resolve.py").resolve()
    spec = importlib.util.spec_from_file_location("ppr", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_path_from_pending_repo_env(tmp_path):
    mod = _load_resolve()
    p = tmp_path / "bot"
    p.mkdir()
    got = mod.resolve_session_project_path(
        {},
        {"pending_repo_env": {"path": str(p), "queue": ["RATE_LIMIT_SECONDS"]}},
    )
    assert got == str(p.resolve())


def test_readiness_allows_host_with_missing_env():
    from lumen.engine.services.integrations.connections.readiness import evaluate_readiness
    r = evaluate_readiness(
        active_repo={
            "path": "/tmp/x",
            "contract": {
                "is_telegram_bot": True,
                "env_vars": [{"name": "RATE_LIMIT_SECONDS"}, {"name": "DOWNLOAD_TIMEOUT"}],
            },
        }
    )
    assert r.can_show_host is True
    assert r.can_show_trial is True
    assert "RATE_LIMIT_SECONDS" in r.missing_env


def test_wants_host_phrase():
    mod = _load_resolve()
    assert mod.wants_host_after_clone("اسحب البوت وشغله")
