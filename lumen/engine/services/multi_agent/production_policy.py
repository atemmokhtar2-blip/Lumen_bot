"""Single source of truth for production agent runtime policy.

World-class gate (no silent degradation):
  - LangGraph is the only orchestration graph in production
  - Temporal is the only durable workflow engine in production
  - Verified template fallback is forbidden in production
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
    if is_production():
        return False
    return (os.getenv("MULTI_AGENT_ALLOW_TEMPLATE_FALLBACK") or "0").strip().lower() in {
        "1", "true", "yes", "on",
    }


def required_workflow_engine() -> str:
    """Production forces temporal unless explicitly overridden with non-empty TBE_WORKFLOW_ENGINE
    that is still temporal* — only temporal is accepted in production.
    """
    forced = (os.getenv("TBE_WORKFLOW_ENGINE") or "").strip().lower()
    if is_production():
        if forced and forced not in {"temporal", "temporalio"}:
            # reject memory/redis as primary in production
            return "temporal"
        return "temporal"
    return forced or (
        "redis_streams"
        if (os.getenv("REDIS_URL") or os.getenv("JOB_REDIS_URL") or "").strip()
        else "memory"
    )


def policy_snapshot() -> dict[str, Any]:
    return {
        "environment": env_name(),
        "is_production": is_production(),
        "require_langgraph": require_langgraph(),
        "allow_imperative_fallback": allow_imperative_fallback(),
        "allow_template_fallback": allow_template_fallback(),
        "workflow_engine": required_workflow_engine(),
    }


__all__ = [
    "allow_imperative_fallback",
    "allow_template_fallback",
    "env_name",
    "is_production",
    "policy_snapshot",
    "require_langgraph",
    "required_workflow_engine",
]
