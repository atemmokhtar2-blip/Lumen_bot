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
from .model_router import describe_runtime, select_model, select_model_for_goal

logger = logging.getLogger(__name__)

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
        return max(5, min(50, int(os.getenv("CLINE_AGENT_MAX_STEPS") or "24")))
    except ValueError:
        return 16



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
    try:
        from lumen.engine.pipeline.prompt_guard import scan_user_input
        _gr = scan_user_input(goal or "")
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

    limit = max_steps if max_steps is not None else _max_steps()
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

    for i in range(limit):
        try:
            from lumen.engine.services.generation_cancel import is_cancelled

            if is_cancelled(user_id):
                state.stop_reason = "cancelled_by_user"
                state.ok = False
                state.warnings.append("generation_cancelled")
                state.metadata["cancelled"] = True
                return state
        except Exception:
            pass
        msgs = [m.to_dict() for m in state.messages]
        decision = decide(msgs, choice=choice)
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
            return state

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

        import time as _time

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
