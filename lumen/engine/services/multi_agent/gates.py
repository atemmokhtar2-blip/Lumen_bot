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
    """Builder may run only when StrictSpec is buildable."""
    spec = StrictSpec.from_dict(state.strict_spec or {})
    ok, errors = validate_strict_spec(spec)
    # Extra: must have non-empty spec_request after merge
    if not (state.spec_request or spec.spec_request or "").strip():
        errors.append("empty_spec_request")
        ok = False
    if spec.clarification_needed:
        errors.append("clarification_needed")
        ok = False
    # Soft: if features all unknown and catalog present, still allow if spec_request strong
    feats, unknown = filter_features_to_catalog(list(spec.features or []))
    if unknown and not feats and len((spec.spec_request or "")) < 20:
        errors.append("features_not_in_catalog")
        ok = False
    return ok, errors


def apply_catalog_filter_to_state(state: AgentState) -> AgentState:
    """Normalize preferred_keys/features to catalog keys when possible."""
    spec = StrictSpec.from_dict(state.strict_spec or {})
    feats, unknown = filter_features_to_catalog(list(spec.features or state.preferred_keys or []))
    if feats:
        spec.features = feats
        state.preferred_keys = feats
        state.strict_spec = spec.to_dict()
        state.strict_spec.setdefault("raw", {})
        if isinstance(state.strict_spec.get("raw"), dict):
            state.strict_spec["raw"]["unknown_features"] = unknown
    return state
