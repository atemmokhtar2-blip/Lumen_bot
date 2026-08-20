"""Pure helper utilities for the Telegram bot interface."""

from __future__ import annotations

import os
import re
import zipfile
from pathlib import Path

from .config import ALLOWED_USER_IDS, ALLOW_ALL_USERS, logger


def is_allowed(user_id: int | None) -> bool:
    """Public product: allow everyone by default.

    - ALLOW_ALL_USERS (default on for public launch) → any user_id.
    - Only when LOCK_BOT_TO_ALLOWLIST=1 and ALLOWED_USER_IDS is set → allowlist only.
    """
    if user_id is None:
        return False
    from .config import LOCK_BOT_TO_ALLOWLIST

    if LOCK_BOT_TO_ALLOWLIST and ALLOWED_USER_IDS:
        return user_id in ALLOWED_USER_IDS
    if ALLOW_ALL_USERS:
        return True
    if ALLOWED_USER_IDS:
        return user_id in ALLOWED_USER_IDS
    return False


def chat_route(text: str):
    """Single entry: natural language → capability (chat never writes code)."""
    try:
        from telegram_bot_engine.services.chat_router import route_message
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


def normalize_bot_token(text: str) -> str:
    """Collapse whitespace/newlines so pasted tokens still match."""
    return re.sub(r"\s+", "", (text or "").strip())


def looks_like_bot_token(text: str) -> bool:
    return bool(re.match(r"^\d{6,12}:[A-Za-z0-9_-]{30,}$", normalize_bot_token(text)))


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
            from telegram.constants import ParseMode
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
    """Create a clean, safe ZIP containing only deliverable project files."""
    project_path = Path(project_path).resolve()
    if not project_path.is_dir():
        return None

    zip_path = project_path.parent / f"{project_path.name}.zip"
    try:
        zip_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        logger.exception("zip parent mkdir failed")
        return None
    excluded_dirs = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules"}
    excluded_names = {".env", ".env.local", ".env.production", "secrets.json"}
    tmp_zip = zip_path.with_suffix(".zip.tmp")
    try:
        with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for root, dirs, files in os.walk(project_path):
                dirs[:] = [d for d in dirs if d not in excluded_dirs and not d.startswith(".")]
                for name in files:
                    full = (Path(root) / name).resolve()
                    if name in excluded_names or name.endswith((".pyc", ".pyo", ".log")):
                        continue
                    if full == zip_path or not full.is_file():
                        continue
                    try:
                        arc = full.relative_to(project_path)
                    except ValueError:
                        logger.warning("Skipping path outside project: %s", full)
                        continue
                    zf.write(full, arc.as_posix())
        os.replace(tmp_zip, zip_path)
        return zip_path
    except Exception as e:
        try:
            tmp_zip.unlink(missing_ok=True)
        except Exception:
            pass
        logger.exception("Failed to create zip: %s", e)
        return None


def split_file_for_telegram(path: str | Path, max_mb: float = 45.0) -> list[Path]:
    """Return one file or deterministic numbered parts below Telegram's upload limit."""
    source = Path(path).resolve()
    if not source.is_file():
        return []
    limit = max(1, int(max_mb * 1024 * 1024))
    if source.stat().st_size <= limit:
        return [source]
    parts: list[Path] = []
    try:
        with source.open("rb") as src:
            index = 1
            while True:
                chunk = src.read(limit)
                if not chunk:
                    break
                part = source.with_name(f"{source.name}.part{index:03d}")
                part.write_bytes(chunk)
                parts.append(part)
                index += 1
        return parts
    except Exception:
        for part in parts:
            part.unlink(missing_ok=True)
        logger.exception("Failed to split large delivery file: %s", source)
        return []


def run_generation(request: str, work_dir: Path, user_id: int = 0, preferred_keys=None):
    """Synchronous call into the generation engine (runs in a thread).

    Passes user_id so L4 memory + L6 personalization apply per user.
    preferred_keys: optional capability keys from Phase-2 detection.

    Experimental: when GROQ_CODEGEN_ENABLED=1, bypass spec_core and let Groq
    emit the full project (engine remains installed for instant rollback).
    """
    try:
        from telegram_bot_engine.services.groq_codegen import (
            groq_codegen_enabled,
            generate_bot_via_groq,
        )
        if groq_codegen_enabled():
            logger.info("GROQ_CODEGEN_ENABLED=1 — using experimental Groq direct codegen")
            return generate_bot_via_groq(
                request,
                work_dir,
                user_id=int(user_id or 0),
            )
    except Exception:
        logger.exception("Groq codegen path failed to start; falling back to spec_core")

    from telegram_bot_engine import generate_bot

    return generate_bot(
        request,
        work_dir=str(work_dir),
        user_id=int(user_id or 0),
        preferred_keys=preferred_keys,
    )


async def safe_reply_text(message, text: str, *, use_markdown: bool = False) -> None:
    """reply_text that never fails silently on Markdown parse errors."""
    try:
        if use_markdown:
            from telegram.constants import ParseMode
            await message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        else:
            await message.reply_text(text)
        return
    except Exception:
        try:
            await message.reply_text(str(text)[:4000])
        except Exception:
            from .config import logger
            logger.exception("safe_reply_text failed")
