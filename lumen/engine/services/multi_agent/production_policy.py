"""Single source of truth for production agent runtime policy.

World-class gate (no silent degradation) — aligned with 2026 production patterns:
  - LangGraph is the only orchestration graph (Supervisor + Send fan-out)
  - Temporal is the preferred durable shell when TEMPORAL_HOST is set
    (LangGraph for reasoning, Temporal for crash-proof long-running)
  - Parallel workers: official LangGraph Send + max_concurrency throttle
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
    """Always False — template/stub bots are dead. Callers must not use this path."""
    return False


def allow_cline_builtin() -> bool:
    """Catalog compose path. Forbidden in production; opt-in only in dev."""
    if is_production():
        return False
    return (os.getenv("CLINE_ALLOW_BUILTIN") or "0").strip().lower() in {
        "1", "true", "yes", "on",
    }


def temporal_preferred() -> bool:
    """True when Temporal should own the durable shell (host configured)."""
    host = (os.getenv("TEMPORAL_HOST") or os.getenv("TEMPORAL_ADDRESS") or "").strip()
    if not host:
        return False
    if (os.getenv("LUMEN_GENERATE_VIA_TEMPORAL") or "1").strip().lower() in {"0", "false", "no", "off"}:
        return False
    return True


def required_workflow_engine() -> str:
    """Durability stack label for ops / health."""
    if temporal_preferred():
        return "temporal_sequential_activities+cline"
    return "langgraph_sqlite+cline"


def max_parallel_workers() -> int:
    """Official swarm-style concurrency cap for LangGraph Send fan-out."""
    try:
        return max(1, min(32, int(os.getenv("MULTI_AGENT_MAX_PARALLEL") or "8")))
    except ValueError:
        return 8


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
        "temporal_preferred": temporal_preferred(),
        "workflow_engine": required_workflow_engine(),
        "force_cline_agent_mode": force_cline_agent_mode(),
        "max_parallel_workers": max_parallel_workers(),
        "parallel_enabled": (os.getenv("MULTI_AGENT_PARALLEL") or "1").strip().lower()
        not in {"0", "false", "no", "off"},
        # Supervisor + Send fan-out is the 2026 production default for coding agents
        # (peer swarm handoffs are harder to audit; not used as primary path).
        "architecture": "supervisor+send_fanout",
    }


__all__ = [
    "env_name",
    "is_production",
    "require_langgraph",
    "allow_imperative_fallback",
    "allow_template_fallback",
    "allow_cline_builtin",
    "temporal_preferred",
    "required_workflow_engine",
    "max_parallel_workers",
    "force_cline_agent_mode",
    "policy_snapshot",
]
