"""Run the Spec Builder Telegram bot (zero-AI).

Usage:
  export TELEGRAM_BOT_TOKEN=...
  export BUILDER_OUT_DIR=/path/to/output   # optional
  python -m telegram_bot_engine.spec_core.builder_app.main
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from telegram import BotCommand, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from telegram_bot_engine.spec_core.builder_app import handlers

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
logger = logging.getLogger("spec_builder")


async def _post_init(app: Application) -> None:
    await app.bot.set_my_commands(
        [
            BotCommand("start", "بدء البنّاء"),
            BotCommand("help", "مساعدة"),
            BotCommand("summary", "ملخص الإعداد"),
        ]
    )


def build_application() -> Application:
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN")
    out = (os.getenv("BUILDER_OUT_DIR") or "").strip()
    app = Application.builder().token(token).post_init(_post_init).build()
    if out:
        app.bot_data["builder_out_dir"] = Path(out)
    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("help", handlers.help_cmd))
    app.add_handler(CommandHandler("summary", handlers.summary_cmd))
    app.add_handler(CallbackQueryHandler(handlers.on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.on_text))
    return app


def main() -> None:
    logger.info("starting Spec Builder bot")
    build_application().run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
