"""Health / readiness for multi-agent subsystem (slim — no circuit/concurrency)."""
from __future__ import annotations

import os
import time
from typing import Any

from .blackboard import get_blackboard
from .metrics import metrics_snapshot
from .registry import get_registry
from .state import AgentState


def _check_blackboard() -> dict[str, Any]:
    t0 = time.time()
    try:
        board = get_blackboard()
        probe = AgentState(user_id=0, user_text="__health_probe__")
        probe.extensions["health_probe"] = True
        board.put(probe)
        got = board.get(probe.state_id)
        ok = got is not None and got.state_id == probe.state_id
        return {"ok": ok, "latency_ms": int((time.time() - t0) * 1000)}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "latency_ms": int((time.time() - t0) * 1000)}


def _check_agents() -> dict[str, Any]:
    required = {"router", "architect", "builder", "critic"}
    names = set(get_registry().names())
    missing = sorted(required - names)
    return {"ok": not missing, "agents": sorted(names), "missing": missing}


def _check_output_dir() -> dict[str, Any]:
    try:
        base = os.environ.get("OUTPUT_DIR") or str((__import__("pathlib").Path.home() / ".lumen"))
        p = __import__("pathlib").Path(base)
        p.mkdir(parents=True, exist_ok=True)
        probe = p / ".multi_agent_health"
        probe.write_text("ok", encoding="utf-8")
        return {"ok": probe.is_file(), "path": str(p)}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__}


def health_snapshot(*, deep: bool = True) -> dict[str, Any]:
    checks: dict[str, Any] = {"agents": _check_agents()}
    if deep:
        checks["blackboard"] = _check_blackboard()
        checks["output_dir"] = _check_output_dir()
    try:
        from .run_report import recent_reports
        checks["recent_reports"] = len(recent_reports(limit=5))
    except Exception:
        checks["recent_reports"] = 0
    ok = bool(checks["agents"].get("ok"))
    if deep:
        ok = ok and bool(checks.get("blackboard", {}).get("ok")) and bool(checks.get("output_dir", {}).get("ok"))
    return {
        "ok": ok,
        "ready": ok,
        "subsystem": "multi_agent",
        "checks": checks,
        "metrics": metrics_snapshot(),
        "durability": "langgraph_sqlite + temporal_optional",
    }


def liveness() -> dict[str, Any]:
    return {"ok": True, "subsystem": "multi_agent", "live": True}


def readiness() -> dict[str, Any]:
    snap = health_snapshot(deep=True)
    return {"ok": snap["ready"], "ready": snap["ready"], "checks": snap["checks"]}
