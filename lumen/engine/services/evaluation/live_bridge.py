"""Bridge multi_agent run reports / AgentState → EvalRunRecord (Phase D live path)."""
from __future__ import annotations

import time
from typing import Any

from .cost_model import estimate_cost_usd
from .eval_store import append_eval_record
from .run_record import EvalRunRecord, finalize_record


def _usage_from_state(state: Any) -> dict[str, Any]:
    ext = getattr(state, "extensions", None) or {}
    usage = dict(ext.get("usage") or {})
    meta = getattr(state, "metadata", None) or {}
    if isinstance(meta, dict):
        for k, v in (meta.get("usage") or {}).items():
            usage.setdefault(k, v)
    return usage


def record_from_agent_state(state: Any, *, scenario_id: str = "live_orchestration") -> EvalRunRecord:
    usage = _usage_from_state(state)
    platform = "telegram"
    ext = getattr(state, "extensions", None) or {}
    platform = str(ext.get("platform") or ext.get("target_platform") or platform)
    if (getattr(state, "generated_path", None) or ""):
        try:
            from pathlib import Path
            pm = Path(state.generated_path) / "PLATFORM.md"
            if pm.is_file():
                platform = pm.read_text(encoding="utf-8").split("platform:", 1)[-1].split()[0].strip() or platform
        except Exception:
            pass
    success = bool(getattr(state, "qa_passed", False)) or str(getattr(state, "status", "")) in {
        "passed",
        "PASSED",
        "AgentStatus.PASSED",
    }
    # status enum may be .value
    st = getattr(state, "status", "")
    if hasattr(st, "value"):
        success = success or str(st.value).lower() in {"passed", "done", "success"}
    errors = list((getattr(state, "qa_report", None) or {}).get("errors") or [])[:15]
    errors += list(getattr(state, "build_errors", None) or [])[:5]
    rec = EvalRunRecord(
        scenario_id=scenario_id,
        platform=platform,
        attempts=int(getattr(state, "attempts", 0) or 0),
        cost_usd=estimate_cost_usd(usage),
        metrics={
            "state_id": getattr(state, "state_id", ""),
            "status": str(getattr(st, "value", st)),
            "usage": usage,
            "findings_count": len(ext.get("findings") or []),
            "generated_path": getattr(state, "generated_path", "") or "",
        },
        started_at=float(ext.get("started_at") or time.time()) - float(ext.get("elapsed_s") or 0.0),
    )
    finalize_record(rec, success=success, errors=[str(e) for e in errors])
    if ext.get("elapsed_s") is not None:
        try:
            rec.latency_s = float(ext["elapsed_s"])
        except (TypeError, ValueError):
            pass
    return rec


def record_from_run_report(report: dict[str, Any]) -> EvalRunRecord:
    cost = dict(report.get("cost") or {})
    usage = dict(cost.get("usage") or report.get("usage") or {})
    success = bool(report.get("qa_passed"))
    rec = EvalRunRecord(
        scenario_id="run_report",
        platform=str(report.get("platform") or "unknown"),
        attempts=int(report.get("attempts") or cost.get("attempts") or 0),
        cost_usd=estimate_cost_usd(usage),
        metrics={
            "state_id": report.get("state_id"),
            "status": report.get("status"),
            "usage": usage,
            "findings_count": report.get("findings_count"),
        },
    )
    finalize_record(rec, success=success, errors=[str(e) for e in (report.get("errors") or [])[:15]])
    return rec


def persist_state_evaluation(state: Any, *, scenario_id: str = "live_orchestration") -> dict[str, Any]:
    rec = record_from_agent_state(state, scenario_id=scenario_id)
    path = append_eval_record(rec)
    try:
        from lumen.engine.services.multi_agent.metrics import record_eval_outcome

        record_eval_outcome(
            success=rec.success,
            attempts=rec.attempts,
            latency_s=rec.latency_s,
            cost_usd=rec.cost_usd,
            platform=rec.platform,
        )
    except Exception:
        pass
    return {"ok": True, "path": str(path), "record": rec.to_dict()}


__all__ = [
    "record_from_agent_state",
    "record_from_run_report",
    "persist_state_evaluation",
]
