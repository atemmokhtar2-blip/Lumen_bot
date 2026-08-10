"""Lightweight Arabic/English intent engine (no LLM) for preset detection."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class IntentMatch:
    domain: str
    score: float
    confidence: float
    matched_keywords: tuple[str, ...]


SYNONYM_GROUPS: dict[str, list[str]] = {
    "shop": [
        "متجر", "محل", "دكان", "سوق", "بيع", "شراء", "منتجات", "سلع", "بضاعة",
        "ملابس", "احذية", "أحذية", "الكترونيات", "إلكترونيات", "store", "shop",
        "ecommerce", "product", "catalog", "cart", "سلة", "كوبون",
    ],
    "marketplace": [
        "marketplace", "بائعين", "متعدد البائعين", "vendor", "bazaar", "سوق متعدد",
    ],
    "restaurant": [
        "مطعم", "اكل", "طعام", "وجبة", "قائمة", "menu", "restaurant", "food", "delivery",
        "توصيل طعام",
    ],
    "booking": [
        "حجز", "موعد", "مواعيد", "booking", "appointment", "schedule", "عيادة", "طبيب",
    ],
    "education": [
        "تعليم", "تعلم", "درس", "كورس", "دورة", "مدرسة", "education", "course", "quiz",
    ],
    "delivery": [
        "توصيل", "شحن", "شحنة", "تتبع", "delivery", "shipping", "tracking", "courier",
    ],
    "tickets": [
        "دعم", "تذكرة", "شكوى", "support", "ticket", "helpdesk", "customer support",
    ],
    "tasks": ["مهام", "مهمة", "todo", "task", "tasks", "تذكير"],
    "notes": ["ملاحظات", "ملاحظة", "notes", "note", "memo"],
    "community": ["مجتمع", "مجموعة", "community", "group", "forum"],
    "group_management": [
        "إدارة مجموعة", "حظر", "كتم", "تحذير", "ban", "mute", "warn", "moderation",
        "group admin", "مشرف",
    ],
    "wallet": ["محفظة", "رصيد", "wallet", "balance", "topup"],
    "subscriptions": ["اشتراك", "خطة", "subscription", "plan", "vip", "عضوية"],
    "points": ["نقاط", "ولاء", "points", "loyalty", "rewards", "leaderboard"],
    "contests": ["مسابقة", "قرعة", "contest", "giveaway", "raffle"],
    "growth": ["إحالة", "referral", "affiliate", "دعوة"],
    "news": ["اخبار", "أخبار", "news", "نشرة", "feed"],
    "fitness": ["رياضة", "جيم", "تمارين", "gym", "fitness", "workout"],
    "saas": ["saas", "منصة", "workspace", "tenant"],
    "finance": ["محاسبة", "مالية", "finance", "accounting", "ledger"],
    "logistics": ["لوجستيات", "مستودع", "logistics", "warehouse"],
    "creator": ["منشئ", "محتوى", "creator", "patreon", "content"],
    "jobs": ["وظائف", "توظيف", "jobs", "recruitment", "cv"],
    "events": ["فعالية", "حدث", "events", "ticket sales"],
    "crm": ["crm", "عملاء", "leads", "pipeline"],
    "commerce_pro": [
        "commerce pro", "متجر كامل", "متجر متكامل", "متجر احترافي", "متجر شامل",
        "ecommerce full", "commerce suite", "منصة تجارة", "عالمي متكامل",
        "كتالوج", "فواتير", "مدفوعات تيليجرام", "استرجاع", "تجربة مجانية",
        "إهداء اشتراك", "لوحة متصدرين", "سلاسل", "إذاعة", "قاعدة معرفة",
        "وضع صيانة", "ولاء", "تحليلات", "إيرادات",
    ],
    "security_ops": [
        "أمن", "امن", "سيبراني", "cyber", "cybersecurity", "cyberguard",
        "phishing", "تصيد", "تصيّد", "dns", "tls", "ssl", "spf", "dmarc",
        "domain scan", "website scan", "فحص أمني", "ثغرة", "soc", "incident",
        "شهادة", "security headers", "توعية أمنية", "نصائح أمان",
    ],
    "iot": [
        "iot", "إنترنت الأشياء", "حساسات", "مستشعرات", "mqtt", "arduino",
        "esp32", "أجهزة ذكية", "أتمتة منزلية", "smart home",
    ],
    "blockchain": [
        "blockchain", "بلوك تشين", "crypto", "bitcoin", "ethereum", "nft",
        "عقد ذكي", "web3", "عملة رقمية",
    ],
    "ai_assist": [
        "ذكاء اصطناعي", "machine learning", "chatgpt", "gpt", "openai",
        "تعلم آلي", "llm", "nlp",
    ],
    "devops": [
        "devops", "docker", "kubernetes", "k8s", "ci/cd", "deployment",
        "حاوية", "terraform", "pipeline",
    ],
    "gaming": [
        "لعبة", "ألعاب", "game", "tournament", "بطولة", "leaderboard",
        "achievement", "إنجاز",
    ],
}

DOMAIN_TO_PRESET = {
    "shop": "shop",
    "marketplace": "marketplace",
    "restaurant": "restaurant",
    "booking": "booking",
    "education": "education",
    "delivery": "logistics",
    "tickets": "support_tickets",
    "tasks": "tasks",
    "notes": "notes",
    "community": "community",
    "group_management": "group_management",
    "wallet": "wallet",
    "subscriptions": "subscriptions",
    "points": "points",
    "contests": "contests",
    "growth": "growth",
    "news": "community",
    "fitness": "fitness",
    "saas": "saas",
    "finance": "finance",
    "logistics": "logistics",
    "creator": "creator",
    "jobs": "jobs",
    "events": "events",
    "crm": "crm",
    "commerce_pro": "commerce_pro",
    "security_ops": "security_ops",
    "iot": "iot",
    "blockchain": "blockchain",
    "ai_assist": "ai_assist",
    "devops": "devops",
    "gaming": "gaming",
    "generic": "echo_basic",
}

_NEGATIVE = (
    "قصة", "قصه", "قصيدة", "شعر", "مقال", "رواية", "اكتبلي", "اكتب لي",
    "story", "poem", "article", "translate this", "ترجم هذا", "ارسم", "صورة فقط",
    "حكاية", "حكايه",
)


def normalize_arabic(text: str) -> str:
    if not text:
        return ""
    t = re.sub(r"[\u064B-\u0652]", "", text)
    t = re.sub(r"[إأآا]", "ا", t)
    t = re.sub(r"ى", "ي", t)
    t = re.sub(r"ة", "ه", t)
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t


def stem_arabic(text: str) -> str:
    """Lightweight Arabic stemming for intent matching."""
    text = normalize_arabic(text)
    rules = [
        (r"^ال", ""),
        (r"(ات|ين|ون|ان|ة|ه|ي|ك|كم|هم|هن|نا)$", ""),
        (r"^(وال|بال|كال|فال)", ""),
    ]
    out = []
    for w in text.split():
        x = w
        for pat, rep in rules:
            x = re.sub(pat, rep, x)
        out.append(x or w)
    return " ".join(out)


def classify_intent(text: str) -> list[IntentMatch]:

    norm = normalize_arabic(text)
    stemmed = stem_arabic(text)
    if not norm:
        return []
    results: list[IntentMatch] = []
    for domain, keywords in SYNONYM_GROUPS.items():
        score = 0.0
        matched: list[str] = []
        for kw in keywords:
            k = normalize_arabic(kw)
            if not k:
                continue
            if k in norm:
                score += 3.0
                matched.append(kw)
            elif stem_arabic(kw) and stem_arabic(kw) in stemmed:
                score += 2.0
                matched.append(kw)
            elif any(k in w or w in k for w in norm.split() if len(w) > 2 and len(k) > 2):
                score += 1.2
                matched.append(kw)
        if score > 0:
            weight = 1.5 if domain in {"shop", "marketplace", "commerce_pro", "restaurant"} else 1.0
            conf = min(1.0, score / (len(keywords) * 0.5 + 1))
            results.append(
                IntentMatch(domain, score * weight, conf, tuple(matched[:12]))
            )
    results.sort(key=lambda m: (m.score, m.confidence), reverse=True)
    return results


def is_clearly_non_bot(text: str) -> bool:
    norm = normalize_arabic(text)
    negatives = [normalize_arabic(n) for n in _NEGATIVE]
    if any(n and n in norm for n in negatives):
        strong = any(s in norm for s in ("بوت", "bot", "telegram", "تيليجرام", "تلجرام", "روبوت"))
        return not strong
    return False


def detect_bot_request_arabic(text: str) -> tuple[str | None, float]:
    if is_clearly_non_bot(text):
        return None, 0.0
    norm = normalize_arabic(text)
    has_bot = any(s in norm for s in ("بوت", "bot", "telegram", "تيليجرام", "تلجرام", "روبوت"))
    intents = classify_intent(text)
    if not intents:
        return ("generic", 0.45) if has_bot else (None, 0.0)
    best = intents[0]
    if best.score < 1.5 and not has_bot:
        return None, 0.0
    return best.domain, min(1.0, best.confidence + (0.2 if has_bot else 0.0))


def extract_bot_name(text: str) -> str | None:
    norm = normalize_arabic(text)
    patterns = [
        r"(?:اسمه|اسمها|يسمى|تسمى)\s+([A-Za-z0-9_\u0600-\u06FF\-]{2,40})",
        r"(?:named|called)\s+([A-Za-z0-9_\-]{2,40})",
        r"\bbot\s+(?:named\s+|called\s+)?([A-Za-z0-9_\-]{2,40})",
        r"\b([A-Z][a-zA-Z0-9]{2,30}(?:Guard|Bot|Ops|Hub|Pro|App)?)\b",
    ]
    stop = {
        "لبيع", "فيه", "that", "with", "for", "اسمه", "اسمها", "تيليجرام",
        "telegram", "bot", "بوت", "security_ops", "commerce_pro", "group",
    }
    for pat in patterns:
        m = re.search(pat, text or "", re.I)
        if not m:
            m = re.search(pat, norm, re.I)
        if m:
            name = re.sub(r"[^\w\u0600-\u06FF\-]", "_", m.group(1))
            name = re.sub(r"_+", "_", name).strip("_")
            if name and name.lower() not in stop and len(name) >= 2:
                return name[:40]
    return None


def smart_detect_preset(text: str) -> str | None:
    domain, conf = detect_bot_request_arabic(text)
    if not domain or conf < 0.15:
        return None
    return DOMAIN_TO_PRESET.get(domain)


def is_bot_request_smart(text: str) -> bool:
    domain, conf = detect_bot_request_arabic(text)
    return domain is not None and conf >= 0.2


__all__ = [
    "classify_intent",
    "detect_bot_request_arabic",
    "extract_bot_name",
    "smart_detect_preset",
    "is_bot_request_smart",
    "is_clearly_non_bot",
    "normalize_arabic",
    "IntentMatch",
]
