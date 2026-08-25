"""Keyboards: UX menu_buttons first, else feature labels."""
from __future__ import annotations

from ..schema import BotSpec

try:
    from .labels import label, slash
except Exception:
    def label(fid, lang="ar"):
        return fid.replace("_", " ")
    def slash(fid):
        return "".join(c for c in (fid or "").lower() if c.isalnum())[:24] or "cmd"


def _emit_keyboards(spec: BotSpec) -> str:
    ux = getattr(spec, "ux", None)
    menu = list(getattr(ux, "menu_buttons", None) or []) if ux else []
    lines: list[str] = []
    pair: list[str] = []

    def flush() -> None:
        nonlocal pair
        if pair:
            lines.append("        [" + ", ".join(pair) + "],")
            pair = []

    def add(text: str, body: str) -> None:
        pair.append(f"InlineKeyboardButton({text!r}, callback_data='cmd:{body}')")
        if len(pair) == 2:
            flush()

    if menu:
        for b in menu[:12]:
            if not isinstance(b, dict):
                continue
            lab = str(b.get("label") or "").strip()
            if not lab:
                continue
            feat = str(b.get("feature") or "menu")
            body = slash(feat).replace("_", "") if feat else "".join(c for c in lab.lower() if c.isalnum())[:24] or "menu"
            add(lab, body)
    else:
        for f in spec.features or []:
            k = getattr(f, "feature", "") or ""
            if not k or k in {"start", "help"}:
                continue
            add(label(k, "ar"), slash(k).replace("_", ""))
            if len(lines) >= 6:
                break
    flush()
    body = "\n".join(lines) if lines else "        # no buttons"
    return (
        '"""أزرار من وصف المستخدم (ux) أولاً."""\n'
        "from __future__ import annotations\n\n"
        "from telegram import InlineKeyboardButton, InlineKeyboardMarkup\n\n\n"
        "def main_keyboard() -> InlineKeyboardMarkup | None:\n"
        "    rows = [\n"
        f"{body}\n"
        "    ]\n"
        "    rows = [r for r in rows if r]\n"
        "    return InlineKeyboardMarkup(rows) if rows else None\n"
    )
