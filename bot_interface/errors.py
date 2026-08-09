"""Global error handler for the Telegram application."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from .config import logger
from .i18n import get_lang, t


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling update: %s", context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            user = update.effective_user
            lang = get_lang(user, context)
            await update.effective_message.reply_text(t("internal_error", lang))
        except Exception:
            pass
