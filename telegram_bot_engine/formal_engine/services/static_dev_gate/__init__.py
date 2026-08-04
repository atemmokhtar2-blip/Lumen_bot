"""Static development gate — compiler-grade verification for active-repo edits."""

from .service import (
    StaticFinding,
    StaticReport,
    analyze_project,
    verify_after_edit,
    plan_command_adds,
)

__all__ = [
    "StaticFinding",
    "StaticReport",
    "analyze_project",
    "verify_after_edit",
    "plan_command_adds",
]
