"""Deterministic tool contracts for the general execution path.

These are NOT LLM prompts — they are code tools the agent (Cline or builtin)
may call under policy. Matches the createTool() spirit without requiring the
external SDK at import time.
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


def _compose_catalog(ir_dict: dict[str, Any], work_dir: str) -> dict[str, Any]:
    from pathlib import Path

    from lumen.engine.core.ir import BuildIR
    from lumen.engine.services.engine_router import _run_catalog

    ir = BuildIR.from_dict(ir_dict)
    result = _run_catalog(ir, Path(work_dir), int(ir_dict.get("user_id") or 0))
    return {
        "ok": bool(getattr(result, "success", False)),
        "project_path": getattr(result, "project_path", None),
        "errors": list(getattr(result, "errors", None) or []),
        "metadata": dict(getattr(result, "metadata", None) or {}),
    }


def _apply_scaffolds(project_path: str, gaps: list[str]) -> dict[str, Any]:
    from lumen.engine.services.hybrid_scaffolds import apply_hybrid_scaffolds

    written = apply_hybrid_scaffolds(project_path, list(gaps or []))
    return {"ok": True, "written": written}


def _run_smoke(project_path: str) -> dict[str, Any]:
    try:
        from lumen.bot.generation_steps.helpers import _smoke_test_project
        from pathlib import Path

        ok, msg = _smoke_test_project(Path(project_path), seconds=4.0)
        return {"ok": bool(ok), "message": str(msg)[:500]}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}


def _ir_acceptance(project_path: str, ir_dict: dict[str, Any]) -> dict[str, Any]:
    from lumen.engine.core.ir import BuildIR
    from lumen.engine.core.ir_validate import check_project_against_ir

    return check_project_against_ir(project_path, BuildIR.from_dict(ir_dict))


def build_default_tools() -> dict[str, ToolSpec]:
    """Registry of safe tools. Shell/web stay disabled until policy env says otherwise."""
    tools = [
        ToolSpec(
            name="compose_catalog",
            description="Build bot from catalog using IR preferred_keys (deterministic).",
            input_schema={
                "type": "object",
                "properties": {
                    "ir": {"type": "object"},
                    "work_dir": {"type": "string"},
                },
                "required": ["ir", "work_dir"],
            },
            execute=lambda ir, work_dir: _compose_catalog(ir, work_dir),
            auto_approve=True,
            tags=["catalog", "safe"],
        ),
        ToolSpec(
            name="apply_hybrid_scaffolds",
            description="Write webhook/http/cron scaffolds for declared IR gaps.",
            input_schema={
                "type": "object",
                "properties": {
                    "project_path": {"type": "string"},
                    "gaps": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["project_path"],
            },
            execute=lambda project_path, gaps=None: _apply_scaffolds(
                project_path, list(gaps or [])
            ),
            auto_approve=True,
            tags=["hybrid", "safe"],
        ),
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
        ToolSpec(
            name="run_shell",
            description="DISABLED by default — shell execution under sandbox only.",
            input_schema={
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
            execute=lambda command: {"ok": False, "error": "shell_disabled"},
            auto_approve=False,
            enabled=False,
            tags=["dangerous"],
        ),
        ToolSpec(
            name="fetch_web",
            description="DISABLED by default — web fetch under policy only.",
            input_schema={
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
            execute=lambda url: {"ok": False, "error": "web_disabled"},
            auto_approve=False,
            enabled=False,
            tags=["dangerous"],
        ),
    ]
    return {t.name: t for t in tools}


def tool_policies(tools: dict[str, ToolSpec] | None = None) -> dict[str, dict[str, Any]]:
    tools = tools or build_default_tools()
    return {name: t.to_policy() for name, t in tools.items()}


__all__ = ["ToolSpec", "build_default_tools", "tool_policies"]
