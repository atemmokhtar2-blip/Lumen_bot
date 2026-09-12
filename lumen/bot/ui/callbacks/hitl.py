"""HITL confirm/reject callback — extracted from callback_router."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("lumen.bot.ui.callbacks.hitl")


async def handle_hitl_callback(update, context, q, action_id: str) -> bool:
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
