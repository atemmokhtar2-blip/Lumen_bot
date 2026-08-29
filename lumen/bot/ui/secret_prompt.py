"""Professional secret prompts (2026).

Order of preference:
  1) Telegram Mini App (WebApp button) when PUBLIC_BASE_URL is configured —
     secrets never transit chat history.
  2) Chat paste + immediate deleteMessage scrub (token_hygiene).

WebApp URL must be HTTPS and registered with BotFather. The page itself is
served by the existing web/ control plane under /secrets when available.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("lumen_bot.ui.secret_prompt")


def _public_base() -> str:
    return (os.getenv("PUBLIC_BASE_URL") or os.getenv("WEB_APP_URL") or "").strip().rstrip("/")


def secrets_web_url(*, kind: str = "bot") -> str | None:
    base = _public_base()
    if not base.startswith("https://"):
        return None
    k = (kind or "bot").strip().lower()
    if k not in {"bot", "github", "pat"}:
        k = "bot"
    return f"{base}/secrets?kind={k}"


def build_secret_prompt_markup(*, kind: str, user_id: int = 0) -> Any | None:
    """Inline keyboard: optional WebApp + always a chat fallback note is in text."""
    url = secrets_web_url(kind=kind)
    if not url:
        return None
    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

        label = "🔐 فتح لوحة الإدخال الآمنة"
        btn = InlineKeyboardButton(text=label, web_app=WebAppInfo(url=url))
        return InlineKeyboardMarkup([[btn]])
    except Exception:
        logger.exception("web_app keyboard build failed")
        return None


async def prompt_for_secret(
    *,
    message: Any,
    kind: str,
    body: str,
    user_id: int = 0,
) -> Any:
    """Send a secret request with WebApp button when available."""
    markup = build_secret_prompt_markup(kind=kind, user_id=user_id)
    extra = ""
    if markup is not None:
        extra = (
            "\n\nالأفضل: افتح اللوحة الآمنة بالزر أدناه (لا يمر السر عبر الدردشة).\n"
            "أو الصق هنا — سيتم حذف رسالتك فوراً بعد الاستلام."
        )
    else:
        extra = "\n\nالصق السر هنا — سيتم حذف رسالتك فوراً بعد الاستلام وتشفيره."
    text = (body or "").rstrip() + extra
    return await message.reply_text(text[:4000], reply_markup=markup)
