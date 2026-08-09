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
    need = spec.storage.type == "sqlite" or any(
        (get_capability(f.feature) and get_capability(f.feature).service in {"tasks", "notes"})  # type: ignore[union-attr]
        for f in spec.features
    )
    if not need:
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                body TEXT NOT NULL
            )
            """
        )
        conn.commit()
'''


def _emit_moderation() -> str:
    return '''"""Moderation service — Telegram admin APIs."""
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


async def unmute_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> None:
    perms = ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
    )
    await context.bot.restrict_chat_member(chat_id=chat_id, user_id=user_id, permissions=perms)


async def kick_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> None:
    await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
    await context.bot.unban_chat_member(chat_id=chat_id, user_id=user_id)


async def warn_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> str:
    return f"warned:{user_id}"


async def promote_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> None:
    await context.bot.promote_chat_member(
        chat_id=chat_id,
        user_id=user_id,
        can_manage_chat=True,
        can_delete_messages=True,
        can_restrict_members=True,
        can_invite_users=True,
        can_pin_messages=True,
        can_promote_members=False,
        can_change_info=False,
        can_manage_video_chats=False,
    )


async def demote_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> None:
    await context.bot.promote_chat_member(
        chat_id=chat_id,
        user_id=user_id,
        can_manage_chat=False,
        can_delete_messages=False,
        can_restrict_members=False,
        can_invite_users=False,
        can_pin_messages=False,
        can_promote_members=False,
        can_change_info=False,
        can_manage_video_chats=False,
    )


async def pin_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int) -> None:
    await context.bot.pin_chat_message(chat_id=chat_id, message_id=message_id)


async def delete_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int) -> None:
    await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
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


def clear_tasks(user_id: int) -> int:
    ensure()
    with connect() as conn:
        cur = conn.execute("DELETE FROM tasks WHERE user_id = ? AND done = 1", (user_id,))
        conn.commit()
        return int(cur.rowcount)
'''



def _emit_notes() -> str:
    return '''"""Notes service — personal notes in sqlite."""
from __future__ import annotations

from app.db import connect, init_db


def ensure() -> None:
    init_db()


def add_note(user_id: int, body: str) -> int:
    ensure()
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO notes (user_id, body) VALUES (?, ?)",
            (user_id, body),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_notes(user_id: int) -> list[dict]:
    ensure()
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, body FROM notes WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_note(user_id: int, note_id: int) -> bool:
    ensure()
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM notes WHERE id = ? AND user_id = ?",
            (note_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0
'''


def _emit_content(spec: BotSpec) -> str:
    rules = "التزم بالاحترام. ممنوع السبام والإعلانات." if (spec.bot.language or "ar").startswith("ar") else "Be respectful. No spam."
    about = spec.bot.description or spec.bot.name
    return f'''"""Static content helpers."""
from __future__ import annotations

RULES_TEXT = {rules!r}
ABOUT_TEXT = {about!r}


def rules() -> str:
    return RULES_TEXT


def about() -> str:
    return ABOUT_TEXT
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
    def _svc(f):
        c = get_capability(f.feature)
        return c.service if c else ""

    need_mod = any(_svc(f) == "moderation" for f in spec.features)
    need_tasks = any(_svc(f) == "tasks" for f in spec.features)
    need_notes = any(_svc(f) == "notes" for f in spec.features)
    need_content = any(_svc(f) == "content" for f in spec.features)

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
    if need_notes:
        imports.append("from app.services import notes as notes_svc")
    if need_content:
        imports.append("from app.services import content as content_svc")

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
            if cap.method in {"pin_message", "delete_message"}:
                lines.append("    if chat is None or message.reply_to_message is None:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    try:")
                lines.append("        mid = message.reply_to_message.message_id")
                if cap.method == "pin_message":
                    lines.append("        await moderation_svc.pin_message(context, chat.id, mid)")
                else:
                    lines.append("        await moderation_svc.delete_message(context, chat.id, mid)")
                lines.append(f"        await message.reply_text({ok!r})")
                lines.append("    except Exception:")
                lines.append(f"        await message.reply_text({fail!r})")
            else:
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
                method_map = {
                    "ban_user": "ban_user",
                    "unban_user": "unban_user",
                    "mute_user": "mute_user",
                    "unmute_user": "unmute_user",
                    "kick_user": "kick_user",
                    "promote_user": "promote_user",
                    "demote_user": "demote_user",
                    "warn_user": "warn_user",
                }
                m = method_map.get(cap.method, "warn_user")
                lines.append(f"        await moderation_svc.{m}(context, chat.id, target_id)")
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
                lines.append("    text = \"\\n\".join(f\"#{i['id']} {i['title']} [{i['priority']}]\" for i in items)")
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
            elif cap.method == "clear_tasks":
                lines.append("    n = tasks_svc.clear_tasks(user.id)")
                lines.append(f"    await message.reply_text({ok!r} + f' ({{n}})')")
            else:
                lines.append(f"    await message.reply_text({ok!r})")

        elif cap.service == "notes":
            if cap.method == "add_note":
                prompt = _msg(feat, "prompt", "أرسل نص الملاحظة" if lang.startswith("ar") else "Send note text")
                lines.append("    if context.args:")
                lines.append("        notes_svc.add_note(user.id, ' '.join(context.args))")
                lines.append(f"        await message.reply_text({ok!r})")
                lines.append("        return")
                lines.append("    context.user_data['awaiting'] = 'note_body'")
                lines.append(f"    await message.reply_text({prompt!r})")
            elif cap.method == "list_notes":
                empty = "لا توجد ملاحظات" if lang.startswith("ar") else "No notes"
                lines.append("    items = notes_svc.list_notes(user.id)")
                lines.append("    if not items:")
                lines.append(f"        await message.reply_text({empty!r})")
                lines.append("        return")
                lines.append("    text = \"\\n\".join(f\"#{i['id']} {i['body']}\" for i in items)")
                lines.append("    await message.reply_text(text)")
            elif cap.method == "delete_note":
                lines.append("    if not context.args:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    try:")
                lines.append("        nid = int(context.args[0])")
                lines.append("    except ValueError:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    if notes_svc.delete_note(user.id, nid):")
                lines.append(f"        await message.reply_text({ok!r})")
                lines.append("    else:")
                lines.append(f"        await message.reply_text({fail!r})")
            else:
                lines.append(f"    await message.reply_text({ok!r})")

        elif cap.service == "content":
            if cap.method == "rules":
                lines.append("    await message.reply_text(content_svc.rules())")
            elif cap.method == "announce":
                lines.append("    body = ' '.join(context.args) if context.args else ''")
                lines.append("    if not body:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append(f"    await message.reply_text({ok!r} + \"\\n\" + body)")
            else:
                lines.append(f"    await message.reply_text({ok!r})")

        elif cap.service == "core":
            if cap.method == "about":
                about = spec.bot.description or spec.bot.name
                lines.append(f"    await message.reply_text({about!r})")
            elif cap.method == "ping":
                lines.append("    await message.reply_text('pong')")
            elif cap.method == "my_id":
                lines.append("    chat_id = chat.id if chat else 0")
                lines.append("    await message.reply_text(f'user_id={user.id}\\nchat_id={chat_id}')")
            else:
                lines.append(f"    await message.reply_text({ok!r})")

        else:
            lines.append(f"    await message.reply_text({ok!r})")
        lines.append("")
        lines.append("")

    # text router for task/note capture
    if need_tasks or need_notes:
        lines += [
            "async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:",
            "    message = update.effective_message",
            "    user = update.effective_user",
            "    if message is None or user is None or not message.text:",
            "        return",
            "    awaiting = context.user_data.get('awaiting')",
            "    if awaiting == 'task_title':",
            "        tasks_svc.add_task(user.id, message.text.strip())",
            "        context.user_data.pop('awaiting', None)",
            "        await message.reply_text('تمت إضافة المهمة')",
            "        return",
            "    if awaiting == 'note_body':",
            "        notes_svc.add_note(user.id, message.text.strip())",
            "        context.user_data.pop('awaiting', None)",
            "        await message.reply_text('تمت إضافة الملاحظة')",
            "        return",
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
    need_notes = any(
        (get_capability(f.feature) and get_capability(f.feature).service == "notes")  # type: ignore
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
    if need_tasks or need_notes:
        imports_handlers += ", text_router"

    bot_cmds = ",\n        ".join(
        f"BotCommand({c!r}, {d!r})" for c, d in dict.fromkeys(commands)
    ) or 'BotCommand("start", "start")'

    text_handler = ""
    if need_tasks or need_notes:
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
    if "tasks" in services or "notes" in services or spec.storage.type == "sqlite":
        files["app/db.py"] = _emit_db(spec)
    if "tasks" in services:
        files["app/services/tasks.py"] = _emit_tasks()
    if "notes" in services:
        files["app/services/notes.py"] = _emit_notes()
    if "content" in services:
        files["app/services/content.py"] = _emit_content(spec)
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
