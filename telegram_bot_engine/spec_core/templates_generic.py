"""Generic capability runtime — durable SQLite actions for any service.method.

Copied into generated projects as app/services/generic.py so scale/registry
capabilities are never empty "Done" stubs.
"""
from __future__ import annotations

from app.db import connect, init_db


def ensure() -> None:
    init_db()


def _kind(service: str, method: str) -> str:
    return f"{(service or 'gen')[:40]}:{(method or 'run')[:40]}"


def act(service: str, method: str, user_id: int, text: str = "") -> str:
    """Execute a capability by method naming conventions.

    list/view/search/stats/history → list open rows for service
    create/add/submit/open/buy → insert
    delete/cancel/close/archive → close by id or latest
    update → update body by id
    default → log event and acknowledge
    """
    ensure()
    service = (service or "gen").strip()[:40]
    method = (method or "run").strip()[:40]
    text = (text or "").strip()[:2000]
    m = method.lower()

    if m in {
        "list", "view", "search", "filter", "stats", "history", "audit", "export",
    }:
        kind = f"{service}:item"
        with connect() as conn:
            rows = conn.execute(
                "SELECT id, user_id, body, status, created_at FROM extras_kv "
                "WHERE kind=? AND status='open' ORDER BY id DESC LIMIT 30",
                (kind,),
            ).fetchall()
        if not rows:
            return f"No {service} items yet"
        return "\n".join(
            f"#{r['id']} {r['body'][:80]} [{r['status']}]" for r in rows
        )

    if m in {
        "create", "add", "submit", "open", "buy", "sell", "import_data",
        "duplicate", "share", "favorite", "pin",
    }:
        kind = f"{service}:item"
        body = text or f"{method} by {user_id}"
        with connect() as conn:
            cur = conn.execute(
                "INSERT INTO extras_kv (user_id, kind, body, status) VALUES (?,?,?, 'open')",
                (user_id, kind, body),
            )
            conn.commit()
            rid = int(cur.lastrowid)
        return f"Created #{rid} ({service}/{method})"

    if m in {"delete", "cancel", "close", "archive", "reject", "unpin", "unfavorite"}:
        kind = f"{service}:item"
        with connect() as conn:
            if text.isdigit():
                cur = conn.execute(
                    "UPDATE extras_kv SET status='closed' WHERE id=? AND kind=?",
                    (int(text), kind),
                )
            else:
                cur = conn.execute(
                    "UPDATE extras_kv SET status='closed' WHERE id=("
                    "SELECT id FROM extras_kv WHERE kind=? AND status='open' "
                    "ORDER BY id DESC LIMIT 1)",
                    (kind,),
                )
            conn.commit()
            n = int(cur.rowcount)
        return f"Closed {n} item(s)" if n else "Nothing to close"

    if m in {"update", "edit"}:
        parts = text.split(None, 1)
        if not parts or not parts[0].isdigit():
            return "Usage: <id> <new text>"
        iid = int(parts[0])
        body = parts[1] if len(parts) > 1 else ""
        with connect() as conn:
            cur = conn.execute(
                "UPDATE extras_kv SET body=? WHERE id=? AND status='open'",
                (body[:2000], iid),
            )
            conn.commit()
            n = int(cur.rowcount)
        return f"Updated #{iid}" if n else "Not found"

    kind = _kind(service, method)
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO extras_kv (user_id, kind, body, status) VALUES (?,?,?, 'open')",
            (user_id, kind, text or method),
        )
        conn.commit()
        rid = int(cur.lastrowid)
    return f"OK {service}.{method} #{rid}"
