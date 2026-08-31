"""Main text message handler for the Telegram bot interface."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from ..config import OUTPUT_DIR, logger
from ..resource_limits import (
    clamp_user_text,
    clamp_spec_request,
    MAX_USER_MESSAGE_CHARS,
)
from ..helpers import (
    escape_md,
    safe_edit_text,
)
from ..session_store import get_session_store
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

    # Hydrate durable session BEFORE any UI/flow logic (Redis is source of truth).
    # Must run before Engine UI slots so phase/state survive restart & multi-worker.
    try:
        if user and context.user_data is not None:
            get_session_store().hydrate(int(user.id), context.user_data)
    except Exception:
        logger.exception("session hydrate failed")

    # Busy guard: do not start parallel work while generation is running
    try:
        from lumen.bot.progress_tracker import is_generation_busy
        if user and is_generation_busy(int(user.id)):
            low = (request or "").strip().lower()
            if low not in {"/cancel", "cancel", "إلغاء", "الغاء", "الغي", "stop", "/stop"}:
                await message.reply_text(
                    "⏳ البوت لسه بيولّد مشروعك دلوقتي.\n"
                    "هتشوف تحديثات حية للأدوات في رسالة الحالة.\n"
                    "للإلغاء: اكتب إلغاء أو /cancel"
                )
                return
    except Exception:
        logger.exception("busy guard failed")

    # Always write-through durable keys at the end of this update (PTB interval is not enough).
    try:
        await _handle_message_body(
            update=update,
            context=context,
            user=user,
            message=message,
            request=request,
            _show_thinking=_show_thinking,
            _clear_thinking=_clear_thinking,
        )
    finally:
        try:
            if user and context.user_data is not None:
                from lumen.bot.ui.state_store import persist_ui_session
                persist_ui_session(int(user.id), dict(context.user_data))
        except Exception:
            logger.exception("final session persist failed")


async def _handle_message_body(
    *,
    update,
    context,
    user,
    message,
    request: str,
    _show_thinking,
    _clear_thinking,
) -> None:
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
        # Subscription plans removed — credits-only.
        extra = "\n• الفوترة: رصيد (credits) فقط — لا توجد خطط اشتراك."
        try:
            from lumen.platform.credits import get_credit_service
            from lumen.platform.tenants import get_tenant_store
            # best-effort balance hint
            bal = None
            for t in get_tenant_store().list_all():
                if int(getattr(t, "owner_telegram_id", 0) or 0) == int(getattr(message.from_user, "id", 0) or 0):
                    w = get_credit_service().get_wallet(t.tenant_id)
                    bal = int(getattr(w, "current_balance", 0) or 0)
                    break
            if bal is not None:
                extra += f"\n• رصيدك: {bal}"
        except Exception:
            pass
        await _clear_thinking()
        await message.reply_text(
            f"👤 الحساب: نظام الرصيد (بدون خطط){extra}"
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

    # Bot token FIRST
    if await try_bot_token(message=message, context=context, user=user, request=request):
        return

    # Thinking indicator only for normal chat / generation (not tokens)
    await _show_thinking()

    if not request:
        await _clear_thinking()
        await message.reply_text("اكتب وصفاً للبوت أو /help.")
        return

    # Remember last bot-build text for confirm resumes (agents still own the turn)
    if context.user_data is not None and _looks_like_generation_request(request):
        context.user_data["last_bot_request"] = request

    # Confirm phrase without a full spec → resume prior bot request into this turn
    _confirm_now = _is_confirm_phrase(request)
    if _confirm_now and not _looks_like_generation_request(request):
        prior = _prior_bot_request(context.user_data if context.user_data is not None else None)
        if prior:
            request = prior
            if context.user_data is not None:
                context.user_data["last_bot_request"] = prior
            logger.info("Confirm phrase resumed prior bot request into engine_turn")

    # Drop legacy standalone-chat pending actions (never set by agents path)
    if context.user_data is not None:
        context.user_data.pop("pending_chat_action", None)
        context.user_data.pop("force_generate_once", None)

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
        from lumen.infrastructure.ai import handle_user_turn
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
