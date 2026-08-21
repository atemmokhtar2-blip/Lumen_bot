"""Blackboard / shared AgentState for multi-agent orchestration (Phase A)."""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class AgentStatus(str, Enum):
    PENDING = "PENDING"
    ROUTING = "ROUTING"
    PLANNING = "PLANNING"
    BUILDING = "BUILDING"
    QA = "QA"
    PASSED = "PASSED"
    FAILED = "FAILED"
    DELIVERED = "DELIVERED"


class AgentRole(str, Enum):
    ROUTER = "ROUTER"
    ARCHITECT = "ARCHITECT"
    BUILDER = "BUILDER"
    CRITIC = "CRITIC"
    ORCHESTRATOR = "ORCHESTRATOR"


@dataclass
class AgentEvent:
    role: str
    action: str
    at: float
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentState:
    """Shared blackboard — every agent reads/writes only its fields."""

    state_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    user_id: int = 0
    user_text: str = ""
    status: str = AgentStatus.PENDING.value

    # Router
    user_intent: str = ""
    capability_id: str = ""
    route_params: dict[str, Any] = field(default_factory=dict)

    # Architect
    strict_spec: dict[str, Any] = field(default_factory=dict)
    preferred_keys: list[str] = field(default_factory=list)
    spec_request: str = ""

    # Builder
    generated_path: str = ""
    build_success: bool = False
    build_errors: list[str] = field(default_factory=list)
    build_metadata: dict[str, Any] = field(default_factory=dict)

    # Critic
    qa_report: dict[str, Any] = field(default_factory=dict)
    qa_passed: bool = False

    # Delivery
    final_message: str = ""
    attempts: int = 0
    max_attempts: int = 3

    # Audit trail
    events: list[AgentEvent] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.updated_at = time.time()

    def set_status(self, status: AgentStatus | str, *, role: AgentRole | str = AgentRole.ORCHESTRATOR, detail: str = "") -> None:
        self.status = status.value if isinstance(status, AgentStatus) else str(status)
        self.record(role, f"status:{self.status}", detail)
        self.touch()

    def record(self, role: AgentRole | str, action: str, detail: str = "") -> None:
        r = role.value if isinstance(role, AgentRole) else str(role)
        self.events.append(AgentEvent(role=r, action=action, at=time.time(), detail=(detail or "")[:500]))
        self.touch()

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_id": self.state_id,
            "user_id": self.user_id,
            "user_text": self.user_text[:500],
            "status": self.status,
            "user_intent": self.user_intent,
            "capability_id": self.capability_id,
            "route_params": dict(self.route_params or {}),
            "strict_spec": dict(self.strict_spec or {}),
            "preferred_keys": list(self.preferred_keys or []),
            "spec_request": (self.spec_request or "")[:500],
            "generated_path": self.generated_path,
            "build_success": self.build_success,
            "build_errors": list(self.build_errors or [])[:20],
            "build_metadata": dict(self.build_metadata or {}),
            "qa_report": dict(self.qa_report or {}),
            "qa_passed": self.qa_passed,
            "final_message": (self.final_message or "")[:1000],
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "events": [e.to_dict() for e in self.events[-40:]],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# In-process blackboard store (Phase A). Session adapters can mirror later.
_STORE: dict[str, AgentState] = {}


def save_state(state: AgentState) -> AgentState:
    state.touch()
    _STORE[state.state_id] = state
    return state


def get_state(state_id: str) -> Optional[AgentState]:
    return _STORE.get(state_id)


def latest_for_user(user_id: int) -> Optional[AgentState]:
    items = [s for s in _STORE.values() if int(s.user_id or 0) == int(user_id or 0)]
    if not items:
        return None
    return max(items, key=lambda s: s.updated_at)
