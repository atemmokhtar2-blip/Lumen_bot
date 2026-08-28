"""Build UI message bodies from real snapshots (no Telegram, no I/O)."""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import EngineUiPhase, EngineUiState
from .presets import preset_label


@dataclass
class HostRow:
    instance_id: str
    status: str
    bot_username: str = ""
    backend: str = ""


@dataclass
class UiFacts:
    user_id: int = 0
    plan_id: str = ""
    plan_label: str = ""
    generations_per_month: str = ""
    hosted_bots_limit: str = ""
    live_preview_minutes: str = ""
    engine_tier: str = ""
    hosts: list[HostRow] = field(default_factory=list)
    active_project: str = ""
    generate_hint: str = ""


def render_message(state: EngineUiState, facts: UiFacts | None = None) -> str:
    facts = facts or UiFacts()
    phase = state.phase

    if phase in {EngineUiPhase.HOME, EngineUiPhase.IDLE}:
        lines = [
            "أهلاً بك في Lumen",
            "",
            "اختر من الأزرار أو اكتب وصف بوت مباشرة.",
        ]
        if facts.plan_label:
            lines.append(f"خطتك: {facts.plan_label}")
        if facts.active_project:
            lines.append(f"مشروع نشط: `{facts.active_project}`")
        if facts.hosts:
            n_run = sum(1 for h in facts.hosts if h.status == "running")
            lines.append(f"مثيلات استضافة: {len(facts.hosts)} (يعمل: {n_run})")
        return "\n".join(lines)

    if phase == EngineUiPhase.GEN_TYPE:
        lines = [
            "إنشاء بوت — اختر النوع",
            "",
            "بعد الاختيار ستظهر شاشة تأكيد قبل التوليد الحقيقي.",
        ]
        if state.slots.get("awaiting_text") == "1":
            lines.append("")
            lines.append("اكتب وصف البوت الآن في رسالة نصية.")
        if state.missing:
            lines.append("ناقص: " + ", ".join(state.missing))
        return "\n".join(lines)

    if phase == EngineUiPhase.GEN_SLOTS:
        from .engine_needs import remaining_needs
        rem = remaining_needs(state.needs or [], state.slots)
        lines = ["المحرك يطلب توضيحاً قبل التوليد", ""]
        if rem:
            lines.append(f"السؤال ({len(state.missing)} متبقي):")
            lines.append(rem[0].text)
            if rem[0].choices:
                lines.append("اختر من الأزرار أو اكتب في الشات.")
            else:
                lines.append("اكتب الإجابة في الشات.")
        else:
            lines.append("لا يوجد نقص — تابع للتأكيد.")
        filled = [f"{k}={v}" for k, v in state.slots.items() if k not in {"bot_type", "bot_description", "awaiting_text", "awaiting_slot", "confirmed", "intent_kind"} and v]
        if filled:
            lines.append("تم: " + " | ".join(filled[:6]))
        return "\n".join(lines)

    if phase == EngineUiPhase.GEN_CONFIRM:
        tid = state.slots.get("bot_type") or ""
        desc = (state.slots.get("bot_description") or "")[:400]
        lines = [
            "تأكيد التوليد",
            "",
            f"النوع: {preset_label(tid) if tid else '—'}",
            f"الوصف: {desc or '—'}",
        ]
        if facts.plan_label:
            lines.append(f"خطتك: {facts.plan_label}")
        if facts.generations_per_month:
            lines.append(f"حد التوليد: {facts.generations_per_month}/شهر")
        lines.append("")
        lines.append("التوليد يستخدم محرك Lumen الحالي (ليس مساراً وهمياً).")
        return "\n".join(lines)

    if phase == EngineUiPhase.GENERATING:
        return "جاري توليد البوت عبر المحرك…\nلا تغلق الشات."

    if phase == EngineUiPhase.GEN_DONE:
        lines = ["اكتمل التوليد."]
        if state.project_ref:
            lines.append(f"المشروع: `{state.project_ref}`")
        if state.plane and state.plane.value != "none":
            lines.append(f"المستوى: {state.plane.value}")
        lines.append("اختر: تجربة شات | استضافة دائمة | ZIP | معاينة")
        return "\n".join(lines)

    if phase == EngineUiPhase.DASHBOARD:
        lines = ["لوحة التحكم — استضافة حقيقية", ""]
        if facts.active_project:
            lines.append(f"مشروع الجلسة: `{facts.active_project}`")
        count = int((state.slots or {}).get("dash_count") or 0) if (state.slots or {}).get("dash_count", "").isdigit() else 0
        # prefer slot-synced hosts
        shown = 0
        for i in range(5):
            iid = (state.slots or {}).get(f"dash_h{i}") or ""
            if not iid:
                continue
            st = (state.slots or {}).get(f"dash_s{i}") or "?"
            un = (state.slots or {}).get(f"dash_u{i}") or "—"
            be = (state.slots or {}).get(f"dash_b{i}") or "—"
            lines.append(f"#{i+1} `{iid[-12:]}` | {st} | @{un} | {be}")
            shown += 1
        if shown == 0 and facts.hosts:
            for h in facts.hosts[:5]:
                un = f"@{h.bot_username}" if h.bot_username else "—"
                lines.append(f"• `{h.instance_id}` | {h.status} | {un} | {h.backend or '—'}")
            shown = len(facts.hosts[:5])
        if shown == 0:
            lines.append("لا مثيلات HostService لهذا الحساب.")
            lines.append("بعد التوليد: استضافة دائمة + توكن لظهور المثيل هنا.")
        lines.append("")
        lines.append("الأزرار تستدعي status/stop/diagnose من HostService مباشرة.")
        return "\n".join(lines)


    if phase == EngineUiPhase.BILLING:
        lines = ["الرصيد والخطة", ""]
        if facts.plan_label or facts.plan_id:
            lines.append(f"الخطة: {facts.plan_label or facts.plan_id}")
        else:
            lines.append("تعذر قراءة الخطة — جرّب /plan")
        if facts.generations_per_month:
            lines.append(f"• التوليد: {facts.generations_per_month}/شهر")
        if facts.hosted_bots_limit:
            lines.append(f"• استضافة 24/7: {facts.hosted_bots_limit} بوت")
        if facts.live_preview_minutes:
            lines.append(f"• معاينة حية: {facts.live_preview_minutes} دقيقة")
        if facts.engine_tier:
            lines.append(f"• المحرك: {facts.engine_tier}")
        lines.append("")
        lines.append("لا يوجد دفع داخل هذه الشاشة حتى تُفعَّل بوابة دفع حقيقية.")
        return "\n".join(lines)

    if phase == EngineUiPhase.CONTEXT:
        from .ui_events import render_event_message
        return render_event_message(state)

    if phase == EngineUiPhase.HELP:
        return facts.generate_hint or "استخدم /help لعرض القدرات."

    return f"مرحلة `{phase.value}`"
