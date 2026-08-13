"""High-precision intent signatures + negative evidence (Layer-2 MAX).

Each signature is a weighted pattern set. Matches require either:
  - one strong anchor, or
  - enough weak hits to clear a threshold.
Negative evidence vetoes false positives (e.g. bare «بوت كويس» ≠ education).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .normalize import normalize_text


@dataclass(frozen=True)
class SigHit:
    intent: str
    score: float
    anchors: tuple[str, ...]


# Strong anchors (high weight). Weak cues (lower weight).
# format: intent -> (strong_regex_list, weak_regex_list, negative_regex_list)
_SIGNATURES: dict[str, tuple[list[str], list[str], list[str]]] = {
    "security": (
        [
            r"cyber",
            r"سيبراني",
            r"أمن\s*سيبراني",
            r"فحص\s*أمن",
            r"\bdns\b",
            r"\btls\b",
            r"\bssl\b",
            r"\bspf\b",
            r"\bdmarc\b",
            r"\bmx\b",
            r"phishing",
            r"تصيد",
            r"ثغر",
            r"domain\s*scan",
            r"website\s*scan",
            r"security\s*headers",
            r"whois",
            r"malware",
            r"firewall",
            r"فحص\s*(?:الدومين|دومين|موقع)",
            r"تفحص\s*(?:الدومين|دومين|موقع)",
        ],
        [r"headers", r"incident", r"soc", r"password", r"2fa", r"مصادقة"],
        [r"حظر\s*عضو", r"كتم\s*عضو", r"إدارة\s*جروب"],
    ),
    "shop": (
        [
            r"متجر",
            r"\bshop\b",
            r"\bstore\b",
            r"ecommerce",
            r"يبيع",
            r"أبيع",
            r"ابيع",
            r"لبيع",
            r"كتالوج",
            r"\bcart\b",
            r"سلة\s*مشتريات",
            r"منتجات",
        ],
        [r"كوبون", r"خصم", r"طلبية", r"sku", r"wishlist", r"ملابس", r"احذية", r"أحذية"],
        [r"سيبراني", r"\bdns\b", r"\btls\b", r"حساسات", r"\bmqtt\b"],
    ),
    "marketplace": (
        [r"marketplace", r"متعدد\s*البائعين", r"بائعين", r"زي\s*امازون", r"مثل\s*امازون", r"زي\s*نون"],
        [r"عمولة", r"vendor", r"jumia", r"جوميا"],
        [],
    ),
    "tickets": (
        [r"دعم\s*فني", r"تذاكر", r"تذكرة", r"helpdesk", r"\bsupport\b", r"شكاوى", r"شكوى", r"خدمة\s*عملاء"],
        [r"بلاغ", r"ticket", r"SLA", r"أولوية"],
        [],
    ),
    "moderation": (
        [
            r"إدارة\s*(?:جروب|مجموعة|جروب)",
            r"\bban\b",
            r"\bmute\b",
            r"\bwarn\b",
            r"حظر",
            r"كتم",
            r"تحذير",
            r"مشرف",
            r"moderation",
            r"anti\s*spam",
            r"بوت\s*(?:لل)?(?:جروب|مجموعة)",
            r"للمجموعة",
            r"للجروب",
        ],
        [r"فلتر", r"قواعد\s*الجروب", r"group\s*admin"],
        [r"\bdns\b", r"سيبراني", r"فحص\s*دومين"],
    ),
    "education": (
        [r"تعليمليم", r"كورس", r"دورة", r"دورات", r"\bcourse\b", r"\blms\b", r"كويز", r"\bquiz\b", r"منصة\s*تعليمليم"],
        [r"طالب", r"شهادة", r"واجب", r"منهج", r"درس"],
        [r"^[^ك]*بوت\s*كويس", r"يلا\s*نعمل"],  # block vague chatter
    ),
    "booking": (
        [r"حجز", r"موعد", r"مواعيد", r"\bbooking\b", r"\bappointment\b", r"احجز"],
        [r"جدول", r"reservation", r"calendar"],
        [],
    ),
    "clinic": (
        [r"عيادة", r"طبيب", r"دكتور", r"كشف", r"\bclinic\b", r"\bdoctor\b", r"أسنان", r"اسنان"],
        [r"مرضى", r"روشتة", r"patient"],
        [],
    ),
    "restaurant": (
        [r"مطعم", r"منيو", r"\bmenu\b", r"\brestaurant\b", r"كافيه", r"توصيل\s*أكل", r"توصيل\s*اكل"],
        [r"وجبات", r"بيتزا", r"برجر", r"طاولات"],
        [],
    ),
    "iot": (
        [r"\biot\b", r"إنترنت\s*الأشياء", r"حساسات", r"مستشعرات", r"\bmqtt\b", r"arduino", r"esp32", r"smart\s*home"],
        [r"جهاز", r"أجهزة\s*ذكية", r"تنبيهات\s*أجهزة"],
        [],
    ),
    "devops": (
        [r"\bdevops\b", r"\bdocker\b", r"kubernetes", r"\bk8s\b", r"ci\s*/\s*cd", r"\bdeploy\b"],
        [r"terraform", r"nginx", r"pipeline", r"monitoring"],
        [],
    ),
    "crm": (
        [r"\bcrm\b", r"ليدز", r"\bleads\b", r"صفقات", r"pipeline", r"مبيعات"],
        [r"متابعة\s*عملاء", r"عميل\s*محتمل"],
        [],
    ),
    "saas": (
        [r"\bsaas\b", r"workspace", r"multi\s*tenant", r"لوحة\s*تحكم", r"admin\s*panel"],
        [r"webhook", r"\bapi\b", r"اشتراك\s*شهري"],
        [],
    ),
    "gaming": (
        [r"ألعاب", r"لعبة", r"\bgaming\b", r"\bgame\b", r"بطولة", r"متصدرين", r"leaderboard", r"tournament"],
        [r"\bxp\b", r"مستوى", r"سكور"],
        [],
    ),
    "wallet": (
        [r"محفظة", r"\bwallet\b", r"شحن\s*رصيد", r"فودافون\s*كاش", r"instapay", r"فلوس"],
        [r"رصيد", r"تحويل"],
        [r"يبيع", r"متجر", r"منتجات"],
    ),
    "payments": (
        [r"مدفوعات", r"\bpayment\b", r"فيزا", r"\bvisa\b", r"بوابة\s*دفع"],
        [r"كاش", r"بطاقة"],
        [],
    ),
    "points": (
        [r"نقاط", r"ولاء", r"\bpoints\b", r"\bloyalty\b"],
        [r"مكافآت", r"rewards"],
        [],
    ),
    "contests": (
        [r"مسابقة", r"قرعة", r"\bgiveaway\b", r"\braffle\b", r"\bcontest\b"],
        [r"هدايا", r"سحب\s*عشوائي"],
        [],
    ),
    "growth": (
        [r"إحالة", r"ريفرال", r"\breferral\b", r"\baffiliate\b"],
        [r"دعوة\s*أصدقاء"],
        [],
    ),
    "subscriptions": (
        [r"اشتراك", r"عضوية", r"\bsubscription\b", r"\bvip\b"],
        [r"خطة\s*شهرية"],
        [],
    ),
    "jobs": (
        [r"وظائف", r"توظيف", r"\bjobs\b", r"\bhiring\b", r"سيرة\s*ذاتية"],
        [r"\bcv\b", r"مرشح"],
        [],
    ),
    "fitness": (
        [r"جيم", r"تمارين", r"\bfitness\b", r"\bworkout\b"],
        [r"كالوري", r"رياضة"],
        [],
    ),
    "finance": (
        [r"محاسبة", r"مالية", r"\bfinance\b", r"\baccounting\b"],
        [r"ميزانية", r"مصروفات"],
        [],
    ),
    "logistics": (
        [r"لوجستيات", r"مستودع", r"\blogistics\b", r"\bwarehouse\b"],
        [r"أسطول", r"سائقين"],
        [],
    ),
    "blockchain": (
        [r"blockchain", r"بلوك\s*تشين", r"\bcrypto\b", r"\bnft\b", r"\bweb3\b"],
        [r"bitcoin", r"ethereum", r"token"],
        [],
    ),
    "ai_ml": (
        [r"ذكاء\s*اصطناعي", r"machine\s*learning", r"\bllm\b", r"\bchatgpt\b"],
        [r"\bmodel\b", r"dataset", r"\bml\b"],
        [],
    ),
    "tasks": (
        [r"مهام", r"\btodo\b", r"\btasks\b", r"تذكير"],
        [r"task\s*manager"],
        [],
    ),
    "notes": (
        [r"ملاحظات", r"\bnotes\b", r"مذكرة"],
        [r"\bmemo\b"],
        [],
    ),
}


def match_signatures(text: str) -> list[SigHit]:
    raw = text or ""
    norm = normalize_text(raw)
    # search both original and normalized
    corpus = raw + "\n" + norm
    hits: list[SigHit] = []

    for intent, (strong, weak, negative) in _SIGNATURES.items():
        # negative veto
        if any(re.search(pat, corpus, re.I) for pat in negative):
            # only veto if NO strong anchor
            strong_hit = [p for p in strong if re.search(p, corpus, re.I)]
            if not strong_hit:
                continue

        anchors: list[str] = []
        score = 0.0
        for pat in strong:
            if re.search(pat, corpus, re.I):
                score += 1.0
                anchors.append(pat)
        for pat in weak:
            if re.search(pat, corpus, re.I):
                score += 0.35
                anchors.append(pat)

        if score < 0.9:
            continue
        # normalize soft
        hits.append(SigHit(intent=intent, score=min(1.0, score / 2.5), anchors=tuple(anchors[:6])))

    hits.sort(key=lambda h: -h.score)
    return hits


def vague_bot_request(text: str) -> bool:
    """True when user only said make a bot without domain substance."""
    t = normalize_text(text or "")
    # strip common filler
    for w in (
        "عايز", "عاوز", "محتاج", "ابغى", "اريد", "أريد", "يلا", "نعمل", "اعمل", "اعملي",
        "سوي", "بوت", "كويس", "حلو", "جدا", "اوي", "please", "want", "need", "make",
        "build", "bot", "telegram", "تيليجرام", "لي", "ليي",
    ):
        t = re.sub(rf"\b{re.escape(w)}\b", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return len(t) < 3


__all__ = ["SigHit", "match_signatures", "vague_bot_request"]
