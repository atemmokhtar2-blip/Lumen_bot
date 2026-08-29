"""Secure handling of secrets pasted into Telegram chat.

World-class pattern (2025–2026):
  1. Never echo the secret back to the user.
  2. Delete the user's message that contained the secret (Bot API:
     bots can delete incoming messages in private chats).
  3. Confirm receipt without residual plaintext in chat history.
  4. Downstream layers already encrypt at rest (Fernet / TBE_TOKEN_SECRET).

Limitation (Telegram):
  - deleteMessage only works within ~48h and requires the bot to be able
    to delete that message (private chat: yes for incoming).
  - Users can still screenshot; this reduces residual risk in chat logs.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("lumen_bot.ui.token_hygiene")

_CONFIRM_AR = (
    "✅ تم استلام السر وتشفيره بأمان.\n"
    "تم حذف رسالتك التي تحتوي عليه من هذه المحادثة."
)
_CONFIRM_AR_PARTIAL = (
    "✅ تم استلام السر وتشفيره بأمان.\n"
    "تعذّر حذف رسالتك تلقائياً — احذفها يدوياً من المحادثة فوراً."
)


async def scrub_secret_message(
    *,
    bot: Any,
    chat_id: int,
    message_id: int | None,
    is_private: bool = True,
) -> bool:
    """Best-effort delete of the user's secret-bearing message.

    Returns True if Telegram confirmed deletion.
    """
    if not bot or not message_id or int(message_id) <= 0:
        return False
    if not is_private:
        # Groups: only admins with can_delete_messages — skip to avoid noise
        return False
    try:
        await bot.delete_message(chat_id=int(chat_id), message_id=int(message_id))
        return True
    except Exception as exc:
        logger.info(
            "secret message delete failed chat=%s mid=%s err=%s",
            chat_id,
            message_id,
            type(exc).__name__,
        )
        return False


async def confirm_secret_received(
    *,
    reply_target: Any,
    deleted: bool,
) -> None:
    """Send a short confirmation that does not contain any secret material."""
    text = _CONFIRM_AR if deleted else _CONFIRM_AR_PARTIAL
    try:
        await reply_target.reply_text(text)
    except Exception:
        logger.exception("confirm_secret_received failed")


async def scrub_and_confirm(
    *,
    update_message: Any,
    bot: Any | None = None,
) -> bool:
    """Delete the user message that carried a token/PAT and confirm.

    Call this *after* the secret has been handed to the engine (hosting /
    clone / create) so a failed engine call still leaves no secret in chat
    when possible.
    """
    if update_message is None:
        return False
    chat = getattr(update_message, "chat", None)
    chat_id = getattr(chat, "id", None)
    mid = getattr(update_message, "message_id", None)
    chat_type = (getattr(chat, "type", None) or "").lower()
    is_private = chat_type in {"private", "sender"}
    bot_obj = bot
    if bot_obj is None:
        get_bot = getattr(update_message, "get_bot", None)
        if callable(get_bot):
            try:
                bot_obj = get_bot()
            except Exception:
                bot_obj = None
    deleted = await scrub_secret_message(
        bot=bot_obj,
        chat_id=int(chat_id or 0),
        message_id=int(mid) if mid else None,
        is_private=is_private,
    )
    await confirm_secret_received(reply_target=update_message, deleted=deleted)
    return deleted
