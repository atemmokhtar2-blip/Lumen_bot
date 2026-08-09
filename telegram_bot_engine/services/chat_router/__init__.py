"""Chat router — natural language → formal path only. Never writes code."""

from .service import (
    Capability,
    ChatRoute,
    ChatRouter,
    get_router,
    route_message,
)

__all__ = [
    "Capability",
    "ChatRoute",
    "ChatRouter",
    "get_router",
    "route_message",
]
