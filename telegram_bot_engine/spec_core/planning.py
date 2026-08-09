"""Planning Engine — derives file plan and module map from BotSpec (no AI)."""
from __future__ import annotations

from dataclasses import dataclass, field

from .registry import get_capability
from .schema import BotSpec


@dataclass
class PlannedFile:
    path: str
    purpose: str
    required: bool = True


@dataclass
class PlanResult:
    ok: bool
    files: list[PlannedFile] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def plan_from_spec(spec: BotSpec) -> PlanResult:
    errors: list[str] = []
    warnings: list[str] = []
    if not spec.features:
        errors.append("no_features")
    services: set[str] = set()
    for feat in spec.features:
        cap = get_capability(feat.feature)
        if cap is None:
            errors.append(f"unknown_capability:{feat.feature}")
            continue
        services.add(cap.service)

    files = [
        PlannedFile("main.py", "application entry"),
        PlannedFile("requirements.txt", "dependencies"),
        PlannedFile(".env.example", "env template"),
        PlannedFile("README.md", "run instructions"),
        PlannedFile("app/__init__.py", "package"),
        PlannedFile("app/config.py", "settings"),
        PlannedFile("app/handlers.py", "telegram handlers"),
        PlannedFile("app/keyboards.py", "inline keyboards"),
    ]
    if "moderation" in services:
        files.append(PlannedFile("app/services/moderation.py", "moderation service"))
    if "tasks" in services or spec.storage.type == "sqlite":
        files.append(PlannedFile("app/services/tasks.py", "tasks service"))
        files.append(PlannedFile("app/db.py", "sqlite helpers"))
    files.append(PlannedFile("app/services/__init__.py", "services package"))

    return PlanResult(
        ok=len(errors) == 0,
        files=files,
        services=sorted(services),
        errors=errors,
        warnings=warnings,
    )


__all__ = ["PlannedFile", "PlanResult", "plan_from_spec"]
