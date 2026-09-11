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


# Navigation / read-only screens — Telegram may cache answer client-side.
# Write / pay / host / HITL actions always use cache_time=0.
_UI_CACHEABLE_ACTIONS = frozenset({
    "home",
    "open_help",
    "open_generate",
    "open_dashboard",
    "open_billing",
    "open_settings",
    "open_referral",
    "open_connections",
    "nav_back",
    "view_pro_plan",
    "post_trial",
    "post_preview",
    "post_zip",
    "dash_status",
    "dash_logs",
})


async def handle_ui_callback(update, context) -> None:
    """Top-level UI callback — security first, spinner off fast, no LLM budget.

    Order (hot path):
      1. Local allowlist
      2. HMAC-signed callback + closed catalog (fail closed, no DB)
      3. answerCallbackQuery (+ cache_time for safe nav) — official Telegram API
      4. UI rate window only (no LLM budget Redis read)
      5. Body (hydrate + engine + render)
    """
    q = update.callback_query
    if q is None:
        return

    import asyncio

    user = update.effective_user
    uid = int(user.id) if user else 0

    # 1) Identity — pure local, no I/O
    try:
        from lumen.bot.helpers import is_allowed
        if not uid or not is_allowed(uid):
            try:
                await q.answer()
            except Exception:
                pass
            return
    except Exception:
        logger.exception("auth check failed on callback")
        try:
            await q.answer()
        except Exception:
            pass
        return

    # 2) Signed parse + closed catalog — HMAC local; rejects forgery without DB
    parsed = decode_callback(q.data or "", user_id=uid)
    if parsed is None:
        try:
            await q.answer()
        except Exception:
            pass
        return
    action_id, arg = parsed
    try:
        from lumen.engine.services.ui_state.catalog import is_known_action
        if not is_known_action(action_id):
            logger.warning("unknown ui action rejected uid=%s action=%s", uid, action_id)
            try:
                await q.answer()
            except Exception:
                pass
            return
    except Exception:
        logger.exception("catalog check failed")
        try:
            await q.answer()
        except Exception:
            pass
        return

    # 3) UI rate limit BEFORE answer — one Redis ZSET only (no LLM budget).
    # Must run before answer so a reject toast can still reach the client
    # (Telegram accepts a single answerCallbackQuery per query id).
    rate_blocked = False
    try:
        from lumen.bot.middlewares.auth import rate_limit_ui_ok
        ok = await asyncio.wait_for(asyncio.to_thread(rate_limit_ui_ok, uid), timeout=0.8)
        if not ok:
            rate_blocked = True
    except Exception:
        logger.debug("callback rate limit skipped", exc_info=True)

    # 4) Acknowledge (stops spinner). cache_time is official Bot API.
    # Rejected clicks get a short toast; safe nav may be cached client-side.
    try:
        if rate_blocked:
            await q.answer("انتظر قليلاً", show_alert=False, cache_time=0)
            return
        cache_time = 20 if action_id in _UI_CACHEABLE_ACTIONS else 0
        await q.answer(cache_time=cache_time)
    except Exception:
        if rate_blocked:
            return

    # 5) Referral qualify off the critical path (must not delay render)
    try:
        u = getattr(update, "effective_user", None)
        if u is not None:
            from lumen.bot.referral_hooks import qualify_bot_use

            async def _qualify() -> None:
                try:
                    await qualify_bot_use(context, int(u.id), "command_non_start")
                except Exception:
                    logger.debug("referral qualify on ui callback soft-fail", exc_info=True)

            asyncio.create_task(_qualify())
    except Exception:
        logger.debug("referral qualify schedule soft-fail", exc_info=True)

    # HITL resume can run the full LangGraph build — allow long wall time.
    if action_id in {"hitl_confirm", "hitl_reject"}:
        _timeout = 200.0
    elif action_id == "conn_gh_select":
        _timeout = 180.0  # clone + structural + agent explain_repo_with_llm
    else:
        _timeout = 25.0
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
            from lumen.bot.session_store import ensure_account_links
            ensure_account_links(uid_h, context.user_data)
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
        from .repo_sections import get_section, get_section_rich, section_keyboard

        sec_key = (arg or "header").strip()
        markup = section_keyboard(
            user_id=uid,
            show_run=bool((user_data or {}).get("pending_run")),
        )
        # Prefer official Rich Messages (Bot API 10.1+: tables, details, headings)
        rich_html = get_section_rich(user_data, sec_key)
        if rich_html:
            try:
                from lumen.bot.rich_messages import send_or_edit_rich_ui

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
                    ok = await send_or_edit_rich_ui(
                        bot=bot,
                        chat_id=int(chat_id),
                        html=rich_html,
                        markup=markup,
                        preferred_message=preferred,
                        user_data=user_data,
                    )
                    if ok is not None:
                        return
            except Exception:
                logger.exception("repo_sec rich render failed key=%s — plain fallback", sec_key)
        body = get_section(user_data, sec_key)
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
    light_actions = _UI_CACHEABLE_ACTIONS
    if action_id == "open_dashboard":
        try:
            from .facts import invalidate_facts_cache
            invalidate_facts_cache(uid)
        except Exception:
            pass
    # Tight budget for nav — cache in facts.py usually hits within TTL.
    facts_timeout = 1.5 if action_id in light_actions else (6.0 if include_hosts else 3.0)
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

    # GitHub connection (official API) — status + repo list into slots/buttons
    if result.state.phase == EngineUiPhase.CONN_GITHUB and uid:
        try:
            import asyncio as _aio
            from lumen.engine.services.integrations.connections import get_provider
            from lumen.engine.services.ui_state.controller import buttons_for_state

            prov = get_provider("github")
            page = 1
            try:
                page = max(1, int((result.state.slots or {}).get("gh_page") or "1"))
            except ValueError:
                page = 1

            def _gh_load():
                from lumen.engine.services.integrations.connections import get_provider
                from lumen.engine.services.integrations.connections import token_store as _ts
                prov = get_provider("github")
                st = prov.status(int(uid)) if prov else None
                # Cache-first so back-navigation does not feel like a full restart
                use_cache = not _ts.repo_cache_is_stale(int(uid), max_age_sec=300.0)
                resources = []
                if prov and st and st.connected:
                    resources = prov.list_resources(
                        int(uid), page=page, per_page=8, prefer_cache=use_cache
                    )
                    # Auto-refresh when stale or empty
                    if not resources or not use_cache:
                        resources = prov.list_resources(
                            int(uid), page=page, per_page=8, prefer_cache=False
                        )
                return st, resources

            st, resources = await _aio.to_thread(_gh_load)
            # Clear previous repo slots
            for i in range(12):
                result.state.slots.pop(f"gh_r{i}_id", None)
                result.state.slots.pop(f"gh_r{i}_title", None)
            if st and st.connected:
                result.state.slots["gh_connected"] = "1"
                result.state.slots["gh_login"] = st.display_name or ""
                try:
                    from lumen.engine.services.integrations.github.activity_log import list_recent
                    recent = list_recent(int(uid), limit=1)
                    if recent:
                        import time as _time
                        ts = float(recent[0].get("ts") or 0)
                        age = int(_time.time() - ts) if ts else 0
                        if age < 60:
                            result.state.slots["gh_last_sync"] = "الآن"
                        elif age < 3600:
                            result.state.slots["gh_last_sync"] = f"منذ {age // 60} د"
                        else:
                            result.state.slots["gh_last_sync"] = f"منذ {max(1, age // 3600)} س"
                    kind_p = ""
                    try:
                        from lumen.bot.ui.github_connection_store import read_github_profile
                        kind_p = str((read_github_profile(int(uid)) or {}).get("auth_kind") or "")
                    except Exception:
                        pass
                    if kind_p == "github_app":
                        result.state.slots["gh_perms_line"] = (
                            "Contents: قراءة · إنشاء Branch/PR عند الحاجة (عبر GitHub App)"
                        )
                    else:
                        result.state.slots["gh_perms_line"] = "حسب صلاحيات الـ PAT المحفوظ"
                except Exception:
                    pass

                kind = ""
                try:
                    from lumen.bot.ui.github_connection_store import read_github_profile

                    prof = read_github_profile(int(uid)) or {}
                    kind = str(prof.get("auth_kind") or "")
                    if kind == "github_app":
                        sel = str(prof.get("repo_selection") or "")
                        extra = " · GitHub App"
                        if sel:
                            extra += f" ({sel})"
                        result.state.slots["gh_status_line"] = (
                            (f"متصل كـ @{st.display_name}" if st.display_name else "متصل")
                            + extra
                        )
                    else:
                        result.state.slots["gh_status_line"] = (
                            f"متصل كـ @{st.display_name} · PAT"
                            if st.display_name
                            else "متصل · PAT"
                        )
                except Exception:
                    result.state.slots["gh_status_line"] = (
                        f"متصل كـ @{st.display_name}" if st.display_name else "متصل"
                    )
                for i, res in enumerate(resources[:12]):
                    result.state.slots[f"gh_r{i}_id"] = res.resource_id
                    result.state.slots[f"gh_r{i}_title"] = res.title
                    result.state.slots[f"gh_r{i}_full"] = str(
                        (res.meta or {}).get("full_name") or res.title
                    )[:120]
                    result.state.slots[f"gh_r{i}_url"] = str(res.url or "")[:200]
                result.state.slots["gh_has_more"] = "1" if len(resources) >= 8 else "0"
                result.state.slots["gh_page"] = str(page)
            else:
                result.state.slots["gh_connected"] = "0"
                result.state.slots["gh_login"] = ""
                result.state.slots["gh_status_line"] = (
                    "غير متصل — اربط حساب GitHub لعرض المستودعات من API الرسمي."
                )
                result.state.slots["gh_has_more"] = "0"
            from dataclasses import replace as _dc_replace
            result = _dc_replace(result, buttons=buttons_for_state(result.state))
        except Exception:
            logger.exception("github connection UI load failed uid=%s", uid)
            result.state.slots.setdefault(
                "gh_status_line",
                "تعذر تحميل GitHub حالياً.",
            )


    # Phase 2: select repo → official clone → platform active_repo (same plane as git_router)
    if result.ok and action_id == "conn_gh_select" and uid:
        rid = (result.state.slots.get("gh_selected_id") or "").strip()
        if rid:
            status_msg = None
            try:
                from lumen.engine.services.integrations.connections.token_store import (
                    resolve_cached_repo,
                )
                from lumen.engine.services.integrations.connections.bind_repo import (
                    apply_bind_to_user_data,
                    bind_github_repo,
                )
                import asyncio as _aio

                item = resolve_cached_repo(int(uid), rid)
                if item:
                    result.state.slots["gh_selected_full"] = str(item.get("full_name") or "")[:120]
                    result.state.slots["gh_selected_url"] = str(item.get("html_url") or "")[:200]
                    result.state.slots["gh_selected_branch"] = str(
                        item.get("default_branch") or "main"
                    )[:40]

                label = result.state.slots.get("gh_selected_full") or rid
                result.state.slots["gh_status_line"] = f"جاري سحب {label}…"
                try:
                    _em = update.effective_message
                    if _em is not None:
                        status_msg = await _em.reply_text(
                            f"⏳ جاري سحب وفهم المستودع `{label}` عبر اتصال GitHub…"
                        )
                except Exception:
                    status_msg = None

                bind = await _aio.to_thread(
                    bind_github_repo,
                    int(uid),
                    rid,
                    slots=dict(result.state.slots),
                    run_understand=True,
                )
                if bind.ok and context.user_data is not None:
                    apply_bind_to_user_data(
                        context.user_data,
                        bind,
                        user=update.effective_user,
                    )
                    # Phase 3: readiness gate — missing env before trial/host
                    try:
                        from lumen.engine.services.integrations.connections.readiness import (
                            evaluate_readiness,
                        )
                        rr = evaluate_readiness(
                            active_repo=context.user_data.get("active_repo") or {}
                        )
                        # FORBIDDEN: auto sequential env collection (hallucination source).
                        # Store advisory list only; host waits for bot token.
                        if rr.missing_env:
                            context.user_data["advisory_missing_env"] = list(rr.missing_env)[:20]
                        context.user_data.pop("pending_repo_env", None)
                        if bind.is_runnable and bind.path:
                            context.user_data["pending_host"] = {
                                "project_path": bind.path,
                                "entry_point": str(getattr(bind, "entry_point", "") or ""),
                                "plane": "permanent_host",
                            }
                            context.user_data["last_project_path"] = bind.path
                            ar = dict(context.user_data.get("active_repo") or {})
                            ar["path"] = bind.path
                            context.user_data["active_repo"] = ar
                            result.state.slots["gh_missing_env"] = ",".join(rr.missing_env[:12])
                            result.state.slots["gh_ready"] = "0"
                        else:
                            context.user_data.pop("pending_repo_env", None)
                            result.state.slots["gh_ready"] = "1"
                            result.state.slots.pop("gh_missing_env", None)
                    except Exception:
                        logger.exception("readiness evaluate soft-fail")
                    try:
                        from lumen.bot.session_store import get_session_store

                        get_session_store().save(int(uid), dict(context.user_data))
                    except Exception:
                        logger.exception("persist active_repo after bind failed")
                    result.state.slots["gh_bound_path"] = (bind.path or "")[:200]
                    result.state.slots["gh_bound_url"] = (bind.url or "")[:200]
                    result.state.slots["gh_bound_ok"] = "1"
                    result.state.project_ref = (bind.path or "")[:200]
                    summary = bind.contract_summary or "جاهز"
                    level = str((bind.active_repo or {}).get("understanding_level") or "")
                    brief = (bind.agent_brief or "")[:400]
                    status_bits = [f"✅ مربوط: {bind.full_name or label}", summary]
                    if level:
                        status_bits.append(f"فهم: {level}")
                    if brief:
                        status_bits.append(brief)
                    result.state.slots["gh_status_line"] = "\n".join(status_bits)[:1500]
                    try:
                        from dataclasses import replace as _dc_replace
                        from lumen.engine.services.ui_state.controller import buttons_for_state
                        result = _dc_replace(result, buttons=buttons_for_state(result.state))
                    except Exception:
                        logger.exception("rebuild buttons after bind soft-fail")
                    # Same success UI plane as git_router clone
                    try:
                        from lumen.bot.ui.repo_sections import section_keyboard

                        header = bind.header_ar or f"✅ تم سحب `{bind.full_name or label}`"
                        # Never open sequential env trap — token starts host
                        context.user_data.pop("pending_repo_env", None)
                        adv = list((context.user_data or {}).get("advisory_missing_env") or [])
                        if adv:
                            header += (
                                "\n\n⚙️ متغيرات اختيارية لاحقًا: "
                                + ", ".join(f"`{x}`" for x in adv[:5])
                                + ("…" if len(adv) > 5 else "")
                            )
                        if bind.is_runnable:
                            header += (
                                "\n\n🚀 أرسل توكن البوت من @BotFather للاستضافة على Lumen."
                            )
                            markup = section_keyboard(
                                user_id=int(uid),
                                show_run=True,
                            )
                        else:
                            markup = section_keyboard(
                                user_id=int(uid),
                                show_run=False,
                            )
                        if status_msg is not None:
                            await status_msg.edit_text(header[:4000], reply_markup=markup)
                        else:
                            _em = update.effective_message
                            if _em is not None:
                                await _em.reply_text(header[:4000], reply_markup=markup)
                    except Exception:
                        logger.exception("post-bind UI soft-fail")
                        try:
                            if status_msg is not None:
                                await status_msg.edit_text(
                                    f"✅ تم سحب وربط `{bind.full_name or label}`\n{summary}"
                                )
                        except Exception:
                            pass
                else:
                    result.state.slots["gh_bound_ok"] = "0"
                    result.state.slots["gh_status_line"] = f"❌ {bind.message_ar}"
                    if bind.needs_auth:
                        result.state.slots["gh_connected"] = "0"
                    try:
                        if status_msg is not None:
                            await status_msg.edit_text(f"❌ {bind.message_ar[:500]}")
                    except Exception:
                        pass
            except Exception:
                logger.exception("conn_gh_select bind failed")
                result.state.slots["gh_status_line"] = "❌ فشل ربط المستودع."

    # Connections hub: show live GitHub link status
    if result.state.phase == EngineUiPhase.CONNECTIONS and uid:
        try:
            import asyncio as _aio
            from lumen.engine.services.integrations.connections import get_provider

            prov = get_provider("github")

            def _st():
                return prov.status(int(uid)) if prov else None

            st = await _aio.to_thread(_st)
            if st and st.connected:
                result.state.slots["conn_github_line"] = (
                    f"GitHub: متصل (@{st.display_name})" if st.display_name else "GitHub: متصل"
                )
            else:
                result.state.slots["conn_github_line"] = "GitHub: غير متصل"
        except Exception:
            result.state.slots.setdefault("conn_github_line", "GitHub: —")

    # GitHub App connect (preferred) — deep-link to install URL with signed state.
    if result.ok and action_id == "conn_gh_connect" and uid:
        try:
            from lumen.engine.services.integrations.github.app_auth import (
                github_app_configured,
            )
            from lumen.engine.services.integrations.github.app_oauth_state import (
                build_telegram_install_url,
            )

            _msg = update.effective_message
            if github_app_configured():
                url = build_telegram_install_url(int(uid))
                text_prompt = (
                    "🔗 *اتصل بـ GitHub*\n\n"
                    "1) اضغط الزر وافتح GitHub\n"
                    "2) اختر الحساب والمستودعات المسموح بها لـ Lumen\n"
                    "3) بعد التثبيت ستظهر صفحة نجاح — ثم ارجع للبوت\n\n"
                    "_لا نطلب لصق توكن. الصلاحيات تُدار من GitHub._"
                )
                try:
                    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

                    kb = InlineKeyboardMarkup(
                        [[InlineKeyboardButton("فتح GitHub وتثبيت التطبيق", url=url)]]
                    )
                except Exception:
                    kb = None
                    text_prompt += f"\n\n{url}"
                if _msg is not None:
                    await _msg.reply_text(
                        text_prompt, reply_markup=kb, parse_mode="Markdown"
                    )
                return
            # App not configured → fall through to PAT prompt
            logger.info("github_app not configured — PAT fallback uid=%s", uid)
            action_id = "conn_gh_pat"
        except Exception:
            logger.exception("conn_gh_connect app link failed — PAT fallback")
            action_id = "conn_gh_pat"

    # Manual PAT connect (advanced / fallback).
    # CRITICAL: keep the prompt visible until the user sends the token.
    if result.ok and action_id == "conn_gh_pat" and uid:
        try:
            from lumen.bot.ui.input_prompt import ask_text_input
            from lumen.bot.ui.secret_prompt import build_secret_prompt_markup

            prompt = (
                "🔑 ربط يدوي (متقدم): أرسل توكن GitHub (PAT).\n"
                "• Classic: `ghp_...`\n• Fine-grained: `github_pat_...`\n"
                "الأفضل: صلاحيات Contents/PR فقط — تجنّب صلاحيات واسعة.\n\n"
                "بعد الإرسال سيتم التحقق عبر api.github.com وعرض مستودعاتك."
            )
            _msg = update.effective_message
            prompt_sent = None
            if _msg is not None:
                prompt_sent = await _msg.reply_text(
                    prompt,
                    reply_markup=build_secret_prompt_markup(kind="github", user_id=uid),
                    parse_mode="Markdown",
                )
            else:
                await ask_text_input(update.effective_message, kind="github_pat")
            if context.user_data is not None:
                context.user_data["pending_github_connection"] = True
                if prompt_sent is not None:
                    mid = getattr(prompt_sent, "message_id", None)
                    if mid:
                        context.user_data["pending_github_prompt_mid"] = int(mid)
                try:
                    from lumen.bot.session_store import get_session_store

                    get_session_store().save(int(uid), dict(context.user_data))
                except Exception:
                    logger.debug("persist pending_github_connection soft-fail", exc_info=True)
            return
        except Exception:
            logger.exception("conn_gh_pat prompt failed")

    # Disconnect — step 1: ask confirmation (no delete yet).
    if result.ok and action_id == "conn_gh_disconnect" and uid:
        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            from lumen.bot.ui.keyboards import encode_callback

            result.state.slots["gh_await_disconnect"] = "1"
            kb = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "تأكيد الفصل وحذف الأسرار",
                            callback_data=encode_callback(
                                "conn_gh_disconnect_confirm", "", user_id=int(uid)
                            ),
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "إلغاء",
                            callback_data=encode_callback(
                                "conn_gh_refresh", "", user_id=int(uid)
                            ),
                        )
                    ],
                ]
            )
            _msg = update.effective_message
            if _msg is not None:
                await _msg.reply_text(
                    "⚠️ فصل GitHub سيحذف التوكن/التثبيت المحفوظ نهائيًا من Lumen.\n"
                    "هل أنت متأكد؟",
                    reply_markup=kb,
                )
            return
        except Exception:
            logger.exception("conn_gh_disconnect confirm prompt failed")

    # Disconnect — step 2: confirmed delete.
    if result.ok and action_id == "conn_gh_disconnect_confirm" and uid:
        try:
            from lumen.bot.ui.github_connection_store import delete_github_connection

            delete_github_connection(int(uid))
            if context.user_data is not None:
                context.user_data.pop("github_connection", None)
                context.user_data.pop("pending_github_connection", None)
            result.state.slots["gh_connected"] = "0"
            result.state.slots["gh_login"] = ""
            result.state.slots.pop("gh_await_disconnect", None)
            result.state.slots["gh_status_line"] = "تم فصل الاتصال وحذف بيانات GitHub."
            for i in range(12):
                result.state.slots.pop(f"gh_r{i}_id", None)
                result.state.slots.pop(f"gh_r{i}_title", None)
            try:
                from lumen.engine.services.ui_state.controller import buttons_for_state
                from dataclasses import replace as _dc_replace

                result = _dc_replace(result, buttons=buttons_for_state(result.state))
            except Exception:
                pass
            _msg = update.effective_message
            if _msg is not None:
                await _msg.reply_text("تم فصل GitHub وحذف الأسرار المحفوظة.")
        except Exception:
            logger.exception("conn_gh_disconnect_confirm failed uid=%s", uid)

    # Activity log surface.
    if result.ok and action_id == "conn_gh_activity" and uid:
        try:
            from lumen.engine.services.integrations.github.activity_log import (
                format_activity_ar,
            )

            text_act = format_activity_ar(int(uid), limit=12)
            _msg = update.effective_message
            if _msg is not None:
                await _msg.reply_text(text_act, parse_mode="Markdown")
            return
        except Exception:
            logger.exception("conn_gh_activity failed uid=%s", uid)

    # Confirm / cancel sensitive git push
    if result.ok and action_id == "gh_confirm_push" and uid:
        try:
            pending = (context.user_data or {}).get("pending_git_push") or {}
            path = str(pending.get("path") or "")
            if not path:
                _msg = update.effective_message
                if _msg is not None:
                    await _msg.reply_text("لا يوجد دفع معلّق.")
                return
            if context.user_data is not None:
                context.user_data["pending_git_push"] = {
                    "path": path,
                    "confirmed": True,
                    "has_token": pending.get("has_token"),
                }
            from lumen.bot.routers import git_router as gr
            # Re-enter push intent with confirmation flag set
            class _U:
                pass
            # Minimal: run push via internal helper if available; else message
            token = ""
            try:
                from lumen.engine.services.integrations.connections.credentials import (
                    resolve_github_token,
                )
                token = resolve_github_token(int(uid)) or ""
            except Exception:
                token = ""
            from lumen.engine.services.git_safe_import import get_smart_git
            git_push = get_smart_git().git_push
            _msg = update.effective_message
            status_msg = None
            if _msg is not None:
                status_msg = await _msg.reply_text("📤 جاري الدفع بعد التأكيد…")
            import asyncio
            result_push = await asyncio.to_thread(lambda: git_push(path, token=token or None))
            if getattr(result_push, "ok", False):
                if context.user_data is not None:
                    context.user_data.pop("pending_git_push", None)
                try:
                    from lumen.engine.services.integrations.github.activity_log import record as _act
                    _act(int(uid), "push", detail={"path": path[-80:], "confirmed": True})
                except Exception:
                    pass
                if status_msg is not None:
                    await status_msg.edit_text(f"✅ {getattr(result_push, 'message', 'تم')}")
            else:
                if status_msg is not None:
                    await status_msg.edit_text(
                        f"❌ {getattr(result_push, 'message', 'فشل الدفع')}"
                    )
            return
        except Exception:
            logger.exception("gh_confirm_push failed uid=%s", uid)

    if result.ok and action_id == "gh_cancel_push" and uid:
        try:
            if context.user_data is not None:
                context.user_data.pop("pending_git_push", None)
            _msg = update.effective_message
            if _msg is not None:
                await _msg.reply_text("تم إلغاء الدفع.")
            return
        except Exception:
            logger.exception("gh_cancel_push failed")

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
