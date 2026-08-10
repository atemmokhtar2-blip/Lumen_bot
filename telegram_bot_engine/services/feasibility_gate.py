"""Pre-generation feasibility assessment — honest capability boundaries."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class ComplexityLevel(Enum):
    TRIVIAL = "trivial"
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    IMPOSSIBLE = "impossible"


@dataclass
class FeasibilityResult:
    can_generate: bool
    confidence: float
    level: ComplexityLevel
    reason: str
    suggested_scope: str = ""
    partial_features: list[str] = field(default_factory=list)
    blocked_features: list[str] = field(default_factory=list)


# Patterns that require external services / heavy domain logic we cannot invent
_IMPOSSIBLE = [
    (r"يتعلم|machine\s*learning|neural|gpt|llm|ذكاء\s*اصطناعي\s*حقيقي|NLU\s*training", "تدريب نماذج ذكاء اصطناعي"),
    (r"blockchain|bitcoin\s*min|تعدين|consensus|from\s*scratch.*chain", "بلوكتشين أو تعدين"),
    (r"يكسر\s*captcha|hacks?\s+other|اختراق|malware|ransomware|worm", "وظائف ضارة أو غير قانونية"),
    (r"clone\s*telegram|زي\s*تليجرام\s*نفسه|voip|مكالمات\s*صوتية\s*حقيقية|real-?time\s*video", "بروتوكولات/فيديو/VoIP خارج النطاق"),
    (r"self[- ]?replicat|دودة|ينشر\s*نفسه", "سلوك تكراري خبيث"),
    (r"linux\s*server|ssh\s*root|يدير\s*سيرفر", "إدارة أنظمة تشغيل كاملة"),
    (r"predict.*99%|يتوقع\s*أسعار.*دقة", "تنبؤ مالي دقيق"),
    (r"(rust|c\+\+|java|golang|go\s*lang).{0,40}bot|bot.{0,40}(rust|c\+\+|java|golang)|بوت.*(rust|c\+\+|java)", "لغات غير Python"),
    (r"hipaa|soc\s*2|full\s*gdpr\s*compliance", "امتثال قانوني كامل كمنتج"),
    (r"jira-?like|full\s*crm\s*enterprise|ats\s*system|neobank", "أنظمة مؤسسية كاملة خارج النطاق"),
]

_COMPLEX_NEEDS = [
    (r"stripe|paypal|payment\s*gateway|بوابة\s*دفع\s*خارجية", "دفع خارجي يحتاج مفاتيح API"),
    (r"google\s*translate|openweather|unsplash|binance|api\s*key", "تكامل API خارجي يحتاج مفاتيح"),
    (r"hipaa|gdpr\s*compliant|soc2", "امتثال قانوني كامل"),
    (r"real[- ]?time\s*video|gpu|computer\s*vision", "معالجة فيديو/GPU"),
]

_SUPPORTED_HINTS = [
    r"start|help|echo|رد|ترحيب|أوامر|command",
    r"متجر|سلة|cart|shop|منتجات|catalog",
    r"نقاط|ولاء|points|loyalty",
    r"تذكرة|ticket|دعم|support",
    r"اشتراك|subscription|خطة|plan",
    r"إحالة|referral|دعوة",
    r"محفظة|wallet|رصيد",
    r"مسابقة|contest|سحب",
    r"ملاحظة|notes|مهام|tasks|todo",
]


def check_feasibility(request: str) -> FeasibilityResult:
    text = (request or "").strip()
    try:
        from ..spec_core.arabic_intent_engine import is_clearly_non_bot
        if is_clearly_non_bot(text):
            return FeasibilityResult(
                can_generate=False,
                confidence=0.98,
                level=ComplexityLevel.IMPOSSIBLE,
                reason="هذا ليس طلب بوت (قصة/مقال/ترجمة...). أرسل وصف بوت تيليجرام.",
                suggested_scope="مثال: بوت متجر فيه /start و /cart",
            )
    except Exception:
        pass
    if len(text) < 3:
        return FeasibilityResult(
            can_generate=False,
            confidence=1.0,
            level=ComplexityLevel.TRIVIAL,
            reason="الوصف قصير جداً — اكتب ما يفعله البوت بوضوح.",
            suggested_scope="مثال: بوت فيه /start و /help ويرد على الرسائل",
        )

    low = text.lower()
    blocked: list[str] = []
    for pat, label in _IMPOSSIBLE:
        if re.search(pat, low, re.I):
            blocked.append(label)

    if blocked:
        return FeasibilityResult(
            can_generate=False,
            confidence=0.95,
            level=ComplexityLevel.IMPOSSIBLE,
            reason="الطلب خارج قدرات المحرك الحتمي: " + "؛ ".join(blocked),
            suggested_scope="اطلب بوت أوامر/متجر/تذاكر/نقاط داخل تيليجرام بدون APIs خارجية أو ML.",
            blocked_features=blocked,
        )

    complex_hits: list[str] = []
    for pat, label in _COMPLEX_NEEDS:
        if re.search(pat, low, re.I):
            complex_hits.append(label)

    supported = any(re.search(p, low, re.I) for p in _SUPPORTED_HINTS)
    slash_cmds = len(re.findall(r"/[a-zA-Z][a-zA-Z0-9_]{1,32}", text))

    if complex_hits and not supported:
        return FeasibilityResult(
            can_generate=False,
            confidence=0.8,
            level=ComplexityLevel.COMPLEX,
            reason="يحتاج تكاملات خارجية غير متوفرة بدون مفاتيح: " + "؛ ".join(complex_hits),
            suggested_scope="يمكنك توليد هيكل أوامر تيليجرام؛ اربط الـ API لاحقاً يدوياً.",
            blocked_features=complex_hits,
        )

    if complex_hits and supported:
        return FeasibilityResult(
            can_generate=True,
            confidence=0.65,
            level=ComplexityLevel.MODERATE,
            reason="سأولّد الأوامر والهيكل داخل تيليجرام؛ الأجزاء التي تحتاج API خارجي ستظهر كمسارات جاهزة للربط.",
            partial_features=["telegram_commands", "local_state"],
            blocked_features=complex_hits,
            suggested_scope="هيكل أوامر + تخزين محلي؛ بدون اتصال فعلي لـ " + "، ".join(complex_hits[:3]),
        )

    if supported or slash_cmds >= 1 or re.search(r"بوت|bot", low):
        level = ComplexityLevel.SIMPLE if slash_cmds <= 5 else ComplexityLevel.MODERATE
        return FeasibilityResult(
            can_generate=True,
            confidence=0.85,
            level=level,
            reason="الطلب ضمن قدرات التوليد الحتمي (أوامر تيليجرام + منطق محلي).",
            partial_features=["commands", "callbacks", "sqlite_side_effects"],
        )

    return FeasibilityResult(
        can_generate=True,
        confidence=0.55,
        level=ComplexityLevel.SIMPLE,
        reason="سأحاول توليد بوت أوامر أساسي من الوصف.",
        suggested_scope="يفضّل ذكر أوامر مثل /start /help وما يفعله كل أمر.",
    )


__all__ = ["check_feasibility", "FeasibilityResult", "ComplexityLevel"]
