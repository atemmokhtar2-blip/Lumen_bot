"""Real free-path provider — autonomous Cline agent (Phase 5 foundation).

Does not compose catalog templates. Builds project via agent_loop + LLM + FS tools.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .agent_loop import run_agent
from .model_router import describe_runtime

logger = logging.getLogger(__name__)


def _goal_from_ir(ir_dict: dict[str, Any]) -> str:
    """Build agent goal from IR — ProjectKind-aware (no Telegram default)."""
    import json
    parts: list[str] = []
    rt_lang = "python"
    for key in ("raw_request", "user_request", "spec_request", "purpose", "goal"):
        val = ir_dict.get(key)
        if isinstance(val, str) and val.strip():
            parts.append(val.strip())
            break
    feats = ir_dict.get("preferred_keys") or ir_dict.get("features_requested") or []
    if isinstance(feats, list) and feats:
        parts.append("Requested features: " + ", ".join(str(x) for x in feats[:40]))
    gaps = ir_dict.get("capabilities_gap") or []
    if isinstance(gaps, list) and gaps:
        parts.append("Gaps / custom needs: " + ", ".join(str(x) for x in gaps[:30]))
    meta = ir_dict.get("metadata") if isinstance(ir_dict.get("metadata"), dict) else {}
    kind = str(ir_dict.get("project_kind") or meta.get("project_kind") or "").strip().lower()

    # LanguageRuntime (code language for Cline — not UI ar)
    rt_lang = "python"
    try:
        from lumen.engine.core.language_runtime import (
            resolve_language, recipe_for, label_ar as lang_label_ar,
        )
        _lr, _lc, _ln = resolve_language(
            parts[0] if parts else "",
            explicit=ir_dict.get("language")
            or ir_dict.get("runtime_language")
            or meta.get("language")
            or meta.get("runtime_language"),
        )
        rt_lang = _lr.value
        rec = recipe_for(_lr)
        parts.append("RUNTIME_LANGUAGE=%s (%s)" % (rt_lang, lang_label_ar(_lr)))
        parts.append(
            "LANGUAGE_RECIPE: image=%s install=%r start=%r manifests=%s"
            % (rec.docker_image, rec.install_command, rec.default_start, list(rec.manifest_files))
        )
    except Exception:
        rt_lang = str(meta.get("language") or ir_dict.get("language") or "python")
        parts.append("RUNTIME_LANGUAGE=%s" % rt_lang)

    if not kind:
        try:
            from lumen.engine.core.project_kind import resolve_project_kind
            kind = resolve_project_kind(text=parts[0] if parts else "").value
        except Exception:
            kind = "general_app"

    parts.append(f"PROJECT_KIND={kind}")
    try:
        from lumen.engine.core.project_kind import cline_kind_rules, parse_kind, runtime_contract
        pk = parse_kind(kind)
        if pk is not None:
            parts.append("KIND_RULES: " + cline_kind_rules(pk))
            rc = runtime_contract(pk)
            parts.append(
                "RUNTIME: start_command={start_command!r} health_path={health_path!r} "
                "port={port} env_keys={env_keys}".format(**rc)
            )
    except Exception:
        pass

    if rt_lang != "python":
        parts.append(
            "NOTE: Prefer LANGUAGE_RECIPE over python-centric KIND_RULES when "
            "RUNTIME_LANGUAGE is not python. Do not force main.py/requirements.txt."
        )

    deliver = {
        "telegram_bot": (
            "Deliver a complete Telegram bot under the workspace "
            "(main entry, requirements, README, env example)."
        ),
        "web_site": (
            "Deliver a complete website: FastAPI export `app`, GET / home, GET /health, "
            "templates/ or static/, requirements, README. uvicorn main:app. "
            "Do NOT build a Telegram bot."
        ),
        "web_api": (
            "Deliver a complete JSON API: FastAPI `app`, routers/, GET /health, "
            "requirements, README. uvicorn main:app. Do NOT build a Telegram bot."
        ),
        "cli_app": (
            "Deliver a CLI with argparse/click in main.py and --help. "
            "Do NOT build a Telegram bot."
        ),
        "library": (
            "Deliver an importable Python package with tests. Do NOT build a Telegram bot."
        ),
    }.get(
        kind,
        "Deliver a runnable project matching PROJECT_KIND and RUNTIME_LANGUAGE. "
        "Do NOT default to Telegram unless PROJECT_KIND=telegram_bot. "
        "Follow LANGUAGE_RECIPE manifests and entry for RUNTIME_LANGUAGE.",
    )
    parts.append(deliver)

    plan = ir_dict.get("execution_plan") or meta.get("execution_plan")
    if plan:
        parts.append("EXECUTION_PLAN_JSON=" + json.dumps(plan, ensure_ascii=False)[:1800])
    repair = ir_dict.get("repair_directive") or meta.get("repair_directive")
    if repair:
        parts.append("REPAIR_DIRECTIVE_JSON=" + json.dumps(repair, ensure_ascii=False)[:1200])
    return "\n".join(parts) if parts else (
        f"Build a complete {kind or 'app'} project for RUNTIME_LANGUAGE={rt_lang} with correct manifests + README."
    )



def build(ir_dict: dict[str, Any], work_dir: str) -> dict[str, Any]:
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    goal = _goal_from_ir(ir_dict if isinstance(ir_dict, dict) else {})

    logger.info("cline agent provider start work_dir=%s", work)
    try:
        from lumen.engine.services.progress_bus import report_progress
        report_progress({
            "phase": "coding_agent",
            "tool": "coding_agent",
            "detail": "بدء الوكيل الحر",
            "step": 0,
        })
    except Exception:
        pass
    state = run_agent(work_dir=work, goal=goal, ir_dict=ir_dict)

    # Phase 5: hard acceptance gate — project must pass check_agent_project
    try:
        from .agent_acceptance import check_agent_project
        acc = state.metadata.get("acceptance") or check_agent_project(work, goal=goal, project_kind=str((state.metadata or {}).get("project_kind") or ""), language=str((state.metadata or {}).get("language") or (state.metadata or {}).get("runtime_language") or "python"))
        if not isinstance(acc, dict):
            acc = check_agent_project(work, goal=goal, project_kind=str((state.metadata or {}).get("project_kind") or ""), language=str((state.metadata or {}).get("language") or (state.metadata or {}).get("runtime_language") or "python"))
        state.metadata["acceptance"] = acc
        _hard_stops = {
            "insufficient_credits",
            "cancelled_by_user",
            "blocked_by_guardrails",
            "llm_billing_unavailable",
        }
        if str(state.stop_reason or "") in _hard_stops:
            # Never promote billing/cancel/guard failures to success
            state.ok = False
            if state.stop_reason == "insufficient_credits" and not any(
                "insufficient_credits" in str(e) for e in (state.errors or [])
            ):
                state.errors.insert(0, "insufficient_credits")
        elif state.ok and not acc.get("ok"):
            state.ok = False
            state.stop_reason = state.stop_reason or "acceptance_failed"
            state.errors.append(
                "acceptance_failed:" + ",".join(str(x) for x in (acc.get("missing") or [])[:8])
            )
        elif not state.ok and acc.get("ok") and (state.files_written or list(work.rglob("*.py"))):
            # Soft stops only (max_steps, time budget, etc.)
            state.ok = True
            state.stop_reason = state.stop_reason or "completed_by_acceptance"
    except Exception as acc_exc:
        state.warnings.append(f"acceptance_gate:{type(acc_exc).__name__}")

    try:
        from lumen.engine.services.progress_bus import report_progress
        acc = state.metadata.get("acceptance") or {}
        report_progress({
            "phase": "finish" if state.ok else "coding_agent",
            "tool": "finish" if state.ok else "coding_agent",
            "detail": (
                "اكتمل الوكيل ✓ قبول"
                if state.ok
                else (state.stop_reason or "توقف")
            ),
            "provider": (state.metadata.get("router") or {}).get("provider"),
            "model": (state.metadata.get("router") or {}).get("model_id"),
            "files_written": len(state.files_written or []),
            "acceptance_ok": bool(acc.get("ok")),
        })
    except Exception:
        pass

    project_path = str(work.resolve()) if state.ok or state.files_written else None

    try:
        audit = work / "CLINE_AGENT.md"
        lines = [
            "# Cline agent run",
            "",
            f"- ok: `{state.ok}`",
            f"- stop_reason: `{state.stop_reason}`",
            f"- model: `{describe_runtime()}`",
            f"- files: `{state.files_written}`",
            "",
            "## Steps",
            "",
        ]
        for s in state.steps:
            lines.append(
                f"{s.index}. tool=`{s.tool_name}` thought=`{(s.thought or '')[:180]}` "
                f"result_ok=`{(s.tool_result or {}).get('ok')}`"
            )
        lines.append("")
        audit.write_text("\n".join(lines), encoding="utf-8")
    except Exception as exc:
        state.warnings.append(f"audit_write:{type(exc).__name__}")

    return {
        "ok": bool(state.ok),
        "project_path": project_path,
        "engine": "cline_agent",
        "errors": list(state.errors),
        "warnings": list(state.warnings),
        "metadata": {
            **dict(state.metadata),
            "stop_reason": state.stop_reason,
            "files_written": list(state.files_written),
            "steps": [s.to_dict() for s in state.steps],
            "model": describe_runtime(),
        },
        "fallback_catalog": (not state.ok and not state.files_written),
    }


__all__ = ["build"]
