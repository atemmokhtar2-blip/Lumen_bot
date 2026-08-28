"""Build Telegram InlineKeyboardMarkup from engine UiButton rows."""
from __future__ import annotations

from typing import Sequence

from lumen.engine.services.ui_state.models import UiButton

# Telegram callback_data max 64 bytes. Prefix keeps namespace closed.
_PREFIX = "lumen:ui:"


def encode_callback(action: str, arg: str = "") -> str:
    action = (action or "").strip().lower()[:32]
    arg = (arg or "").strip()[:20]
    if arg:
        data = f"{_PREFIX}{action}:{arg}"
    else:
        data = f"{_PREFIX}{action}"
    if len(data.encode("utf-8")) > 64:
        raise ValueError(f"callback_data_too_long:{len(data)}")
    return data


def decode_callback(data: str) -> tuple[str, str] | None:
    raw = (data or "").strip()
    if not raw.startswith(_PREFIX):
        return None
    rest = raw[len(_PREFIX) :]
    if not rest:
        return None
    if ":" in rest:
        action, arg = rest.split(":", 1)
        return action.strip().lower(), arg.strip()
    return rest.strip().lower(), ""


def build_inline_keyboard(rows: Sequence[Sequence[UiButton]]):
    """Return telegram.InlineKeyboardMarkup (import localized to avoid hard dep at import in tests)."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    kb: list[list[InlineKeyboardButton]] = []
    for row in rows:
        line: list[InlineKeyboardButton] = []
        for btn in row:
            line.append(
                InlineKeyboardButton(
                    text=btn.text[:64],
                    callback_data=encode_callback(btn.action, btn.arg),
                )
            )
        if line:
            kb.append(line)
    return InlineKeyboardMarkup(kb)
