"""Emit moderation service from deep runtime module."""
from __future__ import annotations

from pathlib import Path

from ..schema import BotSpec


def _emit_moderation() -> str:
    path = Path(__file__).resolve().parents[1] / "runtime" / "moderation_runtime.py"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"moderation_runtime missing: {path}")
