"""Shared bot-generation execution for the Telegram message router.

Owns: sandbox workdir → run_generation (heartbeat) → deliver / fail UX.
Both the force-generate fast path and the main pipeline call into this module.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from telegram.constants import ChatAction

from ..config import OUTPUT_DIR, logger
from ..sanitize import user_facing_generation_error
from ..helpers import safe_edit_text, make_zip_from_path, run_generation, escape_md
from ..progress_tracker import run_with_heartbeat
from ..middlewares.mongo_sync import persist_session as _persist_session

log = logging.getLogger("lumen_bot.routers.message_generation")


async def allocate_generation_workdir(*, user_id: int, status_msg) -> Path | None:
    """Create an isolated per-user project dir. Returns None if impossible."""
    try:
        out_root = Path(OUTPUT_DIR)
        out_root.mkdir(parents=True, exist_ok=True)
        from lumen.engine.services.user_sandbox import get_user_sandbox

        return get_user_sandbox(int(user_id or 0), out_root).new_project_dir(label="gen")
    except Exception as sandbox_exc:
        logger.exception("sandbox workdir failed: %s", sandbox_exc)
        try:
            from lumen.engine.services.user_sandbox import allocate_fallback_workdir

            return allocate_fallback_workdir(int(user_id or 0))
        except Exception as fb_exc:
            logger.exception("fallback workdir failed: %s", fb_exc)
            if status_msg is not None:
                await safe_edit_text(
                    status_msg,
                    user_facing_generation_error(code="sandbox_unavailable"),
                )
            return None


async def execute_bot_generation(
    *,
    message,
    context,
    user,
    gen_request: str,
    status_msg,
    preferred_keys: list | None = None,
    cache_key: str | None = None,
) -> Any:
    """Run engine generation and deliver result. Never raises to caller for engine errors.

    Returns the GenerationResult (or None on empty/hard failure after UX update).
    """
    gen_request = (gen_request or "").strip()
    if not gen_request:
        await safe_edit_text(status_msg, "لا يوجد وصف للتوليد.")
        return None

    uid = int(user.id) if user else 0
    work_dir = await allocate_generation_workdir(user_id=uid, status_msg=status_msg)
    if work_dir is None:
        return None

    try:
        await context.bot.send_chat_action(
            chat_id=message.chat_id, action=ChatAction.TYPING
        )
    except Exception:
        pass

    try:
        result = await run_with_heartbeat(
            run_generation,
            gen_request,
            work_dir,
            uid,
            status_msg=status_msg,
            user_id=int(uid or 0),
            context=context,
            preferred_keys=preferred_keys,
        )
        if result is None:
            try:
                from lumen.bot.ui.actionable_errors import send_actionable_error
                await send_actionable_error(status_msg, kind="generic", title="فشل التوليد", detail="نتيجة فارغة", user_id=int(uid or 0) if "uid" in dir() else 0)
            except Exception:
                await safe_edit_text(status_msg, "❌ فشل التوليد (نتيجة فارغة).")
            return None

        # Weakness #3 fix: if the multi-agent path failed and the Cline fallback
        # was used, notify the user so it doesn't look like the system is "stuck".
        try:
            _meta = getattr(result, "metadata", None) or {}
            if _meta.get("fallback_used") == "cline":
                await message.reply_text(
                    "⚙️ المسار المتقدم (multi-agent) غير متاح حالياً — "
                    "جاري التوليد بالمسار المباشر (Cline). النتيجة ستكون جاهزة قريباً."
                )
        except Exception:
            pass

        # LangGraph HITL: park confirm token + surface plan approval
        try:
            meta = getattr(result, "metadata", None) or {}
            if meta.get("awaiting_hitl") or meta.get("langgraph_interrupt"):
                from ..multi_agent_bridge import remember_hitl_pending

                class _St:
                    pass

                st = _St()
                st.state_id = meta.get("state_id")
                st.extensions = {
                    "pending_action": {
                        "action_id": meta.get("pending_action_id"),
                        "state_id": meta.get("state_id"),
                        "tool": "langgraph_plan_approve",
                        "confirm_token": meta.get("confirm_token"),
                    },
                    "langgraph_interrupt": True,
                    "langgraph_thread_id": meta.get("langgraph_thread_id"),
                    "hitl_status": "awaiting_approval",
                }
                remember_hitl_pending(context.user_data, st)
                # Hydrate token/action_id from durable board if metadata was incomplete
                try:
                    from lumen.engine.services.multi_agent import get_blackboard
                    sid = str(meta.get("state_id") or "")
                    if sid and isinstance(context.user_data, dict):
                        st_live = get_blackboard().get(sid)
                        if st_live is not None:
                            bp = (getattr(st_live, "extensions", None) or {}).get("pending_action") or {}
                            if isinstance(bp, dict) and bp.get("confirm_token"):
                                pend = dict(context.user_data.get("multi_agent_pending") or {})
                                pend.update({
                                    "action_id": bp.get("action_id") or pend.get("action_id"),
                                    "state_id": sid,
                                    "confirm_token": bp.get("confirm_token"),
                                    "tool": bp.get("tool") or pend.get("tool") or "langgraph_plan_approve",
                                })
                                context.user_data["multi_agent_pending"] = pend
                                context.user_data["multi_agent_state_id"] = sid
                except Exception:
                    logger.exception("HITL token hydrate failed")
                from ..multi_agent_bridge import format_hitl_user_message, build_hitl_keyboard

                class _MsgState:
                    user_text = gen_request
                    extensions = st.extensions

                clean = format_hitl_user_message(_MsgState())
                # Prefer engine final_message only if short and not token-dump
                raw = (meta.get("final_message") or "").strip()
                if raw and "تأكيد " not in raw and len(raw) < 500:
                    clean = raw
                kb = build_hitl_keyboard(user_id=int(uid or 0))
                try:
                    await status_msg.edit_text(
                        clean[:4000],
                        reply_markup=kb,
                        parse_mode="Markdown",
                    )
                except Exception:
                    await safe_edit_text(status_msg, clean, use_markdown=False, reply_markup=kb)
                return result
        except Exception:
            logger.exception("langgraph HITL surface failed")

        success = bool(getattr(result, "success", False))
        project_path = getattr(result, "project_path", None)
        errors = list(getattr(result, "errors", None) or [])

        if not success or not project_path:
            logger.warning(
                "generation failed errors=%s",
                [str(e)[:200] for e in errors[:8]],
            )
            fail_code = "generation_failed"
            if errors:
                fail_code = str(errors[0])[:80]
            # Prefer the engine's user-facing final_message when it's a clear,
            # actionable Arabic message (starts with ❌) — gives the user real
            # guidance (e.g. "set GEMINI_API_KEY") instead of a generic code.
            _engine_msg = ""
            try:
                _fm = str((getattr(result, "metadata", None) or {}).get("final_message") or "").strip()
                if _fm and _fm.startswith("❌") and len(_fm) < 800:
                    _engine_msg = _fm
            except Exception:
                _engine_msg = ""
            _user_msg = _engine_msg or user_facing_generation_error(code=fail_code)
            await safe_edit_text(
                status_msg,
                _user_msg,
            )
            try:
                from lumen.bot.ui.emit_context import emit_context_event

                await emit_context_event(
                    message=message,
                    context=context,
                    user=user,
                    kind="generation_failed",
                    detail=user_facing_generation_error(code=fail_code),
                )
            except Exception:
                logger.exception("emit gen fail context failed")
            return result

        proj = Path(str(project_path))
        if not proj.is_dir():
            await safe_edit_text(
                status_msg,
                "❌ التوليد انتهى بدون مجلد مشروع. أعد المحاولة.",
            )
            return result

        # Post hooks (must not block delivery)
        try:
            from lumen.platform.plan_gate import apply_post_generation

            apply_post_generation(str(proj), user_id=uid)
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
                        await safe_edit_text(status_msg, "✅ تم التوليد — جاري إرسال الملف…")
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
                            "✅ المشروع جاهز على السيرفر لكن رفع ZIP فشل. تم حفظه في مساحة المستخدم المعزولة."
                        )
                else:
                    await message.reply_text(
                        "✅ المشروع اتولد وتم حفظه في مساحة المستخدم المعزولة.\n"
                        "تعذر إنشاء ZIP — راجع السجلات."
                    )

        try:
            if success and project_path:
                from ..generation_cache import get_generation_cache

                get_generation_cache().put(
                    uid,
                    cache_key or gen_request,
                    {"project_path": str(project_path), "entry_point": "main.py"},
                )
                if context.user_data is not None:
                    context.user_data["last_project_path"] = str(project_path)
                    context.user_data["active_bot_path"] = str(project_path)
                try:
                    from lumen.engine.services.chat_memory import get_chat_memory

                    if user:
                        get_chat_memory().set_facts(
                            uid,
                            last_project_path=str(project_path),
                            last_bot_request=(gen_request or "")[:500],
                        )
                except Exception:
                    logger.exception("chat_memory project fact failed")
                # Register a durable project card (semantic memory) so the engine
                # remembers this project's structure + UI elements for precise edits
                # in later sessions ("remove the help button", "add a command"...).
                try:
                    from lumen.engine.services.semantic_memory.project_memory import (
                        get_project_memory_store,
                    )
                    _pc_store = get_project_memory_store()
                    _structure: dict = {}
                    _ui_elements: dict = {}
                    try:
                        from lumen.engine.services.bot_inspector import inspect_bot_project
                        _insp = inspect_bot_project(str(project_path))
                        if _insp:
                            _structure = {
                                "entry_point": getattr(_insp, "entry_point", "main.py"),
                                "files": list(getattr(_insp, "files", []) or [])[:30],
                                "language": getattr(_insp, "language", ""),
                            }
                            _ui_elements = {
                                "buttons": list(getattr(_insp, "commands", []) or []),
                                "commands": list(getattr(_insp, "commands", []) or []),
                            }
                    except Exception:
                        logger.debug("bot_inspector for project card failed", exc_info=True)
                    _pc_store.register_project(
                        user_id=uid,
                        project_id=str(project_path),
                        label=Path(str(project_path)).name,
                        kind="generated",
                        path=str(project_path),
                        source_request=(gen_request or "")[:500],
                        structure=_structure,
                        ui_elements=_ui_elements,
                    )
                except Exception:
                    logger.exception("project_memory register failed")
            _persist_session(user, context)
        except Exception:
            pass
        return result
    except FileNotFoundError as e:
        logger.exception("Generation FileNotFoundError")
        await safe_edit_text(status_msg, user_facing_generation_error(e))
        return None
    except Exception as e:
        logger.exception("Generation failed")
        await safe_edit_text(status_msg, user_facing_generation_error(e))
        return None


__all__ = ["allocate_generation_workdir", "execute_bot_generation"]
