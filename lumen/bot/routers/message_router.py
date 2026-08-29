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
        handled, hitl_reply = try_handle_hitl_message(
            request,
            user_id=int(user.id) if user else 0,
            user_data=context.user_data,
        )
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
            context.user_data["free_agent_path"] = True
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

    # Confirm a sensitive action previously planned by the standalone chat model.
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
            context.user_data["engine_direct_request"] = gen_request
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

    _skip_chat_for_generate = bool(
        (context.user_data or {}).get("force_generate_once")
    )
    if _skip_chat_for_generate:
        # User confirmed generation — skip Gemini entirely (slow / failing).
        # Engine-direct: raw user text goes to multi-agent/Cline. No translate/bridge.
        logger.info("Skipping chat layer; force_generate_once active")
        if context.user_data is not None:
            context.user_data["engine_direct_request"] = request
            context.user_data["translated_preferred_keys"] = []
            context.user_data["translated_source"] = "engine_direct"
            context.user_data["free_agent_path"] = True
        try:
            await message.reply_text("جاري تجهيز البوت الآن…")
        except Exception:
            pass

    if not request.startswith("/") and not _skip_chat_for_generate:
        # Every natural-language message goes to the standalone chat model first.
        # Keyword detection is only used to choose an outage message; it never
        # decides whether the model gets the message.
        _state_question = any(
            token in request.lower()
            for token in (
                "خطة", "الباقة", "اشتراكي", "رسالة", "رسائل", "حرف", "حروف",
                "توليد", "توليدات", "استهلاك", "استخدمت", "المتبقي", "باقي",
                "plan", "subscription", "message", "messages", "character", "usage",
                "remaining", "quota",
            )
        )
        telegram_user_id = int(user.id) if user else 0
        # Context is best-effort. A PostgreSQL/metering failure must not prevent
        # Gemini from answering ordinary chat with an explicit data-unavailable
        # context; the model must never receive invented plan or usage facts.
        live_context = {
            "identity_known": False,
            "telegram_user_id": telegram_user_id,
            "data_available": False,
            "reason": "server_context_unavailable",
        }
        try:
            from lumen.platform.metering import get_metering
            from lumen.platform.tenants import get_tenant_store

            tenant = get_tenant_store().get_by_telegram(telegram_user_id) if telegram_user_id else None
            if tenant is not None:
                get_metering().record(
                    str(tenant.tenant_id),
                    messages=1,
                    characters=len(request),
                    event="chat_message",
                )
        except Exception:
            logger.exception("live model metering unavailable; continuing with chat")

        try:
            from ..live_user_context import build_live_user_context
            live_context = build_live_user_context(telegram_user_id)
        except Exception:
            logger.exception("live model context unavailable; using safe context")

        _active_repo = (context.user_data or {}).get("active_repo") if context.user_data else None
        if isinstance(_active_repo, dict):
            live_context["active_repo"] = {
                "path": str(_active_repo.get("path") or ""),
                "url": str(_active_repo.get("url") or ""),
                "facts": _active_repo.get("facts") or (_active_repo.get("dossier") or {}).get("facts") or {},
                "key_file_names": (_active_repo.get("dossier") or {}).get("key_file_names")
                    or list((_active_repo.get("dossier") or {}).get("key_files") or [])[:20],
                "bound": True,
            }

        # Durable chat memory (survives key failover + worker restart)
        chat_history = []
        _mem_ctx: dict = {}
        try:
            from lumen.engine.services.chat_memory import get_chat_memory
            _cm = get_chat_memory()
            _uid = int(user.id) if user else 0
            if _uid:
                _mem_ctx = _cm.context_for_llm(_uid)
                chat_history = list(_mem_ctx.get("conversation_history") or [])
        except Exception:
            logger.exception("chat_memory load failed")
            _mem_ctx = {}
        if not chat_history and context.user_data is not None:
            try:
                chat_history = list(context.user_data.get("chat_history") or [])[-16:]
            except Exception:
                chat_history = []
        chat_context = dict(live_context)
        chat_context["conversation_history"] = chat_history
        if _mem_ctx.get("conversation_summary"):
            chat_context["conversation_summary"] = _mem_ctx["conversation_summary"]
        if _mem_ctx.get("memory_facts"):
            chat_context["memory_facts"] = _mem_ctx["memory_facts"]
        # Active bot inspection so chat (Groq) can discuss real commands/weaknesses
        try:
            from lumen.engine.services.bot_inspector import inspect_bot_project
            from lumen.engine.services.bot_inspector.service import resolve_user_bot_path
            _bot_path = resolve_user_bot_path(
                user_data=dict(context.user_data or {}),
            )
            if _bot_path:
                _insp = inspect_bot_project(_bot_path)
                chat_context["active_bot"] = _insp.to_dict()
                chat_context["active_bot_brief"] = _insp.chat_brief()
                if context.user_data is not None:
                    context.user_data["last_project_path"] = _bot_path
        except Exception:
            logger.exception("bot inspection for chat failed")
        try:
            from lumen.engine.services.translator_client import chat_request
            chat_result = chat_request(request, chat_context)
        except Exception:
            logger.exception("live model chat unavailable; continuing generation path")
            chat_result = None

        # Persist turns to durable memory + in-process user_data
        _provider = ""
        if isinstance(chat_result, dict):
            _provider = str(chat_result.get("provider") or chat_result.get("model") or "")[:40]
        try:
            from lumen.engine.services.chat_memory import get_chat_memory
            _cm = get_chat_memory()
            _uid = int(user.id) if user else 0
            if _uid:
                _cm.append(_uid, "user", request, provider=_provider)
                if isinstance(chat_result, dict) and str(chat_result.get("answer") or "").strip():
                    _cm.append(
                        _uid,
                        "assistant",
                        str(chat_result["answer"]),
                        provider=_provider,
                        meta={"action": (chat_result.get("action") or {}).get("name")},
                    )
                facts = {}
                if (context.user_data or {}).get("last_bot_request"):
                    facts["last_bot_request"] = context.user_data.get("last_bot_request")
                if (context.user_data or {}).get("pending_chat_action"):
                    facts["pending_chat_action"] = context.user_data.get("pending_chat_action")
                if live_context.get("plan"):
                    facts["plan"] = live_context.get("plan")
                if facts:
                    _cm.set_facts(_uid, **facts)
        except Exception:
            logger.exception("chat_memory persist failed")
        if context.user_data is not None:
            try:
                updated_history = chat_history + [{"role": "user", "content": request}]
                if isinstance(chat_result, dict) and str(chat_result.get("answer") or "").strip():
                    updated_history.append({"role": "assistant", "content": str(chat_result["answer"])})
                context.user_data["chat_history"] = updated_history[-16:]
            except Exception:
                pass

        _translated_generation_request = ""
        _translated_preferred_keys = []
        _translation_source = ""
        if isinstance(chat_result, dict):
            try:
                # Engine-direct policy: do not use Gemini/Qwen translation layers
                # to produce generation contracts. Multi-agent/Cline owns understanding.
                _translation = chat_result.get("translation")
                _action = chat_result.get("action") if isinstance(chat_result.get("action"), dict) else {}
                if str(_action.get("name") or "") in {"generate_bot", "refine_bot"}:
                    # Signal force-generate with raw user text; engine handles the rest.
                    if context.user_data is not None:
                        context.user_data["force_generate_once"] = True
                        context.user_data["engine_direct_request"] = request
                        context.user_data["translated_source"] = "engine_direct_from_chat_action"
                    _translated_generation_request = request
                    _translation_source = "engine_direct"
                    logger.info("Chat action generate_bot → engine-direct (no translate layer)")
            except Exception:
                logger.exception("engine-direct generation handoff failed")

        if _translated_generation_request:
            request = _translated_generation_request
            # refine_bot: merge structural features from the user's current bot
            try:
                _act = (chat_result or {}).get("action") if isinstance(chat_result, dict) else None
                _an = str((_act or {}).get("name") or "") if isinstance(_act, dict) else ""
                if _an == "refine_bot" or "refine" in (_translation_source or ""):
                    from lumen.engine.services.bot_inspector import inspect_bot_project
                    from lumen.engine.services.bot_inspector.service import resolve_user_bot_path
                    _bp = resolve_user_bot_path(user_data=dict(context.user_data or {}))
                    if _bp:
                        _ins = inspect_bot_project(_bp)
                        prior = list(_ins.features_hint or [])
                        # map commands → features via command_map when features_hint empty
                        if not prior and _ins.commands:
                            try:
                                from lumen.engine.services.capability_detection.catalog import feature_for_command
                                for c in _ins.commands:
                                    f = feature_for_command(c)
                                    if f and f not in prior:
                                        prior.append(f)
                            except Exception:
                                pass
                        merged = []
                        for k in list(prior) + list(_translated_preferred_keys or []):
                            if k and k not in merged:
                                merged.append(k)
                        if merged:
                            _translated_preferred_keys = merged
                        # ensure request mentions prior bot refine
                        if "refine" not in request.lower() and "تعديل" not in request:
                            request = (
                                f"تعديل البوت الحالي مع الاحتفاظ بالميزات: "
                                f"{', '.join(prior[:20])}. التغيير المطلوب: {request}"
                            )
            except Exception:
                logger.exception("refine_bot feature merge failed")
            if context.user_data is not None:
                context.user_data["translated_spec_request"] = request
                context.user_data["translated_preferred_keys"] = _translated_preferred_keys
                context.user_data["translated_source"] = _translation_source
                context.user_data["force_generate_once"] = True

        _force_generate = bool((context.user_data or {}).get("force_generate_once"))
        _answer = str((chat_result or {}).get("answer") or "").strip() if isinstance(chat_result, dict) else ""
        _action = (chat_result or {}).get("action") if isinstance(chat_result, dict) else None
        _action_name = str((_action or {}).get("name") or "") if isinstance(_action, dict) else ""
        if isinstance(_action, dict) and _action_name in {"generate_bot", "refine_bot"} and not _action.get("requires_confirmation"):
            _force_generate = True
        # Gemini often *says* it will generate without setting action=generate_bot.
        if _answer and re.search(
            r"سأقوم.*?(?:توليد|ببناء|بتجهيز)|ابدأ(?: الآن)? في توليد|بدء التوليد|start(?:ing)? generat|will (?:now )?generat",
            _answer,
            re.I,
        ):
            _force_generate = True

        if _force_generate and not _translated_generation_request:
            # Engine-direct: use prior bot request or current text. No translate/bridge.
            prior = _prior_bot_request(context.user_data if context.user_data is not None else None)
            gen_src = prior if prior else (request if _looks_like_generation_request(request) else "")
            if gen_src:
                request = gen_src
                if context.user_data is not None:
                    context.user_data["engine_direct_request"] = gen_src
                    context.user_data["translated_source"] = "engine_direct"
                _translated_generation_request = gen_src
                logger.info("Force-generate engine-direct (no translate/bridge) len=%s", len(gen_src))

        # Chat answers that are NOT a generate-now signal stay as chat only.
        if (
            not _translated_generation_request
            and not _force_generate
            and chat_result
            and _answer
        ):
            if isinstance(_action, dict):
                if _action.get("requires_confirmation"):
                    if context.user_data is not None:
                        # Prefer last_bot_request so later "ابدأ" still has the real spec.
                        raw_for_pending = _prior_bot_request(context.user_data) or request
                        context.user_data["pending_chat_action"] = {
                            "name": _action_name or "generate_bot",
                            "raw_text": raw_for_pending,
                        }
                elif _action_name == "host_status":
                    from .hosting_router import try_handle_hosting
                    if await try_handle_hosting(update, context, request, user, message):
                        return
            # Tool path: Groq only selects; engines execute
            if isinstance(_action, dict) and _action_name in {
                "clone_repo", "create_repo", "git_push", "git_pull", "repo_inspect", "repo_understand", "repo_modify",
            }:
                await _clear_thinking()
                try:
                    from lumen.engine.services.tool_runtime import execute_tool
                    _params = dict(_action.get("params") or {})
                    if _action_name == "clone_repo" and not _params.get("url"):
                        _params["text"] = request
                    _tr = execute_tool(
                        _action_name,
                        _params,
                        user_id=int(user.id) if user else 0,
                        user_data=dict(context.user_data or {}),
                    )
                    if _tr.ok and _action_name in {"clone_repo", "create_repo"} and _tr.data.get("path"):
                        if context.user_data is not None:
                            context.user_data["active_repo"] = {
                                "path": _tr.data["path"],
                                "url": _tr.data.get("url") or "",
                            }
                            context.user_data["last_project_path"] = _tr.data["path"]
                    if (not _tr.ok) and _tr.data.get("needs_auth") and context.user_data is not None:
                        if _action_name == "create_repo":
                            context.user_data["pending_create_repo"] = {
                                "name": (_params.get("name") or _tr.data.get("pending_name") or ""),
                            }
                        elif _action_name == "git_push":
                            context.user_data["pending_git_push"] = {
                                "path": _params.get("path") or _tr.data.get("path") or "",
                            }
                    if (
                        _tr.ok
                        and _action_name == "repo_modify"
                        and _tr.data.get("defer_refine")
                        and context.user_data is not None
                    ):
                        change = str(_tr.data.get("change") or request)
                        context.user_data["last_project_path"] = str(
                            _tr.data.get("path") or context.user_data.get("last_project_path") or ""
                        )
                        context.user_data["force_generate_once"] = True
                        context.user_data["translated_spec_request"] = (
                            f"تعديل البوت/المشروع في {_tr.data.get('path')}: {change}"
                        )
                        # continue into refine/generation pipeline
                        request = context.user_data["translated_spec_request"]
                        _force_generate = True
                        _translated_generation_request = request
                        await message.reply_text(
                            (
                                ((_answer + "\n\n") if _answer else "")
                                + (_tr.message or "جاري التعديل عبر المحرك…")
                            )[:4000]
                        )
                        # do not return — fall through to generation
                    else:
                        msg = (_answer + "\n\n" if _answer else "") + (_tr.message or "")
                        await message.reply_text(msg[:4000])
                        return
                    if not (_translated_generation_request and _force_generate):
                        return
                except Exception:
                    logger.exception("tool execution failed")
            if not (_translated_generation_request and _force_generate):
                await _clear_thinking()
                await message.reply_text(_answer)
                return

        if _force_generate and _answer and not _translated_generation_request:
            # Still show the model message, then continue into generation below.
            await _clear_thinking()
            try:
                await message.reply_text(_answer)
            except Exception:
                pass
        # Diagnostics: never log the raw key.
        try:
            from lumen.engine.services.gemini_client import status_snapshot
            snap = status_snapshot()
        except Exception:
            # Prefer key_pool so GEMINI_API_KEYS bulk / numbered keys count
            _kp = False
            try:
                from lumen.engine.services.llm.key_pool import gemini_keys as _gk

                _kp = bool(_gk())
            except Exception:
                _kp = bool(
                    (
                        os.getenv("GEMINI_API_KEY")
                        or os.getenv("GEMINI_API_KEYS")
                        or os.getenv("GOOGLE_API_KEY")
                        or ""
                    ).strip()
                )
            snap = {
                "enabled": False,
                "key_present": _kp,
                "key_len": 0,
                "model": os.getenv("GEMINI_MODEL") or "gemini-2.0-flash",
                "gemini_enabled_env": os.getenv("GEMINI_ENABLED"),
            }
        try:
            if _thinking_msg is not None:
                await _thinking_msg.delete()
                _thinking_msg = None
        except Exception:
            pass
        logger.warning(
            "chat_request returned no answer; gemini_enabled=%s key_present=%s "
            "key_len=%s model=%s GEMINI_ENABLED=%s env_names_seen=%s",
            snap.get("enabled"),
            snap.get("key_present"),
            snap.get("key_len"),
            snap.get("model"),
            snap.get("gemini_enabled_env"),
            snap.get("env_names_seen"),
        )

        _generation_like = (
            _looks_like_generation_request(request)
            or bool((context.user_data or {}).get("force_generate_once"))
            or bool(_translated_generation_request)
        )
        if _generation_like:
            # A model outage must not block an explicit bot build request.
            logger.warning(
                "Gemini chat unavailable for generation request; continuing with Cline path"
            )
        elif _state_question:
            await message.reply_text(
                "تعذر الوصول إلى بيانات الخطة الآن. حاول مرة أخرى بعد قليل."
            )
            return
        # Force re-resolve key at message time (not only boot)
        try:
            from lumen.engine.services.gemini_client import _api_key, status_snapshot as _ss
            snap = _ss()
            if not snap.get("key_present") and _api_key():
                snap["key_present"] = True
                snap["key_len"] = len(_api_key())
        except Exception:
            logger.exception("gemini re-resolve failed")
        if not _generation_like and not snap.get("key_present"):
            await message.reply_text(
                "طبقة المحادثة غير مفعّلة: مفتاح Gemini غير موجود على السيرفر.\n"
                "أضف أحد المتغيرات في Railway ثم أعد النشر:\n"
                "• GEMINI_API_KEYS (مفتاح أو أكثر مفصولة بفاصلة أو سطر)\n"
                "• أو GEMINI_API_KEY / GOOGLE_API_KEY"
            )
            return
        if not _generation_like and snap.get("enabled") is False:
            await message.reply_text(
                "طبقة المحادثة معطّلة عبر GEMINI_ENABLED. احذف المتغير أو اضبطه على 1."
            )
            return
        if _generation_like:
            # Do not send the generic chat outage message for a build request;
            # continue below so Cline can generate.
            pass
        else:
            await message.reply_text(
                "تعذر تشغيل طبقة المحادثة الآن (فشل استدعاء النموذج). حاول مرة أخرى بعد قليل."
            )
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

    try:
        from lumen.engine.services.user_memory import get_user_memory
        _mem = get_user_memory(uid, OUTPUT_DIR)
        _mem.add_turn("user", request)
    except Exception:
        _mem = None
        logger.exception("user_memory load failed")

    _ctx_res = None
    try:
        from lumen.engine.services.context_engine import resolve_context
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
            from lumen.engine.services.continuity import plan_continuity
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
            from lumen.engine.services.advanced_partner import (
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

    # --- Delegated routers (token / git / hosting / active repo) ---
    from ..handlers.token_handler import try_handle_token
    from .git_router import try_handle_git
    from .hosting_router import try_handle_hosting
    from .repo_dev_router import try_handle_repo_dev

    if await try_handle_token(update, context, request, user, message):
        return
    if await try_handle_git(update, context, request, user, message):
        return
    if await try_handle_hosting(update, context, request, user, message):
        return
    if await try_handle_repo_dev(update, context, request, user, message):
        return



    # ChatRouter: help / list capabilities (route only)
    # Skip help when the message is clearly a bot specification (contains /commands etc.)
    _rt_help = chat_route(request)
    _is_bot_spec = False
    try:
        from lumen.engine.services.chat_router.service import _looks_like_bot_spec
        _is_bot_spec = _looks_like_bot_spec(request)
    except Exception:
        _is_bot_spec = bool(
            re.search(r"اعمل\s*بوت|أن?شئ\s*بوت|عايز\s*بوت", request, re.I)
            or len(re.findall(r"/[a-zA-Z][a-zA-Z0-9_]{1,32}", request)) >= 2
        )
    if not _is_bot_spec:
        _is_bot_spec = bool(
            (context.user_data or {}).get("force_generate_once")
            or (context.user_data or {}).get("translated_spec_request")
            or (context.user_data or {}).get("last_bot_request")
            or _looks_like_generation_request(request)
            or (
                "bot" in request.lower()
                and any(k in request for k in ("welcome_set", "user_ban", "telegram", "feature"))
            )
        )
    if (
        (not _is_bot_spec)
        and _rt_help
        and getattr(_rt_help, "ok", False)
        and _rt_help.capability_id == "help"
    ):
        try:
            from lumen.engine.services.chat_router import get_router
            await message.reply_text(honest_help())
        except Exception:
            await message.reply_text("مساعدة: اسحب مستودع | ولّد بوت | استضافة | تحليل استاتيكي")
        return

    # ------------------------------------------------------------------
    # Phase 4 — Developer partner mode (AI only, zero fixed scripts)
    # SmartChat + memory + context: clarify, challenge, route to engines.
    # ------------------------------------------------------------------
    # Bind Grok to the user-cloned active_repo: ANY question not clearly another
    # hard capability is answered from that repo's materials (not phrase whitelist).
    _repo_bound = False
    try:
        _ar = (context.user_data or {}).get("active_repo") if context.user_data else None
        _has_repo = isinstance(_ar, dict) and bool(_ar.get("path"))
        from pathlib import Path as _P
        _repo_path_ok = bool(_has_repo and _P(str(_ar.get("path"))).is_dir())
    except Exception:
        _repo_path_ok = False
        _ar = None

    _rt = chat_route(request)
    _other_hard_ids = {
        "clone_repo", "create_repo", "git_push", "git_pull",
        "host_start", "host_stop", "host_status", "host_diagnose",
        "static_analysis", "package_health", "upgrade_recommend", "upgrade_apply",
        "repo_develop", "live_run", "generate_bot", "repo_modify", "help",
    }
    _rt_cap = str(getattr(_rt, "capability_id", "") or "") if _rt is not None else ""
    _rt_hard_other = (
        bool(getattr(_rt, "ok", False))
        and _rt_cap in _other_hard_ids
        and float(getattr(_rt, "confidence", 0) or 0) >= 0.55
    )
    _looks_gen = False
    try:
        _looks_gen = bool(_looks_like_generation_request(request))
    except Exception:
        _looks_gen = False

    # Never hijack bot-generation specs into repo_understand just because
    # an active_repo exists from a previous clone.
    if (
        _repo_path_ok
        and not _rt_hard_other
        and not _looks_gen
        and not _is_bot_spec
        and not (context.user_data or {}).get("force_generate_once")
        and len((request or "").strip()) >= 2
    ):
        class _BoundRepoRt:
            ok = True
            capability_id = "repo_understand"
            confidence = 0.99
            params = {
                "path": str((_ar or {}).get("path") or ""),
                "url": str((_ar or {}).get("url") or ""),
                "text": request,
                "raw_text": request,
                "question": request,
            }
        _rt = _BoundRepoRt()
        _repo_bound = True
        logger.info("active_repo bound → repo_understand for free-form Q")
    _hard_caps = {
        "clone_repo", "create_repo", "git_push", "git_pull", "host_start", "host_stop", "host_status", "host_diagnose",
        "static_analysis", "package_health", "upgrade_recommend", "upgrade_apply",
        "repo_develop", "live_run", "generate_bot",
        "repo_understand", "repo_inspect", "repo_modify",
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

    # Engine-only hard tools (Grok/chat only routes intent — engines execute)
    _engine_only = {
        "repo_understand", "repo_inspect", "repo_modify",
        "static_analysis", "package_health", "upgrade_recommend", "upgrade_apply",
        "live_run",
    }
    if _is_hard and getattr(_rt, "capability_id", "") in _engine_only:
        await _clear_thinking()
        cap = str(_rt.capability_id)
        status = await message.reply_text(
            "📥 المحرك يجمع المستودع..." if cap == "repo_understand"
            else f"⚙️ جاري تنفيذ `{cap}` عبر المحرك..."
        )
        try:
            from lumen.engine.services.tool_runtime import execute_tool
            params = dict(getattr(_rt, "params", None) or {})
            params.setdefault("text", request)
            params.setdefault("raw_text", request)
            # pass user_id for sandbox clone-if-needed
            ud = dict(context.user_data or {})
            ud["user_id"] = int(user.id) if user else 0
            tr = execute_tool(cap, params, user_id=int(user.id) if user else 0, user_data=ud)
            # write back active_repo if tool updated ud
            if context.user_data is not None and isinstance(ud.get("active_repo"), dict):
                context.user_data["active_repo"] = ud["active_repo"]
                if ud.get("last_project_path"):
                    context.user_data["last_project_path"] = ud["last_project_path"]
                try:
                    _persist_session(user, context)
                except Exception:
                    pass
            await status.edit_text((tr.message or ("تم" if tr.ok else "فشل"))[:4000])
        except Exception as e:
            logger.exception("engine-only tool failed: %s", cap)
            try:
                from lumen.bot.ui.actionable_errors import send_actionable_error
                await send_actionable_error(
                    status, kind="generic",
                    title=f"فشل تنفيذ {cap}",
                    detail=type(e).__name__,
                    user_id=int(user.id) if user else 0,
                )
            except Exception:
                await status.edit_text(f"❌ فشل تنفيذ {cap}: {type(e).__name__}")
        return

    # Non-bot, non-hard messages: short deterministic help (no AI)
    if (
        not _is_hard
        and not _is_bot_spec
        and not (context.user_data or {}).get("force_generate_once")
    ):
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
    if context.user_data is not None and context.user_data.pop("force_generate_once", False):
        _strong_bot_spec = True
        _ai_route_generate = True
        logger.info("force_generate_once honored — entering generation pipeline")
    await _clear_thinking()
    if not _ai_route_generate and not _strong_bot_spec:
        return

    if len(request) < 2:
        return

    # Clear any leftover clarification session state
    if context.user_data is not None:
        context.user_data.pop("pending_spec", None)

    # Capability Detection + feasibility (Phase 2) — honest gate before generation
    _soft_note = ""
    _detection_meta = {}
    try:
        from lumen.engine.services.capability_detection import telegram_preflight

        _pre = telegram_preflight(request)
        _rep = _pre.get("report")
        if _rep is not None:
            try:
                from lumen.engine.services.capability_detection import metadata_from_report
                _detection_meta = metadata_from_report(_rep)
            except Exception:
                _detection_meta = {}
        if _pre.get("should_block"):
            await message.reply_text(_pre.get("user_message") or rejection_message("الطلب خارج النطاق", ""))
            return
        _soft_note = _pre.get("soft_note") or ""
        if context.user_data is not None and _rep is not None:
            try:
                context.user_data["detection_preferred_keys"] = []
                context.user_data["detection_meta"] = dict(_detection_meta or {})
                context.user_data["detection_meta"]["free_agent"] = True
            except Exception:
                pass
        # Fallback: keep legacy blocked_features note if detection silent
        if not _soft_note:
            from lumen.engine.services.feasibility_gate import check_feasibility
            _feas = check_feasibility(request)
            if not _feas.can_generate:
                await message.reply_text(
                    rejection_message(_feas.reason, _feas.suggested_scope),
                )
                return
            if _feas.blocked_features:
                _soft_note = (
                    "\n⚠️ ملاحظة: بعض الأجزاء تحتاج ربط خارجي ولن تُفعَّل تلقائياً: "
                    + "، ".join(_feas.blocked_features[:4])
                )
    except Exception:
        try:
            from lumen.engine.services.feasibility_gate import check_feasibility
            _feas = check_feasibility(request)
            if not _feas.can_generate:
                await message.reply_text(
                    rejection_message(_feas.reason, _feas.suggested_scope),
                )
                return
        except Exception:
            pass

    # Duplicate identical prompt within TTL → reuse last project path
    try:
        from ..generation_cache import get_generation_cache
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
                        "run_seconds": _plan_live_seconds(user),
                    }
                    context.user_data["pending_run"] = payload
                    context.user_data["pending_deploy"] = dict(payload)
                    context.user_data["pending_live_run"] = dict(payload)
                    _persist_session(user, context)
                return
    except Exception:
        pass

    # Stage-4 + quota (extracted module)
    from .message_stages.pre_generate import prepare_status_and_quota

    status_msg = await prepare_status_and_quota(
        message=message,
        context=context,
        user=user,
        request=request,
        soft_note=locals().get("_soft_note") or "",
    )
    if status_msg is None:
        return

    # Shared generation execution (sandbox → engine → deliver)
    await execute_bot_generation(
        message=message,
        context=context,
        user=user,
        gen_request=request,
        status_msg=status_msg,
        preferred_keys=(
            context.user_data.get("preferred_keys")
            if isinstance(context.user_data, dict)
            else None
        ),
        cache_key=request,
    )
