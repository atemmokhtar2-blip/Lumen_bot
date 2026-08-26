"""Tasks + notes runtime — copied as app/services/tasks.py and notes helpers.

Tasks: open → done / cancelled, optional due_ts and priority.
Not a generic_kv bag.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone

from app.db import connect, init_db


def ensure() -> None:
    init_db()
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                priority TEXT NOT NULL DEFAULT 'normal',
                due_ts INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_user ON tasks(user_id, status);
            CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user_id, status);
            """
        )
        for stmt in (
            "ALTER TABLE tasks ADD COLUMN priority TEXT NOT NULL DEFAULT 'normal'",
            "ALTER TABLE tasks ADD COLUMN due_ts INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE tasks ADD COLUMN updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
        ):
            try:
                conn.execute(stmt)
            except Exception:
                pass
        conn.commit()


def _parse_task(text: str) -> tuple[str, str, int]:
    """Return (title, priority, due_ts). Supports !high / !urgent and 'بعد N ساعة'."""
    raw = (text or "").strip()
    pr = "normal"
    due = 0
    m = re.search(r"!(high|urgent|low|normal)\b", raw, re.I)
    if m:
        pr = m.group(1).lower()
        raw = (raw[: m.start()] + raw[m.end() :]).strip()
    m2 = re.search(
        r"(?:بعد|in)\s+(\d+)\s*(دقيقة|دقائق|minute|minutes|m|ساعة|ساعات|hour|hours|h|يوم|أيام|day|days|d)?",
        raw,
        re.I,
    )
    if m2:
        n = int(m2.group(1))
        unit = (m2.group(2) or "m").lower()
        now = int(time.time())
        if unit in {"دقيقة", "دقائق", "minute", "minutes", "m"}:
            due = now + n * 60
        elif unit in {"ساعة", "ساعات", "hour", "hours", "h"}:
            due = now + n * 3600
        else:
            due = now + n * 86400
        raw = (raw[: m2.start()] + raw[m2.end() :]).strip(" -–—,:،")
    title = raw[:300] or "مهمة"
    return title, pr, due


def add_task(user_id: int, text: str) -> int:
    ensure()
    title, pr, due = _parse_task(text)
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO tasks (user_id, title, status, priority, due_ts) VALUES (?,?,?,?,?)",
            (int(user_id), title, "open", pr, int(due)),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_tasks(user_id: int, only_open: bool = True, limit: int = 30) -> list[dict]:
    ensure()
    q = "SELECT id, title, status, priority, due_ts, created_at FROM tasks WHERE user_id=?"
    params: list = [int(user_id)]
    if only_open:
        q += " AND status='open'"
    q += " ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END, due_ts ASC, id DESC LIMIT ?"
    params.append(int(limit))
    with connect() as conn:
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    now = int(time.time())
    for r in rows:
        due = int(r.get("due_ts") or 0)
        r["overdue"] = bool(due and due < now and r.get("status") == "open")
        r["due_in_min"] = max(0, (due - now) // 60) if due else None
    return rows


def format_tasks(items: list[dict]) -> str:
    if not items:
        return "لا مهام مفتوحة"
    lines = []
    for r in items:
        flag = "⚠️" if r.get("overdue") else ("🔥" if r.get("priority") == "urgent" else "•")
        due = ""
        if r.get("due_ts"):
            due = f" | خلال {r.get('due_in_min')} د" if not r.get("overdue") else " | متأخرة"
        lines.append(f"{flag} #{r['id']} [{r.get('priority')}] {r.get('title')}{due}")
    return "\n".join(lines)


def done_task(user_id: int, task_id: int) -> bool:
    ensure()
    with connect() as conn:
        cur = conn.execute(
            "UPDATE tasks SET status='done', updated_at=CURRENT_TIMESTAMP "
            "WHERE id=? AND user_id=? AND status='open'",
            (int(task_id), int(user_id)),
        )
        conn.commit()
        return cur.rowcount > 0


def delete_task(user_id: int, task_id: int) -> bool:
    ensure()
    with connect() as conn:
        cur = conn.execute(
            "UPDATE tasks SET status='cancelled', updated_at=CURRENT_TIMESTAMP "
            "WHERE id=? AND user_id=? AND status='open'",
            (int(task_id), int(user_id)),
        )
        conn.commit()
        return cur.rowcount > 0


def clear_done(user_id: int) -> int:
    ensure()
    with connect() as conn:
        cur = conn.execute(
            "UPDATE tasks SET status='archived' WHERE user_id=? AND status='done'",
            (int(user_id),),
        )
        conn.commit()
        return int(cur.rowcount)


def add_note(user_id: int, body: str) -> int:
    ensure()
    body = (body or "").strip()[:1000] or "ملاحظة"
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO notes (user_id, body, status) VALUES (?,?,?)",
            (int(user_id), body, "open"),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_notes(user_id: int, limit: int = 30) -> list[dict]:
    ensure()
    with connect() as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT id, body, created_at FROM notes WHERE user_id=? AND status='open' "
                "ORDER BY id DESC LIMIT ?",
                (int(user_id), int(limit)),
            ).fetchall()
        ]


def delete_note(user_id: int, note_id: int) -> bool:
    ensure()
    with connect() as conn:
        cur = conn.execute(
            "UPDATE notes SET status='deleted' WHERE id=? AND user_id=? AND status='open'",
            (int(note_id), int(user_id)),
        )
        conn.commit()
        return cur.rowcount > 0


def format_notes(items: list[dict]) -> str:
    if not items:
        return "لا ملاحظات"
    return "\n".join(f"#{i['id']} {i['body'][:120]}" for i in items)
