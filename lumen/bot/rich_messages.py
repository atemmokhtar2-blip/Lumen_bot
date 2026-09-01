"""Telegram Bot API 10.1+ Rich Messages — native tables.

PTB 22.7 has no typed send_rich_message. We call the official endpoint via
do_api_request and intentionally avoid strict Message deserialization (22.7
does not model rich_message fields and would raise after a successful send).

On any failure the caller keeps the existing HTML card path.
"""
from __future__ import annotations

import html as html_lib
import logging
import re
from typing import Any, Sequence

logger = logging.getLogger(__name__)

_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def escape_rich(text: object) -> str:
    return html_lib.escape("" if text is None else str(text), quote=True)


def looks_like_rich_html(text: object) -> bool:
    s = "" if text is None else str(text)
    return "<table" in s and ("<th>" in s or "<td>" in s)


def _clean_html(html: str) -> str:
    """Strip comments / nulls — Telegram rich HTML parser is strict."""
    s = _HTML_COMMENT_RE.sub("", html or "")
    return s.strip()


def build_table_html(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    *,
    caption: str = "",
    bordered: bool = True,
    striped: bool = True,
    compact: bool = True,
) -> str:
    """Official Rich HTML <table> (core.telegram.org/bots/api)."""
    attrs: list[str] = []
    if bordered:
        attrs.append("bordered")
    if striped:
        attrs.append("striped")
    if compact:
        attrs.append("compact")
    open_tag = "<table" + ((" " + " ".join(attrs)) if attrs else "") + ">"
    lines = [open_tag]
    if caption:
        lines.append(f"<caption>{escape_rich(caption)}</caption>")
    lines.append("<tr>")
    for h in headers:
        lines.append(f"<th>{escape_rich(h)}</th>")
    lines.append("</tr>")
    for row in rows:
        lines.append("<tr>")
        cells = list(row) + [""] * max(0, len(headers) - len(row))
        for cell in cells[: len(headers)]:
            lines.append(f"<td>{escape_rich(cell)}</td>")
        lines.append("</tr>")
    lines.append("</table>")
    return "".join(lines)


def build_dashboard_rich_html(
    *,
    host_rows: Sequence[Sequence[str]],
    active_project: str = "",
    empty: bool = False,
) -> str:
    """Dashboard body for sendRichMessage (RTL Arabic)."""
    parts: list[str] = ["<h3>لوحة المشاريع والاستضافة</h3>"]
    if active_project:
        parts.append(f"<p><b>مشروع الجلسة:</b> {escape_rich(active_project)}</p>")
    headers = ["#", "المشروع", "الحالة", "اليوزر", "الخلفية"]
    if empty or not host_rows:
        # Always render a native table so the feature is visible even with 0 hosts
        parts.append(
            build_table_html(
                headers,
                [["—", "لا مشاريع بعد", "—", "—", "—"]],
                caption="0 مشروع مستضاف",
                bordered=True,
                striped=True,
                compact=True,
            )
        )
        parts.append(
            "<p>أنشئ بوتاً من الزر أدناه، ثم انشره للاستضافة الدائمة ليظهر في الجدول.</p>"
        )
    else:
        parts.append(
            build_table_html(
                headers,
                host_rows,
                caption=f"{len(host_rows)} مشروع",
                bordered=True,
                striped=True,
                compact=True,
            )
        )
    parts.append("<p><b>إجراءات:</b> تحديث · حالة · تجربة · نشر</p>")
    return "".join(parts)


def collect_dashboard_rows(state: Any, facts: Any) -> tuple[list[list[str]], bool]:
    rows: list[list[str]] = []
    slots = getattr(state, "slots", None) or {}
    for i in range(5):
        iid = slots.get(f"dash_h{i}") or ""
        if not iid:
            continue
        st = slots.get(f"dash_s{i}") or "?"
        un = slots.get(f"dash_u{i}") or "—"
        be = slots.get(f"dash_b{i}") or "—"
        short = iid[-12:] if len(str(iid)) > 12 else str(iid)
        un_s = str(un)
        if un_s and un_s != "—" and not un_s.startswith("@"):
            un_s = f"@{un_s}"
        rows.append([str(i + 1), short, str(st), un_s, str(be)])
    if not rows and getattr(facts, "hosts", None):
        for i, h in enumerate(list(facts.hosts)[:8]):
            un = getattr(h, "bot_username", None) or "—"
            un_s = str(un)
            if un_s and un_s != "—" and not un_s.startswith("@"):
                un_s = f"@{un_s}"
            rows.append(
                [
                    str(i + 1),
                    str(getattr(h, "instance_id", "") or "")[-12:],
                    str(getattr(h, "status", "") or "?"),
                    un_s,
                    str(getattr(h, "backend", None) or "—"),
                ]
            )
    return rows, len(rows) == 0


def _markup_dict(reply_markup: Any) -> Any:
    if reply_markup is None:
        return None
    to_dict = getattr(reply_markup, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    return reply_markup


def _message_id_from_result(result: Any) -> int | None:
    if result is None:
        return None
    if isinstance(result, dict):
        mid = result.get("message_id")
        return int(mid) if mid is not None else None
    mid = getattr(result, "message_id", None)
    return int(mid) if mid is not None else None


async def send_rich_message(
    bot: Any,
    *,
    chat_id: int,
    html: str,
    reply_markup: Any = None,
    is_rtl: bool = True,
) -> Any:
    """Official sendRichMessage. Returns raw API result (dict or Message)."""
    html_clean = _clean_html(html)
    if not html_clean:
        raise ValueError("empty rich html")

    rich: dict[str, Any] = {
        "html": html_clean,
        "is_rtl": bool(is_rtl),
        "skip_entity_detection": True,
    }
    kwargs: dict[str, Any] = {
        "chat_id": int(chat_id),
        "rich_message": rich,
    }
    mk = _markup_dict(reply_markup)
    if mk is not None:
        kwargs["reply_markup"] = mk

    # return_type=None: PTB 22.7 cannot deserialize rich Message fields and
    # would raise *after* Telegram already accepted the send.
    return await bot.do_api_request(
        "sendRichMessage",
        api_kwargs=kwargs,
        return_type=None,
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
    html_clean = _clean_html(html)
    rich: dict[str, Any] = {
        "html": html_clean,
        "is_rtl": bool(is_rtl),
        "skip_entity_detection": True,
    }
    kwargs: dict[str, Any] = {
        "chat_id": int(chat_id),
        "message_id": int(message_id),
        "rich_message": rich,
    }
    mk = _markup_dict(reply_markup)
    if mk is not None:
        kwargs["reply_markup"] = mk
    return await bot.do_api_request(
        "editMessageText",
        api_kwargs=kwargs,
        return_type=None,
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
    """Strong path: delete old surface → sendRichMessage. Edit only as soft try.

    Returns truthy result on success, None on failure (caller must HTML-fallback).
    """
    from lumen.bot.ui.chat_hygiene import remember_message, prune_bot_messages

    ud = user_data if isinstance(user_data, dict) else {}
    mid = getattr(preferred_message, "message_id", None) if preferred_message else None

    # Soft try: convert in place (works only if previous message was already rich)
    if mid is not None:
        try:
            result = await edit_rich_message(
                bot,
                chat_id=chat_id,
                message_id=int(mid),
                html=html,
                reply_markup=markup,
            )
            remember_message(ud, int(mid))
            await prune_bot_messages(bot, chat_id, ud, protect=int(mid))
            logger.info("rich edit ok chat=%s mid=%s", chat_id, mid)
            return result if result is not None else True
        except Exception as e:
            logger.warning(
                "rich edit failed chat=%s mid=%s err=%s — delete+send",
                chat_id,
                mid,
                e,
            )
            try:
                await bot.delete_message(chat_id=chat_id, message_id=int(mid))
            except Exception:
                pass

    try:
        result = await send_rich_message(
            bot, chat_id=chat_id, html=html, reply_markup=markup
        )
        new_mid = _message_id_from_result(result)
        if new_mid is not None:
            remember_message(ud, new_mid)
            await prune_bot_messages(bot, chat_id, ud, protect=new_mid)
        else:
            # API accepted but shape unknown — still treat as success so we
            # do NOT double-send HTML fallback on top of a live rich message.
            logger.info("rich send ok chat=%s (no message_id in result)", chat_id)
        logger.info("rich send ok chat=%s mid=%s", chat_id, new_mid)
        return result if result is not None else True
    except Exception as e:
        logger.error("send_rich_message FAILED chat=%s err=%s", chat_id, e, exc_info=True)
        return None


__all__ = [
    "looks_like_rich_html",
    "build_table_html",
    "build_dashboard_rich_html",
    "collect_dashboard_rows",
    "send_rich_message",
    "edit_rich_message",
    "send_or_edit_rich_ui",
    "html_from_table_spec",
    "send_table_spec",
]


def html_from_table_spec(spec: Any) -> str:
    """Build Rich HTML from engine TableSpec / dict."""
    if spec is None:
        return ""
    if isinstance(spec, dict):
        headers = [str(h) for h in (spec.get("headers") or [])]
        rows = [[str(c) for c in r] for r in (spec.get("rows") or []) if isinstance(r, (list, tuple))]
        title = str(spec.get("title") or "")
        caption = str(spec.get("caption") or "")
    else:
        headers = list(getattr(spec, "headers", None) or [])
        rows = [list(r) for r in (getattr(spec, "rows", None) or [])]
        title = str(getattr(spec, "title", "") or "")
        caption = str(getattr(spec, "caption", "") or "")
    if len(headers) < 2 or not rows:
        return ""
    parts: list[str] = []
    if title:
        parts.append(f"<h3>{escape_rich(title)}</h3>")
    parts.append(
        build_table_html(
            headers,
            rows,
            caption=caption,
            bordered=True,
            striped=True,
            compact=True,
        )
    )
    return "".join(parts)


async def send_table_spec(
    bot: Any,
    *,
    chat_id: int,
    spec: Any,
    reply_markup: Any = None,
    preferred_message: Any = None,
    user_data: dict[str, Any] | None = None,
) -> Any:
    """Send engine-chosen table via Rich Messages (fallback None)."""
    html = html_from_table_spec(spec)
    if not html:
        return None
    return await send_or_edit_rich_ui(
        bot=bot,
        chat_id=int(chat_id),
        html=html,
        markup=reply_markup,
        preferred_message=preferred_message,
        user_data=user_data,
    )
