"""Autonomous agent loop — the core of free Cline path.

plan → tool call → observe → repeat until finish / max_steps / error.
Does NOT use catalog templates. Writes a real project under work_dir.
"""
from __future__ import annotations

import json
import logging
import os
import time as _time
from pathlib import Path
from typing import Any

from .agent_acceptance import check_agent_project
from .agent_brain import decide
from .agent_fs import run_tool
from .agent_state import AgentState, AgentStep
from .model_router import describe_runtime, select_model, select_model_for_goal

logger = logging.getLogger(__name__)


def _emit_progress(event: dict[str, Any]) -> None:
    """Push live progress to UI sink via engine progress_bus (no bot imports)."""
    try:
        from lumen.engine.services.progress_bus import report_progress
        report_progress(event)
    except Exception:
        pass


# Official tool surface — must match agent_fs.run_tool (no ghost names)
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

    This is the INNER guarantee (weakness #2): even if the outer
    run_with_engine_timeout is not active, the loop itself stops once the
    total elapsed time exceeds this budget. Default 150s — slightly under
    GENERATION_TIMEOUT_SEC (180s) so the loop finishes gracefully before the
    outer hard kill. Tunable via CLINE_AGENT_TIME_BUDGET_SEC. Capped [10, 600].
    """
    try:
        v = float(os.getenv("CLINE_AGENT_TIME_BUDGET_SEC") or "150")
    except ValueError:
        v = 150.0
    return max(10.0, min(v, 600.0))


def _governor_limits_for_band(band: str) -> dict[str, int]:
    """Dynamic step budget by task difficulty band (Phase-1 Loop Governor).

    easy   → tight budget (welcome / single-purpose bots)
    medium → standard
    hard   → more room (multi-feature / repair / large context)
    Absolute ceiling still respects CLINE_AGENT_MAX_STEPS when set.
    """
    band = (band or "medium").strip().lower()
    if band == "easy":
        return {"max_steps": 6, "history_keep_start": 10, "history_keep_end": 5,
                "prompt_chars_start": 12000, "prompt_chars_end": 7000}
    if band == "hard":
        return {"max_steps": 15, "history_keep_start": 14, "history_keep_end": 7,
                "prompt_chars_start": 16000, "prompt_chars_end": 9000}
    # medium default
    return {"max_steps": 10, "history_keep_start": 12, "history_keep_end": 6,
            "prompt_chars_start": 14000, "prompt_chars_end": 8000}


def _governor_progress_caps(
    *,
    step_index: int,
    limit: int,
    history_keep_start: int,
    history_keep_end: int,
    prompt_chars_start: int,
    prompt_chars_end: int,
) -> tuple[int, int]:
    """Linearly shrink history / prompt budget as the loop advances."""
    if limit <= 1:
        return history_keep_end, prompt_chars_end
    ratio = max(0.0, min(1.0, float(step_index) / float(limit - 1)))
    keep = int(round(history_keep_start + (history_keep_end - history_keep_start) * ratio))
    chars = int(round(prompt_chars_start + (prompt_chars_end - prompt_chars_start) * ratio))
    keep = max(4, min(16, keep))
    chars = max(4000, min(20000, chars))
    return keep, chars


def _tool_fingerprint(tool: str, args: dict[str, Any]) -> str:
    """Stable fingerprint for repeated-tool / empty-loop detection.

    Prefer path/command identity over large content blobs so that two write_file
    calls to different paths never collide after truncation.
    """
    args = dict(args or {})
    try:
        identity: dict[str, Any] = {"tool": str(tool or "")}
        for key in ("path", "file", "target", "name", "command", "cmd", "query", "pattern", "glob", "url"):
            if key in args and args[key] is not None:
                identity[key] = str(args[key])[:200]
        # Include a short content hash so identical path+identical content is detected
        content = args.get("content")
        if isinstance(content, str) and content:
            identity["content_len"] = len(content)
            identity["content_head"] = content[:80]
        # Fallback: sorted keys if nothing else
        if len(identity) <= 1:
            identity["keys"] = sorted(str(k) for k in args.keys())
        payload = json.dumps(identity, sort_keys=True, ensure_ascii=False)
    except Exception:
        payload = f"{tool}:{sorted(str(k) for k in args.keys())}"
    return payload[:500]



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



def run_agent(
    *,
    work_dir: str | Path,
    goal: str,
    ir_dict: dict[str, Any] | None = None,
    max_steps: int | None = None,
) -> AgentState:
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    # LLM observability (LangSmith when keyed) — real process setup
    try:
        from lumen.platform.observability import setup_observability
        setup_observability(service_name="lumen-agent")
    except Exception:
        pass
    # Guard goal text (fail-closed on injection)
    # Use scan_user_request_only to scan ONLY the user's original request,
    # not the full task packet that includes repo context / agent-generated code
    # (which can legitimately contain os.getenv('TELEGRAM_BOT_TOKEN') + print patterns).
    try:
        from lumen.engine.pipeline.prompt_guard import scan_user_request_only, scan_user_input
        # Primary scan: only the user's original request portion
        _gr = scan_user_request_only(goal or "")
        # Secondary scan: full goal for DANGEROUS code-exec patterns only
        # (os.system, eval, exec, subprocess shell=True, etc.) — these should
        # never appear anywhere, even in repo context
        if _gr.ok:
            _full = scan_user_input(goal or "")
            dangerous = {"os_system", "eval_call", "exec_call", "subprocess_shell",
                         "compile_exec", "dunder_import", "pickle_loads", "pty_spawn",
                         "write_malware", "tool_abuse"}
            dangerous_hits = [r for r in (_full.reasons or []) if r in dangerous]
            if dangerous_hits:
                _gr = PromptGuardResult(ok=False, reasons=dangerous_hits,
                                        sanitized=_full.sanitized, backend=_full.backend)
        if not _gr.ok:
            state = AgentState(work_dir=str(work.resolve()), goal=goal or "")
            state.ok = False
            state.stop_reason = "blocked_by_guardrails"
            state.errors.append("guardrails:" + ",".join(_gr.reasons)[:300])
            state.metadata["guardrails"] = {"ok": False, "reasons": list(_gr.reasons), "backend": _gr.backend}
            return state
        if _gr.sanitized:
            goal = _gr.sanitized
    except Exception as _gexc:
        state = AgentState(work_dir=str(work.resolve()), goal=goal or "")
        state.ok = False
        state.stop_reason = "guardrails_error"
        state.errors.append(f"guardrails_error:{type(_gexc).__name__}")
        return state
    state = AgentState(work_dir=str(work.resolve()), goal=goal or "")
    state.metadata["model"] = describe_runtime()
    task = "repair" if (
        "MODE=INCREMENTAL_REPAIR" in (goal or "")
        or (isinstance(ir_dict, dict) and (ir_dict.get("metadata") or {}).get("mode") == "incremental_repair")
    ) else "build"
    findings_n = 0
    feats: list = []
    if isinstance(ir_dict, dict):
        findings_n = len(ir_dict.get("findings") or (ir_dict.get("metadata") or {}).get("findings") or [])
        feats = list(ir_dict.get("preferred_keys") or ir_dict.get("features_requested") or [])
    choice, diff = select_model_for_goal(
        task=task,
        goal=goal or "",
        features=feats,
        findings_count=findings_n,
    )
    state.metadata["task_difficulty"] = diff
    if choice.provider == "none":
        state.stop_reason = "no_model"
        state.errors.append("no_llm_provider_configured")
        state.ok = False
        return state

    # --- Phase-1 Loop Governor: dynamic step budget by difficulty band ---
    _band = str((diff or {}).get("band") or "medium")
    _gov_limits = _governor_limits_for_band(_band)
    _env_ceiling = _max_steps()  # respects CLINE_AGENT_MAX_STEPS absolute cap
    if max_steps is not None:
        limit = max(1, min(int(max_steps), _env_ceiling))
        _gov_source = "explicit_max_steps"
    else:
        limit = max(1, min(int(_gov_limits["max_steps"]), _env_ceiling))
        _gov_source = f"band:{_band}"
    state.metadata["loop_governor"] = {
        "enabled": True,
        "band": _band,
        "difficulty_score": (diff or {}).get("score"),
        "max_steps": limit,
        "source": _gov_source,
        "env_ceiling": _env_ceiling,
        "history_keep_start": _gov_limits["history_keep_start"],
        "history_keep_end": _gov_limits["history_keep_end"],
        "prompt_chars_start": _gov_limits["prompt_chars_start"],
        "prompt_chars_end": _gov_limits["prompt_chars_end"],
        "repeated_tool_limit": 3,
        "steps_log": [],
        "stop_reason_detail": None,
        "total_prompt_tokens": 0,
        "total_completion_tokens": 0,
        "total_tokens_est": 0,
    }
    _emit_progress({
        "phase": "loop_start",
        "step": 0,
        "limit": limit,
        "detail": f"بدء حلقة الوكيل (governor band={_band} steps={limit})",
        "governor_band": _band,
    })
    user_id = 0
    if isinstance(ir_dict, dict):
        try:
            user_id = int(ir_dict.get("user_id") or 0)
        except (TypeError, ValueError):
            user_id = 0
    state.metadata["user_id"] = user_id
    try:
        from lumen.engine.services.generation_cancel import clear_cancel

        clear_cancel(user_id)
    except Exception:
        pass
    # Large-repo quality: pack hybrid retrieval context into the system prompt
    repo_ctx = None
    try:
        from lumen.engine.services.code_intelligence.repo_context import (
            pack_repo_context_for_goal,
            context_to_agent_block,
        )
        extra = []
        if isinstance(ir_dict, dict):
            extra = list((ir_dict.get("metadata") or {}).get("pre_read_files") or [])
            extra += list((ir_dict.get("project_context") or {}).get("file_list") or [])
        repo_ctx = pack_repo_context_for_goal(state.work_dir, goal or "", extra_paths=extra)
        state.metadata["repo_context"] = {
            "ok": repo_ctx.get("ok"),
            "file_list": list(repo_ctx.get("file_list") or [])[:20],
            "py_file_count": repo_ctx.get("py_file_count"),
            "graph_stats": repo_ctx.get("graph_stats"),
        }
        # Mark retrieved files as pre-read for repair policy
        state.metadata.setdefault("read_files", [])
        for fp in repo_ctx.get("file_list") or []:
            if fp not in state.metadata["read_files"]:
                state.metadata["read_files"].append(fp)
    except Exception as _rc_exc:
        state.metadata["repo_context_error"] = type(_rc_exc).__name__
        repo_ctx = None
    sys_prompt = _system_prompt(state.work_dir, goal, ir_dict)
    sys_prompt = sys_prompt + (
        "\n\nMULTI-FILE TOOLS:\n"
        "- grep_codebase(pattern), glob_files(pattern), read_files(paths=[...])\n"
        "- apply_edits(edits=[{path,old_string,new_string}, ...]) atomic multi-file\n"
        "- apply_patch(patch=unified diff or *** Update File blocks)\n"
        "- edit_file requires unique old_string unless replace_all=true\n"
        "Prefer apply_edits/apply_patch for changes spanning multiple files.\nCODE INTEL: find_symbol(name), get_symbol_source(name), find_references(name), blast_radius(name|path), code_search(query) — use BEFORE large multi-file edits.\n"
    )
    if repo_ctx and repo_ctx.get("files"):
        try:
            from lumen.engine.services.code_intelligence.repo_context import context_to_agent_block
            sys_prompt = sys_prompt + "\n\n" + context_to_agent_block(repo_ctx)
        except Exception:
            pass
    state.add_system(sys_prompt)
    # Pre-mark files already packed into context as read (repair policy)
    pre_read = []
    if isinstance(ir_dict, dict):
        meta = ir_dict.get("metadata") if isinstance(ir_dict.get("metadata"), dict) else {}
        pre_read = list(meta.get("pre_read_files") or [])
        for path in list((ir_dict.get("project_context") or {}).get("file_list") or []):
            pre_read.append(path)
    if pre_read:
        state.metadata["read_files"] = sorted(set(str(x) for x in pre_read if x))
    repair_mode = "MODE=INCREMENTAL_REPAIR" in (goal or "") or (
        isinstance(ir_dict, dict)
        and (ir_dict.get("metadata") or {}).get("mode") == "incremental_repair"
    )
    if repair_mode:
        state.add_user(
            "REPAIR MODE: Workspace snapshot is in the system/goal. "
            "Fix ERROR findings with edit_file/apply_patch. "
            "If you need another file, read_file first. Then finish."
        )
    else:
        state.add_user(
            "Start building now. Use grep_codebase/glob_files/list_dir to map the project, read_files for context, then apply_edits or write_file/edit_file across all needed files."
        )

    # Wall-clock budget — the INNER time guarantee (weakness #2 root fix).
    # The loop stops as soon as total elapsed exceeds _time_budget(), even if
    # max_steps has not been reached. This prevents the "10-minute hang" when
    # the LLM is slow or retries stack up.
    _budget_sec = _time_budget()
    _loop_start = _time.monotonic()
    _deadline = _loop_start + _budget_sec
    state.metadata["time_budget_sec"] = _budget_sec

    # Loop Governor runtime state
    _gov = state.metadata.get("loop_governor") or {}
    _hist_start = int(_gov.get("history_keep_start") or 12)
    _hist_end = int(_gov.get("history_keep_end") or 6)
    _chars_start = int(_gov.get("prompt_chars_start") or 14000)
    _chars_end = int(_gov.get("prompt_chars_end") or 8000)
    _repeated_limit = int(_gov.get("repeated_tool_limit") or 3)
    _last_fingerprint: str | None = None
    _repeat_count = 0
    _gov_steps_log: list[dict[str, Any]] = list(_gov.get("steps_log") or [])

    for i in range(limit):
        # --- Progressive context shrinkage (Loop Governor) ---
        _keep, _pchars = _governor_progress_caps(
            step_index=i,
            limit=limit,
            history_keep_start=_hist_start,
            history_keep_end=_hist_end,
            prompt_chars_start=_chars_start,
            prompt_chars_end=_chars_end,
        )
        # agent_brain._system_and_user reads these env vars on every decide()
        os.environ["CLINE_HISTORY_KEEP"] = str(_keep)
        os.environ["CLINE_PROMPT_MAX_CHARS"] = str(_pchars)

        # TIME-BUDGET CUTOFF: stop the loop if the wall-clock budget is exhausted.
        _now = _time.monotonic()
        if _now >= _deadline:
            _elapsed = int(_now - _loop_start)
            state.stop_reason = "time_budget_exhausted"
            state.ok = False
            state.warnings.append(f"time_budget_exhausted:{_elapsed}s>={int(_budget_sec)}s")
            state.metadata["time_budget_exhausted"] = True
            state.metadata["elapsed_sec"] = _elapsed
            logger.warning(
                "agent_loop time budget exhausted: %ds >= %ds budget (step %d/%d)",
                _elapsed, int(_budget_sec), i, limit,
            )
            # Attempt a graceful finish: check if anything was built so far.
            try:
                acc = check_agent_project(state.work_dir, goal=goal)
                state.metadata["acceptance"] = acc
                if acc.get("ok"):
                    state.stop_reason = "completed_within_budget"
                    state.ok = True
                    state.metadata["summary"] = "auto_finish_time_budget_ok"
            except Exception:
                pass
            break
        try:
            from lumen.engine.services.generation_cancel import is_cancelled

            if is_cancelled(user_id):
                state.stop_reason = "cancelled_by_user"
                state.ok = False
                state.warnings.append("generation_cancelled")
                state.metadata["cancelled"] = True
                break
        except Exception:
            pass
        msgs = [m.to_dict() for m in state.messages]
        _emit_progress({
            "phase": "thinking",
            "step": i,
            "limit": limit,
            "tool": "thinking",
            "detail": f"الوكيل يفكر في الخطوة {i}/{limit}…",
            "files_written": len(state.files_written or []),
        })
        decision = decide(msgs, choice=choice)
        _emit_progress({
            "phase": "decided",
            "step": i,
            "limit": limit,
            "tool": str(decision.get("tool") or "thinking"),
            "thought": str(decision.get("thought") or "")[:160],
            "detail": "اتخذ قرار الخطوة",
            "files_written": len(state.files_written or []),
        })
        # Phase A cost: accumulate real provider usage when present
        try:
            u = decision.get("usage") or {}
            if u:
                accu = dict(state.metadata.get("usage") or {})
                accu["calls"] = int(accu.get("calls") or 0) + 1
                for k in ("prompt_tokens", "completion_tokens", "total_tokens", "prompt_tokens_est"):
                    if u.get(k):
                        accu[k] = int(accu.get(k) or 0) + int(u[k])
                accu["last_provider"] = u.get("provider") or accu.get("last_provider")
                accu["last_model"] = u.get("model_id") or accu.get("last_model")
                if u.get("estimated"):
                    accu["estimated"] = True
                state.metadata["usage"] = accu
                # Mirror into loop_governor totals
                _gov = state.metadata.setdefault("loop_governor", {})
                _gov["total_prompt_tokens"] = int(_gov.get("total_prompt_tokens") or 0) + int(u.get("prompt_tokens") or 0)
                _gov["total_completion_tokens"] = int(_gov.get("total_completion_tokens") or 0) + int(u.get("completion_tokens") or 0)
                _gov["total_tokens_est"] = int(_gov.get("total_tokens_est") or 0) + int(
                    u.get("total_tokens") or u.get("prompt_tokens_est") or 0
                )
        except Exception:
            pass
        # Governor per-step log (before tool execution)
        try:
            _gov_steps_log.append({
                "step": i,
                "event": "decide",
                "tool": str(decision.get("tool") or ""),
                "finish": bool(decision.get("finish")),
                "history_keep": _keep,
                "prompt_chars": _pchars,
                "parse_ok": bool(decision.get("parse_ok", True)),
                "elapsed_sec": round(_time.monotonic() - _loop_start, 2),
                "cache_hit": bool(decision.get("cache_hit")),
            })
            state.metadata.setdefault("loop_governor", {})["steps_log"] = _gov_steps_log[-60:]
        except Exception:
            pass
        step = AgentStep(
            index=i,
            thought=str(decision.get("thought") or ""),
            tool_name=decision.get("tool"),
            tool_args=dict(decision.get("args") or {}),
            raw_model=str(decision.get("raw") or ""),
        )

        err = str(decision.get("error") or "")
        # Soft errors: keep looping (model format / transient). Hard errors abort.
        soft = (
            not err
            or err.startswith("parse_fail")
            or "parse_fail" in err
            or "empty_content" in err
            or "empty_choices" in err
        )
        if decision.get("error") and not soft:
            step.tool_result = {"ok": False, "error": decision["error"]}
            state.steps.append(step)
            state.errors.append(str(decision["error"]))
            state.stop_reason = "error"
            state.ok = False
            break

        if (not decision.get("parse_ok") and not decision.get("tool")) or (
            decision.get("error") and soft
        ):
            raw_snip = str(decision.get("raw") or decision.get("thought") or "")[:500]
            state.add_assistant(raw_snip or "(invalid)")
            state.add_user(
                "INVALID. Reply with ONLY this JSON shape:\n"
                '{"thought":"...","tool":"write_file","args":{"path":"main.py","content":"..."},'
                '"finish":false,"summary":""}\n'
                "Valid tools: " + ", ".join(AGENT_TOOL_NAMES) + "."
            )
            state.steps.append(step)
            state.warnings.append(f"parse_fail_step_{i}:{err[:80]}")
            continue

        tool = decision.get("tool")
        args = dict(decision.get("args") or {})

        # --- Loop Governor: hard-stop on repeated identical tool calls (empty loop) ---
        if tool and tool != "finish":
            _fp = _tool_fingerprint(str(tool), args)
            if _fp and _fp == _last_fingerprint:
                _repeat_count += 1
            else:
                _repeat_count = 1
                _last_fingerprint = _fp
            if _repeat_count >= _repeated_limit:
                state.stop_reason = "repeated_tool_loop"
                state.ok = False
                state.warnings.append(
                    f"repeated_tool_loop:{tool}x{_repeat_count}"
                )
                state.errors.append(
                    f"empty_loop_detected tool={tool} repeats={_repeat_count}"
                )
                _gov = state.metadata.setdefault("loop_governor", {})
                _gov["stop_reason_detail"] = {
                    "reason": "repeated_tool_loop",
                    "tool": str(tool),
                    "repeats": _repeat_count,
                    "fingerprint": _fp[:200],
                    "step": i,
                }
                _gov_steps_log.append({
                    "step": i,
                    "event": "hard_stop_repeated_tool",
                    "tool": str(tool),
                    "repeats": _repeat_count,
                    "history_keep": _keep,
                    "prompt_chars": _pchars,
                    "elapsed_sec": round(_time.monotonic() - _loop_start, 2),
                })
                _gov["steps_log"] = _gov_steps_log
                logger.warning(
                    "agent_loop hard-stop: tool %s repeated %d times (step %d/%d)",
                    tool, _repeat_count, i, limit,
                )
                step.tool_result = {
                    "ok": False,
                    "error": "repeated_tool_loop",
                    "tool": str(tool),
                    "repeats": _repeat_count,
                }
                state.steps.append(step)
                break

        # Phase A policy: repair mode requires read_file before edit on same path
        repair_mode = "MODE=INCREMENTAL_REPAIR" in (goal or "") or (
            isinstance(ir_dict, dict)
            and (
                (ir_dict.get("metadata") or {}).get("mode") == "incremental_repair"
                or bool(ir_dict.get("repair_directive") or ir_dict.get("findings"))
            )
        )
        read_set = set(state.metadata.get("read_files") or [])
        if tool in {"edit_file", "apply_patch", "search_replace"} and repair_mode:
            target = str(args.get("path") or "")
            if target and target not in read_set:
                state.add_assistant(step.thought or "edit blocked")
                state.add_user(
                    f"POLICY: read_file path={target} before edit_file/apply_patch in repair mode."
                )
                step.tool_result = {"ok": False, "error": "read_before_edit_required", "path": target}
                state.steps.append(step)
                state.warnings.append(f"policy_read_before_edit:{target}")
                continue
        if tool == "read_file":
            rp = str(args.get("path") or "")
            if rp:
                read_set.add(rp)
                state.metadata["read_files"] = sorted(read_set)
        if repair_mode and tool == "write_file":
            wp = str(args.get("path") or "")
            # allow write only for missing files; if exists, force edit
            from pathlib import Path as _P
            if wp and (_P(state.work_dir) / wp).is_file() and wp in {"main.py"}:
                state.add_user(
                    f"POLICY: {wp} exists — use edit_file/apply_patch, not write_file full overwrite."
                )
                step.tool_result = {"ok": False, "error": "prefer_edit_not_overwrite", "path": wp}
                state.steps.append(step)
                state.warnings.append(f"policy_prefer_edit:{wp}")
                continue

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
            # acceptance failed — deterministic local fix then re-check before LLM loop
            state.warnings.append("acceptance_soft_fail:" + ",".join(acc.get("missing") or [])[:200])
            try:
                from lumen.engine.services.multi_agent.deterministic_repair import (
                    apply_deterministic_repairs,
                )
                det = apply_deterministic_repairs(state.work_dir)
                state.metadata["deterministic_on_accept"] = det
                acc2 = check_agent_project(state.work_dir, goal=goal)
                state.metadata["acceptance"] = acc2
                if acc2.get("ok"):
                    state.stop_reason = "completed_by_deterministic"
                    state.ok = True
                    break
            except Exception as exc:
                state.warnings.append(f"det_accept_skip:{type(exc).__name__}")
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

        _path_hint = ""
        _detail_hint = ""
        try:
            if isinstance(args, dict):
                _path_hint = str(
                    args.get("path") or args.get("file") or args.get("target")
                    or args.get("name") or ""
                )[:200]
                if tool in {"run_shell", "bash", "shell"}:
                    _detail_hint = str(args.get("command") or args.get("cmd") or "")[:160]
                elif tool in {"grep_codebase", "code_search", "glob_files"}:
                    _detail_hint = str(args.get("query") or args.get("pattern") or args.get("glob") or "")[:120]
                elif tool in {"browser_navigate", "browser_content"}:
                    _detail_hint = str(args.get("url") or args.get("query") or "")[:120]
                elif tool in {"write_file", "edit_file", "search_replace"}:
                    _detail_hint = str(args.get("path") or args.get("file") or "")[:120]
        except Exception:
            _path_hint = ""
            _detail_hint = ""
        _emit_progress({
            "phase": "tool_start",
            "step": i,
            "limit": limit,
            "tool": str(tool),
            "path": _path_hint,
            "detail": _detail_hint,
            "thought": (step.thought or "")[:160],
            "files_written": len(state.files_written or []),
        })
        _t0 = _time.monotonic()
        result = run_tool(state.work_dir, str(tool), args)
        _elapsed_ms = int((_time.monotonic() - _t0) * 1000)
        if isinstance(result, dict):
            result = dict(result)
            result["elapsed_ms"] = _elapsed_ms
            try:
                from lumen.bot.sanitize import sanitize_log_text

                for _k in ("stdout", "stderr", "content", "message", "error"):
                    if isinstance(result.get(_k), str):
                        result[_k] = sanitize_log_text(result[_k], max_len=8000)
            except Exception:
                pass
        step.tool_result = result
        try:
            timings = list(state.metadata.get("tool_timings") or [])
            timings.append({"step": i, "tool": str(tool), "elapsed_ms": _elapsed_ms, "ok": bool((result or {}).get("ok"))})
            state.metadata["tool_timings"] = timings[-40:]
        except Exception:
            pass
        _emit_progress({
            "phase": "tool_done",
            "step": i,
            "limit": limit,
            "tool": str(tool),
            "path": _path_hint or str((result or {}).get("path") or "")[:200],
            "ok": bool((result or {}).get("ok")),
            "thought": (step.thought or "")[:160],
            "detail": (
                str((result or {}).get("error") or (result or {}).get("message") or "")[:120]
                or _detail_hint
            ),
            "files_written": len(state.files_written or []),
            "elapsed_ms": _elapsed_ms,
        })
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
        # Phase A: force finish path when core deliverables already satisfy acceptance
        try:
            from pathlib import Path as _P
            root = _P(state.work_dir)
            core = [
                (root / "main.py").is_file() or (root / "bot.py").is_file() or (root / "app.py").is_file(),
                (root / "app" / "handlers.py").is_file() or (root / "handlers.py").is_file(),
                (root / "requirements.txt").is_file() or (root / "pyproject.toml").is_file(),
            ]
            if sum(1 for x in core if x) >= 2 and i >= 2:
                acc_now = check_agent_project(state.work_dir, goal=goal)
                state.metadata["acceptance_mid"] = acc_now
                if acc_now.get("ok"):
                    # Explicit finish — do not burn remaining max_steps
                    fin = run_tool(state.work_dir, "finish", {"summary": "auto_finish_deliverables_ok"})
                    state.steps.append(
                        AgentStep(
                            index=i + 1,
                            thought="deliverables accepted — forced finish",
                            tool_name="finish",
                            tool_args={"summary": "auto_finish_deliverables_ok"},
                            tool_result=fin,
                        )
                    )
                    state.metadata["acceptance"] = acc_now
                    state.metadata["forced_finish"] = True
                    state.stop_reason = "completed"
                    state.ok = True
                    state.add_user("finish (forced after acceptance ok)")
                    break
                state.add_user(
                    "Core files present. Add any missing README/.env.example if needed, then call finish NOW."
                )
                # second consecutive nudge without finish → force finish attempt next loop via flag
                nudges = int(state.metadata.get("finish_nudges") or 0) + 1
                state.metadata["finish_nudges"] = nudges
                if nudges >= 2:
                    fin = run_tool(state.work_dir, "finish", {"summary": "auto_finish_after_nudges"})
                    state.steps.append(
                        AgentStep(
                            index=i + 1,
                            thought="finish after repeated deliverable nudges",
                            tool_name="finish",
                            tool_args={"summary": "auto_finish_after_nudges"},
                            tool_result=fin,
                        )
                    )
                    acc2 = check_agent_project(state.work_dir, goal=goal)
                    state.metadata["acceptance"] = acc2
                    state.metadata["forced_finish"] = True
                    if acc2.get("ok"):
                        state.stop_reason = "completed"
                        state.ok = True
                        break
                    state.stop_reason = "finish_forced_incomplete"
                    state.ok = False
                    break
        except Exception:
            pass
        if tool == "edit_file" and result.get("ok") and args.get("path"):
            path = str(args["path"])
            if path not in state.files_written:
                state.files_written.append(path)
    else:
        state.stop_reason = "max_steps"
        state.warnings.append(f"hit_max_steps_{limit}")
        # Phase A: local deliverable fill before declaring partial success
        try:
            from lumen.engine.services.multi_agent.deterministic_repair import (
                apply_deterministic_repairs,
            )
            det = apply_deterministic_repairs(state.work_dir)
            state.metadata["deterministic_on_max_steps"] = det
            if det.get("actions"):
                state.warnings.append("det_fill:" + ",".join(det["actions"][:6]))
        except Exception as exc:
            state.warnings.append(f"det_max_skip:{type(exc).__name__}")
        try:
            acc = check_agent_project(state.work_dir, goal=goal)
            state.metadata["acceptance"] = acc
            if acc.get("ok"):
                state.ok = True
                state.stop_reason = "completed_after_max_steps_det"
            else:
                state.ok = bool(state.files_written)
        except Exception:
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

    # --- Finalize Loop Governor report ---
    try:
        _gov = state.metadata.setdefault("loop_governor", {})
        _gov["final_steps"] = len(state.steps)
        _gov["final_stop_reason"] = state.stop_reason
        _gov["final_ok"] = bool(state.ok)
        _gov["elapsed_sec"] = round(_time.monotonic() - _loop_start, 2) if "_loop_start" in dir() else None
        # Re-sync steps_log if local var still in scope
        try:
            _gov["steps_log"] = _gov_steps_log[-60:]
        except NameError:
            pass
        if not _gov.get("stop_reason_detail") and state.stop_reason:
            _gov["stop_reason_detail"] = {"reason": state.stop_reason}
        # Snapshot final progressive caps used
        _gov["final_history_keep"] = os.environ.get("CLINE_HISTORY_KEEP")
        _gov["final_prompt_chars"] = os.environ.get("CLINE_PROMPT_MAX_CHARS")
    except Exception as _gov_fin_exc:
        try:
            state.metadata.setdefault("loop_governor", {})["finalize_error"] = type(_gov_fin_exc).__name__
        except Exception:
            pass

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
