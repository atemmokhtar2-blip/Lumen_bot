"""Main text message handler for the Telegram bot interface."""

from __future__ import annotations

import asyncio
import os
import re
import tempfile
import time
from collections import defaultdict
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from .config import OUTPUT_DIR, logger
from .sanitize import sanitize_error
from .helpers import (
    is_allowed,
    looks_like_bot_token,
    normalize_bot_token,
    detect_host_intent,
    chat_route,
    escape_md,
    safe_edit_text,
    make_zip_from_path,
    run_generation,
)
from .live import handle_live_run_token, handle_live_deploy_token
from .progress_tracker import run_with_heartbeat
from .session_store import get_session_store
from .capability_boundaries import rejection_message, get_help_text as honest_help

# Process-safe rate limit (SQLite shared across workers / multi-process).
from .config import RATE_LIMIT_PER_MINUTE, RATE_LIMIT_WINDOW_SECONDS


def _rate_limit_ok(user_id: int) -> bool:
    try:
        from b2b_platform.rate_limit import get_rate_limiter
        return get_rate_limiter().allow(
            f"tg:{int(user_id)}",
            limit=RATE_LIMIT_PER_MINUTE,
            window_sec=RATE_LIMIT_WINDOW_SECONDS,
        )
    except Exception:
        return True


def _rate_limit_wait_seconds(user_id: int) -> int:
    try:
        from b2b_platform.rate_limit import get_rate_limiter
        return get_rate_limiter().seconds_until_allow(
            f"tg:{int(user_id)}",
            limit=RATE_LIMIT_PER_MINUTE,
            window_sec=RATE_LIMIT_WINDOW_SECONDS,
        )
    except Exception:
        return int(RATE_LIMIT_WINDOW_SECONDS)


def _persist_session(user, context) -> None:
    try:
        if user and context.user_data is not None:
            get_session_store().save(int(user.id), context.user_data)
    except Exception:
        pass


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.message
    if not message or not message.text:
        return

    if not is_allowed(user.id if user else None):
        await message.reply_text("⛔ غير مصرح لك باستخدام هذا البوت.")
        return

    uid_check = int(user.id) if user else 0
    if not _rate_limit_ok(uid_check):
        wait_s = _rate_limit_wait_seconds(uid_check)
        await message.reply_text(
            f"⏳ تجاوزت الحد المسموح من الطلبات. انتظر حوالي {wait_s} ثانية ثم حاول مرة أخرى."
        )
        return

    # Groups: only respond when @mentioned or replied-to (avoid spam)
    try:
        chat = update.effective_chat
        if chat and getattr(chat, "type", "") in {"group", "supergroup"}:
            bot_user = getattr(context.bot, "username", None) or ""
            text0 = (message.text or "")
            mentioned = bool(bot_user and f"@{bot_user}".lower() in text0.lower())
            is_reply_to_us = bool(
                message.reply_to_message
                and message.reply_to_message.from_user
                and message.reply_to_message.from_user.id == context.bot.id
            )
            if not mentioned and not is_reply_to_us:
                return
    except Exception:
        pass

    request = message.text.strip()

    # Restore durable session (pending_run etc.) after restarts
    try:
        if user and context.user_data is not None:
            saved = get_session_store().load(int(user.id))
            for k, v in (saved or {}).items():
                context.user_data.setdefault(k, v)
    except Exception:
        pass

    if not request:
        await message.reply_text("اكتب وصفاً للبوت أو /help.")
        return
    if request.startswith("/"):
        return
    # Very short non-spec confirmations
    if len(request) < 3 and request.lower() not in {"ok", "yes", "لا", "نعم"}:
        await message.reply_text(
            "الرسالة قصيرة جداً. اكتب ماذا يفعل البوت (مثال: بوت فيه /start و /help)."
        )
        return

    # Phase 2+3: per-user memory + smart context (dynamic only — no fixed scripts)
    uid = int(user.id) if user else 0

    # ── Stage-3: continuous learning from feedback ───────────────────────
    try:
        from telegram_bot_engine.spec_core.language_understanding.continuous_learning import (
            is_feedback_only,
            learn_from_feedback_message,
            detect_outcome,
        )
        if uid and is_feedback_only(request):
            from telegram_bot_engine.spec_core.language_understanding.memory_engine import get_memory_engine as _gme
            last = None
            try:
                last = _gme().last_bot(int(uid))
            except Exception:
                last = None
            sig = learn_from_feedback_message(int(uid), request)
            bot_name = (last or {}).get("name") or "آخر بوت"
            n_feats = 0
            try:
                feats = (last or {}).get("features") or []
                if isinstance(feats, str):
                    import json as _json
                    feats = _json.loads(feats)
                n_feats = len(feats) if isinstance(feats, list) else 0
            except Exception:
                pass
            if sig.kind == "positive" or sig.kind == "complete":
                await message.reply_text(
                    f"شكرًا ✅ (+{sig.score_delta})\n"
                    f"اتقوّت وصفة «{bot_name}» ({n_feats} ميزة) للتوليدات الجاية."
                )
            elif sig.kind == "negative":
                await message.reply_text(
                    f"تم 📝 ({sig.score_delta})\n"
                    f"ميزات «{bot_name}» هتتتجنب أو تتضعف في المرات الجاية."
                )
            return
    except Exception:
        logger.exception("stage3 feedback learn failed")

    # ── Stage-2: learn from explicit corrections ─────────────────────────
    try:
        from telegram_bot_engine.spec_core.language_understanding import (
            is_correction_utterance,
            parse_correction,
            get_memory_engine,
        )
        if uid and is_correction_utterance(request):
            corr = parse_correction(request)
            if corr:
                mem = get_memory_engine()
                mem.record_correction(
                    int(uid),
                    rejected=corr.get("rejected") or "",
                    preferred=corr.get("preferred") or "",
                    context=request[:200],
                )
                # Apply immediately to durable user slots when payment/feature known
                try:
                    from telegram_bot_engine.spec_core.language_understanding.learning_layer import (
                        _match_pay,
                        _match_feature,
                    )
                    pref = corr.get("preferred") or ""
                    rej = corr.get("rejected") or ""
                    if _match_pay(pref):
                        mem.set_durable_slot(int(uid), "preferred_payment", _match_pay(pref))
                    if _match_pay(rej):
                        mem.set_durable_slot(int(uid), "rejected_payment", _match_pay(rej))
                    if _match_feature(pref):
                        mem.set_durable_slot(int(uid), "preferred_feature", _match_feature(pref))
                except Exception:
                    pass
                pref_show = (corr.get("preferred") or "").strip()
                rej_show = (corr.get("rejected") or "").strip()
                msg = "تم تسجيل التصحيح ✅ — هيتطبّق على التوليد الجاي"
                if rej_show or pref_show:
                    msg += f"\n❌ {rej_show or '—'} → ✅ {pref_show or '—'}"
                await message.reply_text(msg)
                # If message is ONLY a correction (short), stop here
                if len(request.split()) <= 12 and not any(
                    k in request for k in ("بوت", "bot", "اعمل", "سوّي", "سوي", "generate")
                ):
                    return
    except Exception:
        logger.exception("stage2 correction learn failed")

    # ── L3 clarification resume (answers for pending questions) ──────────
    _pending_q = (context.user_data or {}).get("pending_clarify") if context.user_data else None
    _clarify_done = False
    if isinstance(_pending_q, dict) and _pending_q.get("questions"):
        try:
            answers = dict(_pending_q.get("answers") or {})
            qlist = list(_pending_q.get("questions") or [])
            idx = int(_pending_q.get("idx") or 0)
            base_req = str(_pending_q.get("base_request") or "")
            low = request.lower().strip()
            # cancel → abort clarification, do NOT generate
            if low in {"/cancel", "cancel", "إلغاء", "الغاء"}:
                context.user_data.pop("pending_clarify", None)
                await message.reply_text("تم إلغاء التوضيح. اكتب وصفاً جديداً للتوليد.")
                return
            # تخطي / skip = skip ALL remaining and generate (no loop)
            if low in {"تخطي", "skip", "/skip", "تخطي الكل", "skip all", "عدي", "continue"}:
                idx = len(qlist)
            else:
                cur = qlist[idx] if 0 <= idx < len(qlist) else None
                if cur:
                    answers[str(cur.get("slot") or cur.get("id") or f"q{idx}")] = request.strip()
                idx += 1
            if idx < len(qlist):
                context.user_data["pending_clarify"] = {
                    "base_request": base_req,
                    "questions": qlist,
                    "answers": answers,
                    "idx": idx,
                }
                nq = qlist[idx]
                await message.reply_text(
                    f"❓ ({idx+1}/{len(qlist)}) {nq.get('text') or nq.get('slot')}\n"
                    "• اكتب الإجابة · تخطي (يتخطى الباقي ويولّد) · إلغاء"
                )
                return
            # Done → enrich + mark so L3 does not re-ask this turn
            context.user_data.pop("pending_clarify", None)
            context.user_data["skip_clarify_once"] = True
            extra = " | ".join(f"{k}: {v}" for k, v in answers.items() if v)
            request = (base_req + ("\n" + extra if extra else "")).strip()
            _clarify_done = True
            await message.reply_text("👍 تمام — هولّد البوت بالمواصفات دي...")
        except Exception:
            logger.exception("pending_clarify resume failed")
            if context.user_data is not None:
                context.user_data.pop("pending_clarify", None)
                context.user_data["skip_clarify_once"] = True

    try:
        from telegram_bot_engine.services.user_memory import get_user_memory
        _mem = get_user_memory(uid, OUTPUT_DIR)
        _mem.add_turn("user", request)
    except Exception:
        _mem = None
        logger.exception("user_memory load failed")

    _ctx_res = None
    try:
        from telegram_bot_engine.services.context_engine import resolve_context
        _active = (context.user_data or {}).get("active_repo") or {}
        _ctx_res = resolve_context(
            uid,
            request,
            base_dir=OUTPUT_DIR,
            active_path=str(_active.get("path") or ""),
        )
        # If user refers to prior work with enough confidence, bind session to that path
        if (
            _ctx_res.refers_to_prior
            and _ctx_res.confidence >= 0.5
            and _ctx_res.target_path
            and Path(_ctx_res.target_path).exists()
        ):
            context.user_data["active_repo"] = {
                "path": _ctx_res.target_path,
                "url": "",
                "contract": {},
                "from_context_engine": True,
                "label": _ctx_res.target_label,
                "kind": _ctx_res.target_kind,
            }
            if _mem:
                _mem.set_last(
                    intent=request[:200],
                    project_path=_ctx_res.target_path,
                    capability="context_prior",
                )
        # Phase 5: continuity plan (modify / continue prior project)
        try:
            from telegram_bot_engine.services.continuity import plan_continuity
            _active = (context.user_data or {}).get("active_repo") or {}
            _cont = plan_continuity(
                uid,
                request,
                base_dir=OUTPUT_DIR,
                active_path=str(_active.get("path") or ""),
                ctx=_ctx_res,
            )
            if (
                _cont.active
                and _cont.target_path
                and Path(_cont.target_path).exists()
            ):
                context.user_data["active_repo"] = {
                    "path": _cont.target_path,
                    "url": (_active.get("url") or ""),
                    "contract": (_active.get("contract") or {}),
                    "from_context_engine": True,
                    "from_continuity": True,
                    "label": getattr(_ctx_res, "target_label", "") or Path(_cont.target_path).name,
                    "kind": _cont.target_kind,
                    "continuity_mode": _cont.mode,
                }
                context.user_data["continuity_plan"] = _cont.to_dict()
                if _mem:
                    _mem.set_last(
                        intent=request[:200],
                        project_path=_cont.target_path,
                        capability="continuity_" + (_cont.mode or "dev"),
                    )
        except Exception:
            logger.exception("continuity plan failed")
        # Phase 6: advanced partner brief
        try:
            from telegram_bot_engine.services.advanced_partner import (
                build_advanced_brief,
            )
            _act = (context.user_data or {}).get("active_repo") or {}
            _brief = build_advanced_brief(
                uid,
                request,
                base_dir=OUTPUT_DIR,
                active_path=str(_act.get("path") or ""),
            )
            context.user_data["advanced_brief"] = _brief.to_dict()
            context.user_data["advanced_brief_ai"] = _brief.to_ai_context()
        except Exception:
            logger.exception("advanced_partner brief failed")
    except Exception:
        logger.exception("context_engine failed")

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
            return
        await status.edit_text(result.to_user_text())
        return

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
                "run_seconds": int(__import__("os").environ.get("LIVE_RUN_SECONDS", 900)),
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
                    "run_seconds": int(__import__("os").environ.get("LIVE_RUN_SECONDS", 900)),
                }
                context.user_data["pending_run"] = pending_run
        if pending_run and pending_run.get("project_path"):
            await handle_live_run_token(message, context, token_text, pending_run)
            _persist_session(user, context)
            return
        # Token sent but no project is pending — do NOT treat as bot description
        await message.reply_text(
            "استلمت توكن بوت، لكن مفيش مشروع جاهز للتشغيل دلوقتي.\n"
            "ولّد بوت أو اسحب مستودع أولاً، وبعد رسالة «أرسل توكن البوت» ابعت التوكن."
        )
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
                return
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
                return

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
        await handle_live_deploy_token(message, context, normalize_bot_token(request), pending)
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
        from telegram_bot_engine.services.hosting import get_hosting_service
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
        from telegram_bot_engine.services.repo_dev import (
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
            "كمّل", "كمل", "السابق", "اللي فات", "اللي قبل", "نفس البوت",
            "نفس المشروع", "حسّن", "حسن", "أصلح", "اصلح", "extend", "continue",
            "update", "improve", "refactor",
        )
        _cont_flag = bool((context.user_data or {}).get("continuity_plan", {}).get("active"))
        if (
            _cap in _repo_caps
            or action != "unknown"
            or _cont_flag
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
                await status.edit_text(f"❌ فشل التنفيذ على المستودع: {type(e).__name__}: {sanitize_error(str(e))}")
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
            try:
                from telegram_bot_engine.services.user_memory import get_user_memory
                mem = get_user_memory(uid, OUTPUT_DIR)
                mem.set_last(
                    intent=request[:200],
                    project_path=str(active.get("path") or ""),
                    capability="continuity_dev",
                )
                note = f"continuity action={getattr(dev, 'action', '')} path={active.get('path')}"
                if dev.changed_files:
                    note += " changed=" + ",".join(dev.changed_files[:8])
                mem.add_turn("note", note, meta={"capability": "continuity_dev", "ok": bool(dev.ok)})
            except Exception:
                logger.exception("memory update after continuity failed")

            if dev.ok and dev.changed_files and active.get("path"):
                try:
                    from telegram_bot_engine.services.advanced_partner import (
                        maybe_snapshot_version,
                    )
                    maybe_snapshot_version(
                        uid,
                        active["path"],
                        label=str(getattr(dev, "action", "") or "edit"),
                        reason=(request or "")[:200],
                        base_dir=OUTPUT_DIR,
                    )
                except Exception:
                    logger.exception("version snapshot failed")

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
        from telegram_bot_engine.services.chat_router.service import _looks_like_bot_spec
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
            from telegram_bot_engine.services.chat_router import get_router
            await message.reply_text(honest_help())
        except Exception:
            await message.reply_text("مساعدة: اسحب مستودع | ولّد بوت | استضافة | تحليل استاتيكي")
        return

    # ------------------------------------------------------------------
    # Phase 4 — Developer partner mode (AI only, zero fixed scripts)
    # SmartChat + memory + context: clarify, challenge, route to engines.
    # ------------------------------------------------------------------
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
    _slash_cmds = re.findall(r"/[a-zA-Z][a-zA-Z0-9_]{1,32}", request)
    # AI chat path removed permanently — no LLM partner routing.
    _ai_route_generate = bool(
        _is_hard and getattr(_rt, "capability_id", "") == "generate_bot"
    )

    # Non-bot, non-hard messages: short deterministic help (no AI)
    # Exception: just finished L3 clarify → always continue to generate
    if not _is_hard and not _is_bot_spec and not _clarify_done:
        help_ar = (
            "أرسل وصفاً واضحاً للبوت الذي تريده، مثلاً:\n"
            "• بوت يرد على الرسائل\n"
            "• بوت فيه /start و /help\n"
            "أو استخدم الأوامر: /start /help /status"
        )
        await message.reply_text(help_ar)
        return

    # ------------------------------------------------------------------
    # Generate only on explicit generate route or strong bot specification.
    # Greetings / small-talk never reach generation (handled above).
    # ------------------------------------------------------------------
    _strong_bot_spec = bool(
        _is_bot_spec
        and (
            len(_slash_cmds) >= 1
            or len(request) >= 80
            or bool(re.search(r"اعمل\s*بوت|أنشئ\s*بوت|انشئ\s*بوت|generate\s*bot", request, re.I))
            or bool(re.search(r"\bبوت\b", request))
        )
    )
    # After L3 answers/skip → force generate with enriched request
    if _clarify_done:
        _strong_bot_spec = True
        _ai_route_generate = True
    if not _ai_route_generate and not _strong_bot_spec:
        return

    if len(request) < 2:
        return

    # Clear any leftover clarification session state
    if context.user_data is not None:
        context.user_data.pop("pending_spec", None)

    # Feasibility gate — refuse impossible / out-of-scope requests honestly
    _soft_note = ""
    try:
        from telegram_bot_engine.services.feasibility_gate import check_feasibility
        _feas = check_feasibility(request)
        if not _feas.can_generate:
            await message.reply_text(
                rejection_message(_feas.reason, _feas.suggested_scope),
            )
            return
        _soft_note = ""
        if _feas.blocked_features:
            _soft_note = (
                "\n⚠️ ملاحظة: بعض الأجزاء تحتاج ربط خارجي ولن تُفعَّل تلقائياً: "
                + "، ".join(_feas.blocked_features[:4])
            )
    except Exception:
        pass

    # ── L3: ask adaptive questions before thin specs (e.g. «بوت متجر») ──
    # Skip if we just finished a clarify session this turn (prevents infinite loop)
    _skip_l3 = False
    if context.user_data is not None:
        _skip_l3 = bool(context.user_data.pop("skip_clarify_once", False)) or _clarify_done
    if not _skip_l3:
        try:
            from telegram_bot_engine.spec_core.language_understanding import (
                understand,
                analyze_intent,
                build_question_plan,
            )
            _lu = understand(request)
            _intent = analyze_intent(request, lu=_lu)
            _qp = build_question_plan(
                request,
                intent=_intent,
                lu=_lu,
                user_id=int(user.id) if user else None,
                remember=True,
                max_questions=3,
            )
            if (
                _qp
                and getattr(_qp, "should_block_generation", False)
                and getattr(_qp, "questions", None)
                and context.user_data is not None
                and len(request) < 120  # rich specs skip Q&A
            ):
                q_payload = [
                    {
                        "id": getattr(q, "id", None) or getattr(q, "slot", f"q{i}"),
                        "slot": getattr(q, "slot", None) or getattr(q, "id", f"q{i}"),
                        "text": getattr(q, "text", "") or str(getattr(q, "slot", "")),
                    }
                    for i, q in enumerate(list(_qp.questions)[:3])
                ]
                # Prefer Arabic wording when user language is Arabic
                _lang = getattr(_intent, "language", "") or ""
                if _lang.startswith("ar"):
                    _ar_map = {
                        "payment": "طرق الدفع؟ (فودافون / محفظة / تيليجرام)",
                        "product_or_category": "هتبيع إيه؟ (مثال: ملابس / إلكترونيات / أكل)",
                        "audience": "مين جمهورك؟ (مبتدئين / محترفين)",
                    }
                    for item in q_payload:
                        slot = str(item.get("slot") or "")
                        if slot in _ar_map:
                            item["text"] = _ar_map[slot]
                        elif item.get("text") and item["text"][:1].isascii():
                            # keep generic Arabic fallback
                            item["text"] = item["text"]
                if q_payload:
                    context.user_data["pending_clarify"] = {
                        "base_request": request,
                        "questions": q_payload,
                        "answers": {},
                        "idx": 0,
                    }
                    await message.reply_text(
                        "🧠 هخصص البوت ليك — جاوب على كام سؤال سريع:\n\n"
                        f"❓ (1/{len(q_payload)}) {q_payload[0]['text']}\n"
                        "• اكتب الإجابة · تخطي (يتخطى الباقي ويولّد) · إلغاء"
                    )
                    return
        except Exception:
            logger.exception("L3 pre-generation questions failed")

    # Duplicate identical prompt within TTL → reuse last project path
    try:
        from .generation_cache import get_generation_cache
        _cached = get_generation_cache().get(int(user.id) if user else 0, request)
        if _cached and _cached.get("project_path"):
            from pathlib import Path as _P
            if _P(_cached["project_path"]).is_dir():
                await message.reply_text(
                    "✅ نفس الطلب مؤخراً — سأستخدم النتيجة السابقة.\n"
                    "🔑 أرسل توكن البوت من @BotFather للتشغيل، أو غيّر الوصف لإعادة التوليد."
                )
                if context.user_data is not None:
                    payload = {
                        "project_path": _cached["project_path"],
                        "entry_point": _cached.get("entry_point") or "main.py",
                        "run_seconds": int(__import__("os").environ.get("LIVE_RUN_SECONDS", 900)),
                    }
                    context.user_data["pending_run"] = payload
                    context.user_data["pending_deploy"] = dict(payload)
                    context.user_data["pending_live_run"] = dict(payload)
                    _persist_session(user, context)
                return
    except Exception:
        pass

    status_msg = await message.reply_text(
        "⏳ جاري توليد المشروع (مسار حتمي) ثم التحقق ضد الهلوسة..."
        + (_soft_note or "")
    )
    await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)

    # Isolated per-user workspace (never share host bot dir/token space)
    try:
        from telegram_bot_engine.services.user_sandbox import get_user_sandbox
        uid = int(user.id) if user else 0
        work_dir = get_user_sandbox(uid, OUTPUT_DIR).new_project_dir(label="gen")
    except Exception:
        work_dir = Path(tempfile.mkdtemp(prefix="botgen_", dir=str(OUTPUT_DIR)))

    try:
        result = await run_with_heartbeat(
            run_generation,
            request,
            work_dir,
            int(user.id) if user else 0,
            status_msg=status_msg,
        )

        if result is None:
            await status_msg.edit_text("❌ فشل التوليد (نتيجة فارغة).")
            return

        from .generation_flow import deliver_generation_result
        await deliver_generation_result(
            message=message,
            status_msg=status_msg,
            context=context,
            user=user,
            request=request,
            result=result,
        )
        try:
            if result and getattr(result, "success", False) and getattr(result, "project_path", None):
                from .generation_cache import get_generation_cache
                get_generation_cache().put(
                    int(user.id) if user else 0,
                    request,
                    {
                        "project_path": str(result.project_path),
                        "entry_point": "main.py",
                    },
                )
            _persist_session(user, context)
        except Exception:
            pass

    except Exception as e:
        logger.exception("Generation failed")
        err_text = escape_md(sanitize_error(str(e), max_len=400))
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


