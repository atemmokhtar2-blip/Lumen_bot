"""Telegram Bot API 10.1+ Rich Messages (native tables).

Uses official sendRichMessage / editMessageText(rich_message=...) via PTB
do_api_request — PTB 22.7 has no typed wrapper yet.

Fallback: caller keeps existing HTML card path when rich fails.
"""
from __future__ import annotations

import html as html_lib
import logging
from typing import Any, Sequence

logger = logging.getLogger(__name__)

# Prefix so send path can detect rich HTML payloads built by us
RICH_HTML_MARKER = "<!--lumen-rich-v1-->"


def escape_rich(text: object) -> str:
    return html_lib.escape("" if text is None else str(text), quote=True)


def looks_like_rich_html(text: object) -> bool:
    s = "" if text is None else str(text)
    return RICH_HTML_MARKER in s or "<table" in s


def build_table_html(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    *,
    caption: str = "",
    bordered: bool = True,
    striped: bool = True,
    compact: bool = True,
) -> str:
    """Official Rich HTML <table> (Bot API 10.1+)."""
    attrs: list[str] = []
    if bordered:
        attrs.append("bordered")
    if striped:
        attrs.append("striped")
    if compact:
        attrs.append("compact")
    open_tag = "<table" + ((" " + " ".join(attrs)) if attrs else "") + ">"
    parts = [open_tag]
    if caption:
        parts.append(f"<caption>{escape_rich(caption)}</caption>")
    # header row
    parts.append("<tr>")
    for h in headers:
        parts.append(f"<th>{escape_rich(h)}</th>")
    parts.append("</tr>")
    for row in rows:
        parts.append("<tr>")
        for cell in row:
            parts.append(f"<td>{escape_rich(cell)}</td>")
        # pad missing cells
        for _ in range(len(headers) - len(row)):
            parts.append("<td></td>")
        parts.append("</tr>")
    parts.append("</table>")
    return "".join(parts)


def build_dashboard_rich_html(
    *,
    host_rows: Sequence[Sequence[str]],
    active_project: str = "",
    empty: bool = False,
) -> str:
    """Rich HTML body for لوحة التحكم — native table when hosts exist."""
    chunks: list[str] = [RICH_HTML_MARKER]
    chunks.append("<h3>🖥️ لوحة المشاريع والاستضافة</h3>")
    if active_project:
        chunks.append(
            f"<p><b>مشروع الجلسة:</b> {escape_rich(active_project)}</p>"
        )
    if empty or not host_rows:
        chunks.append(
            "<p>📭 لا توجد مشاريع مستضافة حالياً.</p>"
            "<p>ابدأ بإنشاء بوت من الزر أدناه، ثم انشره للاستضافة الدائمة.</p>"
        )
    else:
        table = build_table_html(
            ["#", "المشروع", "الحالة", "اليوزر", "الخلفية"],
            host_rows,
            caption=f"{len(host_rows)} مشروع",
            bordered=True,
            striped=True,
            compact=True,
        )
        chunks.append(table)
    chunks.append(
        "<p><b>إجراءات:</b> تحديث القائمة · حالة الكل · تجربة · نشر</p>"
    )
    return "\n".join(chunks)


def collect_dashboard_rows(state: Any, facts: Any) -> tuple[list[list[str]], bool]:
    """Build table rows from UI state slots or facts.hosts."""
    rows: list[list[str]] = []
    slots = getattr(state, "slots", None) or {}
    for i in range(5):
        iid = slots.get(f"dash_h{i}") or ""
        if not iid:
            continue
        st = slots.get(f"dash_s{i}") or "?"
        un = slots.get(f"dash_u{i}") or "—"
        be = slots.get(f"dash_b{i}") or "—"
        short = iid[-12:] if len(iid) > 12 else iid
        rows.append([str(i + 1), short, str(st), f"@{un}" if un and not str(un).startswith("@") else str(un), str(be)])
    if not rows and getattr(facts, "hosts", None):
        for i, h in enumerate(list(facts.hosts)[:8]):
            un = getattr(h, "bot_username", None) or "—"
            if un and not str(un).startswith("@") and un != "—":
                un = f"@{un}"
            rows.append(
                [
                    str(i + 1),
                    str(getattr(h, "instance_id", "") or "")[-12:],
                    str(getattr(h, "status", "") or "?"),
                    str(un),
                    str(getattr(h, "backend", None) or "—"),
                ]
            )
    return rows, len(rows) == 0


async def send_rich_message(
    bot: Any,
    *,
    chat_id: int,
    html: str,
    reply_markup: Any = None,
    is_rtl: bool = True,
) -> Any:
    """Official sendRichMessage. Raises on hard failure."""
    from telegram import Message

    rich: dict[str, Any] = {"html": html, "is_rtl": bool(is_rtl)}
    kwargs: dict[str, Any] = {
        "chat_id": int(chat_id),
        "rich_message": rich,
    }
    if reply_markup is not None:
        to_dict = getattr(reply_markup, "to_dict", None)
        kwargs["reply_markup"] = to_dict() if callable(to_dict) else reply_markup
    return await bot.do_api_request(
        "sendRichMessage",
        api_kwargs=kwargs,
        return_type=Message,
    )


async def edit_rich_message(
    bot: Any,
    *,
    chat_id: int,
    message_id: int,
    html: str,
    reply_markup: Any = None,
    is_rtl: bool = True,
) -> Any:
    """editMessageText with rich_message (Bot API 10.1+)."""
    from telegram import Message

    rich: dict[str, Any] = {"html": html, "is_rtl": bool(is_rtl)}
    kwargs: dict[str, Any] = {
        "chat_id": int(chat_id),
        "message_id": int(message_id),
        "rich_message": rich,
    }
    if reply_markup is not None:
        to_dict = getattr(reply_markup, "to_dict", None)
        kwargs["reply_markup"] = to_dict() if callable(to_dict) else reply_markup
    return await bot.do_api_request(
        "editMessageText",
        api_kwargs=kwargs,
        return_type=Message,
    )


async def send_or_edit_rich_ui(
    *,
    bot: Any,
    chat_id: int,
    html: str,
    markup: Any = None,
    preferred_message: Any = None,
    user_data: dict[str, Any] | None = None,
) -> Any:
    """Try edit rich → else delete+send rich. Returns Message or None."""
    from lumen.bot.ui.chat_hygiene import remember_message, prune_bot_messages

    ud = user_data if isinstance(user_data, dict) else {}
    mid = getattr(preferred_message, "message_id", None) if preferred_message else None

    if mid is not None:
        try:
            msg = await edit_rich_message(
                bot,
                chat_id=chat_id,
                message_id=int(mid),
                html=html,
                reply_markup=markup,
            )
            remember_message(ud, mid)
            await prune_bot_messages(bot, chat_id, ud, protect=mid)
            return msg
        except Exception:
            logger.debug("edit_rich_message failed mid=%s — will send new", mid, exc_info=True)
            try:
                await bot.delete_message(chat_id=chat_id, message_id=int(mid))
            except Exception:
                pass

    try:
        msg = await send_rich_message(
            bot, chat_id=chat_id, html=html, reply_markup=markup
        )
        new_mid = getattr(msg, "message_id", None)
        remember_message(ud, new_mid)
        await prune_bot_messages(bot, chat_id, ud, protect=new_mid)
        return msg
    except Exception:
        logger.exception("send_rich_message failed chat=%s", chat_id)
        return None


__all__ = [
    "RICH_HTML_MARKER",
    "looks_like_rich_html",
    "build_table_html",
    "build_dashboard_rich_html",
    "collect_dashboard_rows",
    "send_rich_message",
    "edit_rich_message",
    "send_or_edit_rich_ui",
]
