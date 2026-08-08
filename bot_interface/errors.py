"""Global error handler for the Telegram application."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from .config import logger


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling update: %s", context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "حدث خطأ داخلي. حاول مرة أخرى لاحقاً."
            )
        except Exception:
            pass
