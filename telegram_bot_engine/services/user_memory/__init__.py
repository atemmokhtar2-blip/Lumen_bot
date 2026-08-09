"""Per-user persistent memory — conversation + project context.

No fixed bot templates. Memory only stores what the user actually did/said.
"""

from .service import UserMemory, get_user_memory

__all__ = ["UserMemory", "get_user_memory"]
