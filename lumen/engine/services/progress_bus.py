"""Process-wide generation progress bus (zero Telegram/bot dependencies).

Used by cline agent_loop, multi-agent coding path, and the Telegram UI layer.
The UI installs a sink for the duration of a generation; the engine only emits.

Why not import lumen.bot from the agent?
  Importing lumen.bot pulls config/secrets and can fail or side-effect during
  generation. This module stays dependency-light so every tool step can report.
"""
from __future__ import annotations

import contextvars
import threading
from typing import Any, Callable, Optional

ProgressHandler = Callable[[dict[str, Any]], None]

_ctx_handler: contextvars.ContextVar[Optional[ProgressHandler]] = contextvars.ContextVar(
    "lumen_progress_handler", default=None
)
# Fallback when contextvars are not copied into a worker thread
_local = threading.local()
_global_lock = threading.Lock()
_global_handler: Optional[ProgressHandler] = None


def set_progress_handler(handler: ProgressHandler | None) -> contextvars.Token:
    """Install handler for this context; also mirrors to thread-local + process global."""
    global _global_handler
    token = _ctx_handler.set(handler)
    _local.handler = handler
    with _global_lock:
        _global_handler = handler
    return token


def reset_progress_handler(token: contextvars.Token) -> None:
    global _global_handler
    try:
        _ctx_handler.reset(token)
    except Exception:
        pass
    _local.handler = None
    with _global_lock:
        _global_handler = None


def report_progress(event: dict[str, Any] | None) -> None:
    """Emit a progress event to the active handler (if any). Never raises."""
    if not event or not isinstance(event, dict):
        return
    handler = _ctx_handler.get()
    if handler is None:
        handler = getattr(_local, "handler", None)
    if handler is None:
        with _global_lock:
            handler = _global_handler
    if handler is None:
        return
    try:
        handler(dict(event))
    except Exception:
        pass


__all__ = [
    "report_progress",
    "set_progress_handler",
    "reset_progress_handler",
]
