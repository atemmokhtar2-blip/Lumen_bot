"""Emit app/sentry_setup.py for generated bots."""
from __future__ import annotations


def emit_sentry_setup() -> str:
    return '''"""Sentry error tracking for this generated bot.

Activate by setting SENTRY_DSN in the environment.
Never required — bot runs normally without it.
Tokens and secrets are scrubbed before send.
"""
from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"\\b\\d{6,}:[A-Za-z0-9_-]{20,}\\b")
_SECRET_KEY_RE = re.compile(
    r"(?i)(token|password|secret|authorization|api[_-]?key|bot_token)"
)
_ready = False


def _scrub(value):
    if isinstance(value, str):
        return _TOKEN_RE.sub("[TELEGRAM_TOKEN_REDACTED]", value)
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if _SECRET_KEY_RE.search(str(k)):
                out[str(k)] = "[REDACTED]"
            else:
                out[str(k)] = _scrub(v)
        return out
    if isinstance(value, (list, tuple)):
        return type(value)(_scrub(x) for x in value)
    return value


def _before_send(event, hint):
    try:
        return _scrub(event)
    except Exception:
        return event


def init_sentry(bot_name: str = "generated-bot") -> bool:
    global _ready
    if _ready:
        return bool((os.getenv("SENTRY_DSN") or "").strip())
    _ready = True
    dsn = (os.getenv("SENTRY_DSN") or "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration
    except ImportError:
        logger.warning("SENTRY_DSN set but sentry-sdk not installed")
        return False
    try:
        traces = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE") or "0.0")
    except Exception:
        traces = 0.0
    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=(os.getenv("SENTRY_ENVIRONMENT") or "production").strip(),
            release=(os.getenv("SENTRY_RELEASE") or "").strip() or None,
            traces_sample_rate=max(0.0, min(1.0, traces)),
            send_default_pii=False,
            before_send=_before_send,
            integrations=[LoggingIntegration(level=logging.ERROR, event_level=logging.ERROR)],
        )
        sentry_sdk.set_tag("bot_name", (bot_name or "generated-bot")[:80])
        uid = (os.getenv("TBE_OWNER_USER_ID") or "").strip()
        if uid:
            sentry_sdk.set_tag("owner_user_id", uid[:32])
        logger.info("sentry active for bot")
        return True
    except Exception as exc:
        logger.warning("sentry init failed: %s", exc)
        return False


async def ptb_error_handler(update, context) -> None:
    """python-telegram-bot global error handler — reports to Sentry + logs."""
    err = getattr(context, "error", None)
    logger.exception("handler error: %s", err)
    dsn = (os.getenv("SENTRY_DSN") or "").strip()
    if not dsn or err is None:
        return
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            try:
                user = update.effective_user if update is not None else None
                if user is not None:
                    scope.set_user({"id": str(getattr(user, "id", ""))})
                chat = update.effective_chat if update is not None else None
                if chat is not None:
                    scope.set_tag("chat_id", str(getattr(chat, "id", "")))
            except Exception:
                pass
            sentry_sdk.capture_exception(err)
    except Exception:
        logger.debug("sentry capture failed", exc_info=True)
'''
