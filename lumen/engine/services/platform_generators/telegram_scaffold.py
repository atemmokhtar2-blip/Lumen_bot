"""Telegram bot scaffold — python-telegram-bot (official PTB patterns)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

HANDLERS = '''"""Telegram handlers."""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text("Hello! Bot is running.")


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(update.message.text or "")
'''

MAIN = '''#!/usr/bin/env python3
"""Telegram bot entry (python-telegram-bot)."""
from __future__ import annotations

import logging
import os

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from app.handlers import message_handler, start

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN") or ""


def main() -> None:
    if not TOKEN:
        raise SystemExit("Set BOT_TOKEN or TELEGRAM_BOT_TOKEN")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.run_polling()


if __name__ == "__main__":
    main()
'''


def write_telegram(root: Path) -> list[str]:
    written: list[str] = []
    (root / "app").mkdir(parents=True, exist_ok=True)
    files = {
        "main.py": MAIN,
        "app/__init__.py": '"""App package."""\n',
        "app/handlers.py": HANDLERS,
        "requirements.txt": "python-telegram-bot>=21.0\n",
        ".env.example": "BOT_TOKEN=\nTELEGRAM_BOT_TOKEN=\n",
        "README.md": "# Telegram bot\n\n```bash\nexport BOT_TOKEN=...\npython main.py\n```\n",
    }
    for rel, content in files.items():
        path = root / rel
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            written.append(rel)
    meta = root / "PLATFORM.md"
    meta.write_text("platform: telegram\nruntime: python-telegram-bot\n", encoding="utf-8")
    written.append("PLATFORM.md")
    return written
