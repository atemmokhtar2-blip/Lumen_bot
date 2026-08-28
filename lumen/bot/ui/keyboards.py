"""Build Telegram InlineKeyboardMarkup from engine UiButton rows.

Bot API 9.4 native button colors via ``style``:
  primary = blue, success = green, danger = red

Always inject ``style`` into the outbound API payload (not only constructor
kwargs) so colors work even when the PTB version or intermediate layer
drops unknown fields.
"""
from __future__ import annotations

from typing import Sequence

from lumen.engine.services.ui_state.models import UiButton

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
    aliases = {"blue": "primary", "green": "success", "red": "danger"}
    s = aliases.get(s, s)
    return s if s in _VALID_STYLES else None


def _style_for_action(action: str, explicit: str = "") -> str | None:
    """Fallback style map so every meaningful button is colored."""
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


def _make_inline_button(btn: UiButton):
    from telegram import InlineKeyboardButton

    text = (btn.text or "")[:64]
    callback_data = encode_callback(btn.action, btn.arg)
    style = _style_for_action(btn.action, getattr(btn, "style", "") or "")

    kwargs = {"text": text, "callback_data": callback_data}
    if style:
        kwargs["style"] = style
        # Force field into wire payload regardless of PTB version quirks
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


def build_inline_keyboard(rows: Sequence[Sequence[UiButton]]):
    from telegram import InlineKeyboardMarkup

    kb: list[list] = []
    for row in rows:
        line = [_make_inline_button(btn) for btn in row]
        if line:
            kb.append(line)
    markup = InlineKeyboardMarkup(kb)
    # Ensure style survives serialization to Telegram
    try:
        data = markup.to_dict()
        for i, row in enumerate(rows):
            for j, btn in enumerate(row):
                style = _style_for_action(btn.action, getattr(btn, "style", "") or "")
                if style and i < len(data.get("inline_keyboard", [])) and j < len(
                    data["inline_keyboard"][i]
                ):
                    data["inline_keyboard"][i][j]["style"] = style
        # Rebuild from dict so outbound JSON carries style
        from telegram import InlineKeyboardButton as IKB

        rebuilt = []
        for row in data.get("inline_keyboard", []):
            rebuilt.append(
                [
                    IKB(
                        text=b.get("text", ""),
                        callback_data=b.get("callback_data"),
                        **({"style": b["style"]} if b.get("style") else {}),
                        **(
                            {"api_kwargs": {"style": b["style"]}}
                            if b.get("style")
                            else {}
                        ),
                    )
                    if True
                    else None
                    for b in row
                ]
            )
        return InlineKeyboardMarkup(rebuilt)
    except Exception:
        return markup
