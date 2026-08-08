"""Telegram command handlers (/start, /help, /status)."""

from __future__ import annotations

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from .config import OUTPUT_DIR
from .helpers import is_allowed


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_allowed(user.id if user else None):
        await update.message.reply_text("⛔ غير مصرح لك باستخدام هذا البوت.")
        return

    text = (
        "👋 *مرحباً بك في AI Agent 7h Bot*\n\n"
        "أنا محرك توليد بوتات تليجرام.\n"
        "أرسل لي وصفاً باللغة العربية أو الإنجليزية لما تريده، وسأولّد مشروعاً جاهزاً.\n\n"
        "*أمثلة:*\n"
        "• اعمل بوت متجر إلكتروني\n"
        "• بوت إدارة مجموعات مع نظام نقاط\n"
        "• Telegram bot for customer support with tickets\n\n"
        "الأوامر:\n"
        "/start — هذه الرسالة\n"
        "/status — حالة النظام\n"
        "/help — مساعدة\n\n"
        "✅ المحرك الرسمي (Formal Engine) يعمل — فهم حتمي + توليد كود نظيف."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start_cmd(update, context)


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_allowed(user.id if user else None):
        await update.message.reply_text("⛔ غير مصرح.")
        return

    try:
        from telegram_bot_engine import bootstrap
        registry, orchestrator, manager = bootstrap()
        engine_count = len(getattr(registry, "_engines", {}) or getattr(registry, "engines", {}) or {})
        if not engine_count:
            try:
                engine_count = len(manager._engines) if hasattr(manager, "_engines") else "?"
            except Exception:
                engine_count = "?"
        msg = (
            f"✅ النظام يعمل\n"
            f"• المحركات المسجّلة: {engine_count}\n"
            f"• مجلد الإخراج: `{OUTPUT_DIR}`\n"
            f"• المحرك النشط: Formal Engine (فهم + توليد)."
        )
    except Exception as e:
        msg = f"⚠️ خطأ أثناء فحص الحالة:\n`{e}`"
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
