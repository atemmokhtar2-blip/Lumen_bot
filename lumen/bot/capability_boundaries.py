"""Honest capability list for /help and rejection messages — Telegram HTML UI."""
from __future__ import annotations

from lumen.bot.telegram_text import html_bullets, html_card

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
    """Full /help body — official expandable blue cards."""
    return html_card(
        "المساعدة — قدرات Lumen",
        [
            ("ماذا أستطيع؟", html_bullets(CAN_DO_AR)),
            ("ماذا لا أستطيع؟", html_bullets(CANNOT_DO_AR)),
            (
                "كيف تبدأ",
                "أرسل وصفاً واضحاً للبوت من زر إنشاء بوت،\n"
                "أو اضغط /start للعودة للقائمة الرئيسية.",
            ),
        ],
        subtitle="حدود صادقة — بدون وعود وهمية",
    )


def rejection_message(reason: str, suggested: str = "") -> str:
    """Capability rejection — HTML card, never markdown asterisks."""
    sections: list[tuple[str, str]] = [
        ("السبب", (reason or "غير محدد").strip() or "غير محدد"),
    ]
    if (suggested or "").strip():
        sections.append(("بديل مقترح", suggested.strip()))
    sections.append(
        (
            "أقدر أساعدك في",
            html_bullets(
                [
                    "بوتات أوامر تيليجرام",
                    "متجر محلي / نقاط / تذاكر / اشتراكات",
                ]
            ),
        )
    )
    return html_card(
        "تعذّر توليد هذا البوت",
        sections,
        subtitle="الطلب خارج حدود المحرك الحالية",
        footer="اكتب /help لعرض الحدود بوضوح.",
    )


__all__ = ["get_help_text", "rejection_message", "CAN_DO_AR", "CANNOT_DO_AR"]
