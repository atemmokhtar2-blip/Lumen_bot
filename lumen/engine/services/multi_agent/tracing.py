"""Phase E — correlation tracing across agent pipeline."""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from .state import AgentState


@dataclass
class Span:
    name: str
    started_at: float
    ended_at: float = 0.0
    ok: bool = True
    detail: str = ""

    def close(self, *, ok: bool = True, detail: str = "") -> None:
        self.ended_at = time.time()
        self.ok = ok
        self.detail = (detail or "")[:300]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["duration_ms"] = int(max(0.0, (self.ended_at or time.time()) - self.started_at) * 1000)
        return d


def ensure_trace(state: AgentState) -> str:
    """Attach correlation_id + span list on state.extensions['trace']."""
    ext = state.extensions
    tr = ext.get("trace")
    if not isinstance(tr, dict):
        tr = {
            "correlation_id": uuid.uuid4().hex[:16],
            "spans": [],
        }
        ext["trace"] = tr
    elif not tr.get("correlation_id"):
        tr["correlation_id"] = uuid.uuid4().hex[:16]
    return str(tr["correlation_id"])


def start_span(state: AgentState, name: str) -> Span:
    ensure_trace(state)
    span = Span(name=name, started_at=time.time())
    spans = state.extensions["trace"].setdefault("spans", [])
    spans.append(span.to_dict())  # placeholder; closed span will replace
    # Keep open spans on the side
    open_map = state.extensions["trace"].setdefault("_open", {})
    open_map[name] = span
    return span


def end_span(state: AgentState, name: str, *, ok: bool = True, detail: str = "") -> None:
    tr = state.extensions.get("trace") or {}
    open_map = tr.get("_open") or {}
    span = open_map.pop(name, None)
    if span is None:
        span = Span(name=name, started_at=time.time())
    span.close(ok=ok, detail=detail)
    spans = tr.setdefault("spans", [])
    # replace last matching open name or append
    for i in range(len(spans) - 1, -1, -1):
        if spans[i].get("name") == name and not spans[i].get("ended_at"):
            spans[i] = span.to_dict()
            break
    else:
        spans.append(span.to_dict())
    # cap
    if len(spans) > 80:
        tr["spans"] = spans[-60:]
    # strip non-serializable open map for board persistence
    if not open_map:
        tr.pop("_open", None)


def trace_summary(state: AgentState) -> dict[str, Any]:
    tr = dict((state.extensions or {}).get("trace") or {})
    tr.pop("_open", None)
    return tr
