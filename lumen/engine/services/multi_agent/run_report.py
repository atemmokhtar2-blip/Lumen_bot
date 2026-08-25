"""Phase E — durable run reports for ops (last N orchestrations)."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from .state import AgentState
from .tracing import trace_summary


def _root() -> Path:
    base = Path(os.environ.get("OUTPUT_DIR") or (Path.home() / ".lumen"))
    path = base / "multi_agent_reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


_LOCK = threading.Lock()


def write_run_report(state: AgentState) -> Path:
    """Persist a compact report JSON for this orchestration."""
    report = {
        "state_id": state.state_id,
        "user_id": state.user_id,
        "status": state.status,
        "attempts": state.attempts,
        "qa_passed": state.qa_passed,
        "build_success": state.build_success,
        "generated_path": state.generated_path,
        "selected_tool": (state.extensions or {}).get("selected_tool"),
        "architect_source": (state.strict_spec or {}).get("source"),
        "errors": list((state.qa_report or {}).get("errors") or state.build_errors or [])[:15],
        "trace": trace_summary(state),
        "events_tail": [e.to_dict() for e in (state.events or [])[-12:]],
        "written_at": time.time(),
    }
    path = _root() / f"{state.state_id}.json"
    with _LOCK:
        path.write_text(json.dumps(report, ensure_ascii=False, indent=0), encoding="utf-8")
        # prune to last 200
        files = sorted(_root().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[200:]:
            try:
                old.unlink()
            except Exception:
                pass
    return path


def recent_reports(*, limit: int = 20) -> list[dict[str, Any]]:
    files = sorted(_root().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[: max(1, min(limit, 100))]
    out = []
    for f in files:
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out
