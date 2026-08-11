"""Layer 5 — Suggestion Engine (zero-AI, dynamic).

Suggestions are NEVER a fixed list. They are computed from:
  1) What L2 already planned (feature_plan) — only propose gaps
  2) What L1 entities imply (payments/delivery/security checks…)
  3) Iron Memory patterns (co-occurrence probabilities per intent)
  4) Association rules seeded per domain (priors until stats mature)
  5) Post-build audit of the actual selected features
  6) Preventive heuristics (scale / risk)

Every suggestion carries: reason, confidence, source, action feature keys.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .engine import LanguageUnderstandingResult, understand
from .intent_analysis import IntentAnalysis, analyze_intent
from .memory_engine import MemoryEngine, get_memory_engine

# Seed association priors: intent → [(feature, prior_p, label_ar, label_en)]
# Used only when statistical sample is thin; real stats override when available.
_PRIORS: dict[str, list[tuple[str, float, str, str]]] = {
    "shop": [
        ("cart_view", 0.85, "سلة مشتريات", "shopping cart"),
        ("cart_checkout", 0.82, "إتمام شراء", "checkout"),
        ("coupon_apply", 0.72, "كوبونات وخصومات", "coupons & discounts"),
        ("review_add", 0.60, "تقييمات المنتجات", "product reviews"),
        ("order_track", 0.58, "تتبع الطلبات", "order tracking"),
        ("wishlist_add", 0.45, "قائمة أمنيات", "wishlist"),
        ("pay_methods", 0.70, "اختيار طريقة الدفع", "payment method picker"),
        ("wallet_topup", 0.40, "شحن محفظة", "wallet top-up"),
        ("product_search", 0.55, "بحث منتجات", "product search"),
        ("shipping_set", 0.50, "إعدادات الشحن", "shipping settings"),
    ],
    "marketplace": [
        ("listing_create", 0.80, "إنشاء إعلان", "create listing"),
        ("listing_search", 0.75, "بحث إعلانات", "search listings"),
        ("review_add", 0.55, "تقييمات", "reviews"),
        ("pay_methods", 0.65, "طرق الدفع", "payments"),
    ],
    "security": [
        ("sec_dns_check", 0.90, "فحص DNS", "DNS check"),
        ("sec_tls_check", 0.88, "فحص TLS/SSL", "TLS/SSL check"),
        ("sec_headers_check", 0.70, "Security Headers", "security headers"),
        ("sec_tips", 0.65, "توعية أمنية", "security awareness"),
        ("sec_list_reports", 0.55, "سجل البلاغات", "incident reports"),
        ("sec_domain_overview", 0.80, "نظرة عامة على الدومين", "domain overview"),
    ],
    "tickets": [
        ("ticket_open", 0.95, "فتح تذكرة", "open ticket"),
        ("ticket_status", 0.80, "حالة التذكرة", "ticket status"),
        ("ticket_reply", 0.70, "رد على تذكرة", "reply to ticket"),
        ("ticket_list", 0.75, "قائمة التذاكر", "ticket list"),
    ],
    "education": [
        ("course_list", 0.90, "قائمة الكورسات", "course list"),
        ("quiz_start", 0.70, "اختبارات", "quizzes"),
        ("progress_view", 0.65, "تتبع التقدم", "progress tracking"),
        ("course_enroll", 0.80, "تسجيل في كورس", "enroll"),
    ],
    "restaurant": [
        ("menu_view", 0.95, "عرض المنيو", "menu"),
        ("menu_order", 0.85, "طلب من المنيو", "place order"),
        ("table_book", 0.55, "حجز طاولة", "table booking"),
        ("order_status", 0.70, "حالة الطلب", "order status"),
    ],
    "crm": [
        ("lead_capture", 0.90, "التقاط ليد", "lead capture"),
        ("pipeline_board", 0.80, "لوحة Pipeline", "pipeline board"),
        ("deal_create", 0.75, "إنشاء صفقة", "create deal"),
        ("followup_set", 0.65, "متابعة", "follow-ups"),
    ],
    "gaming": [
        ("leaderboard", 0.85, "لوحة متصدرين", "leaderboard"),
        ("contests", 0.60, "بطولات", "tournaments"),
        ("balance", 0.55, "نقاط/رصيد", "points balance"),
    ],
    "iot": [
        ("note_add", 0.50, "سجل أجهزة", "device notes"),
        ("task_add", 0.45, "مهام تنبيه", "alert tasks"),
    ],
    "moderation": [
        ("rules", 0.85, "قواعد الجروب", "group rules"),
        ("my_id", 0.50, "عرض المعرف", "show user id"),
    ],
    "wallet": [
        ("wallet_balance", 0.95, "رصيد المحفظة", "wallet balance"),
        ("wallet_topup", 0.85, "شحن", "top up"),
        ("pay_methods", 0.60, "طرق الدفع", "payment methods"),
    ],
}


@dataclass
class Suggestion:
    feature: str
    label_ar: str
    label_en: str
    confidence: float  # 0..1
    reason: str
    source: str  # pattern|prior|entity|audit|preventive|memory
    kind: str  # build|improve|preventive

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "label_ar": self.label_ar,
            "label_en": self.label_en,
            "confidence": round(self.confidence, 3),
            "reason": self.reason,
            "source": self.source,
            "kind": self.kind,
        }


@dataclass
class SuggestionReport:
    build: list[Suggestion] = field(default_factory=list)
    improve: list[Suggestion] = field(default_factory=list)
    preventive: list[Suggestion] = field(default_factory=list)
    intent: str | None = None
    already: list[str] = field(default_factory=list)
    prompt_ar: str = ""
    prompt_en: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "already": self.already,
            "build": [s.to_dict() for s in self.build],
            "improve": [s.to_dict() for s in self.improve],
            "preventive": [s.to_dict() for s in self.preventive],
            "prompt_ar": self.prompt_ar,
            "prompt_en": self.prompt_en,
        }

    def all_features(self) -> list[str]:
        return [s.feature for s in self.build + self.improve + self.preventive]


def _label(feature: str, intent: str) -> tuple[str, str]:
    for row in _PRIORS.get(intent, []):
        if row[0] == feature:
            return row[2], row[3]
    # generic fallback from feature key
    nice = feature.replace("_", " ")
    return nice, nice


def _blend_stats(
    intent: str,
    already: set[str],
    mem: MemoryEngine | None,
) -> list[Suggestion]:
    """Pattern stats override priors when enough samples exist."""
    out: list[Suggestion] = []
    seen: set[str] = set()
    stats: dict[str, float] = {}
    if mem is not None:
        for feat, p in mem.top_features_for_intent(intent, limit=20):
            stats[feat] = p

    # Start from priors, upgrade with stats
    prior_map = {f: (p, ar, en) for f, p, ar, en in _PRIORS.get(intent, [])}
    keys = list(dict.fromkeys(list(stats.keys()) + list(prior_map.keys())))

    for feat in keys:
        if feat in already or feat in seen:
            continue
        if feat in stats and stats[feat] >= 0.25:
            p = stats[feat]
            ar, en = _label(feat, intent)
            out.append(
                Suggestion(
                    feature=feat,
                    label_ar=ar,
                    label_en=en,
                    confidence=min(0.98, p),
                    reason=f"{int(round(p * 100))}% من بوتات «{intent}» المشابهة تستخدمها",
                    source="pattern",
                    kind="build",
                )
            )
            seen.add(feat)
        elif feat in prior_map:
            p, ar, en = prior_map[feat]
            # lower confidence for pure prior
            out.append(
                Suggestion(
                    feature=feat,
                    label_ar=ar,
                    label_en=en,
                    confidence=min(0.75, p * 0.85),
                    reason=f"شائع مع بوتات {intent} (تقدير أولي حتى تتراكم إحصائياتك)",
                    source="prior",
                    kind="build",
                )
            )
            seen.add(feat)
    out.sort(key=lambda s: -s.confidence)
    return out


def _entity_suggestions(
    intent: str | None,
    lu: LanguageUnderstandingResult | None,
    already: set[str],
) -> list[Suggestion]:
    if not lu:
        return []
    ent = lu.entities
    out: list[Suggestion] = []

    def add(feat: str, ar: str, en: str, why: str, conf: float = 0.9) -> None:
        if feat in already:
            return
        out.append(
            Suggestion(
                feature=feat,
                label_ar=ar,
                label_en=en,
                confidence=conf,
                reason=why,
                source="entity",
                kind="build",
            )
        )

    if intent in {"shop", "marketplace", "restaurant"}:
        pays = set(ent.payment_methods or [])
        if pays & {"vodafone_cash", "fawry", "instapay", "wallet"}:
            add("vodafone_cash", "فودافون كاش / محفظة", "Vodafone Cash / wallet", "ذكرت دفع محفظة/فودافون في طلبك")
            add("pay_methods", "اختيار طريقة الدفع", "payment methods", "طرق دفع متعددة في النص")
        if pays & {"visa", "stripe", "paypal", "telegram_payments"}:
            add("shop_buy", "شراء ببطاقة", "card checkout", "ذكرت فيزا/بطاقة/Stripe")
            add("pay_methods", "اختيار طريقة الدفع", "payment methods", "دفع إلكتروني مذكور")
        if ent.wants_delivery:
            add("shipping_set", "إعداد الشحن", "shipping", "طلبت توصيل")
            add("order_track", "تتبع الطلب", "order tracking", "التوصيل يستفيد من التتبع")
        if ent.wants_discounts:
            add("coupon_apply", "كوبونات", "coupons", "طلبت خصومات/كوبونات")
            add("coupon_create", "إنشاء كوبون", "create coupon", "إدارة الكوبونات للمشرف")
        if ent.wants_reviews:
            add("review_add", "تقييمات", "reviews", "طلبت تقييمات")
        if ent.brand_analogy in {"amazon", "noon", "jumia"}:
            add("product_search", "بحث منتجات", "product search", f"تشبيه بـ {ent.brand_analogy} يحتاج بحث قوي")
            add("wishlist_add", "قائمة أمنيات", "wishlist", f"شائع في تجربة {ent.brand_analogy}")

    if intent == "security" or ent.security_checks:
        checks = set(ent.security_checks or [])
        if "dns" in checks or "mx" in checks or "spf" in checks:
            add("sec_dns_check", "فحص DNS", "DNS check", "فحوصات DNS/MX/SPF مذكورة", 0.95)
        if "tls" in checks:
            add("sec_tls_check", "فحص TLS", "TLS check", "TLS/SSL مذكور", 0.95)
        if "headers" in checks:
            add("sec_headers_check", "Headers", "headers", "Security headers مذكورة", 0.92)
        if "phishing" in checks:
            add("sec_tips", "توعية تصيد", "phishing tips", "توعية التصيد مذكورة", 0.9)
        if ent.target_domain or ent.target_url:
            add("sec_domain_overview", "فحص الدومين", "domain overview", "دومين/رابط مستهدف محدد", 0.93)

    if intent == "education" and (ent.course_topic or "كويز" in (lu.original or "")):
        add("quiz_start", "اختبارات", "quizzes", "كويز/اختبار مذكور في الطلب")
        add("progress_view", "تتبع التقدم", "progress", "مناسب لمنصات التعليم")

    if intent == "iot" and ent.tech_stack:
        add("note_add", "سجل أجهزة", "device log", f"تقنيات: {', '.join(ent.tech_stack)}")

    return out


def _memory_user_suggestions(
    user_id: int | None,
    intent: str | None,
    already: set[str],
    mem: MemoryEngine | None,
) -> list[Suggestion]:
    if user_id is None or mem is None or not intent:
        return []
    out: list[Suggestion] = []
    profile = mem.get_user(int(user_id))
    for feat in profile.preferred_features:
        if feat in already:
            continue
        # only if somewhat related: appears in priors for this intent or previous bots of same intent
        related = feat in {r[0] for r in _PRIORS.get(intent, [])}
        if not related:
            bots = mem.list_bots(int(user_id), limit=10)
            related = any(b.get("intent") == intent and feat in (b.get("features") or []) for b in bots)
        if not related:
            continue
        ar, en = _label(feat, intent)
        out.append(
            Suggestion(
                feature=feat,
                label_ar=ar,
                label_en=en,
                confidence=0.72,
                reason="من تفضيلاتك في بوتات سابقة",
                source="memory",
                kind="build",
            )
        )
    return out[:6]


def _audit_improve(selected: list[str], intent: str | None) -> list[Suggestion]:
    """Post-build improvement suggestions from actual feature set gaps."""
    have = set(selected or [])
    out: list[Suggestion] = []

    def need(feat: str, ar: str, en: str, why: str, conf: float = 0.8) -> None:
        if feat not in have:
            out.append(
                Suggestion(
                    feature=feat, label_ar=ar, label_en=en, confidence=conf, reason=why, source="audit", kind="improve"
                )
            )

    # Universal hygiene
    if "help" not in have and "start" in have:
        need("help", "أمر /help واضح", "clear /help", "البوت فيه أوامر لكن بدون /help صريح", 0.85)
    if intent in {"shop", "marketplace"}:
        if "shop_catalog" in have and "product_search" not in have:
            need("product_search", "بحث منتجات", "product search", "كتالوج بدون بحث — هيتعب مع زيادة المنتجات", 0.78)
        if "shop_buy" in have or "cart_checkout" in have:
            if "pay_methods" not in have:
                need("pay_methods", "طرق الدفع", "payment methods", "فيه شراء لكن بدون قائمة طرق دفع واضحة", 0.8)
            if "order_track" not in have:
                need("order_track", "تتبع الطلب", "order tracking", "بعد الشراء المستخدم يحتاج يتتبع", 0.7)
        if "review_add" not in have and "shop_catalog" in have:
            need("review_add", "تقييمات", "reviews", "التقييمات ترفع الثقة في المتجر", 0.55)
    if intent == "security":
        if "sec_dns_check" in have and "sec_tls_check" not in have:
            need("sec_tls_check", "فحص TLS", "TLS check", "DNS موجود — TLS مكمل طبيعي", 0.75)
        if "sec_tips" not in have:
            need("sec_tips", "توعية أمنية", "awareness tips", "الفحص التقني أقوى مع توعية للمستخدمين", 0.6)
    if intent == "tickets":
        if "ticket_open" in have and "ticket_status" not in have:
            need("ticket_status", "حالة التذكرة", "ticket status", "فتح تذكرة بدون متابعة الحالة", 0.8)
    return out


def _preventive(selected: list[str], intent: str | None, lu: LanguageUnderstandingResult | None) -> list[Suggestion]:
    have = set(selected or [])
    out: list[Suggestion] = []
    qty = None
    if lu and lu.entities and lu.entities.quantity:
        qty = lu.entities.quantity

    if intent in {"shop", "marketplace"}:
        if qty and qty >= 20 and "product_search" not in have:
            out.append(
                Suggestion(
                    feature="product_search",
                    label_ar="بحث منتجات",
                    label_en="product search",
                    confidence=0.9,
                    reason=f"⚠️ ذكرت حوالي {qty} منتج/عنصر — بدون بحث التجربة هتضعف",
                    source="preventive",
                    kind="preventive",
                )
            )
        if "shop_catalog" in have and "cart_view" not in have:
            out.append(
                Suggestion(
                    feature="cart_view",
                    label_ar="سلة",
                    label_en="cart",
                    confidence=0.88,
                    reason="⚠️ كتالوج بدون سلة — معظم المتاجر تحتاج سلة",
                    source="preventive",
                    kind="preventive",
                )
            )
    if intent == "security" and lu and not (lu.entities.target_domain or lu.entities.target_url):
        out.append(
            Suggestion(
                feature="sec_domain_overview",
                label_ar="فحص دومين",
                label_en="domain overview",
                confidence=0.7,
                reason="⚠️ مفيش دومين محدد — المستخدم هيحتاج يمرّر دومين مع كل فحص",
                source="preventive",
                kind="preventive",
            )
        )
    return out


def _format_prompt(report: "SuggestionReport", *, lang: str = "ar") -> tuple[str, str]:
    def block(title_ar: str, title_en: str, items: list[Suggestion]) -> tuple[str, str]:
        if not items:
            return "", ""
        ar_lines = [title_ar]
        en_lines = [title_en]
        for s in items[:6]:
            pct = int(round(s.confidence * 100))
            ar_lines.append(f"  • {s.label_ar} — {s.reason} ({pct}%)")
            en_lines.append(f"  • {s.label_en} — {s.reason} ({pct}%)")
        ar_lines.append("  عايز أضيف أي منهم؟")
        en_lines.append("  Add any of these?")
        return "\n".join(ar_lines), "\n".join(en_lines)

    ar_parts, en_parts = [], []
    a, e = block("💡 اقتراحات أثناء البناء:", "💡 Build suggestions:", report.build)
    if a:
        ar_parts.append(a)
        en_parts.append(e)
    a, e = block("💡 تحسينات بعد التوليد:", "💡 Post-build improvements:", report.improve)
    if a:
        ar_parts.append(a)
        en_parts.append(e)
    a, e = block("⚠️ تنبيهات وقائية:", "⚠️ Preventive tips:", report.preventive)
    if a:
        ar_parts.append(a)
        en_parts.append(e)
    return "\n\n".join(ar_parts), "\n\n".join(en_parts)


def suggest(
    text: str = "",
    *,
    intent: IntentAnalysis | None = None,
    lu: LanguageUnderstandingResult | None = None,
    selected_features: list[str] | None = None,
    user_id: int | None = None,
    memory: MemoryEngine | None = None,
    limit: int = 6,
) -> SuggestionReport:
    """Compute dynamic suggestions for this bot request / build."""
    if lu is None and text:
        lu = understand(text)
    if intent is None and text:
        intent = analyze_intent(text, lu=lu)

    primary = intent.primary.intent if intent and intent.primary else (lu.primary_domain if lu else None)
    already = set(selected_features or [])
    if intent and intent.feature_plan:
        already |= set(intent.feature_plan)

    mem = memory
    if mem is None and user_id is not None:
        try:
            mem = get_memory_engine()
        except Exception:
            mem = None

    build: list[Suggestion] = []
    if primary:
        build.extend(_entity_suggestions(primary, lu, already))
        build.extend(_memory_user_suggestions(user_id, primary, already, mem))
        build.extend(_blend_stats(primary, already, mem))

    # de-dupe build by feature keeping highest confidence
    bag: dict[str, Suggestion] = {}
    for s in build:
        if s.feature in already:
            continue
        prev = bag.get(s.feature)
        if not prev or s.confidence > prev.confidence:
            bag[s.feature] = s
    build = sorted(bag.values(), key=lambda s: -s.confidence)[:limit]

    selected = list(selected_features or (intent.feature_plan if intent else []) or [])
    improve = _audit_improve(selected, primary)[:limit]
    preventive = _preventive(selected, primary, lu)[:limit]

    report = SuggestionReport(
        build=build,
        improve=improve,
        preventive=preventive,
        intent=primary,
        already=sorted(already),
    )
    lang = intent.language if intent else "ar"
    report.prompt_ar, report.prompt_en = _format_prompt(report, lang=lang)
    return report


def suggest_for_spec_features(
    features: list[str],
    *,
    intent: str | None = None,
    text: str = "",
    user_id: int | None = None,
) -> SuggestionReport:
    """Post-generation entry: audit a concrete feature list."""
    lu = understand(text) if text else None
    ia = analyze_intent(text, lu=lu) if text else None
    if ia and intent and not ia.primary:
        pass
    return suggest(
        text,
        intent=ia,
        lu=lu,
        selected_features=features,
        user_id=user_id,
        limit=8,
    )


__all__ = [
    "Suggestion",
    "SuggestionReport",
    "suggest",
    "suggest_for_spec_features",
]
