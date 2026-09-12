"""Template: clean welcome bot."""
from __future__ import annotations

import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("tpl.welcome")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    name = ""
    if update.effective_user:
        name = update.effective_user.first_name or update.effective_user.username or ""
    text = "أهلًا" + (f" {name}" if name else "") + "!\n"
    text += "هذا بوت ترحيب جاهز من قوالب Lumen.\n"
    text += "استخدم /help لمعرفة الأوامر."
    await update.effective_message.reply_text(text)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text("/start — ترحيب\n/help — هذه الرسالة")


def main() -> None:
    token = (os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        raise SystemExit("BOT_TOKEN missing")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    log.info("welcome_bot template starting")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
