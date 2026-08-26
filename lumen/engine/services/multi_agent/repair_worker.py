"""Incremental repair Worker — edit existing project instead of regenerating.

This is the Cursor-class gap closer for Phase A: after Critic fails, the Worker
must patch files in-place (edit_file / write_file) under the existing project,
not wipe and re-scaffold.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .findings import CritiqueFinding
from .state import AgentRole, AgentState

logger = logging.getLogger(__name__)


def _findings(state: AgentState) -> list[CritiqueFinding]:
    raw = list((state.extensions or {}).get("findings") or [])
    out: list[CritiqueFinding] = []
    for x in raw:
        if isinstance(x, dict):
            try:
                out.append(CritiqueFinding.from_dict(x))
            except Exception:
                continue
    return out


def should_incremental_repair(state: AgentState) -> bool:
    """True when we already have a project on disk and a repair directive/findings."""
    path = (state.generated_path or "").strip()
    if not path or not Path(path).is_dir():
        return False
    if not any(Path(path).iterdir()):
        return False
    has_repair = bool((state.extensions or {}).get("last_repair"))
    has_findings = bool((state.extensions or {}).get("findings"))
    has_failed_qa = bool(state.qa_report) and not bool(state.qa_passed)
    return bool((has_repair or has_findings) and (has_failed_qa or int(state.attempts or 0) >= 1))


def build_repair_goal(state: AgentState) -> str:
    findings = _findings(state)
    repair = (state.extensions or {}).get("last_repair") or {}
    lines = [
        "MODE=INCREMENTAL_REPAIR",
        "Do NOT recreate the whole project from scratch.",
        "Do NOT delete working files. Prefer edit_file over write_file.",
        "Read each target file before editing.",
        "Fix every ERROR finding below, then call finish.",
        "",
        "ERROR_FINDINGS:",
    ]
    for i, f in enumerate(findings, 1):
        if f.severity != "error":
            continue
        lines.append(
            f"{i}. [{f.code}] path={f.path or '—'} :: {f.message}"
            f" :: FIX={f.fix_hint or 'resolve this error'}"
        )
    if not any(f.severity == "error" for f in findings):
        for e in list(repair.get("blocking_errors") or [])[:15]:
            lines.append(f"- {e}")
        for a in list(repair.get("actions") or [])[:15]:
            lines.append(f"ACTION: {a}")
    lines.append("")
    lines.append("After fixes: ensure main.py/requirements.txt/README.md/.env.example exist and Python syntax is valid.")
    return "\n".join(lines)


def run_incremental_repair(state: AgentState, *, work_dir: Path | None = None) -> AgentState:
    """Run Cline agent_loop on the existing generated_path in repair mode."""
    project = Path((state.generated_path or "").strip())
    if not project.is_dir():
        state.build_success = False
        state.build_errors = ["incremental_repair_no_project"]
        return state

    # Real workspace snapshot via agent_fs (not a fake script)
    try:
        from .project_context import pack_project_context, context_to_prompt_block
        ctx = pack_project_context(project)
        state.extensions["project_context"] = {
            "ok": ctx.get("ok"),
            "tree": (ctx.get("tree") or "")[:1500],
            "file_list": list((ctx.get("files") or {}).keys()),
            "errors": ctx.get("errors") or [],
        }
        snap = context_to_prompt_block(ctx)
    except Exception as exc:
        snap = ""
        state.extensions["project_context_error"] = type(exc).__name__

    goal = build_repair_goal(state)
    if snap:
        goal = goal + "\n\n" + snap
    ir_dict: dict[str, Any] = {
        "spec_request": goal,
        "raw_request": goal,
        "preferred_keys": list(state.preferred_keys or []),
        "execution_plan": (state.extensions or {}).get("execution_plan") or {},
        "repair_directive": (state.extensions or {}).get("last_repair") or {},
        "findings": list((state.extensions or {}).get("findings") or [])[:30],
        "metadata": {
            "mode": "incremental_repair",
            "pre_read_files": list(((state.extensions or {}).get("project_context") or {}).get("file_list") or []),
            "execution_plan": (state.extensions or {}).get("execution_plan") or {},
            "repair_directive": (state.extensions or {}).get("last_repair") or {},
        },
        "language": (state.extensions or {}).get("language") or "ar",
    }

    # 1) Fast local fixes (no LLM) — Cursor always has this layer
    try:
        from .deterministic_repair import apply_deterministic_repairs
        det = apply_deterministic_repairs(
            project,
            findings=_findings(state),
            extensions=state.extensions or {},
        )
        state.extensions["deterministic_repair"] = det
        state.record(
            AgentRole.BUILDER,
            "deterministic_repair",
            f"actions={len(det.get('actions') or [])}",
        )
        try:
            from .trajectory import append_trajectory
            append_trajectory(
                state,
                step="deterministic_repair",
                role=AgentRole.BUILDER.value,
                ok=True,
                detail=",".join((det.get("actions") or [])[:8]),
            )
        except Exception:
            pass
    except Exception as exc:
        logger.debug("deterministic repair skip: %s", type(exc).__name__)

    try:
        from lumen.engine.services.cline_runtime.agent_loop import run_agent

        # More steps focused on edits; agent_loop clamps to 50
        max_steps = 16
        try:
            import os
            max_steps = max(8, min(30, int(os.getenv("CLINE_REPAIR_MAX_STEPS") or "16")))
        except ValueError:
            max_steps = 16

        agent_state = run_agent(
            work_dir=project,
            goal=goal,
            ir_dict=ir_dict,
            max_steps=max_steps,
        )
    except Exception as exc:
        logger.exception("incremental repair failed")
        state.build_success = False
        state.build_errors = [f"repair_exception:{type(exc).__name__}:{exc}"]
        state.record(AgentRole.BUILDER, "incremental_repair_error", type(exc).__name__)
        return state

    ok = bool(agent_state.ok or agent_state.files_written)
    state.build_success = ok or project.is_dir()
    state.generated_path = str(project.resolve())
    state.build_errors = list(agent_state.errors or [])[:20]
    state.extensions["worker_engine"] = "cline_incremental_repair"
    state.extensions["worker_meta"] = {
        "engine": "cline_incremental_repair",
        "stop_reason": agent_state.stop_reason,
        "files_written": list(agent_state.files_written or [])[:30],
        "steps": len(agent_state.steps or []),
        "ok": bool(agent_state.ok),
    }
    state.record(
        AgentRole.BUILDER,
        "incremental_repair_done",
        f"ok={agent_state.ok} files={len(agent_state.files_written or [])} stop={agent_state.stop_reason}",
    )
    try:
        from .trajectory import append_trajectory
        append_trajectory(
            state,
            step="worker_incremental_repair",
            role=AgentRole.BUILDER.value,
            ok=bool(agent_state.ok),
            detail=str(agent_state.stop_reason or ""),
            payload={"files": list(agent_state.files_written or [])[:15]},
        )
    except Exception:
        pass
    return state


__all__ = [
    "should_incremental_repair",
    "build_repair_goal",
    "run_incremental_repair",
]
