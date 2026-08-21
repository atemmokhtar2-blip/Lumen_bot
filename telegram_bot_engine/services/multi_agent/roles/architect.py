"""Architect agent — writes StrictSpec only. Never chats with the user. Never builds."""
from __future__ import annotations

from typing import Any, Optional

from ..architect_backends import SpecBackend, default_backends, produce_strict_spec
from ..context_views import architect_view
from ..protocol import Agent
from ..state import AgentRole, AgentState, AgentStatus
from ..strict_spec import merge_spec_request, validate_strict_spec
from ..gates import apply_catalog_filter_to_state


class ArchitectAgent(Agent):
    role = AgentRole.ARCHITECT.value
    name = "architect"
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

        spec = produce_strict_spec(view, backends=backends)
        if not (spec.spec_request or "").strip():
            spec.spec_request = merge_spec_request(spec)

        state.strict_spec = spec.to_dict()
        state.spec_request = spec.spec_request
        state = apply_catalog_filter_to_state(state)
        spec = type(spec).from_dict(state.strict_spec)
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
