"""
Structured logging facade for the generation engine.

This module provides :class:`EngineLogger`, a thin wrapper around the
standard library :mod:`logging` that:

* Reads its configuration from a :class:`~configuration.config.Configuration`
  object instead of hardcoding values.
* Guarantees that a logger exists for every component (``core``,
  ``pipeline``, ``engines``, etc.).
* Exposes convenience methods that record both a human message and a
  structured payload, useful for later analysis.
* Offers a global accessor :func:`get_logger` so any module can obtain a
  named logger without re-configuring handlers.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


class EngineLogger:
    """Centralised logging controller for the whole engine.

    The controller is created once with a configuration and then every
    module calls :meth:`get` to obtain a standard :class:`logging.Logger`.
    """

    _initialized: bool = False
    _level: int = logging.INFO
    _format: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    _log_dir: Optional[Path] = None
    _to_file: bool = True
    _to_console: bool = True
    _root_logger: Optional[logging.Logger] = None

    @classmethod
    def configure(cls, config: Any) -> None:
        """Initialise the logging system from a :class:`Configuration`.

        ``config`` is expected to expose a ``get(section, field, default)``
        method, matching the engine's :class:`Configuration` contract.
        """
        level_name = config.get("logging", "level", "INFO")
        cls._level = _LEVELS.get(str(level_name).upper(), logging.INFO)
        cls._format = config.get(
            "logging", "format",
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        )
        log_dir = config.get("logging", "log_dir", "logs")
        cls._log_dir = Path(log_dir)
        cls._to_file = bool(config.get("logging", "to_file", True))
        cls._to_console = bool(config.get("logging", "to_console", True))

        root = logging.getLogger("tbe")
        root.setLevel(cls._level)
        # Remove existing handlers so re-configuration is idempotent.
        for handler in list(root.handlers):
            root.removeHandler(handler)

        formatter = logging.Formatter(cls._format)

        if cls._to_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            root.addHandler(console_handler)

        if cls._to_file:
            cls._log_dir.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(
                cls._log_dir / "engine.log", encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)

        cls._root_logger = root
        cls._initialized = True

    @classmethod
    def get(cls, name: str) -> logging.Logger:
        """Return a configured logger under the ``tbe`` namespace."""
        if not cls._initialized:
            # Fall back to a minimal console configuration.
            root = logging.getLogger("tbe")
            if not root.handlers:
                handler = logging.StreamHandler(sys.stdout)
                handler.setFormatter(logging.Formatter(cls._format))
                root.addHandler(handler)
                root.setLevel(logging.INFO)
            cls._root_logger = root
            cls._initialized = True
        return logging.getLogger(f"tbe.{name}")

    @classmethod
    def reset(cls) -> None:
        """Reset the logging state — mainly used in tests."""
        if cls._root_logger is not None:
            for handler in list(cls._root_logger.handlers):
                cls._root_logger.removeHandler(handler)
        cls._initialized = False
        cls._root_logger = None


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

def _structured(logger: logging.Logger, level: int, message: str,
               payload: Optional[Dict[str, Any]] = None) -> None:
    """Emit a log record, appending a JSON payload when present."""
    if payload:
        logger.log(level, "%s | %s", message, json.dumps(payload, default=str))
    else:
        logger.log(level, message)


class _LoggerFacade:
    """Small adapter giving access to the structured helpers."""

    def __init__(self, logger: logging.Logger):
        self._logger = logger

    def debug(self, message: str, payload: Optional[Dict[str, Any]] = None) -> None:
        _structured(self._logger, logging.DEBUG, message, payload)

    def info(self, message: str, payload: Optional[Dict[str, Any]] = None) -> None:
        _structured(self._logger, logging.INFO, message, payload)

    def warning(self, message: str, payload: Optional[Dict[str, Any]] = None) -> None:
        _structured(self._logger, logging.WARNING, message, payload)

    def error(self, message: str, payload: Optional[Dict[str, Any]] = None) -> None:
        _structured(self._logger, logging.ERROR, message, payload)

    def critical(self, message: str, payload: Optional[Dict[str, Any]] = None) -> None:
        _structured(self._logger, logging.CRITICAL, message, payload)

    def exception(self, message: str,
                  payload: Optional[Dict[str, Any]] = None) -> None:
        self._logger.exception(message)
        if payload:
            _structured(self._logger, logging.ERROR, message, payload)


def get_logger(name: str) -> _LoggerFacade:
    """Return a :class:`_LoggerFacade` for the named component."""
    return _LoggerFacade(EngineLogger.get(name))


__all__ = ["EngineLogger", "get_logger"]
