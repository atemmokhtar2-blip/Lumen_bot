"""Deterministic repair — fix obvious Critic findings without an LLM.

Cursor-class systems always have a fast local apply path. This closes the gap
when the model is rate-limited or weak: missing deliverables, empty entry, etc.
"""
from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any

from .findings import CritiqueFinding

logger = logging.getLogger(__name__)

_MIN_MAIN = '''#!/usr/bin/env python3
"""Telegram bot entry — deterministic scaffold (replace/extend as needed)."""
from __future__ import annotations

import logging
import os

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN") or ""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text("مرحباً! البوت يعمل.")


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(update.message.text or "")


def main() -> None:
    if not TOKEN:
        raise SystemExit("Set BOT_TOKEN")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    app.run_polling()


if __name__ == "__main__":
    main()
'''

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
    """Apply safe local fixes. Returns report of actions taken."""
    root = Path(project_path)
    report: dict[str, Any] = {"ok": True, "actions": [], "remaining": []}
    if not root.is_dir():
        return {"ok": False, "actions": [], "error": "no_project"}

    findings = list(findings or [])
    if not findings and extensions:
        findings = _findings_from_state_ext(extensions)

    codes = {f.code for f in findings if f.severity == "error"}
    messages = " ".join(f.message for f in findings if f.severity == "error")

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
        if "no_token_env" in codes or (
            "BOT_TOKEN" not in src and "TELEGRAM_BOT_TOKEN" not in src
        ):
            if "BOT_TOKEN" not in src and "TELEGRAM_BOT_TOKEN" not in src:
                if "import os" not in src:
                    src = (
                        "import os\n"
                        "TOKEN = os.environ.get('BOT_TOKEN') or "
                        "os.environ.get('TELEGRAM_BOT_TOKEN') or ''\n"
                        + src
                    )
                else:
                    src = src.replace(
                        "import os",
                        "import os\nTOKEN = os.environ.get('BOT_TOKEN') or "
                        "os.environ.get('TELEGRAM_BOT_TOKEN') or ''",
                        1,
                    )
                main.write_text(src, encoding="utf-8")
                report["actions"].append("inject_token_env:main.py")

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
            else:
                report["remaining"].append(f.to_dict())

    mod = root / "modules"
    if not mod.exists() and any("modules/" in (f.path or "") for f in findings):
        mod.mkdir(parents=True, exist_ok=True)
        (mod / "__init__.py").write_text('"""modules"""\n', encoding="utf-8")
        report["actions"].append("ensure_modules_pkg")

    report["ok"] = True
    report["files"] = [
        p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()
    ][:40]
    return report


__all__ = ["apply_deterministic_repairs"]
