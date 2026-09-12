"""Direct callback actions: repo sections, tokens, host restart."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("lumen.bot.ui.callbacks.direct_actions")


async def handle_direct_actions(
    *,
    action_id: str,
    arg: str,
    update: Any,
    context: Any,
    q: Any,
    user_data: dict,
    uid: int,
    msg: Any,
    state: Any,
) -> bool:
    """Return True if the action was fully handled."""
    # ── Direct engine-bound actions (not phase transitions) ──────────
    if action_id == "repo_sec":
        from lumen.bot.ui.repo_sections import get_section, get_section_rich, section_keyboard

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
                        return True
            except Exception:
                logger.exception("repo_sec rich render failed key=%s — plain fallback", sec_key)
        body = get_section(user_data, sec_key)
        await _safe_render_ui(q, msg, body, markup, user_data=user_data, context=context)
        return True
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
        return True
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
        return True
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
                        return True
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
        return True
    return False
