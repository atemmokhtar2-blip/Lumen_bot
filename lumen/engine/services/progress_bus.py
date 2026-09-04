"""Process-wide generation progress bus (no Telegram imports).

Handlers are stacked so nested set/reset (heartbeat outer + worker thread)
cannot wipe an active outer sink mid-generation.
"""
from __future__ import annotations

import contextvars
import threading
from typing import Any, Callable, Optional

ProgressHandler = Callable[[dict[str, Any]], None]

_ctx_handler: contextvars.ContextVar[Optional[ProgressHandler]] = contextvars.ContextVar(
    "lumen_progress_handler", default=None
)
_local = threading.local()
_global_lock = threading.Lock()
_handler_stack: list[ProgressHandler] = []


def set_progress_handler(handler: ProgressHandler | None) -> contextvars.Token:
    """Push handler onto the stack and activate it for this context + thread."""
    token = _ctx_handler.set(handler)
    _local.handler = handler
    if handler is not None:
        with _global_lock:
            _handler_stack.append(handler)
    return token


def reset_progress_handler(token: contextvars.Token) -> None:
    """Pop matching handler; restore previous if any remain."""
    try:
        current = _ctx_handler.get()
    except Exception:
        current = None
    try:
        _ctx_handler.reset(token)
    except Exception:
        pass
    _local.handler = _ctx_handler.get()
    if current is not None:
        with _global_lock:
            # Remove last occurrence of this handler
            for i in range(len(_handler_stack) - 1, -1, -1):
                if _handler_stack[i] is current:
                    _handler_stack.pop(i)
                    break


def report_progress(event: dict[str, Any] | None) -> None:
    """Emit to the most specific active handler. Never raises."""
    if not event or not isinstance(event, dict):
        return
    handler = _ctx_handler.get()
    if handler is None:
        handler = getattr(_local, "handler", None)
    if handler is None:
        with _global_lock:
            handler = _handler_stack[-1] if _handler_stack else None
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
