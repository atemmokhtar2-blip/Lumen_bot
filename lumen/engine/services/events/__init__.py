"""Platform event bus — Redis pub/sub when available, in-process fallback."""
from __future__ import annotations

from .bus import EventBus, emit, get_bus, on, subscribe

__all__ = ["EventBus", "emit", "get_bus", "on", "subscribe"]
