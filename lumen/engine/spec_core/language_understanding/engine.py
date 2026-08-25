"""Language Understanding Engine — Layer 1 MAX (zero-AI).

Synonyms + dialect map + fuzzy + stems + entities + multi-domain ranking
+ ambiguity + adaptive questions + feature hints personalized per utterance.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from .entities import ExtractedEntities, extract_entities
from .fuzzy import best_match, partial_ratio, token_set_ratio
from .normalize import light_stem_ar, normalize_text, tokenize

_DATA = Path(__file__).resolve().parent / "data"

DOMAIN_TO_PRESET: dict[str, str] = {
    "shop": "shop",
    "marketplace": "marketplace",
    "restaurant": "restaurant",
    "booking": "booking",
    "tickets": "support_pro",
    "wallet": "wallet",
    "payments": "shop",
    "delivery": "shop",
    "education": "education",
    "crm": "crm",
    "saas": "saas",
    "security": "security_ops",
    "iot": "iot",
    "blockchain": "blockchain",
    "devops": "devops",
    "ai_ml": "ai_assist",
    "gaming": "gaming",
    "healthcare": "clinic",
    "finance": "finance",
    "logistics": "logistics",
    "tasks": "tasks",
    "notes": "notes",
    "growth": "growth",
    "points": "points",
    "subscriptions": "subscriptions",
    "contests": "contests",
    "jobs": "jobs",
    "events": "events",
    "fitness": "fitness",
    "clinic": "clinic",
    "moderation": "group_admin",
    "commerce_pro": "commerce_pro",
}


@dataclass
class DomainSignal:
    domain: str
    score: float
    confidence: float
    sources: list[str] = field(default_factory=list)
    matched: list[str] = field(default_factory=list)


@dataclass
class LanguageUnderstandingResult:
    original: str
    normalized: str
    tokens: list[str]
    domains: list[DomainSignal]
    primary_domain: str | None
    primary_preset: str | None
    secondary_domains: list[str]
    entities: ExtractedEntities
    is_ambiguous: bool
    ambiguity_reason: str
    skill_hint: str
    suggested_questions: list[str] = field(default_factory=list)
    feature_hints: list[str] = field(default_factory=list)
    complexity_hint: str = "simple"  # simple | medium | complex

    def to_dict(self) -> dict[str, Any]:
        return {
            "normalized": self.normalized,
            "primary_domain": self.primary_domain,
            "primary_preset": self.primary_preset,
            "secondary_domains": self.secondary_domains,
            "domains": [
                {
                    "domain": d.domain,
                    "score": round(d.score, 2),
                    "confidence": round(d.confidence, 3),
                    "matched": d.matched[:6],
                    "sources": d.sources,
                }
                for d in self.domains[:8]
            ],
            "entities": self.entities.to_dict(),
            "is_ambiguous": self.is_ambiguous,
            "ambiguity_reason": self.ambiguity_reason,
            "skill_hint": self.skill_hint,
            "complexity_hint": self.complexity_hint,
            "suggested_questions": self.suggested_questions,
            "feature_hints": self.feature_hints,
        }


@lru_cache(maxsize=1)
def _load_json(name: str) -> dict:
    path = _DATA / name
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _stop_words() -> set[str]:
    path = _DATA / "stop_words_ar.txt"
    if not path.exists():
        return set()
    return {ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()}


@lru_cache(maxsize=1)
def _all_synonym_entries() -> dict[str, list[str]]:
    ar = _load_json("synonyms_ar.json")
    en = _load_json("synonyms_en.json")
    merged: dict[str, list[str]] = {}
    for src in (ar, en):
        for dom, words in src.items():
            merged.setdefault(dom, [])
            for w in words:
                nw = normalize_text(w)
                if nw and nw not in merged[dom]:
                    merged[dom].append(nw)
                st = light_stem_ar(nw)
                if st and st not in merged[dom] and len(st) >= 3:
                    merged[dom].append(st)
    return merged


def _content_tokens(text: str) -> list[str]:
    stops = _stop_words()
    out: list[str] = []
    for t in tokenize(text):
        if t in stops or len(t) <= 1:
            continue
        out.append(t)
        st = light_stem_ar(t)
        if st != t and st not in stops:
            out.append(st)
    return out


def _skill_hint(text: str, tokens: list[str]) -> str:
    tech = {
        "api", "webhook", "rest", "oauth", "sqlite", "postgres", "docker",
        "jwt", "ci/cd", "kubernetes", "endpoint", "schema", "middleware",
        "rate limit", "microservice", "redis", "nginx",
    }
    low = (text or "").lower()
    hits = sum(1 for t in tech if t in low)
    if hits >= 2 or len(tokens) > 28:
        return "expert"
    if hits == 1 or len(tokens) > 12:
        return "intermediate"
    return "beginner"


def _complexity(entities: ExtractedEntities, domains: list[DomainSignal], tokens: list[str]) -> str:
    score = 0
    score += min(3, len(domains))
    score += len(entities.payment_methods)
    score += int(entities.wants_delivery) + int(entities.wants_discounts)
    score += int(entities.wants_wallet) + int(entities.wants_reviews)
    score += int(bool(entities.brand_analogy))
    score += 1 if len(tokens) > 15 else 0
    if score >= 7:
        return "complex"
    if score >= 3:
        return "medium"
    return "simple"


def _feature_hints(entities: ExtractedEntities, domains: list[DomainSignal]) -> list[str]:
    hints: list[str] = []
    if not domains:
        doms = set()
    else:
        top = domains[0].score
        # keep domains within 55% of top score (or score>=2.5) to avoid weak bleed
        doms = {
            d.domain
            for d in domains
            if d.score >= 1.0 and (d.score >= top * 0.55 or d.score >= 2.5 or d is domains[0])
        }

    def add(*keys: str) -> None:
        for k in keys:
            if k not in hints:
                hints.append(k)

    # ── Commerce (only when commerce domains actually ranked) ─
    non_commerce = {
        "security", "education", "iot", "blockchain", "devops", "ai_ml",
        "gaming", "tickets", "crm", "saas", "moderation", "clinic",
        "healthcare", "finance", "logistics", "jobs", "fitness", "tasks", "notes",
    }
    commerce_hit = bool(doms & {"shop", "marketplace", "restaurant", "delivery", "payments"})
    # product/category only counts as commerce if not a non-commerce category label
    cat = (entities.category or "")
    product_is_commerce = bool(entities.product or cat) and cat not in {
        "أمن سيبراني", "دورات",
    } and not (doms & non_commerce and not commerce_hit)
    if commerce_hit or (product_is_commerce and not (doms & non_commerce)):
        add("shop_catalog", "cart_view", "cart_checkout", "shop_add_item", "shop_orders")
        if entities.wants_discounts:
            add("coupon_apply", "coupon_create")
        if entities.wants_delivery:
            add("shipping_set", "order_track")
        if entities.wants_reviews:
            add("review_add")
        pays = set(entities.payment_methods)
        if pays & {"vodafone_cash", "fawry", "orange_cash", "instapay", "wallet"}:
            add("wallet_balance", "wallet_topup", "vodafone_cash", "pay_methods")
        if pays & {"visa", "telegram_payments"}:
            add("shop_buy", "payment_history", "pay_methods", "invoice_preview")
        if "cod" in pays:
            add("pay_methods", "order_track")
        if pays:
            add("pay_methods")
        if entities.brand_analogy in {"amazon", "noon", "jumia"}:
            add("product_search", "wishlist_add", "wishlist_view", "review_add")
    if "marketplace" in doms:
        add("listing_create", "listing_search", "listing_mine")

    # ── Security / Cyber ──────────────────────────────────────
    if "security" in doms or entities.security_checks or entities.target_domain:
        add("sec_domain_overview", "sec_dns_check", "sec_tls_check", "sec_tips")
        checks = set(entities.security_checks)
        if "dns" in checks or "mx" in checks:
            add("sec_dns_check", "sec_mx_check")
        if "spf" in checks or "dmarc" in checks:
            add("sec_dns_check")
        if "tls" in checks:
            add("sec_tls_check")
        if "headers" in checks:
            add("sec_headers_check")
        if "phishing" in checks:
            add("sec_tips")
        if "whois" in checks:
            add("sec_domain_overview")
        add("sec_list_reports", "sec_checklist")

    # ── Support / tickets ─────────────────────────────────────
    if "tickets" in doms:
        add("ticket_open", "ticket_my", "ticket_list", "ticket_status", "ticket_reply")

    # ── Booking / clinic / restaurant ─────────────────────────
    if "booking" in doms or "clinic" in doms:
        add("ticket_open", "ticket_my")  # appointment-style capture
    if "restaurant" in doms:
        add("menu_view", "menu_order", "order_status", "table_book")

    # ── Education ─────────────────────────────────────────────
    if "education" in doms:
        add("course_list", "course_enroll", "lesson_list", "quiz_start", "progress_view")
        if entities.course_topic:
            add("course_list")

    # ── CRM / SaaS / growth ───────────────────────────────────
    if "crm" in doms:
        add("lead_capture", "lead_list", "pipeline_board", "deal_create", "followup_set")
    if "saas" in doms:
        add("plans", "subscribe", "my_sub", "analytics_overview", "admin_users")
    if "subscriptions" in doms:
        add("plans", "subscribe", "my_sub")
    if "points" in doms:
        add("balance", "leaderboard", "daily_checkin")
    if "growth" in doms:
        add("referral_code", "referral_invite", "referral_stats")
    if "contests" in doms:
        add("contests", "join_contest", "draw_winner")

    # ── IoT / Blockchain / DevOps / AI / Gaming ───────────────
    if "iot" in doms:
        add("sec_http_check", "note_add", "task_add")  # device notes + alerts
        if "mqtt" in (entities.tech_stack or []):
            add("note_add")
    if "blockchain" in doms:
        add("wallet_balance", "note_add")
    if "devops" in doms:
        add("status_cmd", "note_add", "task_add") if False else add("note_add", "task_add")
        if "docker" in (entities.tech_stack or []):
            add("note_add")
    if "ai_ml" in doms:
        add("note_add", "faq_show")
    if "gaming" in doms:
        add("leaderboard", "balance", "contests", "join_contest")

    # ── Healthcare / finance / logistics / jobs / fitness ─────
    if "healthcare" in doms or "clinic" in doms:
        add("ticket_open", "ticket_my", "ticket_list")
    if "finance" in doms:
        add("invoice_preview", "payment_history", "wallet_balance")
    if "logistics" in doms:
        add("order_track", "shipping_set", "shop_orders")
    if "jobs" in doms:
        add("job_list", "job_apply", "job_my_apps")
    if "fitness" in doms:
        add("daily_checkin", "streak_status", "balance")
    if "events" in doms:
        add("contests", "join_contest")
    if "moderation" in doms:
        add("rules", "my_id")
    if "tasks" in doms:
        add("task_add", "task_list")
    if "notes" in doms:
        add("note_add", "note_list")

    return hints



def _suggested_questions(
    primary: str | None,
    entities: ExtractedEntities,
    is_ambiguous: bool,
    skill: str,
) -> list[str]:
    qs: list[str] = []
    if not primary or is_ambiguous:
        if skill == "expert":
            qs.append("حدّد الـ vertical: shop / security / support / booking / saas / iot / education؟")
        else:
            qs.append("عايز البوت يعمل إيه؟ (متجر / أمن سيبراني / دعم / حجوزات / تعليم / مطعم / IoT…)")
        return qs[:4]

    if primary in {"shop", "marketplace"}:
        if not entities.product and not entities.category:
            qs.append("هتبيع إيه؟ (ملابس / أحذية / إلكترونيات…)" if skill != "expert" else "Catalog domain + physical/digital SKUs؟")
        if not entities.payment_methods:
            qs.append("طرق الدفع؟ (فيزا / فودافون / فوري / COD)")
        if not entities.wants_delivery:
            qs.append("محتاج توصيل وتتبع شحنات؟")
    elif primary == "security":
        if not entities.target_domain and not entities.target_url:
            qs.append("فحص على دومين معيّن؟ اكتب المثال: example.com")
        if not entities.security_checks:
            qs.append("أي فحوصات؟ DNS / TLS / Headers / Phishing awareness / Incident reports")
        qs.append("التقارير للمستخدم ولا للإدمن فقط؟")
    elif primary == "tickets":
        qs.append("التذاكر لعملاء خارجيين ولا فريق داخلي؟")
        qs.append("محتاج أولويات (low/normal/high) وSLA؟")
    elif primary in {"booking", "clinic"}:
        qs.append("الحجز لمواعيد / طاولات / خدمات؟ ومدة الجلسة؟")
    elif primary == "restaurant":
        qs.append("منيو + طلبات، ولا كمان حجز طاولات وتوصيل؟")
    elif primary == "education":
        if not entities.course_topic:
            qs.append("الكورسات عن إيه؟ وعايز اختبارات/شهادات؟")
        else:
            qs.append("تتبع تقدّم الطلاب وواجبات؟")
    elif primary == "crm":
        qs.append("مراحل الـ pipeline؟ (جديد → تواصل → صفقة…)")
    elif primary == "saas":
        qs.append("خطط الاشتراك؟ وعايز لوحة أدمن وتحليلات؟")
    elif primary == "iot":
        qs.append("الأجهزة تتصل بإيه؟ MQTT / HTTP / Telegram alerts؟")
    elif primary == "blockchain":
        qs.append("متابعة محفظة / تنبيهات أسعار / NFT gallery؟")
    elif primary == "devops":
        qs.append("تنبيهات deploy / حالة الخدمات / ربط webhook؟")
    elif primary == "gaming":
        qs.append("لوحة متصدرين، بطولات، ولا اقتصاد نقاط داخل اللعبة؟")
    elif primary == "moderation":
        qs.append("أوامر المشرفين: حظر / كتم / تحذير / فلتر كلمات؟")
    elif primary == "jobs":
        qs.append("نشر وظائف + تقديم، ولا متابعة مرشحين فقط؟")
    elif primary == "finance":
        qs.append("فواتير ومصروفات، ولا محفظة داخلية؟")
    elif primary == "logistics":
        qs.append("تتبع شحنات، أسطول، ولا إدارة مستودع؟")
    elif primary == "fitness":
        qs.append("تمارين يومية، سعرات، ولا اشتراكات جيم؟")
    return qs[:4]



@lru_cache(maxsize=512)
def understand(text: str) -> LanguageUnderstandingResult:
    original = text or ""
    normalized = normalize_text(original)
    tokens = _content_tokens(original)
    synonyms = _all_synonym_entries()

    rev: dict[str, set[str]] = {}
    all_syn: list[str] = []
    for dom, words in synonyms.items():
        if dom == "bot":
            continue
        for w in words:
            rev.setdefault(w, set()).add(dom)
            all_syn.append(w)

    scores: dict[str, DomainSignal] = {}

    def bump(dom: str, amount: float, source: str, matched: str) -> None:
        if dom not in scores:
            scores[dom] = DomainSignal(domain=dom, score=0.0, confidence=0.0)
        s = scores[dom]
        s.score += amount
        if source not in s.sources:
            s.sources.append(source)
        if matched and matched not in s.matched:
            s.matched.append(matched[:40])

    # 1) exact / stem token hits
    for tok in tokens:
        if tok in rev:
            for dom in rev[tok]:
                bump(dom, 2.4, "keyword", tok)
        else:
            m, sc = best_match(tok, all_syn, cutoff=74.0)
            if m and m in rev:
                for dom in rev[m]:
                    bump(dom, 1.6 * (sc / 100.0) + 0.6, "fuzzy", f"{tok}~{m}")

    # 2) phrase presence in full normalized text
    for dom, words in synonyms.items():
        if dom == "bot":
            continue
        for w in words:
            if len(w) >= 3 and w in normalized:
                bump(dom, 2.8 if len(w) >= 5 else 2.0, "phrase", w)
            elif len(w) >= 5:
                pr = partial_ratio(w, normalized)
                if pr >= 86:
                    bump(dom, 1.3, "partial", w)

    # 3) intent keywords
    for dom, groups in (_load_json("intent_keywords.json") or {}).items():
        for w in groups.get("primary") or []:
            nw = normalize_text(w)
            if nw and nw in normalized:
                bump(dom, 2.2, "intent_primary", w)
        for w in groups.get("secondary") or []:
            nw = normalize_text(w)
            if nw and nw in normalized:
                bump(dom, 1.1, "intent_secondary", w)

    # 4) token-set similarity against domain synonym blob
    for dom, words in synonyms.items():
        if dom == "bot":
            continue
        blob = " ".join(words[:40])
        tsr = token_set_ratio(normalized, blob)
        if tsr >= 35:
            bump(dom, tsr / 50.0, "token_set", f"tsr={tsr:.0f}")

    entities = extract_entities(original)

    # 5) entity-driven domain boosts (all verticals)
    if entities.product or entities.category:
        if entities.category == "أمن سيبراني" or entities.security_checks:
            bump("security", 3.0, "entity_sec_cat", entities.category or "sec")
        elif entities.category == "دورات" or entities.course_topic:
            bump("education", 2.8, "entity_edu", entities.course_topic or "course")
        else:
            bump("shop", 2.5, "entity_product", entities.category or entities.product or "")
    if entities.payment_methods:
        bump("payments", 2.0, "entity_pay", ",".join(entities.payment_methods[:3]))
        # only drag shop if commerce signals exist
        if entities.product or entities.category or entities.wants_delivery or entities.wants_discounts:
            bump("shop", 1.2, "entity_pay_shop", "pay")
    if entities.wants_delivery:
        bump("delivery", 1.5, "entity_delivery", "delivery")
        if entities.product or entities.category:
            bump("shop", 0.8, "entity_delivery_shop", "ship")
    if entities.brand_analogy in {"amazon", "noon", "jumia"}:
        bump("marketplace", 3.0, "brand_analogy", entities.brand_analogy)
        bump("shop", 2.0, "brand_analogy_shop", entities.brand_analogy)
    if entities.wants_discounts:
        bump("shop", 1.0, "entity_discount", "coupon")
    if entities.security_checks or entities.target_domain or entities.target_url or entities.target_ip:
        bump("security", 3.5, "entity_sec", ",".join(entities.security_checks[:4]) or (entities.target_domain or "host"))
    if entities.course_topic:
        bump("education", 2.5, "entity_course", entities.course_topic)
    if entities.tech_stack:
        for tech in entities.tech_stack:
            if tech in {"docker", "kubernetes", "nginx"}:
                bump("devops", 2.2, "entity_tech", tech)
            if tech in {"mqtt", "arduino", "esp32"}:
                bump("iot", 2.5, "entity_tech", tech)
            if tech in {"postgres", "redis"}:
                bump("saas", 1.2, "entity_tech", tech)

    # Commerce gravity: selling verbs / product → shop owns delivery/payments
    sell = any(
        x in normalized
        for x in (
            "يبيع", "بيع", "لبيع", "منتج", "منتجات", "متجر", "محل", "دكان",
            "shop", "store", "catalog", "cart", "ecommerce", "ملابس", "احذية", "احذيه",
        )
    )
    if sell and "shop" in scores and "security" not in scores:
        scores["shop"].score += 2.5
        if "delivery" in scores:
            scores["delivery"].score *= 0.55
        if "payments" in scores and scores["payments"].score > scores["shop"].score:
            scores["shop"].score = max(scores["shop"].score, scores["payments"].score * 0.9)

    # Strong vertical lock: security / iot / devops / education beat weak shop bleed
    for lock_dom, min_score in (
        ("security", 3.0), ("iot", 2.5), ("devops", 2.5), ("education", 2.5),
        ("blockchain", 2.5), ("gaming", 2.5), ("moderation", 2.5), ("crm", 2.5),
        ("contests", 2.5), ("tickets", 2.5), ("clinic", 2.5), ("restaurant", 2.5),
        ("saas", 2.5), ("ai_ml", 2.5), ("jobs", 2.5), ("fitness", 2.5),
    ):
        if lock_dom in scores and scores[lock_dom].score >= min_score:
            if "shop" in scores and scores["shop"].score < scores[lock_dom].score:
                scores["shop"].score *= 0.35
            if "marketplace" in scores and scores["marketplace"].score < scores[lock_dom].score:
                scores["marketplace"].score *= 0.35

    ranked = sorted(scores.values(), key=lambda d: d.score, reverse=True)
    for d in ranked:
        d.confidence = max(0.0, min(0.99, d.score / (d.score + 3.5)))

    primary = ranked[0].domain if ranked and ranked[0].score >= 1.0 else None
    # Map pure payments/delivery primary back to shop when sell gravity
    if primary in {"payments", "delivery"} and sell:
        primary = "shop"
    primary_preset = DOMAIN_TO_PRESET.get(primary) if primary else None
    secondary = [
        d.domain
        for d in ranked[1:6]
        if d.score >= 1.2 and d.domain != primary
    ]

    is_ambiguous = False
    reason = ""
    if not primary:
        is_ambiguous = True
        reason = "لم يتضح نوع البوت من النص"
    elif len(ranked) >= 2 and ranked[1].score >= 1.5 and abs(ranked[0].score - ranked[1].score) < 0.7:
        cluster_ok = [
            {"shop", "delivery", "payments", "marketplace"},
            {"clinic", "booking", "healthcare"},
            {"restaurant", "delivery", "shop"},
            {"security"},
            {"education", "saas"},
            {"iot", "devops"},
            {"gaming", "points", "contests"},
            {"tickets", "crm"},
        ]
        top2 = {ranked[0].domain, ranked[1].domain}
        if any(top2 <= c or top2 & c == top2 for c in cluster_ok):
            pass  # related cluster — not ambiguous
        else:
            is_ambiguous = True
            reason = f"تعارض بين {ranked[0].domain} و {ranked[1].domain}"
    elif len([t for t in tokens if t not in _stop_words()]) <= 1 and (
        not ranked or ranked[0].confidence < 0.5
    ):
        is_ambiguous = True
        reason = "الوصف قصير جداً — نحتاج تفاصيل"

    skill = _skill_hint(original, tokens)
    complexity = _complexity(entities, ranked, tokens)
    feature_hints = _feature_hints(entities, ranked)
    questions = _suggested_questions(primary, entities, is_ambiguous, skill)
    # ask product question for bare shop
    if (
        primary in {"shop", "marketplace"}
        and not entities.product
        and not entities.category
        and not questions
    ):
        questions = _suggested_questions(primary, entities, True, skill)

    return LanguageUnderstandingResult(
        original=original,
        normalized=normalized,
        tokens=tokens,
        domains=ranked,
        primary_domain=primary,
        primary_preset=primary_preset,
        secondary_domains=secondary,
        entities=entities,
        is_ambiguous=is_ambiguous,
        ambiguity_reason=reason,
        skill_hint=skill,
        suggested_questions=questions,
        feature_hints=feature_hints,
        complexity_hint=complexity,
    )


__all__ = [
    "LanguageUnderstandingResult",
    "DomainSignal",
    "understand",
    "DOMAIN_TO_PRESET",
]
