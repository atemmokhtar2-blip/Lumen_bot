"""Macro discovery — surface successful infinite specs to chat / translator."""
from __future__ import annotations

from typing import Any


def list_macro_hints(*, limit: int = 10) -> list[dict[str, Any]]:
    try:
        from .macro_registry import get_macro_registry
        return get_macro_registry().list_macros(limit=limit)
    except Exception:
        return []


def macros_for_prompt(*, limit: int = 8) -> str:
    """Arabic/English bullet list for system prompts."""
    items = list_macro_hints(limit=limit)
    if not items:
        return ""
    lines = ["Known successful flow macros (prefer reusing patterns):"]
    for m in items:
        lines.append(
            f"- id={m.get('id')} name={m.get('bot_name')} "
            f"nodes={m.get('nodes')} uses={m.get('uses')} score={m.get('score')}"
        )
    return "\n".join(lines)


def suggest_macros_for_user(*, limit: int = 5) -> str:
    """Short Arabic suggestion block for chat answers."""
    items = list_macro_hints(limit=limit)
    if not items:
        return ""
    lines = ["قوالب تدفق ناجحة سابقاً (Macros):"]
    for m in items:
        lines.append(f"• {m.get('bot_name') or m.get('id')} — {m.get('nodes')} عقدة")
    return "\n".join(lines)
