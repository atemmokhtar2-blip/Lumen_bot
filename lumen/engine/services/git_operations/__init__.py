"""Git operations used by the bot (clone / push / pull / create).

Moved out of the deleted legacy generators package.
"""
from __future__ import annotations

from . import smart_clone, smart_git

__all__ = ["smart_clone", "smart_git"]
