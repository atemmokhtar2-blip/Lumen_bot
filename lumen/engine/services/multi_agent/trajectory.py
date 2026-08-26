"""Trajectory store — systematic attempt logging for Phase A self-correction.

Persists Observe → Critique → Repair steps per state_id so the orchestrator
and ops can audit failed paths (not just the final run_report).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from .state import AgentState

logger = logging.getLogger(__name__)
_LOCK = threading.Lock()


def _root() -> Path:
    base = Path(os.environ.get("OUTPUT_DIR") or (Path.home() / ".lumen"))
    path = base / "multi_agent_trajectories"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _path_for(state_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (state_id or "unknown"))[:80]
    return _root() / f"{safe}.jsonl"


def append_trajectory(
    state: AgentState,
    *,
    step: str,
    role: str = "",
    ok: bool | None = None,
    detail: str = "",
    payload: dict[str, Any] | None = None,
) -> None:
    """Append one trajectory event (JSONL). Best-effort; never raises to callers."""
    try:
        event = {
            "ts": time.time(),
            "state_id": state.state_id,
            "user_id": int(state.user_id or 0),
            "step": step,
            "role": role or "",
            "status": state.status,
            "attempts": int(state.attempts or 0),
            "ok": ok,
            "detail": (detail or "")[:500],
            "build_success": bool(state.build_success),
            "qa_passed": bool(state.qa_passed),
            "generated_path": (state.generated_path or "")[:300],
            "payload": payload or {},
        }
        path = _path_for(state.state_id)
        line = json.dumps(event, ensure_ascii=False) + "\n"
        with _LOCK:
            with path.open("a", encoding="utf-8") as f:
                f.write(line)
        # mirror on state for in-process consumers
        traj = list((state.extensions or {}).get("trajectory") or [])
        traj.append({k: event[k] for k in ("ts", "step", "role", "ok", "detail", "attempts")})
        state.extensions["trajectory"] = traj[-40:]
    except Exception as exc:
        logger.debug("trajectory append failed: %s", type(exc).__name__)


def load_trajectory(state_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
    path = _path_for(state_id)
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for ln in lines[-max(1, min(limit, 500)):]:
            try:
                out.append(json.loads(ln))
            except Exception:
                continue
    except Exception:
        return []
    return out


def trajectory_summary(state: AgentState) -> dict[str, Any]:
    events = list((state.extensions or {}).get("trajectory") or [])
    if not events:
        events = load_trajectory(state.state_id, limit=40)
    fails = [e for e in events if e.get("ok") is False]
    return {
        "count": len(events),
        "steps": [e.get("step") for e in events[-12:]],
        "last": events[-1] if events else None,
        "fail_count": len(fails),
        "fail_steps": [e.get("step") for e in fails[-8:]],
    }


def analyze_trajectory(state_id: str = "", *, limit: int = 200) -> dict[str, Any]:
    """Aggregate Observe→Critique→Fix stats for one run (Phase A self-correction analytics)."""
    events = load_trajectory(state_id, limit=max(1, min(limit, 500))) if state_id else []
    by_step: dict[str, dict[str, int]] = {}
    fails: list[dict[str, Any]] = []
    for e in events:
        step = str(e.get("step") or "unknown")
        bucket = by_step.setdefault(step, {"total": 0, "ok": 0, "fail": 0})
        bucket["total"] += 1
        if e.get("ok") is False:
            bucket["fail"] += 1
            fails.append(
                {
                    "step": step,
                    "role": e.get("role"),
                    "detail": e.get("detail"),
                    "attempts": e.get("attempts"),
                    "ts": e.get("ts"),
                }
            )
        elif e.get("ok") is True:
            bucket["ok"] += 1
    return {
        "state_id": state_id,
        "event_count": len(events),
        "by_step": by_step,
        "failures": fails[-30:],
        "failure_rate": round(len(fails) / max(1, len(events)), 3),
    }


def failure_board(*, limit: int = 50) -> list[dict[str, Any]]:
    """Ops board: recent failed trajectories across runs (not a web UI — Phase A data surface)."""
    root = _root()
    files = sorted(root.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[
        : max(1, min(limit, 200))
    ]
    board: list[dict[str, Any]] = []
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()[-40:]
            events = [json.loads(x) for x in lines if x.strip()]
        except Exception:
            continue
        fails = [e for e in events if e.get("ok") is False]
        last = events[-1] if events else {}
        if not fails and last.get("qa_passed") is not False and last.get("build_success") is not False:
            # skip clean successes on the board
            if last.get("ok") is True or last.get("qa_passed") is True:
                continue
        analysis = {
            "state_id": last.get("state_id") or path.stem,
            "user_id": last.get("user_id"),
            "last_step": last.get("step"),
            "last_status": last.get("status"),
            "attempts": last.get("attempts"),
            "fail_count": len(fails),
            "fail_steps": [e.get("step") for e in fails[-6:]],
            "qa_passed": last.get("qa_passed"),
            "build_success": last.get("build_success"),
            "updated_ts": last.get("ts") or path.stat().st_mtime,
        }
        if analysis["fail_count"] or analysis["qa_passed"] is False or analysis["build_success"] is False:
            board.append(analysis)
    board.sort(key=lambda x: float(x.get("updated_ts") or 0), reverse=True)
    return board[: max(1, min(limit, 100))]


__all__ = [
    "append_trajectory",
    "load_trajectory",
    "trajectory_summary",
    "analyze_trajectory",
    "failure_board",
]
