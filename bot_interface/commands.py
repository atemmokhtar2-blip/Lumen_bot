"""Telegram command handlers (/start, /help, /status, /lang)."""
from __future__ import annotations

from pathlib import Path

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from .capability_boundaries import get_help_text
from .config import OUTPUT_DIR
from .helpers import is_allowed, safe_reply_text
from .i18n import get_lang, set_lang, t, SUPPORTED
from .session_store import get_session_store


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if not message:
        return
    if not is_allowed(user.id if user else None):
        lang = get_lang(user, context)
        await message.reply_text(t("not_authorized", lang))
        return

    lang = get_lang(user, context)
    if context.user_data is not None and "lang" not in context.user_data:
        set_lang(context, lang)

    # Ensure user exists in Mongo (plan = free) on first contact
    try:
        if user:
            from b2b_platform.mongo_users import get_or_create_by_telegram
            import os
            if (os.getenv("MONGODB_URI") or "").strip():
                name = (
                    getattr(user, "full_name", None)
                    or getattr(user, "username", None)
                    or f"tg_{user.id}"
                )
                get_or_create_by_telegram(int(user.id), name=str(name)[:120], plan_id="free")
    except Exception:
        pass

    # Restore session so pending token flow survives /start after restart
    try:
        if user and context.user_data is not None:
            for k, v in (get_session_store().load(int(user.id)) or {}).items():
                context.user_data.setdefault(k, v)
    except Exception:
        pass

    # Brand welcome (image + caption) — same for every new user
    caption = (
        "مرحباً بك في Maestro 👋\n"
        "أنا هنا لمساعدتك في بناء وإدارة مشاريع البوتات بكل سهولة وذكاء."
    )
    welcome_img = Path(__file__).resolve().parent / "assets" / "welcome.jpg"
    sent = False
    if welcome_img.is_file():
        try:
            from telegram import InputFile
            with welcome_img.open("rb") as fh:
                await message.reply_photo(
                    photo=InputFile(fh, filename="welcome.jpg"),
                    caption=caption,
                )
            sent = True
        except Exception:
            sent = False
    if not sent:
        try:
            await message.reply_text(caption)
        except Exception:
            await safe_reply_text(message, caption)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return
    user = update.effective_user
    if not is_allowed(user.id if user else None):
        await message.reply_text("⛔ غير مصرح.")
        return
    text = get_help_text()
    try:
        await message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await message.reply_text(text)


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if not message:
        return
    if not is_allowed(user.id if user else None):
        await message.reply_text("⛔ غير مصرح.")
        return
    pending = {}
    if context.user_data:
        for k in ("pending_run", "pending_deploy", "pending_live_run", "active_repo"):
            if context.user_data.get(k):
                pending[k] = "yes"
    lines = [
        "📊 حالة الجلسة",
        f"• user_id: {user.id if user else '?'}",
        f"• OUTPUT_DIR: {OUTPUT_DIR}",
        f"• pending: {', '.join(pending) if pending else 'لا يوجد'}",
    ]
    await message.reply_text("\n".join(lines))


async def lang_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if not message:
        return
    args = (context.args or []) if context else []
    if args and args[0].lower() in SUPPORTED:
        set_lang(context, args[0].lower())
        await message.reply_text(f"Language set to {args[0].lower()}")
        return
    await message.reply_text("Usage: /lang ar | /lang en")


async def handle_non_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Voice/photo/sticker/document — never silent."""
    message = update.effective_message
    if not message:
        return
    await message.reply_text(
        "حالياً أستقبل النص فقط.\n"
        "اكتب وصف البوت أو استخدم /help — الصور والصوت غير مدعومين بعد."
    )
