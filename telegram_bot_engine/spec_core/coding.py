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
        (get_capability(f.feature) and get_capability(f.feature).service in {"tasks", "notes", "welcome", "tickets", "security", "shop", "booking", "crm", "reminders", "community", "edu", "hr", "utils", "gate"})  # type: ignore[union-attr]
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS welcome_settings (
                chat_id INTEGER PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1,
                message TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL DEFAULT 0,
                subject TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ticket_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                is_staff INTEGER NOT NULL DEFAULT 0,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS security_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS extras_kv (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 0,
                kind TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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


async def lock_chat(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    perms = ChatPermissions(can_send_messages=False)
    await context.bot.set_chat_permissions(chat_id=chat_id, permissions=perms)


async def unlock_chat(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    perms = ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
    )
    await context.bot.set_chat_permissions(chat_id=chat_id, permissions=perms)
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
    return (
        '"""Static content helpers."""\n'
        "from __future__ import annotations\n\n"
        f"RULES_TEXT = {rules!r}\n"
        f"ABOUT_TEXT = {about!r}\n\n"
        "def rules() -> str:\n"
        "    return RULES_TEXT\n\n"
        "def about() -> str:\n"
        "    return ABOUT_TEXT\n\n"
        "def faq() -> str:\n"
        "    return (\n"
        '        "الأسئلة الشائعة:\\n"\n'
        '        "- /start للبداية\\n"\n'
        '        "- /help للأوامر\\n"\n'
        '        "- للمساعدة تواصل مع المشرف"\n'
        "    )\n"
    )



def _emit_welcome() -> str:
    return (
        '"""Welcome service — per-chat auto-welcome for new members."""\n'
        "from __future__ import annotations\n\n"
        "from app.db import connect, init_db\n\n"
        'DEFAULT_MESSAGE = "أهلاً {name} 👋 نورت المجموعة!"\n\n'
        "def ensure() -> None:\n"
        "    init_db()\n\n"
        "def set_message(chat_id: int, message: str) -> None:\n"
        "    ensure()\n"
        "    with connect() as conn:\n"
        "        conn.execute(\n"
        '            """\n'
        "            INSERT INTO welcome_settings (chat_id, enabled, message) VALUES (?, 1, ?)\n"
        "            ON CONFLICT(chat_id) DO UPDATE SET message = excluded.message, enabled = 1\n"
        '            """,\n'
        "            (chat_id, message),\n"
        "        )\n"
        "        conn.commit()\n\n"
        "def toggle(chat_id: int) -> bool:\n"
        "    ensure()\n"
        "    with connect() as conn:\n"
        "        row = conn.execute(\n"
        '            "SELECT enabled FROM welcome_settings WHERE chat_id = ?", (chat_id,)\n'
        "        ).fetchone()\n"
        "        if row is None:\n"
        "            conn.execute(\n"
        '                "INSERT INTO welcome_settings (chat_id, enabled, message) VALUES (?, 1, ?)",\n'
        "                (chat_id, DEFAULT_MESSAGE),\n"
        "            )\n"
        "            conn.commit()\n"
        "            return True\n"
        "        new_val = 0 if int(row['enabled']) else 1\n"
        "        conn.execute(\n"
        '            "UPDATE welcome_settings SET enabled = ? WHERE chat_id = ?",\n'
        "            (new_val, chat_id),\n"
        "        )\n"
        "        conn.commit()\n"
        "        return bool(new_val)\n\n"
        "def get_settings(chat_id: int) -> dict:\n"
        "    ensure()\n"
        "    with connect() as conn:\n"
        "        row = conn.execute(\n"
        '            "SELECT enabled, message FROM welcome_settings WHERE chat_id = ?",\n'
        "            (chat_id,),\n"
        "        ).fetchone()\n"
        "    if row is None:\n"
        '        return {"enabled": True, "message": DEFAULT_MESSAGE}\n'
        "    return {\n"
        "        'enabled': bool(int(row['enabled'])),\n"
        "        'message': row['message'] or DEFAULT_MESSAGE,\n"
        "    }\n\n"
        "def format_welcome(chat_id: int, name: str) -> str | None:\n"
        "    cfg = get_settings(chat_id)\n"
        "    if not cfg['enabled']:\n"
        "        return None\n"
        "    msg = cfg['message'] or DEFAULT_MESSAGE\n"
        "    return msg.replace('{name}', name).replace('{NAME}', name)\n"
    )


def _emit_tickets() -> str:
    return (
        '"""Support tickets service — open/close/list/reply with sqlite."""\n'
        "from __future__ import annotations\n\n"
        "from app.db import connect, init_db\n\n"
        "def ensure() -> None:\n"
        "    init_db()\n\n"
        "def open_ticket(user_id: int, subject: str, chat_id: int = 0) -> int:\n"
        "    ensure()\n"
        '    subject = (subject or "").strip() or "بدون عنوان"\n'
        "    with connect() as conn:\n"
        "        cur = conn.execute(\n"
        '            "INSERT INTO tickets (user_id, chat_id, subject, status) VALUES (?, ?, ?, \'open\')",\n'
        "            (user_id, chat_id, subject[:200]),\n"
        "        )\n"
        "        tid = int(cur.lastrowid)\n"
        "        conn.execute(\n"
        '            "INSERT INTO ticket_messages (ticket_id, user_id, is_staff, body) VALUES (?, ?, 0, ?)",\n'
        "            (tid, user_id, subject),\n"
        "        )\n"
        "        conn.commit()\n"
        "        return tid\n\n"
        "def close_ticket(ticket_id: int, user_id: int | None = None, staff: bool = False) -> bool:\n"
        "    ensure()\n"
        "    with connect() as conn:\n"
        '        row = conn.execute("SELECT user_id, status FROM tickets WHERE id = ?", (ticket_id,)).fetchone()\n'
        "        if row is None:\n"
        "            return False\n"
        "        if not staff and user_id is not None and int(row['user_id']) != int(user_id):\n"
        "            return False\n"
        "        if row['status'] == 'closed':\n"
        "            return True\n"
        '        conn.execute("UPDATE tickets SET status = \'closed\' WHERE id = ?", (ticket_id,))\n'
        "        conn.commit()\n"
        "        return True\n\n"
        "def list_tickets(user_id: int | None = None, only_open: bool = True, limit: int = 20) -> list[dict]:\n"
        "    ensure()\n"
        '    q = "SELECT id, user_id, subject, status, created_at FROM tickets WHERE 1=1"\n'
        "    params: list = []\n"
        "    if user_id is not None:\n"
        '        q += " AND user_id = ?"\n'
        "        params.append(user_id)\n"
        "    if only_open:\n"
        '        q += " AND status = \'open\'"\n'
        '    q += " ORDER BY id DESC LIMIT ?"\n'
        "    params.append(limit)\n"
        "    with connect() as conn:\n"
        "        rows = conn.execute(q, params).fetchall()\n"
        "    return [dict(r) for r in rows]\n\n"
        "def my_tickets(user_id: int) -> list[dict]:\n"
        "    return list_tickets(user_id=user_id, only_open=True)\n\n"
        "def reply_ticket(ticket_id: int, user_id: int, body: str, staff: bool = False) -> bool:\n"
        "    ensure()\n"
        '    body = (body or "").strip()\n'
        "    if not body:\n"
        "        return False\n"
        "    with connect() as conn:\n"
        '        row = conn.execute("SELECT id, status FROM tickets WHERE id = ?", (ticket_id,)).fetchone()\n'
        "        if row is None or row['status'] == 'closed':\n"
        "            return False\n"
        "        conn.execute(\n"
        '            "INSERT INTO ticket_messages (ticket_id, user_id, is_staff, body) VALUES (?, ?, ?, ?)",\n'
        "            (ticket_id, user_id, 1 if staff else 0, body),\n"
        "        )\n"
        "        conn.commit()\n"
        "        return True\n\n"
        "def ticket_status(ticket_id: int) -> dict | None:\n"
        "    ensure()\n"
        "    with connect() as conn:\n"
        "        row = conn.execute(\n"
        '            "SELECT id, user_id, subject, status, created_at FROM tickets WHERE id = ?",\n'
        "            (ticket_id,),\n"
        "        ).fetchone()\n"
        "        if row is None:\n"
        "            return None\n"
        "        msgs = conn.execute(\n"
        '            "SELECT user_id, is_staff, body, created_at FROM ticket_messages WHERE ticket_id = ? ORDER BY id ASC LIMIT 10",\n'
        "            (ticket_id,),\n"
        "        ).fetchall()\n"
        "    data = dict(row)\n"
        "    data['messages'] = [dict(m) for m in msgs]\n"
        "    return data\n"
    )



def _emit_security() -> str:
    return (
        '"""Defensive security ops — reports & awareness (not offensive tooling)."""\n'
        "from __future__ import annotations\n\n"
        "from app.db import connect, init_db\n\n"
        "CHECKLIST = (\n"
        '    "1) لا تشارك كلمات المرور أو رموز التحقق\\n"\n'
        '    "2) راجع الروابط قبل الفتح\\n"\n'
        '    "3) فعّل التحقق بخطوتين\\n"\n'
        '    "4) بلّغ فورًا عن أي رسالة مشبوهة\\n"\n'
        '    "5) حدّث التطبيقات باستمرار"\n'
        ")\n\n"
        "def ensure() -> None:\n"
        "    init_db()\n\n"
        "def report(user_id: int, kind: str, body: str) -> int:\n"
        "    ensure()\n"
        '    kind = (kind or "incident").strip()[:40]\n'
        '    body = (body or "").strip() or "—"\n'
        "    with connect() as conn:\n"
        "        cur = conn.execute(\n"
        '            "INSERT INTO security_reports (user_id, kind, body, status) VALUES (?, ?, ?, \'open\')",\n'
        "            (user_id, kind, body[:2000]),\n"
        "        )\n"
        "        conn.commit()\n"
        "        return int(cur.lastrowid)\n\n"
        "def list_reports(only_open: bool = True, limit: int = 20) -> list[dict]:\n"
        "    ensure()\n"
        '    q = "SELECT id, user_id, kind, body, status, created_at FROM security_reports"\n'
        "    if only_open:\n"
        "        q += \" WHERE status = 'open'\"\n"
        "    q += \" ORDER BY id DESC LIMIT ?\"\n"
        "    with connect() as conn:\n"
        "        rows = conn.execute(q, (limit,)).fetchall()\n"
        "    return [dict(r) for r in rows]\n\n"
        "def close_report(report_id: int) -> bool:\n"
        "    ensure()\n"
        "    with connect() as conn:\n"
        '        cur = conn.execute("UPDATE security_reports SET status = \'closed\' WHERE id = ?", (report_id,))\n'
        "        conn.commit()\n"
        "        return cur.rowcount > 0\n\n"
        "def checklist() -> str:\n"
        "    return CHECKLIST\n"
    )



def _emit_extras() -> str:
    """Shared lightweight services: shop/booking/crm/reminders/community/edu/hr/utils/gate."""
    return (
        '"""Market extras — lightweight product modules (deterministic)."""\n'
        "from __future__ import annotations\n\n"
        "import random\n"
        "from datetime import datetime, timezone\n"
        "from app.db import connect, init_db\n\n"
        "def ensure() -> None:\n"
        "    init_db()\n\n"
        "def _add(user_id: int, kind: str, body: str, status: str = 'open') -> int:\n"
        "    ensure()\n"
        "    with connect() as conn:\n"
        "        cur = conn.execute(\n"
        '            "INSERT INTO extras_kv (user_id, kind, body, status) VALUES (?, ?, ?, ?)",\n'
        "            (user_id, kind, body[:2000], status),\n"
        "        )\n"
        "        conn.commit()\n"
        "        return int(cur.lastrowid)\n\n"
        "def _list(kind: str, user_id: int | None = None, only_open: bool = False, limit: int = 30) -> list[dict]:\n"
        "    ensure()\n"
        '    q = "SELECT id, user_id, kind, body, status, created_at FROM extras_kv WHERE kind = ?"\n'
        "    params: list = [kind]\n"
        "    if user_id is not None:\n"
        '        q += " AND user_id = ?"\n'
        "        params.append(user_id)\n"
        "    if only_open:\n"
        '        q += " AND status = \'open\'"\n'
        '    q += " ORDER BY id DESC LIMIT ?"\n'
        "    params.append(limit)\n"
        "    with connect() as conn:\n"
        "        return [dict(r) for r in conn.execute(q, params).fetchall()]\n\n"
        "def _close(item_id: int, kind: str | None = None) -> bool:\n"
        "    ensure()\n"
        "    with connect() as conn:\n"
        "        if kind:\n"
        '            cur = conn.execute("UPDATE extras_kv SET status = \'closed\' WHERE id = ? AND kind = ?", (item_id, kind))\n'
        "        else:\n"
        '            cur = conn.execute("UPDATE extras_kv SET status = \'closed\' WHERE id = ?", (item_id,))\n'
        "        conn.commit()\n"
        "        return cur.rowcount > 0\n\n"
        "# shop\n"
        "def catalog() -> str:\n"
        "    items = _list('product')\n"
        "    if not items:\n"
        "        return 'لا منتجات بعد'\n"
        "    return '\\n'.join(f\"#{i['id']} {i['body']}\" for i in items)\n\n"
        "def add_item(admin_id: int, title: str) -> int:\n"
        "    return _add(admin_id, 'product', title, 'open')\n\n"
        "def place_order(user_id: int, text: str) -> int:\n"
        "    return _add(user_id, 'order', text)\n\n"
        "def list_orders() -> list[dict]:\n"
        "    return _list('order', only_open=True)\n\n"
        "# booking\n"
        "def book_slot(user_id: int, slot: str) -> int:\n"
        "    return _add(user_id, 'booking', slot)\n\n"
        "def list_bookings(user_id: int) -> list[dict]:\n"
        "    return _list('booking', user_id=user_id, only_open=True)\n\n"
        "def cancel_booking(user_id: int, item_id: int) -> bool:\n"
        "    ensure()\n"
        "    with connect() as conn:\n"
        '        cur = conn.execute("UPDATE extras_kv SET status = \'closed\' WHERE id = ? AND user_id = ? AND kind = \'booking\'", (item_id, user_id))\n'
        "        conn.commit()\n"
        "        return cur.rowcount > 0\n\n"
        "def admin_list_bookings() -> list[dict]:\n"
        "    return _list('booking', only_open=True)\n\n"
        "# crm\n"
        "def lead_capture(user_id: int, text: str) -> int:\n"
        "    return _add(user_id, 'lead', text)\n\n"
        "def lead_list() -> list[dict]:\n"
        "    return _list('lead', only_open=True)\n\n"
        "# reminders\n"
        "def set_reminder(user_id: int, text: str) -> int:\n"
        "    return _add(user_id, 'reminder', text)\n\n"
        "def list_reminders(user_id: int) -> list[dict]:\n"
        "    return _list('reminder', user_id=user_id, only_open=True)\n\n"
        "def clear_reminders(user_id: int) -> int:\n"
        "    ensure()\n"
        "    with connect() as conn:\n"
        '        cur = conn.execute("UPDATE extras_kv SET status = \'closed\' WHERE user_id = ? AND kind = \'reminder\' AND status = \'open\'", (user_id,))\n'
        "        conn.commit()\n"
        "        return int(cur.rowcount)\n\n"
        "# community\n"
        "def feedback(user_id: int, text: str) -> int:\n"
        "    return _add(user_id, 'feedback', text)\n\n"
        "def suggest(user_id: int, text: str) -> int:\n"
        "    return _add(user_id, 'suggest', text)\n\n"
        "def report_user(user_id: int, text: str) -> int:\n"
        "    return _add(user_id, 'user_report', text)\n\n"
        "def poll_create(admin_id: int, text: str) -> int:\n"
        "    return _add(admin_id, 'poll', text)\n\n"
        "# edu / hr\n"
        "def course_list() -> str:\n"
        "    items = _list('course')\n"
        "    return '\\n'.join(f\"#{i['id']} {i['body']}\" for i in items) if items else 'لا دورات'\n\n"
        "def enroll(user_id: int, text: str) -> int:\n"
        "    return _add(user_id, 'enroll', text)\n\n"
        "def quiz_start() -> str:\n"
        "    return 'اختبار سريع: ما أقوى ممارسة أمنية؟ أ) مشاركة كلمة المرور ب) 2FA — اكتب إجابتك كرسالة'\n\n"
        "def leave_request(user_id: int, text: str) -> int:\n"
        "    return _add(user_id, 'leave', text)\n\n"
        "def leave_list() -> list[dict]:\n"
        "    return _list('leave', only_open=True)\n\n"
        "def checkin(user_id: int) -> int:\n"
        "    return _add(user_id, 'checkin', datetime.now(timezone.utc).isoformat())\n\n"
        "# gate / utils\n"
        "def verify_start() -> str:\n"
        "    return 'للتحقق أرسل: أنا لست روبوت'\n\n"
        "def verify_ok(text: str) -> bool:\n"
        "    return 'لست روبوت' in (text or '') or 'not a robot' in (text or '').lower()\n\n"
        "def force_sub_info() -> str:\n"
        "    return 'الاشتراك الإجباري: أضف قناتك هنا من الإعدادات لاحقًا. هذه نسخة معلوماتية.'\n\n"
        "def calc(expr: str) -> str:\n"
        "    allowed = set('0123456789+-*/(). %')\n"
        "    e = ''.join(ch for ch in (expr or '') if ch in allowed)\n"
        "    if not e:\n"
        "        return 'تعبير غير صالح'\n"
        "    try:\n"
        "        return str(eval(e, {'__builtins__': {}}, {}))  # noqa: S307 — filtered charset only\n"
        "    except Exception:\n"
        "        return 'تعذر الحساب'\n\n"
        "def time_now() -> str:\n"
        "    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')\n\n"
        "def echo(text: str) -> str:\n"
        "    return text or '—'\n\n"
        "def random_pick(text: str) -> str:\n"
        "    parts = [p.strip() for p in (text or '').split(',') if p.strip()]\n"
        "    return random.choice(parts) if parts else 'أدخل عناصر مفصولة بفاصلة'\n\n"
        "def short_note(user_id: int, text: str) -> int:\n"
        "    return _add(user_id, 'short_note', text)\n\n"
        "def stats_basic() -> str:\n"
        "    ensure()\n"
        "    with connect() as conn:\n"
        '        n = conn.execute("SELECT COUNT(*) AS c FROM extras_kv").fetchone()["c"]\n'
        "    return f'سجلات extras: {n}'\n"
    )


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
    need_welcome = any(_svc(f) == "welcome" for f in spec.features)
    need_tickets = any(_svc(f) == "tickets" for f in spec.features)
    need_security = any(_svc(f) == "security" for f in spec.features)
    _extra_set = {"shop", "booking", "crm", "reminders", "community", "edu", "hr", "utils", "gate"}
    need_extras = any(_svc(f) in _extra_set for f in spec.features)

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
    if need_welcome:
        imports.append("from app.services import welcome as welcome_svc")
    if need_tickets:
        imports.append("from app.services import tickets as tickets_svc")
    if need_security:
        imports.append("from app.services import security as security_svc")
    if need_extras:
        imports.append("from app.services import extras as extras_svc")

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
                if cap.method == "user_info":
                    lines.append("        await message.reply_text(f'user_id={target_id}')" )
                    lines.append("        return")
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
            elif cap.method == "faq":
                lines.append("    await message.reply_text(content_svc.faq() if hasattr(content_svc, 'faq') else content_svc.rules())")
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
            elif cap.method == "settings":
                lines.append("    await message.reply_text('الإعدادات: اللغة العربية افتراضيًا')")
            elif cap.method == "language":
                lines.append("    await message.reply_text('اللغة الحالية: العربية')")
            elif cap.method == "cancel":
                lines.append("    context.user_data.clear()")
                lines.append("    await message.reply_text('تم الإلغاء')")
            else:
                lines.append(f"    await message.reply_text({ok!r})")

        elif cap.service == "welcome":
            lines.append("    if chat is None:")
            lines.append(f"        await message.reply_text({fail!r})")
            lines.append("        return")
            if cap.method == "set_message":
                lines.append("    if context.args:")
                lines.append("        welcome_svc.set_message(chat.id, ' '.join(context.args))")
                lines.append(f"        await message.reply_text({ok!r})")
                lines.append("        return")
                lines.append("    context.user_data['awaiting'] = 'welcome_message'")
                lines.append("    await message.reply_text('أرسل نص الترحيب. استخدم {name} لاسم العضو')")
            elif cap.method == "toggle":
                lines.append("    enabled = welcome_svc.toggle(chat.id)")
                lines.append("    await message.reply_text('الترحيب مفعّل' if enabled else 'الترحيب متوقف')")
            elif cap.method == "show":
                lines.append("    cfg = welcome_svc.get_settings(chat.id)")
                lines.append("    state = 'مفعّل' if cfg['enabled'] else 'متوقف'")
                lines.append('    await message.reply_text(f"الحالة: {state}\\nالرسالة:\\n{cfg[\'message\']}")')
            elif cap.method == "test":
                lines.append("    name = user.full_name if user else 'عضو'")
                lines.append("    text = welcome_svc.format_welcome(chat.id, name) or 'الترحيب متوقف'")
                lines.append("    await message.reply_text(text)")
            else:
                lines.append(f"    await message.reply_text({ok!r})")

        elif cap.service == "tickets":
            if cap.method == "open_ticket":
                lines.append("    if context.args:")
                lines.append("        subject = ' '.join(context.args)")
                lines.append("        tid = tickets_svc.open_ticket(user.id, subject, chat.id if chat else 0)")
                lines.append(f"        await message.reply_text({ok!r} + f' #{{tid}}')")
                lines.append("        return")
                lines.append("    context.user_data['awaiting'] = 'ticket_subject'")
                lines.append("    await message.reply_text('اكتب موضوع تذكرة الدعم')")
            elif cap.method == "close_ticket":
                lines.append("    if not context.args:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    try:")
                lines.append("        tid = int(context.args[0])")
                lines.append("    except ValueError:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    ok_close = tickets_svc.close_ticket(tid, user_id=user.id, staff=False)")
                lines.append("    if not ok_close:")
                lines.append("        ok_close = tickets_svc.close_ticket(tid, staff=True)")
                lines.append(f"    await message.reply_text({ok!r} if ok_close else {fail!r})")
            elif cap.method == "my_tickets":
                lines.append("    items = tickets_svc.my_tickets(user.id)")
                lines.append("    if not items:")
                lines.append("        await message.reply_text('لا توجد تذاكر مفتوحة')")
                lines.append("        return")
                lines.append('    text = "\\n".join(f"#{i[\'id\']} [{i[\'status\']}] {i[\'subject\']}" for i in items)')
                lines.append("    await message.reply_text(text)")
            elif cap.method == "list_tickets":
                lines.append("    items = tickets_svc.list_tickets(only_open=True)")
                lines.append("    if not items:")
                lines.append("        await message.reply_text('لا توجد تذاكر مفتوحة')")
                lines.append("        return")
                lines.append('    text = "\\n".join(f"#{i[\'id\']} u={i[\'user_id\']} [{i[\'status\']}] {i[\'subject\']}" for i in items)')
                lines.append("    await message.reply_text(text)")
            elif cap.method == "reply_ticket":
                lines.append("    if len(context.args or []) < 2:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    try:")
                lines.append("        tid = int(context.args[0])")
                lines.append("    except ValueError:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    body = ' '.join(context.args[1:])")
                lines.append("    if tickets_svc.reply_ticket(tid, user.id, body, staff=True):")
                lines.append(f"        await message.reply_text({ok!r})")
                lines.append("    else:")
                lines.append(f"        await message.reply_text({fail!r})")
            elif cap.method == "ticket_status":
                lines.append("    if not context.args:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    try:")
                lines.append("        tid = int(context.args[0])")
                lines.append("    except ValueError:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    data = tickets_svc.ticket_status(tid)")
                lines.append("    if not data:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    msgs = data.get('messages') or []")
                lines.append("    parts = []")
                lines.append("    for m in msgs[-5:]:")
                lines.append("        role = 'staff' if m['is_staff'] else 'user'")
                lines.append("        parts.append(f'- {role}: {m[\'body\']}')")
                lines.append('    tail = "\\n".join(parts)')
                lines.append('    await message.reply_text(f"#{data[\'id\']} [{data[\'status\']}] {data[\'subject\']}\\n{tail}")')
            else:
                lines.append(f"    await message.reply_text({ok!r})")


        elif cap.service == "security":
            if cap.method == "checklist":
                lines.append("    await message.reply_text(security_svc.checklist())")
            elif cap.method in {"report_phish", "report_incident"}:
                kind = "phish" if cap.method == "report_phish" else "incident"
                lines.append("    if context.args:")
                lines.append(f"        rid = security_svc.report(user.id, {kind!r}, ' '.join(context.args))")
                lines.append(f"        await message.reply_text({ok!r} + f' #{{rid}}')")
                lines.append("        return")
                lines.append(f"    context.user_data['awaiting'] = 'sec_{kind}'")
                lines.append("    await message.reply_text('صف البلاغ بإيجاز (رابط/وصف)')")
            elif cap.method == "list_reports":
                lines.append("    items = security_svc.list_reports(only_open=True)")
                lines.append("    if not items:")
                lines.append("        await message.reply_text('لا بلاغات مفتوحة')")
                lines.append("        return")
                lines.append('    text = "\\n".join(f"#{i[\'id\']} [{i[\'kind\']}] {i[\'body\'][:60]}" for i in items)')
                lines.append("    await message.reply_text(text)")
            elif cap.method == "close_report":
                lines.append("    if not context.args:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    try:")
                lines.append("        rid = int(context.args[0])")
                lines.append("    except ValueError:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    if security_svc.close_report(rid):")
                lines.append(f"        await message.reply_text({ok!r})")
                lines.append("    else:")
                lines.append(f"        await message.reply_text({fail!r})")
            else:
                lines.append(f"    await message.reply_text({ok!r})")


        else:
            lines.append(f"    await message.reply_text({ok!r})")
        lines.append("")
        lines.append("")


    # text router for multi-step captures
    if need_tasks or need_notes or need_welcome or need_tickets or need_security:
        lines += [
            "async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:",
            "    message = update.effective_message",
            "    user = update.effective_user",
            "    chat = update.effective_chat",
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
            "    if awaiting == 'welcome_message' and chat is not None:",
            "        welcome_svc.set_message(chat.id, message.text.strip())",
            "        context.user_data.pop('awaiting', None)",
            "        await message.reply_text('تم حفظ رسالة الترحيب')",
            "        return",
            "    if awaiting == 'ticket_subject':",
            "        tid = tickets_svc.open_ticket(user.id, message.text.strip(), chat.id if chat else 0)",
            "        context.user_data.pop('awaiting', None)",
            "        await message.reply_text(f'تم فتح التذكرة #{tid}')",
            "        return",
            "    if awaiting == 'sec_phish':",
            "        rid = security_svc.report(user.id, 'phish', message.text.strip())",
            "        context.user_data.pop('awaiting', None)",
            "        await message.reply_text(f'تم تسجيل بلاغ التصيد #{rid}')",
            "        return",
            "    if awaiting == 'sec_incident':",
            "        rid = security_svc.report(user.id, 'incident', message.text.strip())",
            "        context.user_data.pop('awaiting', None)",
            "        await message.reply_text(f'تم تسجيل البلاغ الأمني #{rid}')",
            "        return",
            "",
            "",
        ]

    if need_welcome:
        lines += [
            "async def chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:",
            "    result = update.chat_member or update.my_chat_member",
            "    if result is None:",
            "        return",
            "    old = result.old_chat_member.status if result.old_chat_member else ''",
            "    new = result.new_chat_member.status if result.new_chat_member else ''",
            "    if new not in {'member', 'restricted'} or old in {'member', 'restricted', 'administrator', 'creator'}:",
            "        return",
            "    user = result.new_chat_member.user if result.new_chat_member else None",
            "    chat = result.chat",
            "    if user is None or user.is_bot:",
            "        return",
            "    text = welcome_svc.format_welcome(chat.id, user.full_name or user.first_name or 'عضو')",
            "    if text:",
            "        await context.bot.send_message(chat_id=chat.id, text=text)",
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
    need_welcome = any(
        (get_capability(f.feature) and get_capability(f.feature).service == "welcome")  # type: ignore
        for f in spec.features
    )
    need_tickets = any(
        (get_capability(f.feature) and get_capability(f.feature).service == "tickets")  # type: ignore
        for f in spec.features
    )
    need_security = any(
        (get_capability(f.feature) and get_capability(f.feature).service == "security")  # type: ignore
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
    if need_tasks or need_notes or need_welcome or need_tickets or need_security:
        imports_handlers += ", text_router"
    if need_welcome:
        imports_handlers += ", chat_member_handler"

    bot_cmds = ",\n        ".join(
        f"BotCommand({c!r}, {d!r})" for c, d in dict.fromkeys(commands)
    ) or 'BotCommand("start", "start")'

    text_handler = ""
    if need_tasks or need_notes or need_welcome or need_tickets or need_security:
        text_handler = "\n    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))"
    if need_welcome:
        text_handler += "\n    app.add_handler(ChatMemberHandler(chat_member_handler, ChatMemberHandler.CHAT_MEMBER))"

    return f'''"""Application entry — python-telegram-bot v21."""
from __future__ import annotations

import logging
import sys

from telegram import BotCommand, Update
from telegram.ext import Application, CallbackQueryHandler, ChatMemberHandler, CommandHandler, MessageHandler, filters

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
    return (
        "python-telegram-bot>=22.8,<23\n"
        "python-dotenv>=1.2.2\n"
    )


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
    if "welcome" in services:
        files["app/services/welcome.py"] = _emit_welcome()
    if "tickets" in services:
        files["app/services/tickets.py"] = _emit_tickets()
    if "security" in services:
        files["app/services/security.py"] = _emit_security()
    if {"shop", "booking", "crm", "reminders", "community", "edu", "hr", "utils", "gate"} & set(services):
        files["app/services/extras.py"] = _emit_extras()
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
