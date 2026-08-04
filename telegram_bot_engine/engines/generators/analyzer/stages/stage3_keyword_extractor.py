"""
Stage 3 — Keyword extraction.

Responsibilities:
    * Scan all tokens (and multi-word phrases) for keywords that map to
      known categories.
    * Produce a list of :class:`KeywordMatch` objects with category,
      position, synonyms, and confidence.
    * Categories: ``"bot_type"``, ``"feature"``, ``"technology"``,
      ``"database"``, ``"runtime"``, ``"framework"``.

The keyword dictionary is bilingual (Arabic + English).  Each keyword
entry maps a set of surface forms (synonyms) to a canonical keyword and
a category.
"""

from __future__ import annotations

from typing import Dict, List, Set

from ..analysis_report import AnalysisReport, KeywordMatch


# ---------------------------------------------------------------------------#
# Keyword dictionary
# ---------------------------------------------------------------------------#
# Each entry: (canonical, category, [surface_forms], confidence)
# Arabic surface forms are included alongside their English counterparts.

_KEYWORDS: List[tuple] = [
    # --- bot_type keywords ------------------------------------------------
    ("bot", "bot_type",
     ["bot", "بوت", "روبوت", "бот"], 1.0),
    ("telegram", "bot_type",
     ["telegram", "تيليجرام", "تيليغرام", "تلجرام"], 1.0),
    ("store", "bot_type",
     ["store", "shop", "ecommerce", "e-commerce", "متجر", "متجري", "متجر"], 0.95),
    ("group_admin", "bot_type",
     ["admin", "manage", "management", "moderate", "moderation",
      "group", "ادارة", "إدارة", "اداره", "مدير", "مشرف", "تخكيم"], 0.9),
    ("downloader", "bot_type",
     ["download", "downloader", "تحميل", "تحميلات", "يوتيوب", "youtube",
      "video", "فيديو", "ميديا", "media"], 0.9),
    ("ai_assistant", "bot_type",
     ["ai", "gpt", "chatgpt", "assistant", "intelligent", "ذكاء",
      "اصطناعي", "ذكاء اصطناعي", "مساعد", "ذكي"], 0.9),
    ("task_manager", "bot_type",
     ["task", "todo", "reminder", "tasks", "مهمة", "مهام", "تذكير"], 0.85),
    ("quiz", "bot_type",
     ["quiz", "poll", "survey", "استبيان", "استفتاء", "اختبار"], 0.85),
    ("news", "bot_type",
     ["news", "rss", "اخبار", "أخبار", "نشرة"], 0.85),
    ("weather", "bot_type",
     ["weather", "طقس", "الأحوال الجوية"], 0.85),
    ("currency", "bot_type",
     ["currency", "price", "اسعار", "أسعار", "صرف"], 0.85),

    # --- feature keywords -------------------------------------------------
    ("database", "feature",
     ["database", "db", "storage", "store data", "قاعدة", "قاعدة بيانات",
      "بيانات", "تخزين"], 0.9),
    ("admin_panel", "feature",
     ["panel", "dashboard", "لوحة", "لوحة تحكم", "تحكم", "ادارة"], 0.85),
    ("payments", "feature",
     ["payment", "pay", "checkout", "billing", "invoice",
      "دفع", "مدفوعات", "فاتورة", "دفع"], 0.9),
    ("authentication", "feature",
     ["auth", "login", "authenticate", "otp", "2fa",
      "تسجيل", "تسجيل دخول", "مصادقة", "توثيق"], 0.85),
    ("scheduling", "feature",
     ["schedule", "cron", "calendar", "جداول", "جدولة", "مجدول"], 0.8),
    ("notifications", "feature",
     ["notification", "notify", "alert", "إشعار", "إشعارات", "تنبيه"], 0.85),
    ("file_upload", "feature",
     ["upload", "file upload", "attachment", "رفع", "مرفق", "مرفقات"], 0.85),
    ("search", "feature",
     ["search", "query", "find", "بحث", "بحث عن"], 0.8),
    ("multi_language", "feature",
     ["language", "multilingual", "i18n", "translation",
      "لغات", "متعدد اللغات", "ترجمة"], 0.8),
    ("rate_limit", "feature",
     ["rate", "limit", "throttle", "حد", "محدود", "كوتا"], 0.8),
    ("logging", "feature",
     ["log", "logging", "audit", "سجل", "سجلات", "تسجيل"], 0.8),
    ("user_management", "feature",
     ["user", "users", "member", "members", "مستخدم", "مستخدمين",
      "اعضاء", "أعضاء"], 0.85),
    ("content_management", "feature",
     ["content", "post", "article", "محتوى", "مقال", "مقالات"], 0.8),
    ("analytics", "feature",
     ["analytics", "statistics", "stats", "تحليلات", "إحصائيات"], 0.8),
    ("webhook", "feature",
     ["webhook", "webhooks", "ويب هوك"], 0.85),
    ("polling", "feature",
     ["polling", "long polling", "بولينج"], 0.85),
    ("inline_mode", "feature",
     ["inline", "inline mode", "انلاين"], 0.8),
    ("welcome", "feature",
     ["welcome", "greeting", "ترحيب", "ترحيبات"], 0.75),
    ("ban", "feature",
     ["ban", "kick", "mute", "warn", "warning", "حظر", "طرد", "كتم", "تحذير"], 0.8),
    ("subscription", "feature",
     ["subscribe", "subscription", "newsletter", "اشتراك", "اشتراكات"], 0.8),
    ("shopping_cart", "feature",
     ["cart", "shopping cart", "basket", "سلة", "سلة مشتريات"], 0.85),
    ("product_catalog", "feature",
     ["catalog", "catalogue", "products", "product list",
      "كتالوج", "منتجات", "قائمة منتجات"], 0.85),
    ("order_management", "feature",
     ["order", "orders", "طلب", "طلبات", "إدارة الطلبات"], 0.85),
    ("ai_chat", "feature",
     ["chat", "conversation", "chatbot", "محادثة", "دردشة"], 0.8),
    ("media_download", "feature",
     ["download", "تحميل", "تنزيل", "تنزيلات"], 0.85),
    # Simple text reply / echo bots (very common first requests)
    ("message_handler", "feature",
     ["reply", "echo", "respond", "message handler", "text reply",
      "بيرد", "يرد", "رد", "يردو", "رسالة", "هاي", "hello", "hi"], 0.9),

    # --- technology keywords ----------------------------------------------
    ("python", "technology",
     ["python", "بايثون"], 1.0),
    ("nodejs", "technology",
     ["node", "nodejs", "node.js", "نود"], 0.9),
    ("sqlite", "database",
     ["sqlite", "sqlite3", "إس كيو لايت"], 0.95),
    ("postgres", "database",
     ["postgres", "postgresql", "pg", "بوسطgres", "بوسطجريس"], 0.95),
    ("mysql", "database",
     ["mysql", "mariadb", "ماي إس كيو ال"], 0.9),
    ("mongodb", "database",
     ["mongo", "mongodb", "مونجو"], 0.9),
    ("redis", "database",
     ["redis", "ريديس"], 0.9),
    ("docker", "runtime",
     ["docker", "container", "حاوية", "دوكر"], 0.9),
    ("python_telegram_bot", "framework",
     ["python-telegram-bot", "ptb", "python telegram bot"], 0.9),
    ("aiogram", "framework",
     ["aiogram", "ايوجرام"], 0.9),
    ("pyrogram", "framework",
     ["pyrogram", "بايروجرام"], 0.9),
    ("telethon", "framework",
     ["telethon", "تيليثون"], 0.9),
    ("flask", "framework",
     ["flask", "فلاسك"], 0.85),
    ("fastapi", "framework",
     ["fastapi", "فاست إي بي آي"], 0.85),
    ("openai", "technology",
     ["openai", "gpt-4", "gpt3", "gpt4", "chatgpt",
      "أوبن إيه آي", "جي بي تي"], 0.9),
    ("requests", "technology",
     ["requests", "httpx", "aiohttp"], 0.85),
    ("sqlalchemy", "technology",
     ["sqlalchemy", "orm", "sqlalchemy"], 0.85),
    ("pillow", "technology",
     ["pillow", "pil", "image processing", "معالجة الصور"], 0.8),
    ("yt-dlp", "technology",
     ["yt-dlp", "ytdlp", "youtube-dl", "youtube dl"], 0.9),
    ("ffmpeg", "technology",
     ["ffmpeg", "اف اف ام بي جي"], 0.85),
]


# ---------------------------------------------------------------------------#
# Matching
# ---------------------------------------------------------------------------#

def _build_index(keywords: List[tuple]) -> Dict[str, tuple]:
    """Build a lookup index mapping each surface form (lowercased) to
    (canonical, category, surface_forms, confidence)."""
    index: Dict[str, tuple] = {}
    for entry in keywords:
        canonical, category, surfaces, confidence = entry
        for surface in surfaces:
            key = surface.lower()
            if key not in index:
                index[key] = (canonical, category, surfaces, confidence)
    return index


def run(state: Dict, report: AnalysisReport) -> List[str]:
    """Extract keywords from the segmented tokens.

    Writes:
        report.keywords  ← list of KeywordMatch.
        state["keyword_canonicals"] ← set of canonical keywords found.
    """
    text = report.cleaned_request.lower()
    tokens = report.tokens

    index = _build_index(_KEYWORDS)
    matched: Dict[str, KeywordMatch] = {}  # canonical → KeywordMatch

    warnings: List[str] = []

    # First pass: match multi-word phrases in the full text
    for surface, entry in index.items():
        if " " in surface:
            # Multi-word phrase
            if surface in text:
                canonical, category, surfaces, confidence = entry
                if canonical not in matched:
                    pos = text.index(surface)
                    matched[canonical] = KeywordMatch(
                        keyword=canonical,
                        category=category,
                        synonyms=[s for s in surfaces if s.lower() != surface],
                        position=pos,
                        confidence=confidence,
                    )

    # Second pass: match single-word tokens
    for idx, token in enumerate(tokens):
        if token.role in ("filler", "punctuation"):
            continue
        key = token.normalized.lower()
        if key in index:
            entry = index[key]
            canonical, category, surfaces, confidence = entry
            if canonical not in matched:
                matched[canonical] = KeywordMatch(
                    keyword=canonical,
                    category=category,
                    synonyms=[s for s in surfaces if s.lower() != key],
                    position=idx,
                    confidence=confidence,
                )
            else:
                # Already matched — extend synonyms if new surface form
                existing = matched[canonical]
                if key not in [s.lower() for s in existing.synonyms] and key != existing.keyword:
                    existing.synonyms.append(token.normalized)

    # Sort by position
    report.keywords = sorted(matched.values(), key=lambda k: k.position)

    state["keyword_canonicals"] = set(matched.keys())

    if not report.keywords:
        warnings.append("No keywords were matched in the request.")

    return warnings


__all__ = ["run"]
