"""Emit tasks + notes services — prefers deep runtime module."""
from __future__ import annotations

from pathlib import Path

from ..schema import BotSpec


def _tasks_source() -> str:
    path = Path(__file__).resolve().parents[1] / "runtime" / "tasks_runtime.py"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"tasks_runtime missing: {path}")


def _emit_tasks() -> str:
    return _tasks_source()


def _emit_notes() -> str:
    """Notes share tasks_runtime (add_note/list_notes/delete_note/format_notes)."""
    return _tasks_source()
