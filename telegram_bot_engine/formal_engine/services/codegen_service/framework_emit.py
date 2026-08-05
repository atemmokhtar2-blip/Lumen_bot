"""
framework_emit.py — TEMPLATE PATH DELETED.

Framework wiring is emitted by formal_engine.transpiler.micro only.
"""

from __future__ import annotations

from typing import Any


class TemplatePathDisabledError(RuntimeError):
    pass


def _dead(*_a: Any, **_k: Any) -> Any:
    raise TemplatePathDisabledError(
        "Template path disabled. Use formal Micro-Transpiler / build_from_text."
    )


emit_main_aiogram = _dead
emit_main_ptb = _dead
emit_start_aiogram = _dead
emit_cmd_aiogram = _dead
emit_callbacks_aiogram = _dead
emit_messages_aiogram = _dead
normalize_framework = _dead
layer_paths_to_create = _dead
requirements_for = _dead
