"""Handlers for the zero-AI Spec Builder Telegram bot.

Projects are stored under the per-user sandbox:
  OUTPUT_DIR/users/<telegram_user_id>/projects/<name_timestamp>/

Live try uses LiveRunnerService / run_bot_project with the user's own bot token.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from telegram_bot_engine.spec_core.builder import get_session, reset_session
from telegram_bot_engine.spec_core.builder_app.keyboards import (
    after_build_menu,
    capabilities_menu,
    categories_menu,
    main_menu,
    projects_menu,
)
from telegram_bot_engine.spec_core.pipeline import build_from_spec
from telegram_bot_engine.services.user_sandbox import get_user_sandbox

logger = logging.getLogger(__name__)


def _sandbox_base() -> str | None:
    return (os.getenv("BUILDER_OUT_DIR") or os.getenv("OUTPUT_DIR") or "").strip() or None


def _user_sb(user_id: int):
    return get_user_sandbox(user_id, _sandbox_base())


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    session = get_session(user.id)
    session.awaiting_name = False
    session.awaiting_description = False
    session.awaiting_try_token = False
    sb = _user_sb(user.id)
    await message.reply_text(
        "مرحباً بك في **بنّاء البوتات** (بدون ذكاء اصطناعي).\n"
        "اختر القدرات → توليد → احفظ في مجلدك → جرب بـ توكن بوتك.\n"
        f"مجلدك: `{sb.root}`",
        reply_markup=main_menu(),
        parse_mode="Markdown",
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    await message.reply_text(
        "الخطوات:\n"
        "1) اسم البوت\n"
        "2) وصف (اختياري)\n"
        "3) تفعيل القدرات\n"
        "4) توليد المشروع (يُحفظ في مجلدك)\n"
        "5) جرب البوت: أرسل توكن بوت **خاص بك** (مش توكن البنّاء)\n\n"
        "/start /help /summary /projects",
        reply_markup=main_menu(),
    )


async def summary_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    session = get_session(user.id)
    extra = ""
    if session.last_project_path:
        extra = f"\n\nآخر مشروع:\n`{session.last_project_path}`"
    await message.reply_text(session.summary_text() + extra, reply_markup=main_menu(), parse_mode="Markdown")


async def projects_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    projects = _user_sb(user.id).list_projects()
    if not projects:
        await message.reply_text("لا توجد مشاريع بعد. ولّد مشروعًا أولًا.", reply_markup=main_menu())
        return
    lines = [f"• `{p.get('id')}` — {p.get('label')}" for p in projects[:15]]
    await message.reply_text(
        "مشاريعك:\n" + "\n".join(lines),
        reply_markup=projects_menu(projects),
        parse_mode="Markdown",
    )


def _resolve_project(user_id: int, project_id: str | None = None) -> Path | None:
    session = get_session(user_id)
    sb = _user_sb(user_id)
    if project_id:
        for p in sb.list_projects():
            if str(p.get("id")) == project_id:
                path = Path(str(p.get("path") or ""))
                return path if path.exists() else None
        # fallback: direct folder under projects
        cand = sb.projects_dir / project_id
        return cand if cand.exists() else None
    if session.last_project_path:
        path = Path(session.last_project_path)
        if path.exists():
            return path
    projects = sb.list_projects()
    if projects:
        path = Path(str(projects[0].get("path") or ""))
        return path if path.exists() else None
    return None


def _start_live_try(chat_id: int, user_id: int, project_path: Path, token: str, bot) -> None:
    """Background thread: install + run user bot for a limited window."""

    def worker() -> None:
        try:
            from telegram_bot_engine.services.live_runner import run_bot_project

            # Keep try sessions bounded
            run_seconds = float(os.environ.get("BUILDER_TRY_SECONDS", os.environ.get("LIVE_RUN_SECONDS", "120")))
            report = run_bot_project(
                project_path=project_path,
                bot_token=token,
                entry_hint="main.py",
                run_seconds=run_seconds,
            )
            text = report.to_user_text() if hasattr(report, "to_user_text") else (
                f"{'✅' if report.ok else '❌'} {report.phase}: {report.message}"
            )
            # schedule send from this thread via bot API is sync-unfriendly; use requests-less approach
            import asyncio

            try:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(bot.send_message(chat_id, text[:3500], parse_mode="Markdown"))
                loop.close()
            except Exception:
                # fallback plain
                try:
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(bot.send_message(chat_id, text[:3500]))
                    loop.close()
                except Exception as e:
                    logger.exception("failed to notify try result: %s", e)
        except Exception as e:
            logger.exception("live try failed")
            try:
                import asyncio

                loop = asyncio.new_event_loop()
                loop.run_until_complete(
                    bot.send_message(chat_id, f"❌ فشل التشغيل: {type(e).__name__}: {e}"[:500])
                )
                loop.close()
            except Exception:
                pass

    threading.Thread(target=worker, name=f"try-bot-{user_id}", daemon=True).start()


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None or not message.text:
        return
    session = get_session(user.id)
    text = message.text.strip()

    if session.awaiting_name:
        session.set_name(text)
        session.awaiting_name = False
        await message.reply_text(
            f"تم ضبط الاسم: `{session.bot_name}`",
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )
        return

    if session.awaiting_description:
        session.set_description(text)
        session.awaiting_description = False
        await message.reply_text("تم حفظ الوصف.", reply_markup=main_menu())
        return

    if session.awaiting_try_token:
        session.awaiting_try_token = False
        token = text
        # delete message with token for safety if possible
        try:
            await message.delete()
        except Exception:
            pass
        project = _resolve_project(user.id)
        if project is None:
            await context.bot.send_message(
                message.chat_id,
                "لا يوجد مشروع للتشغيل. ولّد مشروعًا أولًا.",
                reply_markup=main_menu(),
            )
            return
        if ":" not in token or len(token) < 20:
            await context.bot.send_message(
                message.chat_id,
                "التوكن غير صالح. أرسل توكن بوت من @BotFather.",
                reply_markup=main_menu(),
            )
            return
        await context.bot.send_message(
            message.chat_id,
            f"جاري تجربة المشروع:\n`{project}`\n"
            "سيتم التشغيل لفترة محدودة ثم يتوقف تلقائيًا.",
            parse_mode="Markdown",
        )
        _start_live_try(message.chat_id, user.id, project, token, context.bot)
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
        session.awaiting_try_token = False
        await query.edit_message_text("القائمة الرئيسية:", reply_markup=main_menu())
        return

    if data == "b:name":
        session.awaiting_name = True
        session.awaiting_description = False
        session.awaiting_try_token = False
        await query.edit_message_text("أرسل الآن اسم البوت (حروف/أرقام/_ فقط):")
        return

    if data == "b:desc":
        session.awaiting_description = True
        session.awaiting_name = False
        session.awaiting_try_token = False
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
        extra = ""
        if session.last_project_path:
            extra = f"\n\nآخر مشروع:\n`{session.last_project_path}`"
        await query.edit_message_text(
            session.summary_text() + extra,
            reply_markup=main_menu(),
            parse_mode="Markdown",
        )
        return

    if data == "b:reset":
        reset_session(user.id)
        await query.edit_message_text("تمت إعادة الضبط.", reply_markup=main_menu())
        return

    if data == "b:projects":
        projects = _user_sb(user.id).list_projects()
        if not projects:
            await query.edit_message_text("لا توجد مشاريع محفوظة.", reply_markup=main_menu())
            return
        lines = [f"• `{p.get('id')}`" for p in projects[:12]]
        await query.edit_message_text(
            "مشاريعك المحفوظة:\n" + "\n".join(lines),
            reply_markup=projects_menu(projects),
            parse_mode="Markdown",
        )
        return

    if data.startswith("b:open:"):
        pid = data.split(":", 2)[2]
        path = _resolve_project(user.id, pid)
        if path is None:
            await query.edit_message_text("المشروع غير موجود.", reply_markup=main_menu())
            return
        session.last_project_path = str(path)
        session.last_project_id = pid
        await query.edit_message_text(
            f"تم اختيار:\n`{path}`\nيمكنك الضغط على جرب البوت.",
            reply_markup=after_build_menu(),
            parse_mode="Markdown",
        )
        return

    if data == "b:try" or data.startswith("b:tryid:"):
        if data.startswith("b:tryid:"):
            pid = data.split(":", 2)[2]
            path = _resolve_project(user.id, pid)
            if path is not None:
                session.last_project_path = str(path)
                session.last_project_id = pid
        project = _resolve_project(user.id)
        if project is None:
            await query.edit_message_text(
                "لا يوجد مشروع. ولّد مشروعًا أولًا.",
                reply_markup=main_menu(),
            )
            return
        session.awaiting_try_token = True
        session.awaiting_name = False
        session.awaiting_description = False
        await query.edit_message_text(
            f"تشغيل تجريبي للمشروع:\n`{project}`\n\n"
            "أرسل الآن **توكن البوت** من @BotFather "
            "(توكن بوتك أنت، ليس توكن البنّاء).\n"
            "سيتم حذف رسالة التوكن إن أمكن.",
            parse_mode="Markdown",
        )
        return

    if data == "b:build":
        await query.edit_message_text("جاري التوليد والحفظ في مجلدك…")
        spec = session.to_spec()
        sb = _user_sb(user.id)
        out_dir = sb.new_project_dir(label=session.bot_name)
        result = build_from_spec(spec, out_dir)
        if not result.ok:
            await context.bot.send_message(
                chat_id,
                "فشل التوليد:\n" + "\n".join(result.errors[:8]),
                reply_markup=main_menu(),
            )
            return

        spec_path = out_dir / "bot_spec.json"
        spec_path.write_text(
            json.dumps(spec.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        entry = sb.register_project(
            out_dir,
            label=session.bot_name,
            source_request="spec_builder",
            kind="spec_core",
            extra={
                "features": sorted(session.selected),
                "services": list(result.plan_services),
            },
        )
        session.last_project_path = str(out_dir)
        session.last_project_id = str(entry.get("id") or out_dir.name)

        files_preview = "\n".join(f"• {Path(f).name}" for f in result.files[:12])
        text = (
            f"✅ تم التوليد والحفظ\n"
            f"المعرف: `{session.last_project_id}`\n"
            f"المسار:\n`{out_dir}`\n\n"
            f"الخدمات: {', '.join(result.plan_services) or '—'}\n"
            f"الملفات:\n{files_preview}\n\n"
            f"اضغط **جرب البوت** وأرسل توكن بوتك للتجربة."
        )
        await context.bot.send_message(
            chat_id,
            text,
            parse_mode="Markdown",
            reply_markup=after_build_menu(),
        )
        logger.info("built+registered user=%s path=%s", user.id, out_dir)
        return

    await query.edit_message_text("أمر غير معروف", reply_markup=main_menu())
