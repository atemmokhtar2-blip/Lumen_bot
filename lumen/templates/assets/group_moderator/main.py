"""Template: group moderator — welcome + basic commands."""
from __future__ import annotations

import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("tpl.moderator")

RULES = "قوانين المجموعة: الاحترام، لا سبام، التزم بتعليمات المشرفين."


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text("مشرف المجموعات جاهز. /rules — القوانين.")


async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(RULES)


async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    for m in update.message.new_chat_members or []:
        name = m.full_name or m.username or "عضو"
        await update.effective_message.reply_text(f"مرحبًا {name}! اقرأ /rules")


def main() -> None:
    token = (os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        raise SystemExit("BOT_TOKEN missing")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("rules", rules))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    log.info("group_moderator template starting")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
