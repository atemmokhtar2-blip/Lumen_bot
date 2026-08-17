"""Emit service modules for generated bots (split package)."""
from __future__ import annotations

from ..schema import BotSpec

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




