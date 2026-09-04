"""Coding agent worker — official Cline agent_loop with layered context.

Layers:
  1. StepBudget     — elevated autonomous steps for multi-file work
  2. TaskPacket     — goal + acceptance criteria + target files (forces completion criteria)
  3. RepoContext    — hybrid retrieval + symbol graph when workspace has code
  4. SymbolOutline  — AST find_symbol top definitions for entry files
  5. Session        — run_agent with injected IR metadata (pre_read, code intel)
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---- Layer 1 ----
def step_budget(*, repair: bool = False) -> int:
    key = "MULTI_AGENT_WORKER_MAX_STEPS" if not repair else "MULTI_AGENT_REPAIR_MAX_STEPS"
    default = "40" if not repair else "24"
    try:
        return max(16, min(80, int(os.getenv(key) or os.getenv("CLINE_AGENT_MAX_STEPS") or default)))
    except ValueError:
        return 40 if not repair else 24


# ---- Layer 2 ----
def build_task_packet(
    *,
    goal: str,
    task_brief: str = "",
    acceptance: list[str] | None = None,
    target_files: list[str] | None = None,
    repair: bool = False,
    constraints: list[str] | None = None,
) -> str:
    """Compose a strict worker brief the agent must satisfy before finish."""
    parts: list[str] = []
    g = (goal or "").strip()
    if g:
        parts.append(g)
    if task_brief:
        parts.append("---\nTASK (complete fully before finish):\n" + task_brief.strip())
    if target_files:
        parts.append("TARGET FILES:\n" + "\n".join(f"- {p}" for p in target_files[:20]))
    if acceptance:
        parts.append(
            "ACCEPTANCE CRITERIA (must all be true before calling finish):\n"
            + "\n".join(f"- [ ] {a}" for a in acceptance[:15])
        )
    if constraints:
        parts.append("CONSTRAINTS:\n" + "\n".join(f"- {c}" for c in constraints[:12]))
    if repair:
        parts.insert(
            0,
            "MODE=INCREMENTAL_REPAIR\n"
            "Edit existing project. Prefer edit_file/apply_edits. Never wipe the project.\n"
            "Fix ERROR findings only.",
        )
    parts.append(
        "HARD GATE: do not call finish until EVERY acceptance checkbox is satisfied.\n"
        "PROTOCOL:\n"
        "- Use find_symbol / grep_codebase before large edits\n"
        "- Prefer apply_edits for multi-file changes\n"
        "- After edits run verification (compile/import) when possible\n"
        "- Do not call finish until acceptance criteria are met"
    )
    return "\n\n".join(parts).strip()


# ---- Layer 3 + 4 ----
def build_worker_context(work_dir: Path, goal: str, target_files: list[str] | None = None) -> dict[str, Any]:
    """Repo retrieval + symbol outline for entrypoints."""
    ctx: dict[str, Any] = {
        "repo_block": "",
        "symbol_outline": [],
        "pre_read_files": [],
        "errors": [],
    }
    try:
        py_files = [p for p in work_dir.rglob("*.py") if p.is_file()][:80]
    except Exception:
        py_files = []
    if not py_files:
        return ctx

    # Pre-read targets + entrypoints
    pre: list[str] = []
    for name in list(target_files or []) + ["main.py", "bot.py", "app.py"]:
        if name and (work_dir / name).is_file() and name not in pre:
            pre.append(name)
    ctx["pre_read_files"] = pre[:12]

    try:
        from lumen.engine.services.code_intelligence.repo_context import (
            pack_repo_context_for_goal,
            context_to_agent_block,
        )
        rc = pack_repo_context_for_goal(str(work_dir), goal[:2000], extra_paths=pre)
        block = context_to_agent_block(rc) if callable(context_to_agent_block) else ""
        if block:
            ctx["repo_block"] = block
        for fp in list((rc or {}).get("file_list") or [])[:10]:
            if fp not in ctx["pre_read_files"]:
                ctx["pre_read_files"].append(str(fp))
    except Exception as exc:
        ctx["errors"].append(f"repo_context:{type(exc).__name__}")
        logger.debug("repo_context failed: %s", exc)

    # Symbol outline from official tree-sitter symbol graph (not keyword guessing)
    try:
        from lumen.engine.services.code_intelligence.symbol_graph import build_symbol_graph
        g = build_symbol_graph(work_dir, max_files=200)
        nodes = list(g.get("nodes") or [])
        # Prefer functions/classes; skip pure modules
        ranked = [
            n for n in nodes
            if n.get("kind") in {"function", "method", "class"}
        ]
        # Entry-file bias
        def _score(n: dict) -> int:
            path = str(n.get("path") or "")
            s = 0
            if path.endswith("main.py") or path.endswith("bot.py") or path.endswith("app.py"):
                s += 10
            if n.get("kind") == "class":
                s += 2
            return -s
        ranked.sort(key=_score)
        ctx["symbol_outline"] = [
            {
                "id": n.get("id"),
                "name": n.get("name"),
                "kind": n.get("kind"),
                "path": n.get("path"),
                "start_line": n.get("start_line"),
                "end_line": n.get("end_line"),
            }
            for n in ranked[:25]
        ]
    except Exception as exc:
        ctx["errors"].append(f"symbols:{type(exc).__name__}")
        try:
            from lumen.engine.services.cline_runtime.agent_code_intel import find_symbol
            for seed in ("main", "start", "handle"):
                r = find_symbol(str(work_dir), seed, max_results=5)
                if r.get("ok"):
                    ctx["symbol_outline"].extend(r.get("symbols") or [])
        except Exception as exc2:
            ctx["errors"].append(f"symbols_fallback:{type(exc2).__name__}")

    return ctx


def _outline_block(symbols: list[dict[str, Any]]) -> str:
    if not symbols:
        return ""
    lines = ["SYMBOL OUTLINE (AST):"]
    for s in symbols[:15]:
        lines.append(
            f"- {s.get('kind')} {s.get('name')} @ {s.get('path')}:{s.get('start_line')}-{s.get('end_line')}"
        )
    return "\n".join(lines)


# ---- Layer 5 ----
def run_coding_session(
    *,
    work_dir: str | Path,
    goal: str,
    task_brief: str = "",
    ir_hint: dict[str, Any] | None = None,
    repair: bool = False,
    max_steps: int | None = None,
    acceptance: list[str] | None = None,
    target_files: list[str] | None = None,
    constraints: list[str] | None = None,
    user_id: int = 0,
) -> dict[str, Any]:
    """Run official ``cline_runtime.agent_loop.run_agent`` with full context stack."""
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)

    packet = build_task_packet(
        goal=goal,
        task_brief=task_brief,
        acceptance=acceptance,
        target_files=target_files,
        repair=repair,
        constraints=constraints,
    )
    wctx = build_worker_context(work, packet, target_files=target_files)
    outline = _outline_block(list(wctx.get("symbol_outline") or []))
    # Blast-radius advisory for repair / multi-file (official code_intelligence)
    blast_block = ""
    if repair or (target_files and len(target_files) > 1):
        try:
            from lumen.engine.services.code_intelligence.blast_radius import blast_radius
            seeds = list(target_files or [])[:3]
            br = blast_radius(str(work), path=seeds[0] if seeds else "", symbol_name="", max_depth=2)
            if br.get("ok"):
                imp = br.get("impacted_files") or []
                blast_block = "BLAST RADIUS (impacted files):\n" + "\n".join(f"- {x}" for x in list(imp)[:15])
        except Exception:
            pass
    full_goal = packet
    if blast_block:
        full_goal = full_goal + "\n\n" + blast_block
    if wctx.get("repo_block"):
        full_goal = full_goal + "\n\n" + str(wctx["repo_block"])[:6000]
    if outline:
        full_goal = full_goal + "\n\n" + outline

    steps = int(max_steps if max_steps is not None else step_budget(repair=repair))
    prev = os.environ.get("CLINE_AGENT_MAX_STEPS")
    os.environ["CLINE_AGENT_MAX_STEPS"] = str(steps)

    hint = dict(ir_hint or {})
    # E2E cancel: agent_loop polls is_cancelled(user_id)
    try:
        uid = int(user_id or hint.get("user_id") or 0)
    except (TypeError, ValueError):
        uid = 0
    if uid:
        hint["user_id"] = uid
    meta = dict(hint.get("metadata") or {})
    meta["pre_read_files"] = list(dict.fromkeys(
        list(meta.get("pre_read_files") or []) + list(wctx.get("pre_read_files") or [])
    ))[:20]
    meta["acceptance"] = list(acceptance or [])[:20]
    meta["worker_context_errors"] = list(wctx.get("errors") or [])
    hint["metadata"] = meta
    if meta["pre_read_files"]:
        pc = dict(hint.get("project_context") or {})
        pc["file_list"] = list(dict.fromkeys(
            list(pc.get("file_list") or []) + meta["pre_read_files"]
        ))[:30]
        hint["project_context"] = pc

    try:
        from lumen.engine.services.cline_runtime.agent_loop import run_agent
        try:
            from lumen.engine.services.progress_bus import report_progress
            report_progress({
                "phase": "coding_agent",
                "detail": "بدء وكيل البرمجة (Cline)",
                "step": 0,
            })
        except Exception:
            pass

        state = run_agent(
            work_dir=str(work),
            goal=full_goal[:20000],
            ir_dict=hint,
            max_steps=steps,
        )
        ok = bool(getattr(state, "ok", False) or getattr(state, "finished", False))
        files = []
        try:
            files = [
                p.relative_to(work).as_posix()
                for p in work.rglob("*")
                if p.is_file() and not any(x in p.parts for x in (".git", "__pycache__", ".swarm_w"))
            ][:80]
        except Exception:
            pass
        # Layer: post-session acceptance (AST) — session claims are not enough
        acc_rep = {"ok": True, "skipped": True}
        try:
            from .acceptance_check import evaluate_task
            acc_rep = evaluate_task(
                work,
                files=list(target_files or []),
                acceptance=list(acceptance or []),
                strict=True,
            )
            if not acc_rep.get("ok"):
                ok = False
        except Exception as _acc_exc:
            acc_rep = {"ok": False, "error": type(_acc_exc).__name__}
            ok = False

        router = (getattr(state, "metadata", None) or {}).get("router") or {}
        return {
            "ok": ok,
            "path": str(work),
            "files": files,
            "files_written": files,
            "steps": len(getattr(state, "steps", None) or []),
            "stop_reason": str(getattr(state, "stop_reason", "") or ""),
            "errors": list(getattr(state, "errors", None) or [])[:20],
            "acceptance": list(acceptance or []),
            "acceptance_report": acc_rep,
            "context_errors": list(wctx.get("errors") or []),
            "engine": "cline_agent_loop+layered_context+acceptance",
            "router": router,
            "provider": (router or {}).get("provider"),
            "model_id": (router or {}).get("model_id"),
            "user_id": int(hint.get("user_id") or 0),
            "agent_metadata": dict(getattr(state, "metadata", None) or {}),
        }
    except Exception as exc:
        logger.exception("run_coding_session failed")
        return {
            "ok": False,
            "path": str(work),
            "files": [],
            "errors": [f"{type(exc).__name__}:{exc}"],
            "engine": "cline_agent_loop_error",
        }
    finally:
        if prev is None:
            os.environ.pop("CLINE_AGENT_MAX_STEPS", None)
        else:
            os.environ["CLINE_AGENT_MAX_STEPS"] = prev


# backward alias
_step_budget = step_budget

__all__ = [
    "step_budget",
    "build_task_packet",
    "build_worker_context",
    "run_coding_session",
]
