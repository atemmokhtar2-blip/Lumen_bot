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
            UiButton("💾 نسخة احتياطية", "dash_backup", idx, style="primary"),
        ),
        (
            UiButton("📦 الإصدارات", "dash_versions", idx, style="primary"),
            UiButton("🔄 إعادة تشغيل", "host_restart", idx, style="success"),
        ),
        (
            UiButton("🛑 إيقاف", "dash_stop", idx, style="danger"),
        ),
    )


def format_host_success(result: Any) -> str:
    """User-facing confirmation after HostService.start — official Telegram HTML."""
    from lumen.bot.telegram_text import escape_html, html_card, html_code

    details: list[str] = []
    inst = getattr(result, "instance", None)
    if inst is not None:
        status = str(getattr(inst, "status", "") or "").strip()
        if status:
            details.append(f"الحالة: {html_code(status)}")
        un = str(getattr(inst, "bot_username", "") or "").strip().lstrip("@")
        if un:
            details.append(f"البوت: @{escape_html(un)}")
        iid = str(getattr(inst, "instance_id", "") or "").strip()
        if iid:
            details.append(f"المعرّف: {html_code(iid[:20])}")
        be = str(getattr(inst, "sandbox_backend", "") or "").strip()
        if be:
            # User-facing name — no vendor brand
            label = "استضافة Lumen" if be in {"lumen_serverless", "serverless", "vercel"} else escape_html(be)
            details.append(f"العزل: {label}")
        pub = str(getattr(inst, "public_base_url", "") or "").strip()
        if pub.startswith("http"):
            safe = escape_html(pub)
            details.append(f'الرابط: <a href="{safe}">{safe}</a>')
        wh = str(getattr(inst, "webhook_public_url", "") or "").strip()
        if wh.startswith("http"):
            safe = escape_html(wh)
            details.append(f'Webhook: <a href="{safe}">{safe}</a>')
        path = str(getattr(inst, "project_path", "") or "").strip()
        if path:
            short = path if len(path) <= 80 else "…" + path[-77:]
            details.append(f"المسار: {html_code(short)}")
        details.append("الأسرار: مشفّرة على القرص")
    else:
        msg = str(getattr(result, "message", "") or "").strip()
        if msg:
            details.append(escape_html(msg[:400]))

    # html_section/blockquote escapes plain text — so for mixed HTML lines we
    # build a pre-escaped body and pass through a light card that won't re-escape.
    body_lines = "\n".join(f"• {line}" for line in details) if details else "• المثيل يعمل."
    # Use expandable blockquote with content that already contains safe HTML tags
    # (html_code / <a>). html_blockquote would escape them — inject carefully.
    from lumen.bot.telegram_text import html_title

    head = html_title("الاستضافة شغّالة", subtitle="تشغيل حقيقي على استضافة Lumen")
    # Multi-line for expandable arrow; keep HTML tags intact
    if body_lines.count("\n") < 2:
        body_lines = body_lines + "\n\u200c"
    block = f"<blockquote expandable>{body_lines}</blockquote>"
    next_block = (
        "<b>التالي</b>\n"
        "<blockquote expandable>"
        "استخدم الأزرار أدناه لإدارة المثيل\n"
        "(حالة · سجلات · تشخيص · إيقاف)."
        "</blockquote>"
    )
    return f"{head}\n\n<b>المثيل</b>\n{block}\n\n{next_block}"[:3500]


async def attach_host_panel(
    *,
    status_message: Any,
    result: Any,
    user_id: int,
    user_data: dict | None = None,
) -> None:
    """Edit the status message with host panel keyboard bound to real engine."""
    text = format_host_success(result)
    try:
        from .dash_actions import sync_dashboard_slots
        from .state_store import load_ui_state, save_ui_state
        from lumen.engine.services.ui_state.models import EngineUiPhase

        ud = user_data if isinstance(user_data, dict) else {}
        st = load_ui_state(ud)
        st.slots = sync_dashboard_slots(int(user_id), dict(st.slots or {}))
        st.phase = EngineUiPhase.DASHBOARD
        save_ui_state(ud, st)
        if user_data is not None:
            user_data.update(ud)
    except Exception:
        logger.exception("sync dash slots for host panel failed")

    markup = build_inline_keyboard(host_panel_buttons(instance_index="0"), user_id=int(user_id))
    from lumen.bot.telegram_text import safe_edit_text, safe_reply_text

    try:
        await safe_edit_text(status_message, text, reply_markup=markup)
    except Exception:
        logger.exception("attach_host_panel edit failed")
        try:
            await safe_reply_text(status_message, text, reply_markup=markup)
        except Exception:
            logger.exception("attach_host_panel reply failed")
