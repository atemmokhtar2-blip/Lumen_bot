"""Build Telegram InlineKeyboardMarkup from engine UiButton rows.

Colored buttons use Bot API 9.4 ``style`` field:
  primary → blue (main actions)
  success → green (positive / create / confirm)
  danger  → red (cancel / destructive)

Requires python-telegram-bot >= 22.7 and a Telegram client after 2026-02-09.
Older clients ignore ``style`` and still show a working button.
"""
from __future__ import annotations

from typing import Sequence

from lumen.engine.services.ui_state.models import UiButton

# Telegram callback_data max 64 bytes. Prefix keeps namespace closed.
_PREFIX = "lumen:ui:"

_VALID_STYLES = frozenset({"primary", "success", "danger"})


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


def _normalize_style(raw: str) -> str | None:
    s = (raw or "").strip().lower()
    if s in {"blue"}:
        s = "primary"
    elif s in {"green"}:
        s = "success"
    elif s in {"red"}:
        s = "danger"
    if s in _VALID_STYLES:
        return s
    return None


def _make_inline_button(btn: UiButton):
    """Build InlineKeyboardButton with native color style when supported."""
    from telegram import InlineKeyboardButton

    text = (btn.text or "")[:64]
    callback_data = encode_callback(btn.action, btn.arg)
    style = _normalize_style(getattr(btn, "style", "") or "")

    # Preferred: PTB 22.7+ named ``style`` parameter
    if style:
        try:
            return InlineKeyboardButton(
                text=text,
                callback_data=callback_data,
                style=style,
            )
        except TypeError:
            # Older PTB: force style through api_kwargs so Telegram still receives it
            try:
                return InlineKeyboardButton(
                    text=text,
                    callback_data=callback_data,
                    api_kwargs={"style": style},
                )
            except TypeError:
                pass
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def build_inline_keyboard(rows: Sequence[Sequence[UiButton]]):
    """Return telegram.InlineKeyboardMarkup (import localized to avoid hard dep in tests)."""
    from telegram import InlineKeyboardMarkup

    kb: list[list] = []
    for row in rows:
        line = []
        for btn in row:
            line.append(_make_inline_button(btn))
        if line:
            kb.append(line)
    return InlineKeyboardMarkup(kb)
