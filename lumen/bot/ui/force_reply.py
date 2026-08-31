"""ForceReply prompt with input_field_placeholder (Weakness 5 fix).

When the bot asks the user to type something (bot description, slot value,
bot name, API key, etc.), we send a short follow-up message with
``ForceReply`` + ``input_field_placeholder`` so Telegram shows a grayed-out
hint in the input field — the user feels like filling a form instead of
guessing what to type.

The inline keyboard (with bottom nav) remains on the previous message, so
the user can still navigate while the reply prompt is active.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("lumen_bot.ui.force_reply")

# Arabic placeholder hints per context (slot name → example hint).
_PLACEHOLDER_HINTS: dict[str, str] = {
    "bot_description": "مثال: بوت يرحب بالمستخدمين ويرد على الأسئلة الشائعة",
    "bot_name": "مثال: MyWeatherBot",
    "bot_username": "مثال: my_weather_bot",
    "bot_token": "الصق التوكن من @BotFather",
    "github_token": "الصق GitHub PAT (ghp_...)",
    "api_key": "الصق مفتاح API هنا",
    "webhook_url": "مثال: https://example.com/webhook",
    "channel_name": "مثال: @my_channel",
    "admin_id": "مثال: 123456789",
    "language": "مثال: العربية أو English",
    "timezone": "مثال: Asia/Riyadh",
    "welcome_message": "مثال: أهلاً بك! كيف أساعدك؟",
}


def _placeholder_for(slot: str | None, phase: str | None) -> str:
    """Pick the most relevant placeholder hint for the current input context."""
    if slot and slot in _PLACEHOLDER_HINTS:
        return _PLACEHOLDER_HINTS[slot]
    if phase == "gen_type":
        return _PLACEHOLDER_HINTS["bot_description"]
    # Generic fallback for unknown slots
    return "اكتب إجابتك هنا…"


async def send_force_reply_prompt(
    *,
    bot: Any,
    chat_id: int,
    prompt_text: str,
    slot: str | None = None,
    phase: str | None = None,
) -> None:
    """Send a ForceReply message with an input_field_placeholder (Weakness 5).

    This makes Telegram show a grayed-out hint in the user's text input field,
    so the user knows exactly what to type — like filling a form.
    """
    try:
        from telegram import ForceReply

        placeholder = _placeholder_for(slot, phase)[:64]  # Telegram limit
        reply_markup = ForceReply(
            input_field_placeholder=placeholder,
            selective=False,
        )
        await bot.send_message(
            chat_id=int(chat_id),
            text=(prompt_text or "اكتب إجابتك:")[:4000],
            reply_markup=reply_markup,
        )
    except Exception:
        logger.debug("send_force_reply_prompt failed", exc_info=True)


def should_send_force_reply(state: Any) -> bool:
    """True if the current UI state is awaiting free-text input from the user."""
    try:
        return (
            getattr(state, "phase", None) is not None
            and getattr(state.slots, "get", None) is not None
            and state.slots.get("awaiting_text") == "1"
        )
    except Exception:
        return False


__all__ = ["send_force_reply_prompt", "should_send_force_reply"]
