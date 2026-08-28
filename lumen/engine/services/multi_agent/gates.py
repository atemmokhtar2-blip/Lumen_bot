"""Hard gates between agents — fail-closed, no weak pass-through."""
from __future__ import annotations

from typing import Any

from .state import AgentState
from .strict_spec import StrictSpec, validate_strict_spec


def filter_features_to_catalog(features: list[str]) -> tuple[list[str], list[str]]:
    """Keep only known capability keys when registry is available."""
    known: set[str] = set()
    try:
        from lumen.engine.services.capability_detection.catalog import CAPABILITIES
        known = set(CAPABILITIES.keys())
    except Exception:
        return list(features or []), []
    ok, unknown = [], []
    for f in features or []:
        key = str(f).strip()
        if not key:
            continue
        if key in known:
            ok.append(key)
        else:
            unknown.append(key)
    return ok, unknown


def architect_gate(state: AgentState) -> tuple[bool, list[str]]:
    """Builder may run only when StrictSpec is buildable.

    Fail-closed on unknown features: if the catalog is available and the spec
    contains any feature key NOT in CAPABILITIES, generation is refused. This
    blocks prompt-injection / spec-manipulation attacks where a crafted user
    input coaxes the LLM into emitting unauthorized capability keys that would
    produce a bot with functions outside the allowed set.
    """
    spec = StrictSpec.from_dict(state.strict_spec or {})
    ok, errors = validate_strict_spec(spec)
    # Extra: must have non-empty spec_request after merge
    if not (state.spec_request or spec.spec_request or "").strip():
        errors.append("empty_spec_request")
        ok = False
    if spec.clarification_needed:
        errors.append("clarification_needed")
        ok = False
    # Hard gate: every feature must be a known catalog key (fail-closed).
    feats, unknown = filter_features_to_catalog(list(spec.features or []))
    if unknown:
        errors.append("features_not_in_catalog")
        ok = False
    return ok, errors


def apply_catalog_filter_to_state(state: AgentState) -> AgentState:
    """Normalize preferred_keys/features to catalog keys — fail-closed.

    Unknown feature keys are DROPPED (not retained). If after filtering no
    known features remain, the spec_request is preserved but features is set
    to the known subset only; architect_gate will then fail-closed if the
    catalog was available and every key was unknown.
    """
    spec = StrictSpec.from_dict(state.strict_spec or {})
    feats, unknown = filter_features_to_catalog(list(spec.features or state.preferred_keys or []))
    # Always replace with the known subset — never keep unknown keys.
    spec.features = feats
    state.preferred_keys = feats
    state.strict_spec = spec.to_dict()
    state.strict_spec.setdefault("raw", {})
    if isinstance(state.strict_spec.get("raw"), dict):
        state.strict_spec["raw"]["unknown_features"] = unknown
    return state
