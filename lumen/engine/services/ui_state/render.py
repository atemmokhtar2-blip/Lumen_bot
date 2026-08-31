"""Build UI message bodies from real snapshots (no Telegram, no I/O).

Professional-grade Arabic UX — every screen is clear, welcoming, and
actionable. No technical jargon exposed to the end user.

All text is plain (no Markdown here) — the Telegram send layer
(chat_hygiene / safe_reply_text) handles MarkdownV2 conversion.
Emojis are used as visual section markers for scannability.
"""
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


# ---------------------------------------------------------------------------
# Status translation — engine-internal labels → human Arabic
# ---------------------------------------------------------------------------
_STATUS_AR: dict[str, str] = {
    "running": "🟢 يعمل",
    "active": "🟢 يعمل",
    "stopped": "🔴 متوقف",
    "stopped_gracefully": "🔴 متوقف",
    "error": "⚠️ خطأ",
    "failed": "⚠️ خطأ",
    "pending": "🟡 قيد التشغيل",
    "starting": "🟡 قيد التشغيل",
    "building": "🟡 قيد البناء",
    "deploying": "🟡 قيد النشر",
}


def _status_ar(raw: str) -> str:
    """Translate internal host status to user-facing Arabic + emoji."""
    s = (raw or "").strip().lower()
    return _STATUS_AR.get(s, f"⚪ {raw}" if raw else "⚪ غير معروف")


def _mask_path(path: str) -> str:
    """Show only the last folder name — never expose server filesystem layout."""
    p = (path or "").strip().rstrip("/")
    if "/" in p:
        p = p.rsplit("/", 1)[-1]
    return p or "—"


# ---------------------------------------------------------------------------
# Phase renderers
# ---------------------------------------------------------------------------

def _render_home(facts: UiFacts) -> str:
    """Homepage — welcoming, explains what Lumen does, clear actions."""
    bal = int(facts.credits_available or facts.credits_balance or 0)
    lines = [
        "🤖 أهلاً بك في Lumen",
        "",
        "منصّة ذكاء اصطناعي تصنع لك بوتات تيليجرام احترافية",
        "اكتب وصف ما تريد، وسيقوم المحرك ببرمجته لك بالكامل.",
        "",
        "💡 أمثلة:",
        "• بوت متجر لعرض المنتجات واستقبال الطلبات",
        "• بوت تذكيرات يومية للمهام والمواعيد",
        "• بوت أسئلة شائعة للرد على عملائك تلقائياً",
        "• بوت إدارة مهام مع قائمة TODO وتنبيهات",
        "",
        f"💎 رصيدك الحالي: {bal} كريديت",
        "",
        "اختر من القائمة أدناه 👇",
    ]
    return "\n".join(lines)


def _render_gen_type() -> str:
    """Generation start — clear instructions with examples."""
    return (
        "✍️ صِف البوت الذي تريده\n"
        "\n"
        "اكتب وصفاً واضحاً لما تريد أن يفعله البوت.\n"
        "كلما كان الوصف أدق، كانت النتيجة أفضل.\n"
        "\n"
        "💡 أمثلة جيدة:\n"
        "• بوت متجر إلكترونيات يعرض المنتجات ويسمح بالطلب والدفع عند الاستلام\n"
        "• بوت يرسل تذكير يومي الساعة 8 صباحاً بقائمة مهامي\n"
        "• بوت أسئلة شائعة يرد على عملاء متجري بكلمات مفتاحية محددة\n"
        "\n"
        "اكتب وصفك في الشات 👇"
    )


def _render_gen_slots(state: EngineUiState) -> str:
    """Slot collection — clear question + progress indicator."""
    from .engine_needs import remaining_needs
    rem = remaining_needs(state.needs or [], state.slots)
    total = len(state.needs or []) if state.needs else len(rem)
    answered = max(0, total - len(rem))

    lines = ["📝 نحتاج بعض التفاصيل لإكمال البوت"]
    lines.append("")

    if rem:
        if total > 0:
            lines.append(f"السؤال {answered + 1} من {total}:")
        else:
            lines.append("السؤال:")
        lines.append("")
        lines.append(f"❓ {rem[0].text}")
        lines.append("")
        if rem[0].choices:
            lines.append("اختر من الأزرار أدناه أو اكتب إجابتك في الشات 👇")
        else:
            lines.append("اكتب إجابتك في الشات 👇")
    else:
        lines.append("✅ اكتملت جميع التفاصيل!")
        lines.append("تابع للتأكيد وبدء التوليد 👇")

    # Show what's already filled (user-facing labels, not slot keys)
    filled = _filled_slots_human(state)
    if filled:
        lines.append("")
        lines.append("✓ ما تم إدخاله:")
        lines.append(filled)

    return "\n".join(lines)


# Human-readable labels for filled slots (never expose internal key names)
_SLOT_LABEL_AR: dict[str, str] = {
    "payment": "طريقة الدفع",
    "product_or_category": "نوع المنتجات",
    "audience": "الجمهور المستهدف",
    "storage": "التخزين",
    "language": "اللغة",
    "bot_name": "اسم البوت",
    "commands": "الأوامر",
    "bot_type": "نوع البوت",
    "bot_description": "الوصف",
}

_VALUE_LABEL_AR: dict[str, str] = {
    "vodafone_cash": "فودافون كاش",
    "wallet": "محفظة",
    "telegram_only": "تيليجرام فقط",
    "none": "بدون دفع",
    "clothes": "ملابس",
    "electronics": "إلكترونيات",
    "food": "أكل",
    "beginners": "مبتدئين",
    "pros": "محترفين",
    "everyone": "الجميع",
    "sqlite": "قاعدة بيانات SQLite",
    "memory": "الذاكرة فقط",
    "ar": "العربية",
    "en": "English",
    "other": "مخصّص",
    "custom": "مخصّص",
}

_EXCLUDE_SLOTS = {
    "awaiting_text",
    "awaiting_slot",
    "confirmed",
    "needs_json",
    "intent_kind",
    "ui_event",
    "ui_event_detail",
    "dash_count",
}


def _filled_slots_human(state: EngineUiState) -> str:
    """Format filled slots as human-readable lines."""
    out: list[str] = []
    for k, v in (state.slots or {}).items():
        if k in _EXCLUDE_SLOTS or k.startswith("dash_"):
            continue
        if not v:
            continue
        label = _SLOT_LABEL_AR.get(k, k.replace("_", " "))
        val_label = _VALUE_LABEL_AR.get(v, v)
        out.append(f"• {label}: {val_label}")
    return "\n".join(out[:8])


def _render_gen_confirm(state: EngineUiState) -> str:
    """Confirmation — visual summary before generation starts."""
    desc = (state.slots.get("bot_description") or "").strip()
    lines = ["✅ تأكيد التوليد"]
    lines.append("")
    lines.append("📋 ملخص طلبك:")
    lines.append("")

    # Description
    if desc:
        lines.append(f"📝 الوصف: {desc[:300]}")
        lines.append("")

    # Filled slots
    filled = _filled_slots_human(state)
    if filled:
        lines.append(filled)
        lines.append("")

    lines.append("هل تريد بدء توليد البوت الآن؟")
    lines.append("اضغط \"نعم، ابدأ التوليد\" للمتابعة 👇")
    return "\n".join(lines)


def _render_generating() -> str:
    """Generation in progress — stages + time estimate + reassurance."""
    return (
        "⚙️ جاري صناعة البوت...\n"
        "\n"
        "🧠 المحرك يقوم بـ:\n"
        "• تحليل طلبك وتخطيط البنية\n"
        "• كتابة الكود (Python + aiogram)\n"
        "• إضافة الأوامر والمعالجات\n"
        "• اختبار الكود للتأكد من عمله\n"
        "\n"
        "⏱️ قد يستغرق هذا 1-3 دقائق\n"
        "ستظهر كل خطوة هنا لحظة بلحظة 👇"
    )


def _render_gen_done(state: EngineUiState) -> str:
    """Generation complete — celebration + clear next steps."""
    lines = [
        "🎉 تم صنع البوت بنجاح!",
        "",
        "✅ البوت جاهز الآن.",
    ]

    project = _mask_path(state.project_ref)
    if project and project != "—":
        lines.append(f"📦 المشروع: {project}")

    lines.append("")
    lines.append("ماذا تريد أن تفعل الآن؟")
    lines.append("")
    lines.append("🚀 جرّب البوت في الشات")
    lines.append("☁️ استضفه دائماً (يعمل 24/7)")
    lines.append("📥 حمّل الكود (ملف ZIP)")
    lines.append("👁️ معاينة الملفات")
    lines.append("")
    lines.append("اختر من الأزرار أدناه 👇")
    return "\n".join(lines)


def _render_dashboard(state: EngineUiState, facts: UiFacts) -> str:
    """Dashboard — user's bots with status, in plain Arabic."""
    lines = ["📊 لوحة التحكم"]
    lines.append("")
    lines.append("إدارة بوتاتك المستضافة:")
    lines.append("")

    # Show session project if available
    if facts.active_project:
        lines.append(f"📦 مشروعك الحالي: {_mask_path(facts.active_project)}")
        lines.append("")

    # Collect hosts from slot-sync (preferred) or facts
    hosts: list[tuple[str, str, str, str]] = []  # (id_suffix, status, username, backend)
    for i in range(5):
        iid = (state.slots or {}).get(f"dash_h{i}") or ""
        if not iid:
            continue
        st = (state.slots or {}).get(f"dash_s{i}") or "?"
        un = (state.slots or {}).get(f"dash_u{i}") or ""
        be = (state.slots or {}).get(f"dash_b{i}") or ""
        hosts.append((iid[-12:], st, un, be))

    if not hosts and facts.hosts:
        for h in facts.hosts[:5]:
            un = h.bot_username or ""
            hosts.append((h.instance_id[-12:], h.status, un, h.backend))

    if hosts:
        lines.append("🤖 بوتاتك:")
        lines.append("")
        for idx, (iid, st, un, be) in enumerate(hosts, 1):
            status_label = _status_ar(st)
            un_display = f"@{un}" if un else "بدون اسم"
            lines.append(f"  #{idx} {un_display} — {status_label}")
    else:
        lines.append("📭 لا توجد بوتات مستضافة حالياً")
        lines.append("")
        lines.append("بعد توليد بوت، يمكنك استضافته هنا ليعمل 24/7")

    lines.append("")
    lines.append("اختر من الأزرار أدناه 👇")
    return "\n".join(lines)


def _render_billing(facts: UiFacts) -> str:
    """Billing — balance + cost + how it works (no fake payment UI)."""
    bal = int(facts.credits_available or facts.credits_balance or 0)
    reserved = int(facts.credits_reserved or 0)
    gen_cost = int(facts.gen_cost_credits or 50)
    host_cost = int(facts.host_hourly_credits or 10)

    lines = ["💎 الرصيد والاشتراك"]
    lines.append("")
    lines.append(f"رصيدك المتاح: {bal} كريديت")
    if reserved > 0:
        lines.append(f"محجوز مؤقتاً: {reserved} كريديت")
    lines.append("")
    lines.append("📊 كيف تُستهلك الكريديتات:")
    lines.append(f"• توليد بوت جديد: {gen_cost} كريديت")
    lines.append(f"• استضافة بوت (كل ساعة): {host_cost} كريديت")
    lines.append("")
    lines.append("🔄 يتم منحك كريديتات ترحيبية عند البداية")
    lines.append("للمزيد من الكريديتات تواصل مع الدعم")
    lines.append("")
    lines.append("اختر من الأزرار أدناه 👇")
    return "\n".join(lines)


def _render_help() -> str:
    """Help — comprehensive, organized guide."""
    return (
        "❓ المساعدة\n"
        "\n"
        "🤖 ما هو Lumen؟\n"
        "منصة تصنع لك بوتات تيليجرام بالكامل — فقط اكتب ما تريد\n"
        "والذكاء الاصطناعي يبرمج البوت لك.\n"
        "\n"
        "✅ ما يمكننا صناعته:\n"
        "• متجر إلكتروني (منتجات، سلة، طلبات)\n"
        "• بوت تذكيرات وإشعارات\n"
        "• بوت إدارة مهام (TODO)\n"
        "• بوت محادثة وردود جاهزة\n"
        "• بوت اشتراكات ونشر رسائل\n"
        "• أي بوت تيليجرام بـ Python وأوامر ومعالجات حقيقية\n"
        "\n"
        "🚀 كيف أبدأ؟\n"
        "1. اضغط \"إنشاء بوت\"\n"
        "2. اكتب وصفاً لما تريد\n"
        "3. أجب على الأسئلة (إن وُجدت)\n"
        "4. أكّد وانتظر صناعة البوت\n"
        "5. جرّب البوت أو استضفه أو حمّله\n"
        "\n"
        "💡 نصائح لوصف أفضل:\n"
        "• كن محدداً: \"بوت متجر ملابس\" أفضل من \"بوت متجر\"\n"
        "• اذكر الأوامر: \"أوامر: /start /catalog /order\"\n"
        "• اذكر طريقة الدفع: \"دفع عند الاستلام\"\n"
        "\n"
        "📤 ماذا بعد التوليد؟\n"
        "• تجربة في الشات — تتفاعل مع البوت فوراً\n"
        "• استضافة دائمة — يعمل 24/7\n"
        "• تحميل ZIP — تحصل على الكود كاملاً\n"
        "\n"
        "اكتب /start للعودة للقائمة الرئيسية"
    )


def _render_context(state: EngineUiState) -> str:
    """Contextual events — clear error messages with solutions."""
    from .ui_events import render_event_message
    return render_event_message(state)


# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------

def render_message(state: EngineUiState, facts: UiFacts | None = None) -> str:
    facts = facts or UiFacts()
    phase = state.phase

    if phase in {EngineUiPhase.HOME, EngineUiPhase.IDLE}:
        return _render_home(facts)

    if phase == EngineUiPhase.GEN_TYPE:
        return _render_gen_type()

    if phase == EngineUiPhase.GEN_SLOTS:
        return _render_gen_slots(state)

    if phase == EngineUiPhase.GEN_CONFIRM:
        return _render_gen_confirm(state)

    if phase == EngineUiPhase.GENERATING:
        return _render_generating()

    if phase == EngineUiPhase.GEN_DONE:
        return _render_gen_done(state)

    if phase == EngineUiPhase.DASHBOARD:
        return _render_dashboard(state, facts)

    if phase == EngineUiPhase.BILLING:
        return _render_billing(facts)

    if phase == EngineUiPhase.CONTEXT:
        return _render_context(state)

    if phase == EngineUiPhase.HELP:
        return _render_help()

    # Fallback — should never reach here in production
    return "📖 اختر من القائمة أدناه 👇"
