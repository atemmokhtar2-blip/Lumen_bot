"""
Error hierarchy for the generation engine.

All exceptions raised by the engine derive from a single base class so
that callers can catch ``EngineError`` to handle any engine failure,
while still being able to distinguish specific failure categories when
needed.
"""

from __future__ import annotations


class EngineError(Exception):
    """Base exception for every error produced by the engine."""


class ConfigurationError(EngineError):
    """Raised when the configuration is invalid or incomplete."""


class PipelineError(EngineError):
    """Raised when the pipeline cannot proceed."""


class EngineExecutionError(EngineError):
    """Raised when an :class:`~core.contracts.Engine` fails to run."""


class BuilderError(EngineError):
    """Raised when a :class:`~core.contracts.Builder` fails to build."""


class ValidationError(EngineError):
    """Raised when a :class:`~core.contracts.Validator` detects errors."""

    def __init__(self, message: str, report=None):
        super().__init__(message)
        self.report = report


__all__ = [
    "EngineError",
    "ConfigurationError",
    "PipelineError",
    "EngineExecutionError",
    "BuilderError",
    "ValidationError",
]
