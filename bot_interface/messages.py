"""Main text message handler for the Telegram bot interface."""

from __future__ import annotations

import asyncio
import re
import tempfile
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from .config import OUTPUT_DIR, logger
from .helpers import (
    is_allowed,
    looks_like_bot_token,
    detect_host_intent,
    chat_route,
    escape_md,
    safe_edit_text,
    make_zip_from_path,
    run_generation,
)
from .live import handle_live_run_token, handle_live_deploy_token


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.message
    if not message or not message.text:
        return

    if not is_allowed(user.id if user else None):
        await message.reply_text("⛔ غير مصرح لك باستخدام هذا البوت.")
        return

    request = message.text.strip()
    if not request or request.startswith("/"):
        return

    # Phase 2: per-user memory (dynamic context only — no fixed reply templates)
    uid = int(user.id) if user else 0
    try:
        from telegram_bot_engine.formal_engine.services.user_memory import get_user_memory
        _mem = get_user_memory(uid, OUTPUT_DIR)
        _mem.add_turn("user", request)
    except Exception:
        _mem = None
        logger.exception("user_memory load failed")

    # Spec 065 — if user is sending a bot token after successful generation
    pending_host = (context.user_data or {}).get("pending_host")
    if pending_host and looks_like_bot_token(request):
        context.user_data.pop("pending_host", None)
        status = await message.reply_text("🚀 جاري بدء الاستضافة (عملية طويلة الأمد)...")
        await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)

        def _do_host():
            from telegram_bot_engine.formal_engine.services.hosting import get_hosting_service
            svc = get_hosting_service(OUTPUT_DIR)
            return svc.start(
                user_id=message.from_user.id if message.from_user else 0,
                project_path=pending_host.get("project_path") or "",
                bot_token=request,
            )

        try:
            result = await asyncio.to_thread(_do_host)
        except Exception as e:
            logger.exception("hosting start failed")
            await status.edit_text(f"❌ فشل الاستضافة: {type(e).__name__}: {str(e)[:200]}")
            return
        await status.edit_text(result.to_user_text())
        return

    pending_run = (context.user_data or {}).get("pending_run")
    if looks_like_bot_token(request):
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
                    "run_seconds": int(__import__("os").environ.get("LIVE_RUN_SECONDS", 900)),
                }
                context.user_data["pending_run"] = pending_run
        if pending_run:
            await handle_live_run_token(message, context, request, pending_run)
            return

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
                from telegram_bot_engine.formal_engine.services.user_sandbox import get_user_sandbox
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
                logger.exception("private reclone failed")
                await status.edit_text(f"❌ فشل السحب بالتوكن: {type(e).__name__}: {str(e)[:200]}")
                return
            finally:
                git_tok = ""  # noqa: F841

            if not result.ok:
                err_msg = f"❌ {result.message}"
                if result.stderr:
                    err_msg += f"\n`{result.stderr[:250]}`"
                await status.edit_text(err_msg)
                if not result.needs_auth:
                    context.user_data.pop("pending_clone_auth", None)
                return

            context.user_data.pop("pending_clone_auth", None)
            lines = [
                "✅ تم سحب المستودع الخاص بنجاح",
                f"• الرابط: `{result.url or ''}`",
                f"• المسار: `{result.path or ''}`",
            ]
            try:
                await status.edit_text("\n".join(lines + ["", "🔍 جاري فهم المستودع..."]))
                from telegram_bot_engine.formal_engine.services.repo_understanding import understand_repo

                def _do_u():
                    return understand_repo(result.path, remote_url=result.url or "")

                repo_contract = await asyncio.to_thread(_do_u)
                context.user_data["active_repo"] = {
                    "path": result.path,
                    "url": result.url,
                    "contract": repo_contract.model_dump(mode="json"),
                }
                try:
                    from telegram_bot_engine.formal_engine.services.user_sandbox import get_user_sandbox
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
                        "run_seconds": int(__import__("os").environ.get("LIVE_RUN_SECONDS", 900)),
                    }
                    lines.append("")
                    lines.append("🚀 *للتشغيل الحقيقي:* أرسل توكن البوت من @BotFather")
                await status.edit_text("\n".join(lines))
            except Exception as e:
                logger.exception("understand after private clone failed")
                await status.edit_text("\n".join(lines + [f"⚠️ الفهم فشل: {type(e).__name__}"]))
            return

    pending = (context.user_data or {}).get("pending_deploy")
    if pending and looks_like_bot_token(request):
        await handle_live_deploy_token(message, context, request, pending)
        return

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
        from telegram_bot_engine.formal_engine.services.chat_router import route_message as _route_msg
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
            from telegram_bot_engine.formal_engine.services.user_sandbox import get_user_sandbox
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
            await status.edit_text(f"❌ فشل سحب المستودع: {type(e).__name__}: {str(e)[:200]}")
            return

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
                    from telegram_bot_engine.formal_engine.services.repo_understanding import (
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
                        from telegram_bot_engine.formal_engine.services.user_sandbox import get_user_sandbox
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
                            "run_seconds": int(__import__("os").environ.get("LIVE_RUN_SECONDS", 900)),
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
        return

    # --- Hosting (owner-only foundation; no billing yet) ---
    host_action = detect_host_intent(request)
    if host_action != "none":
        from telegram_bot_engine.formal_engine.services.hosting import get_hosting_service
        svc = get_hosting_service(OUTPUT_DIR)
        uid = message.from_user.id if message.from_user else 0
        active = (context.user_data or {}).get("active_repo") or {}

        if host_action == "start":
            project_path = active.get("path") or ""
            if not project_path or not Path(project_path).exists():
                await message.reply_text(
                    "ما فيش مشروع نشط للاستضافة.\n"
                    "اسحب مستودع أو ولّد بوت أولاً، بعدين اكتب: استضف"
                )
                return
            context.user_data["pending_host"] = {
                "project_path": project_path,
                "user_id": uid,
            }
            await message.reply_text(
                "🚀 *استضافة المشروع النشط*\n"
                f"• المسار: `{project_path}`\n\n"
                "أرسل الآن توكن البوت من @BotFather لبدء التشغيل الطويل الأمد.\n"
                "(الأساس جاهز — بدون طبقة دفع حالياً)"
            )
            return

        if host_action == "status":
            result = svc.status(user_id=uid)
            await message.reply_text(result.to_user_text())
            return

        if host_action == "stop":
            items = svc.list_for_user(uid)
            running = [i for i in items if i.status == "running"]
            if not running:
                await message.reply_text("ما فيش مثيل استضافة شغال لإيقافه.")
                return
            # stop the most recent running
            target = sorted(running, key=lambda x: x.started_at, reverse=True)[0]
            result = await asyncio.to_thread(
                lambda: svc.stop(instance_id=target.instance_id, user_id=uid)
            )
            await message.reply_text(result.to_user_text())
            return

        if host_action == "diagnose":
            items = svc.list_for_user(uid)
            if not items:
                await message.reply_text("ما فيش مثيلات لتشخيصها.")
                return
            target = sorted(items, key=lambda x: x.started_at, reverse=True)[0]
            result = await asyncio.to_thread(
                lambda: svc.diagnose(user_id=uid, instance_id=target.instance_id)
            )
            await message.reply_text(result.to_user_text())
            return

    # --- Active repo development (must run before generate_bot) ---
    active = (context.user_data or {}).get("active_repo")
    if active and active.get("path") and Path(active["path"]).exists():
        from telegram_bot_engine.formal_engine.services.repo_dev import (
            handle_repo_request,
            detect_repo_intent,
        )
        action, _ = detect_repo_intent(request)
        # ChatRouter knows system capabilities — prefer it for routing only
        _rt = chat_route(request)
        _cap = getattr(_rt, "capability_id", "") if _rt and getattr(_rt, "ok", False) else ""
        _repo_caps = {
            "static_analysis", "package_health", "upgrade_recommend",
            "upgrade_apply", "repo_develop",
        }
        develop_hints = (
            "أضف", "اضف", "ضيف", "عدل", "عدّل", "اشرح", "الأوامر", "الاوامر",
            "امسح", "أعد", "طور", "طوّر", "هيكل", "command", "add", "explain",
            "stats", "fix", "modify", "ساعد", "تقدر",
            "خطة تطوير", "فجوات", "أين أعد", "تطوير المستودع", "سد فجوات",
        )
        if (
            _cap in _repo_caps
            or action != "unknown"
            or any(h in request.lower() for h in develop_hints)
            or any(h in request for h in develop_hints)
        ):
            status = await message.reply_text("🛠 جاري التنفيذ على المستودع النشط...")
            await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)

            # Canonical phrase when ChatRouter recognized capability but wording was soft
            _cap_to_phrase = {
                "static_analysis": "تحليل استاتيكي",
                "package_health": "صحة الحزم",
                "upgrade_recommend": "توصيات الترقية",
                "upgrade_apply": "طبّق الترقيات الآمنة",
                "repo_develop": request,
            }
            _dev_text = request
            if _cap in _cap_to_phrase and action == "unknown":
                _dev_text = _cap_to_phrase[_cap]

            def _run_dev():
                return handle_repo_request(
                    _dev_text,
                    active["path"],
                    contract_dict=active.get("contract"),
                )

            try:
                dev = await asyncio.to_thread(_run_dev)
            except Exception as e:
                logger.exception("RepoDev failed")
                await status.edit_text(f"❌ فشل التنفيذ على المستودع: {type(e).__name__}: {str(e)[:200]}")
                return

            if dev.contract is not None:
                context.user_data["active_repo"] = {
                    "path": active["path"],
                    "url": active.get("url"),
                    "contract": dev.contract.model_dump(mode="json"),
                }

            text_out = dev.message
            if dev.changed_files:
                text_out += "\n• ملفات تغيّرت: " + ", ".join(f"`{f}`" for f in dev.changed_files)
            await status.edit_text(text_out)

            # If file changed, offer zip of repo
            if dev.ok and dev.changed_files and Path(active["path"]).exists():
                try:
                    zip_path = make_zip_from_path(active["path"])
                    if zip_path and zip_path.exists() and zip_path.stat().st_size < 45 * 1024 * 1024:
                        with open(zip_path, "rb") as f:
                            await message.reply_document(
                                document=f,
                                filename=f"{Path(active['path']).name}_updated.zip",
                                caption="📦 المستودع بعد التعديل",
                            )
                except Exception:
                    logger.exception("zip after repo dev failed")
            return


    # ChatRouter: help / list capabilities (route only)
    # Skip help when the message is clearly a bot specification (contains /commands etc.)
    _rt_help = chat_route(request)
    _is_bot_spec = False
    try:
        from telegram_bot_engine.formal_engine.services.chat_router.service import _looks_like_bot_spec
        _is_bot_spec = _looks_like_bot_spec(request)
    except Exception:
        _is_bot_spec = bool(
            re.search(r"اعمل\s*بوت|أن?شئ\s*بوت|عايز\s*بوت", request, re.I)
            or len(re.findall(r"/[a-zA-Z][a-zA-Z0-9_]{1,32}", request)) >= 2
        )
    if (
        (not _is_bot_spec)
        and _rt_help
        and getattr(_rt_help, "ok", False)
        and _rt_help.capability_id == "help"
    ):
        try:
            from telegram_bot_engine.formal_engine.services.chat_router import get_router
            await message.reply_text(get_router().help_text())
        except Exception:
            await message.reply_text("مساعدة: اسحب مستودع | ولّد بوت | استضافة | تحليل استاتيكي")
        return

    # ------------------------------------------------------------------
    # Conversational AI layer (SmartChat + UserMemory) when the message is not
    # clearly a bot specification. AI understands and routes; no fixed scripts.
    # ------------------------------------------------------------------
    if not _is_bot_spec:
        _rt = chat_route(request)
        _hard_caps = {
            "clone_repo", "host_start", "host_stop", "host_status", "host_diagnose",
            "static_analysis", "package_health", "upgrade_recommend", "upgrade_apply",
            "repo_develop", "live_run", "generate_bot",
        }
        _is_hard = (
            _rt is not None
            and getattr(_rt, "ok", False)
            and getattr(_rt, "capability_id", "") in _hard_caps
            and float(getattr(_rt, "confidence", 0) or 0) >= 0.55
        )
        if not _is_hard:
            try:
                from telegram_bot_engine.chat_ai import smart_chat_reply
                mem_ctx = _mem.context_for_ai() if _mem else ""
                sc = await asyncio.to_thread(
                    smart_chat_reply,
                    request,
                    memory_context=mem_ctx,
                )
                sc_type = getattr(sc, "type", "") or ""
                sc_text = (getattr(sc, "text", None) or "").strip()
                sc_cap = getattr(sc, "capability_id", None) or ""
                sc_conf = float(getattr(sc, "confidence", 0) or 0)

                # AI recommends generation with clear intent → fall through to formal
                if sc_type == "recommend" and sc_cap == "generate_bot" and sc_conf >= 0.55:
                    pass  # continue to formal generation below
                elif sc_type == "recommend" and sc_cap in _hard_caps and sc_conf >= 0.55:
                    # Let existing handlers above deal with hard caps on next patterns;
                    # if we reached here, reply with AI text so user can refine.
                    if sc_text:
                        if _mem:
                            _mem.add_turn("assistant", sc_text, meta={"capability": sc_cap})
                            _mem.set_last(intent=request[:200], capability=sc_cap)
                        await message.reply_text(sc_text)
                        return
                elif sc_text:
                    if _mem:
                        _mem.add_turn("assistant", sc_text, meta={"capability": sc_cap or "chat"})
                        if sc_cap:
                            _mem.set_last(intent=request[:200], capability=sc_cap)
                    await message.reply_text(sc_text)
                    return
            except Exception:
                logger.exception("smart_chat path failed")
                # fall through to generation attempt rather than fixed error scripts

    # ------------------------------------------------------------------
    # Generate via SpecTranslator (Hugging Face) + Formal Engine.
    # No progressive clarification questionnaires — AI handles understanding.
    # ------------------------------------------------------------------
    if len(request) < 2:
        await message.reply_text("اكتب وصف البوت عشان أبدأ التوليد.")
        return

    # Clear any leftover clarification session state
    if context.user_data is not None:
        context.user_data.pop("pending_spec", None)

    status_msg = await message.reply_text(
        "⏳ جاري ترجمة الوصف وتوليد المشروع (Hugging Face + Formal Engine)..."
    )
    await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)

    # Isolated per-user workspace (never share host bot dir/token space)
    try:
        from telegram_bot_engine.formal_engine.services.user_sandbox import get_user_sandbox
        uid = int(user.id) if user else 0
        work_dir = get_user_sandbox(uid, OUTPUT_DIR).new_project_dir(label="gen")
    except Exception:
        work_dir = Path(tempfile.mkdtemp(prefix="botgen_", dir=str(OUTPUT_DIR)))

    try:
        result = await asyncio.to_thread(run_generation, request, work_dir)

        if result is None:
            await status_msg.edit_text("❌ فشل التوليد (نتيجة فارغة).")
            return

        success = getattr(result, "success", False)
        project_path = getattr(result, "project_path", None)
        errors = getattr(result, "errors", []) or []
        stages = getattr(result, "stages", []) or []

        ok_stages = sum(1 for s in stages if getattr(s, "success", False))
        total_stages = len(stages)

        summary_lines = [
            f"{'✅' if success else '⚠️'} *نتيجة التوليد*",
            f"• النجاح: {'نعم' if success else 'جزئي / فشل'}",
            f"• المراحل الناجحة: {ok_stages}/{total_stages}",
        ]
        if project_path:
            summary_lines.append(f"• المسار: `{escape_md(project_path)}`")
        meta = getattr(result, "metadata", None) or {}
        if meta.get("button_count") is not None:
            summary_lines.append(f"• الأزرار في /start: {meta.get('button_count')}")
        if meta.get("buttons"):
            summary_lines.append(f"• نصوص الأزرار: {', '.join(meta.get('buttons') or [])}")
        if meta.get("commands"):
            summary_lines.append(f"• الأوامر: {'/' + ' /'.join(meta.get('commands') or [])}")
        if errors:
            summary_lines.append("• أخطاء:")
            for e in errors[:5]:
                # Dynamic engine errors often contain _, *, ` — escape them
                summary_lines.append(f"  - {escape_md(e)}")

        # Keep summary short — no engine marketing blurb after generation

        await safe_edit_text(status_msg, "\n".join(summary_lines), use_markdown=True)

        # Register into this user's private workspace index (dynamic, no templates)
        if project_path and Path(project_path).exists():
            try:
                from telegram_bot_engine.formal_engine.services.user_sandbox import get_user_sandbox
                uid = int(user.id) if user else 0
                get_user_sandbox(uid, OUTPUT_DIR).register_project(
                    project_path,
                    label=Path(project_path).name,
                    source_request=request,
                    kind="generated",
                    extra={
                        "success": bool(success),
                        "commands": list((meta or {}).get("commands") or [])[:30],
                    },
                )
            except Exception:
                logger.exception("register_project failed")
            try:
                from telegram_bot_engine.formal_engine.services.user_memory import get_user_memory
                mem = get_user_memory(uid, OUTPUT_DIR)
                mem.set_last(
                    intent=request[:200],
                    project_path=str(project_path),
                    capability="generate_bot",
                )
                cmds = list((meta or {}).get("commands") or [])[:20]
                note = f"generated project at {project_path}"
                if cmds:
                    note += " commands=" + ",".join(cmds)
                mem.add_turn("note", note, meta={"capability": "generate_bot", "success": bool(success)})
            except Exception:
                logger.exception("user_memory update after generate failed")

        # Try to send zip if project exists
        if project_path and Path(project_path).exists():
            zip_path = make_zip_from_path(project_path)
            if zip_path and zip_path.exists() and zip_path.stat().st_size > 0:
                size_mb = zip_path.stat().st_size / (1024 * 1024)
                if size_mb < 48:  # Telegram limit ~50MB
                    await message.reply_document(
                        document=zip_path.open("rb"),
                        filename=zip_path.name,
                        caption="📦 المشروع المُولَّد (zip)",
                    )
                else:
                    await message.reply_text(
                        f"📦 تم إنشاء المشروع لكن حجم الـ zip كبير ({size_mb:.1f} MB). "
                        "يمكنك الوصول إليه من السيرفر."
                    )
            else:
                await message.reply_text("تم التوليد لكن تعذر إنشاء ملف zip.")

            # Structural review report + token request only if gate passed
            ready = bool(success) and bool(meta.get("ready_for_token", success))
            gate = meta.get("static_gate") or {}
            if gate:
                g_lines = [
                    "🔬 مراجعة StaticDevGate",
                    "• النتيجة: " + ("نجاح" if gate.get("ok") else "فشل"),
                    f"• أخطاء: {gate.get('errors', 0)} | تحذيرات: {gate.get('warnings', 0)}",
                ]
                for f in (gate.get("findings") or [])[:8]:
                    if f.get("severity") == "error":
                        g_lines.append(f"  🔴 {f.get('code')}: {str(f.get('msg', ''))[:80]}")
                await message.reply_text("\n".join(g_lines))

            if ready:
                context.user_data["pending_deploy"] = {
                    "project_path": str(project_path),
                    "owner_user_id": user.id if user else None,
                    "sandbox": True,
                }
                context.user_data["pending_live_run"] = {
                    "project_path": str(project_path),
                    "owner_user_id": user.id if user else None,
                }
                await message.reply_text(
                    "📦 المشروع جاهز.\n"
                    "🔑 أرسل توكن البوت من @BotFather لتجربته."
                )
            else:
                await message.reply_text(
                    "⚠️ المشروع اتولّد لكن في أخطاء — راجع الملخص أعلاه."
                )

        elif not success:
            await message.reply_text(
                "لم يُنشأ مشروع. جرّب وصفاً أبسط أو أوضح."
            )

    except Exception as e:
        logger.exception("Generation failed")
        err_text = escape_md(str(e)[:400])
        await safe_edit_text(
            status_msg,
            f"❌ حدث خطأ أثناء التوليد:\n`{err_text}`\n\n"
            "راجع السجلات أو أعد المحاولة. المحرك الرسمي نشط.",
            use_markdown=True,
        )
    finally:
        # Optional cleanup of very old temp dirs can be added later.
        # Keep the last result for inspection on the server.
        pass


