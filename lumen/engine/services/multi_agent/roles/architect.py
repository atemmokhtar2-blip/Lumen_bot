"""Planner role (Architect) — Phase A: produces StrictSpec plan for the Worker.

Architect agent — writes StrictSpec only. Never chats with the user. Never builds."""
from __future__ import annotations

from typing import Any, Optional

from ..architect_backends import SpecBackend, default_backends, produce_strict_spec
from ..context_views import architect_view
from ..protocol import Agent
from ..state import AgentRole, AgentState, AgentStatus
from ..strict_spec import merge_spec_request, validate_strict_spec
from ..gates import apply_catalog_filter_to_state
from ..repair import build_repair_directive, apply_deterministic_repair, spec_hash, record_repair_history


class ArchitectAgent(Agent):
    role = AgentRole.ARCHITECT.value
    name = "architect"
    role_alias = "planner"
    order = 20

    def __init__(self, backends: list[SpecBackend] | None = None) -> None:
        self.backends = backends  # None → default chain

    def run(self, state: AgentState, *, context: Optional[dict[str, Any]] = None) -> AgentState:
        state.transition(AgentStatus.PLANNING, role=AgentRole.ARCHITECT)
        view = architect_view(state)

        # Optional inject of custom backends via context (tests / future hosts)
        backends = None
        if context and context.get("spec_backends"):
            backends = list(context["spec_backends"])
        elif self.backends is not None:
            backends = self.backends

        # Phase C: build structured repair directive when prior QA failed
        directive = None
        if state.qa_report and not state.qa_passed and int(state.attempts or 0) >= 1:
            directive = build_repair_directive(state)
            state.extensions["last_repair"] = directive.to_dict()
            view = {**view, "repair_directive": directive.to_dict()}

        spec = produce_strict_spec(view, backends=backends)
        if not (spec.spec_request or "").strip():
            spec.spec_request = merge_spec_request(spec)

        # Always apply deterministic repair mutations when we have a directive
        if directive is not None:
            spec = apply_deterministic_repair(spec, directive)
            state.record(AgentRole.ARCHITECT, "repair_applied", f"actions={len(directive.actions)}")

        state.strict_spec = spec.to_dict()
        state.spec_request = spec.spec_request
        state = apply_catalog_filter_to_state(state)
        spec = type(spec).from_dict(state.strict_spec)
        if directive is not None:
            record_repair_history(state, directive, spec_hash(spec))
        # preferred_keys for Builder = features from contract
        if spec.features:
            state.preferred_keys = list(spec.features)
        state.extensions["architect"] = {
            "source": spec.source,
            "model": spec.model,
            "confidence": spec.confidence,
            "buildable": spec.is_buildable(),
            "backend_chain": (spec.raw or {}).get("backend_chain"),
        }

        ok, errors = validate_strict_spec(spec)
        state.record(
            AgentRole.ARCHITECT,
            "spec_written",
            f"source={spec.source} buildable={ok} conf={spec.confidence:.2f}",
        )
        if not ok and spec.clarification_needed:
            # Phase B: mark but still allow Builder if caller forced generate;
            # store questions for delivery layer
            state.extensions["architect"]["validation_errors"] = errors
        return state


def run_architect(state: AgentState) -> AgentState:
    return ArchitectAgent().run(state)
