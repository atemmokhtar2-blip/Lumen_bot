"""
Logging package for the Telegram Bot Generation Engine.

Every action performed by the engine is recorded through this package so
that the cause of any problem can be traced after the fact.  The package
wraps the standard :mod:`logging` module with a thin, engine-specific
facade that integrates with the :class:`Configuration` system.
"""

from .logger import EngineLogger, get_logger

__all__ = ["EngineLogger", "get_logger"]
