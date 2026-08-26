"""Context isolation — each agent sees only what it needs (token hygiene + less confusion).

Phase A+: Planner/Worker receive structured findings + project snapshot on repair.
"""
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
    """Planner view — includes repair findings so re-plans are grounded."""
    repair = (state.extensions or {}).get("last_repair")
    findings = list((state.extensions or {}).get("findings") or [])[:20]
    traj = list((state.extensions or {}).get("trajectory") or [])[-12:]
    return {
        "user_text": (state.user_text or "")[:8000],
        "user_intent": state.user_intent,
        "capability_id": state.capability_id,
        "route_params": dict(state.route_params or {}),
        "preferred_keys_hint": list(state.preferred_keys or [])[:40],
        "attempts": state.attempts,
        "qa_summary": _qa_summary(state),
        "repair_directive": repair,
        "findings": findings,
        "trajectory_tail": traj,
        "previous_strict_spec": dict(state.strict_spec or {}) if state.attempts else None,
        "execution_plan": (state.extensions or {}).get("execution_plan"),
        "generated_path": state.generated_path,
    }


def builder_view(state: AgentState) -> dict[str, Any]:
    """Worker view — contract + repair + optional project snapshot."""
    spec = dict(state.strict_spec or {})
    return {
        "strict_spec": spec,
        "spec_request": (state.spec_request or spec.get("spec_request") or "")[:20000],
        "preferred_keys": list(state.preferred_keys or [])[:80],
        "user_id": state.user_id,
        "language": spec.get("language") or "ar",
        "execution_plan": (state.extensions or {}).get("execution_plan"),
        "last_repair": (state.extensions or {}).get("last_repair"),
        "findings": list((state.extensions or {}).get("findings") or [])[:20],
        "generated_path": state.generated_path,
        "project_context": (state.extensions or {}).get("project_context"),
    }


def critic_view(state: AgentState) -> dict[str, Any]:
    return {
        "generated_path": state.generated_path,
        "build_success": state.build_success,
        "build_errors": list(state.build_errors or [])[:20],
        "strict_spec_features": list((state.strict_spec or {}).get("features") or [])[:40],
        "execution_plan": (state.extensions or {}).get("execution_plan"),
        "preferred_keys": list(state.preferred_keys or [])[:40],
    }


def deliver_view(state: AgentState) -> dict[str, Any]:
    """Router/delivery may see outcomes, not raw model internals."""
    return {
        "status": state.status,
        "generated_path": state.generated_path,
        "qa_passed": state.qa_passed,
        "build_success": state.build_success,
        "final_message": state.final_message,
        "user_intent": state.user_intent,
        "clarification_needed": bool((state.strict_spec or {}).get("clarification_needed")),
        "clarification_questions": list(
            (state.strict_spec or {}).get("clarification_questions") or []
        )[:5],
        "trajectory_summary": (state.extensions or {}).get("trajectory", [])[-6:],
    }


def _qa_summary(state: AgentState) -> dict[str, Any] | None:
    rep = state.qa_report or {}
    if not rep:
        return None
    findings = list((state.extensions or {}).get("findings") or [])[:15]
    return {
        "ok": bool(rep.get("ok")),
        "errors": list(rep.get("errors") or [])[:15],
        "warnings": list(rep.get("warnings") or [])[:10],
        "findings": findings,
        "findings_count": int(rep.get("findings_count") or len(findings) or 0),
    }


__all__ = [
    "router_view",
    "architect_view",
    "builder_view",
    "critic_view",
    "deliver_view",
]
