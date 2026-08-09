"""Smart context engine — link current request to this user's prior work.

No fixed user-facing scripts. Resolution is dynamic from memory + sandbox index.
"""

from .service import ContextResolution, resolve_context, get_context_engine

__all__ = ["ContextResolution", "resolve_context", "get_context_engine"]
