"""Pure helper utilities for the Telegram bot interface."""

from __future__ import annotations

import os
import re
import zipfile
from pathlib import Path

from telegram.constants import ParseMode

from .config import ALLOWED_USER_IDS, logger


def is_allowed(user_id: int | None) -> bool:
    if not ALLOWED_USER_IDS:
        return True
    return user_id is not None and user_id in ALLOWED_USER_IDS


def chat_route(text: str):
    """Single entry: natural language → capability (chat never writes code)."""
    try:
        from telegram_bot_engine.formal_engine.services.chat_router import route_message
        return route_message(text or "")
    except Exception:
        return None


def detect_host_intent(text: str) -> str:
    """Return host action via ChatRouter."""
    r = chat_route(text)
    if r is None or not getattr(r, "ok", False):
        t = (text or "").strip().lower()
        if any(k in t for k in ("استضف", "استضافة", "host")):
            return "start"
        return "none"
    return {
        "host_start": "start",
        "host_stop": "stop",
        "host_status": "status",
        "host_diagnose": "diagnose",
    }.get(r.capability_id, "none")


def looks_like_bot_token(text: str) -> bool:
    return bool(re.match(r"^\d{6,12}:[A-Za-z0-9_-]{30,}$", (text or "").strip()))


def escape_md(text: object) -> str:
    """Escape Telegram legacy Markdown special characters in dynamic text."""
    s = str(text) if text is not None else ""
    for ch in ("\\", "`", "*", "_", "[", "]", "(", ")"):
        s = s.replace(ch, f"\\{ch}")
    return s


async def safe_edit_text(message, text: str, *, use_markdown: bool = True) -> None:
    """edit_text with Markdown; fall back to plain text if Telegram rejects entities."""
    if use_markdown:
        try:
            await message.edit_text(text, parse_mode=ParseMode.MARKDOWN)
            return
        except Exception as e:
            err = str(e).lower()
            if "can't parse entities" in err or "parse entities" in err:
                logger.warning("Markdown parse failed, retrying as plain text: %s", e)
            else:
                raise
    plain = (
        text.replace("\\", "")
        .replace("*", "")
        .replace("`", "")
        .replace("_", "")
    )
    await message.edit_text(plain)


def make_zip_from_path(project_path: str | Path) -> Path | None:
    """Create a zip of the generated project. Returns zip path or None."""
    project_path = Path(project_path)
    if not project_path.exists():
        return None

    zip_path = project_path.parent / f"{project_path.name}.zip"
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(project_path):
                for name in files:
                    full = Path(root) / name
                    arc = full.relative_to(project_path)
                    zf.write(full, arc)
        return zip_path
    except Exception as e:
        logger.exception("Failed to create zip: %s", e)
        return None


def run_generation(request: str, work_dir: Path):
    """Synchronous call into the generation engine (runs in a thread)."""
    from telegram_bot_engine import generate_bot

    return generate_bot(request, work_dir=str(work_dir))
