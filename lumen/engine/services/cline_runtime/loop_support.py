"""Shared helpers for the Cline agent loop (prompts, budgets, progress)."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _emit_progress(event: dict[str, Any]) -> None:
    """Push live progress to UI sink via engine progress_bus (no bot imports)."""
    try:
        from lumen.engine.services.progress_bus import report_progress
        report_progress(event)
    except Exception:
        pass


AGENT_TOOL_NAMES: tuple[str, ...] = (
    "list_dir", "tree", "read_file", "read_files", "write_file", "edit_file",
    "search_replace", "apply_edits", "apply_patch", "grep_codebase", "glob_files",
    "run_shell", "find_symbol", "get_symbol_source", "find_references", "blast_radius",
    "code_search", "browser_navigate", "browser_content", "browser_click",
    "browser_fill", "browser_screenshot", "run_skill", "finish",
)


def _tools_help() -> str:
    return (
        "Tools (exactly one JSON object per turn): "
        + ", ".join(AGENT_TOOL_NAMES)
        + ". Multi-file: apply_edits/apply_patch/read_files/grep_codebase/glob_files. "
        "Code intel: find_symbol/get_symbol_source/find_references/blast_radius/code_search. "
        "Browser needs Playwright+BROWSER_USE_ENABLED. Shell needs CLINE_ALLOW_SHELL=1."
    )


def _max_steps() -> int:
    try:
        # Default 12 steps (was 24) — weakness #2 fix: fewer steps means the
        # loop cannot run for 108 minutes even without the time budget. The
        # time budget (150s) is the primary guarantee; this is a secondary cap.
        return max(5, min(50, int(os.getenv("CLINE_AGENT_MAX_STEPS") or "12")))
    except ValueError:
        return 12


def _time_budget() -> float:
    """Hard wall-clock budget (seconds) for the entire agent loop.

    INNER guarantee: loop stops when elapsed exceeds budget. Default 150s
    (under GENERATION_TIMEOUT_SEC 180s). Tunable via CLINE_AGENT_TIME_BUDGET_SEC.
    """
    try:
        v = float(os.getenv("CLINE_AGENT_TIME_BUDGET_SEC") or "150")
    except ValueError:
        v = 150.0
    return max(10.0, min(600.0, v))


def _system_prompt(work_dir: str, goal: str, ir_hint: dict[str, Any] | None) -> str:
    hint = ""
    plan_block = ""
    repair_block = ""
    if ir_hint:
        slim = {
            "request": (
                ir_hint.get("raw_request")
                or ir_hint.get("user_request")
                or ir_hint.get("spec_request")
                or ""
            )[:500],
            "features": (ir_hint.get("preferred_keys") or ir_hint.get("features_requested") or [])[:20],
            "lang": ir_hint.get("language") or "ar",
        }
        hint = "\nHINT: " + json.dumps(slim, ensure_ascii=False)[:800]
        meta = ir_hint.get("metadata") if isinstance(ir_hint.get("metadata"), dict) else {}
        plan = ir_hint.get("execution_plan") or meta.get("execution_plan") or {}
        repair = ir_hint.get("repair_directive") or meta.get("repair_directive") or {}
        if plan:
            plan_block = "\n\nEXECUTION_PLAN (follow tasks in order):\n" + json.dumps(
                plan, ensure_ascii=False
            )[:2000]
        if repair:
            repair_block = "\n\nREPAIR_DIRECTIVE (must resolve before finish):\n" + json.dumps(
                repair, ensure_ascii=False
            )[:1500]
    goal_s = (goal or "")[:4000]
    repair_mode = "MODE=INCREMENTAL_REPAIR" in goal_s or (
        isinstance(ir_hint, dict)
        and (
            (ir_hint.get("metadata") or {}).get("mode") == "incremental_repair"
            or bool(ir_hint.get("repair_directive") or ir_hint.get("findings"))
        )
    )
    role_line = (
        "You are Cline (multi-file coding agent) in INCREMENTAL REPAIR mode. Edit the existing project. "
        "Prefer edit_file. Never wipe the project. Fix ERROR findings only."
        if repair_mode
        else "You are Cline, an autonomous coding agent operating as the Worker role."
    )
    return f"""{role_line}
Build a complete runnable project matching the GOAL (any platform). No stub-only placeholders for required features.

Workspace: {work_dir}

{_tools_help()}

Rules:
1. Minimum deliverables: main.py, requirements.txt, README.md, .env.example
2. BOT_TOKEN / TELEGRAM_BOT_TOKEN from environment only — never hardcode secrets
3. Valid Python syntax in every .py file; prefer telegram.ext.Application
4. If REPAIR_DIRECTIVE is present, fix those items first (prefer edit_file)
5. If EXECUTION_PLAN is present, complete priority-1 tasks before finish
6. Arabic UX when goal/language is Arabic
7. Call finish only when deliverables exist and repairs are addressed

GOAL:
{goal_s}{hint}{plan_block}{repair_block}
""".strip()


def _safe_args(args: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in (args or {}).items():
        if k == "content" and isinstance(v, str) and len(v) > 400:
            out[k] = v[:400] + f"...({len(v)} chars)"
        else:
            out[k] = v
    return out
