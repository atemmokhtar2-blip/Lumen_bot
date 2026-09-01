"""Persistent hosting control panel — real HostService bindings.

After a successful host_start, the confirmation message carries an inline
keyboard that drives HostingService.status / stop / diagnose, and a restart
flow that re-requests the bot token securely (raw tokens are never stored).
"""
from __future__ import annotations

import logging
from typing import Any

from lumen.engine.services.ui_state.models import UiButton

from .keyboards import build_inline_keyboard
from .rtl_text import code_path

logger = logging.getLogger("lumen_bot.ui.host_panel")


def host_panel_buttons(*, instance_index: str = "0") -> tuple[tuple[UiButton, ...], ...]:
    """Control plane for one hosted instance (index into dash slots)."""
    idx = (instance_index or "0").strip() or "0"
    return (
        (
            UiButton("📊 الحالة", "dash_status", idx, style="primary"),
            UiButton("📝 السجلات", "dash_logs", idx, style="primary"),
        ),
        (
            UiButton("🩺 تشخيص", "dash_diagnose", idx, style="primary"),
            UiButton("🔄 إعادة تشغيل", "host_restart", idx, style="success"),
        ),
        (
            UiButton("🛑 إيقاف", "dash_stop", idx, style="danger"),
        ),
    )


def format_host_success(result: Any) -> str:
    """User-facing confirmation after HostService.start succeeded — HTML card."""
    from lumen.bot.telegram_text import html_bullets, html_card

    details: list[str] = []
    inst = getattr(result, "instance", None)
    if inst is not None:
        status = str(getattr(inst, "status", "") or "")
        if status:
            details.append(f"الحالة: {status}")
        un = str(getattr(inst, "bot_username", "") or "")
        if un:
            details.append(f"البوت: @{un}")
        iid = str(getattr(inst, "instance_id", "") or "")
        if iid:
            details.append(f"المعرّف: {iid[:16]}")
        be = str(getattr(inst, "sandbox_backend", "") or "")
        if be:
            details.append(f"العزل: {be}")
        path = str(getattr(inst, "project_path", "") or "")
        if path:
            details.append(f"المسار: {code_path(path)}")
    else:
        msg = str(getattr(result, "message", "") or "").strip()
        if msg:
            details.append(msg[:400])
    body = html_bullets(details) if details else "المثيل يعمل."
    return html_card(
        "الاستضافة شغّالة",
        [
            ("المثيل", body),
            ("التالي", "استخدم الأزرار أدناه لإدارة المثيل\n(حالة · سجلات · تشخيص · إيقاف)."),
        ],
        subtitle="HostService · تشغيل حقيقي",
    )[:3500]


async def attach_host_panel(
    *,
    status_message: Any,
    result: Any,
    user_id: int,
    user_data: dict | None = None,
) -> None:
    """Edit the status message with host panel keyboard bound to real engine."""
    text = format_host_success(result)
    # Sync dashboard slots so dash_* actions resolve this instance
    try:
        from .dash_actions import sync_dashboard_slots
        from .state_store import load_ui_state, save_ui_state
        from lumen.engine.services.ui_state.models import EngineUiPhase

        ud = user_data if isinstance(user_data, dict) else {}
        st = load_ui_state(ud)
        st.slots = sync_dashboard_slots(int(user_id), dict(st.slots or {}))
        st.phase = EngineUiPhase.DASHBOARD
        # Prefer newest instance index 0
        save_ui_state(ud, st)
        if user_data is not None:
            user_data.update(ud)
    except Exception:
        logger.exception("sync dash slots for host panel failed")

    markup = build_inline_keyboard(host_panel_buttons(instance_index="0"), user_id=int(user_id))
    try:
        await status_message.edit_text(text, reply_markup=markup)
    except Exception:
        logger.exception("attach_host_panel edit failed")
        try:
            await status_message.reply_text(text, reply_markup=markup)
        except Exception:
            logger.exception("attach_host_panel reply failed")
