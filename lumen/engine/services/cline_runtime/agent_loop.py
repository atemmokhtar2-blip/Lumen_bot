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
from dataclasses import dataclass, field
from typing import Any

from .agent_acceptance import check_agent_project
from .agent_brain import decide
from .agent_fs import run_tool
from .agent_state import AgentState, AgentStep
from .model_router import describe_runtime, select_model, select_model_for_goal
from .structured_recovery import StructuredRecovery

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
        v = 150
@dataclass
class LoopGovernor:
    """Explicit controller for the agent loop (Phase-1).

    Owns: dynamic step budget, progressive context caps, empty-loop detection
    (repeated tool + no-progress), and the authoritative loop_governor report.
    """

    band: str
    difficulty_score: float | None
    max_steps: int
    source: str
    env_ceiling: int
    history_keep_start: int
    history_keep_end: int
    prompt_chars_start: int
    prompt_chars_end: int
    repeated_tool_limit: int = 3
    no_progress_limit: int = 3

    # runtime
    step_index: int = 0
    last_fingerprint: str | None = None
    repeat_count: int = 0
    no_progress_streak: int = 0
    files_at_last_progress: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens_est: int = 0
    steps_log: list = field(default_factory=list)
    stop_reason_detail: dict | None = None
    loop_start: float = 0.0

    _INSPECT_TOOLS: frozenset = frozenset({
        "list_dir", "tree", "read_file", "read_files", "grep_codebase",
        "glob_files", "find_symbol", "get_symbol_source", "find_references",
        "blast_radius", "code_search", "browser_content", "browser_screenshot",
    })

    @classmethod
    def from_difficulty(
        cls,
        diff: dict[str, Any] | None,
        *,
        explicit_max_steps: int | None = None,
    ) -> "LoopGovernor":
        band = str((diff or {}).get("band") or "medium").strip().lower()
        limits = _band_limits(band)
        # Env override only when CLINE_AGENT_MAX_STEPS is *explicitly* set.
        # Default ceiling must not defeat hard-band (14).
        raw_env = (os.getenv("CLINE_AGENT_MAX_STEPS") or "").strip()
        if raw_env:
            try:
                env_ceiling = max(5, min(50, int(raw_env)))
            except ValueError:
                env_ceiling = 15
        else:
            env_ceiling = 15  # allows hard band full budget
        if explicit_max_steps is not None:
            max_steps = max(1, min(int(explicit_max_steps), env_ceiling))
            source = "explicit_max_steps"
        else:
            max_steps = max(1, min(int(limits["max_steps"]), env_ceiling))
            source = f"band:{band}"
        return cls(
            band=band,
            difficulty_score=(diff or {}).get("score"),
            max_steps=max_steps,
            source=source,
            env_ceiling=env_ceiling,
            history_keep_start=int(limits["history_keep_start"]),
            history_keep_end=int(limits["history_keep_end"]),
            prompt_chars_start=int(limits["prompt_chars_start"]),
            prompt_chars_end=int(limits["prompt_chars_end"]),
            repeated_tool_limit=3,
            no_progress_limit=int(limits["no_progress_limit"]),
        )

    def start(self) -> None:
        self.loop_start = _time.monotonic()

    def context_caps(self) -> tuple[int, int]:
        """Progressive history_keep + prompt_max_chars for the current step."""
        limit = max(1, self.max_steps)
        if limit <= 1:
            return self.history_keep_end, self.prompt_chars_end
        ratio = max(0.0, min(1.0, float(self.step_index) / float(limit - 1)))
        keep = int(round(
            self.history_keep_start
            + (self.history_keep_end - self.history_keep_start) * ratio
        ))
        chars = int(round(
            self.prompt_chars_start
            + (self.prompt_chars_end - self.prompt_chars_start) * ratio
        ))
        return max(4, min(16, keep)), max(4000, min(20000, chars))

    def note_decide(
        self,
        *,
        tool: str | None,
        finish: bool,
        parse_ok: bool,
        usage: dict[str, Any] | None,
        history_keep: int,
        prompt_chars: int,
        cache_hit: bool = False,
    ) -> None:
        if usage:
            self.total_prompt_tokens += int(usage.get("prompt_tokens") or 0)
            self.total_completion_tokens += int(usage.get("completion_tokens") or 0)
            self.total_tokens_est += int(
                usage.get("total_tokens") or usage.get("prompt_tokens_est") or 0
            )
        self.steps_log.append({
            "step": self.step_index,
            "event": "decide",
            "tool": str(tool or ""),
            "finish": bool(finish),
            "parse_ok": bool(parse_ok),
            "history_keep": history_keep,
            "prompt_chars": prompt_chars,
            "cache_hit": bool(cache_hit),
            "elapsed_sec": round(_time.monotonic() - self.loop_start, 2) if self.loop_start else 0,
        })
        # Soft failures (no usable tool) count as no-progress
        if not finish and (not parse_ok or not tool):
            self.no_progress_streak += 1

    def check_repeated_tool(self, tool: str, args: dict[str, Any]) -> str | None:
        """Return stop reason if identical tool+args repeated too many times."""
        if not tool or tool == "finish":
            return None
        fp = _tool_fingerprint(tool, args)
        if fp and fp == self.last_fingerprint:
            self.repeat_count += 1
        else:
            self.repeat_count = 1
            self.last_fingerprint = fp
        if self.repeat_count >= self.repeated_tool_limit:
            self.stop_reason_detail = {
                "reason": "repeated_tool_loop",
                "tool": str(tool),
                "repeats": self.repeat_count,
                "fingerprint": (fp or "")[:200],
                "step": self.step_index,
            }
            self.steps_log.append({
                "step": self.step_index,
                "event": "hard_stop_repeated_tool",
                "tool": str(tool),
                "repeats": self.repeat_count,
                "elapsed_sec": round(_time.monotonic() - self.loop_start, 2),
            })
            return "repeated_tool_loop"
        return None

    def note_blocked_step(self, *, tool: str | None, reason: str) -> str | None:
        """Record a step that did not execute a mutating tool (policy/parse block).

        Always counts as no-progress. Returns stop reason when limit hit.
        """
        tool_s = str(tool or "") or "blocked"
        self.no_progress_streak += 1
        self.steps_log.append({
            "step": self.step_index,
            "event": "blocked",
            "tool": tool_s,
            "reason": str(reason)[:120],
            "streak": self.no_progress_streak,
            "elapsed_sec": round(_time.monotonic() - self.loop_start, 2) if self.loop_start else 0,
        })
        if self.no_progress_streak >= self.no_progress_limit and self.step_index >= 1:
            self.stop_reason_detail = {
                "reason": "no_progress",
                "streak": self.no_progress_streak,
                "limit": self.no_progress_limit,
                "last_tool": tool_s,
                "blocked_reason": str(reason)[:120],
                "step": self.step_index,
            }
            self.steps_log.append({
                "step": self.step_index,
                "event": "hard_stop_no_progress",
                "streak": self.no_progress_streak,
                "tool": tool_s,
                "via": "blocked",
            })
            return "no_progress"
        return None

    def note_tool_result(
        self,
        *,
        tool: str | None,
        result: dict[str, Any] | None,
        files_written: list[str],
    ) -> str | None:
        """Update progress tracking. Return stop reason on no-progress limit."""
        result = result or {}
        tool_s = str(tool or "")
        mutating = tool_s not in self._INSPECT_TOOLS and tool_s not in {"", "finish"}
        new_files = len(files_written) > self.files_at_last_progress
        tool_ok = bool(result.get("ok"))
        progress = new_files or (
            mutating
            and tool_ok
            and tool_s in {
                "write_file", "edit_file", "apply_edits", "apply_patch",
                "search_replace", "run_shell",
            }
        )
        if progress:
            self.no_progress_streak = 0
            self.files_at_last_progress = len(files_written)
        elif tool_s not in {"", "finish"}:
            self.no_progress_streak += 1

        if self.no_progress_streak >= self.no_progress_limit and self.step_index >= 1:
            self.stop_reason_detail = {
                "reason": "no_progress",
                "streak": self.no_progress_streak,
                "limit": self.no_progress_limit,
                "files_written": len(files_written),
                "last_tool": tool_s,
                "step": self.step_index,
            }
            self.steps_log.append({
                "step": self.step_index,
                "event": "hard_stop_no_progress",
                "streak": self.no_progress_streak,
                "tool": tool_s,
                "files_written": len(files_written),
                "elapsed_sec": round(_time.monotonic() - self.loop_start, 2),
            })
            return "no_progress"
        return None

    def to_metadata(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "band": self.band,
            "difficulty_score": self.difficulty_score,
            "max_steps": self.max_steps,
            "source": self.source,
            "env_ceiling": self.env_ceiling,
            "history_keep_start": self.history_keep_start,
            "history_keep_end": self.history_keep_end,
            "prompt_chars_start": self.prompt_chars_start,
            "prompt_chars_end": self.prompt_chars_end,
            "repeated_tool_limit": self.repeated_tool_limit,
            "no_progress_limit": self.no_progress_limit,
            "no_progress_streak": self.no_progress_streak,
            "repeat_count": self.repeat_count,
            "step_index": self.step_index,
            "steps_log": list(self.steps_log)[-60:],
            "stop_reason_detail": self.stop_reason_detail,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens_est": self.total_tokens_est,
        }


    def finalize(self, state: "AgentState") -> None:
        meta = self.to_metadata()
        meta["final_steps"] = len(state.steps)
        meta["final_stop_reason"] = state.stop_reason
        meta["final_ok"] = bool(state.ok)
        meta["elapsed_sec"] = (
            round(_time.monotonic() - self.loop_start, 2) if self.loop_start else None
        )
        if not meta.get("stop_reason_detail") and state.stop_reason:
            meta["stop_reason_detail"] = {"reason": state.stop_reason}
        keep, chars = self.context_caps()
        meta["final_history_keep"] = keep
        meta["final_prompt_chars"] = chars
        state.metadata["loop_governor"] = meta


def _band_limits(band: str) -> dict[str, int]:
    band = (band or "medium").strip().lower()
    if band == "easy":
        return {
            "max_steps": 5,  # 4–6
            "history_keep_start": 8, "history_keep_end": 4,
            "prompt_chars_start": 10000, "prompt_chars_end": 6000,
            "no_progress_limit": 2,
        }
    if band == "hard":
        return {
            "max_steps": 14,  # 12–15
            "history_keep_start": 12, "history_keep_end": 6,
            "prompt_chars_start": 15000, "prompt_chars_end": 8000,
            "no_progress_limit": 4,
        }
    return {
        "max_steps": 9,  # 8–10
        "history_keep_start": 10, "history_keep_end": 5,
        "prompt_chars_start": 12000, "prompt_chars_end": 7000,
        "no_progress_limit": 3,
    }


def _tool_fingerprint(tool: str, args: dict[str, Any]) -> str:
    """Stable fingerprint for repeated-tool detection (path/command first)."""
    args = dict(args or {})
    try:
        identity: dict[str, Any] = {"tool": str(tool or "")}
        for key in (
            "path", "file", "target", "name", "command", "cmd",
            "query", "pattern", "glob", "url",
        ):
            if key in args and args[key] is not None:
                identity[key] = str(args[key])[:200]
        content = args.get("content")
        if isinstance(content, str) and content:
            identity["content_len"] = len(content)
            identity["content_head"] = content[:80]
        if len(identity) <= 1:
            identity["keys"] = sorted(str(k) for k in args.keys())
        return json.dumps(identity, sort_keys=True, ensure_ascii=False)[:500]
    except Exception:
        return f"{tool}:{sorted(str(k) for k in args.keys())}"


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

    # --- Phase-1 Loop Governor (explicit controller) ---
    gov = LoopGovernor.from_difficulty(diff, explicit_max_steps=max_steps)
    limit = gov.max_steps
    state.metadata["loop_governor"] = gov.to_metadata()
    _emit_progress({
        "phase": "loop_start",
        "step": 0,
        "limit": limit,
        "detail": f"بدء حلقة الوكيل (governor band={gov.band} steps={limit})",
        "governor_band": gov.band,
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

    # Wall-clock budget — the INNER time guarantee.
    _budget_sec = _time_budget()
    gov.start()
    _deadline = gov.loop_start + _budget_sec
    state.metadata["time_budget_sec"] = _budget_sec

    # Phase-2 Structured Recovery controller
    recovery = StructuredRecovery()
    state.metadata["recovery"] = recovery.to_metadata()
    state.metadata["recovery_attempts"] = recovery.total_attempts

    for i in range(limit):
        gov.step_index = i
        _keep, _pchars = gov.context_caps()

        # TIME-BUDGET CUTOFF
        _now = _time.monotonic()
        if _now >= _deadline:
            _elapsed = int(_now - gov.loop_start)
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
        decision = decide(
            msgs,
            choice=choice,
            history_keep=_keep,
            prompt_max_chars=_pchars,
        )
        _emit_progress({
            "phase": "decided",
            "step": i,
            "limit": limit,
            "tool": str(decision.get("tool") or "thinking"),
            "thought": str(decision.get("thought") or "")[:160],
            "detail": "اتخذ قرار الخطوة",
            "files_written": len(state.files_written or []),
        })
        # Phase A cost + Governor decide note
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
        except Exception:
            u = {}
        try:
            gov.note_decide(
                tool=decision.get("tool"),
                finish=bool(decision.get("finish")),
                parse_ok=bool(decision.get("parse_ok", True)),
                usage=u if isinstance(u, dict) else {},
                history_keep=_keep,
                prompt_chars=_pchars,
                cache_hit=bool(decision.get("cache_hit")),
            )
            state.metadata["loop_governor"] = gov.to_metadata()
            # Soft no-progress limit after decide (parse_fail / no tool)
            if (
                gov.no_progress_streak >= gov.no_progress_limit
                and i >= 1
                and not decision.get("finish")
                and not (decision.get("parse_ok", True) and decision.get("tool"))
            ):
                state.stop_reason = "no_progress"
                state.ok = bool(state.files_written)
                state.warnings.append(
                    f"no_progress_streak:{gov.no_progress_streak}>={gov.no_progress_limit}"
                )
                logger.warning(
                    "agent_loop hard-stop: no progress after decide (step %d/%d)",
                    i, limit,
                )
                break
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
            state.steps.append(step)
            state.warnings.append(f"parse_fail_step_{i}:{err[:80]}")
            # Phase-2: short parse repair ONLY (no full tool-list INVALID dump)
            _ra = recovery.plan(
                tool=None, args=None,
                result={"ok": False, "error": err},
                parse_fail=True, parse_err=err,
            )
            if _ra:
                recovery.commit(_ra)
                state.metadata["recovery"] = recovery.to_metadata()
                state.metadata["recovery_attempts"] = recovery.total_attempts
                state.add_user(_ra.prompt)
            else:
                state.add_user(
                    'PARSE REPAIR: one JSON tool call only '
                    '{"thought":"...","tool":"list_dir","args":{"path":"."},"finish":false}'
                )
            if recovery.total_attempts >= recovery.max_total and not state.files_written:
                state.stop_reason = "recovery_exhausted"
                state.ok = False
                state.warnings.append("recovery_exhausted_on_parse")
                break
            continue

        tool = decision.get("tool")
        args = dict(decision.get("args") or {})

        # --- Loop Governor: repeated identical tool hard-stop ---
        _rep_reason = gov.check_repeated_tool(str(tool or ""), args)
        if _rep_reason:
            state.stop_reason = _rep_reason
            state.ok = False
            state.warnings.append(f"{_rep_reason}:{tool}x{gov.repeat_count}")
            state.errors.append(
                f"empty_loop_detected tool={tool} repeats={gov.repeat_count}"
            )
            state.metadata["loop_governor"] = gov.to_metadata()
            logger.warning(
                "agent_loop hard-stop: tool %s repeated %d times (step %d/%d)",
                tool, gov.repeat_count, i, limit,
            )
            step.tool_result = {
                "ok": False,
                "error": _rep_reason,
                "tool": str(tool),
                "repeats": gov.repeat_count,
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
                _br = gov.note_blocked_step(tool=str(tool), reason=f"read_before_edit:{target}")
                state.metadata["loop_governor"] = gov.to_metadata()
                if _br:
                    state.stop_reason = _br
                    state.ok = bool(state.files_written)
                    state.warnings.append(
                        f"no_progress_streak:{gov.no_progress_streak}>={gov.no_progress_limit}"
                    )
                    break
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
                _br = gov.note_blocked_step(tool=str(tool), reason=f"prefer_edit:{wp}")
                state.metadata["loop_governor"] = gov.to_metadata()
                if _br:
                    state.stop_reason = _br
                    state.ok = bool(state.files_written)
                    state.warnings.append(
                        f"no_progress_streak:{gov.no_progress_streak}>={gov.no_progress_limit}"
                    )
                    break
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
            _br = gov.note_blocked_step(tool="finish", reason="acceptance_soft_fail")
            state.metadata["loop_governor"] = gov.to_metadata()
            if _br:
                state.stop_reason = _br
                state.ok = bool(state.files_written)
                break
            continue

        if not tool:
            state.add_assistant(step.thought or "(no tool)")
            state.add_user("Call a tool or finish. JSON only.")
            state.steps.append(step)
            _br = gov.note_blocked_step(tool="no_tool", reason="missing_tool")
            state.metadata["loop_governor"] = gov.to_metadata()
            if _br:
                state.stop_reason = _br
                state.ok = bool(state.files_written)
                break
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
        if tool == "edit_file" and result.get("ok") and args.get("path"):
            path = str(args["path"])
            if path not in state.files_written:
                state.files_written.append(path)

        # --- Phase-2 Structured Recovery FIRST (before no-progress hard-stop) ---
        _recovery_applied = False
        if isinstance(result, dict) and not result.get("ok") and tool and tool != "finish":
            _ra = recovery.plan(tool=str(tool), args=args, result=result)
            if _ra is None:
                if recovery.total_attempts >= recovery.max_total:
                    state.stop_reason = "recovery_exhausted"
                    state.ok = bool(state.files_written)
                    state.warnings.append("recovery_exhausted")
                    state.metadata["recovery"] = recovery.to_metadata()
                    state.metadata["recovery_attempts"] = recovery.total_attempts
                    logger.warning(
                        "agent_loop recovery exhausted (step %d/%d total=%d)",
                        i, limit, recovery.total_attempts,
                    )
                    break
            else:
                recovery.commit(_ra)
                _recovery_applied = True
                state.metadata["recovery"] = recovery.to_metadata()
                state.metadata["recovery_attempts"] = recovery.total_attempts
                if _ra.backoff_sec > 0:
                    try:
                        _time.sleep(min(float(_ra.backoff_sec), 5.0))
                    except Exception:
                        pass
                # ENFORCE force_tool (write recovery → real read_file before sub-agent)
                _enforced_read = None
                if _ra.force_tool == "read_file" and _ra.force_args:
                    try:
                        _enforced_read = run_tool(
                            state.work_dir, "read_file", dict(_ra.force_args)
                        )
                        state.steps.append(
                            AgentStep(
                                index=i,
                                thought="recovery enforced read_file",
                                tool_name="read_file",
                                tool_args=dict(_ra.force_args),
                                tool_result=_enforced_read if isinstance(_enforced_read, dict) else {"ok": False},
                            )
                        )
                        state.add_tool_result(
                            "read_file",
                            _enforced_read if isinstance(_enforced_read, dict) else {},
                        )
                        if isinstance(_enforced_read, dict) and _enforced_read.get("ok"):
                            _rp = str(_ra.force_args.get("path") or "")
                            if _rp:
                                _rs = set(state.metadata.get("read_files") or [])
                                _rs.add(_rp)
                                state.metadata["read_files"] = sorted(_rs)
                    except Exception as _enf_exc:
                        state.warnings.append(f"recovery_force_read:{type(_enf_exc).__name__}")
                state.add_user(_ra.prompt)
                # Sub-agent: same model, recovery system prompt, minimal window
                try:
                    _rec_msgs = recovery.build_recovery_messages(
                        action=_ra,
                        tool=str(tool),
                        args=args,
                        result=result,
                        enforced_read=_enforced_read if isinstance(_enforced_read, dict) else None,
                    )
                    _rec_decision = decide(
                        _rec_msgs,
                        choice=choice,
                        history_keep=2,
                        prompt_max_chars=4000,
                    )
                    try:
                        _ru = _rec_decision.get("usage") or {}
                        if _ru:
                            gov.note_decide(
                                tool=_rec_decision.get("tool"),
                                finish=bool(_rec_decision.get("finish")),
                                parse_ok=bool(_rec_decision.get("parse_ok", True)),
                                usage=_ru,
                                history_keep=2,
                                prompt_chars=4000,
                                cache_hit=bool(_rec_decision.get("cache_hit")),
                            )
                    except Exception:
                        pass
                    _rec_tool = _rec_decision.get("tool")
                    _rec_args = dict(_rec_decision.get("args") or {})
                    # Soft-enforce: after write recovery, prefer edit/patch over full write
                    if (
                        _ra.mode == "force_read_patch"
                        and _rec_tool == "write_file"
                        and _ra.force_args.get("path")
                    ):
                        _rec_tool = "edit_file"
                        _rec_args.setdefault("path", _ra.force_args.get("path"))
                    if _rec_decision.get("parse_ok") and _rec_tool and _rec_tool != "finish":
                        _rec_result = run_tool(state.work_dir, str(_rec_tool), _rec_args)
                        state.steps.append(
                            AgentStep(
                                index=i,
                                thought=str(_rec_decision.get("thought") or "recovery")[:500],
                                tool_name=str(_rec_tool),
                                tool_args=_rec_args,
                                tool_result=_rec_result if isinstance(_rec_result, dict) else {"ok": False},
                                raw_model=str(_rec_decision.get("raw") or "")[:500],
                            )
                        )
                        state.add_assistant(
                            json.dumps(
                                {
                                    "thought": "recovery",
                                    "tool": _rec_tool,
                                    "args": _safe_args(_rec_args),
                                    "strategy": _ra.strategy,
                                },
                                ensure_ascii=False,
                            )[:2000]
                        )
                        state.add_tool_result(
                            str(_rec_tool),
                            _rec_result if isinstance(_rec_result, dict) else {},
                        )
                        if (
                            _rec_tool in {"write_file", "edit_file", "apply_edits", "apply_patch"}
                            and isinstance(_rec_result, dict)
                            and _rec_result.get("ok")
                        ):
                            _rp = str((_rec_result.get("path") or _rec_args.get("path") or ""))
                            if _rp and _rp not in state.files_written:
                                state.files_written.append(_rp)
                        # Progress accounting uses recovery outcome (not the failed primary)
                        _np_reason = gov.note_tool_result(
                            tool=str(_rec_tool),
                            result=_rec_result if isinstance(_rec_result, dict) else {},
                            files_written=list(state.files_written or []),
                        )
                        state.metadata["loop_governor"] = gov.to_metadata()
                        _emit_progress({
                            "phase": "recovery",
                            "step": i,
                            "limit": limit,
                            "tool": str(_rec_tool),
                            "ok": bool((_rec_result or {}).get("ok") if isinstance(_rec_result, dict) else False),
                            "detail": f"recovery:{_ra.mode}:{_ra.strategy}",
                        })
                        if _np_reason:
                            state.stop_reason = _np_reason
                            state.ok = bool(state.files_written)
                            state.warnings.append(
                                f"no_progress_streak:{gov.no_progress_streak}>={gov.no_progress_limit}"
                            )
                            break
                except Exception as _rec_exc:
                    state.warnings.append(f"recovery_subagent:{type(_rec_exc).__name__}")
                    logger.warning("recovery sub-agent failed: %s", _rec_exc)

        # --- Loop Governor no-progress (only if recovery did not handle progress) ---
        if not _recovery_applied:
            _np_reason = gov.note_tool_result(
                tool=str(tool or ""),
                result=result if isinstance(result, dict) else {},
                files_written=list(state.files_written or []),
            )
            state.metadata["loop_governor"] = gov.to_metadata()
            if _np_reason:
                state.stop_reason = _np_reason
                state.ok = bool(state.files_written)
                state.warnings.append(
                    f"no_progress_streak:{gov.no_progress_streak}>={gov.no_progress_limit}"
                )
                logger.warning(
                    "agent_loop hard-stop: no progress for %d steps (step %d/%d, files=%d)",
                    gov.no_progress_streak, i, limit, len(state.files_written),
                )
                break

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
        state.metadata["recovery"] = recovery.to_metadata()
        state.metadata["recovery_attempts"] = recovery.total_attempts
    except Exception:
        pass
    try:
        gov.finalize(state)
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
