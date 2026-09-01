"""Honest capability list for /help and rejection messages — Telegram HTML UI."""
from __future__ import annotations

from lumen.bot.telegram_text import html_bullets, html_card

CAN_DO_AR = [
    "بناء فوري: وصف بسيط = بوت جاهز للتشغيل (مع منطق SQLite، سلة، نقاط، اشتراكات).",
    "استضافة Docker: بوتك يعمل في بيئة معزولة وآمنة.",
    "استيراد ذكي: استنساخ مشاريع عامة (أو خاصة بتوكن) وتحليلها.",
    "فحص الجودة: تحليل ضد الأخطاء المنطقية («الهلوسة») قبل التسليم.",
]

CANNOT_DO_AR = [
    "التعلم العميق من المحادثات (ML/NLP متقدم).",
    "بوابات دفع خارجية (ستُضاف قريباً).",
    "إدارة السيرفرات أو تنفيذ أوامر نظام خطيرة.",
    "بناء بوتات بلغات أخرى غير Python في هذه النسخة.",
]


def get_help_text() -> str:
    """Full /help body — official expandable blue cards."""
    return html_card(
        "📖 دليل Lumen الشامل",
        [
            ("✨ ما يمكنني فعله لك", html_bullets(CAN_DO_AR)),
            ("⚠️ ما ليس ضمن اختصاصي حالياً", html_bullets(CANNOT_DO_AR)),
        ],
        subtitle="الدعم والإرشاد",
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
