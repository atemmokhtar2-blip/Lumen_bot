"""Production durable workflow for multi-agent generation.

Guarantees:
  - Every agent step is journaled (file + Redis stream when available)
  - Crash mid-loop → resume_from_checkpoint() continues from last completed step
  - Journal survives process restart (OUTPUT_DIR/workflow_journal/)

This is the operational engine; Temporal/Prefect adapters in workflow_engine.py
remain optional workers that can consume the same checkpoints.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_STEPS_ORDER = ("start", "architect", "builder", "critic", "deliver", "done")


@dataclass
class JournalEntry:
    workflow_id: str
    state_id: str
    step: str
    status: str
    user_id: int = 0
    description: str = ""
    attempts: int = 0
    payload: dict[str, Any] = field(default_factory=dict)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "state_id": self.state_id,
            "step": self.step,
            "status": self.status,
            "user_id": self.user_id,
            "description": self.description[:2000],
            "attempts": self.attempts,
            "payload": self.payload,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "JournalEntry":
        return cls(
            workflow_id=str(d.get("workflow_id") or ""),
            state_id=str(d.get("state_id") or ""),
            step=str(d.get("step") or "start"),
            status=str(d.get("status") or "running"),
            user_id=int(d.get("user_id") or 0),
            description=str(d.get("description") or ""),
            attempts=int(d.get("attempts") or 0),
            payload=dict(d.get("payload") or {}),
            updated_at=float(d.get("updated_at") or time.time()),
        )


class DurableWorkflowJournal:
    """Append-only + latest-pointer journal on disk; optional Redis mirror."""

    def __init__(self, root: Path | None = None) -> None:
        base = Path(
            root
            or os.environ.get("TBE_WORKFLOW_JOURNAL_DIR")
            or (Path(os.environ.get("OUTPUT_DIR") or (Path.home() / ".lumen")) / "workflow_journal")
        )
        self.root = base
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, workflow_id: str) -> Path:
        safe = "".join(c for c in workflow_id if c.isalnum() or c in "-_")[:64]
        return self.root / f"{safe}.json"

    def _index_path(self) -> Path:
        return self.root / "_index.json"

    def write(self, entry: JournalEntry) -> JournalEntry:
        entry.updated_at = time.time()
        with self._lock:
            path = self._path(entry.workflow_id)
            path.write_text(json.dumps(entry.to_dict(), ensure_ascii=False, indent=0), encoding="utf-8")
            # index by state_id for resume lookup
            idx: dict = {}
            if self._index_path().exists():
                try:
                    idx = json.loads(self._index_path().read_text(encoding="utf-8") or "{}")
                except Exception:
                    idx = {}
            idx[entry.state_id] = {
                "workflow_id": entry.workflow_id,
                "step": entry.step,
                "status": entry.status,
                "updated_at": entry.updated_at,
            }
            if len(idx) > 2000:
                ordered = sorted(idx.items(), key=lambda kv: float(kv[1].get("updated_at") or 0), reverse=True)[:1000]
                idx = dict(ordered)
            self._index_path().write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")
        # Redis mirror
        try:
            from .redis_board import append_agent_event, redis_board_enabled
            if redis_board_enabled():
                append_agent_event(
                    entry.state_id,
                    f"workflow:{entry.step}",
                    {"workflow_id": entry.workflow_id, "status": entry.status},
                )
        except Exception:
            pass
        # workflow_engine checkpoint
        try:
            from .workflow_engine import get_workflow_engine
            eng = get_workflow_engine()
            eng.checkpoint(
                entry.workflow_id,
                state_id=entry.state_id,
                step=entry.step,
                status=entry.status,
                payload=entry.payload,
            )
        except Exception:
            pass
        return entry

    def get(self, workflow_id: str) -> Optional[JournalEntry]:
        path = self._path(workflow_id)
        if not path.exists():
            return None
        try:
            return JournalEntry.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return None

    def get_by_state(self, state_id: str) -> Optional[JournalEntry]:
        with self._lock:
            if not self._index_path().exists():
                return None
            try:
                idx = json.loads(self._index_path().read_text(encoding="utf-8") or "{}")
            except Exception:
                return None
            meta = idx.get(state_id)
            if not meta:
                return None
            return self.get(str(meta.get("workflow_id") or ""))

    def list_resumable(self, *, limit: int = 50) -> list[JournalEntry]:
        with self._lock:
            if not self._index_path().exists():
                return []
            try:
                idx = json.loads(self._index_path().read_text(encoding="utf-8") or "{}")
            except Exception:
                return []
            out: list[JournalEntry] = []
            for sid, meta in sorted(
                idx.items(),
                key=lambda kv: float(kv[1].get("updated_at") or 0),
                reverse=True,
            ):
                if str(meta.get("status") or "") not in {"running", "paused", "building", "planning"}:
                    continue
                e = self.get(str(meta.get("workflow_id") or ""))
                if e:
                    out.append(e)
                if len(out) >= limit:
                    break
            return out


_JOURNAL: DurableWorkflowJournal | None = None
_JLOCK = threading.Lock()


def get_journal() -> DurableWorkflowJournal:
    global _JOURNAL
    with _JLOCK:
        if _JOURNAL is None:
            _JOURNAL = DurableWorkflowJournal()
        return _JOURNAL


def next_step_after(step: str) -> str:
    step = (step or "start").strip().lower()
    try:
        i = _STEPS_ORDER.index(step)
    except ValueError:
        return "architect"
    if i + 1 >= len(_STEPS_ORDER):
        return "done"
    return _STEPS_ORDER[i + 1]


def resume_generate(
    state_id: str,
    *,
    board=None,
) -> Any:
    """Reload AgentState + journal and continue orchestrate from last step.

    Returns the final AgentState (or None if nothing to resume).
    """
    from .blackboard import get_blackboard
    from .orchestrator import MultiAgentOrchestrator
    from .state import AgentState, AgentStatus

    board = board or get_blackboard()
    state = board.get(state_id)
    if state is None:
        logger.warning("resume: state not found id=%s", state_id)
        return None

    journal = get_journal()
    entry = journal.get_by_state(state_id)
    last_step = entry.step if entry else "start"
    if state.status in {AgentStatus.COMPLETED.value, "completed", AgentStatus.DELIVERED.value if hasattr(AgentStatus, "DELIVERED") else "delivered"}:
        logger.info("resume: already completed id=%s", state_id)
        return state

    # Mark as running again
    try:
        state.status = AgentStatus.BUILDING.value if hasattr(AgentStatus, "BUILDING") else "building"
    except Exception:
        state.status = "building"
    board.put(state)

    if entry:
        journal.write(
            JournalEntry(
                workflow_id=entry.workflow_id,
                state_id=state_id,
                step=last_step,
                status="resuming",
                user_id=int(state.user_id or 0),
                description=str(getattr(state, "description", "") or ""),
                attempts=int(state.attempts or 0),
                payload={"resumed_from": last_step},
            )
        )

    orch = MultiAgentOrchestrator(board=board)
    from_step = next_step_after(last_step) if last_step not in {"start", ""} else "architect"
    return orch.resume_run(state, from_step=from_step)
