"""Support tickets runtime — copied into generated bots as app/services/tickets.py.

Real ticket lifecycle: open → pending_staff → in_progress → resolved → closed.
Staff replies, user replies, assignment, and audit events — not a generic_kv dump.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.db import connect, init_db

_TICKET_TRANSITIONS: dict[str, frozenset[str]] = {
    "open": frozenset({"pending_staff", "in_progress", "closed"}),
    "pending_staff": frozenset({"in_progress", "closed"}),
    "in_progress": frozenset({"resolved", "pending_staff", "closed"}),
    "resolved": frozenset({"closed", "open"}),  # reopen
    "closed": frozenset({"open"}),  # reopen only
}


def ensure() -> None:
    init_db()
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL DEFAULT 0,
                subject TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                priority TEXT NOT NULL DEFAULT 'normal',
                assignee_id INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS ticket_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL DEFAULT 0,
                is_staff INTEGER NOT NULL DEFAULT 0,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS ticket_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                event TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                actor_id INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_tickets_user ON tickets(user_id, status);
            CREATE INDEX IF NOT EXISTS idx_ticket_msgs ON ticket_messages(ticket_id);
            """
        )
        for stmt in (
            "ALTER TABLE tickets ADD COLUMN priority TEXT NOT NULL DEFAULT 'normal'",
            "ALTER TABLE tickets ADD COLUMN assignee_id INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE tickets ADD COLUMN updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
        ):
            try:
                conn.execute(stmt)
            except Exception:
                pass
        conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _event(conn, ticket_id: int, event: str, note: str = "", actor_id: int = 0) -> None:
    conn.execute(
        "INSERT INTO ticket_events (ticket_id, event, note, actor_id) VALUES (?,?,?,?)",
        (int(ticket_id), event, (note or "")[:200], int(actor_id)),
    )


def open_ticket(
    user_id: int,
    subject: str,
    chat_id: int = 0,
    *,
    priority: str = "normal",
) -> int:
    ensure()
    subject = (subject or "").strip() or "بدون عنوان"
    pr = (priority or "normal").lower()
    if pr not in {"low", "normal", "high", "urgent"}:
        pr = "normal"
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO tickets (user_id, chat_id, subject, status, priority, updated_at) "
            "VALUES (?,?,?,?,?,?)",
            (int(user_id), int(chat_id or 0), subject[:200], "open", pr, _now()),
        )
        tid = int(cur.lastrowid)
        conn.execute(
            "INSERT INTO ticket_messages (ticket_id, user_id, is_staff, body) VALUES (?,?,0,?)",
            (tid, int(user_id), subject[:1000]),
        )
        _event(conn, tid, "opened", subject[:120], int(user_id))
        conn.commit()
        return tid


def transition(
    ticket_id: int,
    new_status: str,
    *,
    actor_id: int = 0,
    staff: bool = False,
    note: str = "",
) -> str:
    ensure()
    new_status = (new_status or "").strip().lower()
    with connect() as conn:
        row = conn.execute("SELECT * FROM tickets WHERE id=?", (int(ticket_id),)).fetchone()
        if not row:
            return f"❌ تذكرة #{ticket_id} غير موجودة"
        if not staff and actor_id and int(row["user_id"]) != int(actor_id):
            return "❌ غير مصرح"
        cur = (row["status"] or "open").lower()
        allowed = _TICKET_TRANSITIONS.get(cur, frozenset())
        if new_status not in allowed:
            return f"❌ انتقال غير مسموح: {cur} → {new_status}"
        conn.execute(
            "UPDATE tickets SET status=?, updated_at=? WHERE id=?",
            (new_status, _now(), int(ticket_id)),
        )
        _event(conn, int(ticket_id), new_status, note, int(actor_id))
        conn.commit()
    return f"✅ تذكرة #{ticket_id}: {cur} → {new_status}"


def close_ticket(ticket_id: int, user_id: int | None = None, staff: bool = False) -> bool:
    msg = transition(
        int(ticket_id),
        "closed",
        actor_id=int(user_id or 0),
        staff=bool(staff),
        note="close",
    )
    return msg.startswith("✅")


def reopen_ticket(ticket_id: int, user_id: int, staff: bool = False) -> str:
    return transition(int(ticket_id), "open", actor_id=int(user_id), staff=staff, note="reopen")


def assign(ticket_id: int, staff_id: int, actor_id: int = 0) -> str:
    ensure()
    with connect() as conn:
        row = conn.execute("SELECT id, status FROM tickets WHERE id=?", (int(ticket_id),)).fetchone()
        if not row:
            return f"❌ تذكرة #{ticket_id} غير موجودة"
        conn.execute(
            "UPDATE tickets SET assignee_id=?, status=CASE WHEN status='open' THEN 'in_progress' ELSE status END, "
            "updated_at=? WHERE id=?",
            (int(staff_id), _now(), int(ticket_id)),
        )
        _event(conn, int(ticket_id), "assigned", f"staff={staff_id}", int(actor_id or staff_id))
        conn.commit()
    return f"✅ تذكرة #{ticket_id} عُيّنت للموظف {staff_id}"


def reply(ticket_id: int, user_id: int, body: str, *, staff: bool = False) -> str:
    ensure()
    body = (body or "").strip()
    if not body:
        return "❌ نص الرد فارغ"
    with connect() as conn:
        row = conn.execute("SELECT * FROM tickets WHERE id=?", (int(ticket_id),)).fetchone()
        if not row:
            return f"❌ تذكرة #{ticket_id} غير موجودة"
        if (row["status"] or "") == "closed":
            return "❌ التذكرة مغلقة — أعد فتحها أولاً"
        if not staff and int(row["user_id"]) != int(user_id):
            return "❌ غير مصرح"
        conn.execute(
            "INSERT INTO ticket_messages (ticket_id, user_id, is_staff, body) VALUES (?,?,?,?)",
            (int(ticket_id), int(user_id), 1 if staff else 0, body[:2000]),
        )
        new_status = "pending_staff" if not staff else "in_progress"
        if (row["status"] or "") in {"open", "pending_staff", "in_progress", "resolved"}:
            conn.execute(
                "UPDATE tickets SET status=?, updated_at=? WHERE id=?",
                (new_status, _now(), int(ticket_id)),
            )
        _event(conn, int(ticket_id), "reply_staff" if staff else "reply_user", body[:80], int(user_id))
        conn.commit()
    who = "موظف" if staff else "مستخدم"
    return f"✅ رد {who} على تذكرة #{ticket_id}"


def list_tickets(
    user_id: int | None = None,
    only_open: bool = True,
    limit: int = 20,
) -> list[dict]:
    ensure()
    q = "SELECT id, user_id, subject, status, priority, assignee_id, created_at FROM tickets WHERE 1=1"
    params: list = []
    if user_id is not None:
        q += " AND user_id = ?"
        params.append(int(user_id))
    if only_open:
        q += " AND status NOT IN ('closed')"
    q += " ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END, id DESC LIMIT ?"
    params.append(int(limit))
    with connect() as conn:
        return [dict(r) for r in conn.execute(q, params).fetchall()]


def ticket_thread(ticket_id: int, limit: int = 30) -> str:
    ensure()
    with connect() as conn:
        t = conn.execute("SELECT * FROM tickets WHERE id=?", (int(ticket_id),)).fetchone()
        if not t:
            return f"❌ تذكرة #{ticket_id} غير موجودة"
        msgs = conn.execute(
            "SELECT user_id, is_staff, body, created_at FROM ticket_messages "
            "WHERE ticket_id=? ORDER BY id ASC LIMIT ?",
            (int(ticket_id), int(limit)),
        ).fetchall()
    lines = [
        f"【 تذكرة #{t['id']} 】",
        f"الحالة: {t['status']} | الأولوية: {t['priority']}",
        f"الموضوع: {t['subject']}",
        "— المحادثة —",
    ]
    for m in msgs:
        tag = "👤 موظف" if int(m["is_staff"]) else "🧑 مستخدم"
        lines.append(f"{tag}: {m['body']}")
    return "\n".join(lines)


def format_tickets(items: list[dict]) -> str:
    if not items:
        return "لا تذاكر"
    return "\n".join(
        f"#{i['id']} [{i.get('status')}/{i.get('priority','normal')}] {i.get('subject','')[:60]}"
        for i in items
    )
