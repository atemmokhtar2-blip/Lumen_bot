"""Honest capability list for /help and rejection messages."""
from __future__ import annotations

CAN_DO_AR = [
    "توليد بوت تيليجرام بأوامر ومعالجات حقيقية (Python)",
    "متجر / سلة / نقاط / محفظة / اشتراكات / تذاكر (منطق محلي + SQLite)",
    "تشغيل تجريبي بالتوكن داخل عزل (Docker إن وُجد، وإلا عملية محلية معزولة)",
    "سحب وفهم مستودعات عامة (وخاصة بتوكن GitHub)",
    "التحقق ضد الهلوسة قبل تسليم المشروع",
]

CANNOT_DO_AR = [
    "ذكاء اصطناعي يتعلم من المحادثات أو نماذج ML",
    "بوابات دفع خارجية حقيقية (Stripe/PayPal) بدون مفاتيحك",
    "إدارة سيرفرات Linux أو اختراق أو تعدين",
    "بوتات بلغات غير Python",
    "فيديو حي / VoIP / بلوكتشين من الصفر",
]


def get_help_text() -> str:
    can = "\n".join(f"• {x}" for x in CAN_DO_AR)
    cannot = "\n".join(f"• {x}" for x in CANNOT_DO_AR)
    return (
        "🤖 *ماذا أستطيع؟*\n"
        f"{can}\n\n"
        "🚫 *ماذا لا أستطيع؟*\n"
        f"{cannot}\n\n"
        "أرسل وصفاً واضحاً للبوت، أو /start"
    )


def rejection_message(reason: str, suggested: str = "") -> str:
    parts = [
        "⚠️ لا أستطيع توليد هذا البوت كما هو مطلوب.",
        "",
        f"السبب: {reason}",
    ]
    if suggested:
        parts += ["", f"💡 بديل مقترح:\n{suggested}"]
    parts += [
        "",
        "أقدر أساعدك في بوتات أوامر تيليجرام، متجر محلي، نقاط، تذاكر، اشتراكات.",
        "اكتب /help لعرض الحدود بوضوح.",
    ]
    return "\n".join(parts)


__all__ = ["get_help_text", "rejection_message", "CAN_DO_AR", "CANNOT_DO_AR"]
