"""Autonomous agent loop — the core of free Cline path.

plan → tool call → observe → repeat until finish / max_steps / error.
Does NOT use catalog templates. Writes a real project under work_dir.

Implementation split (behavior unchanged):
  - loop_governor.py — LoopGovernor, budgets per band, tool fingerprints
  - loop_support.py  — prompts, progress, step/time budgets, safe args
  - agent_loop.py    — run_agent (public entry)
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
from .loop_governor import LoopGovernor
from .loop_support import (
    AGENT_TOOL_NAMES,
    _emit_progress,
    _max_steps,
    _safe_args,
    _system_prompt,
    _time_budget,
    _tools_help,
)

logger = logging.getLogger(__name__)


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
        from lumen.engine.security.prompt_guard import scan_user_request_only, scan_user_input
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
    # --- Cost guard: refuse to start LLM loop without spend allowance ---
    try:
        from lumen.platform.credits.guards import (
            GenerationBlockedError,
            assert_llm_spend_allowed,
        )
        _uid = 0
        _tid_hint = ""
        if isinstance(ir_dict, dict):
            try:
                _uid = int(ir_dict.get("user_id") or (ir_dict.get("metadata") or {}).get("user_id") or 0)
            except (TypeError, ValueError):
                _uid = 0
            _tid_hint = str(
                ir_dict.get("tenant_id")
                or (ir_dict.get("metadata") or {}).get("tenant_id")
                or ""
            ).strip()
        _tid = assert_llm_spend_allowed(tenant_id=_tid_hint, user_id=_uid)
        state.metadata["billing_tenant_id"] = _tid
        state.metadata["tenant_id"] = _tid
        if _uid:
            state.metadata["user_id"] = _uid
    except Exception as _bg:
        from lumen.platform.credits.guards import GenerationBlockedError as _GBE
        if isinstance(_bg, _GBE) or type(_bg).__name__ == "GenerationBlockedError":
            state.ok = False
            state.stop_reason = "insufficient_credits"
            state.errors.append(f"insufficient_credits:{getattr(_bg, 'reason', _bg)}")
            state.metadata["insufficient_credits"] = {
                "reason": getattr(_bg, "reason", str(_bg)),
                "tenant_id": getattr(_bg, "tenant_id", ""),
            }
            return state
        # unknown gate errors: fail closed
        state.ok = False
        state.stop_reason = "billing_gate_error"
        state.errors.append(f"billing_gate_error:{type(_bg).__name__}")
        return state
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
    # Workspace size feeds R2 allocator difficulty signal
    try:
        file_count = sum(1 for _ in work.rglob("*") if _.is_file()) if work.is_dir() else 0
    except Exception:
        file_count = 0
    choice, diff = select_model_for_goal(
        task=task,
        goal=goal or "",
        features=feats,
        findings_count=findings_n,
        file_count=file_count,
    )
    state.metadata["router"] = {
        "provider": choice.provider,
        "model_id": choice.model_id,
        "meta": diff,
    }
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
        "provider": choice.provider,
        "model": choice.model_id,
        "router": (diff or {}).get("router") if isinstance(diff, dict) else None,
    })
    user_id = 0
    if isinstance(ir_dict, dict):
        try:
            user_id = int(ir_dict.get("user_id") or 0)
        except (TypeError, ValueError):
            user_id = 0
    state.metadata["user_id"] = user_id
    if user_id and not state.metadata.get("tenant_id"):
        state.metadata["tenant_id"] = f"tg:{int(user_id)}"
    # Do NOT clear_cancel here — generation start already cleared in
    # run_with_heartbeat. Clearing again would wipe a cancel issued while
    # multi-agent was planning before the first agent_loop step.
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
    # Phase 2: resolve ProjectKind, seed scaffold, stamp runtime metadata
    _project_kind = ""
    try:
        from lumen.engine.core.project_kind import (
            kind_metadata,
            parse_kind,
            resolve_project_kind,
            seed_workspace,
        )
        if isinstance(ir_dict, dict):
            _project_kind = str(
                ir_dict.get("project_kind")
                or (ir_dict.get("metadata") or {}).get("project_kind")
                or ""
            ).strip()
            plan = ir_dict.get("execution_plan") or (ir_dict.get("metadata") or {}).get("execution_plan")
            if not _project_kind and isinstance(plan, dict):
                _project_kind = str(plan.get("project_kind") or "").strip()
        _pk = parse_kind(_project_kind) or resolve_project_kind(text=goal or "")
        _project_kind = _pk.value
        state.metadata["project_kind"] = _project_kind
        # LanguageRuntime Phase 1
        try:
            from lumen.engine.core.language_runtime import parse_language, recipe_for, language_metadata
            _lang = "python"
            if isinstance(ir_dict, dict):
                _lang = str(
                    ir_dict.get("language")
                    or (ir_dict.get("metadata") or {}).get("language")
                    or "python"
                ).strip() or "python"
            _lr = parse_language(_lang)
            if _lr is not None:
                state.metadata["language"] = _lr.value
                state.metadata.update(language_metadata(_lr, kind=_project_kind))
        except Exception:
            state.metadata.setdefault("language", "python")

        state.metadata.update({k: v for k, v in kind_metadata(_pk).items() if k not in state.metadata})
        # Greenfield seed only (never overwrite agent work)
        if not (Path(state.work_dir) / "main.py").exists() and not (
            Path(state.work_dir) / "src" / "__init__.py"
        ).exists():
            created = seed_workspace(state.work_dir, _pk)
            if created:
                state.metadata["seeded_files"] = created
                state.warnings.append("seeded:" + ",".join(created[:8]))
    except Exception as _seed_exc:
        state.warnings.append(f"seed_skip:{type(_seed_exc).__name__}")

    sys_prompt = _system_prompt(state.work_dir, goal, ir_dict)
    # Bind active conversation id for decide(); history inject happens once in agent_brain.decide
    try:
        _cuid = int(state.metadata.get("user_id") or 0)
        _ccid = ""
        if isinstance(ir_dict, dict):
            _ccid = str(
                ir_dict.get("conversation_id")
                or (ir_dict.get("metadata") or {}).get("conversation_id")
                or ""
            )
        if _cuid:
            from lumen.platform.conversations import get_conversation_service
            _cobj = get_conversation_service().ensure_active(_cuid, conversation_id=_ccid or None)
            state.metadata["conversation_id"] = _cobj.id
            state.metadata["tenant_id"] = state.metadata.get("tenant_id") or f"tg:{_cuid}"
    except Exception as _conv_exc:
        state.warnings.append(f"conversation_bind_skip:{type(_conv_exc).__name__}")

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

    # --- Phase-3: fold Project Card + semantic memory into FIRST system message ---
    try:
        _uid = int(state.metadata.get("user_id") or 0)
        _pid = ""
        if isinstance(ir_dict, dict):
            _pid = str(
                ir_dict.get("project_id")
                or (ir_dict.get("metadata") or {}).get("project_id")
                or ""
            )
        from lumen.engine.services.semantic_memory.project_memory import (
            get_project_memory_store,
        )
        _pm = get_project_memory_store()
        _card = _pm.get_active_card(_uid, path=str(state.work_dir or ""), project_id=_pid)
        if _card is None:
            # Ensure a card exists for this generation workspace so later recovery can attach
            try:
                _card = _pm.register_project(
                    user_id=_uid,
                    project_id=_pid or None,
                    label=str(goal or "")[:80] or "project",
                    kind="generated",
                    path=str(state.work_dir or ""),
                    source_request=str(goal or "")[:500],
                )
            except Exception as _reg_exc:
                state.warnings.append(f"project_register_skip:{type(_reg_exc).__name__}")
                _card = None
        if _card:
            _card_txt = _pm.context_for_engine(_card.project_id, max_history=12)
            if _card_txt:
                state.metadata["project_card_id"] = _card.project_id
                state.metadata["project_card_injected"] = True
                sys_prompt = (
                    sys_prompt
                    + "\n\nPROJECT_CARD (active project memory - use for continuity):\n"
                    + _card_txt[:2500]
                )
        try:
            from lumen.engine.services.semantic_memory.retrieval import build_memory_context
            _sem = build_memory_context(
                user_id=_uid,
                user_message=str(goal or "")[:500],
                project_id=str(getattr(_card, "project_id", None) or _pid or ""),
                top_k=6,
            )
            if _sem:
                state.metadata["semantic_memory_injected"] = True
                sys_prompt = (
                    sys_prompt
                    + "\n\nSEMANTIC_MEMORY (relevant facts before planning):\n"
                    + _sem[:2500]
                )
        except Exception as _sem_exc:
            state.warnings.append(f"semantic_memory_skip:{type(_sem_exc).__name__}")
    except Exception as _mem_exc:
        state.warnings.append(f"project_memory_skip:{type(_mem_exc).__name__}")

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

    # --- Phase-3: parallel inspect of workspace (max 3 independent tools) ---
    try:
        from .agent_fs import run_tools_parallel
        _par_calls = [
            {"tool": "list_dir", "args": {"path": "."}},
            {"tool": "glob_files", "args": {"pattern": "*.py"}},
            {"tool": "glob_files", "args": {"pattern": "requirements*.txt"}},
        ]
        _par_results = run_tools_parallel(str(state.work_dir), _par_calls, max_parallel=3)
        state.metadata["parallel_inspect"] = [
            {"tool": (r or {}).get("tool"), "ok": bool((r or {}).get("ok"))}
            for r in (_par_results or [])
        ]
        _bits = []
        for r in _par_results or []:
            if not isinstance(r, dict) or not r.get("ok"):
                continue
            t = str(r.get("tool") or "")
            if t == "list_dir":
                ents = r.get("entries") or r.get("items") or r.get("files") or []
                names = []
                if isinstance(ents, list):
                    for x in ents[:12]:
                        if isinstance(x, dict):
                            names.append(str(x.get("name") or x.get("path") or "")[:40])
                        else:
                            names.append(str(x)[:40])
                if names:
                    _bits.append("list_dir: " + ", ".join(n for n in names if n))
            elif t == "glob_files":
                files = r.get("files") or r.get("matches") or []
                if isinstance(files, list) and files:
                    _bits.append("glob: " + ", ".join(str(x)[:60] for x in files[:8]))
        if _bits:
            state.add_user(
                "PARALLEL_INSPECT (workspace snapshot):\n" + "\n".join(_bits)[:1800]
            )
    except Exception as _par_exc:
        state.warnings.append(f"parallel_inspect_skip:{type(_par_exc).__name__}")

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
                acc = check_agent_project(state.work_dir, goal=goal, project_kind=str(state.metadata.get("project_kind") or ""), language=str(state.metadata.get("language") or state.metadata.get("runtime_language") or "python"))
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
                _emit_progress({
                    "phase": "finish",
                    "tool": "finish",
                    "detail": "تم الإلغاء بواسطة المستخدم",
                    "step": i,
                    "limit": limit,
                    "provider": choice.provider,
                    "model": choice.model_id,
                })
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
            "provider": choice.provider,
            "model": choice.model_id,
        })
        _charge_token = None
        try:
            from lumen.platform.credits.llm_live import (
                InsufficientCreditsError,
                bind_charge_context,
                clear_charge_context,
            )
            _charge_token = bind_charge_context(
                tenant_id=str(
                    state.metadata.get("billing_tenant_id")
                    or state.metadata.get("tenant_id")
                    or ""
                ),
                user_id=int(state.metadata.get("user_id") or 0),
                state_id=str(state.metadata.get("state_id") or state.work_dir or ""),
                step=i,
                call_index=int((state.metadata.get("usage") or {}).get("calls") or 0),
            )
        except Exception:
            InsufficientCreditsError = Exception  # type: ignore
            clear_charge_context = lambda *a, **k: None  # type: ignore
            _charge_token = None
        try:
            decision = decide(
                msgs,
                choice=choice,
                history_keep=_keep,
                prompt_max_chars=_pchars,
                task=task,
                user_id=int(state.metadata.get("user_id") or 0),
                conversation_id=str(state.metadata.get("conversation_id") or ""),
            )
        except InsufficientCreditsError as _ice:
            state.ok = False
            state.stop_reason = "insufficient_credits"
            state.errors.append(
                f"insufficient_credits:needed={getattr(_ice, 'needed', 0)}:"
                f"available={getattr(_ice, 'available', 0)}:step={getattr(_ice, 'step', i)}"
            )
            state.metadata["insufficient_credits"] = {
                "tenant_id": getattr(_ice, "tenant_id", ""),
                "needed": getattr(_ice, "needed", 0),
                "available": getattr(_ice, "available", 0),
                "reason": getattr(_ice, "reason", "insufficient_balance"),
                "step": getattr(_ice, "step", i),
            }
            _emit_progress({
                "phase": "stopped",
                "step": i,
                "limit": limit,
                "detail": "توقف: رصيد غير كافٍ لتكلفة خطوة الذكاء الاصطناعي",
                "stop_reason": "insufficient_credits",
            })
            try:
                clear_charge_context(_charge_token)
            except Exception:
                pass
            break
        except RuntimeError as _re:
            if "llm_billing_unavailable" not in str(_re):
                raise
            state.ok = False
            state.stop_reason = "llm_billing_unavailable"
            state.errors.append(f"llm_billing_unavailable:{_re}")
            _emit_progress({
                "phase": "stopped",
                "step": i,
                "limit": limit,
                "detail": "توقف: نظام الفوترة غير متاح",
                "stop_reason": "llm_billing_unavailable",
            })
            try:
                clear_charge_context(_charge_token)
            except Exception:
                pass
            break
        finally:
            try:
                clear_charge_context(_charge_token)
            except Exception:
                pass
        # Per-step R2 reallocation (local router only) — Foundry routes each prompt itself
        try:
            if (diff or {}).get("router") == "r2_allocator" or (
                (os.getenv("CLINE_ROUTER") or "auto").strip().lower() in {"local", "r2", "catalog"}
            ):
                last_tool = str(decision.get("tool") or "")
                soft = bool(decision.get("soft_parse_fail"))
                new_choice, new_meta = select_model_for_goal(
                    task=task,
                    goal=goal or "",
                    features=feats,
                    findings_count=findings_n,
                    file_count=file_count,
                    last_tool=last_tool,
                    soft_parse_fail=soft,
                )
                if new_choice.provider != "none" and (
                    new_choice.provider != choice.provider or new_choice.model_id != choice.model_id
                ):
                    logger.info(
                        "r2 reallocate %s/%s → %s/%s kind=%s",
                        choice.provider,
                        choice.model_id,
                        new_choice.provider,
                        new_choice.model_id,
                        (new_meta or {}).get("step_kind"),
                    )
                    choice = new_choice
                    diff = new_meta
                    state.metadata["router"] = {
                        "provider": choice.provider,
                        "model_id": choice.model_id,
                        "meta": diff,
                        "reallocated_at_step": i,
                    }
        except Exception:
            logger.debug("r2 reallocate skipped", exc_info=True)
        if decision.get("underlying_model") or decision.get("foundry_mode"):
            state.metadata["last_foundry"] = {
                "underlying_model": decision.get("underlying_model"),
                "mode": decision.get("foundry_mode"),
                "deployment": decision.get("foundry_deployment"),
                "step": i,
            }
        _emit_progress({
            "phase": "decided",
            "step": i,
            "limit": limit,
            "tool": str(decision.get("tool") or "thinking"),
            "thought": str(decision.get("thought") or "")[:160],
            "detail": "اتخذ قرار الخطوة",
            "files_written": len(state.files_written or []),
            "model": decision.get("underlying_model") or decision.get("model_id") or choice.model_id,
            "provider": decision.get("provider") or choice.provider,
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
        # Live charge happens inside decide() via bound contextvars.
        # Accumulate charge receipt on state when present.
        try:
            _cr = decision.get("credit_charge") if isinstance(decision, dict) else None
            if isinstance(_cr, dict) and _cr.get("charged"):
                state.metadata["llm_credits_charged"] = int(
                    state.metadata.get("llm_credits_charged") or 0
                ) + int(_cr.get("credits") or 0)
                _charges = list(state.metadata.get("llm_charges") or [])
                _charges.append(_cr)
                state.metadata["llm_charges"] = _charges[-50:]
        except Exception:
            pass
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
            acc = check_agent_project(state.work_dir, goal=goal, project_kind=str(state.metadata.get("project_kind") or ""), language=str(state.metadata.get("language") or state.metadata.get("runtime_language") or "python"))
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
                acc2 = check_agent_project(state.work_dir, goal=goal, project_kind=str(state.metadata.get("project_kind") or ""), language=str(state.metadata.get("language") or state.metadata.get("runtime_language") or "python"))
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
            "provider": choice.provider,
            "model": choice.model_id,
        })
        _t0 = _time.monotonic()
        result = run_tool(state.work_dir, str(tool), args)
        _elapsed_ms = int((_time.monotonic() - _t0) * 1000)
        if isinstance(result, dict):
            result = dict(result)
            result["elapsed_ms"] = _elapsed_ms
            try:
                from lumen.platform.sanitize import sanitize_log_text

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
                _recovery_tool_ok = False
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
                    _rec_charge_token = None
                    try:
                        from lumen.platform.credits.llm_live import (
                            InsufficientCreditsError as _ICE_Rec,
                            bind_charge_context as _bind_rec,
                            clear_charge_context as _clear_rec,
                        )
                        _rec_charge_token = _bind_rec(
                            tenant_id=str(state.metadata.get("tenant_id") or ""),
                            user_id=int(state.metadata.get("user_id") or 0),
                            state_id=str(state.metadata.get("state_id") or state.work_dir or ""),
                            step=i,
                            call_index=int((state.metadata.get("usage") or {}).get("calls") or 0) + 1000,
                        )
                    except Exception:
                        _ICE_Rec = Exception  # type: ignore
                        _clear_rec = lambda *a, **k: None  # type: ignore
                        _rec_charge_token = None
                    try:
                        _rec_decision = decide(
                            _rec_msgs,
                            choice=choice, task=task,
                            history_keep=2,
                            prompt_max_chars=4000,
                            user_id=int(state.metadata.get("user_id") or 0),
                            conversation_id=str(state.metadata.get("conversation_id") or ""),
                        )
                    except _ICE_Rec as _ice:
                        state.ok = False
                        state.stop_reason = "insufficient_credits"
                        state.errors.append(
                            f"insufficient_credits:needed={getattr(_ice, 'needed', 0)}:"
                            f"available={getattr(_ice, 'available', 0)}:step={i}"
                        )
                        state.metadata["insufficient_credits"] = {
                            "tenant_id": getattr(_ice, "tenant_id", ""),
                            "needed": getattr(_ice, "needed", 0),
                            "available": getattr(_ice, "available", 0),
                            "reason": getattr(_ice, "reason", "insufficient_balance"),
                            "step": i,
                        }
                        try:
                            _clear_rec(_rec_charge_token)
                        except Exception:
                            pass
                        break
                    finally:
                        try:
                            _clear_rec(_rec_charge_token)
                        except Exception:
                            pass
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
                        _recovery_tool_ok = bool(
                            isinstance(_rec_result, dict) and _rec_result.get("ok")
                        )

                        # Persist resolved error → solution on project card
                        if _recovery_tool_ok:
                            try:
                                _pid = str(state.metadata.get("project_card_id") or "")
                                if _pid:
                                    from lumen.engine.services.semantic_memory.project_memory import (
                                        get_project_memory_store,
                                    )
                                    get_project_memory_store().record_resolved_error(
                                        _pid,
                                        error=str((result or {}).get("error") or (result or {}).get("message") or "")[:400],
                                        solution=f"recovery:{_ra.mode}:{_ra.strategy} tool={_rec_tool}",
                                        tool=str(tool or ""),
                                        strategy=str(getattr(_ra, "strategy", "") or _ra.mode),
                                    )
                            except Exception as _re_exc:
                                state.warnings.append(f"record_resolved_skip:{type(_re_exc).__name__}")
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
                    # Recovery attempted but sub-agent crashed → count as no progress
                    _np_reason = gov.note_tool_result(
                        tool=str(tool or ""),
                        result=result if isinstance(result, dict) else {},
                        files_written=list(state.files_written or []),
                    )
                    state.metadata["loop_governor"] = gov.to_metadata()
                    if _np_reason:
                        state.stop_reason = _np_reason
                        state.ok = bool(state.files_written)
                        break

        # --- Loop Governor no-progress ---
        # Count original failure when: no recovery, or recovery ran but did not fix.
        if (not _recovery_applied) or (
            _recovery_applied and not locals().get("_recovery_tool_ok", False)
        ):
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
                acc_now = check_agent_project(state.work_dir, goal=goal, project_kind=str(state.metadata.get("project_kind") or ""), language=str(state.metadata.get("language") or state.metadata.get("runtime_language") or "python"))
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
                    acc2 = check_agent_project(state.work_dir, goal=goal, project_kind=str(state.metadata.get("project_kind") or ""), language=str(state.metadata.get("language") or state.metadata.get("runtime_language") or "python"))
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
            acc = check_agent_project(state.work_dir, goal=goal, project_kind=str(state.metadata.get("project_kind") or ""), language=str(state.metadata.get("language") or state.metadata.get("runtime_language") or "python"))
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
        acc = check_agent_project(state.work_dir, goal=goal, project_kind=str(state.metadata.get("project_kind") or ""), language=str(state.metadata.get("language") or state.metadata.get("runtime_language") or "python"))
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


# Re-export names tests and callers already import from agent_loop
__all__ = [
    "run_agent",
    "AGENT_TOOL_NAMES",
    "LoopGovernor",
    "_system_prompt",
    "_tools_help",
    "_max_steps",
    "_time_budget",
]
