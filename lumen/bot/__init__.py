"""Telegram interface package for Lumen.

Heavy imports (handlers that need python-telegram-bot) are lazy so unit tests
can import sanitize/session_store/helpers without the telegram package.
"""

from .config import (
    TELEGRAM_BOT_TOKEN,
    ALLOWED_USER_IDS,
    ALLOW_ALL_USERS,
    LOCK_BOT_TO_ALLOWLIST,
    OUTPUT_DIR,
    PORT,
    logger,
)

__all__ = [
    "TELEGRAM_BOT_TOKEN",
    "ALLOWED_USER_IDS",
    "ALLOW_ALL_USERS",
    "LOCK_BOT_TO_ALLOWLIST",
    "OUTPUT_DIR",
    "PORT",
    "logger",
]


def __getattr__(name: str):
    if name in {
        "is_allowed",
        "chat_route",
        "detect_host_intent",
        "looks_like_bot_token",
        "escape_md",
        "safe_edit_text",
        "make_zip_from_path",
        "run_generation",
        "normalize_bot_token",
    }:
        from . import helpers as h
        return getattr(h, name)
    if name in {"handle_live_run_token", "handle_live_deploy_token"}:
        from . import live as lv
        return getattr(lv, name)
    if name in {"start_cmd", "help_cmd", "status_cmd", "lang_cmd", "referral_cmd"}:
        from . import commands as c
        return getattr(c, name)
    if name == "handle_message":
        from .messages import handle_message
        return handle_message
    if name == "start_health_server":
        from .health import start_health_server
        return start_health_server
    if name == "error_handler":
        from .errors import error_handler
        return error_handler
    if name in {"t", "get_lang", "set_lang"}:
        from . import i18n as i
        return getattr(i, name)
    raise AttributeError(name)
