"""Telegram command handlers (/start, /help, /status, /lang)."""
from __future__ import annotations

import asyncio
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
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

    # Persist user on every /start — off event loop (pymongo is sync)
    try:
        if user:
            from lumen.bot.middlewares.mongo_sync import ensure_mongo_user
            await asyncio.to_thread(ensure_mongo_user, user)
    except Exception:
        pass

    try:
        from lumen.bot.ui.menu_button import configure_menu_button
        if update.effective_chat:
            await configure_menu_button(context.bot, chat_id=update.effective_chat.id)
    except Exception:
        pass
    # Hydrate durable session (Redis source of truth) before /start UI
    try:
        if user and context.user_data is not None:
            get_session_store().hydrate(int(user.id), context.user_data)
    except Exception:
        pass

    # Deep link: /start conversation_<id> OR /start ref_<telegram_id>
    try:
        payload = ""
        if context.args:
            payload = " ".join(str(a) for a in context.args).strip()
        if user and payload:
            # Referral deep-link (pending until invitee *uses* the bot)
            try:
                from lumen.platform.referrals.config import parse_referrer_from_start_payload
                from lumen.application.commands.register_referral import RegisterReferralCommand
                from lumen.application.handlers.referral_handlers import handle_register_referral

                referrer_id = parse_referrer_from_start_payload(payload)
                if referrer_id is not None:
                    result = await asyncio.to_thread(
                        handle_register_referral,
                        RegisterReferralCommand(
                            referrer_telegram_id=int(referrer_id),
                            referred_telegram_id=int(user.id),
                        ),
                    )
                    try:
                        if result.ok and not result.already_registered:
                            await message.reply_text(
                                "مرحباً بك في Lumen — تم تسجيل دعوتك. "
                                "أرسل أي رسالة للبوت حتى تُحتسب الإحالة للمحيل."
                            )
                        elif not result.ok and result.error == "self_referral_forbidden":
                            await message.reply_text(
                                "لا يمكنك استخدام رابط الإحالة الخاص بك."
                            )
                    except Exception:
                        pass
            except Exception:
                pass
            from lumen.bot.conversation_ui import apply_start_deep_link
            note = apply_start_deep_link(context, int(user.id), payload)
            if note:
                try:
                    await message.reply_text(note)
                except Exception:
                    pass
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
        try:
            await asyncio.to_thread(persist_ui_session, uid, dict(ud))
        except Exception:
            persist_ui_session(uid, dict(ud))

    try:
        facts = await asyncio.wait_for(asyncio.to_thread(gather_ui_facts, uid, ud), timeout=6.0)
    except Exception:
        from lumen.engine.services.ui_state.render import UiFacts
        facts = UiFacts()
    # Official Telegram HTML cards (<blockquote expandable> blue box + arrow)
    menu_body = render_message(ui, facts)
    markup = build_inline_keyboard(buttons_for_phase(EngineUiPhase.HOME), user_id=uid, nav=False)

    from lumen.bot.ui.chat_hygiene import remember_message, prune_bot_messages

    # First-time hero image only (no HTML in caption — blockquotes need a text message).
    # Menu body is ALWAYS a separate text message; safe_reply auto-sets parse_mode=HTML.
    already_welcomed = bool(ud.get("lumen_welcome_shown"))
    if not already_welcomed:
        welcome_img = Path(__file__).resolve().parent / "assets" / "welcome.jpg"
        if welcome_img.is_file():
            try:
                from telegram import InputFile

                with welcome_img.open("rb") as fh:
                    photo_msg = await message.reply_photo(
                        photo=InputFile(fh, filename="welcome.jpg"),
                    )
                ud["lumen_welcome_shown"] = True
                ud["lumen_welcome_msg_id"] = getattr(photo_msg, "message_id", None)
                if context.user_data is not None:
                    context.user_data["lumen_welcome_shown"] = True
                    context.user_data["lumen_welcome_msg_id"] = ud["lumen_welcome_msg_id"]
                try:
                    if uid:
                        get_session_store().save(uid, dict(ud if isinstance(ud, dict) else {}))
                except Exception:
                    pass
            except Exception:
                pass

    sent_msg = None
    try:
        sent_list = await safe_reply_text(message, menu_body, reply_markup=markup)
        sent_msg = sent_list[-1] if sent_list else None
    except Exception:
        try:
            from telegram.constants import ParseMode

            sent_msg = await message.reply_text(
                menu_body, parse_mode=ParseMode.HTML, reply_markup=markup
            )
        except Exception:
            await safe_reply_text(message, menu_body[:4000])
            sent_msg = None
    if sent_msg is not None and context.user_data is not None:
        remember_message(context.user_data, getattr(sent_msg, "message_id", None))
        try:
            await prune_bot_messages(
                context.bot,
                int(message.chat_id),
                context.user_data,
                protect=getattr(sent_msg, "message_id", None),
            )
        except Exception:
            pass


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
        await safe_reply_text(message, text)
    except Exception:
        await safe_reply_text(message, text)


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



async def referral_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show personal referral link + qualified progress toward reward."""
    user = update.effective_user
    message = update.effective_message
    if not message or not user:
        return
    if not is_allowed(user.id):
        lang = get_lang(user, context)
        await message.reply_text(t("not_authorized", lang))
        return
    try:
        from lumen.platform.referrals import (
            REFERRAL_QUALIFIED_TARGET,
            REFERRAL_REWARD_USD,
            bot_username_link,
            get_referral_repository,
        )

        me = await context.bot.get_me()
        username = (me.username or "").strip()
        if username:
            link = bot_username_link(username, int(user.id))
        else:
            from lumen.platform.referrals.config import referral_deep_link_payload
            link = referral_deep_link_payload(int(user.id))
        def _live_stats(uid: int):
            repo = get_referral_repository()
            st = repo.stats_for(uid)
            st.qualified_count = int(repo.count_qualified(uid))
            try:
                st.total_invited = max(
                    int(st.total_invited), int(repo.count_for_referrer(uid))
                )
            except Exception:
                pass
            return st

        stats = await asyncio.to_thread(_live_stats, int(user.id))
        remaining = max(0, int(REFERRAL_QUALIFIED_TARGET) - int(stats.qualified_count))
        nl = chr(10)
        text = nl.join(
            [
                "⭐ برنامج إحالة Lumen",
                "",
                "رابط الدعوة الخاص بك:",
                str(link),
                "",
                f"• إجمالي المدعوين: {stats.total_invited}",
                f"• استخدموا البوت (يُحتسب): {stats.qualified_count}",
                f"• بانتظار الاستخدام: {stats.pending_count}",
                f"• المتبقي للمكافأة: {remaining}",
                f"• المكافأة: ${int(REFERRAL_REWARD_USD)} عند {int(REFERRAL_QUALIFIED_TARGET)} مستخدم نشط",
                f"• حالة الصرف: {'تم ✓' if stats.reward_paid else 'لم تُصرف بعد'}",
                "",
                "ملاحظة: فتح الرابط وحده لا يُحتسب — يجب أن يستخدم المدعو البوت.",
            ]
        )
        # Share button (opens Telegram share sheet with the invite link)
        share_kb = None
        try:
            from urllib.parse import quote
            share_kb = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "مشاركة الرابط",
                            url=(
                                "https://t.me/share/url?url="
                                + quote(str(link), safe="")
                                + "&text="
                                + quote("جرب Lumen", safe="")
                            ),
                        )
                    ]
                ]
            )
        except Exception:
            share_kb = None
        await message.reply_text(text, reply_markup=share_kb)
    except Exception:
        await message.reply_text("تعذر جلب إحصائيات الإحالة حالياً.")
