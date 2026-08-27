"""Single source of truth for production agent runtime policy.

World-class gate (no silent degradation):
  - LangGraph is the only orchestration graph
  - Temporal is the preferred durable shell (when TEMPORAL_HOST set)
  - Verified template fallback is FORBIDDEN always
  - Imperative while-True generate path is FORBIDDEN always
  - CLINE_MODE=builtin catalog path is FORBIDDEN in production
"""
from __future__ import annotations

import os
from typing import Any


def env_name() -> str:
    return (os.getenv("ENVIRONMENT") or os.getenv("LUMEN_ENV") or "development").strip().lower()


def is_production() -> bool:
    return env_name() in {"production", "prod", "staging"}


def require_langgraph() -> bool:
    """Always required unless MULTI_AGENT_LANGGRAPH=0 in non-production."""
    if is_production():
        return True
    flag = (os.getenv("MULTI_AGENT_LANGGRAPH") or "1").strip().lower()
    return flag not in {"0", "false", "no", "off"}


def allow_imperative_fallback() -> bool:
    """Always False — LangGraph + Cline agent_loop only."""
    return False


def allow_template_fallback() -> bool:
    """Always False — template/stub bots are dead."""
    return False


def allow_cline_builtin() -> bool:
    """Catalog compose path. Forbidden in production; opt-in only in dev."""
    if is_production():
        return False
    return (os.getenv("CLINE_ALLOW_BUILTIN") or "0").strip().lower() in {
        "1", "true", "yes", "on",
    }



def required_workflow_engine() -> str:
    """Durability: LangGraph SqliteSaver (HITL) + optional Temporal host."""
    return "langgraph_sqlite+temporal_optional"


def force_cline_agent_mode() -> bool:
    """True when builtin must not run."""
    return not allow_cline_builtin()


def policy_snapshot() -> dict[str, Any]:
    return {
        "env": env_name(),
        "is_production": is_production(),
        "require_langgraph": require_langgraph(),
        "allow_imperative_fallback": allow_imperative_fallback(),
        "allow_template_fallback": allow_template_fallback(),
        "allow_cline_builtin": allow_cline_builtin(),
                "workflow_engine": required_workflow_engine(),
        "force_cline_agent_mode": force_cline_agent_mode(),
    }


__all__ = [
    "env_name",
    "is_production",
    "require_langgraph",
    "allow_imperative_fallback",
    "allow_template_fallback",
    "allow_cline_builtin",
    "required_workflow_engine",
    "force_cline_agent_mode",
    "policy_snapshot",
]
