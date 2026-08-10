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


def _saas_pack() -> tuple[str, ...]:
    return _pack_from_prefixes(
        (
            "saas", "seat", "plan3", "billing2", "meter", "quota", "subscription2",
            "trial2", "addon2", "workspace2", "org", "team2", "rbac", "flag2",
            "webhook3", "apikey", "oauth2",
        ),
        limit=72,
        extra=_SAAS_CAPS,
    )


def _marketplace_pack() -> tuple[str, ...]:
    return _pack_from_prefixes(
        (
            "mkt", "listing2", "vendor2", "buyer", "offer2", "bid2", "escrow",
            "payout2", "commission2", "catalog2", "storefront", "auction3",
            "rfq2", "quote2", "dispute3", "review3",
        ),
        limit=72,
        extra=_MARKETPLACE_CAPS,
    )


def _logistics_pack() -> tuple[str, ...]:
    return _pack_from_prefixes(
        (
            "logi", "ship4", "fleet2", "route3", "hub2", "dock2", "warehouse4",
            "courier2", "manifest", "lane", "container", "lastmile", "pod2",
            "eta2", "load2", "trip",
        ),
        limit=72,
        extra=("start", "help", "order_track", "order_status", "lang"),
    )


def _finance_pack() -> tuple[str, ...]:
    return _pack_from_prefixes(
        (
            "fin", "ledger2", "journal", "payout3", "settle2", "recon", "treasury",
            "fx", "card3", "wallet3", "loan2", "credit2", "limit2", "kyc2", "aml2",
            "invoice4", "receivable", "payable", "tax3", "fee2",
        ),
        limit=72,
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


def detect_preset_stack(request: str, *, limit: int = 8) -> list[str]:
    """Multi-domain stack; complex requests get denser enterprise backbone."""
    ranked = score_presets(request)
    out: list[str] = []
    for name, _score in ranked:
        if name not in out:
            out.append(name)
        if len(out) >= limit:
            break
    t = _norm(request)
    complexity_keys = (
        "متكامل", "كامل", "enterprise", "all-in-one", "all in one", "شامل",
        "معقد", "ضخم", "احترافي", "production", "suite", "منصة", "platform",
        "multi", "متعدد", "كل شيء", "rule them all", "جاهز للسوق", "operating system",
    )
    is_complex = any(k in t for k in complexity_keys) or len(t) > 120 or len(out) >= 3
    if is_complex:
        for b in ("commerce_pro", "group_management", "support_pro", "crm", "education", "growth", "wallet", "community"):
            if b not in out:
                out.append(b)
            if len(out) >= 8:
                break
    if "commerce_pro" in out:
        skip = {"shop", "subscriptions", "points", "wallet", "growth"}
        out = [x for x in out if x not in skip or x == "commerce_pro"]
    return out[:8 if is_complex else limit]



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

    # Domain pack densify — complex systems get real registry keys
    names = set(presets)
    if "saas" in names:
        s.selected.update(_saas_pack())
    if "marketplace" in names:
        s.selected.update(_marketplace_pack())
    if "logistics" in names:
        s.selected.update(_logistics_pack())
    if "finance" in names:
        s.selected.update(_finance_pack())
    if "commerce_pro" in names or "shop" in names:
        s.selected.update(_COMMERCE_PRO_CAPS)

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
    if len(presets) >= 3 or len(t) > 140 or complexity_hit:
        for pack in (
            _GROUP_CAPS, _SHOP_CAPS, _SUB_CAPS, _POINTS_CAPS, _GROWTH_CAPS,
            _WALLET_CAPS, _SUPPORT_PRO_CAPS, _CRM_CAPS, _EDU_CAPS,
            _COMMUNITY_CAPS, _EVENTS_CAPS, _SAAS_CAPS, _CONTEST_CAPS,
        ):
            s.selected.update(pack)
        s.selected.update(_COMMERCE_PRO_CAPS)
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
        s.selected.update(_marketplace_pack())
    elif preset == "saas":
        s.set_name(bot_name or "saas_bot")
        s.set_description("SaaS: seats, trials, quotas, billing, RBAC, webhooks, flags")
        s.selected.update(_saas_pack())
    elif preset == "logistics":
        s.set_name(bot_name or "logistics_bot")
        s.set_description("Logistics: shipments, fleet, routes, hubs, POD, last-mile")
        s.selected.update(_logistics_pack())
    elif preset == "finance":
        s.set_name(bot_name or "finance_bot")
        s.set_description("Light finance: ledger, payouts, KYC, invoices, wallets")
        s.selected.update(_finance_pack())
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
