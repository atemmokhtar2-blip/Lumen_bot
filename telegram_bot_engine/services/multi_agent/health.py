"""Phase E — health/readiness snapshot for multi-agent subsystem."""
from __future__ import annotations

from typing import Any

from .blackboard import get_blackboard
from .circuit import get_circuit_board
from .concurrency import active_count
from .metrics import metrics_snapshot
from .registry import get_registry


def health_snapshot() -> dict[str, Any]:
    reg = get_registry()
    board = get_blackboard()
    try:
        ids = board.list_ids(limit=5)
    except Exception:
        ids = []
    return {
        "ok": True,
        "subsystem": "multi_agent",
        "agents": reg.names(),
        "active_orchestrations": active_count(),
        "recent_state_ids": ids,
        "circuits": get_circuit_board().snapshot(),
        "metrics": metrics_snapshot(),
    }
