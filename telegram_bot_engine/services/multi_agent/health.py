"""Phase E — deep health / readiness for multi-agent subsystem."""
from __future__ import annotations

import os
import time
from typing import Any

from .blackboard import get_blackboard
from .circuit import get_circuit_board
from .concurrency import active_count
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
        base = os.environ.get("OUTPUT_DIR") or str((__import__("pathlib").Path.home() / ".capability_maestro"))
        p = __import__("pathlib").Path(base)
        p.mkdir(parents=True, exist_ok=True)
        probe = p / ".multi_agent_health"
        probe.write_text("ok", encoding="utf-8")
        ok = probe.is_file()
        return {"ok": ok, "path": str(p)}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__}


def _open_circuits() -> list[str]:
    snap = get_circuit_board().snapshot()
    return [k for k, v in snap.items() if (v or {}).get("state") == "open"]


def health_snapshot(*, deep: bool = True) -> dict[str, Any]:
    checks: dict[str, Any] = {
        "agents": _check_agents(),
        "active_orchestrations": active_count(),
        "circuits_open": _open_circuits(),
    }
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
    # open circuits degrade readiness but don't fail liveness
    ready = ok and len(checks["circuits_open"]) == 0

    return {
        "ok": ok,
        "ready": ready,
        "subsystem": "multi_agent",
        "checks": checks,
        "metrics": metrics_snapshot(),
        "circuits": get_circuit_board().snapshot(),
    }


def liveness() -> dict[str, Any]:
    return {"ok": True, "subsystem": "multi_agent", "live": True}


def readiness() -> dict[str, Any]:
    snap = health_snapshot(deep=True)
    return {"ok": snap["ready"], "ready": snap["ready"], "checks": snap["checks"]}
