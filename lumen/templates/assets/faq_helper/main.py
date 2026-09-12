"""Template: FAQ helper — static Q&A."""
from __future__ import annotations

import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("tpl.faq")

FAQ = {
    "ساعات": "نعمل من 9 ص إلى 6 م بتوقيت القاهرة.",
    "سعر": "الأسعار تظهر عبر قوالب المتجر؛ هنا FAQ عام.",
    "دعم": "راسل الدعم: support@example.com (قالب).",
}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "بوت الأسئلة الشائعة.\n/faq — القائمة\nأو اكتب كلمة: ساعات / سعر / دعم"
    )


async def faq(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lines = "\n".join(f"• {k}: {v}" for k, v in FAQ.items())
    await update.effective_message.reply_text(lines)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.effective_message.text or "").strip()
    for k, v in FAQ.items():
        if k in text:
            await update.effective_message.reply_text(v)
            return
    await update.effective_message.reply_text("لم أجد جوابًا. جرّب /faq")


def main() -> None:
    token = (os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        raise SystemExit("BOT_TOKEN missing")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("faq", faq))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    log.info("faq_helper template starting")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
