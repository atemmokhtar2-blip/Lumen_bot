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
    return {
        "count": len(events),
        "steps": [e.get("step") for e in events[-12:]],
        "last": events[-1] if events else None,
    }


__all__ = [
    "append_trajectory",
    "load_trajectory",
    "trajectory_summary",
]
