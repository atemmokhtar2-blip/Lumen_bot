"""Autonomous agent loop — the core of free Cline path.

plan → tool call → observe → repeat until finish / max_steps / error.
Does NOT use catalog templates. Writes a real project under work_dir.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from .agent_acceptance import check_agent_project
from .agent_brain import decide
from .agent_fs import run_tool
from .agent_state import AgentState, AgentStep
from .model_router import describe_runtime, select_model

logger = logging.getLogger(__name__)


def _max_steps() -> int:
    try:
        return max(5, min(50, int(os.getenv("CLINE_AGENT_MAX_STEPS") or "24")))
    except ValueError:
        return 16



def _system_prompt(work_dir: str, goal: str, ir_hint: dict[str, Any] | None) -> str:
    hint = ""
    if ir_hint:
        slim = {
            "request": (ir_hint.get("raw_request") or ir_hint.get("user_request") or "")[:500],
            "features": (ir_hint.get("preferred_keys") or ir_hint.get("features_requested") or [])[:20],
            "lang": ir_hint.get("language") or "ar",
        }
        hint = "\nHINT: " + json.dumps(slim, ensure_ascii=False)[:800]
    goal_s = (goal or "")[:900]
    return f"""You are Cline, an autonomous coding agent. Build a complete runnable Telegram bot from the GOAL.
No templates — write real files under workspace (relative paths only).

Workspace: {work_dir}

Tools (one JSON per turn):
list_dir, tree, read_file, write_file, edit_file, run_shell (if allowed), finish.

Minimum deliverables: main.py, requirements.txt, README.md, .env.example
Use BOT_TOKEN from env. Arabic UX if goal is Arabic. Call finish when coherent.

GOAL:
{goal_s}{hint}
""".strip()


def run_agent(
    *,
    work_dir: str | Path,
    goal: str,
    ir_dict: dict[str, Any] | None = None,
    max_steps: int | None = None,
) -> AgentState:
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    state = AgentState(work_dir=str(work.resolve()), goal=goal or "")
    state.metadata["model"] = describe_runtime()
    choice = select_model(task="build")
    if choice.provider == "none":
        state.stop_reason = "no_model"
        state.errors.append("no_llm_provider_configured")
        state.ok = False
        return state

    limit = max_steps if max_steps is not None else _max_steps()
    state.add_system(_system_prompt(state.work_dir, goal, ir_dict))
    state.add_user(
        "Start building now. Inspect the workspace, then write the project files."
    )

    for i in range(limit):
        msgs = [m.to_dict() for m in state.messages]
        decision = decide(msgs, choice=choice)
        step = AgentStep(
            index=i,
            thought=str(decision.get("thought") or ""),
            tool_name=decision.get("tool"),
            tool_args=dict(decision.get("args") or {}),
            raw_model=str(decision.get("raw") or ""),
        )

        if decision.get("error"):
            step.tool_result = {"ok": False, "error": decision["error"]}
            state.steps.append(step)
            state.errors.append(str(decision["error"]))
            state.stop_reason = "error"
            state.ok = False
            return state

        if not decision.get("parse_ok") and not decision.get("tool"):
            state.add_assistant(str(decision.get("raw") or decision.get("thought") or ""))
            state.add_user("Your last reply was not valid JSON tool call. Reply with JSON only.")
            state.steps.append(step)
            state.warnings.append(f"parse_fail_step_{i}")
            continue

        tool = decision.get("tool")
        args = dict(decision.get("args") or {})

        if decision.get("finish") or tool == "finish":
            if decision.get("summary"):
                args.setdefault("summary", decision["summary"])
            result = run_tool(state.work_dir, "finish", args)
            step.tool_name = "finish"
            step.tool_result = result
            state.steps.append(step)
            state.add_assistant(step.thought or decision.get("summary") or "done")
            acc = check_agent_project(state.work_dir, goal=goal)
            state.metadata["acceptance"] = acc
            if acc.get("ok"):
                state.stop_reason = "completed"
                state.ok = True
                state.metadata["summary"] = args.get("summary") or decision.get("summary") or ""
                break
            # acceptance failed — push agent to fix instead of stopping if steps remain
            state.warnings.append("acceptance_soft_fail:" + ",".join(acc.get("missing") or [])[:200])
            state.add_user(
                "Acceptance failed. Missing: "
                + ", ".join(acc.get("missing") or [])
                + ". Continue writing the missing files, then call finish again."
            )
            continue

        if not tool:
            state.add_assistant(step.thought or "(no tool)")
            state.add_user("Call a tool or finish. JSON only.")
            state.steps.append(step)
            continue

        result = run_tool(state.work_dir, str(tool), args)
        step.tool_result = result
        state.steps.append(step)
        state.add_assistant(
            json.dumps(
                {"thought": step.thought, "tool": tool, "args": _safe_args(args)},
                ensure_ascii=False,
            )[:4000]
        )
        state.add_tool_result(str(tool), result)

        if tool == "write_file" and result.get("ok") and result.get("path"):
            path = str(result["path"])
            if path not in state.files_written:
                state.files_written.append(path)
        if tool == "edit_file" and result.get("ok") and args.get("path"):
            path = str(args["path"])
            if path not in state.files_written:
                state.files_written.append(path)
    else:
        state.stop_reason = "max_steps"
        state.warnings.append(f"hit_max_steps_{limit}")
        state.ok = bool(state.files_written)

    if state.stop_reason == "completed" and not state.files_written:
        try:
            written = [
                p.relative_to(work).as_posix()
                for p in work.rglob("*")
                if p.is_file() and p.name not in {".DS_Store"}
            ][:50]
            state.files_written = written
            if not written:
                state.ok = False
                state.errors.append("finish_without_files")
        except Exception:
            pass

    # Final acceptance snapshot
    try:
        acc = check_agent_project(state.work_dir, goal=goal)
        state.metadata["acceptance"] = acc
        if state.ok and not acc.get("ok"):
            state.warnings.append("acceptance_final_fail")
            # demote ok only if nothing useful written
            if not state.files_written:
                state.ok = False
        elif not state.ok and acc.get("ok"):
            state.ok = True
            if not state.stop_reason:
                state.stop_reason = "completed_by_acceptance"
    except Exception as exc:
        state.warnings.append(f"acceptance_error:{type(exc).__name__}")

    state.metadata["steps"] = len(state.steps)
    state.metadata["files_written"] = list(state.files_written)
    return state


def _safe_args(args: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in (args or {}).items():
        if k == "content" and isinstance(v, str) and len(v) > 400:
            out[k] = v[:400] + f"...({len(v)} chars)"
        else:
            out[k] = v
    return out


__all__ = ["run_agent"]
