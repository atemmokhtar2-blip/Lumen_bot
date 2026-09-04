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



async def _qualify_bot_use(
    context: ContextTypes.DEFAULT_TYPE, user_id: int, event: str
) -> None:
    from lumen.bot.referral_hooks import qualify_bot_use
    await qualify_bot_use(context, user_id, event)


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if not message:
        return

    # Referral deep-link MUST run even if invitee is not yet in ALLOWED_USER_IDS.
    # Otherwise stats never move when a new account opens the link.
    try:
        payload = ""
        if context.args:
            payload = " ".join(str(a) for a in context.args).strip()
        if user and payload:
            from lumen.platform.referrals.config import parse_referrer_from_start_payload
            from lumen.application.commands.register_referral import RegisterReferralCommand
            from lumen.application.handlers.referral_handlers import handle_register_referral

            referrer_id = parse_referrer_from_start_payload(payload)
            if referrer_id is not None:
                try:
                    result = await asyncio.to_thread(
                        handle_register_referral,
                        RegisterReferralCommand(
                            referrer_telegram_id=int(referrer_id),
                            referred_telegram_id=int(user.id),
                        ),
                    )
                except RuntimeError:
                    result = None
                    await message.reply_text(
                        "تم استلام الدعوة، لكن الخادم لا يصل لقاعدة Mongo "
                        "(تحقق من MONGODB_URI أو MONGO_URL بعد إعادة التشغيل)."
                    )
                except Exception:
                    result = None
                try:
                    if result is not None and result.ok and not result.already_registered:
                        await message.reply_text(
                            "مرحباً بك في Lumen — تم تسجيل دعوتك. "
                            "أرسل أي رسالة أو استخدم البوت حتى تُحتسب الإحالة "
                            "(فتح الرابط وحده لا يكفي)."
                        )
                    elif result is not None and result.ok and result.already_registered:
                        await message.reply_text(
                            "حسابك مرتبط بدعوة مسبقاً. أكمل استخدام البوت إن لم تُحتسب بعد."
                        )
                    elif result is not None and not result.ok:
                        err = result.error or ""
                        if err == "self_referral_forbidden":
                            await message.reply_text(
                                "لا يمكنك استخدام رابط الإحالة الخاص بك."
                            )
                        elif err == "register_rate_limited":
                            await message.reply_text(
                                "محاولات كثيرة حالياً — أعد المحاولة بعد دقيقة."
                            )
                        elif err == "referrer_invite_cap_reached":
                            await message.reply_text(
                                "هذا المحيل وصل للحد الأقصى من الدعوات."
                            )
                        elif err == "referral_backend_unavailable":
                            await message.reply_text(
                                "نظام الإحالة غير متاح: الخادم لا يرى رابط Mongo. "
                                "ضع MONGODB_URI أو MONGO_URL في بيئة التشغيل وأعد تشغيل البوت."
                            )
                except Exception:
                    pass
    except Exception:
        pass

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
    if user:
        await _qualify_bot_use(context, int(user.id), "command_non_start")
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
    if user:
        await _qualify_bot_use(context, int(user.id), "command_non_start")
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
    if user and is_allowed(user.id if user else None):
        await _qualify_bot_use(context, int(user.id), "command_non_start")
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
    if user:
        await _qualify_bot_use(context, int(user.id), "command_non_start")
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
    if user:
        await _qualify_bot_use(context, int(user.id), "command_non_start")

    # Link never depends on Mongo / credits backend
    try:
        from lumen.platform.referrals import (
            REFERRAL_QUALIFIED_TARGET,
            REFERRAL_REWARD_USD,
            bot_username_link,
        )
        from lumen.platform.referrals.config import referral_deep_link_payload

        me = await context.bot.get_me()
        username = (me.username or "").strip()
        if username:
            link = bot_username_link(username, int(user.id))
        else:
            link = referral_deep_link_payload(int(user.id))
    except Exception:
        await message.reply_text("تعذر إنشاء رابط الإحالة.")
        return

    stats_lines = []
    try:
        from lumen.platform.referrals import get_referral_repository

        def _live():
            repo = get_referral_repository()
            st = repo.stats_for(int(user.id))
            st.qualified_count = int(repo.count_qualified(int(user.id)))
            try:
                st.total_invited = max(
                    int(st.total_invited), int(repo.count_for_referrer(int(user.id)))
                )
            except Exception:
                pass
            return st

        stats = await asyncio.to_thread(_live)
        remaining = max(0, int(REFERRAL_QUALIFIED_TARGET) - int(stats.qualified_count))
        stats_lines = [
            f"• إجمالي المدعوين: {stats.total_invited}",
            f"• استخدموا البوت (يُحتسب): {stats.qualified_count}",
            f"• بانتظار الاستخدام: {stats.pending_count}",
            f"• المتبقي للمكافأة: {remaining}",
            f"• المكافأة: ${int(REFERRAL_REWARD_USD)} عند {int(REFERRAL_QUALIFIED_TARGET)} مستخدم نشط",
            f"• حالة الصرف: {'تم ✓' if stats.reward_paid else 'لم تُصرف بعد'}",
        ]
    except Exception:
        stats_lines = [
            "• الإحصائيات غير متاحة حالياً (قاعدة الإحالات)",
            f"• المكافأة: ${int(REFERRAL_REWARD_USD)} عند {int(REFERRAL_QUALIFIED_TARGET)} مستخدم نشط",
        ]

    nl = chr(10)
    text = nl.join(
        [
            "⭐ برنامج إحالة Lumen — $5",
            "",
            "رابط الدعوة الخاص بك:",
            str(link),
            "",
            *stats_lines,
            "",
            "ملاحظة: فتح الرابط وحده لا يُحتسب — يجب أن يستخدم المدعو البوت.",
        ]
    )
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


async def referral_stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin-only program-wide referral counters."""
    user = update.effective_user
    message = update.effective_message
    if not message or not user:
        return
    try:
        from lumen.platform.referrals.config import is_referral_admin
        if not is_referral_admin(int(user.id)):
            await message.reply_text("هذا الأمر للمشرفين فقط.")
            return
    except Exception:
        await message.reply_text("هذا الأمر للمشرفين فقط.")
        return
    try:
        from lumen.platform.referrals import (
            REFERRAL_QUALIFIED_TARGET,
            REFERRAL_REWARD_USD,
            get_referral_repository,
        )

        st = await asyncio.to_thread(get_referral_repository().system_stats)
        nl = chr(10)
        text = nl.join(
            [
                "إحصائيات برنامج الإحالة (أدمن)",
                "",
                f"• إجمالي الإحالات: {st.get('total_referrals', 0)}",
                f"• مؤهّلون (استخدموا البوت): {st.get('qualified', 0)}",
                f"• بانتظار الاستخدام: {st.get('pending', 0)}",
                f"• مرفوضون: {st.get('rejected', 0)}",
                f"• مكافآت تم صرفها: {st.get('rewards_paid', 0)}",
                "",
                f"الهدف لكل محيل: {REFERRAL_QUALIFIED_TARGET} → ${REFERRAL_REWARD_USD}",
            ]
        )
        await message.reply_text(text)
    except RuntimeError:
        await message.reply_text("نظام الإحالة غير متاح حالياً (إعدادات الخادم).")
    except Exception:
        await message.reply_text("تعذر جلب الإحصائيات.")
