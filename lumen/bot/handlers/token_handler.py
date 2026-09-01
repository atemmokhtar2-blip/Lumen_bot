"""Isolated handling of Telegram bot tokens and private-repo PATs."""
from __future__ import annotations

import asyncio
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from ..config import OUTPUT_DIR, logger
from ..helpers import safe_edit_text, safe_reply_text, looks_like_bot_token, normalize_bot_token
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
    # Consume secrets submitted via Mini App (never transit chat history)
    try:
        from lumen.platform.secret_inbox import consume_secret, peek_meta
        uid = int(getattr(user, "id", 0) or 0)
        if uid:
            for kind in ("bot", "github"):
                meta = peek_meta(user_id=uid, kind=kind)
                if not meta:
                    continue
                # Only inject when a pending flow needs this kind
                needs_bot = bool(
                    (context.user_data or {}).get("pending_host")
                    or (context.user_data or {}).get("pending_run")
                    or (context.user_data or {}).get("pending_live_run")
                    or (context.user_data or {}).get("pending_deploy")
                )
                needs_gh = bool(
                    (context.user_data or {}).get("pending_clone_auth")
                    or (context.user_data or {}).get("pending_create_repo")
                    or (context.user_data or {}).get("pending_git_push")
                )
                if kind == "bot" and not needs_bot:
                    continue
                if kind == "github" and not needs_gh:
                    continue
                plain = consume_secret(user_id=uid, kind=kind)
                if plain:
                    request = plain
                    try:
                        await safe_reply_text(message, 
                            "✅ تم استلام السر من اللوحة الآمنة وتشفيره — جاري المتابعة."
                        )
                    except Exception:
                        pass
                    break
    except Exception:
        logger.exception("secret_inbox consume failed")

    # Spec 065 — if user is sending a bot token after successful generation
    pending_host = (context.user_data or {}).get("pending_host")
    if pending_host and looks_like_bot_token(request):
        # Resolve path if UI left a relative/stale ref
        try:
            from lumen.bot.ui.project_resolve import resolve_project_path, resolve_entry_point
            _root = resolve_project_path(str(pending_host.get("project_path") or ""), context.user_data)
            if _root is not None:
                pending_host = dict(pending_host)
                pending_host["project_path"] = str(_root)
                pending_host.setdefault("entry_point", resolve_entry_point(_root))
                context.user_data["pending_host"] = pending_host
        except Exception:
            pass
        context.user_data.pop("pending_host", None)
        # Ensure trial pending cannot steal this token mid-flight
        if context.user_data is not None:
            context.user_data.pop("pending_run", None)
            context.user_data.pop("pending_live_run", None)
            context.user_data.pop("pending_deploy", None)
        _sent = await safe_reply_text(message, 
            "🚀 جاري بدء الاستضافة الدائمة (HostService / Firecracker)..."
        )

        status = _sent[-1] if _sent else None

        if status is None:

            return
        await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)

        # SECURITY (Vuln #3): validate project_path against per-user sandbox
        try:
            from lumen.api.security import validate_user_project_path
            _uid = message.from_user.id if message.from_user else 0
            _validated = str(validate_user_project_path(_uid, pending_host.get("project_path") or ""))
            pending_host = dict(pending_host)
            pending_host["project_path"] = _validated
            context.user_data["pending_host"] = pending_host
        except ValueError:
            try:
                from lumen.bot.ui.actionable_errors import send_actionable_error
                await send_actionable_error(status, kind="generic", title="مسار غير صالح", detail="خارج مساحة المستخدم المعزولة", user_id=int(_uid or 0))
            except Exception:
                await safe_edit_text(status, "❌ مسار المشروع غير صالح.")
            return True

        def _do_host():
            from lumen.engine.services.hosting import get_hosting_service
            svc = get_hosting_service(OUTPUT_DIR)
            return svc.start(
                user_id=message.from_user.id if message.from_user else 0,
                project_path=pending_host.get("project_path") or "",
                bot_token=normalize_bot_token(request),
            )

        # Scrub secret from chat BEFORE long host work (reduces residual exposure)
        try:
            from lumen.bot.ui.token_hygiene import scrub_and_confirm
            await scrub_and_confirm(update_message=message, bot=context.bot)
        except Exception:
            logger.exception("token scrub after pending_host failed")

        try:
            result = await asyncio.to_thread(_do_host)
        except Exception as e:
            logger.exception("hosting start failed")
            try:
                from lumen.bot.ui.actionable_errors import host_error
                uid = message.from_user.id if message.from_user else 0
                text, markup = host_error(
                    detail=f"{type(e).__name__}",
                    project_path=str(pending_host.get("project_path") or ""),
                    user_id=int(uid or 0),
                )
                await safe_edit_text(status, text, reply_markup=markup)
            except Exception:
                try:
                    from lumen.bot.ui.actionable_errors import send_actionable_error
                    await send_actionable_error(status, kind="host", detail=type(e).__name__, project_path=str(pending_host.get("project_path") or ""), user_id=int(message.from_user.id if message.from_user else 0))
                except Exception:
                    await safe_edit_text(status, f"❌ فشل الاستضافة (`{type(e).__name__}`).")
            try:
                from lumen.bot.ui.emit_context import emit_context_event, classify_host_failure
                await emit_context_event(
                    message=message, context=context, user=message.from_user,
                    kind=classify_host_failure(str(e)),
                    detail=f"hosting start exception: {type(e).__name__}",
                )
            except Exception:
                pass
            return True

        if getattr(result, "ok", False):
            try:
                from lumen.bot.ui.host_panel import attach_host_panel
                uid = message.from_user.id if message.from_user else 0
                await attach_host_panel(
                    status_message=status,
                    result=result,
                    user_id=int(uid or 0),
                    user_data=context.user_data,
                )
            except Exception:
                logger.exception("attach_host_panel failed")
                try:
                    from lumen.bot.ui.host_panel import host_panel_buttons, format_host_success
                    from lumen.bot.ui.keyboards import build_inline_keyboard
                    uid = message.from_user.id if message.from_user else 0
                    markup = build_inline_keyboard(host_panel_buttons(), user_id=int(uid or 0))
                    await safe_edit_text(status, format_host_success(result), reply_markup=markup)
                except Exception:
                    await safe_edit_text(status, result.to_user_text())
        else:
            try:
                from lumen.bot.ui.actionable_errors import host_error
                uid = message.from_user.id if message.from_user else 0
                text, markup = host_error(
                    detail=str(getattr(result, "message", "") or "")[:280],
                    project_path=str(pending_host.get("project_path") or ""),
                    user_id=int(uid or 0),
                )
                await safe_edit_text(status, text, reply_markup=markup)
            except Exception:
                await safe_edit_text(status, result.to_user_text())
            try:
                from lumen.bot.ui.emit_context import emit_context_event, classify_host_failure
                await emit_context_event(
                    message=message, context=context, user=message.from_user,
                    kind=classify_host_failure(getattr(result, "message", "") or ""),
                    detail=str(getattr(result, "message", "") or "")[:400],
                )
            except Exception:
                pass
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
            # Only honor deploy pending when it was explicitly plane-bound
            plane = str(pending_deploy.get("plane") or "").strip()
            if plane in {"trial_chat", "TRIAL_CHAT"} or pending_deploy.get("sandbox"):
                pending_run = {
                    "project_path": pending_deploy.get("project_path") or "",
                    "entry_point": pending_deploy.get("entry_point") or "",
                    "run_seconds": _plan_live_seconds(user),
                    "plane": plane or "trial_chat",
                }
                context.user_data["pending_run"] = pending_run
        # Phase 1: never invent trial pending from active_repo or disk recovery.
        # User must choose «تجربة في الشات» or «استضافة دائمة» first.
        if pending_run and pending_run.get("project_path"):
            try:
                from lumen.bot.ui.token_hygiene import scrub_and_confirm
                await scrub_and_confirm(update_message=message, bot=context.bot)
            except Exception:
                logger.exception("token scrub before live run failed")
            await handle_live_run_token(message, context, token_text, pending_run)
            _persist_session(user, context)
            return True

        # Token sent but no explicit plane pending
        await safe_reply_text(
            message,
            "استلمت توكن بوت، لكن مفيش مسار تشغيل محدد.\n"
            "بعد التوليد اختر من الأزرار:\n"
            "• تجربة في الشات — تشغيل مؤقت\n"
            "• استضافة دائمة — HostService / Firecracker\n"
            "أو اكتب: استضف",
        )
        return True


    # Create repo: user sends GitHub PAT after being asked
    pending_create = (context.user_data or {}).get("pending_create_repo")
    if pending_create:
        from lumen.engine.services.git_safe_import import get_smart_clone
        extract_token = get_smart_clone().extract_token
        from lumen.engine.services.git_operations.smart_git import run_git_intent
        git_tok = extract_token(request)
        if git_tok:
            try:
                from lumen.bot.ui.token_hygiene import scrub_and_confirm
                await scrub_and_confirm(update_message=message, bot=context.bot)
            except Exception:
                logger.exception("PAT scrub before create_repo failed")
            name = str(pending_create.get("name") or "").strip()
            _sent = await safe_reply_text(message, f"🔑 جاري إنشاء المستودع `{name}`...")

            status = _sent[-1] if _sent else None

            if status is None:

                return
            await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)
            uid = int(user.id) if user else 0
            try:
                from lumen.engine.services.user_sandbox import get_user_sandbox
                dest = get_user_sandbox(uid, OUTPUT_DIR).new_clone_dir(label="newrepo")
            except Exception:
                logger.exception("sandbox allocation failed for user %s (newrepo)", uid)
                try:
                    from lumen.bot.ui.actionable_errors import send_actionable_error
                    await send_actionable_error(status, kind="generic", title="مساحة معزولة", detail="تعذّر الإنشاء — رُفض لأسباب أمان", user_id=int(user.id) if user else 0)
                except Exception:
                    await safe_edit_text(status, "❌ تعذّر إنشاء مساحة معزولة.")
                return True

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
                try:
                    from lumen.bot.ui.actionable_errors import create_repo_error
                    _uid = int(user.id) if user else 0
                    text, markup = create_repo_error(
                        detail=type(e).__name__, user_id=_uid
                    )
                    await safe_edit_text(status, text, reply_markup=markup)
                except Exception:
                    try:
                        from lumen.bot.ui.actionable_errors import send_actionable_error
                        await send_actionable_error(status, kind="create", detail=type(e).__name__, user_id=int(user.id) if user else 0)
                    except Exception:
                        await safe_edit_text(status, f"❌ فشل الإنشاء (`{type(e).__name__}`).")
                return True
            if result.ok:
                context.user_data.pop("pending_create_repo", None)
                if result.path:
                    context.user_data["active_repo"] = {
                        "path": result.path,
                        "url": result.url or "",
                    }
                    context.user_data["last_project_path"] = result.path
                try:
                    from lumen.bot.ui.rtl_text import code_path, code_url
                    body = f"✅ {result.message}"
                    if result.url:
                        body += f"\n• الرابط: {code_url(result.url)}"
                    if result.path:
                        body += f"\n• المسار: {code_path(result.path)}"
                    await safe_edit_text(status, body)
                except Exception:
                    await safe_edit_text(status, f"✅ {result.message}")
            else:
                try:
                    from lumen.bot.ui.actionable_errors import create_repo_error
                    _uid = int(user.id) if user else 0
                    text, markup = create_repo_error(
                        detail=str(getattr(result, "message", "") or "create_failed"),
                        user_id=_uid,
                    )
                    await safe_edit_text(status, text, reply_markup=markup)
                except Exception:
                    try:
                        from lumen.bot.ui.actionable_errors import send_actionable_error
                        await send_actionable_error(status, kind="create", detail=str(result.message or ""), user_id=int(user.id) if user else 0)
                    except Exception:
                        await safe_edit_text(status, f"❌ {result.message}")
            return True

    # Push: PAT after auth failure
    pending_push = (context.user_data or {}).get("pending_git_push")
    if pending_push:
        from lumen.engine.services.git_safe_import import get_smart_clone
        extract_token = get_smart_clone().extract_token
        from lumen.engine.services.git_operations.smart_git import git_push
        git_tok = extract_token(request)
        if git_tok:
            path = str(pending_push.get("path") or "").strip()
            # SECURITY (Vuln #3): validate path against per-user sandbox before push
            try:
                from lumen.api.security import validate_user_project_path
                uid = int(user.id) if user else 0
                path = str(validate_user_project_path(uid, path))
            except ValueError:
                try:
                    from lumen.bot.ui.actionable_errors import send_actionable_error
                    await send_actionable_error(message, kind="generic", title="مسار غير صالح", detail="خارج العزل", user_id=int(user.id) if user else 0)
                except Exception:
                    await safe_reply_text(message, "❌ مسار المشروع غير صالح.")
                return True
            _sent = await safe_reply_text(message, "🔑 جاري الدفع بالتوكن...")

            status = _sent[-1] if _sent else None

            if status is None:

                return
            result = await asyncio.to_thread(lambda: git_push(path, token=git_tok))
            if result.ok:
                context.user_data.pop("pending_git_push", None)
                await safe_edit_text(status, f"✅ {result.message}")
            else:
                try:
                    from lumen.bot.ui.actionable_errors import git_op_error
                    _uid = int(user.id) if user else 0
                    text, markup = git_op_error(op="push", detail="push_failed", user_id=_uid)
                    await safe_edit_text(status, text, reply_markup=markup)
                except Exception:
                    try:
                        from lumen.bot.ui.actionable_errors import send_actionable_error
                        await send_actionable_error(status, kind="push", detail="push_failed", user_id=int(user.id) if user else 0)
                    except Exception:
                        await safe_edit_text(status, "❌ فشلت العملية.")
            return True

    # Private repo: user sends GitHub PAT after auth failure
    pending_clone = (context.user_data or {}).get("pending_clone_auth")
    if pending_clone:
        from lumen.engine.services.git_safe_import import get_smart_clone
        _sc = get_smart_clone()
        extract_token = _sc.extract_token
        smart_clone = _sc.smart_clone
        git_tok = extract_token(request)
        if git_tok:
            try:
                from lumen.bot.ui.token_hygiene import scrub_and_confirm
                await scrub_and_confirm(update_message=message, bot=context.bot)
            except Exception:
                logger.exception("PAT scrub before reclone failed")
            _sent = await safe_reply_text(message, "🔑 جاري إعادة سحب المستودع بالتوكن...")

            status = _sent[-1] if _sent else None

            if status is None:

                return
            await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)
            uid = int(user.id) if user else 0
            try:
                from lumen.engine.services.user_sandbox import get_user_sandbox
                dest = get_user_sandbox(uid, OUTPUT_DIR).new_clone_dir(label="reclone")
            except Exception:
                logger.exception("sandbox allocation failed for user %s (reclone)", uid)
                try:
                    from lumen.bot.ui.actionable_errors import send_actionable_error
                    await send_actionable_error(status, kind="generic", title="مساحة معزولة", detail="إعادة السحب مرفوضة", user_id=int(uid or 0))
                except Exception:
                    await safe_edit_text(status, "❌ تعذّر إنشاء مساحة معزولة.")
                return True
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
                logger.exception("private reclone failed")
                try:
                    from lumen.bot.ui.actionable_errors import private_clone_error
                    text, markup = private_clone_error(
                        url=url, detail=type(e).__name__, user_id=int(uid or 0)
                    )
                    await safe_edit_text(status, text, reply_markup=markup)
                except Exception:
                    try:
                        from lumen.bot.ui.actionable_errors import git_op_error
                        _uid = int(user.id) if user else 0
                        text, markup = git_op_error(op="clone", detail=type(e).__name__, user_id=_uid)
                        await safe_edit_text(status, text, reply_markup=markup)
                    except Exception:
                        try:
                            from lumen.bot.ui.actionable_errors import send_actionable_error
                            await send_actionable_error(status, kind="clone", detail=type(e).__name__, url=url, user_id=int(uid or 0))
                        except Exception:
                            await safe_edit_text(status, f"❌ فشل السحب بالتوكن (`{type(e).__name__}`).")
                return True

            finally:
                try:
                    git_tok = None  # drop reference
                    del git_tok
                except Exception:
                    pass

            if not result.ok:
                try:
                    from lumen.bot.ui.actionable_errors import private_clone_error
                    detail = (result.message or "")[:200]
                    if result.stderr:
                        detail = (detail + " " + str(result.stderr)[:150]).strip()
                    text, markup = private_clone_error(
                        url=url, detail=detail, user_id=int(uid or 0)
                    )
                    await safe_edit_text(status, text, reply_markup=markup)
                except Exception:
                    err_msg = f"❌ {result.message}"
                    if result.stderr:
                        err_msg += f"\n`{result.stderr[:250]}`"
                    await safe_edit_text(status, err_msg)
                if not result.needs_auth:
                    context.user_data.pop("pending_clone_auth", None)
                return True

            context.user_data.pop("pending_clone_auth", None)
            try:
                await safe_edit_text(status, "🔍 جاري فهم المستودع...")
                from lumen.engine.services.repo_understanding import understand_repo

                def _do_u():
                    return understand_repo(result.path, remote_url=result.url or "")

                repo_contract = await asyncio.to_thread(_do_u)
                context.user_data["active_repo"] = {
                    "path": result.path,
                    "url": result.url,
                    "contract": (
                        __import__(
                            "lumen.engine.schemas.repo_contract",
                            fromlist=["safe_contract_dict"],
                        ).safe_contract_dict(repo_contract)
                    ),
                }
                try:
                    from lumen.engine.services.user_sandbox import get_user_sandbox
                    uid = int(user.id) if user else 0
                    get_user_sandbox(uid, OUTPUT_DIR).register_clone(
                        result.path, url=result.url or "", label=Path(result.path).name
                    )
                except Exception:
                    logger.exception("register_clone failed")
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
                from lumen.bot.ui.repo_sections import (
                    build_sections_from_contract,
                    section_keyboard,
                    store_sections,
                )
                sections = build_sections_from_contract(
                    repo_contract, path=result.path or "", url=result.url or ""
                )
                store_sections(context.user_data, sections)
                header = sections.get("header") or "✅ تم فهم المستودع"
                if _is_runnable:
                    header += "\n\n🚀 للتشغيل الحقيقي: أرسل توكن البوت من @BotFather أو اضغط الزر."
                await safe_edit_text(status, 
                    header,
                    reply_markup=section_keyboard(
                        user_id=int(uid or 0), show_run=bool(_is_runnable)
                    ),
                )
            except Exception as e:
                logger.exception("understand after private clone failed")
                from lumen.bot.ui.rtl_text import code_path, code_url
                await safe_edit_text(status, 
                    "✅ تم السحب\n"
                    f"• الرابط: {code_url(result.url or '')}\n"
                    f"• المسار: {code_path(result.path or '')}\n"
                    f"⚠️ الفهم فشل: {type(e).__name__}"
                )
            return True


    pending = (context.user_data or {}).get("pending_deploy")
    if pending and looks_like_bot_token(request):
        await handle_live_deploy_token(message, context, normalize_bot_token(request), pending)
        return True

    return False
