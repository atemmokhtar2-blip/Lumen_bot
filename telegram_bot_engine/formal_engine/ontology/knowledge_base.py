"""
Formal Knowledge Base — dense structured knowledge for deep understanding.

This is NOT an LLM. It is a curated, typed, relational knowledge store that
lets the engine recognize what the user is asking for and map it to precise
software structures (handlers, models, services, integrations, flows).

Expand this file to strengthen understanding; generation must consume the
resulting FormalBotSpec, not hard-coded domain templates.
"""

from __future__ import annotations

from typing import Any

# ── Bot archetypes: signals → canonical type + default structure ──────────

BOT_ARCHETYPES: dict[str, dict[str, Any]] = {
    "ecommerce": {
        "signals_ar": ["متجر", "منتجات", "سلة", "شراء", "طلب", "كتالوج", "مخزون", "دفع"],
        "signals_en": ["shop", "store", "product", "cart", "checkout", "order", "catalog", "payment"],
        "default_commands": [
            ("start", "تشغيل البوت", False),
            ("help", "المساعدة", False),
            ("products", "عرض المنتجات", False),
            ("cart", "السلة", False),
            ("orders", "طلباتي", False),
            ("admin", "لوحة الإدارة", True),
        ],
        "default_buttons": [
            ("🛒 المنتجات", "products"),
            ("🧺 السلة", "cart"),
            ("📦 طلباتي", "orders"),
            ("⚙️ الإدارة", "admin"),
        ],
        "data_models": [
            {"name": "Product", "fields": ["id", "name", "price", "description", "stock", "image_url"]},
            {"name": "CartItem", "fields": ["user_id", "product_id", "qty"]},
            {"name": "Order", "fields": ["id", "user_id", "items", "total", "status", "address", "phone"]},
            {"name": "User", "fields": ["id", "telegram_id", "name", "phone"]},
        ],
        "handlers": [
            {"name": "start", "type": "command", "triggers": ["/start"]},
            {"name": "products", "type": "command", "triggers": ["/products", "callback:products"]},
            {"name": "cart", "type": "command", "triggers": ["/cart", "callback:cart"]},
            {"name": "checkout", "type": "callback", "triggers": ["callback:checkout"]},
            {"name": "orders", "type": "command", "triggers": ["/orders"]},
            {"name": "admin", "type": "command", "triggers": ["/admin"], "admin_only": True},
        ],
        "services": ["catalog", "cart", "orders", "payments", "notifications"],
        "integrations": ["telegram", "database"],
        "optional_integrations": ["stripe", "redis", "s3"],
    },
    "ticketing": {
        "signals_ar": ["تذكرة", "تذاكر", "دعم", "شكوى", "بلاغ", "مساعدة فنية"],
        "signals_en": ["ticket", "support", "complaint", "helpdesk", "issue"],
        "default_commands": [
            ("start", "تشغيل", False),
            ("help", "مساعدة", False),
            ("new", "فتح تذكرة", False),
            ("mytickets", "تذاكري", False),
            ("admin", "إدارة التذاكر", True),
        ],
        "default_buttons": [
            ("📝 تذكرة جديدة", "new_ticket"),
            ("📋 تذاكري", "my_tickets"),
            ("⚙️ الإدارة", "admin"),
        ],
        "data_models": [
            {"name": "Ticket", "fields": ["id", "user_id", "subject", "body", "status", "priority", "assignee"]},
            {"name": "TicketMessage", "fields": ["id", "ticket_id", "sender_id", "text", "created_at"]},
        ],
        "handlers": [
            {"name": "start", "type": "command", "triggers": ["/start"]},
            {"name": "new_ticket", "type": "conversation", "triggers": ["/new", "callback:new_ticket"]},
            {"name": "my_tickets", "type": "command", "triggers": ["/mytickets"]},
            {"name": "admin", "type": "command", "triggers": ["/admin"], "admin_only": True},
        ],
        "services": ["tickets", "assignment", "notifications"],
        "integrations": ["telegram", "database"],
        "optional_integrations": ["redis"],
    },
    "admin": {
        "signals_ar": [
            "إدارة مجموعة", "إدارة مجموعات", "بوت إدارة", "حظر", "كتم", "طرد",
            "ترحيب", "قواعد", "مشرف", "مشرفين", "تحذير", "فك الحظر", "فك الكتم",
            "مودريشن", "حماية مجموعة",
        ],
        "signals_en": [
            "moderation", "ban", "mute", "welcome", "group admin", "kick",
            "unban", "unmute", "warn", "group management", "moderator",
        ],
        "default_commands": [
            ("start", "تشغيل البوت", False),
            ("help", "المساعدة والأوامر", False),
            ("ban", "حظر عضو من المجموعة", True),
            ("unban", "فك حظر عضو", True),
            ("kick", "طرد عضو", True),
            ("mute", "كتم عضو", True),
            ("unmute", "فك كتم عضو", True),
            ("warn", "تحذير عضو", True),
            ("rules", "عرض قواعد المجموعة", False),
            ("setwelcome", "تعيين رسالة ترحيب", True),
            ("stats", "إحصائيات المجموعة", True),
        ],
        "default_buttons": [
            ("📜 القواعد", "rules"),
            ("📊 إحصائيات", "stats"),
            ("⚙️ الإعدادات", "settings"),
        ],
        "data_models": [
            {"name": "GroupSettings", "fields": ["chat_id", "welcome_text", "rules", "mute_duration", "warn_limit"]},
            {"name": "ModAction", "fields": ["id", "chat_id", "user_id", "action", "by_admin", "reason", "created_at"]},
            {"name": "UserWarn", "fields": ["chat_id", "user_id", "count", "last_reason"]},
        ],
        "handlers": [
            {"name": "start", "type": "command", "triggers": ["/start"]},
            {"name": "help", "type": "command", "triggers": ["/help"]},
            {"name": "ban", "type": "command", "triggers": ["/ban"], "admin_only": True},
            {"name": "unban", "type": "command", "triggers": ["/unban"], "admin_only": True},
            {"name": "kick", "type": "command", "triggers": ["/kick"], "admin_only": True},
            {"name": "mute", "type": "command", "triggers": ["/mute"], "admin_only": True},
            {"name": "unmute", "type": "command", "triggers": ["/unmute"], "admin_only": True},
            {"name": "warn", "type": "command", "triggers": ["/warn"], "admin_only": True},
            {"name": "rules", "type": "command", "triggers": ["/rules"]},
            {"name": "setwelcome", "type": "command", "triggers": ["/setwelcome"], "admin_only": True},
            {"name": "stats", "type": "command", "triggers": ["/stats"], "admin_only": True},
            {"name": "welcome", "type": "message", "triggers": ["new_chat_members"]},
        ],
        "services": ["moderation", "settings", "warns"],
        "integrations": ["telegram", "database"],
        "optional_integrations": [],
    },
    "assistant": {
        "signals_ar": ["مساعد", "أسئلة", "إجابة", "محادثة", "ذكاء"],
        "signals_en": ["assistant", "qa", "chatbot", "answer", "ai helper"],
        "default_commands": [
            ("start", "تشغيل", False),
            ("help", "مساعدة", False),
            ("clear", "مسح المحادثة", False),
        ],
        "default_buttons": [("💬 ابدأ محادثة", "chat"), ("🗑 مسح", "clear")],
        "data_models": [
            {"name": "Conversation", "fields": ["user_id", "messages", "updated_at"]},
        ],
        "handlers": [
            {"name": "start", "type": "command", "triggers": ["/start"]},
            {"name": "message", "type": "message", "triggers": ["text"]},
            {"name": "clear", "type": "command", "triggers": ["/clear"]},
        ],
        "services": ["conversation", "llm_gateway"],
        "integrations": ["telegram"],
        "optional_integrations": ["openai", "database"],
    },
    "document": {
        "signals_ar": ["pdf", "مستند", "تقرير", "تحويل", "ملف", "مصمم مستندات"],
        "signals_en": ["pdf", "document", "report", "convert", "file"],
        "default_commands": [
            ("start", "تشغيل", False),
            ("help", "مساعدة", False),
            ("new", "مستند جديد", False),
        ],
        "default_buttons": [("📄 مستند جديد", "new_doc"), ("📁 ملفاتي", "my_files")],
        "data_models": [
            {"name": "DocumentJob", "fields": ["id", "user_id", "status", "input_text", "output_path"]},
        ],
        "handlers": [
            {"name": "start", "type": "command", "triggers": ["/start"]},
            {"name": "new_doc", "type": "conversation", "triggers": ["/new", "callback:new_doc"]},
            {"name": "document", "type": "message", "triggers": ["document", "text"]},
        ],
        "services": ["document_pipeline", "storage"],
        "integrations": ["telegram"],
        "optional_integrations": ["s3", "database", "redis"],
    },
    "notification": {
        "signals_ar": ["إشعار", "بث", "تنبيه", "إعلان", "رسالة جماعية"],
        "signals_en": ["broadcast", "notification", "announce", "push"],
        "default_commands": [
            ("start", "تشغيل", False),
            ("subscribe", "اشتراك", False),
            ("unsubscribe", "إلغاء اشتراك", False),
            ("broadcast", "بث رسالة", True),
        ],
        "default_buttons": [("✅ اشتراك", "subscribe"), ("❌ إلغاء", "unsubscribe")],
        "data_models": [
            {"name": "Subscriber", "fields": ["user_id", "active", "joined_at"]},
            {"name": "Broadcast", "fields": ["id", "text", "sent_count", "created_at"]},
        ],
        "handlers": [
            {"name": "start", "type": "command", "triggers": ["/start"]},
            {"name": "subscribe", "type": "command", "triggers": ["/subscribe"]},
            {"name": "broadcast", "type": "command", "triggers": ["/broadcast"], "admin_only": True},
        ],
        "services": ["subscribers", "broadcast"],
        "integrations": ["telegram", "database"],
        "optional_integrations": ["redis"],
    },
    "game": {
        "signals_ar": ["لعبة", "نقاط", "تحدي", "مستوى", "ترتيب"],
        "signals_en": ["game", "score", "quiz", "leaderboard", "level"],
        "default_commands": [
            ("start", "تشغيل", False),
            ("play", "لعب", False),
            ("score", "نقاطي", False),
            ("top", "الترتيب", False),
        ],
        "default_buttons": [("🎮 العب", "play"), ("🏆 الترتيب", "top")],
        "data_models": [
            {"name": "Player", "fields": ["user_id", "score", "level"]},
            {"name": "GameSession", "fields": ["id", "user_id", "state", "score"]},
        ],
        "handlers": [
            {"name": "start", "type": "command", "triggers": ["/start"]},
            {"name": "play", "type": "command", "triggers": ["/play", "callback:play"]},
            {"name": "score", "type": "command", "triggers": ["/score"]},
        ],
        "services": ["game", "leaderboard"],
        "integrations": ["telegram", "database"],
        "optional_integrations": [],
    },
}

# ── Feature lexicon: phrase → structured feature tag ──────────────────────

FEATURE_LEXICON: list[tuple[list[str], str, str]] = [
    # (phrases, feature_id, category)
    (["سلة", "cart", "shopping cart"], "shopping_cart", "commerce"),
    (["دفع", "payment", "stripe", "checkout", "فوري", "تحويل بنكي"], "payments", "commerce"),
    (["منتجات", "catalog", "كتالوج", "products"], "product_catalog", "commerce"),
    (["طلبات", "orders", "طلب"], "order_management", "commerce"),
    (["مخزون", "stock", "inventory"], "inventory", "commerce"),
    (["أدمن", "admin", "لوحة إدارة", "لوحة تحكم", "admin panel"], "admin_panel", "admin"),
    (["إشعار", "notification", "تنبيه", "notify"], "notifications", "messaging"),
    (["بث", "broadcast", "رسالة جماعية"], "broadcast", "messaging"),
    (["ترحيب", "welcome"], "welcome_message", "group"),
    (["حظر", "ban", "كتم", "mute", "طرد", "kick"], "moderation", "group"),
    (["تذاكر", "ticket", "دعم فني", "support"], "ticketing", "support"),
    (["ملف", "file", "رفع", "upload", "pdf", "صورة"], "file_handling", "media"),
    (["قاعدة بيانات", "database", "postgres", "sqlite"], "database", "infra"),
    (["عدة مستخدمين", "concurrent", "scalability"], "concurrency", "infra"),
    (["طابور", "queue", "celery", "redis queue"], "task_queue", "infra"),
    (["عربي", "العربية", "rtl"], "arabic_rtl", "i18n"),
    (["إنجليزي", "english"], "english", "i18n"),
    (["اشتراك", "subscribe", "عضوية", "membership"], "subscriptions", "commerce"),
    (["نقاط", "score", "leaderboard", "ترتيب"], "gamification", "engagement"),
    (["محادثة", "conversation", "state", "wizard"], "conversation_state", "ux"),
    (["أزرار", "buttons", "inline keyboard", "قائمة"], "inline_buttons", "ux"),
    (["أوامر", "commands", "/start"], "bot_commands", "ux"),
]

# ── Data model field knowledge ────────────────────────────────────────────

COMMON_FIELDS: dict[str, list[str]] = {
    "user": ["id", "telegram_id", "username", "full_name", "language", "created_at"],
    "product": ["id", "name", "price", "description", "stock", "image_url", "category"],
    "order": ["id", "user_id", "items", "total", "status", "address", "phone", "created_at"],
    "ticket": ["id", "user_id", "subject", "body", "status", "priority", "assignee", "created_at"],
    "message": ["id", "chat_id", "user_id", "text", "created_at"],
}

# ── Integration knowledge ─────────────────────────────────────────────────

INTEGRATIONS: dict[str, dict[str, Any]] = {
    "telegram": {"required": True, "packages": ["python-telegram-bot>=21.0"]},
    "postgres": {"packages": ["asyncpg", "sqlalchemy[asyncio]"], "env": ["DATABASE_URL"]},
    "sqlite": {"packages": ["aiosqlite"], "env": []},
    "redis": {"packages": ["redis", "arq"], "env": ["REDIS_URL"]},
    "stripe": {"packages": ["stripe"], "env": ["STRIPE_SECRET_KEY"]},
    "s3": {"packages": ["boto3"], "env": ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "S3_BUCKET"]},
}

# ── Architecture rules (constraints the solver/generator must respect) ────

ARCHITECTURE_RULES: list[str] = [
    "If payments then require database and order_management",
    "If admin_panel then require admin command and admin_user_ids config",
    "If concurrency or task_queue then prefer redis queue",
    "If file_handling and production then prefer object storage",
    "Every bot must have /start and /help",
    "Inline buttons must map to callback handlers",
    "Conversation flows require state management",
    "Admin-only commands must check admin_ids",
    "Ecommerce requires Product + Cart + Order models",
    "Ticketing requires Ticket model and status machine",
]


def detect_archetype(text: str) -> str:
    """Score archetypes by signal density + massive lexicon; return best match."""
    from .lexicon_ar_en import score_domains

    t = text.lower()
    scores: dict[str, int] = {}
    for name, meta in BOT_ARCHETYPES.items():
        score = 0
        for s in meta.get("signals_ar", []) + meta.get("signals_en", []):
            if s.lower() in t:
                score += 2 if len(s) > 3 else 1
        scores[name] = score
    # lexicon boost
    for domain, sc in score_domains(text).items():
        scores[domain] = scores.get(domain, 0) + sc
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "custom"


def extract_feature_tags(text: str) -> list[dict[str, str]]:
    from .lexicon_ar_en import extract_features_fast

    # category map for known ids
    cat_map = {fid: cat for phrases, fid, cat in FEATURE_LEXICON}
    # also from FEATURE_PHRASES categories inferred
    default_cat = {
        "shopping_cart": "commerce", "payments": "commerce", "product_catalog": "commerce",
        "order_management": "commerce", "inventory": "commerce", "coupons": "commerce",
        "admin_panel": "admin", "notifications": "messaging", "broadcast": "messaging",
        "welcome_message": "group", "moderation": "group", "ticketing": "support",
        "file_handling": "media", "database": "infra", "concurrency": "infra",
        "task_queue": "infra", "arabic_rtl": "i18n", "english": "i18n",
        "subscriptions": "commerce", "gamification": "engagement",
        "conversation_state": "ux", "inline_buttons": "ux", "bot_commands": "ux",
        "multi_language": "i18n", "analytics": "ops", "auth": "security",
        "search": "ux", "ratings": "engagement", "shipping": "commerce",
        "invoicing": "commerce", "booking": "commerce", "crm": "ops",
    }
    found = []
    seen = set()
    # legacy lexicon
    for phrases, fid, cat in FEATURE_LEXICON:
        t = text.lower()
        if any(p.lower() in t for p in phrases) and fid not in seen:
            seen.add(fid)
            found.append({"id": fid, "category": cat})
    # massive lexicon
    for fid in extract_features_fast(text):
        if fid not in seen:
            seen.add(fid)
            found.append({"id": fid, "category": default_cat.get(fid, cat_map.get(fid, "general"))})
    return found


def enrich_from_archetype(archetype: str) -> dict[str, Any]:
    return dict(BOT_ARCHETYPES.get(archetype, {}))
