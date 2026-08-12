"""Git clone and repository pull flows for the consumer bot."""
from __future__ import annotations

import asyncio
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from ..config import OUTPUT_DIR, logger
from ..sanitize import sanitize_error
from ..helpers import make_zip_from_path
from ..middlewares.mongo_sync import (
    persist_session as _persist_session,
    plan_live_seconds as _plan_live_seconds,
)


async def try_handle_git(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    request: str,
    user,
    message,
) -> bool:
    """Return True if this message was fully handled as a clone/pull flow."""
    # --- Smart Git: clone repo from natural language + URL ---
    try:
        from telegram_bot_engine.engines.generators.git_operations.smart_clone import (
            looks_like_clone_request,
            smart_clone,
            extract_repo_url,
        )
    except Exception:
        looks_like_clone_request = None  # type: ignore

    # ChatRouter: natural "اسحب المستودع..." → clone path only
    try:
        from telegram_bot_engine.services.chat_router import route_message as _route_msg
        _cr = _route_msg(request)
        _clone_via_router = (
            _cr.ok
            and _cr.capability_id == "clone_repo"
            and (bool(_cr.params.get("url")) or "github.com" in request.lower() or "gitlab.com" in request.lower())
        )
    except Exception:
        _clone_via_router = False

    if (looks_like_clone_request and looks_like_clone_request(request)) or _clone_via_router:
        status = await message.reply_text("📥 جاري سحب المستودع...")
        await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)
        uid = int(user.id) if user else 0
        try:
            from telegram_bot_engine.services.user_sandbox import get_user_sandbox
            dest = get_user_sandbox(uid, OUTPUT_DIR).new_clone_dir(label="clone")
        except Exception:
            dest = Path(OUTPUT_DIR) / "clones"
            dest.mkdir(parents=True, exist_ok=True)

        def _do_clone():
            return smart_clone(request, dest_dir=dest)

        try:
            result = await asyncio.to_thread(_do_clone)
        except Exception as e:
            logger.exception("Clone failed")
            await status.edit_text(f"❌ فشل سحب المستودع: {type(e).__name__}: {sanitize_error(str(e))}")
            return True


        if result.ok:
            lines = [
                "✅ تم سحب المستودع بنجاح",
                f"• الرابط: `{result.url or ''}`",
                f"• المسار: `{result.path or ''}`",
            ]
            # Auto-understand repository
            repo_contract = None
            if result.path and Path(result.path).exists():
                try:
                    await status.edit_text("\n".join(lines + ["", "🔍 جاري فهم المستودع..."]))
                    from telegram_bot_engine.services.repo_understanding import (
                        understand_repo,
                    )

                    def _do_understand():
                        return understand_repo(result.path, remote_url=result.url or "")

                    repo_contract = await asyncio.to_thread(_do_understand)
                    # Keep context for future development turns
                    context.user_data["active_repo"] = {
                        "path": result.path,
                        "url": result.url,
                        "contract": repo_contract.model_dump(mode="json"),
                    }
                    try:
                        from telegram_bot_engine.services.user_sandbox import get_user_sandbox
                        uid = int(user.id) if user else 0
                        get_user_sandbox(uid, OUTPUT_DIR).register_clone(
                            result.path, url=result.url or "", label=Path(result.path).name
                        )
                    except Exception:
                        logger.exception("register_clone failed")
                    lines.append("")
                    lines.append(repo_contract.to_user_summary())
                    lines.append("")
                    lines.append(
                        "يمكنك الآن طلب تطوير على هذا المستودع، مثال:\n"
                        "• أضف أمر /stats\n"
                        "• اشرح هيكل المشروع\n"
                        "• قائمة الملفات / ابحث عن X"
                    )
                    _tg_fws = ("python-telegram-bot", "aiogram", "pyTelegramBotAPI", "pyrogram")
                    _is_runnable = (
                        repo_contract.is_telegram_bot
                        or repo_contract.architecture_style in ("telegram_bot", "generation_engine")
                        or any(f in _tg_fws for f in (repo_contract.frameworks or []))
                        or any(
                            str(d).lower().replace("_", "-").startswith(
                                ("python-telegram-bot", "aiogram", "pytelegrambotapi", "telebot", "pyrogram")
                            )
                            for d in (repo_contract.dependencies or [])
                        )
                    )
                    if _is_runnable:
                        entry = ""
                        if repo_contract.entry_points:
                            entry = repo_contract.entry_points[0].path
                        context.user_data["pending_run"] = {
                            "project_path": result.path,
                            "entry_point": entry,
                            "run_seconds": _plan_live_seconds(user),
                        }
                        lines.append("")
                        lines.append(
                            "🚀 *للتشغيل الحقيقي:* أرسل الآن توكن البوت من @BotFather\n"
                            "(تحقق + تثبيت تبعيات + تشغيل — بدون نجاح وهمي)"
                        )
                except Exception as e:
                    logger.exception("Repo understanding failed")
                    lines.append(f"⚠️ السحب نجح لكن الفهم فشل: {type(e).__name__}")

            await status.edit_text("\n".join(lines))
            # zip and send if small enough
            if result.path and Path(result.path).exists():
                try:
                    zip_path = make_zip_from_path(result.path)
                    if zip_path and zip_path.exists() and zip_path.stat().st_size < 45 * 1024 * 1024:
                        with open(zip_path, "rb") as f:
                            await message.reply_document(
                                document=f,
                                filename=f"{Path(result.path).name}.zip",
                                caption="📦 نسخة من المستودع المسحوب",
                            )
                except Exception:
                    logger.exception("Failed to zip cloned repo")
        else:
            if getattr(result, "needs_auth", False):
                context.user_data["pending_clone_auth"] = {
                    "url": result.url or "",
                }
                await status.edit_text(
                    "🔒 المستودع خاص أو يحتاج صلاحية.\n\n"
                    "أرسل الآن *توكن GitHub* (PAT) بصلاحية `repo`:\n"
                    "• Classic: ghp_...\n"
                    "• Fine-grained: github_pat_...\n\n"
                    "بعدها هُعاد السحب تلقائياً."
                )
            else:
                err = (result.message or "فشل غير معروف")
                if result.stderr:
                    err += f"\n`{result.stderr[:300]}`"
                await status.edit_text(f"❌ {err}")
        return True


    return False
