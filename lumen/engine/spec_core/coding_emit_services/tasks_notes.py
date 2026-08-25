"""Emit service modules for generated bots (split package)."""
from __future__ import annotations

from ..schema import BotSpec

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




