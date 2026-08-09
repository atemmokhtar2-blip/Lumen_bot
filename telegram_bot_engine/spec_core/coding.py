"""Coding Engine — emits python-telegram-bot v21 project files from BotSpec (no AI)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .planning import plan_from_spec
from .registry import get_capability
from .schema import BotSpec, Feature


def _msg(feat: Feature, kind: str, default: str) -> str:
    if kind == "success":
        return feat.messages.success or feat.success.get("message") or default
    if kind == "failure":
        return feat.messages.failure or feat.failure.get("message") or default
    return feat.messages.prompt or default


def _emit_config() -> str:
    return '''"""Runtime settings."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str = ""

    @classmethod
    def load(cls) -> "Settings":
        return cls(telegram_bot_token=(os.getenv("TELEGRAM_BOT_TOKEN") or "").strip())


def get_settings() -> Settings:
    return Settings.load()
'''


def _emit_db(spec: BotSpec) -> str:
    if spec.storage.type != "sqlite" and not any(
        get_capability(f.feature) and get_capability(f.feature).service == "tasks"  # type: ignore[union-attr]
        for f in spec.features
    ):
        return ""
    return '''"""SQLite helpers."""
from __future__ import annotations

import sqlite3
from pathlib import Path

_DB = Path(__file__).resolve().parent.parent / "data.sqlite3"


def connect() -> sqlite3.Connection:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                priority TEXT NOT NULL DEFAULT 'medium',
                done INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.commit()
'''


def _emit_moderation() -> str:
    return '''"""Moderation service — Telegram Chat Permissions / ban API."""
from __future__ import annotations

from telegram import ChatPermissions
from telegram.ext import ContextTypes


async def ban_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> None:
    await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)


async def unban_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> None:
    await context.bot.unban_chat_member(chat_id=chat_id, user_id=user_id)


async def mute_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> None:
    perms = ChatPermissions(can_send_messages=False)
    await context.bot.restrict_chat_member(chat_id=chat_id, user_id=user_id, permissions=perms)


async def warn_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> str:
    # Lightweight warn: no persistence beyond message; extend later if needed.
    return f"warned:{user_id}"
'''


def _emit_tasks() -> str:
    return '''"""Tasks service — sqlite-backed personal tasks."""
from __future__ import annotations

from app.db import connect, init_db


def ensure() -> None:
    init_db()


def add_task(user_id: int, title: str, description: str = "", priority: str = "medium") -> int:
    ensure()
    priority = priority if priority in {"high", "medium", "low"} else "medium"
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO tasks (user_id, title, description, priority, done) VALUES (?, ?, ?, ?, 0)",
            (user_id, title, description, priority),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_tasks(user_id: int, only_open: bool = True) -> list[dict]:
    ensure()
    q = "SELECT id, title, description, priority, done FROM tasks WHERE user_id = ?"
    if only_open:
        q += " AND done = 0"
    q += " ORDER BY id DESC"
    with connect() as conn:
        rows = conn.execute(q, (user_id,)).fetchall()
    return [dict(r) for r in rows]


def done_task(user_id: int, task_id: int) -> bool:
    ensure()
    with connect() as conn:
        cur = conn.execute(
            "UPDATE tasks SET done = 1 WHERE id = ? AND user_id = ?",
            (task_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0


def delete_task(user_id: int, task_id: int) -> bool:
    ensure()
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM tasks WHERE id = ? AND user_id = ?",
            (task_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0
'''


def _emit_keyboards(spec: BotSpec) -> str:
    rows = []
    for b in spec.start_buttons:
        rows.append(
            f"        [InlineKeyboardButton({b.label!r}, callback_data={b.callback_id!r})],"
        )
    # auto buttons from callback features if no start_buttons
    if not rows:
        for feat in spec.features:
            if feat.trigger.type == "callback":
                label = feat.messages.success or feat.feature
                rows.append(
                    f"        [InlineKeyboardButton({label!r}, callback_data={feat.trigger.id!r})],"
                )
    body = "\n".join(rows) if rows else "        # no buttons"
    return f'''"""Inline keyboards derived from BotSpec."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_keyboard() -> InlineKeyboardMarkup | None:
    rows = [
{body}
    ]
    rows = [r for r in rows if r]
    if not rows:
        return None
    return InlineKeyboardMarkup(rows)
'''


def _emit_handlers(spec: BotSpec) -> str:
    lang = (spec.bot.language or "ar").lower()
    welcome = "مرحباً بك 👋" if lang.startswith("ar") else "Welcome 👋"
    help_lines = []
    for feat in spec.features:
        if feat.trigger.type == "command":
            desc = feat.messages.prompt or feat.feature
            help_lines.append(f"/{feat.trigger.id} — {desc}")
    help_text = "\\n".join(help_lines) if help_lines else "/start"

    # collect needs
    need_mod = any(
        (get_capability(f.feature) or None) and get_capability(f.feature).service == "moderation"  # type: ignore
        for f in spec.features
    )
    need_tasks = any(
        (get_capability(f.feature) or None) and get_capability(f.feature).service == "tasks"  # type: ignore
        for f in spec.features
    )

    imports = [
        "from __future__ import annotations",
        "",
        "from telegram import Update",
        "from telegram.ext import ContextTypes",
        "from app.keyboards import main_keyboard",
    ]
    if need_mod:
        imports.append("from app.services import moderation as moderation_svc")
    if need_tasks:
        imports.append("from app.services import tasks as tasks_svc")

    lines: list[str] = imports + ["", ""]

    # start / help always useful
    lines += [
        "async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:",
        "    message = update.effective_message",
        "    if message is None:",
        "        return",
        f"    text = {welcome!r}",
        "    kb = main_keyboard()",
        "    await message.reply_text(text, reply_markup=kb)",
        "",
        "",
        "async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:",
        "    message = update.effective_message",
        "    if message is None:",
        "        return",
        f"    await message.reply_text({help_text!r})",
        "",
        "",
    ]

    # feature handlers
    for feat in spec.features:
        cap = get_capability(feat.feature)
        if cap is None:
            continue
        fname = f"handle_{feat.id}".replace("-", "_")
        ok = _msg(feat, "success", "تم بنجاح" if lang.startswith("ar") else "Done")
        fail = _msg(feat, "failure", "فشل التنفيذ" if lang.startswith("ar") else "Failed")

        if cap.method == "start":
            continue  # already have start_handler
        if cap.method == "help":
            continue

        lines.append(f"async def {fname}(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:")
        lines.append("    message = update.effective_message")
        lines.append("    user = update.effective_user")
        lines.append("    chat = update.effective_chat")
        lines.append("    if message is None or user is None:")
        lines.append("        return")

        if cap.service == "moderation":
            lines.append("    target_id = None")
            lines.append("    if message.reply_to_message and message.reply_to_message.from_user:")
            lines.append("        target_id = message.reply_to_message.from_user.id")
            lines.append("    elif context.args:")
            lines.append("        try:")
            lines.append("            target_id = int(context.args[0])")
            lines.append("        except ValueError:")
            lines.append("            target_id = None")
            lines.append("    if target_id is None or chat is None:")
            lines.append(f"        await message.reply_text({fail!r})")
            lines.append("        return")
            lines.append("    try:")
            if cap.method == "ban_user":
                lines.append("        await moderation_svc.ban_user(context, chat.id, target_id)")
            elif cap.method == "unban_user":
                lines.append("        await moderation_svc.unban_user(context, chat.id, target_id)")
            elif cap.method == "mute_user":
                lines.append("        await moderation_svc.mute_user(context, chat.id, target_id)")
            else:
                lines.append("        await moderation_svc.warn_user(context, chat.id, target_id)")
            lines.append(f"        await message.reply_text({ok!r})")
            lines.append("    except Exception:")
            lines.append(f"        await message.reply_text({fail!r})")

        elif cap.service == "tasks":
            if cap.method == "add_task":
                prompt = _msg(feat, "prompt", "أرسل عنوان المهمة" if lang.startswith("ar") else "Send task title")
                lines.append("    if context.args:")
                lines.append("        title = ' '.join(context.args)")
                lines.append("        tasks_svc.add_task(user.id, title)")
                lines.append(f"        await message.reply_text({ok!r})")
                lines.append("        return")
                lines.append("    context.user_data['awaiting'] = 'task_title'")
                lines.append(f"    await message.reply_text({prompt!r})")
            elif cap.method == "list_tasks":
                empty = "لا توجد مهام" if lang.startswith("ar") else "No tasks"
                lines.append("    items = tasks_svc.list_tasks(user.id)")
                lines.append("    if not items:")
                lines.append(f"        await message.reply_text({empty!r})")
                lines.append("        return")
                lines.append(
                    "    text = '\\n'.join(f\"#{i['id']} {i['title']} [{i['priority']}]\" for i in items)"
                )
                lines.append("    await message.reply_text(text)")
            elif cap.method == "done_task":
                lines.append("    if not context.args:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    try:")
                lines.append("        tid = int(context.args[0])")
                lines.append("    except ValueError:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    if tasks_svc.done_task(user.id, tid):")
                lines.append(f"        await message.reply_text({ok!r})")
                lines.append("    else:")
                lines.append(f"        await message.reply_text({fail!r})")
            elif cap.method == "delete_task":
                lines.append("    if not context.args:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    try:")
                lines.append("        tid = int(context.args[0])")
                lines.append("    except ValueError:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    if tasks_svc.delete_task(user.id, tid):")
                lines.append(f"        await message.reply_text({ok!r})")
                lines.append("    else:")
                lines.append(f"        await message.reply_text({fail!r})")
            else:
                lines.append(f"    await message.reply_text({ok!r})")
        else:
            lines.append(f"    await message.reply_text({ok!r})")
        lines.append("")
        lines.append("")

    # text router for simple task title capture
    if need_tasks:
        lines += [
            "async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:",
            "    message = update.effective_message",
            "    user = update.effective_user",
            "    if message is None or user is None or not message.text:",
            "        return",
            "    if context.user_data.get('awaiting') == 'task_title':",
            "        tasks_svc.add_task(user.id, message.text.strip())",
            "        context.user_data.pop('awaiting', None)",
            "        await message.reply_text('تمت إضافة المهمة' if True else 'Task added')",
            "",
            "",
        ]

    # callback router
    cb_map: list[tuple[str, str]] = []
    for feat in spec.features:
        if feat.trigger.type == "callback":
            cb_map.append((feat.trigger.id, f"handle_{feat.id}".replace("-", "_")))

    lines.append("async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:")
    lines.append("    query = update.callback_query")
    lines.append("    if query is None:")
    lines.append("        return")
    lines.append("    await query.answer()")
    lines.append("    data = query.data or ''")
    if cb_map:
        for cid, handler in cb_map:
            lines.append(f"    if data == {cid!r}:")
            lines.append(f"        await {handler}(update, context)")
            lines.append("        return")
    lines.append("    message = update.effective_message")
    lines.append("    if message is not None:")
    lines.append("        await message.reply_text(data)")
    lines.append("")

    return "\n".join(lines) + "\n"


def _emit_main(spec: BotSpec) -> str:
    commands: list[tuple[str, str]] = []
    handler_regs: list[str] = []
    for feat in spec.features:
        if feat.trigger.type != "command":
            continue
        cmd = feat.trigger.id
        if feat.feature == "start" or cmd == "start":
            handler_regs.append('    app.add_handler(CommandHandler("start", start_handler))')
            commands.append(("start", "start"))
        elif feat.feature == "help" or cmd == "help":
            handler_regs.append('    app.add_handler(CommandHandler("help", help_handler))')
            commands.append(("help", "help"))
        else:
            h = f"handle_{feat.id}".replace("-", "_")
            handler_regs.append(f'    app.add_handler(CommandHandler({cmd!r}, {h}))')
            commands.append((cmd, feat.feature))

    # ensure start/help registered
    reg_text = "\n".join(dict.fromkeys(handler_regs))
    if 'CommandHandler("start"' not in reg_text:
        reg_text = '    app.add_handler(CommandHandler("start", start_handler))\n' + reg_text
    if 'CommandHandler("help"' not in reg_text:
        reg_text += '\n    app.add_handler(CommandHandler("help", help_handler))'

    need_tasks = any(
        (get_capability(f.feature) and get_capability(f.feature).service == "tasks")  # type: ignore
        for f in spec.features
    )
    imports_handlers = "start_handler, help_handler, callback_router"
    extra_imports = []
    for feat in spec.features:
        if feat.feature in ("start", "help"):
            continue
        extra_imports.append(f"handle_{feat.id}".replace("-", "_"))
    if extra_imports:
        imports_handlers += ", " + ", ".join(dict.fromkeys(extra_imports))
    if need_tasks:
        imports_handlers += ", text_router"

    bot_cmds = ",\n        ".join(
        f"BotCommand({c!r}, {d!r})" for c, d in dict.fromkeys(commands)
    ) or 'BotCommand("start", "start")'

    text_handler = ""
    if need_tasks:
        text_handler = "\n    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))"

    return f'''"""Application entry — python-telegram-bot v21."""
from __future__ import annotations

import logging
import sys

from telegram import BotCommand, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from app.config import get_settings
from app.handlers import {imports_handlers}

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
logger = logging.getLogger({spec.bot.name!r})


async def _post_init(app: Application) -> None:
    await app.bot.set_my_commands([
        {bot_cmds}
    ])


def build_application() -> Application:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN in .env")
    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(_post_init)
        .build()
    )
{reg_text}
    app.add_handler(CallbackQueryHandler(callback_router)){text_handler}
    return app


def main() -> None:
    logger.info("starting bot")
    build_application().run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
'''


def _emit_requirements() -> str:
    return "python-telegram-bot>=21.0,<22\npython-dotenv>=1.0.0\n"


def _emit_env() -> str:
    return "TELEGRAM_BOT_TOKEN=\n"


def _emit_readme(spec: BotSpec) -> str:
    return f"""# {spec.bot.name}

Generated by **spec_core** (zero-AI deterministic engine).

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# put TELEGRAM_BOT_TOKEN in .env
python main.py
```

## Features

{chr(10).join(f"- `{f.feature}` via {f.trigger.type}:{f.trigger.id}" for f in spec.features)}
"""


def generate_files(spec: BotSpec) -> dict[str, str]:
    """Return path → file content for a full project."""
    plan = plan_from_spec(spec)
    services = set(plan.services)
    files: dict[str, str] = {
        "main.py": _emit_main(spec),
        "requirements.txt": _emit_requirements(),
        ".env.example": _emit_env(),
        "README.md": _emit_readme(spec),
        "app/__init__.py": '"""App package."""\n',
        "app/config.py": _emit_config(),
        "app/handlers.py": _emit_handlers(spec),
        "app/keyboards.py": _emit_keyboards(spec),
        "app/services/__init__.py": '"""Services package."""\n',
    }
    if "moderation" in services:
        files["app/services/moderation.py"] = _emit_moderation()
    if "tasks" in services or spec.storage.type == "sqlite":
        files["app/db.py"] = _emit_db(spec)
        files["app/services/tasks.py"] = _emit_tasks()
    return files


def write_project(spec: BotSpec, out_dir: str | Path) -> list[str]:
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for rel, content in generate_files(spec).items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.rstrip() + "\n", encoding="utf-8")
        written.append(str(path))
    return written


__all__ = ["generate_files", "write_project"]
