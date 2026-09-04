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
    import json
    parts: list[str] = []
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
    lang = ir_dict.get("language") or "ar"
    parts.append(f"Primary language: {lang}")
    parts.append(
        "Deliver a complete Telegram bot project under the workspace "
        "(main entry, requirements, README, env example)."
    )
    meta = ir_dict.get("metadata") if isinstance(ir_dict.get("metadata"), dict) else {}
    plan = ir_dict.get("execution_plan") or meta.get("execution_plan")
    if plan:
        parts.append("EXECUTION_PLAN_JSON=" + json.dumps(plan, ensure_ascii=False)[:1800])
    repair = ir_dict.get("repair_directive") or meta.get("repair_directive")
    if repair:
        parts.append("REPAIR_DIRECTIVE_JSON=" + json.dumps(repair, ensure_ascii=False)[:1200])
    return "\n".join(parts) if parts else (
        "Build a complete Telegram bot project with main.py, requirements.txt, README."
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
        acc = state.metadata.get("acceptance") or check_agent_project(work, goal=goal)
        if not isinstance(acc, dict):
            acc = check_agent_project(work, goal=goal)
        state.metadata["acceptance"] = acc
        if state.ok and not acc.get("ok"):
            state.ok = False
            state.stop_reason = state.stop_reason or "acceptance_failed"
            state.errors.append(
                "acceptance_failed:" + ",".join(str(x) for x in (acc.get("missing") or [])[:8])
            )
        elif not state.ok and acc.get("ok") and (state.files_written or list(work.rglob("*.py"))):
            # Built enough to accept even if loop stop_reason was soft
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
