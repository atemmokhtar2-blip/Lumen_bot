"""ForceReply + input_field_placeholder for free-text collection (weakness #5).

Telegram only shows a real input hint via ForceReply.input_field_placeholder
(or Mini App forms). Inline keyboards alone never populate the compose box.

Strategy:
  - Keep the main UI message + inline nav as-is.
  - Send a short companion ForceReply that opens the keyboard with a concrete
    example placeholder so the user is filling a field, not guessing.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("lumen_bot.ui.input_prompt")

# kind → (body_ar, placeholder ≤ 64 chars)
_PROMPTS: dict[str, tuple[str, str]] = {
    "bot_description": (
        "✍️ اكتب وصف البوت في الرد على هذه الرسالة:",
        "مثال: بوت متجر يرد على الطلبات والفواتير",
    ),
    "bot_name": (
        "✍️ اكتب اسم البوت:",
        "مثال: بوت المتجر الذكي",
    ),
    "slot_answer": (
        "✍️ اكتب الإجابة في الرد هنا:",
        "اكتب إجابتك باختصار…",
    ),
    "bot_token": (
        "🔑 الصق توكن البوت من @BotFather:",
        "123456789:AA…توكن_BotFather",
    ),
    "github_pat": (
        "🔑 الصق GitHub PAT (صلاحية repo):",
        "ghp_xxxxxxxx أو github_pat_…",
    ),
    "repo_name": (
        "✍️ اكتب اسم المستودع:",
        "مثال: my-telegram-shop-bot",
    ),
    "repo_url": (
        "✍️ الصق رابط المستودع:",
        "https://github.com/user/repo",
    ),
    "generic": (
        "✍️ اكتب ردك هنا:",
        "اكتب هنا…",
    ),
}


def _clip_placeholder(text: str, limit: int = 64) -> str:
    s = (text or "").strip()
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def force_reply_markup(placeholder: str, *, selective: bool = False) -> Any:
    """Build ForceReply with input_field_placeholder (Telegram Bot API)."""
    from telegram import ForceReply

    ph = _clip_placeholder(placeholder)
    try:
        return ForceReply(
            selective=selective,
            input_field_placeholder=ph or None,
        )
    except TypeError:
        # Older PTB without placeholder kw
        return ForceReply(selective=selective)


def prompt_spec(kind: str) -> tuple[str, str]:
    return _PROMPTS.get((kind or "").strip().lower()) or _PROMPTS["generic"]


async def ask_text_input(
    message: Any,
    *,
    kind: str = "generic",
    body: str | None = None,
    placeholder: str | None = None,
    bot: Any = None,
    chat_id: int | None = None,
) -> Any | None:
    """Send a ForceReply companion message so the compose box shows a hint.

    Returns the sent Message or None on failure.
    """
    default_body, default_ph = prompt_spec(kind)
    text = (body if body is not None else default_body).strip() or default_body
    ph = placeholder if placeholder is not None else default_ph
    markup = force_reply_markup(ph)

    try:
        if message is not None and hasattr(message, "reply_text"):
            return await message.reply_text(text[:500], reply_markup=markup)
        if bot is not None and chat_id is not None:
            return await bot.send_message(
                chat_id=int(chat_id),
                text=text[:500],
                reply_markup=markup,
            )
    except Exception:
        logger.exception("ask_text_input failed kind=%s", kind)
    return None


async def ask_after_ui(
    *,
    context: Any,
    msg: Any,
    kind: str,
    body: str | None = None,
    placeholder: str | None = None,
) -> None:
    """Fire ForceReply after an inline UI surface was rendered."""
    bot = getattr(context, "bot", None) if context is not None else None
    chat_id = None
    try:
        chat_id = getattr(getattr(msg, "chat", None), "id", None)
    except Exception:
        chat_id = None
    await ask_text_input(
        msg,
        kind=kind,
        body=body,
        placeholder=placeholder,
        bot=bot,
        chat_id=chat_id,
    )


__all__ = [
    "force_reply_markup",
    "prompt_spec",
    "ask_text_input",
    "ask_after_ui",
]
