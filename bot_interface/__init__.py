"""Telegram interface package for AI Agent 7h Bot."""

from .config import (
    TELEGRAM_BOT_TOKEN,
    ALLOWED_USER_IDS,
    ALLOW_ALL_USERS,
    OUTPUT_DIR,
    PORT,
    logger,
)
from .helpers import (
    is_allowed,
    chat_route,
    detect_host_intent,
    looks_like_bot_token,
    escape_md,
    safe_edit_text,
    make_zip_from_path,
    run_generation,
)
from .live import handle_live_run_token, handle_live_deploy_token
from .commands import start_cmd, help_cmd, status_cmd, lang_cmd
from .messages import handle_message
from .health import start_health_server
from .errors import error_handler
from .i18n import t, get_lang, set_lang

__all__ = [
    "TELEGRAM_BOT_TOKEN",
    "ALLOWED_USER_IDS",
    "ALLOW_ALL_USERS",
    "OUTPUT_DIR",
    "PORT",
    "logger",
    "is_allowed",
    "chat_route",
    "detect_host_intent",
    "looks_like_bot_token",
    "escape_md",
    "safe_edit_text",
    "make_zip_from_path",
    "run_generation",
    "handle_live_run_token",
    "handle_live_deploy_token",
    "start_cmd",
    "help_cmd",
    "status_cmd",
    "lang_cmd",
    "handle_message",
    "start_health_server",
    "error_handler",
    "t",
    "get_lang",
    "set_lang",
]
