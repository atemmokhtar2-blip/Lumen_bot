"""
StaticDevGate public API — stable for ActiveDev / RepoDev.

Foundation:
  AnalysisContext (one parse) → Rule registry → StaticReport
  New checks = new Rule class + register in rules/registry.py
"""

from __future__ import annotations

import re
from pathlib import Path

from .engine import analyze, run_rules
from .context import build_context
from .models import StaticFinding, StaticReport


def analyze_project(root: str | Path, focus_files: list[str] | None = None) -> StaticReport:
    return analyze(str(root), focus_files=focus_files)


def verify_after_edit(
    root: str | Path,
    changed_files: list[str],
    expected_commands: list[str] | None = None,
) -> StaticReport:
    root_p = Path(root)
    focus = list(changed_files or [])
    for name in ("main.py", "bot.py", "app.py", "active_dev_commands.py"):
        if (root_p / name).is_file() and name not in focus:
            focus.append(name)
    # Gate uses core + telegram tags primarily, but run all enabled rules
    return analyze(
        str(root_p),
        focus_files=focus,
        expected_commands=expected_commands,
    )


def plan_command_adds(
    existing_commands: set[str],
    wanted: list[str],
) -> tuple[list[str], list[StaticFinding]]:
    findings: list[StaticFinding] = []
    accepted: list[str] = []
    for raw in wanted:
        name = re.sub(r"[^a-z0-9_]", "", (raw or "").lstrip("/").lower())[:32]
        if not name or not re.match(r"^[a-z][a-z0-9_]{0,31}$", name):
            findings.append(StaticFinding(
                severity="error",
                code="illegal_command_name",
                rule_id="plan",
                file="plan",
                message_ar=f"اسم أمر غير صالح: `{raw}`",
            ))
            continue
        if name in existing_commands:
            findings.append(StaticFinding(
                severity="info",
                code="command_exists",
                rule_id="plan",
                file="plan",
                message_ar=f"/{name} موجود — لن يُضاف مجدداً",
            ))
            continue
        if name in accepted:
            continue
        accepted.append(name)
    return accepted, findings


__all__ = [
    "StaticFinding",
    "StaticReport",
    "analyze_project",
    "verify_after_edit",
    "plan_command_adds",
    "build_context",
    "run_rules",
]
