"""
Massive Arabic/English lexicon for deep natural-language understanding.
Designed for speed: simple substring scans, no ML.
Every entry maps free text → formal signals the extractor consumes.
"""

from __future__ import annotations

# ── Intent verbs (user says "اعمل/عايز/ابني" …) ───────────────────────────

INTENT_VERBS: tuple[str, ...] = (
    "اعمل", "أعمل", "سوي", "سوّي", "ابني", "ابنِ", "أنشئ", "انشئ", "اصنع",
    "عايز", "عاوز", "أريد", "اريد", "محتاج", "نحتاج", "أبي", "ابغى",
    "make", "build", "create", "generate", "i want", "i need", "please make",
)

# ── Domain phrase → archetype boost ───────────────────────────────────────

DOMAIN_PHRASES: dict[str, tuple[str, ...]] = {
    "ecommerce": (
        "متجر", "متجر إلكتروني", "متجر الكتروني", "بيع منتجات", "بيع أونلاين",
        "سلة مشتريات", "سلة التسوق", "إتمام الشراء", "checkout", "كتالوج",
        "منتجات", "طلب شراء", "فواتير بيع", "كوبون", "خصم", "شحن",
        "online store", "shop bot", "ecommerce", "shopping cart", "product catalog",
        "add to cart", "place order", "sku", "inventory",
    ),
    "ticketing": (
        "نظام تذاكر", "تذاكر دعم", "دعم فني", "خدمة عملاء", "شكوى", "بلاغ",
        "فتح تذكرة", "تذكرة جديدة", "helpdesk", "support ticket", "customer support",
        "issue tracker", "complaint",
    ),
    "admin": (
        "إدارة مجموعة", "إدارة جروب", "مشرف", "حظر أعضاء", "كتم أعضاء",
        "طرد", "ترحيب تلقائي", "قوانين الجروب", "group moderation", "ban users",
        "mute members", "anti spam", "welcome bot",
    ),
    "assistant": (
        "مساعد ذكي", "بوت محادثة", "أسئلة وأجوبة", "رد آلي", "chatbot",
        "ai assistant", "q&a bot", "faq bot",
    ),
    "document": (
        "تحويل إلى pdf", "إنشاء pdf", "مصمم مستندات", "تقرير pdf",
        "document bot", "pdf generator", "make pdf", "file converter",
    ),
    "notification": (
        "بث رسائل", "إشعارات جماعية", "إعلان للمشتركين", "newsletter",
        "broadcast bot", "notification bot", "announce",
    ),
    "game": (
        "لعبة", "مسابقة", "تحدي", "نقاط", "ترتيب اللاعبين", "quiz",
        "trivia", "leaderboard", "score bot",
    ),
    "community": (
        "مجتمع", "أعضاء", "قناة", "منتدى", "community bot", "members club",
    ),
}

# ── Feature phrases → feature_id ──────────────────────────────────────────

FEATURE_PHRASES: list[tuple[str, tuple[str, ...]]] = [
    ("shopping_cart", ("سلة", "cart", "سلة مشتريات", "shopping cart", "أضف للسلة")),
    ("payments", ("دفع", "payment", "stripe", "paypal", "فوري", "تحويل بنكي", "بطاقة", "كارت", "checkout")),
    ("product_catalog", ("كتالوج", "منتجات", "catalog", "products list", "قائمة منتجات")),
    ("order_management", ("طلبات", "orders", "إدارة الطلبات", "تتبع الطلب")),
    ("inventory", ("مخزون", "stock", "inventory", "الكمية المتاحة")),
    ("coupons", ("كوبون", "خصم", "coupon", "discount", "برومو")),
    ("admin_panel", ("أدمن", "admin", "لوحة إدارة", "لوحة تحكم", "admin panel", "لوحة الأدمن")),
    ("notifications", ("إشعار", "تنبيه", "notification", "notify", "إشعارات")),
    ("broadcast", ("بث", "broadcast", "رسالة جماعية", "إعلان للجميع")),
    ("welcome_message", ("ترحيب", "welcome", "رسالة ترحيب")),
    ("moderation", ("حظر", "كتم", "طرد", "ban", "mute", "kick", "anti-spam", "سبام")),
    ("ticketing", ("تذكرة", "تذاكر", "ticket", "support", "شكوى", "بلاغ")),
    ("file_handling", ("ملف", "رفع", "upload", "pdf", "صورة", "مستند", "file", "document")),
    ("database", ("قاعدة بيانات", "database", "postgres", "sqlite", "db")),
    ("concurrency", ("عدة مستخدمين", "concurrent", "في نفس الوقت", "scalability", "حمل عالي")),
    ("task_queue", ("طابور", "queue", "celery", "خلفية", "background job")),
    ("arabic_rtl", ("عربي", "العربية", "rtl", "من اليمين", "لغة عربية")),
    ("english", ("english", "إنجليزي", "الإنجليزية", "انجليزي")),
    ("subscriptions", ("اشتراك", "subscribe", "عضوية", "membership", "subscription")),
    ("gamification", ("نقاط", "score", "level", "مستوى", "ترتيب", "leaderboard")),
    ("conversation_state", ("محادثة", "wizard", "خطوات", "حالة المستخدم", "conversation", "state machine")),
    ("inline_buttons", ("أزرار", "زر", "buttons", "inline", "keyboard", "قائمة أزرار")),
    ("bot_commands", ("أوامر", "commands", "/start", "slash command")),
    ("multi_language", ("لغتين", "متعدد اللغات", "i18n", "bilingual", "multilingual")),
    ("analytics", ("إحصائيات", "analytics", "تقارير", "stats", "dashboard")),
    ("auth", ("تسجيل دخول", "login", "مصادقة", "auth", "otp", "تحقق")),
    ("search", ("بحث", "search", "فلتر", "filter")),
    ("ratings", ("تقييم", "rating", "مراجعة", "review", "نجوم")),
    ("shipping", ("شحن", "shipping", "توصيل", "delivery", "عنوان الشحن")),
    ("invoicing", ("فاتورة", "invoice", "فواتير")),
    ("booking", ("حجز", "booking", "موعد", "appointment", "reservation")),
    ("crm", ("عملاء", "crm", "عميل", "customer profile")),
]

# ── Tech stack phrases ────────────────────────────────────────────────────

TECH_PHRASES: dict[str, tuple[str, ...]] = {
    "postgres": ("postgres", "postgresql", "بوستجريس", "قاعدة بيانات postgres"),
    "sqlite": ("sqlite", "sql light"),
    "redis": ("redis", "ريديس"),
    "stripe": ("stripe", "سترايب"),
    "s3": ("s3", "minio", "object storage", "تخزين سحابي"),
    "docker": ("docker", "dockerfile", "حاوية"),
    "webhook": ("webhook", "ويب هوك"),
}

# ── Quality / non-functional ──────────────────────────────────────────────

QUALITY_PHRASES: dict[str, tuple[str, ...]] = {
    "high_performance": ("سرعة", "أداء عالي", "fast", "performance", "سريع"),
    "error_handling": ("معالجة أخطاء", "error handling", "استثناءات", "try except"),
    "clean_code": ("كود نظيف", "clean code", "منظم", "قابل للتطوير", "modular"),
    "security": ("أمان", "security", "حماية", "تشفير"),
    "logging": ("سجلات", "logging", "log", "تتبع"),
}


def score_domains(text: str) -> dict[str, int]:
    t = text.lower()
    scores: dict[str, int] = {}
    for domain, phrases in DOMAIN_PHRASES.items():
        score = 0
        for p in phrases:
            if p.lower() in t:
                score += 3 if len(p) > 6 else 2
        scores[domain] = score
    return scores


def extract_features_fast(text: str) -> list[str]:
    t = text.lower()
    out: list[str] = []
    seen: set[str] = set()
    for fid, phrases in FEATURE_PHRASES:
        if fid in seen:
            continue
        for p in phrases:
            if p.lower() in t:
                seen.add(fid)
                out.append(fid)
                break
    return out


def detect_tech(text: str) -> list[str]:
    t = text.lower()
    return [k for k, phrases in TECH_PHRASES.items() if any(p.lower() in t for p in phrases)]


def detect_quality(text: str) -> list[str]:
    t = text.lower()
    return [k for k, phrases in QUALITY_PHRASES.items() if any(p.lower() in t for p in phrases)]
