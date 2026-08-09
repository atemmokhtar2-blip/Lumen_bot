"""
AI Agent 7h Bot — Telegram interface for the Generation Engine.

Runs on Railway (or any host). Requires:
  TELEGRAM_BOT_TOKEN  — BotFather token
  Optional:
  ALLOWED_USER_IDS    — comma-separated Telegram user IDs (recommended)
  ALLOW_ALL_USERS=1   — explicit opt-in to accept ANY user (insecure; only when ALLOWED empty)
  OUTPUT_DIR          — where generated projects are written (default: /tmp/generated)
"""

from __future__ import annotations

import threading

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)

from bot_interface import (
    TELEGRAM_BOT_TOKEN,
    ALLOWED_USER_IDS,
    ALLOW_ALL_USERS,
    OUTPUT_DIR,
    PORT,
    logger,
    start_cmd,
    help_cmd,
    status_cmd,
    lang_cmd,
    handle_message,
    error_handler,
    start_health_server,
)


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        logger.error(
            "TELEGRAM_BOT_TOKEN is not set. "
            "Set it in Railway Variables or a local .env file."
        )
        raise SystemExit(1)

    logger.info("Starting AI Agent 7h Bot...")
    allowed_repr = (
        sorted(ALLOWED_USER_IDS)
        if ALLOWED_USER_IDS
        else ("ALL (ALLOW_ALL_USERS=1)" if ALLOW_ALL_USERS else "NONE (safe default)")
    )
    logger.info(
        "OUTPUT_DIR=%s | ALLOWED_USER_IDS=%s | PORT=%s",
        OUTPUT_DIR,
        allowed_repr,
        PORT,
    )

    # Railway / container health check
    threading.Thread(target=start_health_server, args=(PORT,), daemon=True).start()

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("lang", lang_cmd))
    app.add_handler(CommandHandler("language", lang_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    logger.info("Bot is running (polling)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
