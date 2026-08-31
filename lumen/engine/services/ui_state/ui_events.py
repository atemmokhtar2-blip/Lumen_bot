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


def render_event_message(state: EngineUiState) -> str:
    kind = (state.slots or {}).get("ui_event") or ""
    detail = (state.slots or {}).get("ui_event_detail") or ""
    title = event_label_ar(kind)
    lines = [f"تنبيه: {title}", ""]
    if detail:
        lines.append(detail[:800])
        lines.append("")
    lines.append("اختر إجراءً من الأزرار حسب السياق.")
    return "\n".join(lines)
