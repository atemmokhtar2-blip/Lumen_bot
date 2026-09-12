"""Template: quick diagnostic tools."""
from __future__ import annotations

import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("tpl.echo")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text("أدوات سريعة جاهزة. /id — معرّفك · /ping — فحص")


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text("pong ✅")


async def uid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    chat = update.effective_chat
    lines = []
    if u:
        lines.append(f"user_id: {u.id}")
        if u.username:
            lines.append(f"username: @{u.username}")
    if chat:
        lines.append(f"chat_id: {chat.id}")
    await update.effective_message.reply_text("\n".join(lines) or "لا بيانات")


def build_application() -> Application:
    token = (os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN missing")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("id", uid))
    return app


def main() -> None:
    app = build_application()
    log.info("echo_tools template starting")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
