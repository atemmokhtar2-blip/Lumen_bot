"""Builtin general provider — Phase 3 hardened (ToolRunner + audit)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .model_router import describe_runtime
from .tool_runner import ToolRunner

logger = logging.getLogger(__name__)


def build(ir_dict: dict[str, Any], work_dir: str) -> dict[str, Any]:
    runner = ToolRunner()
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    warnings: list[str] = []

    compose = runner.run("compose_catalog", ir=ir_dict, work_dir=str(work))
    if not compose.get("ok") or not compose.get("project_path"):
        return {
            "ok": False,
            "project_path": None,
            "engine": "cline_builtin",
            "errors": list(compose.get("errors") or ["compose_catalog_failed"]),
            "warnings": warnings,
            "metadata": {
                "history": runner.history,
                "model": describe_runtime(),
            },
            "fallback_catalog": True,
        }

    path = str(compose["project_path"])
    gaps = list(ir_dict.get("capabilities_gap") or [])
    runner.run("apply_hybrid_scaffolds", project_path=path, gaps=gaps)
    acc = runner.run("ir_acceptance", project_path=path, ir=ir_dict)
    if not acc.get("ok"):
        warnings.append(
            "ir_acceptance_soft_fail:"
            + ",".join(acc.get("missing_features") or [])[:200]
        )
    smoke = runner.run("run_smoke", project_path=path)
    if not smoke.get("ok"):
        errors.append(
            "smoke_failed:"
            + str(smoke.get("message") or smoke.get("error") or "")[:200]
        )

    try:
        from .mcp_bridge import status as mcp_status

        mcp = mcp_status()
    except Exception:
        mcp = {}

    try:
        audit = Path(path) / "TOOLS_USED.md"
        lines = [
            "# Tools used (builtin Cline path)",
            "",
            f"- model: `{describe_runtime()}`",
            f"- mcp: `{mcp}`",
            f"- gaps: `{gaps}`",
            "",
            "## History",
            "",
        ]
        for h in runner.history:
            lines.append(
                f"- **{h.get('tool')}** allowed={h.get('allowed')}: `{h.get('result')}`"
            )
        lines.append("")
        audit.write_text("\n".join(lines), encoding="utf-8")
    except Exception as exc:
        warnings.append(f"audit_write:{type(exc).__name__}")

    ok = bool(compose.get("ok")) and not errors
    return {
        "ok": ok,
        "project_path": path,
        "engine": "cline_builtin",
        "errors": errors,
        "warnings": warnings,
        "metadata": {
            "history": runner.history,
            "model": describe_runtime(),
            "mcp": mcp,
        },
        "fallback_catalog": False,
    }


__all__ = ["build"]
