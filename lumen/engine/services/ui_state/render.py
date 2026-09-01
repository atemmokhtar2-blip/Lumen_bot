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
    # Credits-first economy (primary UX surface)
    credits_balance: int = 0
    credits_reserved: int = 0
    credits_available: int = 0
    gen_cost_credits: int = 50
    host_hourly_credits: int = 10


def render_message(state: EngineUiState, facts: UiFacts | None = None) -> str:
    facts = facts or UiFacts()
    from lumen.bot.telegram_text import html_card, escape_html

    phase = state.phase

    if phase in {EngineUiPhase.HOME, EngineUiPhase.IDLE}:
        # Homepage — balance only under open_billing (product rule)
        return html_card(
            "مرحباً بك في Lumen 🔮",
            [
                (
                    "ماذا تقدر تعمل؟",
                    "• إنشاء بوت — اكتب وصفاً واحداً\n"
                    "• الرصيد — رصيدك الحالي فقط\n"
                    "• لوحة التحكم — الاستضافة والمشاريع\n"
                    "• المساعدة — شرح سريع للأوامر",
                ),
            ],
            subtitle="المنصة الأولى لإنشاء وإدارة بوتات المحادثة دون برمجة",
        )

    if phase == EngineUiPhase.GEN_TYPE:
        return html_card(
            "إنشاء بوت",
            [
                (
                    "اكتب الوصف",
                    "اكتب وصف البوت في رسالة واحدة تحت هذا الصندوق.\n"
                    "مثال: بوت متجر يرد على الطلبات ويحسب الفواتير ويرسل إشعارات.",
                ),
            ],
            subtitle="رسالة واحدة واضحة تكفي للبدء",
        )

    if phase == EngineUiPhase.GEN_SLOTS:
        from .engine_needs import remaining_needs

        rem = remaining_needs(state.needs or [], state.slots)
        body_lines: list[str] = []
        if rem:
            body_lines.append(f"السؤال ({len(state.missing)} متبقي):")
            body_lines.append(rem[0].text)
            if rem[0].choices:
                body_lines.append("اختر من الأزرار أو اكتب في الشات.")
            else:
                body_lines.append("اكتب الإجابة في الشات.")
        else:
            body_lines.append("لا يوجد نقص — تابع للتأكيد.")
        filled = [
            f"{k}={v}"
            for k, v in state.slots.items()
            if k
            not in {
                "bot_type",
                "bot_description",
                "awaiting_text",
                "awaiting_slot",
                "confirmed",
                "intent_kind",
            }
            and v
        ]
        sections: list[tuple[str, str]] = [
            ("المحرك يطلب توضيحاً", "\n".join(body_lines)),
        ]
        if filled:
            sections.append(("ما تم تسجيله", " | ".join(filled[:6])))
        return html_card("قبل التوليد", sections)

    if phase == EngineUiPhase.GEN_CONFIRM:
        desc = (state.slots.get("bot_description") or "")[:400] or "—"
        return html_card(
            "تأكيد التوليد",
            [("الوصف", desc)],
        )

    if phase == EngineUiPhase.GENERATING:
        return html_card(
            "جاري التوليد",
            [("الحالة", "المحرك يبني البوت الآن.\nلا تغلق الشات حتى يكتمل.")],
        )

    if phase == EngineUiPhase.GEN_DONE:
        body = "اختر الخطوة التالية من الأزرار."
        if state.project_ref:
            body = f"المسار: {state.project_ref}\n\n" + body
        if state.plane and state.plane.value != "none":
            body = f"المستوى: {state.plane.value}\n" + body
        return html_card(
            "اكتمل التوليد",
            [
                ("المشروع", body),
                (
                    "الخيارات",
                    "• تجربة في الشات — تشغيل مؤقت\n"
                    "• استضافة دائمة — Firecracker\n"
                    "• ZIP أو معاينة",
                ),
            ],
        )

    if phase == EngineUiPhase.DASHBOARD:
        host_lines: list[str] = []
        shown = 0
        for i in range(5):
            iid = (state.slots or {}).get(f"dash_h{i}") or ""
            if not iid:
                continue
            st = (state.slots or {}).get(f"dash_s{i}") or "?"
            un = (state.slots or {}).get(f"dash_u{i}") or "—"
            be = (state.slots or {}).get(f"dash_b{i}") or "—"
            host_lines.append(f"#{i + 1} {iid[-12:]} | {st} | @{un} | {be}")
            shown += 1
        if shown == 0 and facts.hosts:
            for h in facts.hosts[:5]:
                un = f"@{h.bot_username}" if h.bot_username else "—"
                host_lines.append(
                    f"• {h.instance_id} | {h.status} | {un} | {h.backend or '—'}"
                )
            shown = len(facts.hosts[:5])
        if shown == 0:
            host_lines = [
                "لا مثيلات HostService لهذا الحساب.",
                "بعد التوليد: استضافة دائمة + توكن لظهور المثيل هنا.",
            ]
        sections = [
            ("المثيلات", "\n".join(host_lines)),
            (
                "الأزرار",
                "تحديث القائمة — حالة الكل — تجربة/استضافة المشروع\n"
                "status / stop / diagnose من HostService مباشرة.",
            ),
        ]
        if facts.active_project:
            sections.insert(0, ("مشروع الجلسة", str(facts.active_project)))
        return html_card(
            "لوحة التحكم — استضافة حقيقية",
            sections,
            subtitle="إدارة المثيلات من HostService",
        )

    if phase == EngineUiPhase.BILLING:
        bal = int(facts.credits_available or facts.credits_balance or 0)
        reserved = int(facts.credits_reserved or 0)
        body = f"المتاح: {bal} كريدت"
        if reserved:
            body += f"\nمحجوز: {reserved} كريدت"
        body += "\n\nالرصيد يخصم حسب التوليد والاستضافة."
        return html_card(
            "الرصيد",
            [("حسابك", body)],
            subtitle="نظام الكريدت",
        )

    if phase == EngineUiPhase.CONTEXT:
        from .ui_events import render_event_message

        raw = render_event_message(state)
        # Wrap plain event text in expandable card when not already HTML
        if raw and "<blockquote" not in raw:
            return html_card("تحديث", [("", raw)])
        return raw

    if phase == EngineUiPhase.HELP:
        from lumen.bot.telegram_text import looks_like_telegram_html

        hint = (facts.generate_hint or "").strip()
        # get_help_text() is already a full HTML card — never nest/escape it again
        if hint and looks_like_telegram_html(hint):
            return hint
        main = chr(10).join(
            [
                "• إنشاء بوت — اكتب وصفاً واحداً",
                "• الرصيد — رصيدك الحالي",
                "• لوحة التحكم — مشاريعك والاستضافة",
                "• /start — القائمة الرئيسية",
            ]
        )
        sections: list[tuple[str, str]] = [("الأوامر", main)]
        if hint and hint not in main:
            sections.append(("تفاصيل", hint[:1500]))
        return html_card(
            "المساعدة",
            sections,
            subtitle="دليل سريع للأوامر",
        )

    return html_card("مرحلة", [("", escape_html(str(phase.value)))])

