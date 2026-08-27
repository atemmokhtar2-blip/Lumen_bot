"""Coding agent worker — official Cline agent_loop (not a thin wrapper).

This is the real Worker engine used by the LangGraph multi-agent pipeline.
It runs the same autonomous plan→tool→observe loop as production Cline,
with elevated step budgets and code-intelligence context injection.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _step_budget(*, repair: bool = False) -> int:
    """Cursor-class sessions need enough steps for multi-file work."""
    key = "MULTI_AGENT_WORKER_MAX_STEPS" if not repair else "MULTI_AGENT_REPAIR_MAX_STEPS"
    default = "32" if not repair else "20"
    try:
        return max(12, min(60, int(os.getenv(key) or os.getenv("CLINE_AGENT_MAX_STEPS") or default)))
    except ValueError:
        return 32 if not repair else 20


def run_coding_session(
    *,
    work_dir: str | Path,
    goal: str,
    task_brief: str = "",
    ir_hint: dict[str, Any] | None = None,
    repair: bool = False,
    max_steps: int | None = None,
) -> dict[str, Any]:
    """Run official ``cline_runtime.agent_loop.run_agent``.

    Returns a serializable result dict (ok, path, files, errors, steps).
    """
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)

    full_goal = (goal or "").strip()
    if task_brief:
        full_goal = f"{full_goal}\n\n---\nFOCUS (must complete this task fully before finish):\n{task_brief}".strip()
    if repair:
        full_goal = (
            "MODE=INCREMENTAL_REPAIR\n"
            "Edit the existing project. Prefer edit_file. Never wipe the project.\n"
            "Fix ERROR findings only.\n\n" + full_goal
        )

    steps = int(max_steps if max_steps is not None else _step_budget(repair=repair))
    # Temporarily raise CLINE_AGENT_MAX_STEPS for this session
    prev = os.environ.get("CLINE_AGENT_MAX_STEPS")
    os.environ["CLINE_AGENT_MAX_STEPS"] = str(steps)

    hint = dict(ir_hint or {})
    # Inject code intelligence context when the tree already has files
    try:
        py_count = len(list(work.rglob("*.py")))
        if py_count >= 1:
            from lumen.engine.services.code_intelligence.repo_context import (
                pack_repo_context_for_goal,
                context_to_agent_block,
            )
            rc = pack_repo_context_for_goal(str(work), full_goal[:1500])
            block = context_to_agent_block(rc) if callable(context_to_agent_block) else ""
            if block:
                full_goal = f"{full_goal}\n\n--- REPO CONTEXT ---\n{block[:6000]}"
            hint["repo_context"] = {
                "py_file_count": rc.get("py_file_count"),
                "file_list": list(rc.get("file_list") or [])[:20],
            }
    except Exception as exc:
        logger.debug("code intel inject skipped: %s", exc)

    try:
        from lumen.engine.services.cline_runtime.agent_loop import run_agent

        agent_state = run_agent(str(work), full_goal[:12000], ir_hint=hint or None)
        ok = bool(getattr(agent_state, "ok", False))
        files = list(getattr(agent_state, "files_written", None) or [])
        errors = list(getattr(agent_state, "errors", None) or [])
        warnings = list(getattr(agent_state, "warnings", None) or [])
        meta = dict(getattr(agent_state, "metadata", None) or {})
        stop = str(getattr(agent_state, "stop_reason", "") or "")
        # Require real files for success
        if ok and not files:
            existing = [p.relative_to(work).as_posix() for p in work.rglob("*.py") if p.is_file()][:30]
            if not existing:
                ok = False
                errors.append("agent_finished_without_python_files")
            else:
                files = existing
        return {
            "ok": ok,
            "project_path": str(work) if ok or files else None,
            "files_written": files[:50],
            "errors": [str(e)[:300] for e in errors[:20]],
            "warnings": [str(w)[:200] for w in warnings[:20]],
            "steps": int(meta.get("steps") or 0),
            "stop_reason": stop,
            "acceptance": meta.get("acceptance"),
            "engine": "cline_agent_loop",
            "max_steps": steps,
        }
    except Exception as exc:
        logger.exception("coding session failed")
        return {
            "ok": False,
            "project_path": None,
            "files_written": [],
            "errors": [f"{type(exc).__name__}:{exc}"],
            "warnings": [],
            "steps": 0,
            "stop_reason": "exception",
            "engine": "cline_agent_loop",
            "max_steps": steps,
        }
    finally:
        if prev is None:
            os.environ.pop("CLINE_AGENT_MAX_STEPS", None)
        else:
            os.environ["CLINE_AGENT_MAX_STEPS"] = prev


__all__ = ["run_coding_session"]
