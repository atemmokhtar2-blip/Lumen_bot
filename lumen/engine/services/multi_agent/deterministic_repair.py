"""Deterministic repair — fix obvious Critic findings without an LLM.

Aligns with platform gen_verify / smoke: requires main.py + app/handlers.py.
"""
from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any

from .findings import CritiqueFinding

logger = logging.getLogger(__name__)

_MIN_HANDLERS = '''"""Bot handlers."""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text("مرحباً! البوت يعمل.")


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(update.message.text or "")
'''

_MIN_MAIN = '''#!/usr/bin/env python3
"""Telegram bot entry."""
from __future__ import annotations

import logging
import os

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from app.handlers import message_handler, start

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN") or ""


def main() -> None:
    if not TOKEN:
        raise SystemExit("Set BOT_TOKEN")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.run_polling()


if __name__ == "__main__":
    main()
'''

_APP_INIT = '"""App package."""\n'
_REQ = "python-telegram-bot>=21.0\n"
_ENV = "BOT_TOKEN=\nTELEGRAM_BOT_TOKEN=\n"
_README = "# Generated bot\n\nSet BOT_TOKEN and run: python main.py\n"


def _findings_from_state_ext(extensions: dict[str, Any]) -> list[CritiqueFinding]:
    out: list[CritiqueFinding] = []
    for x in list((extensions or {}).get("findings") or []):
        if isinstance(x, dict):
            try:
                out.append(CritiqueFinding.from_dict(x))
            except Exception:
                continue
    return out


def apply_deterministic_repairs(
    project_path: str | Path,
    *,
    findings: list[CritiqueFinding] | None = None,
    extensions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply safe local fixes matching Lumen gen_verify layout."""
    root = Path(project_path)
    report: dict[str, Any] = {"ok": True, "actions": [], "remaining": []}
    if not root.is_dir():
        return {"ok": False, "actions": [], "error": "no_project"}

    findings = list(findings or [])
    if not findings and extensions:
        findings = _findings_from_state_ext(extensions)

    codes = {f.code for f in findings if f.severity == "error"}
    messages = " ".join(f.message for f in findings if f.severity == "error")

    # Platform layout: main.py + app/handlers.py
    app_dir = root / "app"
    handlers = app_dir / "handlers.py"
    if not handlers.is_file() or "handlers_py_missing" in messages or "handlers_py_missing" in codes:
        app_dir.mkdir(parents=True, exist_ok=True)
        initp = app_dir / "__init__.py"
        if not initp.is_file():
            initp.write_text(_APP_INIT, encoding="utf-8")
            report["actions"].append("write_missing:app/__init__.py")
        if not handlers.is_file():
            handlers.write_text(_MIN_HANDLERS, encoding="utf-8")
            report["actions"].append("write_missing:app/handlers.py")

    deliverables = {
        "main.py": _MIN_MAIN,
        "requirements.txt": _REQ,
        "README.md": _README,
        ".env.example": _ENV,
    }
    for name, content in deliverables.items():
        path = root / name
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            report["actions"].append(f"write_missing:{name}")

    main = root / "main.py"
    if main.is_file():
        src = main.read_text(encoding="utf-8", errors="replace")
        try:
            ast.parse(src)
            syn_ok = True
        except SyntaxError:
            syn_ok = False
        if not syn_ok or "syntax_error" in codes:
            main.write_text(_MIN_MAIN, encoding="utf-8")
            report["actions"].append("reset_broken_main.py")
            src = _MIN_MAIN
        if "BOT_TOKEN" not in src and "TELEGRAM_BOT_TOKEN" not in src:
            main.write_text(_MIN_MAIN, encoding="utf-8")
            report["actions"].append("reset_main_token_layout")
        if "app.handlers" not in src and "from app" not in src:
            # Prefer platform import layout when handlers exist
            if handlers.is_file():
                main.write_text(_MIN_MAIN, encoding="utf-8")
                report["actions"].append("align_main_to_app_handlers")

    for f in findings:
        if f.code != "syntax_error" or not f.path:
            continue
        target = root / f.path
        if not target.is_file():
            continue
        try:
            ast.parse(target.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            if target.name == "main.py":
                target.write_text(_MIN_MAIN, encoding="utf-8")
                report["actions"].append("reset_broken_main.py")
            elif target.as_posix().endswith("app/handlers.py") or target.name == "handlers.py":
                target.write_text(_MIN_HANDLERS, encoding="utf-8")
                report["actions"].append("reset_broken_handlers.py")
            else:
                report["remaining"].append(f.to_dict())

    report["ok"] = True
    report["files"] = [
        p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()
    ][:40]
    return report


__all__ = ["apply_deterministic_repairs"]
