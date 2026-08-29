"""Configure Telegram chat Menu Button → Mini App secrets (when PUBLIC_BASE_URL set)."""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("lumen_bot.ui.menu_button")


def secrets_menu_url() -> str | None:
    base = (os.getenv("PUBLIC_BASE_URL") or os.getenv("WEB_APP_URL") or "").strip().rstrip("/")
    if not base.startswith("https://"):
        return None
    return f"{base}/secrets?kind=bot"


async def configure_menu_button(bot, *, chat_id: int | None = None) -> bool:
    """Set MenuButtonWebApp globally or per chat. Returns True on success."""
    url = secrets_menu_url()
    if not url or bot is None:
        return False
    try:
        from telegram import MenuButtonWebApp, WebAppInfo
        button = MenuButtonWebApp(text="🔐 أسرار آمنة", web_app=WebAppInfo(url=url))
        await bot.set_chat_menu_button(chat_id=chat_id, menu_button=button)
        return True
    except Exception:
        logger.exception("set_chat_menu_button failed")
        return False
