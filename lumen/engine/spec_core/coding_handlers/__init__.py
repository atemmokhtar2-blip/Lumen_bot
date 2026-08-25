"""Split coding_handlers package — public emit API."""
from __future__ import annotations

from .keyboards import _emit_keyboards
from .handlers import _emit_handlers
from .main_emit import _emit_main
from .scaffold import _emit_requirements, _emit_env, _emit_readme
from .market_lines import _market_handler_lines

__all__ = [
    "_emit_keyboards",
    "_emit_handlers",
    "_emit_main",
    "_emit_requirements",
    "_emit_env",
    "_emit_readme",
    "_market_handler_lines",
]
