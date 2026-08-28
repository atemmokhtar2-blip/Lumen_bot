"""Security gates: no host-local fallback in multi-tenant; openat2 in prod paths."""
from __future__ import annotations

from pathlib import Path

import pytest


def test_api_app_does_not_force_local_fallback_on():
    """Regression: app.py must never default LOCAL_FALLBACK=1 (RCE when no sandbox)."""
    src = Path("lumen/api/app.py").read_text(encoding="utf-8")
    assert 'TBE_LOCAL_FALLBACK_WHEN_NO_DOCKER"] = "1"' not in src
    assert 'TBE_LOCAL_FALLBACK_WHEN_NO_DOCKER"] = "0"' in src


def test_decide_isolation_ignores_local_fallback_in_multi_tenant(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_MULTI_TENANT", "1")
    monkeypatch.setenv("TBE_LOCAL_FALLBACK_WHEN_NO_DOCKER", "1")
    monkeypatch.delenv("TBE_ALLOW_LOCAL_PROCESS", raising=False)
    monkeypatch.delenv("TBE_FORCE_LOCAL_PROCESS", raising=False)
    # Re-import path: decide_isolation reads env at call time
    from lumen.engine.services.isolation_policy import decide_isolation

    d = decide_isolation()
    assert d.require_strong_isolation is True
    assert d.allow_local is False


def test_decide_isolation_dual_gate_still_allows_local(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_MULTI_TENANT", "1")
    monkeypatch.setenv("TBE_ALLOW_LOCAL_PROCESS", "1")
    monkeypatch.setenv("TBE_FORCE_LOCAL_PROCESS", "1")
    from lumen.engine.services.isolation_policy import decide_isolation

    d = decide_isolation()
    assert d.allow_local is True
    assert d.require_strong_isolation is False


def test_safe_fs_requires_openat2_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_MULTI_TENANT", "1")
    monkeypatch.delenv("TBE_REQUIRE_OPENAT2", raising=False)
    from lumen.engine.services import safe_fs

    assert safe_fs._require_openat2_for_paths() is True


def test_safe_fs_openat2_optional_in_dev(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("TBE_MULTI_TENANT", "0")
    monkeypatch.delenv("TBE_REQUIRE_OPENAT2", raising=False)
    from lumen.engine.services import safe_fs

    assert safe_fs._require_openat2_for_paths() is False


def test_gemini_forces_confirmation_on_high_risk_actions():
    from lumen.engine.services import gemini_client as gc

    # Simulate model trying to skip confirmation
    result = {
        "answer": "ok",
        "action": {"name": "clone_repo", "requires_confirmation": False, "evil": 1},
        "translation": {
            "purpose": "x",
            "features_requested": [],
            "flows": [],
            "strict_spec": False,
            "confidence": 0.5,
            "clarification_needed": False,
            "clarification_questions": [],
            "spec_request": "",
        },
    }
    out = gc._normalize(result)  # type: ignore[attr-defined]
    assert out["action"]["name"] == "clone_repo"
    assert out["action"]["requires_confirmation"] is True
    assert "evil" not in out["action"]


def test_gemini_rejects_unknown_action_name():
    from lumen.engine.services import gemini_client as gc

    result = {
        "answer": "ok",
        "action": {"name": "delete_all_servers", "requires_confirmation": False},
        "translation": {
            "purpose": "",
            "features_requested": [],
            "flows": [],
            "strict_spec": False,
            "confidence": 0.0,
            "clarification_needed": True,
            "clarification_questions": [],
            "spec_request": "",
        },
    }
    out = gc._normalize(result)  # type: ignore[attr-defined]
    assert out["action"]["name"] == ""
