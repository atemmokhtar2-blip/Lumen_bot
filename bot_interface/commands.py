from .capability_boundaries import get_help_text
"""Telegram command handlers (/start, /help, /status, /lang)."""

from __future__ import annotations

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from .config import OUTPUT_DIR
from .helpers import is_allowed
from .i18n import get_lang, set_lang, t, SUPPORTED


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_allowed(user.id if user else None):
        lang = get_lang(user, context)
        await update.message.reply_text(t("not_authorized", lang))
        return

    lang = get_lang(user, context)
    # First interaction: store detected language so later messages stay consistent
    if context.user_data is not None and "lang" not in context.user_data:
        set_lang(context, lang)

    await update.message.reply_text(
        t("start_welcome", lang),
        parse_mode=ParseMode.MARKDOWN,
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start_cmd(update, context)


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    lang = get_lang(user, context)
    if not is_allowed(user.id if user else None):
        await update.message.reply_text(t("not_authorized_short", lang))
        return

    try:
        from telegram_bot_engine import bootstrap
        registry, orchestrator, manager = bootstrap()
        engine_count = len(
            getattr(registry, "_engines", {}) or getattr(registry, "engines", {}) or {}
        )
        if not engine_count:
            try:
                engine_count = len(manager._engines) if hasattr(manager, "_engines") else "?"
            except Exception:
                engine_count = "?"
        msg = t(
            "status_ok",
            lang,
            engine_count=engine_count,
            output_dir=str(OUTPUT_DIR),
        )
    except Exception as e:
        msg = t("status_error", lang, error=str(e))
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def lang_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Change interface language: /lang en | /lang ar"""
    user = update.effective_user
    lang = get_lang(user, context)
    if not is_allowed(user.id if user else None):
        await update.message.reply_text(t("not_authorized_short", lang))
        return

    args = (context.args or []) if context else []
    if not args:
        await update.message.reply_text(
            t("lang_usage", lang, lang=lang),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    requested = (args[0] or "").strip().lower()
    if requested not in SUPPORTED:
        await update.message.reply_text(t("lang_unsupported", lang))
        return

    new_lang = set_lang(context, requested)
    await update.message.reply_text(
        t("lang_changed", new_lang, lang=new_lang),
        parse_mode=ParseMode.MARKDOWN,
    )
