"""Engine roles — hard separation Planning vs Generation vs Validation vs Runtime."""

from __future__ import annotations

from enum import Enum


class EngineRole(str, Enum):
    PLANNING = "planning"
    GENERATION = "generation"
    VALIDATION = "validation"
    RUNTIME = "runtime"
    INFRA = "infra"


PLANNING_OWNED_KEYS = frozenset(
    {
        "analysis_report",
        "project_blueprint",
        "project_structure_blueprint",
        "file_generation_plan",
        "blueprint",
        "intent",
        "user_intent",
        "gemini_understanding",
        "spec_backends",
        "spec_core_capabilities",
    }
)

__all__ = ["EngineRole", "PLANNING_OWNED_KEYS"]
