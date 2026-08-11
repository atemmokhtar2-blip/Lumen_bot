"""Phase 2 — wire Capability Detection into generation + Telegram UX.

Deterministic only. Does not invent capabilities.
"""
from __future__ import annotations

from typing import Any

from ...spec_core.registry import CAPABILITIES
from .engine import detect_capabilities
from .models import DetectionReport, DetectionStatus


def run_detection(request: str) -> DetectionReport:
    return detect_capabilities(request or "")


def feature_keys(report: DetectionReport, *, include_core: bool = True, synthesize: bool = True) -> list[str]:
    """Matched registry keys suitable for session.selected.

    When synthesize=True (default), expands dependencies via Template Synthesis.
    """
    if synthesize:
        try:
            from .synthesis import synthesize_from_report
            plan = synthesize_from_report(report)
            keys = list(plan.keys)
            if not include_core:
                keys = [k for k in keys if k not in {"start", "help"}]
            return keys
        except Exception:
            pass
    keys: list[str] = []
    seen: set[str] = set()
    for m in report.matched:
        if m.key not in CAPABILITIES:
            continue
        if m.key in seen:
            continue
        if not include_core and m.key in {"start", "help"}:
            continue
        seen.add(m.key)
        keys.append(m.key)
    if include_core:
        for core in ("start", "help"):
            if core in CAPABILITIES and core not in seen:
                keys.append(core)
                seen.add(core)
    return keys


def apply_detection_to_session(session: Any, report: DetectionReport) -> list[str]:
    """Merge detection matches into BuilderSession.selected. Returns keys added."""
    if session is None or not hasattr(session, "selected"):
        return []
    added: list[str] = []
    try:
        selected = session.selected
        if not isinstance(selected, set):
            return []
        for key in feature_keys(report, include_core=True):
            if key not in selected and key in CAPABILITIES:
                selected.add(key)
                added.append(key)
    except Exception:
        return []
    return added


def telegram_preflight(request: str) -> dict[str, Any]:
    """Pre-generation gate for the Telegram consumer bot.

    Returns:
      should_block: bool — stop generation entirely
      user_message: str — full rejection text when blocked
      soft_note: str — optional note when generation continues
      report: DetectionReport
    """
    report = run_detection(request)
    feats = feature_keys(report, include_core=False)
    # Phase 4: persist gaps for future research / packs
    if report.gaps:
        try:
            from .gap_journal import record_gaps
            record_gaps(
                request=request,
                gaps=report.gaps,
                detection_status=report.status.value,
            )
        except Exception:
            pass

    if report.status == DetectionStatus.IMPOSSIBLE or not report.can_generate:
        from bot_interface.capability_boundaries import rejection_message

        msg = rejection_message(
            report.reason_ar or "الطلب خارج قدرات المحرك الحتمي",
            report.suggested_scope_ar or "",
        )
        # Append concise detection snapshot
        if report.gaps:
            msg += "\n\n" + "\n".join(
                f"• {g.phrase}: {g.reason}" for g in report.gaps[:4]
            )
        return {
            "should_block": True,
            "user_message": msg,
            "soft_note": "",
            "report": report,
        }

    # Treat lang-only as non-feature for gap decisions
    _incidental = {"lang"}
    _real_feats = [f for f in feats if f not in _incidental]
    if report.status == DetectionStatus.GAP and not _real_feats:
        from bot_interface.capability_boundaries import rejection_message

        msg = rejection_message(
            report.reason_ar or "لا توجد قدرات مطابقة في السجل الحالي",
            report.suggested_scope_ar
            or "جرّب: ترحيب، متجر، تذاكر، نقاط، مسابقات، حجز، اشتراكات",
        )
        if report.gaps:
            msg += "\n\nالفجوات:\n" + "\n".join(
                f"• {g.phrase}: {g.reason}" for g in report.gaps[:5]
            )
        # Phase 5 research note on pure gap (offline-safe)
        try:
            import os as _os
            if _os.getenv("CAPABILITY_RESEARCH_ON_GAP", "1").strip().lower() in {"1", "true", "yes"}:
                from .web_research import research_for_detection_gaps
                _rs = research_for_detection_gaps(report.gaps, request=request, limit=1, persist=True)
                if _rs and _rs[0].get("spec"):
                    _sp = _rs[0]["spec"]
                    _libs = ", ".join((_sp.get("libraries") or [])[:4])
                    msg += "\n\n🔎 مسودة بحث: " + str(_sp.get("title") or "")[:80]
                    if _libs:
                        msg += f"\nمكتبات مرشحة: {_libs}"
                    msg += "\n(لن يُفعَّل تلقائياً — يحتاج موافقة + emit-safe pack)"
        except Exception:
            pass
        return {
            "should_block": True,
            "user_message": msg,
            "soft_note": "",
            "report": report,
        }

    # Weak / nonsense: no bot-intent language and no real product category → block
    _WEAK_CATS = {"utils", "core", "i18n", "general"}
    _req = (request or "").lower()
    _bot_intent = any(
        w in _req
        for w in (
            "بوت", "bot", "أمر", "اوامر", "أوامر", "ترحيب", "متجر", "سلة",
            "تذكرة", "نقاط", "مسابقة", "حجز", "اشتراك", "جروب", "مجموعة",
            "welcome", "shop", "cart", "ticket", "start",
        )
    )
    _product_cats = {
        m.category
        for m in report.matched
        if m.key not in {"start", "help"} and m.category not in _WEAK_CATS
    }
    if not _bot_intent and not _product_cats:
        from bot_interface.capability_boundaries import rejection_message
        msg = rejection_message(
            "الوصف غير واضح كطلب بوت — لم يُرصد قصد منتج واضح",
            "اكتب مثلاً: بوت ترحيب للمجموعة / بوت متجر فيه سلة / بوت تذاكر دعم",
        )
        return {
            "should_block": True,
            "user_message": msg,
            "soft_note": "",
            "report": report,
        }

    soft_parts: list[str] = []
    if report.status == DetectionStatus.GAP and _real_feats:
        soft_parts.append(
            "⚠️ جزء من طلبك غير مدعوم بالكامل؛ سأبني الجزء المتاح من القوالب."
        )
        for g in report.gaps[:3]:
            soft_parts.append(f"• غير متاح: {g.phrase} — {g.reason}")
        soft_parts.append(
            "المدعوم: " + "، ".join(_real_feats[:10]) + ("…" if len(_real_feats) > 10 else "")
        )
        # Phase 5: optional research note (local KB / web) — never auto-registers
        try:
            import os as _os
            if _os.getenv("CAPABILITY_RESEARCH_ON_GAP", "").strip() in {"1", "true", "yes"}:
                from .web_research import research_for_detection_gaps
                _rs = research_for_detection_gaps(report.gaps, request=request, limit=1, persist=True)
                if _rs and _rs[0].get("spec"):
                    _title = (_rs[0]["spec"].get("title") or "")[:80]
                    _libs = ", ".join((_rs[0]["spec"].get("libraries") or [])[:4])
                    soft_parts.append(f"🔎 بحث مسودة: {_title}" + (f" | libs: {_libs}" if _libs else ""))
        except Exception:
            pass
    elif report.status in (DetectionStatus.EXISTS, DetectionStatus.COMPOSABLE) and feats:
        soft_parts.append(
            f"🔧 تم رصد {len(feats)} قدرة من السجل: "
            + "، ".join(feats[:8])
            + ("…" if len(feats) > 8 else "")
        )

    return {
        "should_block": False,
        "user_message": "",
        "soft_note": ("\n".join(soft_parts) if soft_parts else ""),
        "report": report,
    }


def metadata_from_report(report: DetectionReport) -> dict[str, Any]:
    synthesis = None
    try:
        from .synthesis import synthesize_from_report
        synthesis = synthesize_from_report(report).to_dict()
    except Exception:
        synthesis = None
    return {
        "capability_detection": {
            "status": report.status.value,
            "confidence": report.confidence,
            "matched_keys": feature_keys(report, include_core=False, synthesize=False),
            "synthesized_keys": feature_keys(report, include_core=False, synthesize=True),
            "categories": list(report.categories_covered),
            "gaps": [
                {"phrase": g.phrase, "reason": g.reason, "suggested": g.suggested_keys[:5]}
                for g in report.gaps[:8]
            ],
            "can_generate": report.can_generate,
            "reason_ar": report.reason_ar,
            "synthesis": synthesis,
        }
    }


__all__ = [
    "run_detection",
    "feature_keys",
    "apply_detection_to_session",
    "telegram_preflight",
    "metadata_from_report",
]
