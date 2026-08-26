"""Phase 9 — Pipeline Trace & Fail-Safe Report.

Runs Detection → Synthesis → Emit assessment → Research note → Learning/Promotion
status in one deterministic pass. Never generates code from research.
"""
from __future__ import annotations

import os
import time
from typing import Any

from .engine import detect_capabilities
from .integration import feature_keys
from .models import DetectionStatus
from .packs.emit_contract import assess_capability
from .synthesis import synthesize_from_report


def pipeline_trace(request: str, *, include_research: bool = True) -> dict[str, Any]:
    """Full transparent pipeline snapshot for a user request."""
    t0 = time.time()
    report = detect_capabilities(request)
    feats = feature_keys(report, include_core=False)
    core_feats = feature_keys(report, include_core=True)
    plan = synthesize_from_report(report)
    # Local block decision — do NOT call telegram_preflight (avoids recursion with soft_note)
    should_block = (
        report.status == DetectionStatus.IMPOSSIBLE
        or not report.can_generate
        or (report.status == DetectionStatus.GAP and not feats)
    )
    pre = {
        "should_block": should_block,
        "soft_note": "",
        "user_message": report.reason_ar or "",
    }

    emit_rows: list[dict[str, Any]] = []
    for key in plan.keys:
        if key in {"start", "help"}:
            continue
        from .catalog import get_capability
        cap = get_capability(key)
        if not cap:
            emit_rows.append({"key": key, "safe": False, "level": "missing", "notes": ["not in registry"]})
            continue
        a = assess_capability(key, cap.service, cap.method)
        emit_rows.append(a.to_dict())

    research_note: dict[str, Any] | None = None
    if include_research and report.gaps:
        try:
            from .web_research import research_for_detection_gaps
            offline = os.getenv("CAPABILITY_RESEARCH_OFFLINE", "1")
            rows = research_for_detection_gaps(report.gaps, request=request, limit=1, persist=False)
            if rows:
                research_note = rows[0]
        except Exception as exc:
            research_note = {"error": str(exc)}

    learning: dict[str, Any] = {}
    try:
        from .learning_loop import learning_stats, load_learned_kb
        from .pack_promotion import promotion_status
        learning = {
            "stats": learning_stats(),
            "learned_entries": len(load_learned_kb()),
            "promotion": promotion_status(),
        }
    except Exception as exc:
        learning = {"error": str(exc)}

    unsafe = [e for e in emit_rows if not e.get("safe")]
    scaffold_keys = [k for k in plan.keys if k.startswith("scaffold_") or k.startswith("pack_learned_")]

    # Fail-safe user-facing summary
    if pre.get("should_block"):
        fail_safe = {
            "level": "block",
            "title_ar": "لا يمكن توليد البوت لهذا الطلب",
            "detail_ar": (pre.get("user_message") or "")[:500],
            "alternatives_ar": [
                "رحّب + قوانين",
                "متجر + سلة",
                "تذاكر دعم",
                "ترجمة عبر /translate (scaffold)",
            ],
        }
    elif report.gaps and feats:
        alts = []
        if research_note and isinstance(research_note, dict):
            sp = research_note.get("spec") or {}
            libs = sp.get("libraries") or []
            if libs:
                alts.append("بحث: " + ", ".join(str(x) for x in libs[:4]))
        fail_safe = {
            "level": "partial",
            "title_ar": "توليد جزئي — بعض الأجزاء غير مكتملة",
            "detail_ar": "؛ ".join(f"{g.phrase}: {g.reason}" for g in report.gaps[:3]),
            "available_ar": feats[:12],
            "scaffolds_ar": scaffold_keys,
            "alternatives_ar": alts,
        }
    elif unsafe:
        fail_safe = {
            "level": "emit_risk",
            "title_ar": "بعض القدرات ستُستبدل بـ scaffold آمن",
            "detail_ar": "، ".join(f"{u.get('key')}:{u.get('level')}" for u in unsafe[:5]),
            "available_ar": feats[:12],
        }
    else:
        # map keys to friendly commands when possible
        try:
            from .catalog import DEFAULT_COMMANDS
            cmds = []
            for k in plan.keys:
                if k in {"start", "help"}:
                    continue
                c = DEFAULT_COMMANDS.get(k) or k
                cmds.append(f"/{c}")
        except Exception:
            cmds = []
        fail_safe = {
            "level": "ok",
            "title_ar": "جاهز للتوليد الحتمي",
            "detail_ar": f"{len(plan.keys)} قدرة — status={plan.status}",
            "available_ar": plan.keys[:16],
            "scaffolds_ar": scaffold_keys,
            "commands_ar": cmds[:12],
        }

    return {
        "ok": True,
        "request": request,
        "elapsed_ms": int((time.time() - t0) * 1000),
        "detection": {
            "status": report.status.value,
            "can_generate": report.can_generate,
            "confidence": report.confidence,
            "matched_keys": [m.key for m in report.matched],
            "feature_keys": feats,
            "gaps": [g.to_dict() if hasattr(g, "to_dict") else {
                "phrase": g.phrase, "reason": g.reason
            } for g in report.gaps],
            "reason_ar": report.reason_ar,
        },
        "preflight": {
            "should_block": pre.get("should_block"),
            "soft_note": (pre.get("soft_note") or "")[:400],
        },
        "synthesis": {
            "status": plan.status,
            "keys": plan.keys,
            "dropped": getattr(plan, "dropped", []) or [],
            "warnings": list(getattr(plan, "warnings", []) or [])[:12],
        },
        "emit": {
            "assessments": emit_rows,
            "unsafe_count": len(unsafe),
        },
        "research": research_note,
        "learning": learning,
        "fail_safe": fail_safe,
        "core_keys": core_feats,
    }


def fail_safe_message(trace: dict[str, Any]) -> str:
    """Arabic user-facing summary from a pipeline_trace result."""
    fs = trace.get("fail_safe") or {}
    lines = [str(fs.get("title_ar") or "تقرير المسار")]
    if fs.get("detail_ar"):
        lines.append(str(fs["detail_ar"]))
    if fs.get("available_ar"):
        lines.append("المتاح: " + "، ".join(str(x) for x in fs["available_ar"][:10]))
    if fs.get("scaffolds_ar"):
        lines.append("Scaffold: " + "، ".join(str(x) for x in fs["scaffolds_ar"][:8]))
    if fs.get("alternatives_ar"):
        lines.append("بدائل: " + " / ".join(str(x) for x in fs["alternatives_ar"][:6]))
    if fs.get("commands_ar"):
        lines.append("أوامر: " + " ".join(str(x) for x in fs["commands_ar"][:10]))
    det = trace.get("detection") or {}
    lines.append(f"الحالة: {det.get('status')} — ثقة {det.get('confidence')}")
    return "\n".join(lines)


__all__ = ["pipeline_trace", "fail_safe_message"]
