"""
AI Agent 7h — Consumer Telegram bot + optional B2B API.

Modes:
  - Default: Telegram polling (consumer product)
  - ENABLE_API=1: also serves B2B HTTP API on PORT (generate/host/billing/dashboard)
  - python api_main.py: API-only process
"""

from __future__ import annotations

import os
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


def _start_b2b_api(port: int) -> None:
    from aiohttp import web
    from api.app import create_app

    app = create_app()
    logger.info("B2B API enabled on 0.0.0.0:%s", port)
    web.run_app(app, host="0.0.0.0", port=port, print=lambda *a, **k: None)


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        logger.error(
            "TELEGRAM_BOT_TOKEN is not set. "
            "Set it in Railway Variables or a local .env file."
        )
        raise SystemExit(1)

    logger.info("Starting AI Agent 7h Bot (consumer)...")
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

    enable_api = (os.getenv("ENABLE_API") or "1").strip().lower() not in {"0", "false", "no", "off"}
    if enable_api:
        threading.Thread(target=_start_b2b_api, args=(PORT,), daemon=True).start()
    else:
        threading.Thread(target=start_health_server, args=(PORT,), daemon=True).start()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("lang", lang_cmd))
    app.add_handler(CommandHandler("language", lang_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    logger.info("Telegram bot is running (polling)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
