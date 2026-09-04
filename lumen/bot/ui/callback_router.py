"""CallbackQuery entry — engine actions + optional real generation."""
from __future__ import annotations

import logging

from lumen.engine.services.ui_state.controller import apply_action
from lumen.engine.services.ui_state.models import EngineUiPhase
# Bound once at module level — never re-import as `render_message` inside
# handlers (that causes UnboundLocalError: "cannot access local variable
# 'render_message' where it is not associated with a value").
from lumen.engine.services.ui_state.render import render_message as render_ui_message

from .facts import gather_ui_facts
from .keyboards import build_inline_keyboard, decode_callback
from .state_store import load_ui_state, persist_ui_session, save_ui_state

logger = logging.getLogger("lumen_bot.ui")


def _help_body() -> str:
    try:
        from lumen.bot.capability_boundaries import get_help_text

        return get_help_text()
    except Exception:
        return "استخدم /help"


async def _safe_render_ui(q, msg, text: str, markup, *, user_data=None, context=None) -> None:
    """Single-surface UI: edit in place, then hard-prune chat to max 2 bot messages."""
    from .chat_hygiene import send_or_edit_ui

    bot = getattr(context, "bot", None) if context is not None else None
    chat_id = None
    preferred = None
    if q is not None and getattr(q, "message", None) is not None:
        preferred = q.message
        chat_id = getattr(q.message.chat, "id", None)
    elif msg is not None:
        preferred = msg
        chat_id = getattr(getattr(msg, "chat", None), "id", None)
    if bot is None and preferred is not None:
        bot = getattr(preferred, "get_bot", lambda: None)()
    if chat_id is None:
        # last resort legacy path — still apply HTML when UI tags present
        try:
            from lumen.bot.telegram_text import looks_like_telegram_html
            from telegram.constants import ParseMode

            pk = {}
            if looks_like_telegram_html(text or ""):
                pk["parse_mode"] = ParseMode.HTML
            if preferred is not None and getattr(preferred, "text", None):
                await preferred.edit_text(
                    text=(text or "")[:4000], reply_markup=markup, **pk
                )
                return
            if preferred is not None:
                await preferred.reply_text(
                    (text or "")[:4000], reply_markup=markup, **pk
                )
        except Exception:
            logger.exception("legacy render failed")
        return
    await send_or_edit_ui(
        bot=bot,
        chat_id=int(chat_id),
        user_data=user_data,
        text=text,
        markup=markup,
        preferred_message=preferred,
    )



async def _handle_hitl_callback(update, context, q, action_id: str) -> bool:
    """Root HITL: confirm/reject must always give visible feedback + resume off-loop."""
    if action_id not in {"hitl_confirm", "hitl_reject"}:
        return False
    import asyncio

    user = update.effective_user
    uid = int(user.id) if user else 0
    # Always use the live PTB dict so pending survives
    if context.user_data is None:
        try:
            context.user_data = {}
        except Exception:
            pass
    ud = context.user_data if isinstance(context.user_data, dict) else {}
    msg = update.effective_message or (q.message if q else None)
    verb = "تأكيد" if action_id == "hitl_confirm" else "رفض"
    progress = "⏳ جاري تأكيد الخطة ومتابعة البناء…" if action_id == "hitl_confirm" else "⏳ جاري إلغاء الخطة…"

    try:
        await q.answer("تم استلام الأمر…", show_alert=False)
    except Exception:
        pass
    if msg is not None:
        try:
            await msg.edit_text(progress, reply_markup=None)
        except Exception:
            try:
                await msg.reply_text(progress)
            except Exception:
                pass

    def _run():
        from lumen.bot.multi_agent_bridge import try_handle_hitl_message
        return try_handle_hitl_message(verb, user_id=uid, user_data=ud)

    try:
        result_tuple = await asyncio.wait_for(asyncio.to_thread(_run), timeout=300.0)
        # try_handle_hitl_message now returns (handled, reply, state)
        if len(result_tuple) == 3:
            handled, reply, hitl_state = result_tuple
        else:
            handled, reply = result_tuple
            hitl_state = None
        if not handled:
            reply = "لا يوجد إجراء معلّق. أعد الطلب من جديد."
        text = (reply or "تم.")[:4000]
        if msg is not None:
            try:
                await msg.edit_text(text, reply_markup=None)
            except Exception:
                try:
                    await msg.reply_text(text)
                except Exception:
                    logger.exception("HITL reply delivery failed")
        else:
            try:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=text)
            except Exception:
                pass

        # CRITICAL: After HITL resume, if generation succeeded, deliver the zip!
        # Without this, the user gets a "done" text but never receives the project file.
        if hitl_state is not None and verb == "تأكيد":
            try:
                _ext = getattr(hitl_state, "extensions", None) or {}
                _status = str(getattr(hitl_state, "status", "") or "").upper()
                _project_path = (
                    getattr(hitl_state, "generated_path", "") or ""
                    or _ext.get("project_path") or _ext.get("work_dir") or ""
                )
                # Check if the LangGraph pipeline completed successfully with a project
                if _status in {"DELIVERED", "PASSED", "COMPLETED", "DONE", "SUCCESS"} and _project_path:
                    from pathlib import Path as _P
                    proj = _P(str(_project_path))
                    if proj.is_dir():
                        # Build a result-like object for deliver_generation_result
                        class _GenResult:
                            success = True
                            project_path = str(proj)
                            errors = []
                            stages = []
                            metadata = {"final_message": getattr(hitl_state, "final_message", "")}
                        from lumen.bot.generation_flow import deliver_generation_result
                        await deliver_generation_result(
                            message=msg or update.effective_message,
                            status_msg=msg or update.effective_message,
                            context=context,
                            user=user,
                            request=str(ud.get("last_request") or "bot"),
                            result=_GenResult(),
                        )
                        logger.info("HITL resume → deliver_generation_result called for project %s", proj)
            except Exception as _del_exc:
                logger.exception("HITL post-resume delivery failed: %s", _del_exc)

        return True
    except asyncio.TimeoutError:
        logger.error("HITL resume timed out uid=%s", uid)
        err = "استغرق البناء وقتاً طويلاً. أعد الضغط على تأكيد أو اطلب التوليد من جديد."
        if msg is not None:
            try:
                await msg.edit_text(err)
            except Exception:
                pass
        return True
    except Exception:
        logger.exception("hitl callback failed")
        err = "فشل التأكيد. أعد الطلب أو اكتب: تأكيد"
        if msg is not None:
            try:
                await msg.edit_text(err)
            except Exception:
                pass
        try:
            await q.answer("فشل التأكيد", show_alert=True)
        except Exception:
            pass
        return True


async def handle_ui_callback(update, context) -> None:
    # Referral: tapping UI counts as bot use for invitees
    try:
        u = getattr(update, "effective_user", None)
        if u is not None:
            from lumen.bot.referral_hooks import qualify_bot_use
            await qualify_bot_use(context, int(u.id), "command_non_start")
    except Exception:
        logger.debug("referral qualify on ui callback soft-fail", exc_info=True)

    """Top-level UI callback — answer first, never hang on Redis/DB."""
    q = update.callback_query
    if q is None:
        return

    import asyncio

    user = update.effective_user
    uid = int(user.id) if user else 0

    # 0) Acknowledge IMMEDIATELY — stops Telegram loading spinner (best practice)
    try:
        await q.answer()
    except Exception:
        pass

    # 1) Identity
    try:
        from lumen.bot.helpers import is_allowed
        if not uid or not is_allowed(uid):
            return
    except Exception:
        logger.exception("auth check failed on callback")
        return

    # 2) Signed parse + closed catalog
    parsed = decode_callback(q.data or "", user_id=uid)
    if parsed is None:
        # Stale / unsigned / foreign button — silent fail-closed
        return
    action_id, arg = parsed
    try:
        from lumen.engine.services.ui_state.catalog import is_known_action
        if not is_known_action(action_id):
            logger.warning("unknown ui action rejected uid=%s action=%s", uid, action_id)
            return
    except Exception:
        logger.exception("catalog check failed")
        return

    # 3) Rate limit with hard timeout (never block UI on Redis stall)
    try:
        from lumen.bot.middlewares.auth import rate_limit_ok
        ok = await asyncio.wait_for(asyncio.to_thread(rate_limit_ok, uid), timeout=1.5)
        if not ok:
            try:
                await q.answer("انتظر قليلاً", show_alert=False)
            except Exception:
                pass
            return
    except Exception:
        logger.debug("callback rate limit skipped", exc_info=True)

    # HITL resume can run the full LangGraph build — allow long wall time.
    _timeout = 200.0 if action_id in {"hitl_confirm", "hitl_reject"} else 25.0
    try:
        await asyncio.wait_for(
            _handle_ui_callback_body(update, context, q, action_id, arg),
            timeout=_timeout,
        )
    except asyncio.TimeoutError:
        logger.error("ui callback timeout action=%s uid=%s", action_id, uid)
        try:
            msg = update.effective_message or (q.message if q else None)
            if msg is not None:
                await msg.reply_text("استغرق الرد وقتاً أطول من المعتاد. جرّب مرة أخرى.")
        except Exception:
            pass
    except Exception as exc:
        logger.exception(
            "ui callback fatal action=%s arg=%s err=%s:%s",
            action_id,
            arg,
            type(exc).__name__,
            str(exc)[:200],
        )



async def _handle_ui_callback_body(update, context, q, action_id: str, arg: str) -> None:
    # Hydrate durable session first (Redis source of truth across workers/restarts)
    try:
        uid_h = int(update.effective_user.id) if update.effective_user else 0
        if uid_h and context.user_data is not None:
            from lumen.bot.session_store import get_session_store
            get_session_store().hydrate(uid_h, context.user_data)
    except Exception:
        logger.exception("session hydrate failed on callback")

    # Busy guard during live generation
    try:
        from lumen.bot.progress_tracker import is_generation_busy
        uid_busy = int(update.effective_user.id) if update.effective_user else 0
        # Cooperative cancel from inline button
        if action_id == "cancel_generate" and uid_busy:
            try:
                from lumen.engine.services.generation_cancel import request_cancel
                request_cancel(uid_busy)
            except Exception:
                logger.exception("callback request_cancel failed")
            try:
                from lumen.bot.progress_tracker import clear_generation_busy
                clear_generation_busy(uid_busy)
            except Exception:
                pass

        if uid_busy and is_generation_busy(uid_busy) and action_id not in {
            "cancel_generate", "home", "nav_back", "hitl_reject",
        }:
            try:
                if q is not None:
                    await q.answer("التوليد شغال — استنى التحديثات أو ألغِ", show_alert=False)
            except Exception:
                pass
            return
    except Exception:
        logger.exception("callback busy guard failed")

    # One-shot welcome photo: delete permanently on first button press
    try:
        ud0 = context.user_data if context.user_data is not None else {}
        wmid = ud0.get("lumen_welcome_msg_id")
        if wmid and update.effective_chat:
            try:
                await context.bot.delete_message(
                    chat_id=int(update.effective_chat.id),
                    message_id=int(wmid),
                )
            except Exception:
                pass
            ud0.pop("lumen_welcome_msg_id", None)
            ud0["lumen_welcome_shown"] = True
            # Drop from hygiene tracker so it is never edited again
            try:
                ids = list(ud0.get("lumen_bot_ui_msg_ids") or [])
                ud0["lumen_bot_ui_msg_ids"] = [i for i in ids if int(i) != int(wmid)]
            except Exception:
                pass
    except Exception:
        pass

    user_data = context.user_data if context.user_data is not None else {}
    # Ensure PTB keeps the same dict when user_data was None
    if action_id in {"hitl_confirm", "hitl_reject"}:
        await _handle_hitl_callback(update, context, q, action_id)
        return

    if context.user_data is None:
        try:
            context.user_data = user_data
        except Exception:
            pass

    state = load_ui_state(user_data)
    uid = int(update.effective_user.id) if update.effective_user else 0
    msg = update.effective_message or (q.message if q else None)

    # ── Direct engine-bound actions (not phase transitions) ──────────
    if action_id == "repo_sec":
        from .repo_sections import get_section, section_keyboard
        body = get_section(user_data, (arg or "header").strip())
        markup = section_keyboard(
            user_id=uid,
            show_run=bool((user_data or {}).get("pending_run")),
        )
        await _safe_render_ui(q, msg, body, markup, user_data=user_data, context=context)
        return

    if action_id == "ask_gh_token":
        kind = (arg or "clone").strip().lower()
        if kind == "create":
            # Ensure pending_create_repo exists if name was stored earlier
            if not user_data.get("pending_create_repo"):
                user_data["pending_create_repo"] = {"name": "new-repo", "private": True}
            prompt = (
                "🔒 أرسل الآن توكن GitHub (PAT) بصلاحية `repo`.\n"
                "• Classic: `ghp_...`\n• Fine-grained: `github_pat_...`\n\n"
                "بعد الإرسال سيُحذف سرك من المحادثة تلقائياً."
            )
        else:
            # clone / default — keep or restore URL from active context
            if not user_data.get("pending_clone_auth"):
                active = user_data.get("active_repo") or {}
                url = str(active.get("url") or user_data.get("last_clone_url") or "")
                user_data["pending_clone_auth"] = {"url": url}
            prompt = (
                "🔒 أرسل الآن توكن GitHub (PAT) بصلاحية `repo` لسحب المستودع الخاص.\n\n"
                "بعد الإرسال سيُحذف سرك من المحادثة تلقائياً."
            )
        try:
            from .secret_prompt import build_secret_prompt_markup
            markup = build_secret_prompt_markup(kind="github", user_id=uid)
        except Exception:
            markup = None
        await _safe_render_ui(q, msg, prompt, markup, user_data=user_data, context=context)
        return

    if action_id == "ask_bot_token":
        kind = (arg or "host").strip().lower()
        active = user_data.get("active_repo") or {}
        path = str(
            (user_data.get("pending_host") or {}).get("project_path")
            or active.get("path")
            or (user_data.get("pending_run") or {}).get("project_path")
            or ""
        )
        if kind in {"host", "restart"} and path:
            user_data["pending_host"] = {
                "project_path": path,
                "user_id": uid,
            }
            user_data.pop("pending_run", None)
            prompt = (
                "🚀 أرسل توكن البوت من @BotFather لبدء/إعادة الاستضافة الدائمة.\n"
                "بعد الإرسال سيُحذف سرك من المحادثة ويُشفَّر في المحرك."
            )
        else:
            if path and not user_data.get("pending_run"):
                user_data["pending_run"] = {
                    "project_path": path,
                    "entry_point": "",
                    "run_seconds": 900,
                }
            prompt = (
                "🚀 أرسل توكن البوت من @BotFather للتشغيل.\n"
                "بعد الإرسال سيُحذف سرك من المحادثة تلقائياً."
            )
        try:
            from .secret_prompt import build_secret_prompt_markup
            markup = build_secret_prompt_markup(kind="bot", user_id=uid)
        except Exception:
            markup = None
        await _safe_render_ui(q, msg, prompt, markup, user_data=user_data, context=context)
        return

    if action_id == "host_restart":
        # 1) Stop live instance via HostService  2) re-request token  3) start on next message
        # Raw tokens are never persisted — security by design.
        try:
            from .dash_actions import sync_dashboard_slots, resolve_instance_id, format_host_result
            from lumen.bot.config import OUTPUT_DIR
            from lumen.engine.services.hosting import get_hosting_service
            import asyncio

            slots = sync_dashboard_slots(uid, dict(state.slots or {}))
            iid = resolve_instance_id(arg or "0", slots)
            path = ""
            if iid:
                for i in range(5):
                    if (slots.get(f"dash_h{i}") or "") == iid:
                        path = slots.get(f"dash_p{i}") or ""
                        break
            if not path:
                active = user_data.get("active_repo") or {}
                path = str(active.get("path") or state.project_ref or "")

            # One-shot restart via sealed secrets when possible
            stop_note = ""
            if iid:
                def _restart():
                    return get_hosting_service(OUTPUT_DIR).restart(
                        instance_id=str(iid), user_id=int(uid), bot_token=""
                    )
                try:
                    rr = await asyncio.to_thread(_restart)
                    if getattr(rr, "ok", False):
                        prompt = format_host_result(rr)
                        await _safe_render_ui(
                            q, msg, prompt, None, user_data=user_data, context=context
                        )
                        return
                    stop_note = format_host_result(rr)
                except Exception as exc:
                    logger.exception("host_restart sealed path failed")
                    stop_note = f"restart_error: {type(exc).__name__}"

            if path:
                user_data["pending_host"] = {
                    "project_path": path,
                    "user_id": uid,
                    "restart_of": str(iid or ""),
                }
                prompt = (
                    "🔄 لإعادة التشغيل أرسل توكن البوت من @BotFather.\n"
                    "(لم تُوجد أسرار مشفّرة كافية على المشروع).\n"
                    "سيُحذف التوكن من المحادثة فوراً بعد الاستلام."
                )
                if stop_note:
                    prompt = stop_note[:1200] + "\n\n" + prompt
            else:
                prompt = (
                    (stop_note + "\n\n") if stop_note else ""
                ) + "لا يوجد مسار مشروع مرتبط بهذا المثيل. اسحب/ولّد مشروعاً أولاً."
        except Exception:
            logger.exception("host_restart prep failed")
            prompt = "تعذّر تحضير إعادة التشغيل. حاول من لوحة التحكم."
        try:
            from .secret_prompt import build_secret_prompt_markup
            markup = build_secret_prompt_markup(kind="bot", user_id=uid) if "توكن" in prompt else None
        except Exception:
            markup = None
        await _safe_render_ui(q, msg, prompt, markup, user_data=user_data, context=context)
        return

    result = apply_action(state, action_id, arg, user_id=uid or None)

    # Batch 4: bind live host instances into state slots for dynamic buttons
    if result.state.phase.value == "dashboard":
        try:
            from .dash_actions import sync_dashboard_slots
            from lumen.engine.services.ui_state.controller import ApplyResult, buttons_for_state

            result.state.slots = sync_dashboard_slots(uid, result.state.slots)
            result = ApplyResult(
                state=result.state,
                ok=result.ok,
                message_ar=result.message_ar,
                buttons=buttons_for_state(result.state),
                run_generation=result.run_generation,
                generation_request=result.generation_request,
                post_side_effect=result.post_side_effect,
                dash_effect=result.dash_effect,
                dash_target=result.dash_target,
            )
        except Exception:
            logger.exception("dashboard slot sync failed")

    save_ui_state(user_data, result.state)

    if result.state.phase == EngineUiPhase.GEN_TYPE and result.state.slots.get("awaiting_text") == "1":
        user_data["engine_ui_await_generate"] = True
    elif result.state.phase in {EngineUiPhase.HOME, EngineUiPhase.GEN_CONFIRM, EngineUiPhase.GENERATING}:
        if result.state.phase != EngineUiPhase.GEN_TYPE:
            user_data.pop("engine_ui_await_generate", None)

    # Persist off the event loop (SQLite can block under load)
    if uid:
        try:
            import asyncio
            asyncio.get_running_loop().create_task(
                asyncio.to_thread(persist_ui_session, uid, dict(user_data))
            )
        except Exception:
            try:
                persist_ui_session(uid, dict(user_data))
            except Exception:
                pass

    # Facts I/O (Neon/Mongo) off event loop — include hosts only for dashboard.
    # Root lag: waiting up to 8s on every click for wallet/plan. Keep a short
    # budget for menu actions; only dashboard needs hosts + cache bust.
    include_hosts = result.state.phase == EngineUiPhase.DASHBOARD
    light_actions = {"open_help", "home", "open_generate", "nav_back", "open_billing", "open_settings", "open_referral"}
    if action_id == "open_dashboard":
        try:
            from .facts import invalidate_facts_cache
            invalidate_facts_cache(uid)
        except Exception:
            pass
    facts_timeout = 2.0 if action_id in light_actions else (6.0 if include_hosts else 3.0)
    try:
        import asyncio
        from functools import partial
        facts = await asyncio.wait_for(
            asyncio.to_thread(
                partial(gather_ui_facts, uid, user_data, include_hosts=include_hosts)
            ),
            timeout=facts_timeout,
        )
    except Exception:
        try:
            facts = gather_ui_facts(uid, user_data, include_hosts=False)
        except TypeError:
            facts = gather_ui_facts(uid, user_data)
        except Exception:
            from lumen.engine.services.ui_state.render import UiFacts
            facts = UiFacts(user_id=int(uid or 0))
    if result.state.phase == EngineUiPhase.HELP:
        facts.generate_hint = _help_body()

    # Referral screen: link never depends on Mongo — stats are best-effort
    if result.state.phase == EngineUiPhase.REFERRAL and uid:
        try:
            from lumen.platform.referrals.config import (
                bot_username_link,
                referral_deep_link_payload,
            )
            me = await context.bot.get_me()
            uname = (me.username or "").strip()
            if uname:
                link = bot_username_link(uname, int(uid))
            else:
                link = referral_deep_link_payload(int(uid))
            result.state.slots["referral_link"] = str(link)
        except Exception:
            logger.debug("referral link build soft-fail", exc_info=True)
        try:
            from lumen.platform.referrals import (
                REFERRAL_QUALIFIED_TARGET,
                get_referral_repository,
            )
            import asyncio as _aio

            def _st():
                r = get_referral_repository()
                s = r.stats_for(int(uid))
                s.qualified_count = int(r.count_qualified(int(uid)))
                try:
                    s.total_invited = max(
                        int(s.total_invited), int(r.count_for_referrer(int(uid)))
                    )
                except Exception:
                    pass
                return s

            st = await _aio.to_thread(_st)
            result.state.slots["referral_stats_line"] = (
                f"نشط {st.qualified_count}/{REFERRAL_QUALIFIED_TARGET} | "
                f"مدعوون {st.total_invited} | بانتظار {st.pending_count}"
            )
        except Exception:
            result.state.slots.setdefault(
                "referral_stats_line",
                "الإحصائيات غير متاحة حالياً — الرابط يعمل",
            )
            logger.debug("referral stats soft-fail", exc_info=True)


    text = render_ui_message(result.state, facts)
    if not result.ok:
        text = "⚠️ " + result.message_ar + "\n\n" + text

    try:
        markup = build_inline_keyboard(result.buttons, user_id=uid)
    except Exception:
        logger.exception("build_inline_keyboard failed action=%s", action_id)
        markup = None

    msg = update.effective_message

    # Dashboard: prefer official Rich Messages native table (Bot API 10.1+)
    if result.state.phase == EngineUiPhase.DASHBOARD:
        try:
            from lumen.bot.rich_messages import (
                build_dashboard_rich_html,
                collect_dashboard_rows,
                send_or_edit_rich_ui,
            )

            host_rows, is_empty = collect_dashboard_rows(result.state, facts)
            rich_html = build_dashboard_rich_html(
                host_rows=host_rows,
                active_project=str(getattr(facts, "active_project", "") or ""),
                empty=is_empty,
            )
            bot = getattr(context, "bot", None)
            chat_id = None
            preferred = None
            if q is not None and getattr(q, "message", None) is not None:
                preferred = q.message
                chat_id = getattr(q.message.chat, "id", None)
            elif msg is not None:
                preferred = msg
                chat_id = getattr(getattr(msg, "chat", None), "id", None)
            if bot is not None and chat_id is not None:
                rich_msg = await send_or_edit_rich_ui(
                    bot=bot,
                    chat_id=int(chat_id),
                    html=rich_html,
                    markup=markup,
                    preferred_message=preferred,
                    user_data=user_data,
                )
                if rich_msg is not None:
                    return
        except Exception:
            logger.exception("rich dashboard failed — HTML fallback action=%s", action_id)

    # buy_pro_plan: send Telegram Stars (XTR) invoice — MUST be before the
    # PRO_PLAN Rich Messages block, otherwise the rich table intercepts the
    # callback (phase == PRO_PLAN) and returns before the invoice is sent.
    if result.ok and action_id == "buy_pro_plan":
        try:
            from lumen.engine.services.ui_state.pro_plan import (
                PRO_PLAN_TITLE,
                PRO_PLAN_PRICE_STARS,
                PRO_PLAN_INVOICE_PAYLOAD,
                pro_plan_invoice_description,
            )
            from telegram import LabeledPrice

            bot = getattr(context, "bot", None)
            chat_id = None
            if q is not None and getattr(q, "message", None) is not None:
                chat_id = getattr(q.message.chat, "id", None)
            elif msg is not None:
                chat_id = getattr(getattr(msg, "chat", None), "id", None)
            if bot is not None and chat_id is not None:
                await bot.send_invoice(
                    chat_id=int(chat_id),
                    title=PRO_PLAN_TITLE,
                    description=pro_plan_invoice_description(),
                    payload=PRO_PLAN_INVOICE_PAYLOAD,
                    currency="XTR",
                    prices=[LabeledPrice(label=PRO_PLAN_TITLE, amount=PRO_PLAN_PRICE_STARS)],
                    # provider_token must be empty for Telegram Stars (XTR)
                    provider_token="",
                )
                logger.info("Stars invoice sent uid=%s chat=%s amount=%s", uid, chat_id, PRO_PLAN_PRICE_STARS)
                return
            else:
                logger.warning("buy_pro_plan: bot or chat_id missing uid=%s", uid)
        except Exception:
            logger.exception("send_invoice (Stars) failed action=buy_pro_plan")

    # Lumen Pro plan details: official Rich Messages native table (Bot API 10.1+)
    # Only shown for view_pro_plan (not buy_pro_plan, which is handled above).
    if result.state.phase == EngineUiPhase.PRO_PLAN:
        try:
            from lumen.bot.rich_messages import (
                build_table_html,
                send_or_edit_rich_ui,
            )
            from lumen.engine.services.ui_state.pro_plan import (
                PRO_PLAN_TITLE,
                PRO_PLAN_PRICE_USD,
                PRO_PLAN_PRICE_STARS,
                PRO_PLAN_DURATION_LABEL,
                PRO_PLAN_TABLE_HEADERS,
                PRO_PLAN_TABLE_CAPTION,
                pro_plan_table_rows,
                pro_plan_includes_text,
            )

            rows = pro_plan_table_rows()
            table_html = build_table_html(
                PRO_PLAN_TABLE_HEADERS,
                rows,
                caption=PRO_PLAN_TABLE_CAPTION,
                bordered=True,
                striped=True,
                compact=True,
            )
            includes = pro_plan_includes_text()
            rich_html = (
                f"<h3>{PRO_PLAN_TITLE}</h3>"
                + table_html
                + f"<p><b>السعر:</b> ${PRO_PLAN_PRICE_USD} شهريًا — {PRO_PLAN_PRICE_STARS} ⭐</p>"
                + f"<p><b>المدة:</b> {PRO_PLAN_DURATION_LABEL}</p>"
                + f"<p><b>✅ الاشتراك يشمل:</b><br>{includes.replace(chr(10), '<br>')}</p>"
                + f"<p><b>💳 نظام الرصيد:</b> كريديتات تُخصم حسب الاستخدام.</p>"
                + f"<p>اضغط «اشترك — {PRO_PLAN_PRICE_STARS} ⭐» للدفع بنجوم تيليجرام.</p>"
            )
            bot = getattr(context, "bot", None)
            chat_id = None
            preferred = None
            if q is not None and getattr(q, "message", None) is not None:
                preferred = q.message
                chat_id = getattr(q.message.chat, "id", None)
            elif msg is not None:
                preferred = msg
                chat_id = getattr(getattr(msg, "chat", None), "id", None)
            if bot is not None and chat_id is not None:
                rich_msg = await send_or_edit_rich_ui(
                    bot=bot,
                    chat_id=int(chat_id),
                    html=rich_html,
                    markup=markup,
                    preferred_message=preferred,
                    user_data=user_data,
                )
                if rich_msg is not None:
                    return
        except Exception:
            logger.exception("rich pro_plan failed — HTML fallback action=%s", action_id)

    await _safe_render_ui(q, msg, text, markup, user_data=user_data, context=context)


    # ForceReply placeholder when the engine expects free text.
    # EngineUiPhase is module-level only — never re-import here (UnboundLocalError).
    try:
        from lumen.bot.ui.input_prompt import ask_after_ui
        if result.state.phase == EngineUiPhase.GEN_TYPE or result.state.slots.get("awaiting_text") == "1":
            await ask_after_ui(context=context, msg=msg, kind="bot_description")
        elif result.state.phase == EngineUiPhase.GEN_SLOTS:
            rem = None
            try:
                from lumen.engine.services.ui_state.engine_needs import remaining_needs
                rem = remaining_needs(result.state.needs or [], result.state.slots)
            except Exception:
                rem = None
            if rem and not (rem[0].choices or []):
                await ask_after_ui(
                    context=context,
                    msg=msg,
                    kind="slot_answer",
                    body=f"✍️ {rem[0].text}",
                    placeholder=(rem[0].text or "")[:60] or "اكتب إجابتك…",
                )
    except Exception:
        logger.exception("input placeholder prompt failed")

    # Real generation — same engine as chat path
    if result.ok and result.run_generation and result.generation_request:
        status = None
        try:
            if msg:
                status = await msg.reply_text("جاري توليد البوت عبر المحرك…")
            from .generate_bridge import run_guided_generation

            gen_result = await run_guided_generation(
                message=msg,
                context=context,
                user=update.effective_user,
                gen_request=result.generation_request,
                status_msg=status or msg,
            )
            st2 = load_ui_state(user_data)
            if gen_result is not None and getattr(gen_result, "success", False):
                st2.phase = EngineUiPhase.GEN_DONE
                st2.project_ref = str(getattr(gen_result, "project_path", "") or "")[:500]
            else:
                from lumen.engine.services.ui_state.ui_events import UiEventKind, apply_event

                err = ""
                try:
                    errs = list(getattr(gen_result, "errors", None) or [])
                    err = str(errs[0])[:300] if errs else "generation_failed"
                except Exception:
                    err = "generation_failed"
                st2 = apply_event(st2, UiEventKind.GENERATION_FAILED, detail=err)
            save_ui_state(user_data, st2)
            if uid:
                persist_ui_session(uid, dict(user_data))
            if st2.phase in {EngineUiPhase.CONTEXT, EngineUiPhase.GEN_DONE} and msg:
                from lumen.engine.services.ui_state.controller import buttons_for_state
                if st2.phase == EngineUiPhase.GEN_DONE:
                    body = (
                        "ما التالي؟\n"
                        "• تجربة في الشات — تشغيل مؤقت\n"
                        "• استضافة دائمة — Firecracker\n"
                        "• ZIP أو معاينة"
                    )
                else:
                    body = render_ui_message(st2)[:2000]
                await _safe_render_ui(
                    q, msg, body,
                    build_inline_keyboard(buttons_for_state(st2), user_id=uid),
                    user_data=user_data, context=context,
                )
        except Exception:
            logger.exception("guided generation bridge failed")
            if msg is not None:
                try:
                    await msg.reply_text(
                        "❌ فشل التوليد من الواجهة. أعد المحاولة أو اكتب وصف البوت كنص."
                    )
                except Exception:
                    pass

    if result.ok and getattr(result, "post_side_effect", ""):
        try:
            from .post_actions import execute_post_side_effect
            from .project_resolve import resolve_project_path

            pref = result.state.project_ref
            if not pref:
                rp = resolve_project_path("", user_data)
                pref = str(rp) if rp else ""
                if pref:
                    result.state.project_ref = pref
                    save_ui_state(user_data, result.state)
            note = await execute_post_side_effect(
                effect=result.post_side_effect,
                project_ref=pref,
                message=msg,
                context=context,
                user=update.effective_user,
            )
            if note and msg:
                # Merge into the same UI surface — never flood chat
                merged = (text + "\n\n" + note)[:4000] if text else note[:4000]
                await _safe_render_ui(
                    q, msg, merged, markup, user_data=user_data, context=context
                )
        except Exception:
            logger.exception("post_side_effect failed effect=%s", result.post_side_effect)

    if result.ok and action_id == "open_dashboard" and msg:
        # Status already reflected in dashboard render + hosts facts — no extra spam message
        pass

    if result.ok and getattr(result, "dash_effect", ""):
        try:
            from .dash_actions import execute_dash_effect
            from lumen.engine.services.ui_state.controller import buttons_for_state

            note = await execute_dash_effect(
                effect=result.dash_effect,
                target=result.dash_target,
                user_id=uid,
                user_data=user_data,
                message=msg,
            )
            if result.dash_effect == "dash_stop":
                from .dash_actions import sync_dashboard_slots
                st = load_ui_state(user_data)
                st.slots = sync_dashboard_slots(uid, st.slots)
                save_ui_state(user_data, st)
                body = render_ui_message(
                    st, gather_ui_facts(uid, user_data, include_hosts=True)
                )
                await _safe_render_ui(
                    q, msg, body,
                    build_inline_keyboard(buttons_for_state(st), user_id=uid),
                    user_data=user_data, context=context,
                )
            elif note and msg:
                merged = ((text or "") + "\n\n" + note)[:4000]
                await _safe_render_ui(
                    q, msg, merged, markup, user_data=user_data, context=context
                )
        except Exception:
            logger.exception("dash_effect failed effect=%s", result.dash_effect)
