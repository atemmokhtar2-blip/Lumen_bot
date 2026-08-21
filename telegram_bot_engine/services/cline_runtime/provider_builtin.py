"""Builtin general provider — Phase 3 without external Cline SDK.

Pipeline under IR + tool policies:
  1) compose_catalog
  2) apply_hybrid_scaffolds for gaps
  3) ir_acceptance + smoke
  4) write TOOLS_USED.md + model router metadata

Enable with:
  CLINE_ENABLED=1
  # optional: CLINE_PROVIDER=telegram_bot_engine.services.cline_runtime.provider_builtin:build
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .model_router import describe_runtime
from .tools import build_default_tools

logger = logging.getLogger(__name__)


def build(ir_dict: dict[str, Any], work_dir: str) -> dict[str, Any]:
    """CLINE_PROVIDER entrypoint. Returns dict compatible with ClineExecutionResult."""
    tools = build_default_tools()
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    steps: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []

    # 1) catalog compose
    compose = tools["compose_catalog"].execute(ir_dict, str(work))
    steps.append({"tool": "compose_catalog", "result": {k: compose.get(k) for k in ("ok", "project_path", "errors")}})
    if not compose.get("ok") or not compose.get("project_path"):
        return {
            "ok": False,
            "project_path": None,
            "engine": "cline_builtin",
            "errors": list(compose.get("errors") or ["compose_catalog_failed"]),
            "warnings": warnings,
            "metadata": {"steps": steps, "model": describe_runtime()},
            "fallback_catalog": True,
        }

    path = str(compose["project_path"])
    gaps = list(ir_dict.get("capabilities_gap") or [])

    # 2) scaffolds
    sc = tools["apply_hybrid_scaffolds"].execute(path, gaps)
    steps.append({"tool": "apply_hybrid_scaffolds", "result": sc})

    # 3) acceptance
    acc = tools["ir_acceptance"].execute(path, ir_dict)
    steps.append({"tool": "ir_acceptance", "result": acc})
    if not acc.get("ok"):
        warnings.append("ir_acceptance_soft_fail:" + ",".join(acc.get("missing_features") or [])[:200])

    # 4) smoke
    smoke = tools["run_smoke"].execute(path)
    steps.append({"tool": "run_smoke", "result": smoke})
    if not smoke.get("ok"):
        errors.append("smoke_failed:" + str(smoke.get("message") or smoke.get("error") or "")[:200])

    # 5) audit file
    try:
        audit = Path(path) / "TOOLS_USED.md"
        lines = [
            "# Tools used (builtin Cline path)",
            "",
            f"- model: `{describe_runtime()}`",
            f"- gaps: `{gaps}`",
            "",
            "## Steps",
            "",
        ]
        for s in steps:
            lines.append(f"- **{s['tool']}**: `{s['result']}`")
        lines.append("")
        audit.write_text("\n".join(lines), encoding="utf-8")
    except Exception as exc:
        warnings.append(f"audit_write:{type(exc).__name__}")

    ok = bool(compose.get("ok")) and not errors
    return {
        "ok": ok,
        "project_path": path if ok else path,
        "engine": "cline_builtin",
        "errors": errors,
        "warnings": warnings,
        "metadata": {
            "steps": steps,
            "model": describe_runtime(),
            "tools": list(tools.keys()),
        },
        "fallback_catalog": False,
    }


__all__ = ["build"]
