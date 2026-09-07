"""Hard gates between agents — fail-closed, no weak pass-through."""
from __future__ import annotations

from typing import Any

from .state import AgentState
from .strict_spec import StrictSpec, validate_strict_spec


def filter_features_to_catalog(features: list[str]) -> tuple[list[str], list[str]]:
    """Catalog removed with deterministic engine — pass features through."""
    ok = [str(f).strip() for f in (features or []) if str(f).strip()]
    return ok, []


def architect_gate(state: AgentState) -> tuple[bool, list[str]]:
    """Builder may run only when StrictSpec is buildable."""
    spec = StrictSpec.from_dict(state.strict_spec or {})
    ok, errors = validate_strict_spec(spec)
    if not (state.spec_request or spec.spec_request or "").strip():
        errors.append("empty_spec_request")
        ok = False
    if spec.clarification_needed:
        errors.append("clarification_needed")
        ok = False
    return ok, errors


def apply_catalog_filter_to_state(state: AgentState) -> AgentState:
    """No-op identity (deterministic catalog deleted)."""
    return state
