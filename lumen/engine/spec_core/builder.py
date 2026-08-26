"""Re-export of DEFAULT_COMMANDS for capability_detection / packs.

The old Spec Builder / BuilderSession has been permanently removed.
"""
from __future__ import annotations

from .default_commands import DEFAULT_COMMANDS

__all__ = ["DEFAULT_COMMANDS"]
