"""Build Telegram InlineKeyboardMarkup from engine UiButton rows.

Security (world-class 2025–2026):
  callback_data is HMAC-signed and bound to the viewing user_id.
  Forged / replayed / cross-user button presses fail closed.

Colors (Bot API 9.4): style primary|success|danger forced on the wire payload.
"""
from __future__ import annotations

from typing import Sequence

from lumen.engine.services.ui_state.models import UiButton

from .signed_callback import encode_signed

_VALID_STYLES = frozenset({"primary", "success", "danger"})


def encode_callback(action: str, arg: str = "", *, user_id: int = 0) -> str:
    """Public encoder — always signed when user_id > 0."""
    if int(user_id or 0) <= 0:
        # Dev/test path only — production builders must pass user_id
        from .signed_callback import encode_signed as _es
        return _es(action, arg, user_id=0)
    return encode_signed(action, arg, user_id=int(user_id))


def decode_callback(data: str, *, user_id: int = 0):
    """Verify signed callback; returns (action, arg) or None."""
    from .signed_callback import decode_signed
    if int(user_id or 0) <= 0:
        return None
    return decode_signed(data, user_id=int(user_id))


def _normalize_style(raw: str) -> str | None:
    s = (raw or "").strip().lower()
    aliases = {"blue": "primary", "green": "success", "red": "danger"}
    s = aliases.get(s, s)
    return s if s in _VALID_STYLES else None


def _style_for_action(action: str, explicit: str = "") -> str | None:
    s = _normalize_style(explicit)
    if s:
        return s
    a = (action or "").strip().lower()
    if a in {"open_generate", "confirm_generate", "post_trial", "post_host", "dash_trial"}:
        return "success"
    if a in {"cancel_generate", "home", "dash_stop"}:
        return "danger"
    if a in {
        "open_dashboard",
        "open_billing",
        "dash_status",
        "dash_diagnose",
        "post_zip",
        "post_preview",
    }:
        return "primary"
    return None


def _make_inline_button(btn: UiButton, *, user_id: int):
    from telegram import InlineKeyboardButton

    text = (btn.text or "")[:64]
    callback_data = encode_signed(btn.action, btn.arg, user_id=int(user_id or 0))
    style = _style_for_action(btn.action, getattr(btn, "style", "") or "")
    kwargs = {"text": text, "callback_data": callback_data}
    if style:
        kwargs["style"] = style
        kwargs["api_kwargs"] = {"style": style}
    try:
        return InlineKeyboardButton(**kwargs)
    except TypeError:
        kwargs.pop("style", None)
        try:
            return InlineKeyboardButton(**kwargs)
        except TypeError:
            kwargs.pop("api_kwargs", None)
            return InlineKeyboardButton(text=text, callback_data=callback_data)


def build_inline_keyboard(rows: Sequence[Sequence[UiButton]], *, user_id: int = 0):
    """Build markup. ``user_id`` is required in production so buttons are non-transferable."""
    from telegram import InlineKeyboardMarkup

    uid = int(user_id or 0)
    kb: list[list] = []
    for row in rows:
        line = [_make_inline_button(btn, user_id=uid) for btn in row]
        if line:
            kb.append(line)
    return InlineKeyboardMarkup(kb)
