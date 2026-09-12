"""Template: simple shop assistant — catalog + order note."""
from __future__ import annotations

import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("tpl.shop")

PRODUCTS = (
    "1) باقة أساسية — 10$\n"
    "2) باقة احترافية — 25$\n"
    "3) دعم شهري — 40$\n"
    "اكتب: أطلب 1 أو أطلب 2 …"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text("مساعد المتجر جاهز.\n/catalog — المنتجات")


async def catalog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(PRODUCTS)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.effective_message.text or "").strip()
    if text.startswith("أطلب") or text.startswith("اطلب") or text.lower().startswith("order"):
        await update.effective_message.reply_text(
            "تم استلام طلبك: " + text + "\nسيتواصل معك البائع قريبًا (قالب تجريبي)."
        )
        return
    await update.effective_message.reply_text("استخدم /catalog أو اكتب: أطلب 1")


def main() -> None:
    token = (os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        raise SystemExit("BOT_TOKEN missing")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("catalog", catalog))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    log.info("shop_assistant template starting")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
