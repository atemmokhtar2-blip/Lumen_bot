"""Generic capability runtime — deep durable SQLite for any service.method.

Copied into generated projects as app/services/generic.py.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from app.db import connect, init_db


def ensure() -> None:
    init_db()
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS domain_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service TEXT NOT NULL,
                user_id INTEGER NOT NULL DEFAULT 0,
                title TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                meta TEXT NOT NULL DEFAULT '{}',
                amount REAL NOT NULL DEFAULT 0,
                ref_id INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_domain_svc ON domain_items(service, status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_domain_user ON domain_items(user_id, service)")
        conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _insert(service: str, user_id: int, title: str, body: str = "", status: str = "open",
            meta: dict[str, Any] | None = None, amount: float = 0.0, ref_id: int = 0) -> int:
    ensure()
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO domain_items
               (service, user_id, title, body, status, meta, amount, ref_id, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (service[:40], int(user_id), (title or "")[:200], (body or "")[:4000], status[:40],
             json.dumps(meta or {}, ensure_ascii=False), float(amount or 0), int(ref_id or 0), _now()),
        )
        conn.commit()
        return int(cur.lastrowid)


def _list(service: str, *, user_id: int | None = None, status: str | None = "open", limit: int = 30):
    ensure()
    q, args = "SELECT * FROM domain_items WHERE service=?", [service]
    if user_id is not None:
        q += " AND user_id=?"
        args.append(int(user_id))
    if status:
        q += " AND status=?"; args.append(status)
    q += " ORDER BY id DESC LIMIT ?"; args.append(int(limit))
    with connect() as conn:
        return list(conn.execute(q, tuple(args)).fetchall())


def _get(iid: int):
    ensure()
    with connect() as conn:
        return conn.execute("SELECT * FROM domain_items WHERE id=?", (int(iid),)).fetchone()


def _set_status(iid: int, status: str, *, user_id: int | None = None) -> bool:
    ensure()
    with connect() as conn:
        if user_id is None:
            cur = conn.execute("UPDATE domain_items SET status=?, updated_at=? WHERE id=?",
                               (status[:40], _now(), int(iid)))
        else:
            cur = conn.execute(
                "UPDATE domain_items SET status=?, updated_at=? WHERE id=? AND user_id=?",
                (status[:40], _now(), int(iid), int(user_id)),
            )
        conn.commit()
        return int(cur.rowcount) > 0


def _fmt(rows, empty: str) -> str:
    if not rows:
        return empty
    return "\n".join(
        f"#{r['id']} [{r['status']}] {r['title'][:60] or r['body'][:60]}"
        + (f" amt={r['amount']}" if float(r["amount"] or 0) else "")
        for r in rows
    )


def _first_id(text: str):
    parts = (text or "").split()
    if parts and parts[0].lstrip("#").isdigit():
        return int(parts[0].lstrip("#"))
    return None


def _rest(text: str) -> str:
    parts = (text or "").split(None, 1)
    return parts[1] if len(parts) > 1 else ""


def _clinic(m, uid, text):
    if m in {"slots", "list", "schedule", "view"}:
        rows = _list("clinic", status="open", limit=20)
        if not rows:
            for h in ("09:00", "11:00", "14:00", "16:00"):
                _insert("clinic", 0, f"Slot {h}", f"Available {h}", "open")
            rows = _list("clinic", status="open", limit=20)
        return _fmt(rows, "No clinic slots")
    if m in {"book", "create", "add", "reserve"}:
        return f"Booked clinic appointment #{_insert('clinic', uid, text or f'Appt {uid}', 'booked', 'booked')}: {text or 'appt'}"
    if m in {"cancel", "delete"}:
        iid = _first_id(text)
        return f"Cancelled #{iid}" if iid and _set_status(iid, "cancelled", user_id=uid) else "Usage: <id>"
    if m in {"my", "mine"}:
        return _fmt(_list("clinic", user_id=uid, status=None, limit=20), "No appointments")
    return ""


def _jobs(m, uid, text):
    if m in {"list", "search", "view"}:
        rows = _list("jobs", status="open", limit=30)
        if not rows:
            for t in ("Backend Engineer", "Product Designer", "Growth Marketer"):
                _insert("jobs", 0, t, "Remote", "open")
            rows = _list("jobs", status="open", limit=30)
        return _fmt(rows, "No jobs")
    if m in {"post", "create", "add"}:
        return f"Job posted #{_insert('jobs', uid, text or 'Job', text, 'open')}"
    if m in {"apply", "submit"}:
        iid = _first_id(text)
        if not iid:
            return "Usage: <job_id> [note]"
        job = _get(iid)
        if not job or job["service"] != "jobs":
            return "Job not found"
        return f"Application #{_insert('job_apps', uid, f'App→#{iid}', _rest(text) or 'app', 'submitted', ref_id=iid)}"
    if m in {"my_apps", "mine", "my"}:
        return _fmt(_list("job_apps", user_id=uid, status=None, limit=30), "No applications")
    return ""


def _edu(m, uid, text):
    if m in {"course_list", "list", "catalog", "view"}:
        rows = _list("courses", status="open", limit=30)
        if not rows:
            for t, p in (("Python 101", 0), ("Bots Pro", 29), ("SQL", 19)):
                _insert("courses", 0, t, f"price={p}", "open", amount=p)
            rows = _list("courses", status="open", limit=30)
        return _fmt(rows, "No courses")
    if m in {"enroll", "course_enroll", "join", "buy"}:
        iid = _first_id(text) or 0
        return f"Enrolled #{_insert('enrollments', uid, _rest(text) or f'course #{iid}', 'enrolled', 'active', ref_id=iid)}"
    if m in {"quiz_start", "quiz"}:
        return f"Quiz #{_insert('quizzes', uid, 'Quiz', text or 'default', 'in_progress')} started"
    if m in {"quiz_score", "score"}:
        score = int(text.split()[0]) if text and text.split()[0].isdigit() else 0
        return f"Score saved #{_insert('quizzes', uid, 'Score', f'score={score}', 'done', amount=score)}"
    if m in {"homework_submit", "submit"}:
        return f"Homework #{_insert('homework', uid, 'HW', text or 'sub', 'submitted')}"
    if m in {"certificate_issue", "certificate"}:
        return f"Certificate #{_insert('certificates', uid, 'Cert', text or 'done', 'issued')}"
    if m in {"progress_view", "progress"}:
        ens = _list("enrollments", user_id=uid, status=None, limit=20)
        qs = _list("quizzes", user_id=uid, status="done", limit=50)
        done = len(qs)
        enrolled = max(len(ens), 1)
        pct = min(100, int(100 * done / max(enrolled * 3, 1)))
        return (
            f"Progress ~{pct}% (quizzes done={done}, enrollments={len(ens)})\n"
            + _fmt(ens, "no enrollments")
        )
    if m in {"lesson_list", "lessons"}:
        return _fmt(_list("lessons", status="open", limit=20), "No lessons")
    if m in {"lesson_open", "open_lesson"}:
        iid = _first_id(text)
        row = _get(iid) if iid else None
        return f"Lesson #{iid}: {row['title']}\n{row['body']}" if row else f"Opened #{_insert('lessons', 0, text or 'Lesson', 'body', 'open')}"
    return ""


def _events(m, uid, text):
    if m in {"list", "view", "search"}:
        rows = _list("events", status="open", limit=30)
        if not rows:
            _insert("events", 0, "Meetup", "soon", "open")
            rows = _list("events", status="open", limit=30)
        return _fmt(rows, "No events")
    if m in {"create", "add"}:
        return f"Event #{_insert('events', uid, text or 'Event', text, 'open')}"
    if m in {"rsvp", "join", "book"}:
        iid = _first_id(text)
        return f"RSVP #{_insert('rsvps', uid, f'RSVP→#{iid}', 'yes', 'confirmed', ref_id=iid or 0)}" if iid else "Usage: <event_id>"
    return ""


def _restaurant(m, uid, text):
    if m in {"menu_view", "menu", "list", "view", "catalog"}:
        rows = _list("menu", status="open", limit=40)
        if not rows:
            for t, p in (("Burger", 45), ("Pasta", 55), ("Salad", 30)):
                _insert("menu", 0, t, f"EGP {p}", "open", amount=p)
            rows = _list("menu", status="open", limit=40)
        return _fmt(rows, "Empty menu")
    if m in {"menu_order", "order", "buy", "create"}:
        return f"Order #{_insert('rest_orders', uid, text or 'Order', text, 'pending')}"
    if m in {"order_status", "status", "track"}:
        iid = _first_id(text)
        if iid:
            row = _get(iid)
            if row:
                return f"Order #{iid}: {row['status']} — {row['title']}"
        return _fmt(_list("rest_orders", user_id=uid, status=None, limit=10), "No orders")
    if m in {"table_book", "book", "reserve"}:
        return f"Table #{_insert('tables', uid, text or 'Table', 'reserved', 'reserved')}"
    return ""


def _auction(m, uid, text):
    if m in {"list", "view", "search"}:
        rows = _list("auctions", status="open", limit=30)
        if not rows:
            _insert("auctions", 0, "Rare Item", "start 100", "open", amount=100)
            rows = _list("auctions", status="open", limit=30)
        return _fmt(rows, "No auctions")
    if m in {"create", "add"}:
        nums = re.findall(r"\d+(?:\.\d+)?", text or "")
        amt = float(nums[0]) if nums else 0.0
        return f"Auction #{_insert('auctions', uid, text or 'Auction', text, 'open', amount=amt)} (start={amt})"
    if m in {"bid", "offer"}:
        iid = _first_id(text)
        nums = re.findall(r"\d+(?:\.\d+)?", _rest(text))
        if not iid or not nums:
            return "Usage: <auction_id> <amount>"
        amt = float(nums[0])
        row = _get(iid)
        if not row or row["service"] != "auctions":
            return "Auction not found"
        if amt <= float(row["amount"] or 0):
            return f"Bid must be > current {row['amount']}"
        with connect() as conn:
            conn.execute("UPDATE domain_items SET amount=?, updated_at=? WHERE id=?", (amt, _now(), iid))
            conn.commit()
        return f"Bid #{_insert('bids', uid, f'Bid→#{iid}', f'amount={amt}', 'active', amount=amt, ref_id=iid)} accepted"
    if m in {"my_bids", "mine"}:
        return _fmt(_list("bids", user_id=uid, status=None, limit=30), "No bids")
    return ""


def _delivery(m, uid, text):
    stages = ["created", "picked", "in_transit", "out_for_delivery", "delivered", "returned"]
    if m in {"create", "add"}:
        return f"Shipment #{_insert('shipments', uid, text or 'Shipment', text, 'created')}"
    if m in {"advance", "next_stage"}:
        iid = _first_id(text)
        if not iid:
            return "Usage: <shipment_id>"
        row = _get(iid)
        if not row or row["service"] != "shipments":
            return "Shipment not found"
        cur = row["status"]
        try:
            i = stages.index(cur)
        except ValueError:
            i = 0
        if i >= len(stages) - 1:
            return f"Shipment #{iid} already at {cur}"
        nxt = stages[i + 1]
        _set_status(iid, nxt)
        return f"Shipment #{iid}: {cur} → {nxt}"
    if m in {"track", "status", "view"}:
        iid = _first_id(text)
        if iid:
            row = _get(iid)
            if row and row["service"] == "shipments":
                return f"Shipment #{iid}: {row['status']} — {row['title']}\n{row['body']}"
            return f"Shipment #{iid} not found"
        return _fmt(_list("shipments", user_id=uid, status=None, limit=15), "No shipments")
    if m in {"list"}:
        return _fmt(_list("shipments", status=None, limit=30), "No shipments")
    return ""


def _crm(m, uid, text):
    if m in {"lead_capture", "create", "add", "capture"}:
        return f"Lead #{_insert('leads', uid, text or 'Lead', text, 'new')}"
    if m in {"lead_list", "list", "view", "search"}:
        return _fmt(_list("leads", status=None, limit=40), "No leads")
    if m in {"lead_status", "status", "update"}:
        iid = _first_id(text)
        st = _rest(text) or "qualified"
        return f"Lead #{iid} → {st}" if iid and _set_status(iid, st) else "Usage: <id> <status>"
    if m in {"deal_create", "deal"}:
        return f"Deal #{_insert('deals', uid, text or 'Deal', text, 'open')}"
    if m in {"pipeline_board", "pipeline", "board"}:
        rows = _list("deals", status=None, limit=50)
        by: dict[str, int] = {}
        for r in rows:
            by[r["status"]] = by.get(r["status"], 0) + 1
        return "Pipeline empty" if not by else "Pipeline:\n" + "\n".join(f"  {k}: {v}" for k, v in sorted(by.items()))
    if m in {"followup_set", "followup"}:
        return f"Follow-up #{_insert('followups', uid, text or 'FU', text, 'scheduled')}"
    if m in {"customer_profile", "profile"}:
        return f"Profile {uid}\n" + _fmt(_list("leads", user_id=uid, status=None, limit=10), "—")
    return ""


def _booking(m, uid, text):
    if m in {"book_slot", "book", "create", "reserve"}:
        return f"Booking #{_insert('bookings', uid, text or 'Booking', text, 'booked')}"
    if m in {"book_list", "list", "view", "mine", "my"}:
        return _fmt(_list("bookings", user_id=uid, status=None, limit=30), "No bookings")
    if m in {"book_cancel", "cancel", "delete"}:
        iid = _first_id(text)
        return f"Cancelled #{iid}" if iid and _set_status(iid, "cancelled", user_id=uid) else "Usage: <id>"
    if m in {"book_admin_list", "admin_list"}:
        return _fmt(_list("bookings", status=None, limit=50), "No bookings")
    return ""


def _community(m, uid, text):
    if m in {"post_create", "create", "add", "post"}:
        return f"Post #{_insert('posts', uid, (text or 'Post')[:80], text, 'published')}"
    if m in {"feed_view", "list", "view", "feed"}:
        return _fmt(_list("posts", status="published", limit=30), "Feed empty")
    if m in {"post_like", "like"}:
        iid = _first_id(text)
        return f"Liked #{iid}" if iid else "Usage: <post_id>"
    if m in {"report_content", "report"}:
        return f"Report #{_insert('reports', uid, 'Report', text or 'report', 'open')}"
    if m in {"mod_queue", "queue"}:
        return _fmt(_list("reports", status="open", limit=30), "Mod queue empty")
    if m in {"profile_set", "profile_view", "profile"}:
        if m == "profile_set" or text:
            return f"Profile #{_insert('profiles', uid, 'Profile', text or '', 'active')}"
        rows = _list("profiles", user_id=uid, status=None, limit=1)
        return rows[0]["body"] if rows else "No profile"
    return ""


def _hr(m, uid, text):
    if m in {"hr_checkin", "checkin", "check_in"}:
        return f"Checked in #{_insert('attendance', uid, 'Check-in', _now(), 'present')}"
    if m in {"hr_leave_request", "leave", "request"}:
        return f"Leave #{_insert('leave', uid, text or 'Leave', text, 'pending')}"
    if m in {"hr_leave_list", "list"}:
        return _fmt(_list("leave", user_id=uid, status=None, limit=20), "No leave requests")
    return ""


_HANDLERS = {
    "clinic": _clinic, "jobs": _jobs, "edu": _edu, "education": _edu,
    "events": _events, "restaurant": _restaurant, "auction": _auction, "auctions": _auction,
    "delivery": _delivery, "crm": _crm, "booking": _booking, "community": _community,
    "hr": _hr, "marketplace": _community,
}


def act(service: str, method: str, user_id: int, text: str = "") -> str:
    ensure()
    service = (service or "gen").strip()[:40]
    method = (method or "run").strip()[:40]
    text = (text or "").strip()[:2000]
    m, svc, uid = method.lower(), service.lower(), int(user_id)
    h = _HANDLERS.get(svc)
    if h:
        out = h(m, uid, text)
        if out:
            return out
    if m in {"list", "view", "search", "filter", "stats", "history", "catalog", "board", "feed"}:
        if m == "stats":
            with connect() as conn:
                open_c = conn.execute(
                    "SELECT COUNT(*) c FROM domain_items WHERE service=? AND status='open'", (svc,)
                ).fetchone()["c"]
                all_c = conn.execute(
                    "SELECT COUNT(*) c FROM domain_items WHERE service=?", (svc,)
                ).fetchone()["c"]
            return f"{svc} stats: open={open_c} total={all_c}"
        return _fmt(_list(svc, status=None if m in {"history", "stats"} else "open", limit=30), f"No {svc} items")
    if m in {"create", "add", "submit", "open", "buy", "post", "book", "apply", "join", "rsvp", "order", "enroll"}:
        return f"Created #{_insert(svc, uid, text[:80] or method, text or method, 'open')} ({svc}/{method})"
    if m in {"delete", "cancel", "close", "archive", "reject", "end"}:
        iid = _first_id(text)
        with connect() as conn:
            if iid:
                cur = conn.execute(
                    "UPDATE domain_items SET status='closed', updated_at=? WHERE id=? AND service=?",
                    (_now(), iid, svc),
                )
            else:
                cur = conn.execute(
                    "UPDATE domain_items SET status='closed', updated_at=? WHERE id=("
                    "SELECT id FROM domain_items WHERE service=? AND status='open' ORDER BY id DESC LIMIT 1)",
                    (_now(), svc),
                )
            conn.commit()
            n = int(cur.rowcount)
        return f"Closed {n} item(s)" if n else "Nothing to close"
    if m in {"update", "edit", "assign", "set_status"}:
        iid = _first_id(text)
        body = _rest(text)
        if not iid:
            return "Usage: <id> <value>"
        if m in {"assign", "set_status"} and body:
            return f"#{iid} → {body.split()[0]}" if _set_status(iid, body.split()[0]) else "Not found"
        with connect() as conn:
            cur = conn.execute(
                "UPDATE domain_items SET body=?, updated_at=? WHERE id=?",
                (body[:4000], _now(), iid),
            )
            conn.commit()
            return f"Updated #{iid}" if int(cur.rowcount) else "Not found"
    if m in {"track", "status", "my", "mine"}:
        if m in {"my", "mine"}:
            return _fmt(_list(svc, user_id=uid, status=None, limit=20), f"No {svc} for you")
        iid = _first_id(text)
        if iid:
            row = _get(iid)
            if row:
                return f"#{iid} [{row['status']}] {row['title']}\n{row['body']}"
        return _fmt(_list(svc, user_id=uid, status=None, limit=15), f"No {svc} data")
    return f"OK {svc}.{method} #{_insert(svc, uid, method, text or method, 'open', {'method': method})} saved"
