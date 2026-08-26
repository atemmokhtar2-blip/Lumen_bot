"""Emit content + welcome from deep content_runtime."""
from __future__ import annotations

from pathlib import Path

from ..schema import BotSpec


def _content_source() -> str:
    path = Path(__file__).resolve().parents[1] / "runtime" / "content_runtime.py"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"content_runtime missing: {path}")


def _emit_content(spec: BotSpec) -> str:
    # About text can be injected as module-level default
    about = ""
    try:
        about = (spec.bot.description or spec.bot.name or "").strip()
    except Exception:
        about = ""
    src = _content_source()
    if about:
        src += f"\n\nDEFAULT_ABOUT = {about!r}\n\ndef about() -> str:\n    return DEFAULT_ABOUT or rules()\n"
    else:
        src += "\n\ndef about() -> str:\n    return rules()\n"
    return src


def _emit_welcome() -> str:
    return _content_source()
