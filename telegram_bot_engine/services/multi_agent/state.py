"""Versioned AgentState + formal status machine for the blackboard."""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


SCHEMA_VERSION = 2


class AgentStatus(str, Enum):
    PENDING = "PENDING"
    ROUTING = "ROUTING"
    PLANNING = "PLANNING"
    BUILDING = "BUILDING"
    QA = "QA"
    PASSED = "PASSED"
    FAILED = "FAILED"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class AgentRole(str, Enum):
    ROUTER = "ROUTER"
    ARCHITECT = "ARCHITECT"
    BUILDER = "BUILDER"
    CRITIC = "CRITIC"
    ORCHESTRATOR = "ORCHESTRATOR"
    TOOL = "TOOL"
    HITL = "HITL"


# Allowed transitions (extensible FSM). Unknown edges rejected.
_TRANSITIONS: dict[str, frozenset[str]] = {
    AgentStatus.PENDING.value: frozenset({
        AgentStatus.ROUTING.value, AgentStatus.CANCELLED.value, AgentStatus.FAILED.value,
    }),
    AgentStatus.ROUTING.value: frozenset({
        AgentStatus.PLANNING.value, AgentStatus.AWAITING_CONFIRMATION.value,
        AgentStatus.FAILED.value, AgentStatus.CANCELLED.value,
    }),
    AgentStatus.PLANNING.value: frozenset({
        AgentStatus.BUILDING.value, AgentStatus.FAILED.value, AgentStatus.CANCELLED.value,
    }),
    AgentStatus.BUILDING.value: frozenset({
        AgentStatus.QA.value, AgentStatus.FAILED.value, AgentStatus.CANCELLED.value,
    }),
    AgentStatus.QA.value: frozenset({
        AgentStatus.PASSED.value, AgentStatus.FAILED.value,
        AgentStatus.PLANNING.value,  # Phase C: critic → re-plan
        AgentStatus.CANCELLED.value,
    }),
    AgentStatus.PASSED.value: frozenset({AgentStatus.DELIVERED.value, AgentStatus.FAILED.value}),
    AgentStatus.FAILED.value: frozenset({
        AgentStatus.PLANNING.value,  # retry
        AgentStatus.DELIVERED.value,  # deliver failure message
        AgentStatus.CANCELLED.value,
    }),
    AgentStatus.AWAITING_CONFIRMATION.value: frozenset({
        AgentStatus.PLANNING.value,  # confirmed generate path
        AgentStatus.ROUTING.value,   # re-route after confirm for tools
        AgentStatus.FAILED.value,
        AgentStatus.CANCELLED.value,
        AgentStatus.DELIVERED.value,
    }),
    AgentStatus.DELIVERED.value: frozenset(),
    AgentStatus.CANCELLED.value: frozenset(),
}


class InvalidTransition(ValueError):
    pass


@dataclass
class AgentEvent:
    role: str
    action: str
    at: float
    detail: str = ""
    from_status: str = ""
    to_status: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AgentEvent":
        return cls(
            role=str(d.get("role") or ""),
            action=str(d.get("action") or ""),
            at=float(d.get("at") or time.time()),
            detail=str(d.get("detail") or "")[:500],
            from_status=str(d.get("from_status") or ""),
            to_status=str(d.get("to_status") or ""),
        )


@dataclass
class AgentState:
    """Shared blackboard document — serializable end-to-end."""

    schema_version: int = SCHEMA_VERSION
    state_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    user_id: int = 0
    user_text: str = ""
    status: str = AgentStatus.PENDING.value

    user_intent: str = ""
    capability_id: str = ""
    route_params: dict[str, Any] = field(default_factory=dict)

    strict_spec: dict[str, Any] = field(default_factory=dict)
    preferred_keys: list[str] = field(default_factory=list)
    spec_request: str = ""

    generated_path: str = ""
    build_success: bool = False
    build_errors: list[str] = field(default_factory=list)
    build_metadata: dict[str, Any] = field(default_factory=dict)

    qa_report: dict[str, Any] = field(default_factory=dict)
    qa_passed: bool = False

    final_message: str = ""
    attempts: int = 0
    max_attempts: int = 3

    # Extensibility bag for future agents (hosting, billing, git, …)
    extensions: dict[str, Any] = field(default_factory=dict)

    events: list[AgentEvent] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.updated_at = time.time()

    def record(
        self,
        role: AgentRole | str,
        action: str,
        detail: str = "",
        *,
        from_status: str = "",
        to_status: str = "",
    ) -> None:
        r = role.value if isinstance(role, AgentRole) else str(role)
        self.events.append(
            AgentEvent(
                role=r,
                action=action,
                at=time.time(),
                detail=(detail or "")[:500],
                from_status=from_status,
                to_status=to_status,
            )
        )
        # Cap event log for scalability
        if len(self.events) > 200:
            self.events = self.events[-150:]
        self.touch()

    def transition(self, new_status: AgentStatus | str, *, role: AgentRole | str = AgentRole.ORCHESTRATOR, detail: str = "", force: bool = False) -> None:
        target = new_status.value if isinstance(new_status, AgentStatus) else str(new_status)
        current = self.status
        if current == target:
            return
        allowed = _TRANSITIONS.get(current, frozenset())
        if not force and target not in allowed:
            raise InvalidTransition(f"{current} -> {target} not allowed")
        self.record(role, f"transition:{current}->{target}", detail, from_status=current, to_status=target)
        self.status = target
        self.touch()

    def set_status(self, status: AgentStatus | str, *, role: AgentRole | str = AgentRole.ORCHESTRATOR, detail: str = "") -> None:
        """Backward-compatible: prefer transition(); falls back to force on illegal edge."""
        try:
            self.transition(status, role=role, detail=detail, force=False)
        except InvalidTransition:
            self.transition(status, role=role, detail=f"forced:{detail}", force=True)

    def to_dict(self) -> dict[str, Any]:
        # Never embed non-JSON objects
        meta = {k: v for k, v in (self.build_metadata or {}).items() if not str(k).startswith("_")}
        return {
            "schema_version": self.schema_version,
            "state_id": self.state_id,
            "user_id": self.user_id,
            "user_text": (self.user_text or "")[:500],
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
            "build_metadata": meta,
            "qa_report": dict(self.qa_report or {}),
            "qa_passed": self.qa_passed,
            "final_message": (self.final_message or "")[:1000],
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "extensions": dict(self.extensions or {}),
            "events": [e.to_dict() for e in self.events[-40:]],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AgentState":
        events = [AgentEvent.from_dict(e) for e in (d.get("events") or []) if isinstance(e, dict)]
        return cls(
            schema_version=int(d.get("schema_version") or SCHEMA_VERSION),
            state_id=str(d.get("state_id") or uuid.uuid4().hex[:16]),
            user_id=int(d.get("user_id") or 0),
            user_text=str(d.get("user_text") or ""),
            status=str(d.get("status") or AgentStatus.PENDING.value),
            user_intent=str(d.get("user_intent") or ""),
            capability_id=str(d.get("capability_id") or ""),
            route_params=dict(d.get("route_params") or {}),
            strict_spec=dict(d.get("strict_spec") or {}),
            preferred_keys=list(d.get("preferred_keys") or []),
            spec_request=str(d.get("spec_request") or ""),
            generated_path=str(d.get("generated_path") or ""),
            build_success=bool(d.get("build_success")),
            build_errors=list(d.get("build_errors") or []),
            build_metadata=dict(d.get("build_metadata") or {}),
            qa_report=dict(d.get("qa_report") or {}),
            qa_passed=bool(d.get("qa_passed")),
            final_message=str(d.get("final_message") or ""),
            attempts=int(d.get("attempts") or 0),
            max_attempts=int(d.get("max_attempts") or 3),
            extensions=dict(d.get("extensions") or {}),
            events=events,
            created_at=float(d.get("created_at") or time.time()),
            updated_at=float(d.get("updated_at") or time.time()),
        )
