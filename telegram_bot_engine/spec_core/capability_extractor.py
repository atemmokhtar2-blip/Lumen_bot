"""Extract concrete capability keys from free-text (Arabic/English).

Maps user language → **real registry keys** only. Phantom labels that the
code generator cannot emit are never returned.
"""
from __future__ import annotations

from typing import Iterable

from .registry import CAPABILITIES
from .language_understanding.normalize import normalize_text, apply_dialect_map

_PATTERNS: dict[str, tuple[str, ...]] = {
    # security
    "sec_dns_check": ("dns", "dns records", "فحص dns", "سجلات dns", "a record", "cname", "dns lookup"),
    "sec_mx_check": ("mx", "mx records", "سجلات mx", "mail exchange", "mx check"),
    "sec_tls_check": ("tls", "ssl", "certificate", "شهادة ssl", "tls check", "ssl check"),
    "sec_http_check": ("http status", "http code", "حالة http", "status code", "http check"),
    "sec_headers_check": ("security headers", "http headers", "رؤوس http", "csp", "hsts", "headers check"),
    "sec_domain_overview": (
        "domain scan", "website scan", "فحص الموقع", "site analysis", "domain scanner",
        "فحص نطاق", "domain overview", "domain check",
    ),
    "sec_report_phish": ("phishing", "تصيد", "تصيّد", "phish", "احتيال"),
    "sec_report_incident": ("incident", "حادث أمني", "بلاغ أمني", "security incident", "soc"),
    "sec_checklist": ("checklist", "توعية أمنية", "security checklist", "توعية"),
    "sec_tips": ("security tips", "نصائح أمان", "نصائح أمنية"),
    "sec_password_tips": ("password", "كلمة المرور", "كلمات المرور", "password strength"),
    "sec_list_reports": ("security reports", "بلاغات أمنية"),
    # IoT
    "device_list": ("device list", "أجهزة", "اجهزة", "devices", "قائمة الأجهزة", "smart devices"),
    "device_create": ("add device", "تسجيل جهاز", "register device", "device create"),
    "device_view": ("device status", "حالة جهاز", "device view"),
    "sensor_list": ("sensors", "حساسات", "مستشعرات", "sensor list", "sensor data"),
    "sensor_create": ("add sensor", "إضافة حساس", "sensor create"),
    "sensor_view": ("sensor reading", "قراءة حساس", "telemetry"),
    # DevOps
    "deploy_list": ("deployments", "نشر", "deployment", "deploy list", "deploy status"),
    "deploy_create": ("new deploy", "إنشاء نشر", "deploy create"),
    "deploy_view": ("deploy view", "عرض نشر"),
    "env_list": ("environments", "بيئات", "env list", "staging", "production env"),
    "secret_list": ("secrets", "أسرار", "secret list"),
    "log_list": ("logs", "سجلات", "logging", "audit log", "تسجيل"),
    # Blockchain / wallet
    "wallet_balance": ("wallet", "محفظة", "balance", "رصيد", "crypto wallet"),
    "wallet_history": ("transaction history", "سجل معاملات", "tx history"),
    "wallet_transfer": ("send transaction", "تحويل", "transfer crypto"),
    "wallet_topup": ("topup", "شحن محفظة", "top-up"),
    # AI assist (notes/tasks as lightweight workspace)
    "note_add": ("note", "ملاحظة", "prompt log", "سجل برومبت", "ai log"),
    "note_list": ("list notes", "عرض الملاحظات", "show logs"),
    "task_add": ("task", "مهمة", "todo", "مهام", "job queue"),
    "task_list": ("list tasks", "قائمة المهام"),
    "task_delete": ("delete task", "حذف مهمة", "امسح مهمة", "remove task"),
    "task_done": ("complete task", "إنهاء مهمة", "انهاء مهمة", "تمت المهمة", "done task"),

    # Healthcare
    "clinic_book": ("book appointment", "حجز موعد", "موعد طبي"),
    "clinic_my": ("my appointments", "مواعيدي"),
    "patient_list": ("patients", "مرضى", "patient list"),
    "patient_create": ("new patient", "تسجيل مريض"),
    "doctor2_list": ("doctors", "أطباء", "doctor list"),
    "prescription_list": ("prescriptions", "وصفات", "وصفة طبية"),
    "prescription_create": ("new prescription", "إنشاء وصفة"),
    # Education
    "course_list": ("courses", "دورات", "كورسات", "course list"),
    "course_enroll": ("enroll", "تسجيل في دورة"),
    "lesson_list": ("lessons", "دروس", "lesson list"),
    "lesson_open": ("open lesson", "فتح درس"),
    "quiz_start": ("quiz", "اختبار", "امتحان", "start quiz"),
    "quiz_score": ("quiz score", "درجة الاختبار"),
    "homework_submit": ("homework", "واجب", "submit homework"),
    # Commerce
    "shop_catalog": ("shop", "store", "متجر", "كتالوج", "catalog", "منتجات"),
    "cart_view": ("cart", "سلة"),
    "plans": ("subscription", "اشتراك", "خطة"),
    # Social / community
    "post_create": ("create post", "منشور", "نشر بوست"),
    "post_list": ("feed", "المنشورات", "timeline"),
    "post_like": ("like", "إعجاب", "اعجاب"),
    "post_comment": ("comment", "تعليق"),
    # Projects / reports
    "project_create": ("create project", "إنشاء مشروع", "new project", "مشروع جديد"),
    "project_list": ("list projects", "مشاريعي", "قائمة المشاريع", "projects list"),
    "project_view": ("view project", "عرض مشروع"),
    "project_search": ("search project", "بحث مشروع"),
    "project_stats": ("project stats", "إحصائيات المشروع"),
    "report_create": ("pdf", "تقرير pdf", "export pdf", "generate pdf", "تقرير", "report"),
    "report_list": ("list reports", "قائمة التقارير", "my reports"),
    "report_export": ("export report", "تصدير تقرير", "excel", "xlsx", "csv", "تصدير"),
    # Support
    "ticket_open": ("ticket", "تذكرة", "دعم", "support", "helpdesk"),
    "ticket_list": ("list tickets", "تذاكر مفتوحة"),
    "ticket_status": ("ticket status", "حالة تذكرة"),
    # Gaming proxies
    "leaderboard": ("leaderboard", "لوحة المتصدرين", "متصدرين"),
    "contests": ("tournament", "بطولة", "مسابقة", "contest"),
    "join_contest": ("join tournament", "انضم للبطولة"),
    "balance": ("xp", "points balance", "نقاطي"),
    "achievement_list": ("achievement", "إنجاز", "انجاز", "achievements"),
    # Core
    "start": ("start", "بدء"),
    "help": ("help", "مساعدة"),
    "lang": ("i18n", "multi-language", "متعدد اللغات", "ترجمة", "lang"),
    "my_id": ("api key", "مفتاح api", "token", "my id"),
    "rules": ("rate limit", "rate limiting", "تحديد المعدل", "throttle", "rules"),
    # Welcome / group gate (Phase-1 detection coverage)
    "welcome_set": (
        "ترحيب", "رسالة ترحيب", "نظام ترحيب", "ترحيب الأعضاء", "ترحيب اعضاء",
        "يرحب", "يرحّب", "بالاعضاء", "بالأعضاء", "اعضاء جدد", "أعضاء جدد",
        "الجدد", "الجداد", "welcome", "welcome message", "set welcome",
    ),
    "welcome_toggle": ("تفعيل الترحيب", "إيقاف الترحيب", "toggle welcome"),
    "welcome_show": ("عرض الترحيب", "إعداد الترحيب", "show welcome"),
    "welcome_test": ("تجربة الترحيب", "test welcome"),
    "goodbye_set": ("وداع", "رسالة وداع", "goodbye"),
    "verify_start": ("تحقق عضو", "تحقق الأعضاء", "member verify", "verification"),
    # Moderation / group management
    "user_unmute": ("فك الكتم", "unmute", "الغاء الكتم", "إلغاء الكتم"),
    "user_unban": ("فك الحظر", "unban", "الغاء الحظر", "إلغاء الحظر"),
    "user_info": ("معلومات العضو", "info", "معلومات", "user info", "ايدي"),
    "purge": ("حذف جماعي", "purge", "تنظيف الرسائل"),
    "delete_message": ("حذف رسالة", "delete message", "احذف"),
    "user_ban": ("حظر", "بان", "ban user", "حظر مستخدم"),
    "user_mute": ("كتم", "ميوت", "mute"),
    "user_kick": ("طرد", "kick"),
    "user_warn": ("تحذير", "warn"),
    "pin_message": ("تثبيت", "pin message", "تثبيت رسالة"),
    "delete_message": ("حذف رسالة", "delete message"),
    "lock_chat": ("قفل الدردشة", "قفل الشات", "lock chat"),
    "user_info": ("معلومات عضو", "info member", "user info"),
    "announce": ("إعلان", "announce", "إذاعة"),
    # Contests / giveaways
    "contests": (
        "مسابقة", "مسابقات", "contest", "giveaway", "سحب", "سحب فائز",
        "المسابقات", "تحدي", "تحديات",
    ),
    "join_contest": ("انضم للمسابقة", "الاشتراك في مسابقة", "join contest"),
    "new_contest": ("إنشاء مسابقة", "مسابقة جديدة", "create contest"),
    "draw_winner": ("سحب فائز", "اختيار فائز", "draw winner", "فائز"),
    "end_contest": ("إنهاء مسابقة", "إغلاق مسابقة", "end contest"),
    # Booking / clinic
    "book_slot": (
        # Bare «موعد» must NOT map here — it is shared with task deadlines.
        "حجز موعد", "احجز موعد", "booking", "book slot", "احجز",
        "عيادة", "موعد طبي", "صالون", "تجميل", "حلاق", "باربر", "salon",
        "حجز", "book appointment",
    ),
    "book_list": ("حجوزاتي", "مواعيدي", "my bookings"),
    "book_cancel": ("إلغاء حجز", "cancel booking"),
    "clinic_book": ("حجز عيادة", "موعد عيادة", "clinic book"),
    # Echo / auto-reply
    "echo": (
        "رد آلي", "رد تلقائي", "auto reply", "echo", "يرد على الرسائل",
        "رد على الرسائل", "يردد", "يعيد النص",
    ),
    # Coupons / points extras
    "coupon_apply": ("كوبون", "كوبونات", "خصم", "coupon", "promo code", "برومو"),
    "coupon_create": ("إنشاء كوبون", "create coupon"),
    "redeem_points": ("استبدال نقاط", "redeem points"),
    "points_history": ("سجل نقاط", "points history"),
    # Reminders / notify
    "remind_set": (
        "تذكير", "ذكرني", "تذكيرات", "reminder", "remind", "إشعار",
        "اشعار", "notifications", "يبعت إشعارات", "إشعارات",
    ),
    "remind_list": ("قائمة التذكيرات", "list reminders"),
    # Verify / gate
    "verify_start": (
        "تحقق", "تحقق عضو", "تحقق الأعضاء", "verification", "verify",
        "بوابة تحقق", "captcha بسيط",
    ),
    "verify_ok": ("تأكيد التحقق", "confirm verify"),
    "force_subscribe_info": (
        "اشتراك إجباري", "يجب الاشتراك", "force subscribe", "اشترك أولا",
    ),
    # Wallet
    "wallet_balance": ("محفظة", "رصيد محفظة", "wallet", "wallet balance"),
    "wallet_history": ("سجل محفظة", "wallet history"),
    # Subscriptions extras
    "subscribe": ("اشترك", "الاشتراك", "subscribe"),
    "my_sub": ("اشتراكي", "my subscription"),
    # Support extras
    "ticket_my": ("تذاكري", "my tickets"),
    "ticket_close": ("إغلاق تذكرة", "close ticket"),
    # Shop extras already partial — strengthen
    "shop_order": ("طلب منتج", "place order", "اطلب"),
    "shop_my_orders": ("طلباتي", "my orders"),
    "cart_add": ("أضف للسلة", "add to cart"),
    "cart_checkout": ("إتمام الشراء", "checkout"),
    # Rules content (group rules — distinct from rate-limit)
    "rules": (
        "قوانين", "قوانين المجموعة", "قواعد الجروب", "group rules",
        "rate limit", "rate limiting", "تحديد المعدل", "throttle", "rules",
    ),

    # Broadcast / admin roles / polls / currency / referrals / balance
    "broadcast_admin": (
        "رسائل جماعية", "رسائل جماعيه", "رسالة جماعية", "رسالة جماعيه",
        "برودكاست", "broadcast", "اذاعة للجميع", "إعلان جماعي",
        "يبعت للعضاء", "يبعت للأعضاء", "ارسال جماعي", "إرسال جماعي",
        "رسائل جماعي",
    ),
    "admin_dashboard": ("لوحة مشرف", "لوحة الادمن", "admin dashboard", "صلاحيات", "ادمن"),
    "admin_set_role": ("تعيين دور", "set role", "رتبة", "رول"),
    "user_promote": ("ترقية مشرف", "promote", "ترقية"),
    "poll_create": (
        "تصويت", "استبيان", "استبيانات", "poll", "تصويتات", "عمل تصويت",
    ),
    "currency_convert": (
        "تحويل عملة", "تحويل العملات", "يحول العملات", "currency", "سعر الصرف",
        "عملات", "تحويل فلوس",
    ),
    "balance": ("رصيد نقاط", "نقاطي", "رصيدي", "points balance", "ولاء", "نقاط ولاء"),
    "leaderboard": ("متصدرين", "لوحة المتصدرين", "leaderboard"),
    "referral_code": ("إحالة", "احالة", "كود دعوة", "referral", "ريفيرال"),
    "referral_invite": ("رابط دعوة", "invite link", "دعوة أصدقاء"),
    "task_add": ("تودو", "todo", "مهمة", "مهام", "قائمة مهام", "to-do", "تودوليست"),
    "faq_show": ("faq", "أسئلة شائعة", "اسئله شائعه", "اسئلة شائعة", "الأسئلة الشائعة"),

}

_DOMAIN_CAP_HINTS: dict[str, tuple[str, ...]] = {
    "cybersecurity": (
        "start", "help", "lang",
        "sec_dns_check", "sec_mx_check", "sec_tls_check", "sec_http_check",
        "sec_headers_check", "sec_domain_overview", "sec_password_tips",
        "sec_report_phish", "sec_report_incident", "sec_checklist", "sec_tips",
        "sec_list_reports", "sec_close_report",
        "project_create", "project_list", "project_view", "project_search",
        "report_create", "report_list", "report_export",
        "note_add", "note_list", "task_add", "task_list", "ticket_list", "my_id", "rules",
    ),
    "iot": (
        "start", "help", "lang",
        "device_list", "device_create", "device_view", "device_search",
        "sensor_list", "sensor_create", "sensor_view", "sensor_search",
        "note_add", "note_list", "task_add", "task_list",
        "project_list", "project_create",
    ),
    "blockchain": (
        "start", "help", "lang",
        "wallet_balance", "wallet_history", "wallet_transfer", "wallet_topup",
        "note_add", "ticket_list", "rules", "my_id",
    ),
    "ai_ml": (
        "start", "help", "lang",
        "note_add", "note_list", "task_add", "task_list", "project_create", "project_list",
    ),
    "devops": (
        "start", "help", "lang",
        "deploy_list", "deploy_create", "deploy_view", "deploy_search",
        "env_list", "secret_list", "log_list",
        "task_add", "task_list", "note_add", "note_list",
        "project_create", "project_list",
    ),
    "healthcare": (
        "start", "help", "lang",
        "clinic_book", "clinic_my", "clinic_cancel", "clinic_slots",
        "patient_list", "patient_create", "patient_view",
        "doctor2_list", "doctor2_view",
        "prescription_list", "prescription_create", "note_add",
    ),
    "education": (
        "start", "help", "lang",
        "course_list", "course_enroll", "lesson_list", "lesson_open",
        "quiz_start", "quiz_score", "homework_submit", "homework_list",
    ),
    "ecommerce": (
        "start", "help", "lang", "shop_catalog", "cart_view", "shop_my_orders",
        "plans", "wallet_balance",
    ),
    "marketplace": (
        "start", "help", "lang", "shop_catalog", "cart_view", "wallet_balance",
    ),
    "finance": (
        "start", "help", "lang", "wallet_balance", "wallet_history",
        "report_create", "report_list",
    ),
    "logistics": (
        "start", "help", "lang", "task_list", "note_add",
    ),
    "gaming": (
        "start", "help", "lang", "leaderboard", "contests", "join_contest",
        "balance", "achievement_list", "points_history",
    ),
    "social": (
        "start", "help", "lang", "post_create", "post_list", "post_like",
        "post_comment", "profile_view",
    ),
    "tasks": (
        "start", "help", "lang",
        "task_add", "task_list", "task_delete", "task_done", "task_clear",
        "remind_set", "remind_list", "note_add", "note_list",
    ),
    "projects": (
        "start", "help", "project_create", "project_list", "project_view",
        "project_search", "project_stats", "task_add", "task_list", "note_add",
    ),
    "saas": (
        "start", "help", "lang", "project_list",
    ),
    "hr": (
        "start", "help", "hr_leave_request", "hr_leave_list", "hr_checkin",
    ),
    "fitness": (
        "start", "help", "lang", "gym_checkin", "gym_membership",
    ),
}



def _norm(text: str) -> str:
    raw = (text or "").lower()
    # Use the shared Arabic normalizer so Egyptian, Levantine, Gulf and
    # orthographic variants reach the same capability keys.
    return normalize_text(apply_dialect_map(raw))


# Prefixes that must not appear under a pure tasks lock
_TASKS_DENY_PREFIXES: tuple[str, ...] = (
    "clinic_", "shop_", "cart_", "book_", "wallet_", "mkt_", "saas_",
    "ticket_", "patient_", "prescription_", "doctor",
)
_TASKS_DENY_EXACT: frozenset[str] = frozenset(
    {
        "book_slot", "book_list", "book_cancel", "book_admin_list",
        "ticket_open", "shop_catalog", "cart_view", "shop_buy", "shop_orders",
    }
)


def _match_patterns(text: str) -> list[str]:
    """Longest-phrase-first pattern match with span neutralization."""
    t = _norm(text)
    t_fold = t.replace("ة", "ه")
    # Build (key, keyword, len) candidates; longer keywords win and consume span
    candidates: list[tuple[int, str, str]] = []
    for key, keywords in _PATTERNS.items():
        for kw in keywords:
            kw_norm = _norm(kw)
            kw_fold = kw_norm.replace("ة", "ه")
            if not kw_norm:
                continue
            candidates.append((len(kw_fold), key, kw_fold if kw_fold in t_fold else kw_norm))
    candidates.sort(key=lambda x: -x[0])

    mask = t_fold
    out: list[str] = []
    seen: set[str] = set()
    for _ln, key, kw in candidates:
        if key in seen or key not in CAPABILITIES:
            continue
        if kw not in mask:
            continue
        # short tokens need crude boundary for ASCII
        if len(kw) <= 3 and kw.isascii():
            import re as _re
            if not _re.search(rf"(?<![a-z0-9]){_re.escape(kw)}(?![a-z0-9])", mask):
                continue
        seen.add(key)
        out.append(key)
        mask = mask.replace(kw, " " * len(kw), 1)
    return out


def extract(text: str) -> list[str]:
    """Extract capability keys explicitly evidenced in the request text."""
    out = _match_patterns(text)
    if out:
        for core in ("start", "help"):
            if core in CAPABILITIES and core not in out:
                out.append(core)
    return out


def extract_for_domains(
    domains: Iterable[str],
    *,
    text: str = "",
    require_text_evidence: bool = True,
) -> list[str]:
    """Domain suite injection with confidence gate (Phase C root).

    Full suite is injected only when the domain appears *and* the request
    has at least one pattern hit for that vertical (or suite is the lean
    tasks pack). Otherwise only ``start``/``help`` leak through.
    """
    out: list[str] = []
    seen: set[str] = set()
    evidenced = set(_match_patterns(text)) if (require_text_evidence and text) else set()

    def add(key: str) -> None:
        if key in CAPABILITIES and key not in seen:
            seen.add(key)
            out.append(key)

    for d in domains:
        suite = _DOMAIN_CAP_HINTS.get(d, ())
        if not suite:
            continue
        if d in {"tasks", "projects"}:
            # Lean productivity suite — always OK when domain allowed
            for key in suite:
                add(key)
            continue
        # Other verticals (Phase C): ONLY core + keys evidenced in the text.
        # Never dump the entire domain suite on a single keyword hit.
        for key in suite:
            if key in {"start", "help", "lang"}:
                add(key)
                continue
            if not require_text_evidence:
                add(key)
                continue
            if key in evidenced:
                add(key)
    return out


def _filter_for_decision(keys: list[str], decision: object | None) -> list[str]:
    if decision is None:
        return keys
    primary = getattr(decision, "primary", None)
    if primary == "group_moderation":
        allow_p = ("user_", "welcome_", "delete_", "purge", "pin_", "lock_", "unlock_", "rules", "start", "help", "lang")
        out = []
        for k in keys:
            if k in {"start", "help", "lang", "rules", "purge", "delete_message"} or any(str(k).startswith(p) for p in ("user_", "welcome_", "pin_", "lock_")):
                out.append(k)
        return out
    if primary not in {"tasks", "projects"}:
        return keys
    out: list[str] = []
    for k in keys:
        if k in _TASKS_DENY_EXACT:
            continue
        if any(str(k).startswith(p) for p in _TASKS_DENY_PREFIXES):
            continue
        out.append(k)
    return out


def extract_all(
    text: str,
    domains: Iterable[str] | None = None,
    *,
    decision: object | None = None,
) -> list[str]:
    """Merge text evidence + domain suites under optional DomainDecision lock."""
    if decision is not None and domains is None:
        domains = list(getattr(decision, "allowed_domains", None) or [])
    keys = extract(text)
    if domains:
        for k in extract_for_domains(domains, text=text, require_text_evidence=True):
            if k not in keys:
                keys.append(k)
    keys = _filter_for_decision(keys, decision)
    return keys



# Lean cores — never the full historical fat packs (_SHOP_CAPS etc.)
_LEAN_PRESET_CORE: dict[str, tuple[str, ...]] = {
    "tasks": (
        "start", "help", "lang",
        "task_add", "task_list", "task_delete", "task_done", "task_clear",
        "remind_set", "remind_list",
    ),
    "notes": ("start", "help", "note_add", "note_list"),
    "shop": ("start", "help", "lang", "shop_catalog", "cart_view"),
    "booking": ("start", "help", "book_slot", "book_list", "book_cancel"),
    "clinic": ("start", "help", "clinic_book", "clinic_my", "clinic_cancel", "clinic_slots"),
    "echo_basic": ("start", "help"),
    "group_management": (
        "start", "help", "rules",
        "user_ban", "user_unban", "user_mute", "user_unmute", "user_kick", "user_warn",
        "user_info", "delete_message", "purge",
        "welcome_set", "welcome_toggle",
    ),

    "support_tickets": ("start", "help", "ticket_open", "ticket_status", "ticket_list"),
    "security_ops": (
        "start", "help", "lang",
        "sec_dns_check", "sec_tls_check", "sec_domain_overview",
    ),
}


def resolve_capabilities(
    request: str,
    *,
    presets: Iterable[str] | None = None,
    decision: object | None = None,
) -> list[str]:
    """Authoritative capability set for generation (Phase C root).

    Rules:
    1. Always include text-evidenced keys from ``extract``.
    2. Add only the *lean core* for each preset on the stack — never full
       historical packs (_SHOP_CAPS / commerce pro dumps).
    3. Honour DomainDecision deny-lists (tasks lock strips shop/clinic/book).
    4. Result is registry-filtered and de-duplicated, stable order.
    """
    presets = [p for p in (presets or []) if p]
    if decision is None:
        try:
            from .domain_detector import decide as _decide
            decision = _decide(request)
        except Exception:
            decision = None

    if decision is not None and getattr(decision, "primary", None) in {"tasks", "projects"}:
        presets = ["tasks"]

    evidenced = set(extract(request))
    selected: list[str] = []
    seen: set[str] = set()

    def add(key: str) -> None:
        if key in CAPABILITIES and key not in seen:
            seen.add(key)
            selected.append(key)

    for k in ("start", "help"):
        add(k)

    for k in evidenced:
        add(k)

    for preset in presets:
        lean = _LEAN_PRESET_CORE.get(preset)
        if lean is None:
            # Unknown preset: do not invent fat caps — keep evidence only
            continue
        for k in lean:
            # Under evidence-first policy: for shop/clinic/booking require at least
            # one vertical signal in the request before expanding lean core.
            if preset in {"shop", "clinic", "booking", "security_ops"}:
                vertical_hit = bool(evidenced & set(lean)) or bool(evidenced)
                # If extract found nothing for this vertical, still allow lean
                # only when this preset is the sole stack entry (explicit intent)
                if not vertical_hit and len(presets) > 1:
                    continue
            add(k)

    # Domain lean suite for allowed domains (tasks always; others evidence-only)
    if decision is not None:
        allowed = list(getattr(decision, "allowed_domains", None) or [])
        for k in extract_for_domains(allowed, text=request, require_text_evidence=True):
            add(k)
        selected = _filter_for_decision(selected, decision)

    # Ensure tasks minimal if tasks locked
    if decision is not None and getattr(decision, "primary", None) in {"tasks", "projects"}:
        for k in ("task_add", "task_list"):
            add(k)

    return selected


__all__ = ["extract", "extract_for_domains", "extract_all", "resolve_capabilities"]
