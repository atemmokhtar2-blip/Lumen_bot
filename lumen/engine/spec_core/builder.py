"""Compatibility shim — full Spec Builder was purged.

Only DEFAULT_COMMANDS remains for capability_detection / packs.
"""
from __future__ import annotations

from .default_commands import DEFAULT_COMMANDS

class BuilderSession:  # noqa: D101
    def __init__(self, *a, **k):
        raise RuntimeError("deterministic_engine_purged: BuilderSession removed")

__all__ = ["DEFAULT_COMMANDS", "BuilderSession"]
