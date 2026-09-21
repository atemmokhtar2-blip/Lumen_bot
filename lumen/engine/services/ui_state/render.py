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
            "🔮 مرحباً بك في Lumen",
            [
                (
                    "✨ ماذا تقدر تعمل؟",
                    "• ✨ إنشاء بوت — اكتب وصفاً واحداً\n"
                    "• 📦 القوالب — بوتات جاهزة للتجربة أو الاستخدام\n"
                    "• 💎 الرصيد — رصيدك الحالي فقط\n"
                    "• 📊 لوحة التحكم — الاستضافة والمشاريع\n"
                    "• ❓ المساعدة — شرح سريع للأوامر",
                ),
            ],
            subtitle="المنصة الأولى لإنشاء وإدارة بوتات المحادثة دون برمجة",
        )

    if phase == EngineUiPhase.GEN_TYPE:
        return html_card(
            "✨ إنشاء بوت",
            [
                (
                    "✍️ اكتب الوصف",
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
        return html_card("🧠 قبل التوليد", sections)

    if phase == EngineUiPhase.GEN_CONFIRM:
        desc = (state.slots.get("bot_description") or "")[:400] or "—"
        return html_card(
            "✅ تأكيد التوليد",
            [("الوصف", desc)],
        )

    if phase == EngineUiPhase.GENERATING:
        return html_card(
            "⚙️ جاري التوليد",
            [("الحالة", "المحرك يبني البوت الآن.\nلا تغلق الشات حتى يكتمل.")],
        )

    if phase == EngineUiPhase.GEN_DONE:
        body = "اختر الخطوة التالية من الأزرار."
        if state.project_ref:
            body = f"المسار: {state.project_ref}\n\n" + body
        if state.plane and state.plane.value != "none":
            body = f"المستوى: {state.plane.value}\n" + body
        return html_card(
            "🎉 اكتمل التوليد",
            [
                ("المشروع", body),
                (
                    "🔧 الخيارات",
                    "• 🧪 تجربة في الشات — تشغيل مؤقت\n"
                    "• 🚀 استضافة دائمة\n"
                    "• 📦 ZIP أو معاينة",
                ),
            ],
        )


    if phase == EngineUiPhase.SETTINGS:
        return html_card(
            "⚙️ الإعدادات",
            [
                (
                    "الخيارات",
                    "• 🔗 الاتصالات — ربط GitHub وعرض مستودعاتك الرسمية.\n"
                    "• 🎁 الإحالة — ادعُ أصدقاءك واحصل على $5 عند 50 مستخدماً نشطاً.",
                ),
            ],
            subtitle="إعدادات الحساب",
        )

    if phase == EngineUiPhase.CONNECTIONS:
        gh_line = (state.slots or {}).get("conn_github_line") or "GitHub: —"
        return html_card(
            "🔗 الاتصالات",
            [
                ("الحالة", gh_line),
                (
                    "المزوّدون",
                    "• GitHub — اتصال رسمي (api.github.com) لعرض مستودعاتك.\n"
                    "مزوّدون إضافيون لاحقاً من نفس القائمة.",
                ),
            ],
            subtitle="ربط الحسابات",
        )

    if phase == EngineUiPhase.CONN_GITHUB:
        login = (state.slots or {}).get("gh_login") or ""
        status = (state.slots or {}).get("gh_status_line") or ""
        bound = (state.slots or {}).get("gh_bound_path") or ""
        selected = (state.slots or {}).get("gh_selected_full") or ""
        last_sync = (state.slots or {}).get("gh_last_sync") or ""
        perms = (state.slots or {}).get("gh_perms_line") or ""
        if (state.slots or {}).get("gh_await_disconnect") == "1":
            body = (
                "⚠️ تأكيد فصل الاتصال: سيتم حذف أسرار GitHub من Lumen نهائيًا. "
                "اضغط «تأكيد الفصل» للمتابعة أو «تحديث القائمة» للإلغاء."
            )
        elif (state.slots or {}).get("gh_connected") == "1":
            body = status or (
                f"متصل{(' كـ @' + login) if login else ''}. اختر مستودعاً من الأزرار."
            )
        else:
            body = status or (
                "غير متصل. اضغط «اتصل بـ GitHub» لربط التطبيق، "
                "أو «ربط يدوي (PAT)» للمسار المتقدم."
            )
        sections = [("الحالة", body)]
        if perms:
            sections.append(("الصلاحيات", perms))
        if last_sync:
            sections.append(("آخر مزامنة", last_sync))
        if selected:
            sections.append(("المختار", selected))
        if bound:
            sections.append(("المسار", bound))
        sections.append(
            (
                "ملاحظة",
                "القراءة تلقائية بعد الربط. الدفع وفتح PR يحتاجان تأكيدًا منفصلًا.",
            )
        )
        return html_card(
            "🐙 GitHub",
            sections,
            subtitle="اتصال رسمي",
        )

    if phase == EngineUiPhase.REFERRAL:
        link = (state.slots or {}).get("referral_link") or ""
        stats_line = (state.slots or {}).get("referral_stats_line") or "—"
        return html_card(
            "🎁 برنامج الإحالة — $5",
            [
                ("رابطك", link or "اضغط تحديث لجلب الرابط"),
                ("التقدم", stats_line),
                (
                    "الشروط",
                    "المكافأة لمن يستخدم البوت فقط. كل 10 نشطين ≈ $1 حتى $5 عند 50.",
                ),
            ],
            subtitle="مشاركة الرابط",
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
                "🔄 تحديث · 📡 حالة · 🧪 تجربة · 🚀 نشر\n"
                "⏹ إيقاف · 🩺 تشخيص — مباشرة من HostService.",
            ),
        ]
        if facts.active_project:
            sections.insert(0, ("مشروع الجلسة", str(facts.active_project)))
        return html_card(
            "📊 لوحة المشاريع والاستضافة",
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
            "💎 الرصيد",
            [("💳 حسابك", body)],
            subtitle="نظام الكريدت",
        )

    if phase == EngineUiPhase.PRO_PLAN:
        from .pro_plan import (
            PRO_PLAN_TITLE,
            PRO_PLAN_PRICE_USD,
            PRO_PLAN_PRICE_STARS,
            PRO_PLAN_DURATION_LABEL,
            PRO_PLAN_BOT_LIMIT,
            pro_plan_includes_text,
        )

        includes = pro_plan_includes_text()
        body = (
            f"السعر: ${PRO_PLAN_PRICE_USD} شهريًا — {PRO_PLAN_PRICE_STARS} ⭐\n"
            f"المدة: {PRO_PLAN_DURATION_LABEL}\n\n"
            f"✅ الاشتراك يشمل:\n{includes}\n\n"
            f"💳 نظام الرصيد: كريديتات تُخصم حسب الاستخدام.\n"
            f"🤖 حتى {PRO_PLAN_BOT_LIMIT} بوتات مع استضافة دائمة.\n\n"
            f"اضغط «اشترك — {PRO_PLAN_PRICE_STARS} ⭐» للدفع بنجوم تيليجرام."
        )
        return html_card(
            PRO_PLAN_TITLE,
            [("تفاصيل الخطة", body)],
            subtitle=f"${PRO_PLAN_PRICE_USD}/شهر — {PRO_PLAN_PRICE_STARS} ⭐",
        )

    if phase == EngineUiPhase.CONTEXT:
        from .ui_events import render_event_message

        raw = render_event_message(state)
        # Wrap plain event text in expandable card when not already HTML
        if raw and "<blockquote" not in raw:
            return html_card("تحديث", [("", raw)])
        return raw

    if phase == EngineUiPhase.TEMPLATES:
        _how = chr(10).join([
            "1) اختر قالباً من الأزرار 👇",
            "2) ⏱ تجربة مؤقتة (حتى 50 دقيقة) أو 🚀 استخدام دائم (30 يوماً)",
            "3) أرسل توكن @BotFather عند الطلب 🔑",
            "🆓 الحد المجاني: 3 قوالب شغّالة — Pro حتى 10.",
        ])
        return html_card(
            "📦 القوالب الجاهزة",
            [
                ("🧭 كيف تستخدمها؟", _how),
                (
                    "🤖 بوتاتي",
                    "من زر «بوتاتي من القوالب» ترى الحالة والمتبقي وتوقف ما لا تحتاجه.",
                ),
            ],
            subtitle="جاهز للتشغيل — بدون برمجة",
        )

    if phase == EngineUiPhase.TEMPLATE_DETAIL:
        title = escape_html((state.slots.get("template_title") or "قالب").strip() or "قالب")
        desc = escape_html((state.slots.get("template_description") or "").strip() or "—")
        return html_card(
            title,
            [
                ("الوصف", desc),
                (
                    "التشغيل",
                    "• تجربة مؤقتة — تختار المدة (حد أقصى 50 دقيقة)\n"
                    "• استخدام دائم — يبقى حتى شهر ضمن حد الـ 3 بوتات",
                ),
            ],
        )

    if phase == EngineUiPhase.TEMPLATE_TRIAL_MINUTES:
        return html_card(
            "⏱ مدة التجربة المؤقتة",
            [
                (
                    "اختر الدقائق",
                    "الحد الأقصى 50 دقيقة. بعد الحجز يُجهَّز التشغيل على مسار الاستضافة.",
                ),
            ],
        )

    if phase == EngineUiPhase.TEMPLATE_STATUS:
        lines: list[str] = []
        for i in range(5):
            title = (state.slots.get(f"tpl_t{i}") or "").strip()
            if not title:
                continue
            st = escape_html((state.slots.get(f"tpl_s{i}") or "?").strip())
            rem = escape_html((state.slots.get(f"tpl_r{i}") or "—").strip())
            mode = escape_html((state.slots.get(f"tpl_m{i}") or "").strip())
            line = f"{escape_html(title)} — {st} — متبقي: {rem}"
            if mode:
                line += f" ({mode})"
            lines.append(line)
        body = chr(10).join(lines) if lines else "لا توجد قوالب شغّالة أو محجوزة حاليًا."
        return html_card(
            "🤖 بوتاتي من القوالب",
            [
                ("الحالة", body),
                (
                    "الحد المجاني",
                    "حتى 3 قوالب شغّالة معًا. الإيقاف يحرّر مقعدًا فورًا.",
                ),
            ],
            subtitle="حالة القوالب فقط",
        )

    if phase == EngineUiPhase.HELP:

        from lumen.bot.telegram_text import looks_like_telegram_html

        hint = (facts.generate_hint or "").strip()
        # get_help_text() is already a full HTML card — never nest/escape it again
        if hint and looks_like_telegram_html(hint):
            return hint
        main = chr(10).join(
            [
                "• ✨ إنشاء بوت — اكتب وصفاً واحداً",
                "• 💎 الرصيد — رصيدك الحالي",
                "• 📊 لوحة التحكم — مشاريعك والاستضافة",
                "• 🏠 /start — القائمة الرئيسية",
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

