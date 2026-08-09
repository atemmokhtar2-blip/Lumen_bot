"""Zero-AI pipeline: BotSpec → validate → plan → code → validate project."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .coding import write_project
from .planning import plan_from_spec
from .schema import BotSpec
from .validation import validate_project, validate_spec


@dataclass
class BuildResult:
    ok: bool
    project_path: str | None = None
    files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    plan_services: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "project_path": self.project_path,
            "files": list(self.files),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "plan_services": list(self.plan_services),
        }


def build_from_spec(spec: BotSpec | dict, out_dir: str | Path) -> BuildResult:
    if isinstance(spec, dict):
        spec = BotSpec.from_dict(spec)

    spec_v = validate_spec(spec)
    if not spec_v.ok:
        return BuildResult(False, errors=list(spec_v.errors), warnings=list(spec_v.warnings))

    plan = plan_from_spec(spec)
    if not plan.ok:
        return BuildResult(
            False,
            errors=list(plan.errors),
            warnings=list(spec_v.warnings) + list(plan.warnings),
        )

    written = write_project(spec, out_dir)
    proj_v = validate_project(out_dir)
    errors = list(proj_v.errors)
    warnings = list(spec_v.warnings) + list(plan.warnings) + list(proj_v.warnings)
    return BuildResult(
        ok=proj_v.ok,
        project_path=str(Path(out_dir)),
        files=written,
        errors=errors,
        warnings=warnings,
        plan_services=list(plan.services),
    )


__all__ = ["BuildResult", "build_from_spec"]
