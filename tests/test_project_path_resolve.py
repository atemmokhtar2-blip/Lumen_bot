"""Session project path resolve + host-after-clone intent."""
from __future__ import annotations

import importlib.util
from pathlib import Path

def _load():
    path = Path("lumen/bot/project_path_resolve.py").resolve()
    spec = importlib.util.spec_from_file_location("project_path_resolve", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod

mod = _load()
resolve_session_project_path = mod.resolve_session_project_path
wants_host_after_clone = mod.wants_host_after_clone


def test_resolve_prefers_existing_active_repo(tmp_path):
    p = tmp_path / "repo"
    p.mkdir()
    got = resolve_session_project_path(
        {"project_path": str(tmp_path / "missing")},
        {"active_repo": {"path": str(p)}},
    )
    assert got == str(p.resolve())


def test_resolve_empty_when_nothing():
    assert resolve_session_project_path({}, {}) == ""


def test_wants_host_after_clone():
    assert wants_host_after_clone("اسحب البوت وشغله https://github.com/a/b")
    assert wants_host_after_clone("clone repo and deploy")
    assert not wants_host_after_clone("اسحب المستودع فقط")
