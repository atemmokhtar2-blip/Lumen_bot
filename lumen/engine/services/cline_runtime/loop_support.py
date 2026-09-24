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


def env_max_steps_ceiling() -> int:
    """Single source for CLINE_AGENT_MAX_STEPS ceiling used by LoopGovernor.

    - Explicit env: clamp 5..50
    - Unset: 15 so hard-band (14) is not silently capped by a lower default
    """
    raw = (os.getenv("CLINE_AGENT_MAX_STEPS") or "").strip()
    if not raw:
        return 15
    try:
        return max(5, min(50, int(raw)))
    except ValueError:
        return 15


def _max_steps() -> int:
    """Back-compat alias → env_max_steps_ceiling()."""
    return env_max_steps_ceiling()


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
            "runtime_language": (
                ir_hint.get("runtime_language")
                or ir_hint.get("language")
                or (ir_hint.get("metadata") or {}).get("language")
                or "python"
            ),
            "ui_lang": "ar",
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
    # ProjectKind rules — never force Telegram for web/cli/library
    kind_rules = ""
    try:
        from lumen.engine.core.project_kind import parse_kind, cline_kind_rules, resolve_project_kind
        pk_raw = ""
        if isinstance(ir_hint, dict):
            pk_raw = (
                ir_hint.get("project_kind")
                or (ir_hint.get("metadata") or {}).get("project_kind")
                or ""
            )
            plan = ir_hint.get("execution_plan") or (ir_hint.get("metadata") or {}).get("execution_plan")
            if not pk_raw and isinstance(plan, dict):
                pk_raw = plan.get("project_kind") or ""
        pk = parse_kind(pk_raw)
        if pk is None and goal_s:
            pk = resolve_project_kind(text=goal_s)
        if pk is not None:
            kind_rules = "\nKIND_RULES: " + cline_kind_rules(pk)
    except Exception:
        kind_rules = ""

    lang_rules = ""
    rt_lang = "python"
    try:
        from lumen.engine.core.language_runtime import resolve_language, recipe_for, parse_language
        _explicit = None
        if isinstance(ir_hint, dict):
            _explicit = (
                ir_hint.get("runtime_language")
                or ir_hint.get("language")
                or (ir_hint.get("metadata") or {}).get("language")
                or (ir_hint.get("metadata") or {}).get("runtime_language")
            )
            # Ignore UI language codes
            if str(_explicit or "").lower() in {"ar", "en", "fa", "ur"}:
                _explicit = None
        _lr, _, _ = resolve_language(goal_s, explicit=_explicit)
        rt_lang = _lr.value
        rec = recipe_for(_lr)
        lang_rules = (
            f"\nRUNTIME_LANGUAGE={rt_lang}\n"
            f"LANGUAGE_RECIPE: image={rec.docker_image} install={rec.install_command!r} "
            f"start={rec.default_start!r} manifests={list(rec.manifest_files)} "
            f"sources={list(rec.source_globs)}"
        )
        if rt_lang != "python":
            lang_rules += (
                "\nNOTE: Prefer LANGUAGE_RECIPE over python-centric KIND_RULES. "
                "Do not force main.py/requirements.txt when RUNTIME_LANGUAGE is not python."
            )
    except Exception:
        lang_rules = "\nRUNTIME_LANGUAGE=python"

    if rt_lang == "python":
        deliverable_rule = (
            "1. Minimum deliverables: main.py, requirements.txt, README.md, .env.example "
            "(adjust if KIND_RULES say otherwise)"
        )
        syntax_rule = "3. Valid Python syntax in every .py file"
    else:
        deliverable_rule = (
            f"1. Minimum deliverables for {rt_lang}: manifests from LANGUAGE_RECIPE, "
            "source entry, README.md, .env.example — not Python files unless needed"
        )
        syntax_rule = f"3. Valid {rt_lang} syntax in source files; match LANGUAGE_RECIPE"

    return f"""{role_line}
Build a complete runnable project matching the GOAL and RUNTIME_LANGUAGE. No stub-only placeholders for required features.
{kind_rules}{lang_rules}

Workspace: {work_dir}

{_tools_help()}

Rules:
{deliverable_rule}
2. Never hardcode secrets; tokens/keys from environment only
{syntax_rule}
4. Follow KIND_RULES + RUNTIME_LANGUAGE — do NOT build a Telegram bot unless PROJECT_KIND=telegram_bot
5. If REPAIR_DIRECTIVE is present, fix those items first (prefer edit_file)
6. If EXECUTION_PLAN is present, complete priority-1 tasks before finish
7. Arabic UX when the user request is Arabic
8. Call finish only when deliverables exist and repairs are addressed

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
