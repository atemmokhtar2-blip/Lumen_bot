"""AST acceptance — fail-closed professional checks."""
from __future__ import annotations

from pathlib import Path

from lumen.engine.services.multi_agent.acceptance_check import (
    check_criterion,
    evaluate_task,
    parse_python,
)


def test_syntax_ast_detects_bad_python(tmp_path: Path):
    (tmp_path / "main.py").write_text("def broken(\n", encoding="utf-8")
    r = evaluate_task(tmp_path, files=["main.py"], acceptance=["compileall passes"], strict=True)
    assert r["ok"] is False
    assert r["failed_count"] >= 1


def test_good_telegram_scaffold_passes(tmp_path: Path):
    (tmp_path / "main.py").write_text(
        "import os\n"
        "from telegram.ext import Application, CommandHandler, MessageHandler\n"
        "async def start(update, context):\n"
        "    await update.message.reply_text('hi')\n"
        "def main():\n"
        "    token = os.getenv('BOT_TOKEN')\n"
        "    app = Application.builder().token(token).build()\n"
        "    app.add_handler(CommandHandler('start', start))\n"
        "    app.add_handler(MessageHandler(None, start))\n"
        "    return app\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text("python-telegram-bot>=21\n", encoding="utf-8")
    r = evaluate_task(
        tmp_path,
        files=["main.py", "requirements.txt"],
        acceptance=[
            "main.py exists",
            "compileall passes",
            "requirements lists telegram",
            "token from environment",
            "/start handler registered",
            "safe fallback for unknown text",
        ],
        strict=True,
    )
    assert r["ok"] is True, r.get("failed")


def test_unknown_criterion_fails_closed(tmp_path: Path):
    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
    c = check_criterion(tmp_path, "must integrate with quantum flux capacitor", strict=True)
    assert c["ok"] is False
    assert "unknown" in c.get("detail", "")


def test_parse_python():
    import tempfile
    p = Path(tempfile.mkdtemp()) / "t.py"
    p.write_text("def f():\n    return 1\n", encoding="utf-8")
    tree, err = parse_python(p)
    assert tree is not None and err is None
