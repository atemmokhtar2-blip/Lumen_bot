"""Global error handler for the Telegram application."""

from __future__ import annotations

from telegram import Update
from telegram.error import Conflict, NetworkError, RetryAfter, TimedOut
from telegram.ext import ContextTypes

from .config import logger
from .i18n import get_lang, t


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    # 409 Conflict = another process is polling the same token.
    if isinstance(err, Conflict):
        logger.error(
            "Telegram Conflict (another getUpdates is active). "
            "Ensure only ONE replica runs the bot, then redeploy. detail=%s",
            err,
        )
        return
    if isinstance(err, (TimedOut, NetworkError, RetryAfter)):
        logger.warning("Transient Telegram error: %s", type(err).__name__)
        return
    logger.exception(
        "Exception while handling update: %s:%s",
        type(err).__name__ if err is not None else "None",
        str(err)[:300] if err is not None else "",
    )
    if isinstance(update, Update) and update.effective_message:
        try:
            user = update.effective_user
            lang = get_lang(user, context)
            # Keep user text generic; full traceback stays in Deploy Logs only
            await update.effective_message.reply_text(t("internal_error", lang))
        except Exception:
            pass
