"""Isolated handling of Telegram bot tokens and private-repo PATs."""
from __future__ import annotations

import asyncio
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from ..config import OUTPUT_DIR, logger
from ..sanitize import sanitize_error
from ..helpers import looks_like_bot_token, normalize_bot_token
from ..live import handle_live_run_token, handle_live_deploy_token
from ..middlewares.mongo_sync import (
    persist_session as _persist_session,
    plan_live_seconds as _plan_live_seconds,
)


async def try_handle_token(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    request: str,
    user,
    message,
) -> bool:
    """Return True if this message was fully handled as a token/PAT flow."""
    # Spec 065 — if user is sending a bot token after successful generation
    pending_host = (context.user_data or {}).get("pending_host")
    if pending_host and looks_like_bot_token(request):
        context.user_data.pop("pending_host", None)
        status = await message.reply_text("🚀 جاري بدء الاستضافة (عملية طويلة الأمد)...")
        await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)

        def _do_host():
            from telegram_bot_engine.services.hosting import get_hosting_service
            svc = get_hosting_service(OUTPUT_DIR)
            return svc.start(
                user_id=message.from_user.id if message.from_user else 0,
                project_path=pending_host.get("project_path") or "",
                bot_token=normalize_bot_token(request),
            )

        try:
            result = await asyncio.to_thread(_do_host)
        except Exception as e:
            logger.exception("hosting start failed")
            await status.edit_text(f"❌ فشل الاستضافة: {type(e).__name__}: {sanitize_error(str(e))}")
            return True

        await status.edit_text(result.to_user_text())
        return True


    # Accept token even if Telegram wraps it across lines
    token_text = normalize_bot_token(request) if looks_like_bot_token(request) else ""
    pending_run = (context.user_data or {}).get("pending_run")
    # generation_flow historically set pending_live_run / pending_deploy
    pending_live = (context.user_data or {}).get("pending_live_run")
    pending_deploy = (context.user_data or {}).get("pending_deploy")
    if token_text:
        if not pending_run and pending_live:
            pending_run = dict(pending_live)
            context.user_data["pending_run"] = pending_run
        if not pending_run and pending_deploy:
            pending_run = {
                "project_path": pending_deploy.get("project_path") or "",
                "entry_point": pending_deploy.get("entry_point") or "",
                "run_seconds": _plan_live_seconds(user),
            }
            context.user_data["pending_run"] = pending_run
        if not pending_run:
            active = (context.user_data or {}).get("active_repo") or {}
            if active.get("path") and Path(active["path"]).exists():
                entry = ""
                try:
                    cdict = active.get("contract") or {}
                    eps = cdict.get("entry_points") or []
                    if eps:
                        entry = (eps[0] or {}).get("path") or ""
                except Exception:
                    entry = ""
                if not entry:
                    for cand in ("bot.py", "main.py", "app.py"):
                        if (Path(active["path"]) / cand).exists():
                            entry = cand
                            break
                pending_run = {
                    "project_path": active["path"],
                    "entry_point": entry,
                    "run_seconds": _plan_live_seconds(user),
                }
                context.user_data["pending_run"] = pending_run
        if pending_run and pending_run.get("project_path"):
            await handle_live_run_token(message, context, token_text, pending_run)
            _persist_session(user, context)
            return True

        # Token sent but no project is pending — do NOT treat as bot description
        await message.reply_text(
            "استلمت توكن بوت، لكن مفيش مشروع جاهز للتشغيل دلوقتي.\n"
            "ولّد بوت أو اسحب مستودع أولاً، وبعد رسالة «أرسل توكن البوت» ابعت التوكن."
        )
        return True


    # Create repo: user sends GitHub PAT after being asked
    pending_create = (context.user_data or {}).get("pending_create_repo")
    if pending_create:
        from telegram_bot_engine.engines.generators.git_operations.smart_clone import extract_token
        from telegram_bot_engine.engines.generators.git_operations.smart_git import run_git_intent
        git_tok = extract_token(request)
        if git_tok:
            name = str(pending_create.get("name") or "").strip()
            status = await message.reply_text(f"🔑 جاري إنشاء المستودع `{name}`...")
            await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)
            uid = int(user.id) if user else 0
            try:
                from telegram_bot_engine.services.user_sandbox import get_user_sandbox
                dest = get_user_sandbox(uid, OUTPUT_DIR).new_clone_dir(label="newrepo")
            except Exception:
                dest = Path(OUTPUT_DIR) / "clones"
                dest.mkdir(parents=True, exist_ok=True)

            def _create():
                return run_git_intent(
                    f"create repo {name}",
                    dest_dir=dest,
                    token=git_tok,
                    repo_name=name,
                )

            try:
                result = await asyncio.to_thread(_create)
            except Exception as e:
                await status.edit_text(f"❌ فشل الإنشاء: {sanitize_error(str(e))}")
                return True
            if result.ok:
                context.user_data.pop("pending_create_repo", None)
                if result.path:
                    context.user_data["active_repo"] = {"path": result.path, "url": result.url or ""}
                    context.user_data["last_project_path"] = result.path
                await status.edit_text(
                    f"✅ {result.message}\n• الرابط: {result.url or ''}\n"
                    + (f"• المسار: `{result.path}`" if result.path else "")
                )
            else:
                await status.edit_text(f"❌ {result.message}")
            return True

    # Push: PAT after auth failure
    pending_push = (context.user_data or {}).get("pending_git_push")
    if pending_push:
        from telegram_bot_engine.engines.generators.git_operations.smart_clone import extract_token
        from telegram_bot_engine.engines.generators.git_operations.smart_git import git_push
        git_tok = extract_token(request)
        if git_tok:
            path = str(pending_push.get("path") or "").strip()
            status = await message.reply_text("🔑 جاري الدفع بالتوكن...")
            result = await asyncio.to_thread(lambda: git_push(path, token=git_tok))
            if result.ok:
                context.user_data.pop("pending_git_push", None)
                await status.edit_text(f"✅ {result.message}")
            else:
                await status.edit_text(f"❌ {sanitize_error(result.message)}")
            return True

    # Private repo: user sends GitHub PAT after auth failure
    pending_clone = (context.user_data or {}).get("pending_clone_auth")
    if pending_clone:
        from telegram_bot_engine.engines.generators.git_operations.smart_clone import (
            extract_token,
            smart_clone,
        )
        git_tok = extract_token(request)
        if git_tok:
            status = await message.reply_text("🔑 جاري إعادة سحب المستودع بالتوكن...")
            await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)
            uid = int(user.id) if user else 0
            try:
                from telegram_bot_engine.services.user_sandbox import get_user_sandbox
                dest = get_user_sandbox(uid, OUTPUT_DIR).new_clone_dir(label="reclone")
            except Exception:
                dest = Path(OUTPUT_DIR) / "clones"
                dest.mkdir(parents=True, exist_ok=True)
            url = pending_clone.get("url") or ""

            def _reclone():
                return smart_clone(
                    text=url,
                    dest_dir=dest,
                    token=git_tok,
                    url_override=url,
                    depth=1,
                )

            try:
                result = await asyncio.to_thread(_reclone)
            except Exception as e:
                err_msg = sanitize_error(f"{type(e).__name__}: {e}")
                logger.error("private reclone failed: %s", err_msg)
                await status.edit_text(f"❌ فشل السحب بالتوكن: {err_msg}")
                return True

            finally:
                try:
                    git_tok = None  # drop reference
                    del git_tok
                except Exception:
                    pass

            if not result.ok:
                err_msg = f"❌ {result.message}"
                if result.stderr:
                    err_msg += f"\n`{result.stderr[:250]}`"
                await status.edit_text(err_msg)
                if not result.needs_auth:
                    context.user_data.pop("pending_clone_auth", None)
                return True


            context.user_data.pop("pending_clone_auth", None)
            lines = [
                "✅ تم سحب المستودع الخاص بنجاح",
                f"• الرابط: `{result.url or ''}`",
                f"• المسار: `{result.path or ''}`",
            ]
            try:
                await status.edit_text("\n".join(lines + ["", "🔍 جاري فهم المستودع..."]))
                from telegram_bot_engine.services.repo_understanding import understand_repo

                def _do_u():
                    return understand_repo(result.path, remote_url=result.url or "")

                repo_contract = await asyncio.to_thread(_do_u)
                context.user_data["active_repo"] = {
                    "path": result.path,
                    "url": result.url,
                    "contract": (
                        __import__(
                            "telegram_bot_engine.schemas.repo_contract",
                            fromlist=["safe_contract_dict"],
                        ).safe_contract_dict(repo_contract)
                    ),
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
                    entry = repo_contract.entry_points[0].path if repo_contract.entry_points else ""
                    context.user_data["pending_run"] = {
                        "project_path": result.path,
                        "entry_point": entry,
                        "run_seconds": _plan_live_seconds(user),
                    }
                    lines.append("")
                    lines.append("🚀 *للتشغيل الحقيقي:* أرسل توكن البوت من @BotFather")
                await status.edit_text("\n".join(lines))
            except Exception as e:
                logger.exception("understand after private clone failed")
                await status.edit_text("\n".join(lines + [f"⚠️ الفهم فشل: {type(e).__name__}"]))
            return True


    pending = (context.user_data or {}).get("pending_deploy")
    if pending and looks_like_bot_token(request):
        await handle_live_deploy_token(message, context, normalize_bot_token(request), pending)
        return True

    return False
