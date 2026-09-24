"""Honest capability list for /help and rejection messages — Telegram HTML UI."""
from __future__ import annotations

from lumen.bot.telegram_text import html_bullets, html_card
from lumen.bot.html_emoji import he


CAN_DO_AR = [
    "بناء مشاريع بايثون من وصف: بوت تيليجرام، موقع، واجهة API، برنامج عام، أو مكتبة.",
    "اكتشاف نوع المشروع تلقائياً من الوصف.",
    "استضافة بوتات تيليجرام (تجربة في الشات أو دائمة) واستضافة HTTP للمواقع/APIs مع رابط عام عند ضبط الدومين.",
    "لوحة تحكم لمشاريع مختلطة (بوت + موقع) مع الحالة والرابط.",
    "تسليم الملفات (ZIP / معاينة) لكل الأنواع.",
    "استيراد وتحليل مستودعات عامة (أو خاصة بتوكن).",
    "فحص جودة ضد الأخطاء المنطقية قبل التسليم.",
]

CANNOT_DO_AR = [
    "أوامر نظام خام أو shell على السيرفر من وصف المستخدم.",

    "دومين العميل المخصص (CNAME) — مرحلة لاحقة.",
    "لغات غير مفعّلة: الافتراضي بايثون فقط — التوسيع عبر LUMEN_ENABLED_LANGUAGES بعد قوالب اللغة.",
    "بوابات دفع خارجية (ستُضاف لاحقاً).",
    "إدارة السيرفرات أو تنفيذ أوامر نظام خطيرة.",
    "التعلم العميق من المحادثات (ML/NLP متقدم).",
]


def get_help_text() -> str:
    """Full /help body — official expandable blue cards."""
    return html_card(
        "📖 دليل Lumen الشامل",
        [
            ("✨ ما يمكنني فعله لك", html_bullets(CAN_DO_AR)),
            ("⚠️ ما ليس جاهزاً بعد", html_bullets(CANNOT_DO_AR)),
        ],
        subtitle="منصة بناء وتشغيل تطبيقات — التيليجرام لوحة التحكم",
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
                    "بوت تيليجرام (تشغيل حي + استضافة)",
                    "API / موقع / برنامج بايثون (توليد + ZIP)",
                ]
            ),
        )
    )
    return html_card(
        "تعذّر تنفيذ هذا الطلب",
        sections,
        subtitle="خارج حدود المحرك الحالية",
        footer="اكتب /help لعرض الحدود بوضوح.",
    )


__all__ = ["get_help_text", "rejection_message", "CAN_DO_AR", "CANNOT_DO_AR"]
