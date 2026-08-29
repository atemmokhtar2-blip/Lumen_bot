"""Pre-generation stage: status line + plan quota check.

Returns False if generation must stop (quota exceeded).
"""
from __future__ import annotations

from telegram.constants import ChatAction

from ..config import logger
from ..middlewares.mongo_sync import plan_live_seconds as _plan_live_seconds


async def prepare_status_and_quota(*, message, context, user, request: str, soft_note: str = "") -> object | None:
    """Reply with status_msg and enforce monthly quota.

    Returns status_msg, or None if the caller should stop (quota / hard fail).
    """
    _status_line = "⏳ جاري توليد المشروع (مسار حتمي) ثم التحقق ضد الهلوسة..."
    _soft_note = soft_note or ""
    try:
        from lumen.engine.spec_core.language_understanding import (
            understand,
            analyze_intent,
            personalize,
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
        _status_line = (_nav4.status_start or _status_line) + _soft_note
    except Exception:
        logger.exception("stage4 pre-summary failed")
        _status_line = _status_line + _soft_note

    status_msg = await message.reply_text(_status_line)
    try:
        await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)
    except Exception:
        pass

    try:
        from lumen.platform.plan_gate import check_generation_quota

        _q_ok, _q_reason, _q_info = check_generation_quota(
            user_id=int(user.id) if user else 0
        )
        if not _q_ok:
            limit = _q_info.get("limit") or "?"
            plan_id = _q_info.get("plan_id") or "free"
            detail = (
                f"وصلت للحد الشهري للتوليد على خطة {plan_id} "
                f"({limit} توليد/شهر). السبب: {_q_reason}"
            )
            await status_msg.edit_text("⛔ " + detail)
            try:
                from lumen.bot.ui.emit_context import emit_context_event

                await emit_context_event(
                    message=message,
                    context=context,
                    user=user,
                    kind="insufficient_quota",
                    detail=detail,
                )
            except Exception:
                logger.exception("emit quota context failed")
            return None
    except Exception:
        logger.exception("plan quota check failed")

    return status_msg


__all__ = ["prepare_status_and_quota"]
