"""
Formal Knowledge Base — dense structured knowledge for deep understanding.

Signal lexicon for soft bot_type labeling and feature tags.
Never injects default_commands, handlers, or domain service packs into contracts.
"""

from __future__ import annotations

from typing import Any

# ── Bot archetypes: signals → canonical type + default structure ──────────

# Soft labels only — signals for classification. NO default_commands/handlers/services.
BOT_ARCHETYPES: dict[str, dict[str, Any]] = {
    "ecommerce": {
        "signals_ar": ["متجر", "منتج", "سلة", "طلب", "شراء", "تجارة"],
        "signals_en": ["shop", "product", "cart", "order", "ecommerce", "store"],
    },
    "ticketing": {
        "signals_ar": ["تذكرة", "دعم", "شكوى", "تذاكر"],
        "signals_en": ["ticket", "support", "helpdesk"],
    },
    "admin": {
        "signals_ar": ["إدارة", "أدمن", "مشرف", "لوحة"],
        "signals_en": ["admin", "moderation", "panel"],
    },
    "assistant": {
        "signals_ar": ["مساعد", "محادثة", "ذكاء"],
        "signals_en": ["assistant", "chatbot", "conversation"],
    },
    "document": {
        "signals_ar": ["مستند", "ملف", "وثيقة", "pdf"],
        "signals_en": ["document", "file", "pdf"],
    },
    "notification": {
        "signals_ar": ["إشعار", "تنبيه", "اشتراك"],
        "signals_en": ["notification", "alert", "subscribe"],
    },
    "game": {
        "signals_ar": ["لعبة", "نقاط", "ترتيب"],
        "signals_en": ["game", "score", "leaderboard"],
    },
    "booking": {
        "signals_ar": ["حجز", "موعد", "جدول"],
        "signals_en": ["booking", "appointment", "schedule"],
    },
    "community": {
        "signals_ar": ["مجموعة", "أعضاء", "مجتمع"],
        "signals_en": ["community", "group", "members"],
    },
}

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
    """Deprecated — returns signals only, never command/handler packs."""
    meta = BOT_ARCHETYPES.get(archetype, {})
    return {
        "signals_ar": list(meta.get("signals_ar") or []),
        "signals_en": list(meta.get("signals_en") or []),
    }
