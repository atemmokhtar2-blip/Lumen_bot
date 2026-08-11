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


def _score(text_n: str, toks: set[str], spec: _PatternIntent) -> float:
    score = 0.0
    for ph in spec.any_phrases:
        pn = normalize(ph)
        if pn and pn in text_n:
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
        # prefer guidance over handoff when user is asking how
        if best_intent == "describe_bot_idea":
            best_intent = "ask_how_to_generate"
            best_score = max(best_score, 1.4)
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
    if intent == "greet":
        return (
            "مرحباً بك في Maestro 👋\n"
            "أنا هنا لمساعدتك في بناء وإدارة مشاريع البوتات بكل سهولة وذكاء.\n"
            "اكتب وصف البوت، أو اسأل عن الخطط والمميزات."
        )
    if intent == "goodbye":
        return "إلى اللقاء! اكتب /start أو أي سؤال لما ترجع."
    if intent == "ask_help":
        return (
            "أقدر أساعدك في:\n"
            "• صياغة وصف بوت واضح للتوليد\n"
            "• شرح الخطط (Free / Starter / Growth)\n"
            "• توضيح الحدود والصلاحيات\n"
            "• توجيهك للخطوة الجاية\n\n"
            "أوامر: /plan · /help · /start"
        )
    if intent == "ask_capabilities":
        return (
            "Maestro يولّد بوتات تيليجرام من وصف طبيعي.\n"
            "أنا بفهم قصدك وأوجّهك؛ التوليد الفعلي حسب صلاحيات خطتك."
        )
    if intent == "ask_plan":
        return _plan_body(plan_id)
    if intent == "ask_pricing":
        return (
            "الأسعار:\n"
            "• Free — مجاني (حدود توليد + معاينة حية)\n"
            "• Starter — $8/شهر (بوت واحد 24/7 + دفع/Webhooks)\n"
            "• Growth — $30/شهر (حتى 5 بوتات + DB/تحليلات)\n\n"
            "خطتك الحالية عبر /plan"
        )
    if intent == "ask_how_to_generate":
        return (
            "عشان تولّد بوت:\n"
            "1) اكتب وصف واضح (الأوامر، الجمهور، المميزات)\n"
            "2) مثال: «بوت متجر فيه قائمة منتجات وطلب وتأكيد»\n"
            "3) المنصة تولّد حسب خطتك\n\n"
            "كل ما الوصف أدق، النتيجة أحسن."
        )
    if intent == "describe_bot_idea":
        return (
            "فكرة كويسة — عشان نطلع نتيجة أدق:\n"
            "• الجمهور مين؟\n"
            "• الأوامر أو الأزرار الأساسية إيه؟\n"
            "• فيه دفع / أدمن / ردود تلقائية؟\n"
            "اكتب وصف أوضح وجاهز للتوليد حسب خطتك."
        )
    if intent == "ask_limitations":
        return (
            "بوضوح:\n"
            "• التوليد والاستضافة محدودان حسب الخطة\n"
            "• المميزات المتقدمة للخطط الأعلى\n"
            "• لو طلبت حاجة برة النطاق، هقولك بصراحة"
        )
    if intent == "ask_support":
        return (
            "الدعم للخطط المدفوعة:\n"
            "capability7maestro7bot@gmail.com\n"
            "أو اكتب سؤالك هنا وأوجّهك."
        )
    if intent == "bot_challenge":
        return "أنا مساعد Maestro — طبقة حوار داخل المنصة (قواعد + Rasa عند التفعيل)."
    if intent == "affirm":
        return "تمام، كمّل وصفك أو اسأل اللي محتاجه."
    if intent == "deny":
        return "حاضر. لو حابب نبدأ من جديد اكتب /start أو وصف البوت."
    if intent == "out_of_scope":
        return "الطلب ده برا نطاق Maestro. أقدر أساعد في بوتات تيليجرام والخطط والتوجيه."
    # fallback — still helpful, never empty
    return (
        "مش متأكد إنى فهمت قصدك تماماً.\n"
        "جرّب: «خطتي» · «الأسعار» · «ازاي أولد بوت» · أو اكتب وصف البوت مباشرة."
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
