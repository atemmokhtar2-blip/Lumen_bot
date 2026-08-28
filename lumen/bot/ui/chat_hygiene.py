"""Strict bot-message hygiene — max N bot UI messages per chat, auto-delete excess.

Telegram has no server-side "replace chat history". The strong pattern used by
production bots is: edit-in-place when possible, otherwise send one new message
and delete older bot messages so the thread stays clean (hard cap = 2).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("lumen_bot.ui.hygiene")

_KEY = "lumen_ui_msg_ids"
_MAX_BOT_UI_MSGS = 2  # hard product rule


def _ids(user_data: dict[str, Any] | None) -> list[int]:
    if not isinstance(user_data, dict):
        return []
    raw = user_data.get(_KEY)
    if not isinstance(raw, list):
        return []
    out: list[int] = []
    for x in raw:
        try:
            out.append(int(x))
        except Exception:
            continue
    return out


def remember_message(user_data: dict[str, Any] | None, message_id: int | None) -> None:
    if not isinstance(user_data, dict) or not message_id:
        return
    ids = _ids(user_data)
    mid = int(message_id)
    if mid in ids:
        # move to end (most recent)
        ids = [x for x in ids if x != mid] + [mid]
    else:
        ids.append(mid)
    user_data[_KEY] = ids[-20:]  # keep a small tail for delete attempts


async def prune_bot_messages(
    bot,
    chat_id: int,
    user_data: dict[str, Any] | None,
    *,
    keep: int = _MAX_BOT_UI_MSGS,
    protect: int | None = None,
) -> None:
    """Delete oldest tracked bot messages until only ``keep`` remain.

    ``protect`` message_id is never deleted (current UI surface).
    """
    if not isinstance(user_data, dict) or not bot or not chat_id:
        return
    ids = _ids(user_data)
    if protect:
        ids = [x for x in ids if x != int(protect)] + [int(protect)]
    # keep the newest `keep` messages
    if len(ids) <= keep:
        user_data[_KEY] = ids
        return
    drop, keep_ids = ids[: len(ids) - keep], ids[len(ids) - keep :]
    for mid in drop:
        if protect and mid == int(protect):
            continue
        try:
            await bot.delete_message(chat_id=int(chat_id), message_id=int(mid))
        except Exception:
            # already gone / too old / no permission — drop from tracker
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
    """Prefer edit of preferred/latest UI message; else send and prune to max 2."""
    body = (text or "")[:4000]
    ud = user_data if isinstance(user_data, dict) else {}

    # 1) try edit preferred (callback source)
    if preferred_message is not None:
        mid = getattr(preferred_message, "message_id", None)
        try:
            has_text = bool(getattr(preferred_message, "text", None))
            has_cap = getattr(preferred_message, "caption", None) is not None
            if has_text:
                await preferred_message.edit_text(text=body, reply_markup=markup)
                remember_message(ud, mid)
                await prune_bot_messages(bot, chat_id, ud, protect=mid)
                return preferred_message
            if has_cap:
                await preferred_message.edit_caption(caption=body[:1024], reply_markup=markup)
                remember_message(ud, mid)
                await prune_bot_messages(bot, chat_id, ud, protect=mid)
                return preferred_message
        except Exception:
            logger.debug("preferred edit failed", exc_info=True)

    # 2) try edit latest tracked id
    ids = _ids(ud)
    if ids and bot:
        last = ids[-1]
        try:
            await bot.edit_message_text(
                chat_id=int(chat_id),
                message_id=int(last),
                text=body,
                reply_markup=markup,
            )
            remember_message(ud, last)
            await prune_bot_messages(bot, chat_id, ud, protect=last)
            return None
        except Exception:
            try:
                await bot.edit_message_caption(
                    chat_id=int(chat_id),
                    message_id=int(last),
                    caption=body[:1024],
                    reply_markup=markup,
                )
                remember_message(ud, last)
                await prune_bot_messages(bot, chat_id, ud, protect=last)
                return None
            except Exception:
                logger.debug("tracked edit failed mid=%s", last, exp_info=True) if False else logger.debug(
                    "tracked edit failed mid=%s", last, exc_info=True
                )

    # 3) send new + prune hard to max 2
    if preferred_message is not None:
        try:
            sent = await preferred_message.reply_text(body, reply_markup=markup)
            remember_message(ud, getattr(sent, "message_id", None))
            await prune_bot_messages(bot, chat_id, ud, protect=getattr(sent, "message_id", None))
            return sent
        except Exception:
            logger.exception("reply_text failed")
    if bot:
        sent = await bot.send_message(chat_id=int(chat_id), text=body, reply_markup=markup)
        remember_message(ud, getattr(sent, "message_id", None))
        await prune_bot_messages(bot, chat_id, ud, protect=getattr(sent, "message_id", None))
        return sent
    return None
