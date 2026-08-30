"""Telegram presentation adapter.

Re-exports the live bot package so callers can depend on the interface layer
while the implementation remains in lumen.bot during the migration.
"""
from lumen.bot import (  # noqa: F401
    handle_message,
    start_cmd,
    help_cmd,
    status_cmd,
    error_handler,
)

__all__ = ["handle_message", "start_cmd", "help_cmd", "status_cmd", "error_handler"]
