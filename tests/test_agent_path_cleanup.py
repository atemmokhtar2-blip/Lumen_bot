"""Hard tests: ghost paths stay dead; official agent path only."""
from __future__ import annotations

import os
from pathlib import Path

import pytest


def test_template_fallback_always_dead():
    from lumen.engine.services.multi_agent.fallback_template import (
        should_trigger_verified_fallback,
        build_verified_bot,
        run_verified_fallback_on_state,
    )
    assert should_trigger_verified_fallback() is False
    assert should_trigger_verified_fallback(ok=False, attempts=99) is False
    r = build_verified_bot(None, work_dir="/tmp")
    assert r["ok"] is False
    assert "disabled" in str(r.get("error") or "").lower() or "disabled" in str(r.get("engine") or "")


def test_policy_forbids_imperative_and_template():
    from lumen.engine.services.multi_agent.production_policy import (
        allow_imperative_fallback,
        allow_template_fallback,
        allow_swarm,
        allow_cline_builtin,
        policy_snapshot,
    )
    assert allow_imperative_fallback() is False
    assert allow_template_fallback() is False
    assert allow_swarm() is False
    snap = policy_snapshot()
    assert snap["allow_template_fallback"] is False
    assert snap["allow_imperative_fallback"] is False


def test_swarm_refuses_without_env(tmp_path: Path):
    os.environ.pop("MULTI_AGENT_SWARM", None)
    from lumen.engine.services.multi_agent.swarm import run_swarm
    r = run_swarm(work_dir=str(tmp_path), tasks=[{"id": "a", "title": "t"}], base_goal="goal")
    assert r["ok"] is False
    assert "swarm_disabled" in str(r.get("error") or r.get("engine") or "")


def test_swarm_enable_flag(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MULTI_AGENT_SWARM", "1")
    # re-import policy is env-based functions so ok
    from lumen.engine.services.multi_agent.production_policy import allow_swarm
    assert allow_swarm() is True
    monkeypatch.delenv("MULTI_AGENT_SWARM", raising=False)
    assert allow_swarm() is False


def test_builtin_blocked_without_allow(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CLINE_MODE", "builtin")
    monkeypatch.delenv("CLINE_ALLOW_BUILTIN", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    from lumen.engine.services.multi_agent import production_policy as pp
    assert pp.allow_cline_builtin() is False

    from lumen.engine.services.cline_runtime.executor import execute_cline_ir

    class IR:
        engine_mode = type("E", (), {"value": "cline"})()
        def to_dict(self):
            return {"goal": "x", "features": []}

    res = execute_cline_ir(IR(), tmp_path)
    assert res.ok is False
    assert res.engine in {
        "cline_builtin_blocked",
        "cline_blocked",
        "cline_agent_error",
    } or any("builtin" in str(e).lower() for e in (res.errors or []))


def test_event_wake_module_importable():
    from lumen.engine.services.multi_agent.event_wake import (
        temporal_enabled,
        schedule_wake_cron,
        signal_wake,
    )
    assert temporal_enabled() in {True, False}
    sch = schedule_wake_cron()
    assert "ok" in sch


def test_fallback_not_in_public_all():
    import lumen.engine.services.multi_agent as ma
    names = set(getattr(ma, "__all__", []) or [])
    assert "build_verified_bot" not in names
    assert "should_trigger_verified_fallback" not in names
