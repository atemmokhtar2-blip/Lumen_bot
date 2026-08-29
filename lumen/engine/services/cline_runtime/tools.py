"""Tool contracts for the Cline agent path.

Catalog/hybrid/deterministic compose tools have been permanently removed.
Only QA helpers remain (smoke + IR acceptance).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    execute: Callable[..., Any]
    auto_approve: bool = False
    enabled: bool = True
    tags: list[str] = field(default_factory=list)

    def to_policy(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "autoApprove": self.auto_approve,
        }


def _run_smoke(project_path: str) -> dict[str, Any]:
    try:
        from pathlib import Path

        from lumen.bot.generation_steps.helpers import _smoke_test_project

        ok, msg = _smoke_test_project(Path(project_path), seconds=4.0)
        return {"ok": bool(ok), "message": str(msg)[:500]}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}


def _ir_acceptance(project_path: str, ir_dict: dict[str, Any]) -> dict[str, Any]:
    from lumen.engine.core.ir import BuildIR
    from lumen.engine.core.ir_validate import check_project_against_ir

    return check_project_against_ir(project_path, BuildIR.from_dict(ir_dict))


def build_default_tools() -> dict[str, ToolSpec]:
    """Safe tools only — no catalog/hybrid generation."""
    tools = [
        ToolSpec(
            name="run_smoke",
            description="Import-check generated project briefly.",
            input_schema={
                "type": "object",
                "properties": {"project_path": {"type": "string"}},
                "required": ["project_path"],
            },
            execute=lambda project_path: _run_smoke(project_path),
            auto_approve=True,
            tags=["qa", "safe"],
        ),
        ToolSpec(
            name="ir_acceptance",
            description="Check generated main.py against IR preferred features.",
            input_schema={
                "type": "object",
                "properties": {
                    "project_path": {"type": "string"},
                    "ir": {"type": "object"},
                },
                "required": ["project_path", "ir"],
            },
            execute=lambda project_path, ir: _ir_acceptance(project_path, ir),
            auto_approve=True,
            tags=["qa", "safe"],
        ),
    ]
    return {t.name: t for t in tools}


__all__ = ["ToolSpec", "build_default_tools"]
