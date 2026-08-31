"""Batch 6 — contextual UI events driven by engine/platform outcomes."""
from __future__ import annotations

from enum import Enum
from typing import Any

from .models import EngineUiPhase, EngineUiState, UiButton


class UiEventKind(str, Enum):
    GENERATION_FAILED = "generation_failed"
    INSUFFICIENT_QUOTA = "insufficient_quota"
    HOST_LIMIT = "host_limit"
    HOST_FAILED = "host_failed"
    SANDBOX_UNAVAILABLE = "sandbox_unavailable"
    NO_PROJECT = "no_project"
    CLARIFY_NEEDED = "clarify_needed"


_LABELS_AR = {
    UiEventKind.GENERATION_FAILED: "فشل التوليد",
    UiEventKind.INSUFFICIENT_QUOTA: "حد التوليد / الرصيد غير كافٍ",
    UiEventKind.HOST_LIMIT: "وصلت لحد الاستضافة",
    UiEventKind.HOST_FAILED: "فشلت الاستضافة",
    UiEventKind.SANDBOX_UNAVAILABLE: "العزل غير متاح",
    UiEventKind.NO_PROJECT: "لا يوجد مشروع",
    UiEventKind.CLARIFY_NEEDED: "المحرك يحتاج توضيحاً",
}


def event_label_ar(kind: UiEventKind | str) -> str:
    try:
        k = kind if isinstance(kind, UiEventKind) else UiEventKind(str(kind))
    except ValueError:
        return str(kind)
    return _LABELS_AR.get(k, str(kind))


def buttons_for_event(kind: UiEventKind | str) -> tuple[tuple[UiButton, ...], ...]:
    try:
        k = kind if isinstance(kind, UiEventKind) else UiEventKind(str(kind))
    except ValueError:
        return ((UiButton("القائمة", "home"),),)

    # Weakness 4: event-specific action buttons only.
    # The unified bottom nav [رجوع][الصفحة الرئيسية][إلغاء] is appended
    # by buttons_for_state(), so we no longer include redundant "home" rows.
    if k is UiEventKind.GENERATION_FAILED:
        return (
            (UiButton("إعادة المحاولة", "retry_generate"), UiButton("تعديل الوصف", "open_generate")),
            (UiButton("المساعدة", "open_help"),),
        )
    if k is UiEventKind.INSUFFICIENT_QUOTA:
        return (
            (UiButton("عرض الخطة", "open_billing"),),
        )
    if k is UiEventKind.HOST_LIMIT:
        return (
            (UiButton("لوحة التحكم", "open_dashboard"), UiButton("الخطة", "open_billing")),
        )
    if k is UiEventKind.HOST_FAILED:
        return (
            (UiButton("لوحة التحكم", "open_dashboard"),),
            (UiButton("المساعدة", "open_help"),),
        )
    if k is UiEventKind.SANDBOX_UNAVAILABLE:
        return (
            (UiButton("المساعدة", "open_help"),),
        )
    if k is UiEventKind.NO_PROJECT:
        return (
            (UiButton("إنشاء بوت", "open_generate"),),
        )
    if k is UiEventKind.CLARIFY_NEEDED:
        return (
            (UiButton("أكمل الناقص", "resume_slots"), UiButton("توليد بما هو متاح", "to_confirm")),
        )
    return ()


def apply_event(
    state: EngineUiState,
    kind: UiEventKind | str,
    *,
    detail: str = "",
) -> EngineUiState:
    """Stamp contextual event onto state (phase CONTEXT)."""
    try:
        k = kind if isinstance(kind, UiEventKind) else UiEventKind(str(kind))
        kind_s = k.value
    except ValueError:
        kind_s = str(kind)
    new = EngineUiState(
        phase=EngineUiPhase.CONTEXT,
        slots=dict(state.slots),
        missing=list(state.missing),
        project_ref=state.project_ref,
        plane=state.plane,
        last_action=f"event:{kind_s}",
        needs=list(state.needs or []),
        version=state.version,
    )
    new.slots["ui_event"] = kind_s
    if detail:
        new.slots["ui_event_detail"] = str(detail)[:500]
    return new


_DETAIL_AR: dict[UiEventKind, str] = {
    UiEventKind.GENERATION_FAILED: (
        "تعذّر توليد البوت. تحقّق من وضوح الوصف وحاول مرة أخرى، "
        "أو عدّل الوصف ليكون أكثر تفصيلاً."
    ),
    UiEventKind.INSUFFICIENT_QUOTA: (
        "رصيدك من الكريديت غير كافٍ لإتمام هذه العملية. "
        "راجع الخطط لإعادة شحن رصيدك."
    ),
    UiEventKind.HOST_LIMIT: (
        "وصلت إلى الحد الأقصى لعدد البوتات المستضافة في خطتك. "
        "أوقف بوتاً غير مستخدم أو راجع الخطة."
    ),
    UiEventKind.HOST_FAILED: (
        "تعذّر تشغيل البوت. حاول مرة أخرى بعد لحظات، "
        "وإذا استمرت المشكلة راجع لوحة التحكم."
    ),
    UiEventKind.SANDBOX_UNAVAILABLE: (
        "بيئة التشغيل غير متاحة حالياً. حاول مرة أخرى بعد لحظات."
    ),
    UiEventKind.NO_PROJECT: (
        "لا يوجد مشروع حالي. ابدأ بإنشاء بوت جديد."
    ),
    UiEventKind.CLARIFY_NEEDED: (
        "يحتاج المحرك إلى تفاصيل إضافية ليتمكن من بناء البوت بشكل صحيح."
    ),
}


def _sanitize_detail(raw: str, kind_s: str) -> str:
    """Return a safe, user-facing detail string.

    The raw engine detail may contain stack traces, module names, or English
    error text — never expose those to the end user. We only keep short
    Arabic-friendly fragments and strip obvious technical markers.
    """
    if not raw:
        return ""
    # Reject anything that looks like a stack trace or path
    if any(m in raw for m in ("Traceback", ".py", "line ", "Error: ", "Exception:")):
        return ""
    # Reject file paths (server filesystem layout)
    if "/" in raw and raw.count("/") >= 2:
        return ""
    # Only keep if it's reasonably short and doesn't look like code
    if len(raw) > 200:
        return ""
    return raw.strip()


def render_event_message(state: EngineUiState) -> str:
    kind = (state.slots or {}).get("ui_event") or ""
    raw_detail = (state.slots or {}).get("ui_event_detail") or ""
    title = event_label_ar(kind)

    # User-friendly explanation per event kind
    try:
        k = UiEventKind(str(kind)) if kind else None
    except ValueError:
        k = None
    explanation = _DETAIL_AR.get(k, "") if k else ""

    lines: list[str] = [f"⚠️ {title}", ""]
    if explanation:
        lines.append(explanation)
        lines.append("")
    # Only append sanitized detail — never raw engine errors
    safe_detail = _sanitize_detail(raw_detail, kind)
    if safe_detail and safe_detail != explanation:
        lines.append(f"ℹ️ {safe_detail}")
        lines.append("")
    lines.append("اختر إجراءً من الأزرار بالأسفل 👇")
    return "\n".join(lines)
