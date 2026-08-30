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

from ..config import OUTPUT_DIR, logger
from ..sanitize import user_facing_generation_error
from ..resource_limits import (
    clamp_user_text,
    clamp_spec_request,
    run_with_engine_timeout,
    EngineTimeoutError,
    MAX_USER_MESSAGE_CHARS,
)
from ..helpers import (
    is_allowed,
    looks_like_bot_token,
    normalize_bot_token,
    detect_host_intent,
    chat_route,
    escape_md,
    safe_edit_text,
    make_zip_from_path,
    run_generation,
    run_generation_with_bridge,
)
from ..live import handle_live_run_token, handle_live_deploy_token
from ..progress_tracker import run_with_heartbeat
from ..session_store import get_session_store
from ..capability_boundaries import rejection_message, get_help_text as honest_help
from ..middlewares.auth import (
    rate_limit_ok as _rate_limit_ok,
    rate_limit_wait_seconds as _rate_limit_wait_seconds,
)
from ..middlewares.mongo_sync import (
    ensure_mongo_user as _ensure_mongo_user,
    mongo_plan_for_user as _mongo_plan_for_user,
    persist_session as _persist_session,
    plan_live_seconds as _plan_live_seconds,
)


from .message_intent import (
    _looks_like_generation_request,
    _is_confirm_phrase,
    _prior_bot_request,
)
from .message_generation import execute_bot_generation
from .message_stages.early_gates import (
    gate_auth_and_rate,
    gate_groups,
    try_cancel,
    try_bot_token,
)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.message
    if not message or not message.text:
        return

    # Helpers for ephemeral UX
    _thinking_msg = None

    async def _clear_thinking() -> None:
        nonlocal _thinking_msg
        if _thinking_msg is None:
            return
        try:
            await _thinking_msg.delete()
        except Exception:
            pass
        _thinking_msg = None

    async def _show_thinking() -> None:
        nonlocal _thinking_msg
        if _thinking_msg is not None:
            return
        try:
            try:
                await context.bot.send_chat_action(
                    chat_id=message.chat_id, action="typing"
                )
            except Exception:
                pass
            _thinking_msg = await message.reply_text("Lumen يفكر...🤔")
        except Exception:
            logger.exception("thinking indicator send failed")
            _thinking_msg = None

    request = clamp_user_text(message.text or "")

    if not await gate_auth_and_rate(update=update, context=context, message=message, user=user):
        return

    if not await gate_groups(update=update, context=context, message=message, user=user):
        return

    # Engine UI: answer current need slot with free text when in GEN_SLOTS
    if context.user_data and not (request or "").startswith("/"):
        try:
            from lumen.bot.ui.state_store import load_ui_state, save_ui_state, persist_ui_session
            from lumen.engine.services.ui_state.models import EngineUiPhase
            from lumen.engine.services.ui_state.engine_needs import remaining_needs
            from lumen.engine.services.ui_state.controller import buttons_for_state, missing_for_state
            from lumen.engine.services.ui_state.render import render_message
            from lumen.bot.ui.keyboards import build_inline_keyboard
            from lumen.bot.ui.facts import gather_ui_facts

            ui = load_ui_state(context.user_data)
            if ui.phase == EngineUiPhase.GEN_SLOTS and request:
                rem = remaining_needs(ui.needs or [], ui.slots)
                slot = (ui.slots.get("awaiting_slot") or (rem[0].slot if rem else "")).strip()
                if slot:
                    ui.slots[slot] = request[:500]
                    ui.slots.pop("awaiting_text", None)
                    ui.slots.pop("awaiting_slot", None)
                    rem2 = remaining_needs(ui.needs or [], ui.slots)
                    ui.missing = [n.slot for n in rem2]
                    ui.phase = EngineUiPhase.GEN_SLOTS if rem2 else EngineUiPhase.GEN_CONFIRM
                    save_ui_state(context.user_data, ui)
                    uid_ui = int(user.id) if user else 0
                    if uid_ui:
                        persist_ui_session(uid_ui, dict(context.user_data))
                    facts = gather_ui_facts(uid_ui, context.user_data)
                    body = render_message(ui, facts)
                    await message.reply_text(
                        body[:4000],
                        reply_markup=build_inline_keyboard(buttons_for_state(ui), user_id=uid_ui),
                    )
                    return
        except Exception:
            logger.exception("engine_ui GEN_SLOTS answer failed")

    # Engine UI: description after "إنشاء بوت" → force generate (no type/slots spam)
    if (
        context.user_data
        and context.user_data.get("engine_ui_await_generate")
        and request
        and not request.startswith("/")
    ):
        try:
            from lumen.bot.ui.state_store import load_ui_state, save_ui_state, persist_ui_session
            from lumen.engine.services.ui_state.models import EngineUiPhase

            ui = load_ui_state(context.user_data)
            ui.slots["bot_type"] = "custom"
            ui.slots["bot_description"] = request[:2000]
            ui.slots.pop("awaiting_text", None)
            ui.needs = []
            ui.missing = []
            ui.phase = EngineUiPhase.GENERATING
            save_ui_state(context.user_data, ui)
            context.user_data.pop("engine_ui_await_generate", None)
            context.user_data["force_generate_once"] = True
            context.user_data["last_bot_request"] = request[:2000]
            uid_ui = int(user.id) if user else 0
            if uid_ui:
                persist_ui_session(uid_ui, dict(context.user_data))
            logger.info("engine_ui description received → force generate")
            # fall through into generation pipeline (single status path)
        except Exception:
            logger.exception("engine_ui await_generate handler failed")
            context.user_data["force_generate_once"] = True
    if len((message.text or "").strip()) > MAX_USER_MESSAGE_CHARS:
        await message.reply_text(
            f"⚠️ الرسالة طويلة جداً. الحد الأقصى {MAX_USER_MESSAGE_CHARS} حرفاً."
        )
        # continue with truncated text rather than free DoS
    if not request:
        await _clear_thinking()
        return


    if await try_cancel(message=message, context=context, request=request):
        return

    # Platform under development: deterministic reply on error/bug complaints
    try:
        from lumen.engine.services.platform_status import (
            is_under_development,
            looks_like_error_complaint,
            complaint_reply_ar,
        )
        if is_under_development() and looks_like_error_complaint(request):
            # Keep routing for clear action requests; only pure complaints get this reply.
            _actionish = any(
                k in request.lower()
                for k in (
                    "clone", "generate", "استضاف", "ولّد", "ولد", "اسحب",
                    "repo", "git", "شغل", "ابدأ", "ابدء",
                )
            )
            if not _actionish:
                await _clear_thinking()
                await message.reply_text(complaint_reply_ar()[:4000])
                return
    except Exception:
        logger.exception("platform_status complaint handler failed")

    # Multi-agent HITL (Phase D): تأكيد/رفض <id> [<token>]
    try:
        from ..multi_agent_bridge import try_handle_hitl_message
        _hitl_result = try_handle_hitl_message(
            request,
            user_id=int(user.id) if user else 0,
            user_data=context.user_data,
        )
        if len(_hitl_result) == 3:
            handled, hitl_reply, _hitl_state = _hitl_result
        else:
            handled, hitl_reply = _hitl_result
            _hitl_state = None
        if handled:
            await _clear_thinking()
            await message.reply_text((hitl_reply or "تم.")[:4000])
            return
    except Exception:
        logger.exception("multi_agent HITL bridge failed")

    # User plan status from MongoDB
    if request.lower().split("@")[0] in {"/plan", "/myplan", "/خطة"}:
        uid = int(user.id) if user else 0
        plan = (await asyncio.to_thread(_mongo_plan_for_user, uid)) or "free"
        labels = {
            "free": "Free — مجاني",
            "explorer": "Free — مجاني",
            "starter": "المبادر (Starter) — $8/شهر",
            "growth": "النمو (Growth) — $30/شهر",
            "pro": "النمو (Growth)",
            "unlimited": "النمو (Growth)",
        }
        try:
            from lumen.platform.plans import get_plan, public_plan_dict
            pd = public_plan_dict(get_plan(plan))
            extra = (
                f"\n• التوليد: {pd['generations_per_month']}/شهر"
                f"\n• الاستضافة 24/7: {pd['hosted_bots']} بوت"
                f"\n• معاينة حية: {pd['live_preview_minutes']} دقيقة"
                f"\n• المحرك: {pd['engine_tier']}"
            )
        except Exception:
            extra = ""
        await _clear_thinking()
        await message.reply_text(
            f"👤 خطتك الحالية: {labels.get(plan, plan)}{extra}"
        )
        return

    # Phase 13: capability ops commands (health/trace/learn/promote)
    try:
        from lumen.engine.services.capability_detection.ops import handle_ops_command
        _ops = handle_ops_command(request, user_id=getattr(update.effective_user, "id", None))
        if _ops:
            await _clear_thinking()
            await message.reply_text(_ops)
            return
    except Exception:
        pass

    # Restore durable session (pending_run etc.) after restarts — before token handling
    try:
        if user and context.user_data is not None:
            saved = get_session_store().load(int(user.id))
            for k, v in (saved or {}).items():
                context.user_data.setdefault(k, v)
    except Exception:
        pass

    # Bot token FIRST
    if await try_bot_token(message=message, context=context, user=user, request=request):
        return

    # Thinking indicator only for normal chat / generation (not tokens)
    await _show_thinking()

    if not request:
        await _clear_thinking()
        await message.reply_text("اكتب وصفاً للبوت أو /help.")
        return

    # Remember last explicit bot-build request for later "ابدأ / أنجز" turns.
    if context.user_data is not None and _looks_like_generation_request(request):
        context.user_data["last_bot_request"] = request
        # Fast product path: never wait on Gemini for an explicit bot-build request.
        # User was waiting 10+ minutes with no reply while chat layer hung.
        context.user_data["force_generate_once"] = True
        logger.info("Generation-like request → force generate-now (skip Gemini)")

    # Bare bot specs («بوت متجر…») also skip Gemini catalog chat
    # and go straight to Cline — no (cart_add)/(content_list) feature listing.
    if context.user_data is not None and not (
        context.user_data or {}
    ).get("force_generate_once"):
        _is_bot_spec_early = False
        try:
            from lumen.engine.services.chat_router.service import _looks_like_bot_spec as _llbs
            _is_bot_spec_early = bool(_llbs(request))
        except Exception:
            low = (request or "").lower()
            _is_bot_spec_early = ("بوت" in (request or "")) or ("bot" in low)
        if _is_bot_spec_early or _looks_like_generation_request(request):
            context.user_data["last_bot_request"] = request
            context.user_data["force_generate_once"] = True
            logger.info("Free-agent mode → force generate (skip catalog chat)")

    # If the user embeds start intent in a longer message (… وابدا حالا), force generation.
    if context.user_data is not None and not (context.user_data or {}).get("force_generate_once"):
        _tail = (request or "").strip().lower()
        if any(
            marker in _tail
            for marker in (
                "ابدا حالا", "ابدأ حالا", "ابدأ الآن", "ابدا الان", "وانجز", "و ابدأ",
                "وابدا", "وابدأ", "ابدأ فورا", "generate now", "start now",
            )
        ) and (
            _looks_like_generation_request(request)
            or _prior_bot_request(context.user_data)
            or "بوت" in _tail
            or "bot" in _tail
        ):
            if not _looks_like_generation_request(request):
                prior = _prior_bot_request(context.user_data)
                if prior:
                    request = prior
            context.user_data["force_generate_once"] = True
            logger.info("Start-intent marker forced generate-now path")

    # Confirm a sensitive action previously planned (legacy pending_chat_action / HITL).
    _pending_chat_action = (context.user_data or {}).get("pending_chat_action") if context.user_data else None
    _confirm_now = _is_confirm_phrase(request)
    if _pending_chat_action and _confirm_now:
        action = str(_pending_chat_action.get("name") or "")
        original = str(_pending_chat_action.get("raw_text") or "")
        if context.user_data is not None:
            context.user_data.pop("pending_chat_action", None)
        try:
            if action in {"generate_bot", "refine_bot", "translate_spec", ""}:
                if original.strip():
                    request = original.strip()
                else:
                    prior = _prior_bot_request(context.user_data)
                    if prior:
                        request = prior
                if context.user_data is not None:
                    context.user_data["force_generate_once"] = True
                # fall through into generation
            elif action == "clone_repo":
                from .git_router import try_handle_git
                if await try_handle_git(update, context, original, user, message):
                    return
            elif action in {"host_start", "host_stop", "host_status"}:
                from .hosting_router import try_handle_hosting
                if await try_handle_hosting(update, context, original, user, message):
                    return
            elif action in {"repo_understand", "repo_inspect", "repo_modify"}:
                from lumen.engine.services.tool_runtime import execute_tool
                _tr = execute_tool(
                    action,
                    {},
                    user_id=int(user.id) if user else 0,
                    user_data=dict(context.user_data or {}),
                )
                await message.reply_text((_tr.message or "تم")[:4000])
                return
            else:
                # Unknown pending action + confirm → try bot generation from history
                prior = _prior_bot_request(context.user_data)
                if prior:
                    request = prior
                    if context.user_data is not None:
                        context.user_data["force_generate_once"] = True
                else:
                    await message.reply_text("لم أجد أداة تنفيذ مطابقة لهذا الطلب.")
                    return
        except Exception:
            logger.exception("confirmed chat action failed: %s", action)
            await message.reply_text("تعذر تنفيذ العملية المؤكدة. راجع سجل الخدمة للتفاصيل.")
            return
        if action not in {"generate_bot", "refine_bot", "translate_spec", ""} and not (
            context.user_data or {}
        ).get("force_generate_once"):
            return

    # Short confirmation after a prior generation-like user message in history:
    # "تمام ابدا وانجز" must resume generation even when Gemini is down.
    if _confirm_now and not _looks_like_generation_request(request):
        prior = _prior_bot_request(context.user_data if context.user_data is not None else None)
        if prior:
            request = prior
            if context.user_data is not None:
                context.user_data["force_generate_once"] = True
            logger.info("Confirm phrase resumed prior bot request")


    
    # ══════════════════════════════════════════════════════════════════
    # GENERATE-NOW FAST PATH
    # User confirmed (ابدأ / تمام ابدا وانجز / …) with a known bot request.
    # Do not touch Gemini, L3, help gates, or feasibility soft-blocks.
    # ══════════════════════════════════════════════════════════════════
    if (context.user_data or {}).get("force_generate_once"):
        # Instant ack so the user never stares at silence for minutes.
        try:
            await message.reply_text("استلمت الطلب ✅ جاري التوليد الآن…")
        except Exception:
            pass
        gen_request = clamp_spec_request(request)
        if not _looks_like_generation_request(gen_request):
            prior = _prior_bot_request(context.user_data)
            if prior:
                gen_request = prior
        if not gen_request.strip():
            if context.user_data is not None:
                context.user_data.pop("force_generate_once", None)
            await message.reply_text(
                "مفيش وصف بوت محفوظ. ابعت وصف البوت تاني (مثال: عايز بوت جروب يرحب ويحظر)."
            )
            return

        # Engine owns understanding + keys + generation (no translator/bridge layer).
        # Multi-agent / Cline reads LLM keys itself via model_router + key_pool.
        preferred_keys = None
        if context.user_data is not None:
            context.user_data.pop("force_generate_once", None)
            context.user_data["translated_source"] = "engine_direct"
        logger.info("generate-now engine-direct path (no translate/bridge layer) request_len=%s", len(gen_request))

        await _clear_thinking()
        status_msg = await message.reply_text("⚙️ جاري توليد البوت الآن…")
        await execute_bot_generation(
            message=message,
            context=context,
            user=user,
            gen_request=gen_request,
            status_msg=status_msg,
            preferred_keys=preferred_keys,
            cache_key=gen_request,
        )

        return

    # ── EARLY: bound active_repo → engine tools + answer (skip Gemini fluff) ──
    # NEVER intercept bot generation/specs here — those must reach:
    #   multi-agent / Cline engine (Gemini translate dual-path retired)
    try:
        _ar0 = (context.user_data or {}).get("active_repo") if context.user_data else None
        _path0 = ""
        if isinstance(_ar0, dict):
            _path0 = str(_ar0.get("path") or "").strip()
        from pathlib import Path as _PathEarly
        _repo_ok0 = bool(_path0 and _PathEarly(_path0).is_dir())
        _req0 = (request or "").strip()
        _other0 = bool(re.search(
            r"(اسحب|clone|بوش|push|pull|استضاف|host|ول[ّ]?د|اعمل\s*بوت|generate|/start|/help|/status)",
            _req0,
            re.I,
        ))
        # Bot-spec descriptions (e.g. «بوت متجر إلكتروني…») must NOT be eaten by repo tools
        _bot_spec0 = False
        try:
            from lumen.engine.services.chat_router.service import _looks_like_bot_spec as _llbs
            _bot_spec0 = bool(_llbs(_req0)) or bool(_looks_like_generation_request(_req0))
        except Exception:
            _bot_spec0 = bool(_looks_like_generation_request(_req0)) or bool(
                re.match(r"^\s*بوت\b", _req0) and len(_req0) >= 18
            )
        if (
            _repo_ok0
            and not _other0
            and not _bot_spec0
            and not (context.user_data or {}).get("force_generate_once")
            and len(_req0) >= 2
            and not _req0.startswith("/")
        ):
            await _clear_thinking()
            status0 = await message.reply_text("جاري قياس المستودع بالأدوات…")
            from lumen.engine.services.tool_runtime import execute_tool
            ud0 = dict(context.user_data or {})
            ud0["user_id"] = int(user.id) if user else 0
            tr0 = execute_tool(
                "repo_understand",
                {
                    "path": _path0,
                    "url": str((_ar0 or {}).get("url") or ""),
                    "text": _req0,
                    "raw_text": _req0,
                },
                user_id=int(user.id) if user else 0,
                user_data=ud0,
            )
            if context.user_data is not None and isinstance(ud0.get("active_repo"), dict):
                context.user_data["active_repo"] = ud0["active_repo"]
                if ud0.get("last_project_path"):
                    context.user_data["last_project_path"] = ud0["last_project_path"]
                try:
                    _persist_session(user, context)
                except Exception:
                    pass
            msg0 = (tr0.message or "").strip()
            if re.search(r"(سطر|أسطر|اسطر|lines|loc|ملف|files)", _req0, re.I):
                try:
                    from lumen.engine.services.repo_understanding.repo_tools import run_tool
                    st = run_tool("stats", _PathEarly(_path0))
                    lg = run_tool("largest_files", _PathEarly(_path0), limit=10)
                    facts = (
                        f"إجمالي الملفات: {st.get('total_files')}\n"
                        f"إجمالي الأسطر (نصي): {st.get('total_lines')}\n"
                        f"أسطر الكود: {st.get('code_lines')}\n"
                        f"حسب الامتداد: {st.get('files_by_extension')}\n"
                        f"أسطر الكود حسب الامتداد: {st.get('code_lines_by_extension')}\n"
                        "أكبر الملفات:\n"
                        + "\n".join(
                            f"• {x.get('path')}: {x.get('lines')} سطر"
                            for x in (lg.get('by_lines') or lg.get('files') or [])[:10]
                        )
                    )
                    if msg0 and "engine materials only" not in msg0.lower() and len(msg0) > 40:
                        msg0 = facts + "\n\n" + msg0
                    else:
                        msg0 = facts
                except Exception:
                    logger.exception("stats overlay failed")
            await status0.edit_text((msg0 or ("تم" if tr0.ok else "فشل"))[:4000])
            return
    except Exception:
        logger.exception("early active_repo bind failed")

    # ══════════════════════════════════════════════════════════════════
    # STANDALONE CHAT REMOVED — engine / agents own every NL message.
    # No translator_client.chat_request, no Gemini/Groq conversational layer.
    # Routing: chat_router (capability) → tool_runtime / delegated routers
    #          → multi-agent/Cline for generate/refine.
    # ══════════════════════════════════════════════════════════════════
    if (context.user_data or {}).get("force_generate_once"):
        # Engine-direct generation already handled above when flag was set early.
        # If we still reach here with the flag, keep engine_direct markers.
        if context.user_data is not None:
            context.user_data["translated_preferred_keys"] = []
            context.user_data["translated_source"] = "engine_direct"
        logger.info("engine-direct path (standalone chat layer permanently removed)")

    # Platform metering for NL turns (no LLM chat call)
    if not request.startswith("/"):
        try:
            from lumen.platform.metering import get_metering
            from lumen.platform.tenants import get_tenant_store
            telegram_user_id = int(user.id) if user else 0
            tenant = get_tenant_store().get_by_telegram(telegram_user_id) if telegram_user_id else None
            if tenant is not None:
                get_metering().record(
                    str(tenant.tenant_id),
                    messages=1,
                    characters=len(request),
                    event="engine_message",
                )
        except Exception:
            logger.exception("engine message metering unavailable; continuing")

        # Durable memory context for agents (not for a standalone chat model)
        try:
            from lumen.engine.services.chat_memory import get_chat_memory
            _uid = int(user.id) if user else 0
            if _uid:
                get_chat_memory().append(_uid, "user", request, provider="engine")
        except Exception:
            logger.exception("chat_memory user append failed")

        # Semantic memory ingest of user turn only — agent replies are recorded
        # by tool/generation paths when they produce outcomes.
        try:
            _sem_uid = int(user.id) if user else 0
            if _sem_uid:
                from lumen.engine.services.semantic_memory import ingest_exchange
                _ar = (context.user_data or {}).get("active_repo") or {}
                _sem_pid = str(_ar.get("path") or "") if isinstance(_ar, dict) else ""
                # user-only; assistant side filled when tools answer
                ingest_exchange(
                    user_id=_sem_uid,
                    user_message=request,
                    assistant_message="",
                    project_id=_sem_pid,
                    recent_summary="",
                    recent_turns=[],
                )
        except Exception:
            logger.exception("semantic_memory user ingest failed")

    if request.startswith("/"):
        return
    # Very short non-spec confirmations
    if len(request) < 3 and request.lower() not in {"ok", "yes", "لا", "نعم"}:
        await message.reply_text(
            "الرسالة قصيرة جداً. اكتب ماذا يفعل البوت (مثال: بوت فيه /start و /help)."
        )
        return

    uid = int(user.id) if user else 0

    # Light session memory (agents still own the turn)
    try:
        from lumen.engine.services.user_memory import get_user_memory
        get_user_memory(uid, OUTPUT_DIR).add_turn("user", request)
    except Exception:
        logger.exception("user_memory load failed")

    # Context binding so agents see the active project
    try:
        from lumen.engine.services.context_engine import resolve_context
        _active = (context.user_data or {}).get("active_repo") or {}
        _ctx_res = resolve_context(
            uid,
            request,
            base_dir=OUTPUT_DIR,
            active_path=str(_active.get("path") or ""),
        )
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
    except Exception:
        logger.exception("context_engine failed")

    # Bot token paste remains a specialized early handler
    from ..handlers.token_handler import try_handle_token
    if await try_handle_token(update, context, request, user, message):
        return

    # ══════════════════════════════════════════════════════════════════
    # PRIMARY PATH: multi-agent engine turn owns the message end-to-end
    # RouterAgent → tool_runtime / generate signal — no standalone chat
    # ══════════════════════════════════════════════════════════════════
    await _clear_thinking()
    try:
        from lumen.engine.services.multi_agent.engine_turn import handle_user_turn
        turn = handle_user_turn(
            request,
            user_id=uid,
            user_data=dict(context.user_data or {}),
        )
    except Exception:
        logger.exception("handle_user_turn failed")
        await message.reply_text("تعذر تشغيل المحرك على هذا الطلب. حاول مرة أخرى.")
        return

    # Apply agent side-effects into the Telegram session
    if context.user_data is not None and isinstance(turn.user_data_updates, dict):
        for k, v in turn.user_data_updates.items():
            context.user_data[k] = v
        try:
            _persist_session(user, context)
        except Exception:
            logger.exception("persist after engine_turn failed")

    # Generate / refine → multi-agent / Cline pipeline (same as force-generate)
    if turn.action in {"generate", "refine"}:
        gen_request = (turn.generate_request or request or "").strip()
        if not gen_request:
            prior = _prior_bot_request(context.user_data if context.user_data is not None else None)
            gen_request = prior or ""
        if not gen_request:
            await message.reply_text(
                "مفيش وصف بوت واضح. ابعت وصف البوت (مثال: عايز بوت جروب يرحب ويحظر)."
            )
            return
        if context.user_data is not None:
            context.user_data.pop("force_generate_once", None)
            context.user_data["translated_source"] = "engine_turn"
            context.user_data["last_bot_request"] = gen_request[:2000]
        # Surface agent preamble (e.g. repo_modify brief) before generation starts
        if (turn.reply or "").strip():
            try:
                await message.reply_text(str(turn.reply)[:4000])
            except Exception:
                pass
        status_msg = await message.reply_text(
            "⚙️ المحرك (الوكلاء) يبدأ التوليد الآن…"
            if turn.action == "generate"
            else "⚙️ المحرك يبدأ التعديل الآن…"
        )
        await execute_bot_generation(
            message=message,
            context=context,
            user=user,
            gen_request=clamp_spec_request(gen_request),
            status_msg=status_msg,
            preferred_keys=None,
            cache_key=gen_request,
        )
        return

    # Tool / help / confirm — reply from agent final_message
    reply = (turn.reply or "").strip()
    if not reply:
        reply = "تم." if turn.ok else "تعذر تنفيذ الطلب عبر المحرك."
    await message.reply_text(reply[:4000])
    return
