"""Development intelligence on an understood active repository."""

from .service import (
    DevPlan,
    DevStep,
    build_dev_plan,
    apply_dependency_gaps,
    suggest_edit_targets,
)

__all__ = [
    "DevPlan",
    "DevStep",
    "build_dev_plan",
    "apply_dependency_gaps",
    "suggest_edit_targets",
]
