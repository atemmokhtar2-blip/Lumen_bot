"""
behavior.py — TEMPLATE PATH DELETED.

All code emission is owned by formal_engine.transpiler.micro (Micro-Transpiler).
Any call into this module is a programming error.
"""

from __future__ import annotations

from typing import Any


class TemplatePathDisabledError(RuntimeError):
    """Raised when legacy template emission is attempted."""


def _dead(*_a: Any, **_k: Any) -> Any:
    raise TemplatePathDisabledError(
        "Template path disabled. Use formal_engine.pipeline_formal.build_from_text / Micro-Transpiler."
    )


# legacy names → hard fail
resolve_service_for_command = _dead
primary_entity_snake = _dead
emit_rich_service = _dead
emit_messages_ptb = _dead
emit_messages_aiogram = _dead
emit_cmd_aiogram = _dead
emit_callbacks_aiogram = _dead
snake_entity = _dead
