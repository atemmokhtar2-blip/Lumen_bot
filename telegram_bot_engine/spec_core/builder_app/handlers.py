"""Handlers for the zero-AI Spec Builder Telegram bot."""
from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from telegram_bot_engine.spec_core.builder import get_session, reset_session
from telegram_bot_engine.spec_core.builder_app.keyboards import (
    after_build_menu,
    capabilities_menu,
    categories_menu,
    main_menu,
)
from telegram_bot_engine.spec_core.pipeline import build_from_spec

logger = logging.getLogger(__name__)

# Where generated projects are written (override with BUILDER_OUT_DIR)
DEFAULT_OUT = Path(tempfile.gettempdir()) / "spec_builder_projects"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    session = get_session(user.id)
    session.awaiting_name = False
    session.awaiting_description = False
    await message.reply_text(
        "مرحباً بك في **بنّاء البوتات** (بدون ذكاء اصطناعي).\n"
        "اختر من القوائم لتفعيل القدرات، ثم اضغط توليد.",
        reply_markup=main_menu(),
        parse_mode="Markdown",
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    await message.reply_text(
        "الخطوات:\n"
        "1) عيّن اسم البوت\n"
        "2) (اختياري) الوصف\n"
        "3) فعّل القدرات من التصنيفات\n"
        "4) راجع الملخص\n"
        "5) توليد المشروع\n\n"
        "الأوامر: /start /help /summary",
        reply_markup=main_menu(),
    )


async def summary_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    session = get_session(user.id)
    await message.reply_text(session.summary_text(), reply_markup=main_menu())


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None or not message.text:
        return
    session = get_session(user.id)
    if session.awaiting_name:
        session.set_name(message.text)
        session.awaiting_name = False
        await message.reply_text(f"تم ضبط الاسم: `{session.bot_name}`", parse_mode="Markdown", reply_markup=main_menu())
        return
    if session.awaiting_description:
        session.set_description(message.text)
        session.awaiting_description = False
        await message.reply_text("تم حفظ الوصف.", reply_markup=main_menu())
        return
    await message.reply_text("استخدم الأزرار أو /start", reply_markup=main_menu())


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    data = query.data or ""
    session = get_session(user.id)
    chat_id = query.message.chat_id if query.message else user.id

    if data == "b:home":
        session.awaiting_name = False
        session.awaiting_description = False
        await query.edit_message_text("القائمة الرئيسية:", reply_markup=main_menu())
        return

    if data == "b:name":
        session.awaiting_name = True
        session.awaiting_description = False
        await query.edit_message_text("أرسل الآن اسم البوت (حروف/أرقام/_ فقط):")
        return

    if data == "b:desc":
        session.awaiting_description = True
        session.awaiting_name = False
        await query.edit_message_text("أرسل وصفًا مختصرًا للبوت:")
        return

    if data == "b:cats":
        await query.edit_message_text("اختر تصنيف القدرات:", reply_markup=categories_menu())
        return

    if data.startswith("b:cat:"):
        cat = data.split(":", 2)[2]
        await query.edit_message_text(
            f"تصنيف: {cat}\nاضغط لتفعيل/إيقاف:",
            reply_markup=capabilities_menu(session, cat),
        )
        return

    if data.startswith("b:tog:"):
        key = data.split(":", 2)[2]
        # category from capability for refresh
        from telegram_bot_engine.spec_core.registry import get_capability

        cap = get_capability(key)
        cat = cap.category if cap else "core"
        session.toggle(key)
        state = "مفعّل" if session.is_on(key) else "متوقف"
        await query.edit_message_text(
            f"{key}: {state}\n\nتصنيف: {cat}",
            reply_markup=capabilities_menu(session, cat),
        )
        return

    if data == "b:summary":
        await query.edit_message_text(session.summary_text(), reply_markup=main_menu())
        return

    if data == "b:reset":
        reset_session(user.id)
        await query.edit_message_text("تمت إعادة الضبط.", reply_markup=main_menu())
        return

    if data == "b:build":
        await query.edit_message_text("جاري التوليد…")
        spec = session.to_spec()
        out_root = Path(
            context.application.bot_data.get("builder_out_dir") or DEFAULT_OUT
        )
        out_dir = out_root / f"{session.bot_name}_{user.id}"
        result = build_from_spec(spec, out_dir)
        if not result.ok:
            await context.bot.send_message(
                chat_id,
                "فشل التوليد:\n" + "\n".join(result.errors[:8]),
                reply_markup=main_menu(),
            )
            return
        # Save spec.json beside project
        spec_path = out_dir / "bot_spec.json"
        spec_path.write_text(json.dumps(spec.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        files_preview = "\n".join(f"• {Path(f).name}" for f in result.files[:12])
        text = (
            f"✅ تم توليد المشروع\n"
            f"المسار:\n`{out_dir}`\n\n"
            f"الخدمات: {', '.join(result.plan_services) or '—'}\n"
            f"الملفات:\n{files_preview}\n\n"
            f"شغّل:\n`cd {out_dir} && pip install -r requirements.txt && python main.py`"
        )
        await context.bot.send_message(
            chat_id, text, parse_mode="Markdown", reply_markup=after_build_menu()
        )
        logger.info("built project for user=%s path=%s", user.id, out_dir)
        return

    await query.edit_message_text("أمر غير معروف", reply_markup=main_menu())
