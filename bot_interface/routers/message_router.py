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


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.message
    if not message or not message.text:
        return

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
                return
    except Exception:
        pass

    request = message.text.strip()

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
            from b2b_platform.plans import get_plan, public_plan_dict
            pd = public_plan_dict(get_plan(plan))
            extra = (
                f"\n• التوليد: {pd['generations_per_month']}/شهر"
                f"\n• الاستضافة 24/7: {pd['hosted_bots']} بوت"
                f"\n• معاينة حية: {pd['live_preview_minutes']} دقيقة"
                f"\n• المحرك: {pd['engine_tier']}"
            )
        except Exception:
            extra = ""
        await message.reply_text(
            f"👤 خطتك الحالية: {labels.get(plan, plan)}{extra}"
        )
        return

    # Phase 13: capability ops commands (health/trace/learn/promote)
    try:
        from telegram_bot_engine.services.capability_detection.ops import handle_ops_command
        _ops = handle_ops_command(request, user_id=getattr(update.effective_user, "id", None))
        if _ops:
            await message.reply_text(_ops)
            return
    except Exception:
        pass

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

    # Phase 0: Rasa dialogue bridge (opt-in). Never blocks legacy if disabled/no model.
    if not request.startswith("/"):
        try:
            from ..dialogue_bridge import dialogue_enabled, handle_dialogue
            if dialogue_enabled():
                plan_id = None
                try:
                    from b2b_platform.plan_gate import resolve_user_plan
                    plan_id = resolve_user_plan(user_id=int(user.id) if user else 0)
                except Exception:
                    plan_id = "free"
                _metadata = {}
                try:
                    from b2b_platform.metering import get_metering
                    from b2b_platform.tenants import get_tenant_store
                    _tenant = get_tenant_store().get_by_telegram(int(user.id) if user else 0)
                    _tenant_id = str(getattr(_tenant, "tenant_id", "") or getattr(_tenant, "id", "") or "")
                    if _tenant_id:
                        get_metering().record(
                            _tenant_id,
                            messages=1,
                            characters=len(request),
                            event="dialogue_message",
                        )
                    from dialogue.runtime.live_context import build_live_context
                    _metadata["live_context"] = build_live_context(
                        str(int(user.id) if user else 0),
                        fallback_plan_id=plan_id,
                    )
                except Exception:
                    logger.exception("live dialogue context unavailable")
                _dlg = await handle_dialogue(
                    request,
                    sender_id=str(int(user.id) if user else 0),
                    plan_id=plan_id,
                    metadata=_metadata,
                )
                if _dlg:
                    await message.reply_text(_dlg)
                    return
        except Exception:
            logger.exception("dialogue bridge error — continuing legacy path")

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
        from telegram_bot_engine.spec_core.language_understanding.evaluation_layer import (
            is_eval_command,
            build_performance_report,
        )
        if is_eval_command(request):
            low = request.strip().lower()
            hours = 168.0 if any(x in low for x in ("أسبوع", "اسبوع", "week", "7")) else 24.0
            rep = build_performance_report(window_hours=hours)
            text = rep.to_arabic()
            try:
                from telegram_bot_engine.spec_core.language_understanding.evaluation_layer import (
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
            loop_note = ""
            try:
                from telegram_bot_engine.spec_core.language_understanding.evaluation_layer import (
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
                    from telegram_bot_engine.spec_core.language_understanding.evaluation_layer import (
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
                    from telegram_bot_engine.spec_core.language_understanding.evaluation_layer import (
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

    # Capability Detection + feasibility (Phase 2) — honest gate before generation
    _soft_note = ""
    _detection_meta = {}
    try:
        from telegram_bot_engine.services.capability_detection import telegram_preflight

        _pre = telegram_preflight(request)
        _rep = _pre.get("report")
        if _rep is not None:
            try:
                from telegram_bot_engine.services.capability_detection import metadata_from_report
                _detection_meta = metadata_from_report(_rep)
            except Exception:
                _detection_meta = {}
        if _pre.get("should_block"):
            await message.reply_text(_pre.get("user_message") or rejection_message("الطلب خارج النطاق", ""))
            return
        _soft_note = _pre.get("soft_note") or ""
        if context.user_data is not None and _rep is not None:
            try:
                from telegram_bot_engine.services.capability_detection import feature_keys
                context.user_data["detection_preferred_keys"] = feature_keys(_rep, include_core=True)
                context.user_data["detection_meta"] = _detection_meta
            except Exception:
                pass
        # Fallback: keep legacy blocked_features note if detection silent
        if not _soft_note:
            from telegram_bot_engine.services.feasibility_gate import check_feasibility
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
            from telegram_bot_engine.services.feasibility_gate import check_feasibility
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
        from telegram_bot_engine.spec_core.language_understanding import (
            understand,
            analyze_intent,
            personalize,
            extract_entities,
        )
        from telegram_bot_engine.spec_core.language_understanding.smart_generation import (
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
        from b2b_platform.plan_gate import check_generation_quota
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
        from telegram_bot_engine.services.user_sandbox import get_user_sandbox
        uid = int(user.id) if user else 0
        work_dir = get_user_sandbox(uid, OUTPUT_DIR).new_project_dir(label="gen")
    except Exception:
        work_dir = Path(tempfile.mkdtemp(prefix="botgen_", dir=str(OUTPUT_DIR)))

    try:
        _pref_keys = None
        if context.user_data is not None:
            _pref_keys = context.user_data.get("detection_preferred_keys")
        try:
            from b2b_platform.plan_gate import filter_preferred_keys
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
                from b2b_platform.plan_gate import apply_post_generation
                apply_post_generation(
                    str(result.project_path),
                    user_id=int(user.id) if user else 0,
                )
        except Exception:
            logger.exception("post-generation plan hooks failed")

        from ..generation_flow import deliver_generation_result
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
                from ..generation_cache import get_generation_cache
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


