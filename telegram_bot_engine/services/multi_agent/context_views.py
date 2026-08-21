"""Context isolation — each agent sees only what it needs (token hygiene + less confusion)."""
from __future__ import annotations

from typing import Any

from .state import AgentState


def router_view(state: AgentState) -> dict[str, Any]:
    return {
        "user_text": (state.user_text or "")[:4000],
        "user_id": state.user_id,
        "status": state.status,
    }


def architect_view(state: AgentState) -> dict[str, Any]:
    """Architect must NOT see QA noise, full event logs, or delivery messages."""
    repair = (state.extensions or {}).get("last_repair")
    return {
        "user_text": (state.user_text or "")[:8000],
        "user_intent": state.user_intent,
        "capability_id": state.capability_id,
        "route_params": dict(state.route_params or {}),
        "preferred_keys_hint": list(state.preferred_keys or [])[:40],
        "attempts": state.attempts,
        "qa_summary": _qa_summary(state),
        "repair_directive": repair,
        "previous_strict_spec": dict(state.strict_spec or {}) if state.attempts else None,
    }


def builder_view(state: AgentState) -> dict[str, Any]:
    """Builder sees only the contract — never free-form chat history."""
    spec = dict(state.strict_spec or {})
    return {
        "strict_spec": spec,
        "spec_request": (state.spec_request or spec.get("spec_request") or "")[:20000],
        "preferred_keys": list(state.preferred_keys or [])[:80],
        "user_id": state.user_id,
        "language": spec.get("language") or "ar",
    }


def critic_view(state: AgentState) -> dict[str, Any]:
    return {
        "generated_path": state.generated_path,
        "build_success": state.build_success,
        "build_errors": list(state.build_errors or [])[:20],
        "strict_spec_features": list((state.strict_spec or {}).get("features") or [])[:40],
    }


def deliver_view(state: AgentState) -> dict[str, Any]:
    """Router/delivery may see outcomes, not raw Gemini internals."""
    return {
        "status": state.status,
        "generated_path": state.generated_path,
        "qa_passed": state.qa_passed,
        "build_success": state.build_success,
        "final_message": state.final_message,
        "user_intent": state.user_intent,
        "clarification_needed": bool((state.strict_spec or {}).get("clarification_needed")),
        "clarification_questions": list((state.strict_spec or {}).get("clarification_questions") or [])[:5],
    }


def _qa_summary(state: AgentState) -> dict[str, Any] | None:
    rep = state.qa_report or {}
    if not rep:
        return None
    return {
        "ok": bool(rep.get("ok")),
        "errors": list(rep.get("errors") or [])[:10],
        "warnings": list(rep.get("warnings") or [])[:10],
    }
