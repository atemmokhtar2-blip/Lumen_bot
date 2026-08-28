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

    # Persist user on every /start (create or refresh last_seen — even after bot delete)
    try:
        if user:
            from lumen.bot.middlewares.mongo_sync import ensure_mongo_user
            ensure_mongo_user(user)
    except Exception:
        pass

    # Restore session so pending token flow survives /start after restart
    try:
        if user and context.user_data is not None:
            for k, v in (get_session_store().load(int(user.id)) or {}).items():
                context.user_data.setdefault(k, v)
    except Exception:
        pass

    # Engine UI state → HOME + live facts + real keyboard
    from lumen.engine.services.ui_state.controller import buttons_for_phase
    from lumen.engine.services.ui_state.models import EngineUiPhase, EngineUiState
    from lumen.engine.services.ui_state.render import render_message
    from lumen.bot.ui.facts import gather_ui_facts
    from lumen.bot.ui.keyboards import build_inline_keyboard
    from lumen.bot.ui.state_store import load_ui_state, persist_ui_session, save_ui_state

    ud = context.user_data if context.user_data is not None else {}
    ui = load_ui_state(ud)
    ui.phase = EngineUiPhase.HOME
    ui.last_action = "start"
    save_ui_state(ud, ui)
    uid = int(user.id) if user else 0
    if uid:
        persist_ui_session(uid, dict(ud))

    facts = gather_ui_facts(uid, ud)
    caption = render_message(ui, facts)
    markup = build_inline_keyboard(buttons_for_phase(EngineUiPhase.HOME))

    welcome_img = Path(__file__).resolve().parent / "assets" / "welcome.jpg"
    sent = False
    if welcome_img.is_file():
        try:
            from telegram import InputFile
            with welcome_img.open("rb") as fh:
                await message.reply_photo(
                    photo=InputFile(fh, filename="welcome.jpg"),
                    caption=caption[:1024],
                    reply_markup=markup,
                )
            sent = True
        except Exception:
            sent = False
    if not sent:
        try:
            await message.reply_text(caption[:4000], reply_markup=markup)
        except Exception:
            await safe_reply_text(message, caption[:4000])


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
    ui_phase = "—"
    try:
        from lumen.bot.ui.state_store import load_ui_state
        ui_phase = load_ui_state(context.user_data).phase.value
    except Exception:
        pass
    lines = [
        "📊 حالة الجلسة",
        f"• user_id: {user.id if user else '?'}",
        f"• OUTPUT_DIR: {OUTPUT_DIR}",
        f"• engine_ui.phase: {ui_phase}",
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


async def unknown_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply instead of silently dropping an unregistered slash command."""
    message = update.effective_message
    if not message:
        return
    user = update.effective_user
    if not is_allowed(user.id if user else None):
        await message.reply_text("⛔ غير مصرح لك باستخدام هذا البوت.")
        return
    await message.reply_text(
        "الأمر غير معروف. استخدم /help لعرض الأوامر المتاحة."
    )


async def handle_non_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Voice/photo/sticker/document — never silent."""
    message = update.effective_message
    if not message:
        return
    await message.reply_text(
        "حالياً أستقبل النص فقط.\n"
        "اكتب وصف البوت أو استخدم /help — الصور والصوت غير مدعومين بعد."
    )
