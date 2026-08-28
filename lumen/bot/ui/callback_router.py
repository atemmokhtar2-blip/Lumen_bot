"""Single CallbackQuery entry for engine UI actions (Batch 0)."""
from __future__ import annotations

import logging

from lumen.engine.services.ui_state.controller import apply_action, render_home_message_ar
from lumen.engine.services.ui_state.models import EngineUiPhase

from .keyboards import build_inline_keyboard, decode_callback
from .state_store import load_ui_state, persist_ui_session, save_ui_state

logger = logging.getLogger("lumen_bot.ui")

_PHASE_BODY = {
    EngineUiPhase.HOME: render_home_message_ar,
    EngineUiPhase.IDLE: render_home_message_ar,
    EngineUiPhase.GEN_TYPE: lambda: (
        "🤖 اختيار نوع البوت\n\n"
        "هذه مرحلة هيكل (دفعة 0). التوليد الفعلي يُربط في دفعة لاحقة."
    ),
    EngineUiPhase.DASHBOARD: lambda: (
        "📊 لوحة التحكم\n\n"
        "هيكل فقط — إدارة المثيلات في دفعة لاحقة."
    ),
    EngineUiPhase.BILLING: lambda: (
        "💳 الرصيد والخطة\n\n"
        "هيكل فقط — بدون أسعار أو دفع وهمي في هذه الدفعة.\n"
        "استخدم /plan لعرض خطتك الحالية من النظام."
    ),
    EngineUiPhase.HELP: lambda: (
        "❓ المساعدة\n\n"
        "• اكتب وصف البوت كنص حر للتوليد (المسار الحالي)\n"
        "• /plan — خطتك\n"
        "• /help — الأوامر\n"
        "القائمة الموجَّهة تُبنى على دفعات."
    ),
}


def _body_for_phase(phase: EngineUiPhase) -> str:
    fn = _PHASE_BODY.get(phase)
    if fn is None:
        return f"مرحلة `{phase.value}`"
    return fn()


async def handle_ui_callback(update, context) -> None:
    q = update.callback_query
    if q is None:
        return
    data = q.data or ""
    parsed = decode_callback(data)
    if parsed is None:
        # Not our namespace — ignore (other handlers may own it)
        return
    action_id, arg = parsed
    try:
        await q.answer()
    except Exception:
        pass

    user_data = context.user_data if context.user_data is not None else {}
    state = load_ui_state(user_data)
    result = apply_action(state, action_id, arg)
    save_ui_state(user_data, result.state)
    uid = update.effective_user.id if update.effective_user else 0
    if uid:
        persist_ui_session(uid, dict(user_data))

    text = _body_for_phase(result.state.phase)
    if not result.ok:
        text = f"⚠️ {result.message_ar}\n\n" + text
    try:
        markup = build_inline_keyboard(result.buttons)
        if q.message:
            await q.edit_message_text(text=text, reply_markup=markup)
        else:
            if update.effective_message:
                await update.effective_message.reply_text(text, reply_markup=markup)
    except Exception:
        logger.exception("ui callback edit failed action=%s", action_id)
        try:
            if update.effective_message:
                await update.effective_message.reply_text(text)
        except Exception:
            pass
