"""Zero-AI presets: map plain-language requests to BotSpec packs.

Used when the user asks for a common bot type (e.g. group management)
without going through the button builder or any LLM.
"""
from __future__ import annotations

import re
from typing import Iterable

from .acceptance_packs import tests_for_preset
from .builder import BuilderSession
from .schema import BotSpec
from .seed_packs import seed_for_preset


def _pack_from_prefixes(
    prefixes: tuple[str, ...],
    *,
    limit: int = 64,
    extra: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Real registry keys for a domain (prefix_action) — not phantom labels."""
    from .registry import CAPABILITIES

    out: list[str] = ["start", "help"]
    for e in extra:
        if e in CAPABILITIES or e in {"start", "help", "lang"}:
            out.append(e)
    prefer = (
        "list", "view", "create", "search", "status", "stats", "track", "history",
        "approve", "assign", "checkout", "buy", "sell", "ship", "deliver", "pay",
        "transfer", "refund", "subscribe", "renew", "upgrade", "start_trial",
        "dashboard", "balance", "invoice", "payout", "bid", "catalog",
    )
    for action in prefer:
        for pref in prefixes:
            key = f"{pref}_{action}"
            if key in CAPABILITIES and key not in out:
                out.append(key)
                if len(out) >= limit:
                    return tuple(dict.fromkeys(out))
    for pref in prefixes:
        for key in CAPABILITIES:
            if key.startswith(pref + "_") and key not in out:
                out.append(key)
                if len(out) >= limit:
                    return tuple(dict.fromkeys(out))
    out.append("lang")
    return tuple(dict.fromkeys(out))



def _request_intensity(request: str, presets: list[str] | None = None) -> str:
    """simple | medium | complex — drives pack size caps."""
    presets = list(presets or [])
    t = _norm(request or "")
    complex_domains = {"saas", "marketplace", "logistics", "finance", "commerce_pro"}
    n_complex = sum(1 for d in presets if d in complex_domains)
    enterprise = any(
        k in t
        for k in (
            "enterprise", "all-in-one", "all in one", "منصة", "suite", "operating system",
            "متكامل", "شامل", "ضخم", "multi-tenant", "multi vendor", "multi-vendor",
            "globally", "production grade", "6 month", "شهر", "platform",
        )
    )
    rich = len(t) > 180 or t.count(",") + t.count("،") >= 4 or t.count("+") >= 2
    if n_complex >= 2 or (enterprise and n_complex >= 1) or (enterprise and rich):
        return "complex"
    if n_complex == 1 or any(
        d in presets
        for d in ("shop", "crm", "education", "wallet", "subscriptions", "growth", "creator")
    ):
        # single domain / shop-scale → medium unless ultra-short simple phrase
        if len(t) < 28 and n_complex == 0:
            return "simple"
        return "medium"
    return "simple"


def _pack_limit_for(intensity: str, *, primary: bool) -> int:
    if intensity == "complex":
        return 72 if primary else 48
    if intensity == "medium":
        return 28 if primary else 12
    return 8 if primary else 0


# keyword packs (Arabic + English), lowercase match
_GROUP_KEYS = (
    "اداره مجموعات",
    "إدارة مجموعات",
    "ادارة مجموعات",
    "إدارة جروب",
    "ادارة جروب",
    "إدارة مجموعة",
    "مشرف",
    "moderation",
    "group management",
    "group admin",
    "admin bot",
    "حظر",
    "كتم",
    "طرد",
    "ترحيب",
)
_TASK_KEYS = (
    "مهام",
    "task",
    "todo",
    "to-do",
)
_SUPPORT_KEYS = (
    "تذاكر",
    "دعم",
    "support",
    "ticket",
    "helpdesk",
)
_NOTES_KEYS = (
    "ملاحظات",
    "notes",
)
_SHOP_KEYS = (
    "متجر", "shop", "store", "منتجات", "ecommerce", "مدفوعات", "دفع",
    "payment", "payments", "invoice", "شراء", "سلة", "cart", "كوبون",
    "coupon", "refund", "أمنيات", "wishlist", "order", "تبرع", "donation",
    "خيرية", "صيدلية", "pharmacy",
)
_SUB_KEYS = (
    "اشتراك", "اشتراكات", "عضوية", "subscription", "subscribe", "vip",
    "monthly", "plan", "plans",
)
_POINTS_KEYS = (
    "نقاط", "رصيد", "points", "coins", "xp", "leaderboard", "لوحة متصدرين",
    "ولاء", "loyalty",
)
_CONTEST_KEYS = (
    "مسابقة", "مسابقات", "contest", "giveaway", "raffle", "سحب", "tournament",
)
_I18N_KEYS = (
    "ترجمة", "واجهة", "i18n", "multi-language", "multilingual", "global",
    "عالمي", "bilingual", "عربي انجليزي",
)
_BOOK_KEYS = ("حجز", "booking", "موعد", "appointment")
_HR_KEYS = ("موارد بشرية", "hr", "إجازة", "حضور", "checkin")
_SECURITY_KEYS = (
    "امن", "أمن", "سيبراني", "security", "cyber", "phishing", "تصيد", "تصيّد",
    "بلاغ", "incident", "soc", "توعية",
)

_GROUP_CAPS = (
    "start",
    "help",
    "rules",
    "announce",
    "user_ban",
    "user_unban",
    "user_mute",
    "user_unmute",
    "user_kick",
    "user_warn",
    "user_promote",
    "user_demote",
    "pin_message",
    "delete_message",
    "welcome_set",
    "welcome_toggle",
    "welcome_show",
    "welcome_test",
    "my_id",
)
_TASK_CAPS = ("start", "help", "task_add", "task_list", "task_done", "task_delete", "task_clear")
_SUPPORT_CAPS = (
    "start",
    "help",
    "ticket_open",
    "ticket_my",
    "ticket_list",
    "ticket_reply",
    "ticket_close",
    "ticket_status",
)
_NOTES_CAPS = ("start", "help", "note_add", "note_list", "note_delete")
_SECURITY_CAPS = (
    "start", "help", "sec_report_phish", "sec_report_incident",
    "sec_checklist", "sec_list_reports", "sec_close_report", "rules", "my_id",
)
_SHOP_CAPS = (
    "start", "help", "shop_catalog", "shop_add_item", "shop_buy", "shop_orders",
    "shop_my_orders", "cart_add", "cart_view", "cart_checkout", "product_search",
    "product_info", "coupon_apply", "wishlist_add", "wishlist_view", "review_add",
    "shipping_set", "digital_deliver", "coupon_apply", "coupon_create",
    "order_track", "order_cancel", "lang", "privacy_policy", "terms_of_service",
)
_SUB_CAPS = (
    "start", "help", "plans", "subscribe", "my_sub", "grant_sub", "revoke_sub",
    "lang", "referral_code", "daily_checkin",
)
_POINTS_CAPS = (
    "start", "help", "balance", "leaderboard", "grant_points", "points_history",
    "redeem_points", "daily_checkin", "streak_status", "achievement_list", "lang",
)
_CONTEST_CAPS = (
    "start", "help", "contests", "join_contest", "my_entries",
    "new_contest", "end_contest", "draw_winner", "lang", "referral_invite",
)
_GROWTH_CAPS = (
    "start", "help", "referral_code", "referral_invite", "referral_stats",
    "referral_claim", "referral_rewards", "daily_checkin", "streak_status",
    "achievement_list", "lang",
)
_CRM_CAPS = (
    "start", "help", "lead_capture", "lead_list", "lead_status", "pipeline_board",
    "deal_create", "customer_profile", "followup_set", "lang",
)
_SUPPORT_PRO_CAPS = (
    "start", "help", "ticket_open", "ticket_my", "ticket_list", "ticket_reply",
    "ticket_close", "ticket_status", "ticket_priority", "ticket_assign",
    "kb_search", "kb_article", "csat_rate", "lang",
)
_EDU_CAPS = (
    "start", "help", "course_list", "course_enroll", "lesson_list", "lesson_open",
    "progress_view", "quiz_start", "quiz_score", "homework_submit",
    "certificate_issue", "lang",
)
_RESTAURANT_CAPS = (
    "start", "help", "menu_view", "menu_order", "order_status", "table_book", "lang",
)
_JOBS_CAPS = (
    "start", "help", "job_list", "job_apply", "job_my_apps", "job_post", "lang",
)
_MARKETPLACE_CAPS = (
    "start", "help", "listing_create", "listing_search", "listing_contact",
    "listing_mine", "lang",
)
_SAAS_CAPS = (
    "start", "help", "plans", "subscribe", "my_sub", "analytics_overview",
    "analytics_users", "analytics_revenue", "admin_users", "webhook_set",
    "data_export_me", "data_delete_me", "privacy_policy", "terms_of_service",
    "lang", "maintenance_mode",
)


def _saas_pack(*, limit: int = 72) -> tuple[str, ...]:
    return _pack_from_prefixes(
        (
            "saas", "seat", "plan3", "billing2", "meter", "quota", "subscription2",
            "trial2", "addon2", "workspace2", "org", "team2", "rbac", "flag2",
            "webhook3", "apikey", "oauth2",
        ),
        limit=limit,
        extra=_SAAS_CAPS,
    )


def _marketplace_pack(*, limit: int = 72) -> tuple[str, ...]:
    return _pack_from_prefixes(
        (
            "mkt", "listing2", "vendor2", "buyer", "offer2", "bid2", "escrow",
            "payout2", "commission2", "catalog2", "storefront", "auction3",
            "rfq2", "quote2", "dispute3", "review3",
        ),
        limit=limit,
        extra=_MARKETPLACE_CAPS,
    )


def _logistics_pack(*, limit: int = 72) -> tuple[str, ...]:
    return _pack_from_prefixes(
        (
            "logi", "ship4", "fleet2", "route3", "hub2", "dock2", "warehouse4",
            "courier2", "manifest", "lane", "container", "lastmile", "pod2",
            "eta2", "load2", "trip",
        ),
        limit=limit,
        extra=("start", "help", "order_track", "order_status", "lang"),
    )


def _finance_pack(*, limit: int = 72) -> tuple[str, ...]:
    return _pack_from_prefixes(
        (
            "fin", "ledger2", "journal", "payout3", "settle2", "recon", "treasury",
            "fx", "card3", "wallet3", "loan2", "credit2", "limit2", "kyc2", "aml2",
            "invoice4", "receivable", "payable", "tax3", "fee2",
        ),
        limit=limit,
        extra=("start", "help", "wallet_balance", "wallet_topup", "lang"),
    )

_COMMUNITY_CAPS = (
    "start", "help", "profile_set", "profile_view", "feed_view", "post_create",
    "post_like", "report_content", "mod_queue", "lang",
)
_EVENTS_CAPS = (
    "start", "help", "event_list", "event_rsvp", "event_create", "event_attendees", "lang",
)
_WALLET_CAPS = (
    "start", "help", "wallet_balance", "wallet_topup", "wallet_transfer",
    "wallet_history", "lang",
)
# Creator monetization (digital content + tips + membership gate)
_CREATOR_CAPS = (
    "start", "help", "content_list", "content_unlock", "content_upload",
    "tip_creator", "membership_gate", "plans", "subscribe", "my_sub",
    "shop_buy", "referral_invite", "lang", "privacy_policy", "terms_of_service",
)
# All-in-one commerce pro — densest market pack for launch day
_COMMERCE_PRO_CAPS = tuple(dict.fromkeys(
    list(_SHOP_CAPS)
    + list(_SUB_CAPS)
    + list(_POINTS_CAPS)
    + list(_GROWTH_CAPS)
    + list(_WALLET_CAPS)
    + [
        "payment_precheckout", "payment_success", "analytics_overview",
        "analytics_revenue", "admin_users", "coupon_create", "refund_request",
        "refund_approve", "stock_set", "broadcast_segment",
    ]
))

_CREATOR_KEYS = (
    "منشئ", "creator", "محتوى مدفوع", "paid content", "إكرامية", "tip",
    "عضوية محتوى", "fan", "patreon",
)
_COMMERCE_PRO_KEYS = (
    "متجر متكامل", "commerce pro", "all-in-one shop", "متجر احترافي",
    "full ecommerce", "متجر شامل", "commerce suite",
)

_GROWTH_KEYS = (
    "إحالة", "احالة", "إحالات", "احالات", "referral", "referrals", "invite", "دعوة",
    "check-in", "checkin", "daily reward", "نمو", "growth", "affiliate",
)
_CRM_KEYS = (
    "crm", "مبيعات", "sales", "pipeline", "عملاء محتملين", "leads", "صفقة",
)
_EDU_KEYS = (
    "دورة", "كورس", "course", "تعليم", "education", "درس", "اختبار", "quiz",
    "شهادة", "certificate",
)
_RESTAURANT_KEYS = (
    "مطعم", "restaurant", "قائمة طعام", "menu", "طلب طعام", "food order",
    "طاولة",
)
_JOBS_KEYS = ("وظيفة", "وظائف", "job", "jobs", "توظيف", "hiring", "career")
_MARKETPLACE_KEYS = (
    "سوق", "إعلان", "اعلان", "marketplace", "classified", "بيع وشراء",
    "بائعين", "vendors", "vendor", "متعدد البائعين", "multi-vendor",
    "escrow", "ضمان", "مزايدة", "storefront", "عمولة", "commission",
    "سوق إلكتروني", "classifieds",
)
_SAAS_KEYS = (
    "saas", "ساس", "لوحة تحكم", "analytics", "تحليلات", "webhook", "api token",
    "اشتراك برمجي", "مقعد", "seats", "seat", "tenant", "مستأجر", "workspace",
    "مساحة عمل", "rbac", "صلاحيات", "feature flag", "sso", "تجربة مجانية",
    "trial", "quota", "حصة استخدام", "b2b", "اشتراك برمجيات",
)
_LOGISTICS_KEYS = (
    "لوجستيات", "logistics", "شحن", "shipping", "أسطول", "fleet", "مندوب",
    "courier", "مستودع", "warehouse", "تتبع شحنة", "tracking",
    "توصيل", "delivery network", "بيان شحن", "manifest", "حاوية", "container",
    "مسار توصيل", "route planning", "إثبات تسليم", "pod",
)
_FINANCE_KEYS = (
    "مالية", "finance", "محاسبة", "accounting", "دفتر", "ledger", "خزينة",
    "treasury", "تسوية", "settlement", "مطابقة", "reconciliation", "ذمم",
    "kyc", "aml", "قرض", "loan", "ائتمان", "credit", "فاتورة مالية",
    "receivable", "payable", "fx", "صرف عملات", "رسوم", "fees",
)
_COMMUNITY_KEYS = (
    "مجتمع", "community", "سوشيال", "social feed", "منشورات",
)
_EVENTS_KEYS = ("فعالية", "فعاليات", "event", "events", "rsvp", "مؤتمر")
_WALLET_KEYS = ("محفظة", "wallet", "credits", "رصيد محفظة", "شحن رصيد")
_SUPPORT_PRO_KEYS = ("دعم فني", "knowledge base", "قاعدة معرفة", "csat", "sla")



_FITNESS_CAPS = (
    "start", "help", "gym_book", "gym_schedule", "gym_checkin", "gym_membership",
    "plans", "subscribe", "my_sub", "lang",
)
_REALESTATE_CAPS = (
    "start", "help", "property_list", "property_search", "property_inquiry",
    "property_add", "lang",
)
_CLINIC_CAPS = (
    "start", "help", "clinic_book", "clinic_slots", "clinic_cancel", "clinic_my", "lang",
)
_AUCTION_CAPS = (
    "start", "help", "auction_list", "auction_bid", "auction_create", "auction_my_bids", "lang",
)
_DELIVERY_CAPS = (
    "start", "help", "delivery_track", "delivery_status", "delivery_create", "lang",
)

_FITNESS_KEYS = (
    "جيم", "صالة", "fitness", "gym", "workout", "حصة رياضية", "نادي رياضي",
)
_REALESTATE_KEYS = (
    "عقار", "عقارات", "real estate", "realestate", "property", "شقة", "فيلا",
)
_CLINIC_KEYS = (
    "عيادة", "clinic", "طبيب", "doctor", "موعد طبي", "مستشفى",
)
_AUCTION_KEYS = ("مزاد", "مزادات", "auction", "bid", "مزايدة")
_DELIVERY_KEYS = ("شحنة", "تتبع شحنة", "delivery", "shipping track", "لوجستيك")

def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _has_any(text: str, keys: Iterable[str]) -> bool:
    t = _norm(text)
    return any(k in t for k in keys)



def _token_hit(t: str, k: str) -> bool:
    k = (k or "").strip().lower()
    if not k or k not in t:
        return False
    if len(k) <= 3:
        idx = 0
        while True:
            i = t.find(k, idx)
            if i < 0:
                return False
            before = t[i - 1] if i > 0 else " "
            after = t[i + len(k)] if i + len(k) < len(t) else " "
            def _wc(ch: str) -> bool:
                return ch.isalnum() or ("\u0600" <= ch <= "\u06FF")
            if not _wc(before) and not _wc(after):
                return True
            idx = i + 1
        return False
    return True


def _score_keys(text: str, keys: Iterable[str], weight: float = 1.0) -> float:
    t = _norm(text)
    matched = [k for k in keys if _token_hit(t, k)]
    if not matched:
        return 0.0
    best = max(len(k) for k in matched)
    return len(matched) * weight + min(best, 24) * 0.02


def score_presets(request: str) -> list[tuple[str, float]]:
    """Rank preset intents by keyword evidence (multi-intent aware)."""
    scores: dict[str, float] = {}

    def add(name: str, keys: Iterable[str], weight: float = 1.0) -> None:
        s = _score_keys(request, keys, weight)
        if s > 0:
            scores[name] = scores.get(name, 0.0) + s

    # Higher weights for explicit product packs
    add("commerce_pro", _COMMERCE_PRO_KEYS, 3.0)
    add("creator", _CREATOR_KEYS, 2.2)
    add("saas", _SAAS_KEYS, 2.4)
    add("marketplace", _MARKETPLACE_KEYS, 2.3)
    add("logistics", _LOGISTICS_KEYS, 2.3)
    add("finance", _FINANCE_KEYS, 2.2)
    add("restaurant", _RESTAURANT_KEYS, 2.0)
    add("jobs", _JOBS_KEYS, 1.8)
    add("education", _EDU_KEYS, 1.8)
    add("events", _EVENTS_KEYS, 1.6)
    add("wallet", _WALLET_KEYS, 1.6)
    add("growth", _GROWTH_KEYS, 1.6)
    add("crm", _CRM_KEYS, 1.6)
    add("community", _COMMUNITY_KEYS, 1.5)
    add("contests", _CONTEST_KEYS, 1.5)
    add("subscriptions", _SUB_KEYS, 1.5)
    add("points", _POINTS_KEYS, 1.4)
    add("shop", _SHOP_KEYS, 1.4)
    add("support_pro", _SUPPORT_PRO_KEYS, 1.5)
    add("group_management", _GROUP_KEYS, 1.2)
    add("support_tickets", _SUPPORT_KEYS, 1.2)
    add("tasks", _TASK_KEYS, 1.0)
    add("notes", _NOTES_KEYS, 1.0)
    add("security_ops", _SECURITY_KEYS, 1.3)
    add("booking", _BOOK_KEYS, 1.3)
    add("hr", _HR_KEYS, 1.2)
    add("fitness", _FITNESS_KEYS, 1.9)
    add("realestate", _REALESTATE_KEYS, 1.9)
    add("clinic", _CLINIC_KEYS, 1.9)
    add("auction", _AUCTION_KEYS, 1.7)
    add("delivery", _DELIVERY_KEYS, 1.6)

    # Smart boosts: multi-commerce signals → commerce_pro only if shop/payments present
    commerce_hits = sum(
        1
        for pack in ("shop", "subscriptions", "points", "wallet", "growth")
        if scores.get(pack, 0) > 0
    )
    if scores.get("shop", 0) > 0 and commerce_hits >= 2:
        scores["commerce_pro"] = scores.get("commerce_pro", 0) + 2.5 * commerce_hits
    elif commerce_hits >= 3 and scores.get("subscriptions", 0) > 0:
        scores["commerce_pro"] = scores.get("commerce_pro", 0) + 2.0 * commerce_hits
    if _has_any(request, _I18N_KEYS) and scores:
        # Soft preference for market packs when global is requested
        for name in ("commerce_pro", "shop", "subscriptions", "saas", "creator"):
            if name in scores:
                scores[name] += 0.8

    ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    return ranked


def detect_preset(request: str) -> str | None:
    """Return best preset id or None (uses ranked multi-intent scoring)."""
    ranked = score_presets(request)
    if not ranked:
        return None
    return ranked[0][0]


def _request_signals(request: str) -> dict[str, float]:
    """Fine-grained intent signals for conflict resolution (not just pack scores)."""
    t = _norm(request)
    def n(keys: Iterable[str]) -> float:
        return float(sum(1 for k in keys if _token_hit(t, k)))

    return {
        "vendor": n(("vendor", "vendors", "بائع", "بائعين", "multi-vendor", "متعدد البائعين", "storefront")),
        "escrow": n(("escrow", "ضمان", "ضمانة")),
        "cart": n(("سلة", "cart", "checkout", "إتمام شراء")),
        "catalog": n(("كتالوج", "catalog", "متجر", "shop", "منتجات")),
        "fleet": n(("أسطول", "fleet", "مندوب", "courier", "مستودع", "warehouse", "hub")),
        "track_only": n(("تتبع", "track", "tracking", "شحنة")),
        "ledger": n(("ledger", "دفتر", "محاسبة", "accounting", "kyc", "aml", "خزينة", "treasury")),
        "wallet_only": n(("محفظة", "wallet", "شحن رصيد", "topup", "top-up")),
        "seats": n(("مقعد", "seats", "seat", "tenant", "workspace", "rbac", "sso", "quota")),
        "trial": n(("trial", "تجربة مجانية", "تجربة")),
        "commerce_explicit": n(("commerce pro", "متجر متكامل", "متجر احترافي", "full ecommerce", "commerce suite")),
        "platform": n(("منصة", "platform", "operating system", "suite", "enterprise", "متكامل", "شامل")),
        "saas_word": n(("saas", "ساس", "b2b")),
        "logistics_word": n(("لوجستيات", "logistics", "last mile", "lastmile", "manifest",
                            "shipment", "shipments", "pod", "warehouse", "مستودع", "شحنة", "شحنات")),
        "finance_word": n(("مالية", "finance", "محاسبة", "accounting")),
        "marketplace_word": n(("marketplace", "سوق", "classified", "سوق إلكتروني")),
    }


def prioritize_preset_stack(
    ranked: list[tuple[str, float]],
    request: str,
    *,
    limit: int = 6,
) -> list[str]:
    """Terrifyingly smart merge priority for overlapping domains.

    Rules (highest impact first):
    1) Explicit commerce_pro phrase wins pure shop-suite primary.
    2) Marketplace beats shop when vendor/escrow/multi-vendor signals exist.
    3) Logistics beats thin delivery when fleet/warehouse/route signals exist.
    4) Finance beats wallet when ledger/KYC/accounting signals exist.
    5) SaaS beats bare subscriptions when seats/trial/tenant/RBAC signals exist.
    6) Never inject commerce_pro into pure SaaS / pure logistics / pure finance.
    7) Secondary domains keep order by *adjusted* score, not raw keyword count only.
    """
    if not ranked:
        return []

    sig = _request_signals(request)
    scores = {n: float(s) for n, s in ranked}

    # Specificity bonuses / penalties
    if sig["vendor"] or sig["escrow"] or sig["marketplace_word"]:
        scores["marketplace"] = scores.get("marketplace", 0.0) + 4.0 + 1.5 * sig["vendor"] + 2.0 * sig["escrow"]
        scores["shop"] = scores.get("shop", 0.0) - 2.5
        if not sig["commerce_explicit"]:
            scores["commerce_pro"] = scores.get("commerce_pro", 0.0) - 1.5

    if sig["fleet"] or sig["logistics_word"]:
        scores["logistics"] = scores.get("logistics", 0.0) + 4.0 + 1.2 * sig["fleet"]
        scores["delivery"] = scores.get("delivery", 0.0) - 2.0

    if sig["ledger"] or sig["finance_word"]:
        scores["finance"] = scores.get("finance", 0.0) + 4.0 + 1.2 * sig["ledger"]
        scores["wallet"] = scores.get("wallet", 0.0) - 1.5

    if sig["seats"] or sig["trial"] or sig["saas_word"]:
        scores["saas"] = scores.get("saas", 0.0) + 4.0 + 1.2 * sig["seats"] + 1.0 * sig["trial"]
        scores["subscriptions"] = scores.get("subscriptions", 0.0) - 1.2

    if sig["commerce_explicit"]:
        scores["commerce_pro"] = scores.get("commerce_pro", 0.0) + 6.0

    if sig["cart"] and not (sig["vendor"] or sig["escrow"]):
        scores["shop"] = scores.get("shop", 0.0) + 3.5
        # bare shop/cart — do NOT escalate to commerce_pro unless explicit
        if not sig["commerce_explicit"]:
            scores["commerce_pro"] = scores.get("commerce_pro", 0.0) - 3.0

    # Wallet top-up phrasing often contains "شحن" — do not treat as logistics
    # Keep logistics when shipment/POD/track signals exist (6-month potato platforms)
    if (
        sig["wallet_only"]
        and not sig["logistics_word"]
        and not sig["fleet"]
        and not sig.get("track_only")
    ):
        scores["logistics"] = scores.get("logistics", 0.0) - 5.0
        scores["delivery"] = scores.get("delivery", 0.0) - 3.0
        scores["wallet"] = scores.get("wallet", 0.0) + 3.0

    # Platform multi-domain: boost co-mentioned complex systems
    if sig["platform"]:
        for d in ("saas", "marketplace", "logistics", "finance"):
            if scores.get(d, 0) > 0:
                scores[d] += 1.5

    # Order-of-mention: earlier domain keyword in the request wins ties
    tnorm = _norm(request)
    mention_pos: dict[str, int] = {}
    markers = {
        "saas": ("saas", "ساس", "workspace", "مقعد", "seats"),
        "marketplace": ("marketplace", "سوق", "escrow", "multi-vendor", "بائعين"),
        "logistics": ("logistics", "لوجستيات", "أسطول", "fleet", "مستودع"),
        "finance": ("finance", "مالية", "ledger", "محاسبة", "kyc"),
        "commerce_pro": ("commerce pro", "متجر متكامل", "commerce suite"),
        "shop": ("سلة", "cart", "كتالوج", "catalog", "متجر"),
        "wallet": ("محفظة", "wallet"),
    }
    for dom, words in markers.items():
        positions = [tnorm.find(w) for w in words if w in tnorm]
        positions = [x for x in positions if x >= 0]
        if positions:
            mention_pos[dom] = min(positions)
            # slight bonus for appearing early
            scores[dom] = scores.get(dom, 0.0) + max(0.0, 2.0 - (mention_pos[dom] / 40.0))

    # Drop noise domains with non-positive adjusted score
    # Tie-break: higher score, then earlier mention, then name
    def _sort_key(item: tuple[str, float]) -> tuple:
        name, sc = item
        pos = mention_pos.get(name, 10_000)
        return (-sc, pos, name)

    ordered = sorted(scores.items(), key=_sort_key)
    out = [n for n, s in ordered if s > 0]

    primary = out[0] if out else None

    # Conflict pruning
    pure_complex = primary in {"saas", "logistics", "finance", "marketplace"}
    if pure_complex and not sig["commerce_explicit"]:
        # keep commerce_pro only if strong residual shop suite signal without marketplace primary
        if primary != "marketplace":
            out = [x for x in out if x != "commerce_pro"]
        if primary == "marketplace":
            out = [x for x in out if x not in {"shop"}]
        if primary == "logistics":
            out = [x for x in out if x != "delivery"]
        if primary == "finance":
            out = [x for x in out if x != "wallet"] or out
            out = [x for x in out if x != "wallet"]
        if primary == "saas":
            out = [x for x in out if x != "subscriptions"]

    if primary == "shop" and not sig["commerce_explicit"]:
        out = [x for x in out if x != "commerce_pro"]

    if "commerce_pro" in out:
        out = [x for x in out if x not in {"shop", "subscriptions", "points", "growth"} or x == "commerce_pro"]

    # Protect high-signal complex domains before soft backbone / cap
    complex_domains = ("saas", "marketplace", "logistics", "finance", "commerce_pro")
    hard = [x for x in out if x in complex_domains and scores.get(x, 0) >= 3.0]
    soft = [x for x in out if x not in hard]

    multi_complex = len(hard)
    if multi_complex >= 2 or (sig.get("platform") and multi_complex >= 1):
        for b in ("support_pro", "crm"):
            if b not in soft and b not in hard:
                soft.append(b)
    elif primary in {"group_management", "support_tickets", "tasks"}:
        pass
    else:
        soft = [x for x in soft if x not in {"education", "community", "events"} or scores.get(x, 0) >= 3.0]

    # Hard complex domains first (preserve 6-month potatoes), then soft
    merged = list(dict.fromkeys(hard + soft))
    cap = max(1, min(limit, 8))
    # Never drop a hard domain for backbone if we still have room pressure
    if len(hard) >= cap:
        return hard[:cap]
    return merged[:cap]


def detect_preset_stack(request: str, *, limit: int = 8) -> list[str]:
    """Multi-domain stack with smart merge priority (conflict-aware)."""
    ranked = score_presets(request)
    return prioritize_preset_stack(ranked, request, limit=limit)



def compose_session(
    presets: list[str],
    *,
    user_id: int = 0,
    bot_name: str = "",
    request: str = "",
) -> BuilderSession:
    """Merge multiple preset capability sets into one intelligent session."""
    if not presets:
        return session_for_preset("group_management", user_id=user_id, bot_name=bot_name)

    primary = presets[0]
    s = session_for_preset(primary, user_id=user_id, bot_name=bot_name)
    for extra in presets[1:]:
        other = session_for_preset(extra, user_id=user_id)
        s.selected |= other.selected

    # Intensity-aware domain packs: medium bots get a hard ceiling
    names = list(presets)
    primary = names[0] if names else ""
    secondary = set(names[1:])
    intensity = _request_intensity(request, names)

    def _take(pack: tuple[str, ...], n: int) -> list[str]:
        core = ["start", "help", "lang"]
        body = [x for x in pack if x not in core]
        return list(dict.fromkeys(core + body[: max(0, n - len(core))]))

    # Strip prior fat domain keys from session_for_preset so intensity can re-apply
    _dom_prefixes = (
        "saas_", "seat_", "plan3_", "billing2_", "meter_", "quota_", "subscription2_",
        "trial2_", "addon2_", "workspace2_", "org_", "team2_", "rbac_", "flag2_",
        "webhook3_", "apikey_", "oauth2_",
        "mkt_", "listing2_", "vendor2_", "buyer_", "offer2_", "bid2_", "escrow_",
        "payout2_", "commission2_", "catalog2_", "storefront_", "auction3_",
        "rfq2_", "quote2_", "dispute3_", "review3_",
        "logi_", "ship4_", "fleet2_", "route3_", "hub2_", "dock2_", "warehouse4_",
        "courier2_", "manifest_", "lane_", "container_", "lastmile_", "pod2_",
        "eta2_", "load2_", "trip_",
        "fin_", "ledger2_", "journal_", "payout3_", "settle2_", "recon_", "treasury_",
        "fx_", "card3_", "wallet3_", "loan2_", "credit2_", "limit2_", "kyc2_", "aml2_",
        "invoice4_", "receivable_", "payable_", "tax3_", "fee2_",
    )
    if intensity in {"medium", "simple"} and any(
        d in names for d in ("saas", "marketplace", "logistics", "finance")
    ):
        s.selected = {
            x for x in s.selected
            if not any(x.startswith(pref) for pref in _dom_prefixes)
        }

    def _apply_domain(name: str, builder) -> None:
        if name not in names:
            return
        is_primary = primary == name
        lim = _pack_limit_for(intensity, primary=is_primary)
        if lim <= 0:
            return
        s.selected.update(builder(limit=lim))

    _apply_domain("saas", _saas_pack)
    _apply_domain("marketplace", _marketplace_pack)
    _apply_domain("logistics", _logistics_pack)
    _apply_domain("finance", _finance_pack)

    if primary == "commerce_pro":
        if intensity == "complex":
            s.selected.update(_COMMERCE_PRO_CAPS)
        else:
            s.selected.update(_take(_COMMERCE_PRO_CAPS, 36))
    elif "commerce_pro" in secondary:
        s.selected.update(_take(_COMMERCE_PRO_CAPS, 24 if intensity != "complex" else 40))
    elif primary == "shop" or "shop" in secondary:
        s.selected.update(_SHOP_CAPS)

    # Hard ceiling for medium bots (keep complex potatoes uncapped)
    if intensity == "medium" and len(s.selected) > 40:
        # Prefer primary domain + core commands
        core = {"start", "help", "lang"}
        primary_prefs = {
            "saas": ("saas_", "seat_", "plan3_", "quota_", "trial2_"),
            "marketplace": ("mkt_", "listing2_", "vendor2_", "escrow_", "payout2_"),
            "logistics": ("logi_", "ship4_", "fleet2_", "pod2_", "warehouse4_"),
            "finance": ("fin_", "ledger2_", "kyc2_", "invoice4_", "wallet3_"),
            "commerce_pro": ("shop_", "cart_", "coupon_", "wallet_", "sub"),
            "shop": ("shop_", "cart_"),
        }.get(primary, ())
        kept = [x for x in s.selected if x in core]
        rest = [x for x in s.selected if x not in core]
        rest_pri = [x for x in rest if any(x.startswith(p) for p in primary_prefs)]
        rest_other = [x for x in rest if x not in rest_pri]
        ordered = list(dict.fromkeys(kept + rest_pri + rest_other))
        s.selected = set(ordered[:40])

    # Primary-aware bot identity (name + description)
    _identity = {
        "saas": ("saas_platform_bot", "SaaS platform: seats, trials, quotas, RBAC, billing"),
        "marketplace": ("marketplace_platform_bot", "Marketplace: vendors, escrow, listings, payouts"),
        "logistics": ("logistics_platform_bot", "Logistics: fleet, warehouses, routes, POD tracking"),
        "finance": ("finance_ops_bot", "Finance ops: ledger, KYC, payouts, invoices"),
        "commerce_pro": ("commerce_pro_bot", "Commerce pro: shop, cart, subs, points, wallet, growth"),
        "shop": ("shop_bot", "Shop: catalog, cart, orders"),
    }
    if not bot_name and primary in _identity:
        nm, desc = _identity[primary]
        s.set_name(nm)
        s.set_description(desc)
    elif primary in _identity and (not s.bot_name or s.bot_name in {
        "group_admin_bot", "custom_bot", "my_bot", "market_bot"
    }):
        nm, desc = _identity[primary]
        s.set_name(nm)
        s.set_description(desc)

    # Intelligence: global / i18n language
    if _has_any(request, _I18N_KEYS):
        s.selected.add("lang")
        if s.language in {"ar", ""}:
            s.language = "en"

    # Name from request tokens if still generic
    if bot_name:
        s.set_name(bot_name)
    elif request:
        token = re.sub(r"[^a-zA-Z0-9_\u0600-\u06FF]+", "_", request.strip())[:32].strip("_")
        if token and s.bot_name in {
            "group_admin_bot", "custom_bot", "my_bot", "market_bot", "shop_bot",
        }:
            s.set_name(f"bot_{token[:20]}" if not token[0].isalpha() else token[:24])

    # Description reflects composition
    if len(presets) > 1:
        s.set_description(
            f"Composed bot: {', '.join(presets)} — multi-intent zero-AI pack"
        )

    t = _norm(request)
    complexity_hit = any(
        k in t for k in (
            "متكامل", "enterprise", "all-in-one", "all in one", "منصة", "suite",
            "ضخم", "احترافي", "production", "operating system", "جاهز للسوق",
            "rule them all", "كل شيء", "شامل",
        )
    )
    multi_complex = sum(
        1 for d in ("saas", "marketplace", "logistics", "finance", "commerce_pro")
        if d in presets
    )
    # Only dump broad backbone when user clearly wants a huge multi-domain platform
    if complexity_hit and multi_complex >= 2:
        for pack in (
            _SUPPORT_PRO_CAPS, _CRM_CAPS, _GROWTH_CAPS, _WALLET_CAPS,
        ):
            s.selected.update(pack)
        s.selected.add("lang")
    elif complexity_hit and multi_complex == 0 and len(presets) >= 3:
        # legacy multi-intent without complex systems — light backbone only
        s.selected.update(_SUPPORT_PRO_CAPS)
        s.selected.add("lang")

    # UI language: Arabic request → Arabic menu/welcome
    if any("\u0600" <= ch <= "\u06FF" for ch in (request or "")):
        s.language = "ar"
    elif any(k in _norm(request) for k in ("english", "global en", "en only")):
        s.language = "en"

    return s


def is_bot_request(request: str) -> bool:
    t = _norm(request)
    keys = (
        "بوت", "bot", "telegram", "تيليجرام", "تليجرام", "tg ",
        "اعمل", "أنشئ", "انشئ", "سوي", "أبغى", "ابي", "أريد", "عايز", "عاوز",
        "create", "make", "build",
    )
    return any(k in t for k in keys)


# Full marketplace-grade default pack: group admin + welcome + tickets + basics
_DEFAULT_CAPS = tuple(dict.fromkeys(
    list(_GROUP_CAPS) + list(_SUPPORT_CAPS) + ["ping", "about"]
))


def default_spec_from_request(request: str, *, user_id: int = 0) -> BotSpec:
    """Always-on high-quality pack when the user asks for a bot.

    Uses multi-intent scoring and pack composition when several domains match.
    """
    stack = detect_preset_stack(request, limit=4)
    if not stack:
        stack = ["group_management"]
    s = compose_session(stack, user_id=user_id, request=request)
    if not s.bot_name or s.bot_name in {"group_admin_bot", "custom_bot", "my_bot"}:
        s.set_name("market_bot")
    return s.to_spec()


def session_for_preset(preset: str, *, user_id: int = 0, bot_name: str = "") -> BuilderSession:
    s = BuilderSession(user_id=user_id)
    if preset == "group_management":
        s.set_name(bot_name or "group_admin_bot")
        s.set_description("بوت إدارة مجموعات: حظر/كتم/طرد/ترحيب/قوانين")
        for k in _GROUP_CAPS:
            s.selected.add(k)
    elif preset == "support_tickets":
        s.set_name(bot_name or "support_bot")
        s.set_description("بوت تذاكر دعم")
        for k in _SUPPORT_CAPS:
            s.selected.add(k)
    elif preset == "tasks":
        s.set_name(bot_name or "tasks_bot")
        s.set_description("بوت مهام شخصية")
        for k in _TASK_CAPS:
            s.selected.add(k)
    elif preset == "notes":
        s.set_name(bot_name or "notes_bot")
        s.set_description("بوت ملاحظات")
        for k in _NOTES_CAPS:
            s.selected.add(k)
    elif preset == "security_ops":
        s.set_name(bot_name or "security_ops_bot")
        s.set_description("بوت عمليات أمنية دفاعية: بلاغات وتوعية")
        for k in _SECURITY_CAPS:
            s.selected.add(k)
    elif preset == "shop":
        s.set_name(bot_name or "shop_bot")
        s.set_description(
            "Global shop bot with Telegram Payments invoices, catalog, orders, and /lang (en/ar)"
        )
        for k in _SHOP_CAPS:
            s.selected.add(k)
    elif preset == "subscriptions":
        s.set_name(bot_name or "subscription_bot")
        s.set_description(
            "Subscription bot for end-users: plans, subscribe, my_sub, admin grant/revoke, i18n"
        )
        for k in _SUB_CAPS:
            s.selected.add(k)
    elif preset == "points":
        s.set_name(bot_name or "points_bot")
        s.set_description(
            "Loyalty/points bot: balance, leaderboard, admin grant_points, i18n"
        )
        for k in _POINTS_CAPS:
            s.selected.add(k)
    elif preset == "contests":
        s.set_name(bot_name or "contest_bot")
        s.set_description(
            "Contests/giveaways bot: join, entries, admin create/end/draw, i18n"
        )
        for k in _CONTEST_CAPS:
            s.selected.add(k)
    elif preset == "growth":
        s.set_name(bot_name or "growth_bot")
        s.set_description("Referral, daily check-in, streaks, achievements — growth engine for end-users")
        for k in _GROWTH_CAPS:
            s.selected.add(k)
    elif preset == "crm":
        s.set_name(bot_name or "crm_bot")
        s.set_description("Sales CRM: leads, pipeline, deals, follow-ups")
        for k in _CRM_CAPS:
            s.selected.add(k)
    elif preset == "support_pro":
        s.set_name(bot_name or "support_pro_bot")
        s.set_description("Pro support: tickets, priority, assign, knowledge base, CSAT")
        for k in _SUPPORT_PRO_CAPS:
            s.selected.add(k)
    elif preset == "education":
        s.set_name(bot_name or "education_bot")
        s.set_description("Courses, lessons, quizzes, homework, certificates")
        for k in _EDU_CAPS:
            s.selected.add(k)
    elif preset == "restaurant":
        s.set_name(bot_name or "restaurant_bot")
        s.set_description("Restaurant menu, orders, table booking")
        for k in _RESTAURANT_CAPS:
            s.selected.add(k)
    elif preset == "jobs":
        s.set_name(bot_name or "jobs_bot")
        s.set_description("Job board: list, apply, post (admin)")
        for k in _JOBS_CAPS:
            s.selected.add(k)
    elif preset == "marketplace":
        s.set_name(bot_name or "marketplace_bot")
        s.set_description("Marketplace: vendors, listings, escrow, bids, payouts, disputes")
        s.selected.update(_marketplace_pack(limit=28))
    elif preset == "saas":
        s.set_name(bot_name or "saas_bot")
        s.set_description("SaaS: seats, trials, quotas, billing, RBAC, webhooks, flags")
        s.selected.update(_saas_pack(limit=28))
    elif preset == "logistics":
        s.set_name(bot_name or "logistics_bot")
        s.set_description("Logistics: shipments, fleet, routes, hubs, POD, last-mile")
        s.selected.update(_logistics_pack(limit=28))
    elif preset == "finance":
        s.set_name(bot_name or "finance_bot")
        s.set_description("Light finance: ledger, payouts, KYC, invoices, wallets")
        s.selected.update(_finance_pack(limit=28))
    elif preset == "community":
        s.set_name(bot_name or "community_bot")
        s.set_description("Community feed, profiles, posts, moderation queue")
        for k in _COMMUNITY_CAPS:
            s.selected.add(k)
    elif preset == "events":
        s.set_name(bot_name or "events_bot")
        s.set_description("Events and RSVP management")
        for k in _EVENTS_CAPS:
            s.selected.add(k)
    elif preset == "wallet":
        s.set_name(bot_name or "wallet_bot")
        s.set_description("User wallet: balance, top-up, transfer, history")
        for k in _WALLET_CAPS:
            s.selected.add(k)
    elif preset == "creator":
        s.set_name(bot_name or "creator_bot")
        s.set_description(
            "Creator monetization: paid content, tips, membership, referrals, global i18n"
        )
        for k in _CREATOR_CAPS:
            s.selected.add(k)
    elif preset == "commerce_pro":
        s.set_name(bot_name or "commerce_pro_bot")
        s.set_description(
            "Full commerce suite: shop+cart+payments+subs+points+wallet+growth+analytics"
        )
        for k in _COMMERCE_PRO_CAPS:
            s.selected.add(k)
        # Keep session language (default ar); callers may set en for global EN packs

    elif preset == "fitness":
        s.set_name(bot_name or "fitness_bot")
        s.set_description("Gym/fitness: schedule, book session, membership, check-in")
        for k in _FITNESS_CAPS:
            s.selected.add(k)
    elif preset == "realestate":
        s.set_name(bot_name or "realestate_bot")
        s.set_description("Real estate listings, search, inquiries")
        for k in _REALESTATE_CAPS:
            s.selected.add(k)
    elif preset == "clinic":
        s.set_name(bot_name or "clinic_bot")
        s.set_description("Clinic appointments: slots, book, cancel")
        for k in _CLINIC_CAPS:
            s.selected.add(k)
    elif preset == "auction":
        s.set_name(bot_name or "auction_bot")
        s.set_description("Auctions: list, bid, create, my bids")
        for k in _AUCTION_CAPS:
            s.selected.add(k)
    elif preset == "delivery":
        s.set_name(bot_name or "delivery_bot")
        s.set_description("Delivery tracking and shipment status")
        for k in _DELIVERY_CAPS:
            s.selected.add(k)
    elif preset == "booking":
        s.set_name(bot_name or "booking_bot")
        s.set_description("بوت حجوزات")
        for k in ("start", "help", "book_slot", "book_list", "book_cancel", "book_admin_list"):
            s.selected.add(k)
    elif preset == "hr":
        s.set_name(bot_name or "hr_bot")
        s.set_description("بوت موارد بشرية مبسط")
        for k in ("start", "help", "hr_leave_request", "hr_leave_list", "hr_checkin"):
            s.selected.add(k)
    else:
        s.set_name(bot_name or "custom_bot")
        s.selected.update({"start", "help"})
    return s


def spec_from_request(request: str, *, user_id: int = 0) -> BotSpec | None:
    preset = detect_preset(request)
    if not preset:
        return None
    return session_for_preset(preset, user_id=user_id).to_spec()


__all__ = ["detect_preset", "detect_preset_stack", "score_presets", "compose_session", "session_for_preset", "spec_from_request", "is_bot_request", "default_spec_from_request"]
