"""Deterministic smart guided dialogue — always on, zero extra dependencies.

This is the Phase 0 backbone: works in production without Rasa installed.
RasaEngine sits on top when a trained model is present.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .contract import DialogueEngine, DialogueRequest, DialogueResponse
from .normalize import normalize, tokens


@dataclass(frozen=True)
class _PatternIntent:
    intent: str
    weight: float
    any_phrases: tuple[str, ...] = ()
    any_regex: tuple[str, ...] = ()
    all_words: tuple[str, ...] = ()  # all must appear
    boost_words: tuple[str, ...] = ()
    block_words: tuple[str, ...] = ()


# Ordered knowledge — higher weight wins ties with phrase length
_INTENTS: tuple[_PatternIntent, ...] = (
    _PatternIntent(
        "greet",
        1.0,
        any_phrases=(
            "مرحبا", "مرحبا", "اهلا", "السلام عليكم", "سلام عليكم", "صباح الخير",
            "مساء الخير", "hello", "hi ", "hey", "good morning", "good evening",
            "ازيك", "عامل ايه", "هاي",
        ),
        any_regex=(r"^\s*hi\s*$", r"^\s*hello\s*$", r"^\s*hey\s*$"),
    ),
    _PatternIntent(
        "goodbye",
        1.0,
        any_phrases=("باي", "مع السلامه", "الي اللقاء", "اشوفك", "bye", "goodbye", "see you"),
    ),
    _PatternIntent(
        "ask_plan",
        1.2,
        any_phrases=(
            "خطتي", "خطه", "خطة", "my plan", "/plan", "اشتراكي", "الخطة الحالية",
            "اني خطة", "أنهي خطة",
        ),
        any_regex=(r"/plan\b", r"/خطة"),
    ),
    _PatternIntent(
        "ask_pricing",
        1.15,
        any_phrases=(
            "الاسعار", "الأسعار", "بكام", "pricing", "price", "اشتراك", "ترقية",
            "ارقي", "upgrade", "starter", "growth", "كام الخطه", "فرق الخطط",
        ),
        boost_words=("دولار", "شهر", "شهري", "مجاني", "مدفوع"),
    ),

    _PatternIntent(
        "how_platform_works",
        1.35,
        any_phrases=(
            "ازاي البوت بيشتغل", "ازاي المنصه بتشتغل", "ازاي maestro بيشتغل",
            "كيف يعمل البوت", "كيف تشتغل المنصة", "how does it work", "how the bot works",
            "ايه فكرة النظام", "اشرح النظام", "اشرح المنصة", "نظام الشغل",
            "ازاي بتشتغلوا", "ما هو maestro", "ما هي المنصة",
        ),
        boost_words=("يشتغل", "شغال", "آلية", "workflow"),
    ),
    _PatternIntent(
        "how_to_upgrade",
        1.4,
        any_phrases=(
            "ازاي ارقي", "ازاي أرقى", "ازاي ارقى للبرو", "ترقية للبرو", "ترقيه للبرو",
            "ارقي للخطة", "أرقى للخطة", "upgrade to pro", "upgrade to growth",
            "ازاي اشترك", "عايز أرقى", "عايز ارقي", "حولني لبرو", "ترقية الخطة",
            "ازاي افعل pro", "ازاي افعل starter", "الترقية",
        ),
        boost_words=("ترقية", "upgrade", "برو", "pro", "growth", "starter"),
    ),
    _PatternIntent(
        "ask_about_hosting",
        1.25,
        any_phrases=(
            "الاستضافة", "استضافة 24", "هوستينج", "hosting", "شغال 24",
            "بوت دائم", "استضف البوت", "ازاي استضافة",
        ),
    ),
    _PatternIntent(
        "ask_about_preview",
        1.2,
        any_phrases=(
            "معاينة حية", "لايف بريفيو", "live preview", "تجربة التشغيل",
            "كام دقيقة المعاينة", "مدة التجربة",
        ),
    ),
    _PatternIntent(
        "ask_about_watermark",
        1.15,
        any_phrases=(
            "علامة مائية", "watermark", "powered by maestro", "العلامة المائيه",
        ),
    ),
    _PatternIntent(
        "ask_about_free",
        1.2,
        any_phrases=("خطة free", "الخطة المجانية", "خطة مجانية", "free plan", "الاشتراك المجاني"),
    ),
    _PatternIntent(
        "ask_about_starter",
        1.2,
        any_phrases=("خطة starter", "المبادر", "starter plan", "خطة 8 دولار", "خطة ٨"),
    ),
    _PatternIntent(
        "ask_about_growth",
        1.25,
        any_phrases=(
            "خطة growth", "خطة pro", "النمو", "الخطه البرو", "الخطة البرو",
            "growth plan", "pro plan", "خطة 30 دولار",
        ),
    ),
    _PatternIntent(
        "ask_how_to_generate",
        1.2,
        any_phrases=(
            "ازاي اولد", "ازاي انشئ", "ازاي اعمل بوت", "كيف اولد", "كيف انشئ",
            "how to generate", "how to create a bot", "خطوات التوليد", "اكتب الوصف",
            "ازاي اوصف", "علمني اولد", "ابدأ منين", "ابدأ منين",
        ),
        all_words=(),
        boost_words=("توليد", "generate", "وصف"),
    ),
    _PatternIntent(
        "ask_capabilities",
        1.1,
        any_phrases=(
            "تقدر تعمل ايه", "ايه قدراتك", "what can you do", "مميزاتك",
            "اقدر اعمل بيك", "خدماتك", "قدرتك ايه",
        ),
    ),
    _PatternIntent(
        "ask_help",
        1.05,
        any_phrases=(
            "مساعده", "مساعدة", "ساعدني", "help", "مش عارف ابدأ", "ازاي استخدم",
            "كيف استخدم", "وضح لي", "اشرح لي",
        ),
        any_regex=(r"/help\b",),
    ),
    _PatternIntent(
        "ask_support",
        1.1,
        any_phrases=(
            "دعم فني", "support", "ايميل الدعم", "تواصل", "contact support",
            "مشكلة عندي", "عطل",
        ),
    ),
    _PatternIntent(
        "ask_limitations",
        1.1,
        any_phrases=(
            "مش بتقدر", "القيود", "limitations", "فيه حدود", "الممنوع", "صراحه",
        ),
    ),
    _PatternIntent(
        "bot_challenge",
        1.0,
        any_phrases=(
            "انت بوت", "أنت بوت", "are you a bot", "are you human", "مين انت",
            "عرفني بنفسك", "who are you",
        ),
    ),
    _PatternIntent(
        "describe_bot_idea",
        1.25,
        any_phrases=(
            "عايز بوت", "عايز اعمل بوت", "اولد بوت", "اعمل لي بوت", "بوت فيه",
            "create a bot", "i want a bot", "generate a bot", "بوت متجر",
            "بوت دعم", "بوت تذاكر", "بوت حجوزات", "بوت جروب", "بوت قناة",
        ),
        boost_words=("اوردر", "منتجات", "ادمن", "ازرار", "اوامر", "faq", "دفع"),
        block_words=(),
    ),
    _PatternIntent(
        "affirm",
        0.9,
        any_phrases=("نعم", "ايوه", "أيوه", "موافق", "يلا", "ok", "okay", "yes", "اكيد"),
        any_regex=(r"^\s*yes\s*$", r"^\s*ok\s*$"),
    ),
    _PatternIntent(
        "deny",
        0.9,
        any_phrases=("لا", "لأ", "مش عايز", "no", "nope", "الغاء", "إلغاء", "بلاش"),
        any_regex=(r"^\s*no\s*$",),
    ),
    _PatternIntent(
        "out_of_scope",
        0.8,
        any_phrases=(
            "وصفة", "الطقس", "سعر الدولار", "مباراة", "واجب رياضيات", "كود جافا",
        ),
    ),
)


def _phrase_hit(text_n: str, toks: set[str], phrase: str) -> bool:
    pn = normalize(phrase)
    if not pn:
        return False
    # Short tokens (≤3 chars): require full token match — avoids "لا" inside "علامة"
    if " " not in pn and len(pn) <= 3:
        return pn in toks
    if pn in text_n:
        return True
    # token-sequence soft match
    pt = pn.split()
    if len(pt) >= 2 and all(any(p in t or t in p for t in toks) for p in pt):
        return True
    return False


def _score(text_n: str, toks: set[str], spec: _PatternIntent) -> float:
    score = 0.0
    for ph in spec.any_phrases:
        pn = normalize(ph)
        if _phrase_hit(text_n, toks, ph):
            score += spec.weight * (1.0 + min(len(pn), 24) / 48.0)
    for rx in spec.any_regex:
        if re.search(rx, text_n, re.I):
            score += spec.weight * 1.2
    if spec.all_words:
        if all(normalize(w) in toks or normalize(w) in text_n for w in spec.all_words):
            score += spec.weight
        else:
            return 0.0
    for w in spec.boost_words:
        if normalize(w) in toks or normalize(w) in text_n:
            score += 0.15
    for w in spec.block_words:
        if normalize(w) in toks:
            score -= 0.5
    return score


def classify(text: str) -> tuple[str, float]:
    n = normalize(text)
    toks = set(tokens(text))
    best_intent = "nlu_fallback"
    best_score = 0.0
    for spec in _INTENTS:
        s = _score(n, toks, spec)
        if s > best_score:
            best_score = s
            best_intent = spec.intent
    # Disambiguation: how-to questions vs concrete generation requests
    how_markers = ("ازاي", "ازى", "كيف", "how to", "علمني", "خطوات", "طريقة")
    if any(m in n for m in how_markers) and any(k in n for k in ("اولد", "انشئ", "generate", "بوت", "وصف")):
        if best_intent == "describe_bot_idea":
            best_intent = "ask_how_to_generate"
            best_score = max(best_score, 1.4)
    # Plan detail questions should not collapse to generic ask_plan
    if best_intent == "ask_plan":
        if any(x in n for x in ("مجان", "free")) and any(x in n for x in ("فيه", "تفاصيل", "مميز", "حدود", "ايه")):
            best_intent, best_score = "ask_about_free", max(best_score, 1.5)
        elif any(x in n for x in ("starter", "مبادر", "8")):
            best_intent, best_score = "ask_about_starter", max(best_score, 1.5)
        elif any(x in n for x in ("growth", "pro", "نمو", "30", "برو")):
            best_intent, best_score = "ask_about_growth", max(best_score, 1.5)
    conf = min(0.99, best_score / 2.5) if best_score > 0 else 0.0
    if best_score < 0.55:
        return "nlu_fallback", conf
    return best_intent, conf


_PLAN_LABELS = {
    "free": "Free — مجاني",
    "starter": "المبادر (Starter) — $8/شهر",
    "growth": "النمو (Growth) — $30/شهر",
}


def _plan_body(plan_id: str) -> str:
    plan_id = (plan_id or "free").lower()
    try:
        from b2b_platform.plans import get_plan, public_plan_dict

        pd = public_plan_dict(get_plan(plan_id))
        return (
            f"👤 خطتك الحالية: {_PLAN_LABELS.get(plan_id, plan_id)}\n"
            f"• التوليد: {pd['generations_per_month']}/شهر\n"
            f"• الاستضافة 24/7: {pd['hosted_bots']} بوت\n"
            f"• معاينة حية: {pd['live_preview_minutes']} دقيقة\n"
            f"• المحرك: {pd['engine_tier']}"
        )
    except Exception:
        return f"👤 خطتك الحالية: {_PLAN_LABELS.get(plan_id, plan_id)}"


def _reply(intent: str, plan_id: str, text: str) -> str:
    from .platform_knowledge import (
        HOW_IT_WORKS,
        HOW_TO_UPGRADE,
        PLAN_FREE,
        PLAN_STARTER,
        PLAN_GROWTH,
        HOSTING,
        PREVIEW,
        WATERMARK,
        GENERATE_FLOW,
        LIMITS,
    )
    if intent == "greet":
        return (
            "مرحباً بك في Maestro 👋\n"
            "أنا هنا لمساعدتك في بناء وإدارة مشاريع البوتات بكل سهولة وذكاء.\n"
            "اسألني: ازاي المنصة بتشتغل؟ ازاي أرقى؟ أو اكتب وصف بوت."
        )
    if intent == "goodbye":
        return "إلى اللقاء! اكتب /start أو أي سؤال لما ترجع."
    if intent == "how_platform_works":
        return HOW_IT_WORKS
    if intent == "how_to_upgrade":
        return HOW_TO_UPGRADE
    if intent == "ask_about_hosting":
        return HOSTING
    if intent == "ask_about_preview":
        return PREVIEW
    if intent == "ask_about_watermark":
        return WATERMARK
    if intent == "ask_about_free":
        return PLAN_FREE
    if intent == "ask_about_starter":
        return PLAN_STARTER
    if intent == "ask_about_growth":
        return PLAN_GROWTH
    if intent == "ask_help":
        return (
            "أقدر أشرح لك:\n"
            "• ازاي Maestro بيشتغل\n"
            "• الخطط والترقية (Free / Starter / Growth)\n"
            "• الاستضافة والمعاينة والعلامة المائية\n"
            "• ازاي توصف بوت للتوليد\n\n"
            "أوامر: /plan · /help · /start"
        )
    if intent == "ask_capabilities":
        return HOW_IT_WORKS
    if intent == "ask_plan":
        return _plan_body(plan_id)
    if intent == "ask_pricing":
        return (
            PLAN_FREE + "\n" + PLAN_STARTER + "\n" + PLAN_GROWTH
            + "\nللترقية: اكتب «ازاي أرقى» أو راسل الدعم."
        )
    if intent == "ask_how_to_generate":
        return GENERATE_FLOW
    if intent == "ask_limitations":
        return LIMITS
    if intent == "ask_support":
        return (
            "الدعم للخطط المدفوعة:\n"
            "capability7maestro7bot@gmail.com\n"
            "أو اكتب سؤالك هنا (ترقية، استضافة، حدود…)."
        )
    if intent == "bot_challenge":
        return "أنا مساعد Maestro — بفهم المنصة والخطط ومسار التوليد وأوجّهك بدقة."
    if intent == "affirm":
        return "تمام، كمّل سؤالك أو اكتب وصف البوت."
    if intent == "deny":
        return "حاضر. لو حابب نبدأ من جديد: /start"
    if intent == "out_of_scope":
        return "الطلب ده برا نطاق Maestro. اسأل عن الخطط، الترقية، أو توليد بوتات تيليجرام."
    return (
        "مش متأكد إنى فهمت قصدك.\n"
        "جرّب: «ازاي المنصة بتشتغل» · «ازاي أرقى للبرو» · «خطتي» · أو وصف بوت."
    )

class RuleEngine:
    name = "rule_v1"

    def available(self) -> bool:
        return True

    async def handle(self, request: DialogueRequest) -> DialogueResponse | None:
        text = (request.text or "").strip()
        if not text:
            return None
        # Platform slash commands (except dialogue ones) stay on legacy handlers
        low = text.lower()
        if text.startswith("/") and not low.startswith(("/plan", "/خطة", "/help")):
            return None
        intent, conf = classify(text)
        # Generation-bound intents: do NOT swallow — hand off to messages.py / engine
        if intent == "describe_bot_idea":
            return DialogueResponse(
                text="",
                intent=intent,
                confidence=conf,
                engine=self.name,
                slots={"plan_id": request.plan_id or "free"},
                handled=False,
            )
        reply = _reply(intent, request.plan_id or "free", text)
        return DialogueResponse(
            text=reply,
            intent=intent,
            confidence=conf,
            engine=self.name,
            slots={"plan_id": request.plan_id or "free"},
            handled=True,
        )
