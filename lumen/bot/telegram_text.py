"""Telegram text transport — root fix for Markdown Hell.

Rules
-----
1. Arbitrary agent/LLM text is sent as **plain text** (no parse_mode).
2. Intentional formatting uses **MarkdownV2** or **HTML** with official escaping.
3. UI cards use HTML ``<blockquote>`` / ``<blockquote expandable>`` (Bot API 7+)
   for the native blue quote box + collapse arrow in Telegram clients.
4. Messages longer than 4096 are split on paragraph/line boundaries so
   Telegram never drops the body.

Legacy ``ParseMode.MARKDOWN`` is never used — it breaks on ``_``, ``*``, ``[``.

Refs: https://core.telegram.org/bots/api#html-style
"""
from __future__ import annotations

import html as _html_mod
import re
from typing import Any, Optional, Sequence

# Telegram Bot API hard limit for message text
TELEGRAM_MAX_MESSAGE = 4096

# Official MarkdownV2 special characters (Bot API)
# https://core.telegram.org/bots/api#markdownv2-style
_MDV2_SPECIAL = r"_*[]()~`>#+-=|{}.!"
_MDV2_ESCAPE_RE = re.compile(r"([\\%s])" % re.escape(_MDV2_SPECIAL))


def escape_markdown_v2(text: object) -> str:
    """Escape all MarkdownV2 special characters for safe parse_mode=MarkdownV2."""
    s = "" if text is None else str(text)
    # Backslash must be escaped first — handled by putting \\ in the class via re.escape
    return _MDV2_ESCAPE_RE.sub(r"\\\1", s)


def escape_md(text: object) -> str:
    """Alias kept for callers — always MarkdownV2 escaping (not legacy Markdown)."""
    return escape_markdown_v2(text)


def escape_html(text: object) -> str:
    """Escape &, <, > for Telegram HTML parse_mode (official requirement)."""
    s = "" if text is None else str(text)
    return _html_mod.escape(s, quote=False)


def looks_like_telegram_html(text: object) -> bool:
    """True when body intentionally contains Telegram HTML tags we emit."""
    s = "" if text is None else str(text)
    if not s:
        return False
    markers = (
        "<blockquote",
        "</blockquote>",
        "<b>",
        "</b>",
        "<i>",
        "</i>",
        "<code>",
        "</code>",
        "<pre>",
        "</pre>",
        "<tg-spoiler>",
    )
    return any(m in s for m in markers)


def html_blockquote(body: object, *, expandable: bool = False) -> str:
    """Native Telegram blue quote box. expandable=True shows the collapse arrow.

    Official HTML: ``<blockquote expandable>…</blockquote>`` (Bot API 7.3+).
    Clients only show the arrow when the quote has multiple lines.
    """
    raw = "" if body is None else str(body).strip("\n")
    if not raw:
        return ""
    if expandable and raw.count("\n") < 2:
        raw = raw + "\n\u200c\n\u200c"
    inner = escape_html(raw)
    attr = " expandable" if expandable else ""
    return f"<blockquote{attr}>{inner}</blockquote>"


def html_section(title: object, body: object, *, expandable: bool = True) -> str:
    """Bold title + expandable blue box (XPic-style feature cards)."""
    t = escape_html("" if title is None else str(title).strip())
    block = html_blockquote(body, expandable=expandable)
    if t and block:
        return f"<b>{t}</b>\n{block}"
    return t or block


def html_card(
    title: object,
    sections: Sequence[tuple[object, object]] | None = None,
    *,
    footer: object = "",
) -> str:
    """Full UI card: bold title + expandable blue sections."""
    parts: list[str] = []
    t = ("" if title is None else str(title)).strip()
    if t:
        parts.append(f"<b>{escape_html(t)}</b>")
    for sec_title, sec_body in sections or ():
        st = ("" if sec_title is None else str(sec_title)).strip()
        sb = ("" if sec_body is None else str(sec_body)).strip()
        if not sb and not st:
            continue
        if st:
            parts.append(html_section(st, sb, expandable=True))
        else:
            parts.append(html_blockquote(sb, expandable=True))
    ft = ("" if footer is None else str(footer)).strip()
    if ft:
        parts.append(escape_html(ft))
    return "\n\n".join(p for p in parts if p)


def strip_markdown_noise(text: object) -> str:
    """Remove common markdown control chars for plain-text fallback."""
    s = "" if text is None else str(text)
    # Unescape our escapes then drop controls
    s = s.replace("\\", "")
    for ch in ("*", "`", "_", "[", "]", "(", ")", "~", ">", "#", "|", "{", "}"):
        s = s.replace(ch, "")
    return s


def split_telegram_text(text: object, *, limit: int = TELEGRAM_MAX_MESSAGE) -> list[str]:
    """Split text into chunks ≤ limit, preferring paragraph then line breaks."""
    s = "" if text is None else str(text)
    if not s:
        return []
    limit = max(100, int(limit))
    if len(s) <= limit:
        return [s]

    chunks: list[str] = []
    rest = s
    while rest:
        if len(rest) <= limit:
            chunks.append(rest)
            break
        window = rest[:limit]
        # Prefer double newline, then single newline, then space
        cut = window.rfind("\n\n")
        if cut < limit // 3:
            cut = window.rfind("\n")
        if cut < limit // 3:
            cut = window.rfind(" ")
        if cut < limit // 3:
            cut = limit
        piece = rest[:cut].rstrip()
        if not piece:
            piece = rest[:limit]
            cut = limit
        chunks.append(piece)
        rest = rest[cut:].lstrip("\n")
    return chunks


async def safe_edit_text(
    message: Any,
    text: str,
    *,
    use_markdown: bool = False,
    reply_markup: Any = None,
) -> None:
    """Edit message text. Default plain text — never fails on agent markdown noise.

    When use_markdown=True, sends MarkdownV2 with the body fully escaped
    (so dynamic content is safe; intentional bold is not applied unless the
    caller pre-builds escaped MDV2 themselves and passes use_markdown=False
    with parse handled externally).
    """
    body = "" if text is None else str(text)
    # editMessageText only supports a single message — truncate smartly
    if len(body) > TELEGRAM_MAX_MESSAGE:
        parts = split_telegram_text(body, limit=TELEGRAM_MAX_MESSAGE - 20)
        body = parts[0] if parts else body[: TELEGRAM_MAX_MESSAGE - 20]
        if len(parts) > 1:
            body = body.rstrip() + "\n…(يتبع في الرسائل التالية)"

    kwargs: dict[str, Any] = {}
    if reply_markup is not None:
        kwargs["reply_markup"] = reply_markup

    if use_markdown:
        try:
            from telegram.constants import ParseMode

            escaped = escape_markdown_v2(body)
            await message.edit_text(
                escaped, parse_mode=ParseMode.MARKDOWN_V2, **kwargs
            )
            return
        except Exception:
            pass

    try:
        await message.edit_text(body, **kwargs)
    except Exception:
        try:
            await message.edit_text(strip_markdown_noise(body)[:TELEGRAM_MAX_MESSAGE], **kwargs)
        except Exception:
            from lumen.bot.config import logger

            logger.exception("safe_edit_text failed")


async def safe_reply_text(
    message: Any,
    text: str,
    *,
    use_markdown: bool = False,
    reply_markup: Any = None,
    disable_web_page_preview: bool = True,
) -> list[Any]:
    """Reply with one or more messages if text exceeds Telegram limit.

    Returns the list of sent Message objects (may be empty on total failure).
    Default is plain text (safe for agent output).
    """
    body = "" if text is None else str(text)
    parts = split_telegram_text(body, limit=TELEGRAM_MAX_MESSAGE - 8)
    if not parts:
        parts = [" "]

    sent: list[Any] = []
    for i, part in enumerate(parts):
        # Only attach markup to the last chunk
        kw: dict[str, Any] = {"disable_web_page_preview": disable_web_page_preview}
        if reply_markup is not None and i == len(parts) - 1:
            kw["reply_markup"] = reply_markup

        ok = False
        if use_markdown:
            try:
                from telegram.constants import ParseMode

                await_msg = await message.reply_text(
                    escape_markdown_v2(part),
                    parse_mode=ParseMode.MARKDOWN_V2,
                    **kw,
                )
                sent.append(await_msg)
                ok = True
            except Exception:
                ok = False
        if not ok:
            try:
                await_msg = await message.reply_text(part, **kw)
                sent.append(await_msg)
            except Exception:
                try:
                    await_msg = await message.reply_text(
                        strip_markdown_noise(part)[:TELEGRAM_MAX_MESSAGE]
                    )
                    sent.append(await_msg)
                except Exception:
                    from lumen.bot.config import logger

                    logger.exception("safe_reply_text chunk failed i=%s", i)
    return sent


async def safe_send_text(
    bot: Any,
    chat_id: int,
    text: str,
    *,
    use_markdown: bool = False,
    reply_markup: Any = None,
    disable_web_page_preview: bool = True,
) -> list[Any]:
    """Bot.send_message variant with split + plain default."""
    body = "" if text is None else str(text)
    parts = split_telegram_text(body, limit=TELEGRAM_MAX_MESSAGE - 8)
    if not parts:
        parts = [" "]
    sent: list[Any] = []
    for i, part in enumerate(parts):
        kw: dict[str, Any] = {
            "chat_id": chat_id,
            "text": part,
            "disable_web_page_preview": disable_web_page_preview,
        }
        if reply_markup is not None and i == len(parts) - 1:
            kw["reply_markup"] = reply_markup
        if use_markdown:
            try:
                from telegram.constants import ParseMode

                kw["text"] = escape_markdown_v2(part)
                kw["parse_mode"] = ParseMode.MARKDOWN_V2
                sent.append(await bot.send_message(**kw))
                continue
            except Exception:
                kw.pop("parse_mode", None)
                kw["text"] = part
        try:
            sent.append(await bot.send_message(**kw))
        except Exception:
            try:
                kw["text"] = strip_markdown_noise(part)[:TELEGRAM_MAX_MESSAGE]
                kw.pop("parse_mode", None)
                sent.append(await bot.send_message(**kw))
            except Exception:
                from lumen.bot.config import logger

                logger.exception("safe_send_text failed")
    return sent


__all__ = [
    "TELEGRAM_MAX_MESSAGE",
    "escape_markdown_v2",
    "escape_md",
    "escape_html",
    "looks_like_telegram_html",
    "html_blockquote",
    "html_section",
    "html_card",
    "strip_markdown_noise",
    "split_telegram_text",
    "safe_edit_text",
    "safe_reply_text",
    "safe_send_text",
]
