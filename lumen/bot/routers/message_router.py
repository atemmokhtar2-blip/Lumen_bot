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
from ..sanitize import sanitize_error
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


def _looks_like_generation_request(text: str) -> bool:
    """Explicit generate intent (verbs). Does NOT include bare bot-spec descriptions.

    Bare specs like «بوت متجر إلكتروني…» are handled by _looks_like_bot_spec and
    must flow through Gemini chat → translator → engine — not force_generate.
    """
    value = (text or "").strip().lower()
    # Strip decorative quotes/punctuation that users often paste from chat UIs.
    value = re.sub(r'["“”‘’«»٬،,]+', " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return False
    if "بوت" not in value and "bot" not in value:
        return False
    return bool(
        re.search(
            r"(?:اعمل|عايز|عاوز|أريد|ابغى|أنشئ|انشئ|ابني|صمم|ولّد|ولد|سوي|سوى|generate|create|make|build).{0,80}(?:بوت|bot)"
            r"|(?:بوت|bot).{0,80}(?:ابدأ|ابدء|نفّذ|نفذ|ولّد|ولد|start|generate|create|make|build)",
            value,
            re.IGNORECASE,
        )
    )



def _free_agent_mode() -> bool:
    """Cline is the sole generation path — always on."""
    return True




_CONFIRM_ROOTS = {
    "أكد", "اكد", "تأكيد", "موافق", "نعم", "ايوه", "أيوه", "يلا",
    "ابدأ", "ابدا", "ابدء", "نفذ", "نفّذ", "انجز", "أنجز", "ولّد", "ولد",
    "تمام", "حاضر", "ماشي", "يلاا",
    "confirm", "yes", "ok", "start", "go", "generate", "done",
}
_CONFIRM_FILLER = {"و", "اللي", "على", "كده", "كدا", "بقوة", "فورا", "دلوقتي", "الآن", "الان", "يا", "رجاء", "please", "now"}


def _is_confirm_phrase(text: str) -> bool:
    """True for short go-ahead phrases like 'تمام ابدا وانجز' / 'ابدأ' / 'ok'."""
    value = (text or "").strip().lower()
    value = re.sub(r'["“”‘’«»٬،,!.?؟]+', " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return False
    if value in _CONFIRM_ROOTS:
        return True
    tokens = re.findall(r"[\w\u0600-\u06ff]+", value)
    if not tokens or len(tokens) > 8:
        return False
    # Strip leading waw from tokens (وانجز → انجز)
    norm = []
    for t in tokens:
        if t.startswith("و") and len(t) > 2 and t[1:] in _CONFIRM_ROOTS:
            norm.append(t[1:])
        else:
            norm.append(t)
    useful = [t for t in norm if t not in _CONFIRM_FILLER]
    if not useful or len(useful) > 6:
        return False
    return all(t in _CONFIRM_ROOTS for t in useful) and any(t in _CONFIRM_ROOTS for t in useful)


def _prior_bot_request(user_data: dict | None) -> str:
    """Last generation-like user message from session history."""
    if not user_data:
        return ""
    explicit = str(user_data.get("last_bot_request") or "").strip()
    if explicit and _looks_like_generation_request(explicit):
        return explicit
    for item in reversed(list(user_data.get("chat_history") or [])):
        if not isinstance(item, dict):
            continue
        if str(item.get("role") or "") != "user":
            continue
        content = str(item.get("content") or "").strip()
        if _looks_like_generation_request(content):
            return content
    return ""


def _qwen_rescue_translation(request: str, context: dict) -> dict | None:
    """Translate an explicit bot build when Gemini chat is unavailable."""
    if not _looks_like_generation_request(request):
        return None
    try:
        from lumen.engine.services.gemini_client import validate_spec_translation
        from lumen.engine.services.translator_client import translate_request
        result = translate_request(request, {**(context or {}), "gemini_unavailable": True})
        if isinstance(result, dict) and validate_spec_translation(result):
            return result
    except Exception:
        logger.exception("Direct Qwen rescue translation failed")
    return None


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

    if not is_allowed(user.id if user else None):
        await message.reply_text("⛔ غير مصرح لك باستخدام هذا البوت.")
        return

    # Ensure user identity + plan exist in MongoDB (users collection)
    _ensure_mongo_user(user)

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
                await _clear_thinking()
                return
    except Exception:
        pass

    request = clamp_user_text(message.text.strip())
    if len((message.text or "").strip()) > MAX_USER_MESSAGE_CHARS:
        await message.reply_text(
            f"⚠️ الرسالة طويلة جداً. الحد الأقصى {MAX_USER_MESSAGE_CHARS} حرفاً."
        )
        # continue with truncated text rather than free DoS
    if not request:
        await _clear_thinking()
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
        plan = _mongo_plan_for_user(uid) or "free"
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

    # ── Bot token FIRST (no thinking bubble — deploy progress has its own status) ──
    if looks_like_bot_token(request) or looks_like_bot_token(normalize_bot_token(request)):
        try:
            from ..handlers.token_handler import try_handle_token
            if await try_handle_token(update, context, request, user, message):
                return
        except Exception:
            logger.exception("early token handler failed")

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
        context.user_data["skip_clarify_once"] = True
        context.user_data["force_generate_once"] = True
        logger.info("Generation-like request → force generate-now (skip Gemini)")

    # Free-agent mode: bare bot specs («بوت متجر…») also skip Gemini catalog chat
    # and go straight to Cline — no (cart_add)/(content_list) feature listing.
    if context.user_data is not None and _free_agent_mode() and not (
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
            context.user_data["skip_clarify_once"] = True
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
            context.user_data["skip_clarify_once"] = True
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
                    context.user_data["skip_clarify_once"] = True
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
                        context.user_data["skip_clarify_once"] = True
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
                context.user_data["skip_clarify_once"] = True
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

        preferred_keys = None
        _bridge_pkg = None
        try:
            from lumen.engine.services.translator_client import translate_request
            from lumen.engine.services.engine_groq_bridge import analyze_and_prepare
            _tr = translate_request(
                gen_request,
                {
                    "conversation_history": list((context.user_data or {}).get("chat_history") or [])[-8:],
                    "server_facts": {"project": "Lumen"},
                },
            )
            _bridge_pkg = analyze_and_prepare(gen_request, _tr if isinstance(_tr, dict) else None)
            gen_request = str(_bridge_pkg.get("spec_request") or gen_request).strip()
            preferred_keys = list(_bridge_pkg.get("preferred_keys") or []) or None
            if context.user_data is not None:
                context.user_data["last_bridge"] = {
                    "mode": _bridge_pkg.get("engine_mode"),
                    "keys": preferred_keys,
                    "model": _bridge_pkg.get("model"),
                }
            logger.info(
                "generate-now bridge mode=%s features=%s model=%s",
                _bridge_pkg.get("engine_mode"),
                preferred_keys,
                _bridge_pkg.get("model"),
            )
        except Exception:
            logger.exception("generate-now translate/bridge failed; continuing with raw request")

        if context.user_data is not None:
            context.user_data.pop("force_generate_once", None)
            context.user_data.pop("skip_clarify_once", None)
            context.user_data["translated_spec_request"] = gen_request
            if preferred_keys:
                context.user_data["translated_preferred_keys"] = preferred_keys
            context.user_data["translated_source"] = "generate_now_fastpath"

        await _clear_thinking()
        status_msg = await message.reply_text("⚙️ جاري توليد البوت الآن…")
        try:
            await context.bot.send_chat_action(
                chat_id=message.chat_id, action=ChatAction.TYPING
            )
        except Exception:
            pass

        # Durable writable workdir (Railway-safe)
        work_dir: Path | None = None
        try:
            out_root = Path(OUTPUT_DIR)
            out_root.mkdir(parents=True, exist_ok=True)
            from lumen.engine.services.user_sandbox import get_user_sandbox
            uid = int(user.id) if user else 0
            work_dir = get_user_sandbox(uid, out_root).new_project_dir(label="gen")
        except Exception as sandbox_exc:
            logger.exception("sandbox workdir failed: %s", sandbox_exc)
            fallback = Path(OUTPUT_DIR) / "fallback_gen" / f"u{int(user.id) if user else 0}"
            try:
                fallback.mkdir(parents=True, exist_ok=True)
                work_dir = Path(tempfile.mkdtemp(prefix="botgen_", dir=str(fallback)))
            except Exception:
                work_dir = Path(tempfile.mkdtemp(prefix="botgen_lumen_"))
                work_dir.mkdir(parents=True, exist_ok=True)

        try:
            try:
                from lumen.platform.plan_gate import filter_preferred_keys
                preferred_keys = filter_preferred_keys(
                    list(preferred_keys) if preferred_keys else None,
                    user_id=int(user.id) if user else 0,
                )
            except Exception:
                pass

            # Control plane: BuildIR → engine_router (infinite primary | catalog | hybrid | cline)
            try:
                from lumen.engine.services.engine_router import (
                    build_ir_from_package,
                    execute_ir,
                )
                _pkg = dict(_bridge_pkg or {})
                if preferred_keys is not None:
                    _pkg["preferred_keys"] = list(preferred_keys)
                if not _pkg.get("spec_request"):
                    _pkg["spec_request"] = gen_request
                if not _pkg.get("original_text"):
                    _pkg["original_text"] = gen_request
                # Free-agent / custom path: infinite atomic engine (not cline)
                if _free_agent_mode() or (context.user_data or {}).get("free_agent_path"):
                    _pkg["engine_mode"] = "infinite"
                    _pkg["needs_ai_codegen"] = True
                    _pkg["looks_custom"] = True
                    _pkg["preferred_keys"] = list(_pkg.get("preferred_keys") or [])
                    gaps = list(_pkg.get("capabilities_gap") or [])
                    if "free_agent" not in gaps:
                        gaps.append("free_agent")
                    _pkg["capabilities_gap"] = gaps
                    logger.info("Free-agent IR forced: engine_mode=infinite")
                # Always prefer infinite as product default unless package already set
                if not _pkg.get("engine_mode"):
                    _pkg["engine_mode"] = "infinite"
                if not _pkg.get("engine") and _pkg.get("engine_mode") == "infinite":
                    _pkg["engine"] = "infinite_v1"
                ir = build_ir_from_package(_pkg, user_id=int(user.id) if user else 0)
                logger.info(
                    "force_generate IR mode=%s matched=%s gap=%s",
                    ir.engine_mode.value,
                    ir.capabilities_matched,
                    ir.capabilities_gap,
                )
                result = await run_with_heartbeat(
                    execute_ir,
                    ir,
                    work_dir,
                    status_msg=status_msg,
                    user_id=int(user.id) if user else 0,
                )
            except Exception:
                logger.exception("IR router failed; falling back to run_generation")
                result = await run_with_heartbeat(
                    run_generation,
                    gen_request,
                    work_dir,
                    int(user.id) if user else 0,
                    status_msg=status_msg,
                    preferred_keys=preferred_keys,
                )
            if result is None:
                await safe_edit_text(status_msg, "❌ فشل التوليد (نتيجة فارغة).")
                return

            success = bool(getattr(result, "success", False))
            project_path = getattr(result, "project_path", None)
            errors = list(getattr(result, "errors", None) or [])

            if not success or not project_path:
                err_bits = ", ".join(str(e)[:80] for e in errors[:4]) or "unknown"
                await safe_edit_text(
                    status_msg,
                    f"❌ فشل التوليد: {escape_md(err_bits)[:300]}",
                )
                return

            proj = Path(str(project_path))
            if not proj.is_dir():
                await safe_edit_text(
                    status_msg,
                    "❌ التوليد انتهى بدون مجلد مشروع. أعد المحاولة.",
                )
                return

            # Best-effort post hooks (must not block zip delivery)
            try:
                from lumen.platform.plan_gate import apply_post_generation
                apply_post_generation(str(proj), user_id=int(user.id) if user else 0)
            except Exception:
                logger.exception("post-generation plan hooks failed")

            try:
                from ..generation_flow import deliver_generation_result
                await deliver_generation_result(
                    message=message,
                    status_msg=status_msg,
                    context=context,
                    user=user,
                    request=gen_request,
                    result=result,
                )
            except Exception:
                logger.exception("deliver_generation_result failed; gated zip fallback")
                # Root: never ship untested ZIP. Smoke must pass before any fallback send.
                try:
                    from lumen.bot.generation_steps.helpers import _smoke_test_project
                    smoke_ok, smoke_msg = _smoke_test_project(proj, seconds=8.0)
                except Exception as _sm_exc:
                    smoke_ok, smoke_msg = False, f"smoke_error:{type(_sm_exc).__name__}"
                if not smoke_ok:
                    await message.reply_text(
                        "❌ التسليم الآمن فشل — لم يُرسل ZIP.\n"
                        f"السبب: `{escape_md(str(smoke_msg)[:250])}`"
                    )
                else:
                    zip_path = make_zip_from_path(proj)
                    if zip_path and Path(zip_path).is_file():
                        try:
                            await status_msg.edit_text("✅ تم التوليد — جاري إرسال الملف…")
                        except Exception:
                            pass
                        try:
                            with open(zip_path, "rb") as fh:
                                await message.reply_document(
                                    document=fh,
                                    filename=Path(zip_path).name,
                                    caption="📦 مشروع البوت (ZIP). فك الضغط واتبع README.",
                                )
                        except Exception:
                            logger.exception("zip upload failed")
                            await message.reply_text(
                                f"✅ المشروع جاهز على السيرفر لكن رفع ZIP فشل.\nالمسار: `{escape_md(str(proj))}`"
                            )
                    else:
                        await message.reply_text(
                            f"✅ المشروع اتولد.\nالمسار: `{escape_md(str(proj))}`\n"
                            "تعذر إنشاء ZIP — راجع السجلات."
                        )

            try:
                if success and project_path:
                    from ..generation_cache import get_generation_cache
                    get_generation_cache().put(
                        int(user.id) if user else 0,
                        gen_request,
                        {"project_path": str(project_path), "entry_point": "main.py"},
                    )
                _persist_session(user, context)
            except Exception:
                pass
        except FileNotFoundError as e:
            logger.exception("generate-now FileNotFoundError")
            missing = getattr(e, "filename", None) or (e.args[0] if e.args else "")
            await safe_edit_text(
                status_msg,
                f"❌ ملف/مجلد مفقود أثناء التوليد.\n`{escape_md(str(missing)[:200])}`\n"
                "تأكد أن OUTPUT_DIR قابل للكتابة على السيرفر.",
            )
        except Exception as e:
            logger.exception("generate-now path failed")
            err_text = escape_md(sanitize_error(str(e), max_len=400))
            await safe_edit_text(
                status_msg,
                f"❌ حدث خطأ أثناء التوليد:\n`{err_text}`",
                use_markdown=True,
            )
        return

    # ── EARLY: bound active_repo → engine tools + answer (skip Gemini fluff) ──
    # NEVER intercept bot generation/specs here — those must reach:
    #   Gemini (understand) → translator (spec_core contract) → engine
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
        logger.info("Skipping chat layer; force_generate_once active free_agent=%s", _free_agent_mode())
        if _free_agent_mode():
            # Keep raw user text — do not map to catalog capability keys.
            if context.user_data is not None:
                context.user_data["translated_spec_request"] = request
                context.user_data["translated_preferred_keys"] = []
                context.user_data["last_bridge"] = {
                    "mode": "cline",
                    "keys": [],
                    "needs_ai_codegen": True,
                    "looks_custom": True,
                }
                context.user_data["free_agent_path"] = True
            # Fall through without Gemini translate / catalog bridge.
            pass
        else:
            try:
                from lumen.engine.services.translator_client import translate_request
                _hist = []
                if context.user_data is not None:
                    _hist = list(context.user_data.get("chat_history") or [])[-8:]
                _tr = translate_request(
                    request,
                    {"conversation_history": _hist, "server_facts": {"project": "Lumen"}},
                )
                if isinstance(_tr, dict) and str(_tr.get("spec_request") or "").strip():
                    request = str(_tr.get("spec_request")).strip()
                    if context.user_data is not None:
                        context.user_data["translated_spec_request"] = request
                        try:
                            from lumen.engine.services.engine_groq_bridge import analyze_and_prepare
                            _pkg = analyze_and_prepare(request, _tr)
                            context.user_data["translated_preferred_keys"] = list(_pkg.get("preferred_keys") or [])
                            context.user_data["last_bridge"] = {"mode": _pkg.get("engine_mode"), "keys": _pkg.get("preferred_keys")}
                        except Exception:
                            context.user_data["translated_preferred_keys"] = [
                                str(x) for x in (_tr.get("features_requested") or []) if str(x).strip()
                            ]
                        context.user_data["translated_source"] = "groq_confirm_fastpath"
                        context.user_data["skip_clarify_once"] = True
                    logger.info(
                        "Confirm fast-path Groq translation features=%s",
                        _tr.get("features_requested"),
                    )
                else:
                    logger.warning("Confirm fast-path: Groq returned no spec; using raw request")
            except Exception:
                logger.exception("Confirm fast-path Groq failed; continuing with raw request")
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

        # Two-stage understanding pipeline:
        # Gemini understands the user and produces a structured intent;
        # Qwen translates that intent into the validated spec_core contract.
        # If Gemini is unavailable for an explicit build request, Qwen is the
        # direct translation rescue path; ordinary chat never uses Qwen.
        _direct_qwen_translation = None
        if not isinstance(chat_result, dict):
            _direct_qwen_translation = _qwen_rescue_translation(request, chat_context)
            if _direct_qwen_translation:
                logger.info("Direct Qwen rescue translation validated after Gemini failure")

        _translated_generation_request = ""
        _translated_preferred_keys = []
        _translation_source = ""
        if isinstance(_direct_qwen_translation, dict):
            _translated_generation_request = str(
                _direct_qwen_translation.get("spec_request") or ""
            ).strip()
            _translated_preferred_keys = [
                str(key).strip()
                for key in (_direct_qwen_translation.get("features_requested") or [])
                if str(key).strip()
            ]
            _translation_source = "qwen_direct_after_gemini_failure"
        elif isinstance(chat_result, dict):
            try:
                from lumen.engine.services.gemini_client import validate_spec_translation
                from lumen.engine.services.translator_client import translate_request
                _translation = chat_result.get("translation")
                _action = chat_result.get("action") if isinstance(chat_result.get("action"), dict) else {}
                if (
                    str(_action.get("name") or "") in {"generate_bot", "refine_bot"}
                    and isinstance(_translation, dict)
                    and validate_spec_translation(_translation)
                ):
                    _gemini_keys = [
                        str(key).strip()
                        for key in (_translation.get("features_requested") or [])
                        if str(key).strip()
                    ]
                    _gemini_understanding = {
                        "purpose": str(_translation.get("purpose") or ""),
                        "features_requested": _gemini_keys,
                        "flows": [
                            str(flow).strip()
                            for flow in (_translation.get("flows") or [])
                            if str(flow).strip()
                        ],
                        "strict_spec": bool(_translation.get("strict_spec")),
                        "confidence": float(_translation.get("confidence") or 0.0),
                        "spec_request": str(_translation.get("spec_request") or ""),
                        "source": "gemini",
                    }
                    _qwen_context = dict(chat_context)
                    _qwen_context["server_facts"] = dict(live_context or {})
                    _qwen_context["server_facts"]["gemini_understanding"] = _gemini_understanding
                    _qwen_context["gemini_understanding"] = _gemini_understanding
                    _qwen_translation = translate_request(request, _qwen_context)
                    if isinstance(_qwen_translation, dict):
                        _translated_generation_request = str(
                            _qwen_translation.get("spec_request") or ""
                        ).strip()
                        _translated_preferred_keys = [
                            str(key).strip()
                            for key in (_qwen_translation.get("features_requested") or [])
                            if str(key).strip()
                        ]
                        _translation_source = "qwen_after_gemini"
                        logger.info(
                            "Gemini understanding handed off to Qwen: features=%s",
                            _translated_preferred_keys,
                        )
                    else:
                        # Qwen is an enhancement, not a reason to block a valid
                        # Gemini contract; keep the deterministic path available.
                        _translated_generation_request = str(
                            _translation.get("spec_request") or ""
                        ).strip()
                        _translated_preferred_keys = _gemini_keys
                        _translation_source = "gemini_fallback_qwen_unavailable"
                        logger.warning("Qwen handoff unavailable; using validated Gemini contract")
            except Exception:
                logger.exception("Gemini-to-Qwen-to-spec_core handoff failed")

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
                                from lumen.engine.spec_core.command_map import feature_for_command
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
                context.user_data["skip_clarify_once"] = True
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
            # Ensure we generate the original bot request, not the confirm phrase.
            prior = _prior_bot_request(context.user_data if context.user_data is not None else None)
            gen_src = prior if prior else (request if _looks_like_generation_request(request) else "")
            if gen_src:
                try:
                    from lumen.engine.services.translator_client import translate_request
                    _tr = translate_request(gen_src, chat_context)
                    if isinstance(_tr, dict) and str(_tr.get("spec_request") or "").strip():
                        request = str(_tr.get("spec_request")).strip()
                        if context.user_data is not None:
                            context.user_data["translated_spec_request"] = request
                            try:
                                from lumen.engine.services.engine_groq_bridge import analyze_and_prepare
                                _pkg = analyze_and_prepare(request, _tr)
                                context.user_data["translated_preferred_keys"] = list(_pkg.get("preferred_keys") or [])
                                context.user_data["last_bridge"] = {
                                    "mode": _pkg.get("engine_mode"),
                                    "keys": _pkg.get("preferred_keys"),
                                }
                            except Exception:
                                context.user_data["translated_preferred_keys"] = list(
                                    _tr.get("features_requested") or []
                                )
                            context.user_data["translated_source"] = "groq_on_force_generate"
                            context.user_data["skip_clarify_once"] = True
                        _translated_generation_request = request
                        logger.info(
                            "Force-generate via Groq translation features=%s",
                            _tr.get("features_requested"),
                        )
                    else:
                        request = gen_src
                        if context.user_data is not None:
                            context.user_data["skip_clarify_once"] = True
                        _translated_generation_request = gen_src
                        logger.warning("Force-generate without Groq; using raw prior request")
                except Exception:
                    logger.exception("Force-generate Groq translation failed")
                    request = gen_src
                    _translated_generation_request = gen_src

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
                        context.user_data["skip_clarify_once"] = True
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
            snap = {
                "enabled": False,
                "key_present": bool(
                    (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
                ),
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
            await message.reply_text('طبقة المحادثة غير مفعّلة: مفتاح Gemini غير موجود على السيرفر.\nأضف GEMINI_API_KEY (أو GOOGLE_API_KEY) في Variables في Railway ثم أعد التشغيل.')
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

    # ── Stage-5: performance / eval report ───────────────────────────────
    try:
        from lumen.engine.spec_core.language_understanding.evaluation_layer import (
            is_eval_command,
            build_performance_report,
        )
        if is_eval_command(request):
            low = request.strip().lower()
            hours = 168.0 if any(x in low for x in ("أسبوع", "اسبوع", "week", "7")) else 24.0
            rep = build_performance_report(window_hours=hours)
            text = rep.to_arabic()
            try:
                from lumen.engine.spec_core.language_understanding.evaluation_layer import (
                    assign_ab_variant,
                    recommend_generation_tweaks,
                )
                extra = []
                if uid:
                    ab = assign_ab_variant(int(uid))
                    extra.append(f"• متغيرك A/B: {ab.variant}")
                tw = recommend_generation_tweaks(int(uid) if uid else None)
                if tw.get("prefer_features"):
                    extra.append("• ميزات مُفضّلة عالميًا: " + ", ".join(tw["prefer_features"][:5]))
                if tw.get("avoid_features"):
                    extra.append("• ميزات ضعيفة: " + ", ".join(tw["avoid_features"][:4]))
                if extra:
                    text += "\n" + "\n".join(extra)
                    text = text.replace("\\n", "\n")
                    # actual newlines:
                    text = rep.to_arabic() + chr(10) + chr(10).join(extra)
            except Exception:
                pass
            await message.reply_text(text[:3500])
            return
    except Exception:
        logger.exception("stage5 eval report failed")

    # ── Stage-3: continuous learning from feedback ───────────────────────
    try:
        from lumen.engine.spec_core.language_understanding.continuous_learning import (
            is_feedback_only,
            learn_from_feedback_message,
            detect_outcome,
        )
        if uid and is_feedback_only(request):
            from lumen.engine.spec_core.language_understanding.memory_engine import get_memory_engine as _gme
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
            loop_note = ""
            try:
                from lumen.engine.spec_core.language_understanding.evaluation_layer import (
                    apply_eval_to_features,
                    user_feature_stats,
                )
                ust = user_feature_stats(int(uid))
                _feats, meta5 = apply_eval_to_features(
                    list((last or {}).get("features") or []) if isinstance((last or {}).get("features"), list) else [],
                    int(uid),
                    strict=False,
                )
                if meta5.get("dropped"):
                    loop_note += "\n⏭️ التوليد الجاي هيتجنب: " + ", ".join(meta5["dropped"][:5])
                if meta5.get("prefer"):
                    loop_note += "\n⭐ هيتفضّل: " + ", ".join(list(meta5["prefer"])[:5])
                loop_note += f"\n📊 نجاح بوتاتك: {float(ust.get('success_rate') or 0)*100:.0f}% ({ust.get('bots')} بوت)"
            except Exception:
                pass
            if sig.kind == "positive" or sig.kind == "complete":
                loop_lines = []
                try:
                    from lumen.engine.spec_core.language_understanding.evaluation_layer import (
                        user_feature_stats,
                        recommend_generation_tweaks,
                    )
                    ust = user_feature_stats(int(uid))
                    tw = recommend_generation_tweaks(int(uid))
                    loop_lines.append(
                        f"📊 نجاح بوتاتك: {float(ust.get('success_rate') or 0)*100:.0f}% ({ust.get('bots')} بوت)"
                    )
                    if tw.get("prefer_features"):
                        loop_lines.append("⭐ مُفضّل: " + ", ".join(tw["prefer_features"][:4]))
                except Exception:
                    pass
                msg = (
                    f"شكرًا ✅ (+{sig.score_delta})" + chr(10)
                    + f"اتقوّت وصفة «{bot_name}» ({n_feats} ميزة) للتوليدات الجاية."
                )
                if loop_lines:
                    msg += chr(10) + chr(10).join(loop_lines)
                await message.reply_text(msg)
            elif sig.kind == "negative":
                loop_lines = []
                try:
                    from lumen.engine.spec_core.language_understanding.evaluation_layer import (
                        user_feature_stats,
                        recommend_generation_tweaks,
                    )
                    ust = user_feature_stats(int(uid))
                    tw = recommend_generation_tweaks(int(uid))
                    loop_lines.append(
                        f"📊 نجاح بوتاتك: {float(ust.get('success_rate') or 0)*100:.0f}% ({ust.get('bots')} بوت)"
                    )
                    if tw.get("avoid_features"):
                        loop_lines.append("⏭️ الجاي هيتجنب: " + ", ".join(tw["avoid_features"][:4]))
                except Exception:
                    pass
                msg = (
                    f"تم 📝 ({sig.score_delta})" + chr(10)
                    + f"ميزات «{bot_name}» هتتضعف في المرات الجاية."
                )
                if loop_lines:
                    msg += chr(10) + chr(10).join(loop_lines)
                await message.reply_text(msg)
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
            await status.edit_text(f"❌ فشل تنفيذ {cap}: {type(e).__name__}")
        return

    # Non-bot, non-hard messages: short deterministic help (no AI)
    # Exception: just finished L3 clarify → always continue to generate
    if (
        not _is_hard
        and not _is_bot_spec
        and not _clarify_done
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
    # After L3 answers/skip → force generate with enriched request
    if _clarify_done:
        _strong_bot_spec = True
        _ai_route_generate = True
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
                from lumen.engine.services.capability_detection import feature_keys
                if _free_agent_mode():
                    context.user_data["detection_preferred_keys"] = []
                    context.user_data["detection_meta"] = dict(_detection_meta or {})
                    context.user_data["detection_meta"]["free_agent"] = True
                else:
                    context.user_data["detection_preferred_keys"] = feature_keys(_rep, include_core=True)
                    context.user_data["detection_meta"] = _detection_meta
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

    # ── L3: ask adaptive questions before thin specs (e.g. «بوت متجر») ──
    # Skip if we just finished a clarify session this turn (prevents infinite loop)
    _skip_l3 = False
    if context.user_data is not None:
        _skip_l3 = bool(context.user_data.pop("skip_clarify_once", False)) or _clarify_done
    if not _skip_l3:
        try:
            from lumen.engine.spec_core.language_understanding import (
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

    # Stage-4: personalized status line
    _status_line = "⏳ جاري توليد المشروع (مسار حتمي) ثم التحقق ضد الهلوسة..."
    try:
        from lumen.engine.spec_core.language_understanding import (
            understand,
            analyze_intent,
            personalize,
            extract_entities,
        )
        from lumen.engine.spec_core.language_understanding.smart_generation import (
            build_narrative,
        )
        _lu4 = understand(request)
        _intent4 = analyze_intent(request, lu=_lu4)
        _style4 = personalize(
            request, intent=_intent4, lu=_lu4, user_id=int(user.id) if user else None
        )
        _ent4 = getattr(_lu4, "entities", None)
        _nav4 = build_narrative(
            request,
            style=_style4,
            entities=_ent4,
            intent_name=_intent4.primary.intent if _intent4 and _intent4.primary else None,
            features=list(getattr(_ent4, "features_requested", None) or []),
            strict=bool(getattr(_ent4, "strict_spec", False)) if _ent4 else False,
            bot_name=getattr(_ent4, "bot_name", None) if _ent4 else None,
        )
        if _nav4.pre_summary:
            await message.reply_text(_nav4.pre_summary[:1500])
        _status_line = (_nav4.status_start or _status_line) + (_soft_note or "")
    except Exception:
        logger.exception("stage4 pre-summary failed")
        _status_line = _status_line + (_soft_note or "")
    status_msg = await message.reply_text(_status_line)
    await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)

    # Server-side plan quota (Explorer 25 / Starter 50 / Growth 300 per month)
    try:
        from lumen.platform.plan_gate import check_generation_quota
        _q_ok, _q_reason, _q_info = check_generation_quota(user_id=int(user.id) if user else 0)
        if not _q_ok:
            limit = _q_info.get("limit") or "?"
            plan_id = _q_info.get("plan_id") or "free"
            await status_msg.edit_text(
                f"⛔ وصلت للحد الشهري للتوليد على خطة `{plan_id}` "
                f"({limit} توليد/شهر).\n"
                "رقِّ خطتك: /plan — المبادر $8 أو النمو $30."
            )
            return
    except Exception:
        logger.exception("plan quota check failed")

    # Isolated per-user workspace (never share host bot dir/token space)
    try:
        out_root = Path(OUTPUT_DIR)
        out_root.mkdir(parents=True, exist_ok=True)
        from lumen.engine.services.user_sandbox import get_user_sandbox
        uid = int(user.id) if user else 0
        work_dir = get_user_sandbox(uid, out_root).new_project_dir(label="gen")
    except Exception as _wd_exc:
        logger.exception("workdir sandbox failed: %s", _wd_exc)
        try:
            out_root = Path(OUTPUT_DIR)
            out_root.mkdir(parents=True, exist_ok=True)
            work_dir = Path(tempfile.mkdtemp(prefix="botgen_", dir=str(out_root)))
        except Exception:
            work_dir = Path(tempfile.mkdtemp(prefix="botgen_lumen_"))

    try:
        _pref_keys = None
        if context.user_data is not None:
            _pref_keys = context.user_data.get("translated_preferred_keys")
            if not _pref_keys:
                _pref_keys = context.user_data.get("detection_preferred_keys")
        try:
            from lumen.platform.plan_gate import filter_preferred_keys
            _pref_keys = filter_preferred_keys(
                list(_pref_keys) if _pref_keys else None,
                user_id=int(user.id) if user else 0,
            )
        except Exception:
            pass
        result = await run_with_heartbeat(
            run_generation,
            request,
            work_dir,
            int(user.id) if user else 0,
            status_msg=status_msg,
            preferred_keys=_pref_keys,
        )

        if result is None:
            await status_msg.edit_text("❌ فشل التوليد (نتيجة فارغة).")
            return

        # Explorer watermark + plan post-process (server-side, cannot be skipped by client)
        try:
            if result and getattr(result, "success", False) and getattr(result, "project_path", None):
                from lumen.platform.plan_gate import apply_post_generation
                apply_post_generation(
                    str(result.project_path),
                    user_id=int(user.id) if user else 0,
                )
        except Exception:
            logger.exception("post-generation plan hooks failed")

        try:
            from ..generation_flow import deliver_generation_result
            await deliver_generation_result(
                message=message,
                status_msg=status_msg,
                context=context,
                user=user,
                request=request,
                result=result,
            )
        except Exception:
            logger.exception("deliver_generation_result failed; gated zip fallback")
            proj = Path(str(getattr(result, "project_path", "") or ""))
            if not proj.is_dir():
                raise
            try:
                from lumen.bot.generation_steps.helpers import _smoke_test_project
                smoke_ok, smoke_msg = _smoke_test_project(proj, seconds=8.0)
            except Exception as _sm_exc:
                smoke_ok, smoke_msg = False, f"smoke_error:{type(_sm_exc).__name__}"
            if not smoke_ok:
                await message.reply_text(
                    "❌ التسليم الآمن فشل — لم يُرسل ZIP.\n"
                    f"السبب: `{escape_md(str(smoke_msg)[:250])}`"
                )
            else:
                zip_path = make_zip_from_path(proj)
                if zip_path and Path(zip_path).is_file():
                    try:
                        await status_msg.edit_text("✅ تم التوليد — جاري إرسال الملف…")
                    except Exception:
                        pass
                    try:
                        with open(zip_path, "rb") as fh:
                            await message.reply_document(
                                document=fh,
                                filename=Path(zip_path).name,
                                caption="📦 مشروع البوت (ZIP)",
                            )
                    except Exception:
                        logger.exception("zip upload failed")
                        await message.reply_text(f"✅ المشروع جاهز: `{escape_md(str(proj))}`")
                else:
                    await message.reply_text(f"✅ المشروع جاهز: `{escape_md(str(proj))}`")
        try:
            if result and getattr(result, "success", False) and getattr(result, "project_path", None):
                from ..generation_cache import get_generation_cache
                get_generation_cache().put(
                    int(user.id) if user else 0,
                    request,
                    {
                        "project_path": str(result.project_path),
                        "entry_point": "main.py",
                    },
                )
                if context.user_data is not None:
                    context.user_data["last_project_path"] = str(result.project_path)
                    context.user_data["active_bot_path"] = str(result.project_path)
                try:
                    from lumen.engine.services.chat_memory import get_chat_memory
                    if user:
                        get_chat_memory().set_facts(
                            int(user.id),
                            last_project_path=str(result.project_path),
                            last_bot_request=(request or "")[:500],
                        )
                except Exception:
                    logger.exception("chat_memory project fact failed")
            _persist_session(user, context)
        except Exception:
            pass

    except FileNotFoundError as e:
        logger.exception("Generation FileNotFoundError")
        missing = getattr(e, "filename", None) or (e.args[0] if e.args else str(e))
        # Last-chance: create OUTPUT_DIR and tell user to retry once
        try:
            Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        await safe_edit_text(
            status_msg,
            f"❌ مجلد/ملف مفقود أثناء التوليد.\n`{escape_md(str(missing)[:180])}`\n"
            "أعد المحاولة مرة واحدة بعد ثوانٍ.",
        )
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


