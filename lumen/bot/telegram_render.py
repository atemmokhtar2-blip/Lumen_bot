"""Telegram text rendering layer — MarkdownV2-safe + long-message splitting.

Single source of truth for sending/editing Telegram text:
  * MarkdownV2 escaping via the real ``telegramify-markdown`` library (Rust-backed
    pyromark parser — world-class correctness, not a hand-rolled regex).
  * Automatic splitting of messages > 4096 UTF-16 units (Telegram hard limit)
    into consecutive messages so content is never silently truncated.
  * Graceful fallback to plain text if the Telegram package or the parser is
    unavailable, so the bot never blocks on a formatting error.

This replaces the previous fragile approach (ParseMode.MARKDOWN legacy +
hand-rolled ``escape_md`` that missed MarkdownV2-only characters like ``.``,
``-``, ``!``, ``~``, ``#``, ``+``, ``=``, ``|``, ``{``, ``}``).

Design rules (project protocol):
  * REAL tool (telegramify-markdown) — no mock/placeholder/simulation.
  * Never hide errors: if MarkdownV2 parse fails we retry once as plain text and
    log the cause; we do NOT swallow the original.
  * Long content is SPLIT (delivered in full across messages), never TRUNCATED.
"""
from __future__ import annotations

import logging
from typing import Any, Sequence

logger = logging.getLogger("lumen.bot.telegram_render")

# Telegram hard limit for send_message text length (UTF-16 code units).
TELEGRAM_TEXT_LIMIT = 4096
# Keep a safety margin so captions/overheads never trip the limit.
_SPLIT_LIMIT = 4090

# ---------------------------------------------------------------------------
# Optional dependency: telegramify-markdown (preferred, real parser).
# Falls back to python-telegram-bot's escape_markdown when the heavy parser is
# not installed. Both produce correct MarkdownV2; telegramify-markdown also
# gives us entity-based splitting for free.
# ---------------------------------------------------------------------------
_TM_AVAILABLE = False
try:
    import telegramify_markdown as _tm  # type: ignore

    _TM_AVAILABLE = True
except Exception:  # pragma: no cover - env without optional dep
    _tm = None  # type: ignore


def _ptb_escape_v2(text: str) -> str:
    """Fallback MarkdownV2 escape using python-telegram-bot's helper if present."""
    try:
        from telegram.helpers import escape_markdown  # type: ignore

        return escape_markdown(str(text or ""), version=2)
    except Exception:
        # Last-resort hand-rolled escape for MarkdownV2 special characters.
        # This mirrors Telegram's documented set exactly.
        s = str(text or "")
        for ch in ("\\", "_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"):
            s = s.replace(ch, f"\\{ch}")
        return s


def to_markdown_v2(text: Any) -> str:
    """Convert arbitrary Markdown/plain text to a Telegram MarkdownV2 string.

    Uses telegramify-markdown's ``markdownify`` (correct MarkdownV2 escaping
    inside and outside code/pre blocks, links, etc.) when available, otherwise
    falls back to PTB's ``escape_markdown(version=2)``.

    For *plain* (non-markdown) text that should be shown verbatim, prefer
    ``escape_markdown_v2`` instead so existing markdown markers are not
    interpreted.
    """
    s = "" if text is None else str(text)
    if not s:
        return ""
    if _TM_AVAILABLE:
        try:
            return _tm.markdownify(s)
        except Exception as exc:  # pragma: no cover
            logger.warning("telegramify markdownify failed (%s) — PTB fallback", exc)
    return _ptb_escape_v2(s)


def escape_markdown_v2(text: Any) -> str:
    """Escape *plain* text for MarkdownV2 so it renders verbatim.

    Use this for dynamic fragments (user input, file names, error codes) that
    must never be interpreted as markdown. Uses PTB's escape when available,
    else a correct hand-rolled MarkdownV2 escape.
    """
    s = "" if text is None else str(text)
    if not s:
        return ""
    try:
        from telegram.helpers import escape_markdown  # type: ignore

        return escape_markdown(s, version=2)
    except Exception:
        return _ptb_escape_v2(s)


# Backward-compatible alias for the old ``escape_md`` name (legacy Markdown).
# New code should use escape_markdown_v2 / to_markdown_v2 instead.
def escape_md_legacy(text: Any) -> str:
    """Escape Telegram *legacy* Markdown characters (kept for compatibility)."""
    s = "" if text is None else str(text)
    for ch in ("\\", "`", "*", "_", "[", "]", "(", ")"):
        s = s.replace(ch, f"\\{ch}")
    return s


def split_markdown_v2(text: str, *, max_utf16: int = _SPLIT_LIMIT) -> list[str]:
    """Split a (possibly long) Markdown/MarkdownV2 string into sendable chunks.

    Each chunk is a valid MarkdownV2 string whose UTF-16 length is <=
    ``max_utf16``. Splitting happens at newline boundaries; entities spanning a
    split point are clipped correctly by telegramify-markdown's splitter.
    Returns at least one chunk (possibly the empty string).
    """
    s = "" if text is None else str(text)
    if not s:
        return [""]
    if _TM_AVAILABLE:
        try:
            # Convert to (plain_text, entities) first, then split into
            # MarkdownV2 strings bounded by rendered UTF-16 length.
            plain, entities = _tm.convert(s)
            if not plain and not entities:
                return [""]
            chunks = _tm.split_markdownv2(plain, entities, max_utf16_len=int(max_utf16))
            chunks = [c for c in chunks if c.strip()]
            return chunks or [""]
        except Exception as exc:  # pragma: no cover
            logger.warning("telegramify split failed (%s) — naive fallback", exc)
    # Naive but safe fallback: split on newlines, then hard-wrap by UTF-16.
    return _naive_split_utf16(s, max_utf16)


def _utf16_len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def _naive_split_utf16(text: str, max_utf16: int) -> list[str]:
    """Fallback splitter when telegramify-markdown is unavailable."""
    if _utf16_len(text) <= max_utf16:
        return [text]
    chunks: list[str] = []
    buf = ""
    for line in text.split("\n"):
        candidate = line if not buf else buf + "\n" + line
        if _utf16_len(candidate) <= max_utf16:
            buf = candidate
            continue
        if buf:
            chunks.append(buf)
            buf = ""
        # Hard-wrap a single very long line by code points.
        cur = ""
        for ch in line:
            if _utf16_len(cur + ch) > max_utf16:
                chunks.append(cur)
                cur = ch
            else:
                cur += ch
        buf = cur
    if buf:
        chunks.append(buf)
    return chunks or [text]


def chunk_plain(text: Any, *, max_utf16: int = _SPLIT_LIMIT) -> list[str]:
    """Split plain text (no markdown) into chunks <= max_utf16 UTF-16 units."""
    s = "" if text is None else str(text)
    return _naive_split_utf16(s, max_utf16)


# ---------------------------------------------------------------------------
# High-level async senders — MarkdownV2 + automatic long-message splitting.
# These supersede helpers.safe_edit_text / safe_reply_text (legacy Markdown).
# ---------------------------------------------------------------------------


async def send_long_markdown(
    bot_or_message: Any,
    chat_id: int | None,
    text: str,
    *,
    reply_to: int | None = None,
    disable_web_page_preview: bool = True,
) -> list:
    """Send text as MarkdownV2, splitting into multiple messages if too long.

    ``bot_or_message``: either a ``telegram.Bot`` (then ``chat_id`` is required)
    or a ``telegram.Message`` (uses ``.reply_text``; ``chat_id`` ignored).

    Returns the list of sent Message objects (1 or more). Never raises on a
    Markdown parse error: it retries each chunk as plain text and logs the
    cause. Long content is always delivered in full (split, not truncated).
    """
    from telegram.constants import ParseMode  # type: ignore

    chunks = split_markdown_v2(text)
    sent: list = []
    msg = bot_or_message
    is_bot = hasattr(msg, "send_message") and not hasattr(msg, "reply_text")

    for i, chunk in enumerate(chunks):
        if not chunk or not chunk.strip():
            continue
        sent_msg = await _send_one(
            msg,
            chat_id=chat_id,
            text=chunk,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_to=reply_to if i == 0 else None,
            disable_web_page_preview=disable_web_page_preview,
            is_bot=is_bot,
        )
        if sent_msg is not None:
            sent.append(sent_msg)
    return sent


async def edit_long_markdown(message: Any, text: str, *, disable_web_page_preview: bool = True, reply_markup=None) -> Any:
    """Edit a message's text as MarkdownV2 (first chunk), append the rest.

    Telegram ``edit_message_text`` only edits a single message; if the new text
    exceeds the limit we edit the existing message with the first chunk and send
    the remainder as new messages in the same chat. ``reply_markup`` (optional)
    is attached to the edited message. Returns the edited message (or first sent
    message).
    """
    from telegram.constants import ParseMode  # type: ignore

    chunks = split_markdown_v2(text)
    if not chunks:
        chunks = [""]
    first = chunks[0] or ""
    edited = await _edit_one(message, first, ParseMode.MARKDOWN_V2, disable_web_page_preview, reply_markup=reply_markup)
    # Append overflow as new messages in the same chat.
    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None) if chat is not None else None
    bot = getattr(message, "bot", None) if hasattr(message, "bot") else None
    for extra in chunks[1:]:
        if not extra or not extra.strip():
            continue
        if bot is not None and chat_id is not None:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=extra,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    disable_web_page_preview=disable_web_page_preview,
                )
            except Exception:
                # Plain-text fallback for overflow chunk.
                try:
                    await bot.send_message(chat_id=chat_id, text=extra)
                except Exception:
                    logger.exception("edit_long_markdown overflow send failed")
    return edited


async def _send_one(msg, *, chat_id, text, parse_mode, reply_to, disable_web_page_preview, is_bot) -> Any:
    try:
        if is_bot:
            return await msg.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                reply_to_message_id=reply_to,
                disable_web_page_preview=disable_web_page_preview,
            )
        # Message.reply_text path
        kwargs: dict = {"parse_mode": parse_mode, "disable_web_page_preview": disable_web_page_preview}
        if reply_to is not None:
            kwargs["reply_to_message_id"] = reply_to
        return await msg.reply_text(text, **kwargs)
    except Exception as exc:
        err = str(exc).lower()
        if "can't parse" in err or "parse entities" in err or "parse entit" in err:
            logger.warning("MarkdownV2 parse failed, retrying chunk as plain text: %s", exc)
        else:
            # Non-parse error (network, chat blocked, etc.) — surface, do not hide.
            logger.exception("send_one failed (non-parse)")
            return None
        # Plain-text fallback for this chunk.
        plain = _strip_markdown(text)
        try:
            if is_bot:
                return await msg.send_message(chat_id=chat_id, text=plain, reply_to_message_id=reply_to)
            kwargs = {}
            if reply_to is not None:
                kwargs["reply_to_message_id"] = reply_to
            return await msg.reply_text(plain, **kwargs)
        except Exception:
            logger.exception("send_one plain fallback failed")
            return None


async def _edit_one(message, text, parse_mode, disable_web_page_preview, *, reply_markup=None) -> Any:
    try:
        kwargs: dict = {"parse_mode": parse_mode, "disable_web_page_preview": disable_web_page_preview}
        if reply_markup is not None:
            kwargs["reply_markup"] = reply_markup
        return await message.edit_text(text, **kwargs)
    except Exception as exc:
        err = str(exc).lower()
        if "can't parse" in err or "parse entities" in err or "parse entit" in err:
            logger.warning("MarkdownV2 edit parse failed, retrying as plain text: %s", exc)
        elif "message is not modified" in err:
            return message
        else:
            logger.exception("edit_one failed (non-parse)")
            return None
        try:
            kwargs = {}
            if reply_markup is not None:
                kwargs["reply_markup"] = reply_markup
            return await message.edit_text(_strip_markdown(text), **kwargs)
        except Exception:
            # message-not-modified on identical plain text is fine.
            if "not modified" in str(exc).lower():
                return message
            logger.exception("edit_one plain fallback failed")
            return None


def _strip_markdown(text: str) -> str:
    """Best-effort strip of MarkdownV2 escape backslashes for plain fallback."""
    # Remove the escaping backslashes we added so plain text reads cleanly.
    import re

    s = str(text or "")
    # Remove backslash before special chars, keep literal chars.
    s = re.sub(r"\\([\\\`\*\_\{\}\[\]\(\)\#\+\-\.\!\~\>\=\|])", r"\1", s)
    return s


__all__ = [
    "TELEGRAM_TEXT_LIMIT",
    "to_markdown_v2",
    "escape_markdown_v2",
    "escape_md_legacy",
    "split_markdown_v2",
    "chunk_plain",
    "send_long_markdown",
    "edit_long_markdown",
]
