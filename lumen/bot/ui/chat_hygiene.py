"""Strict chat hygiene — max N bot UI messages; prefer edit; auto-delete excess."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("lumen_bot.ui.chat_hygiene")

_KEY = "lumen_bot_ui_msg_ids"
_MAX_BOT_UI_MSGS = 1  # hard: only current surface


def _ids(user_data: dict[str, Any] | None) -> list[int]:
    if not isinstance(user_data, dict):
        return []
    raw = user_data.get(_KEY) or []
    out: list[int] = []
    for x in raw:
        try:
            out.append(int(x))
        except Exception:
            continue
    return out


def remember_message(user_data: dict[str, Any] | None, message_id: int | None) -> None:
    if not isinstance(user_data, dict) or message_id is None:
        return
    try:
        mid = int(message_id)
    except Exception:
        return
    ids = [i for i in _ids(user_data) if i != mid]
    ids.append(mid)
    user_data[_KEY] = ids[-20:]  # cap tracker


async def prune_bot_messages(
    bot,
    chat_id: int,
    user_data: dict[str, Any] | None,
    *,
    keep: int = _MAX_BOT_UI_MSGS,
    protect: int | None = None,
) -> None:
    """Delete oldest tracked bot UI messages beyond ``keep``."""
    if not bot or not isinstance(user_data, dict):
        return
    ids = _ids(user_data)
    if len(ids) <= keep:
        return
    drop, keep_ids = ids[: len(ids) - keep], ids[len(ids) - keep :]
    for mid in drop:
        if protect and mid == int(protect):
            continue
        try:
            await bot.delete_message(chat_id=int(chat_id), message_id=int(mid))
        except Exception:
            logger.debug("delete_message failed mid=%s", mid, exc_info=True)
    user_data[_KEY] = keep_ids


async def send_or_edit_ui(
    *,
    bot,
    chat_id: int,
    user_data: dict[str, Any] | None,
    text: str,
    markup=None,
    preferred_message=None,
) -> Any:
    """Prefer edit (text or caption); never hang; always leave one surface.

    UI bodies that contain official Telegram HTML (``<blockquote expandable>``
    blue cards) are sent with parse_mode=HTML so clients show the collapse arrow.
    """
    from lumen.bot.telegram_text import (
        TELEGRAM_MAX_MESSAGE,
        looks_like_telegram_html,
        looks_like_telegram_mdv2,
        split_telegram_text,
        strip_markdown_noise,
    )

    raw = text or ""
    use_mdv2 = looks_like_telegram_mdv2(raw)
    use_html = (not use_mdv2) and looks_like_telegram_html(raw)
    parse_kwargs: dict[str, Any] = {}
    if use_mdv2:
        try:
            from telegram.constants import ParseMode

            parse_kwargs["parse_mode"] = ParseMode.MARKDOWN_V2
        except Exception:
            use_mdv2 = False
            use_html = looks_like_telegram_html(raw)
    if use_html and not parse_kwargs:
        try:
            from telegram.constants import ParseMode

            parse_kwargs["parse_mode"] = ParseMode.HTML
        except Exception:
            use_html = False

    parts = split_telegram_text(raw, limit=TELEGRAM_MAX_MESSAGE - 8)
    body = parts[0] if parts else ""
    if len(parts) > 1:
        if use_html:
            body = body.rstrip() + "\n…"
        else:
            body = body.rstrip() + "\n…(المزيد في الرسائل التالية)"
    cap = strip_markdown_noise(body)[:1024] if use_html else body[:1024]
    ud = user_data if isinstance(user_data, dict) else {}

    async def _ok_edit(mid) -> Any:
        remember_message(ud, mid)
        await prune_bot_messages(bot, chat_id, ud, protect=mid)
        return preferred_message

    # 1) preferred message (callback source)
    if preferred_message is not None:
        mid = getattr(preferred_message, "message_id", None)
        has_text = bool(getattr(preferred_message, "text", None))
        has_photo = bool(getattr(preferred_message, "photo", None))
        has_cap = getattr(preferred_message, "caption", None) is not None or has_photo
        try:
            if has_text and not has_photo:
                await preferred_message.edit_text(
                    text=body, reply_markup=markup, **parse_kwargs
                )
                return await _ok_edit(mid)
            if has_photo or has_cap:
                # Captions: prefer plain (HTML blockquotes are poor in captions)
                await preferred_message.edit_caption(
                    caption=cap, reply_markup=markup
                )
                return await _ok_edit(mid)
        except Exception:
            logger.debug("preferred edit failed mid=%s", mid, exc_info=True)
            # Photo cannot change to pure text via edit_caption only if media locked —
            # fall through to delete+send

    # 2) try edit latest tracked id as text then caption
    ids = _ids(ud)
    if ids and bot:
        last = ids[-1]
        for editor in ("text", "caption"):
            try:
                if editor == "text":
                    await bot.edit_message_text(
                        chat_id=int(chat_id),
                        message_id=int(last),
                        text=body,
                        reply_markup=markup,
                        **parse_kwargs,
                    )
                else:
                    await bot.edit_message_caption(
                        chat_id=int(chat_id),
                        message_id=int(last),
                        caption=cap,
                        reply_markup=markup,
                    )
                remember_message(ud, last)
                await prune_bot_messages(bot, chat_id, ud, protect=last)
                return None
            except Exception:
                continue

    # 3) send fresh text surface, delete old tracked
    if not bot:
        return None
    try:
        sent = await bot.send_message(
            chat_id=int(chat_id),
            text=body,
            reply_markup=markup,
            **parse_kwargs,
        )
        mid = getattr(sent, "message_id", None)
        remember_message(ud, mid)
        # Spill overflow as follow-up (plain; HTML cards should fit one message)
        for extra in parts[1:]:
            try:
                follow = await bot.send_message(chat_id=int(chat_id), text=extra)
                remember_message(ud, getattr(follow, "message_id", None))
            except Exception:
                logger.exception("overflow follow-up send failed")
        await prune_bot_messages(bot, chat_id, ud, protect=mid)
        return sent
    except Exception:
        # HTML parse failure → plain fallback once
        if parse_kwargs:
            try:
                plain = strip_markdown_noise(body)[:TELEGRAM_MAX_MESSAGE]
                sent = await bot.send_message(
                    chat_id=int(chat_id),
                    text=plain,
                    reply_markup=markup,
                )
                mid = getattr(sent, "message_id", None)
                remember_message(ud, mid)
                await prune_bot_messages(bot, chat_id, ud, protect=mid)
                return sent
            except Exception:
                pass
        logger.exception("send_or_edit_ui send failed chat=%s", chat_id)
        return None
