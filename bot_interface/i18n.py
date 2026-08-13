"""Lightweight i18n for the Telegram bot interface.

Goal: make the bot global — Arabic + English first, easy to extend.

Usage:
    from .i18n import t, get_lang, set_lang

    lang = get_lang(user, context)
    await message.reply_text(t("not_authorized", lang))
"""

from __future__ import annotations

from typing import Any, Optional

# Supported languages (ISO 639-1). Add more by extending STRINGS.
SUPPORTED = ("en", "ar")
DEFAULT_LANG = "en"  # Global default

STRINGS: dict[str, dict[str, str]] = {
    # ── Auth / access ──────────────────────────────────────────────
    "not_authorized": {
        "en": "⛔ You are not authorized to use this bot.",
        "ar": "⛔ غير مصرح لك باستخدام هذا البوت.",
    },
    "not_authorized_short": {
        "en": "⛔ Not authorized.",
        "ar": "⛔ غير مصرح.",
    },
    "rate_limited": {
        "en": "⏳ You exceeded the rate limit. Please wait a minute and try again.",
        "ar": "⏳ تجاوزت الحد المسموح من الطلبات. انتظر دقيقة ثم حاول مرة أخرى.",
    },
    "internal_error": {
        "en": "An internal error occurred. Please try again later.",
        "ar": "حدث خطأ داخلي. حاول مرة أخرى لاحقاً.",
    },

    # ── /start & /help ─────────────────────────────────────────────
    "start_welcome": {
        "en": (
            "👋 *Welcome to AI Agent 7h Bot*\n\n"
            "I am a Telegram bot generation engine.\n"
            "Send me a description in any language of what you want, "
            "and I will generate a ready project.\n\n"
            "*Examples:*\n"
            "• Create an e-commerce bot\n"
            "• Group management bot with points system\n"
            "• Customer support bot with tickets\n\n"
            "*Commands:*\n"
            "/start — this message\n"
            "/status — system status\n"
            "/help — help\n"
            "/lang — change language (en / ar)\n\n"
            "✅ Active engine: Execution Planner + Plan-driven Codegen (AI)."
        ),
        "ar": (
            "👋 *مرحباً بك في AI Agent 7h Bot*\n\n"
            "أنا محرك توليد بوتات تليجرام.\n"
            "أرسل لي وصفاً بأي لغة لما تريده، وسأولّد مشروعاً جاهزاً.\n\n"
            "*أمثلة:*\n"
            "• اعمل بوت متجر إلكتروني\n"
            "• بوت إدارة مجموعات مع نظام نقاط\n"
            "• Telegram bot for customer support with tickets\n\n"
            "*الأوامر:*\n"
            "/start — هذه الرسالة\n"
            "/status — حالة النظام\n"
            "/help — مساعدة\n"
            "/lang — تغيير اللغة (en / ar)\n\n"
            "✅ المحرك النشط: Execution Planner + Plan-driven Codegen (AI)."
        ),
    },

    # ── /status ────────────────────────────────────────────────────
    "status_ok": {
        "en": (
            "✅ System is running\n"
            "• Registered engines: {engine_count}\n"
            "• Output directory: `{output_dir}`\n"
            "• Active engine: Execution Planner + Plan-driven Codegen."
        ),
        "ar": (
            "✅ النظام يعمل\n"
            "• المحركات المسجّلة: {engine_count}\n"
            "• مجلد الإخراج: `{output_dir}`\n"
            "• المحرك النشط: Execution Planner + Plan-driven Codegen."
        ),
    },
    "status_error": {
        "en": "⚠️ Error while checking status:\n`{error}`",
        "ar": "⚠️ خطأ أثناء فحص الحالة:\n`{error}`",
    },

    # ── /lang ──────────────────────────────────────────────────────
    "lang_usage": {
        "en": "🌐 Language: *{lang}*\nUsage: `/lang en` or `/lang ar`",
        "ar": "🌐 اللغة: *{lang}*\nالاستخدام: `/lang en` أو `/lang ar`",
    },
    "lang_changed": {
        "en": "✅ Language set to *{lang}*.",
        "ar": "✅ تم تعيين اللغة إلى *{lang}*.",
    },
    "lang_unsupported": {
        "en": "⚠️ Unsupported language. Available: en, ar",
        "ar": "⚠️ لغة غير مدعومة. المتاح: en, ar",
    },

    # ── Live run / deploy ──────────────────────────────────────────
    "live_checking_token": {
        "en": "🔐 1/4 Verifying token...",
        "ar": "🔐 1/4 التحقق من التوكن...",
    },
    "live_installing": {
        "en": "📦 2/4 Installing dependencies (may take a minute)...",
        "ar": "📦 2/4 تثبيت التبعيات (قد يستغرق دقيقة أو أكثر)...",
    },
    "live_healing": {
        "en": "🔧 3/4 Auto-repair if needed...",
        "ar": "🔧 3/4 إصلاح تلقائي إن لزم...",
    },
    "live_starting": {
        "en": "🚀 4/4 Starting the bot and checking boot...",
        "ar": "🚀 4/4 تشغيل البوت وفحص الإقلاع...",
    },
    "live_working": {
        "en": "{phase}\n⏳ {elapsed}s elapsed — still working...",
        "ar": "{phase}\n⏳ مرّ {elapsed}ث — لسه شغال، متقلقش.",
    },
    "live_run_failed": {
        "en": "❌ Live run failed: {error}",
        "ar": "❌ فشل التشغيل الحي: {error}",
    },
    "live_deploy_checking": {
        "en": "🔐 Verifying token and starting Live Deployment...",
        "ar": "🔐 جاري التحقق من التوكن وتشغيل Live Deployment...",
    },
    "live_deploy_failed": {
        "en": "❌ Live Deployment failed: {error1}\nfallback: {error2}",
        "ar": "❌ فشل Live Deployment: {error1}\nfallback: {error2}",
    },

    # ── Generation flow ────────────────────────────────────────────
    "gen_working": {
        "en": "⏳ Translating description and generating project (Execution Planner + Codegen)...",
        "ar": "⏳ جاري ترجمة الوصف وتوليد المشروع (Execution Planner + Codegen)...",
    },
    "host_starting": {
        "en": "🚀 Starting long-running hosting...",
        "ar": "🚀 جاري بدء الاستضافة (عملية طويلة الأمد)...",
    },
    "host_failed": {
        "en": "❌ Hosting failed: {error}",
        "ar": "❌ فشل الاستضافة: {error}",
    },
    "clone_with_token": {
        "en": "🔑 Re-cloning repository with token...",
        "ar": "🔑 جاري إعادة سحب المستودع بالتوكن...",
    },
    "clone_token_failed": {
        "en": "❌ Clone with token failed: {error}",
        "ar": "❌ فشل السحب بالتوكن: {error}",
    },
    "clone_ok": {
        "en": "✅ Private repository cloned successfully",
        "ar": "✅ تم سحب المستودع الخاص بنجاح",
    },
    "understanding_repo": {
        "en": "🔍 Understanding the repository...",
        "ar": "🔍 جاري فهم المستودع...",
    },
    "send_bot_token_hint": {
        "en": "🚀 *For a real run:* send the bot token from @BotFather",
        "ar": "🚀 *للتشغيل الحقيقي:* أرسل توكن البوت من @BotFather",
    },
}


def normalize_lang(code: Optional[str]) -> str:
    """Map Telegram language_code (e.g. en-US, ar) to our supported codes."""
    if not code:
        return DEFAULT_LANG
    base = code.strip().lower().replace("_", "-").split("-")[0]
    if base in SUPPORTED:
        return base
    # Common aliases
    if base in ("ara", "arz"):
        return "ar"
    return DEFAULT_LANG


def get_lang(user=None, context=None) -> str:
    """Resolve language preference.

    Priority:
      1. context.user_data['lang'] (explicit /lang choice)
      2. user.language_code from Telegram
      3. DEFAULT_LANG (en — global)
    """
    if context is not None:
        try:
            stored = (context.user_data or {}).get("lang")
            if stored in SUPPORTED:
                return stored
        except Exception:
            pass
    if user is not None:
        return normalize_lang(getattr(user, "language_code", None))
    return DEFAULT_LANG


def set_lang(context, lang: str) -> str:
    """Persist language choice on the user session. Returns normalized lang."""
    lang = normalize_lang(lang)
    if context is not None and context.user_data is not None:
        context.user_data["lang"] = lang
    return lang


def t(key: str, lang: Optional[str] = None, **kwargs: Any) -> str:
    """Translate *key* into *lang*. Falls back to English then to the key itself."""
    lang = normalize_lang(lang) if lang else DEFAULT_LANG
    entry = STRINGS.get(key) or {}
    text = entry.get(lang) or entry.get("en") or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text
