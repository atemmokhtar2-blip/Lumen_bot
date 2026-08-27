"""Behavioral acceptance layers."""
from __future__ import annotations

from pathlib import Path

from lumen.engine.services.multi_agent.acceptance_check import (
    check_criterion,
    evaluate_task,
)


def test_structural_and_syntax(tmp_path: Path):
    (tmp_path / "main.py").write_text(
        "import os\n\ndef main():\n    t = os.getenv('BOT_TOKEN')\n    return t\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text("python-telegram-bot\n", encoding="utf-8")
    r = evaluate_task(
        tmp_path,
        files=["main.py", "requirements.txt"],
        acceptance=[
            "main.py exists",
            "compileall passes",
            "requirements lists telegram",
            "token from env",
        ],
    )
    assert r["ok"] is True
    assert r["failed_count"] == 0


def test_missing_main_fails(tmp_path: Path):
    r = evaluate_task(tmp_path, files=["main.py"], acceptance=["main.py exists"])
    assert r["ok"] is False


def test_start_handler_criterion(tmp_path: Path):
    (tmp_path / "main.py").write_text(
        "from telegram.ext import Application, CommandHandler\n"
        "async def start(u,c): pass\n"
        "app = Application.builder().token('x').build()\n"
        "app.add_handler(CommandHandler('start', start))\n",
        encoding="utf-8",
    )
    c = check_criterion(tmp_path, "/start handler registered")
    assert c["ok"] is True
