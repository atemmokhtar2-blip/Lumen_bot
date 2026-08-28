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


def test_api_security_require_openat2_defined_and_true(monkeypatch):
    monkeypatch.delenv("TBE_ALLOW_WEAK_PATH_OPEN", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    import importlib.util
    from pathlib import Path as P
    path = P("lumen/api/security.py").resolve()
    spec = importlib.util.spec_from_file_location("lumen_api_security_under_test", path)
    sec = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(sec)
    assert callable(sec._require_openat2)
    assert sec._require_openat2() is True


def test_open_beneath_defaults_require_openat2():
    import inspect
    from lumen.engine.services.linux_path_open import open_beneath, verify_dir_beneath
    assert inspect.signature(open_beneath).parameters["require_openat2"].default is True
    assert inspect.signature(verify_dir_beneath).parameters["require_openat2"].default is True


def test_live_runner_allow_local_requires_not_strong(monkeypatch):
    """Even if allow_local leaked True with strong isolation, runner must not host-run."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_MULTI_TENANT", "1")
    from lumen.engine.services.isolation_policy import decide_isolation
    d = decide_isolation()
    # Policy: multi-tenant never allow_local without dual gate
    assert d.allow_local is False or d.require_strong_isolation is False
