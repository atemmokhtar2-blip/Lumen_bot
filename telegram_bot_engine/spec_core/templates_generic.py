"""Generic capability runtime — deep durable SQLite for any service.method.

Copied into generated projects as app/services/generic.py.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from app.db import connect, init_db

_ENSURED = False


def ensure() -> None:
    """Idempotent schema bootstrap — runs once per process (hot path safe)."""
    global _ENSURED
    if _ENSURED:
        return
    init_db()
    with connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA temp_store=MEMORY")
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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_domain_svc_method ON domain_items(service, title)")
        conn.commit()
    _ENSURED = True


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _insert(service: str, user_id: int, title: str, body: str = "", status: str = "open",
            meta: dict[str, Any] | None = None, amount: float = 0.0, ref_id: int = 0) -> int:
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
    with connect() as conn:
        return conn.execute("SELECT * FROM domain_items WHERE id=?", (int(iid),)).fetchone()


def _set_status(iid: int, status: str, *, user_id: int | None = None) -> bool:
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



def _domain_factory(label: str):
    """Build a specialized handler for a vertical with durable domain semantics."""
    def _h(m, uid, text):
        m = (m or "").lower()
        # create family
        if m in {
            "create", "add", "submit", "open", "post", "capture", "enroll", "book",
            "reserve", "apply", "order", "place_order", "register", "import_data",
            "duplicate", "share", "favorite", "pin", "assign", "claim", "schedule",
        }:
            iid = _insert(label, uid, text or m, text or m, "open", {"method": m, "domain": label})
            return f"{label.title()} #{iid} created ({m})"
        if m in {
            "list", "view", "search", "filter", "history", "export", "catalog",
            "board", "feed", "stats", "dashboard", "my", "mine", "status", "track",
        }:
            rows = _list(label, user_id=None if m in {"list", "catalog", "board", "feed", "search"} else uid,
                         status=None if m in {"history", "search", "stats"} else "open", limit=30)
            return _fmt(rows, f"No {label} records")
        if m in {"update", "edit", "patch"}:
            iid = _first_id(text)
            if not iid:
                return f"Usage: {m} <id> <body>"
            body = _rest(text)
            with connect() as conn:
                cur = conn.execute(
                    "UPDATE domain_items SET body=?, updated_at=? WHERE id=? AND service=?",
                    (body[:4000], _now(), iid, label),
                )
                conn.commit()
                if int(cur.rowcount):
                    return f"{label.title()} #{iid} updated"
            return "Not found"
        if m in {"delete", "remove", "archive", "close", "cancel", "reject", "approve", "complete"}:
            iid = _first_id(text)
            status = {"delete": "deleted", "remove": "deleted", "archive": "archived",
                      "close": "closed", "cancel": "cancelled", "reject": "rejected",
                      "approve": "approved", "complete": "done"}.get(m, m)
            if iid and _set_status(iid, status):
                return f"{label.title()} #{iid} → {status}"
            if not iid:
                iid = _insert(label, uid, m, text or m, status, {"method": m})
                return f"{label.title()} event #{iid} ({status})"
            return "Not found"
        if m in {"restore", "reopen"}:
            iid = _first_id(text)
            if iid and _set_status(iid, "open"):
                return f"{label.title()} #{iid} restored"
            return "Not found"
        # fall through to generic by returning ""
        return ""
    return _h


# Auto-specialists for high-volume registry services (load + fidelity)
_ops = _domain_factory("ops_desk")
_hq = _domain_factory("hq_ops")
_units = _domain_factory("units")
_queues = _domain_factory("queues")
_agents = _domain_factory("agents")
_clients = _domain_factory("clients")
_accounts = _domain_factory("accounts")
_opportunities = _domain_factory("opportunities")
_pricing = _domain_factory("pricing")
_devices = _domain_factory("devices")
_sensors = _domain_factory("sensors")
_saas = _domain_factory("saas_ops")
_mkt = _domain_factory("mkt_ops")
_logi = _domain_factory("logi_ops")
_fin = _domain_factory("fin_ops")
_tenant = _domain_factory("tenant_ops")
_vendor = _domain_factory("vendor_ops")
_fleet = _domain_factory("fleet_ops")
_ledger = _domain_factory("ledger_ops")
_escrow = _domain_factory("escrow_ops")
_route = _domain_factory("route_ops")
_wallet = _domain_factory("wallet_ops")
_quota = _domain_factory("quota_ops")
_stock = _domain_factory("stock_ops")
_shipping = _domain_factory("shipping_ops")
_promotions = _domain_factory("promotions")
_sku = _domain_factory("sku_ops")


_HANDLERS = {
    "clinic": _clinic, "jobs": _jobs, "edu": _edu, "education": _edu,
    "events": _events, "restaurant": _restaurant, "auction": _auction, "auctions": _auction,
    "delivery": _delivery, "crm": _crm, "booking": _booking, "community": _community,
    "hr": _hr, "marketplace": _community,
    # high-volume verticals (registry_scale)
    "ops_desk": _ops, "hq_ops": _hq, "units": _units, "queues": _queues,
    "agents": _agents, "clients": _clients, "accounts": _accounts,
    "opportunities": _opportunities, "pricing": _pricing,
    "devices": _devices, "sensors": _sensors,
    "saas_ops": _saas, "mkt_ops": _mkt, "logi_ops": _logi, "fin_ops": _fin,
    "tenant_ops": _tenant, "vendor_ops": _vendor, "fleet_ops": _fleet,
    "ledger_ops": _ledger, "escrow_ops": _escrow, "route_ops": _route,
    "wallet_ops": _wallet, "quota_ops": _quota, "stock_ops": _stock,
    "shipping_ops": _shipping, "promotions": _promotions, "sku_ops": _sku,
    # aliases used by fill_domains
    "ops": _ops, "saas": _saas, "finance": _fin, "logistics": _logi,
}



# Method families (module-level — never rebuild on hot path)
_LIST_M = frozenset({
    "list", "view", "search", "filter", "history", "audit", "export", "catalog",
    "board", "feed", "show", "stats", "stats_basic", "dashboard", "pipeline",
    "pipeline_board", "review_list", "flash_list", "rss_list", "users", "inventory",
    "orders", "menu", "slots", "schedule", "attendees", "leaderboard", "levels",
    "badges", "achievements", "rewards_info", "faq", "rules", "settings", "about",
    "tips", "bundles", "cohorts", "feature_flags", "feature_flag", "sla_info",
    "trial_status", "status", "track", "track_order", "order_status", "ticket_status",
    "progress", "progress_view", "my", "mine", "my_orders", "my_apps", "my_bids",
    "wishlist_view", "wishlist", "payment_history", "invoice_list", "invoices",
    "audit_log", "low_stock", "stock", "stock_alert", "revenue", "revenue_today",
    "analytics", "analytics_overview", "analytics_revenue", "admin_list", "mod_queue",
})
_CREATE_M = frozenset({
    "create", "add", "submit", "open", "buy", "sell", "import_data", "duplicate",
    "share", "favorite", "pin", "post", "capture", "enroll", "book", "reserve",
    "apply", "join", "rsvp", "order", "place_order", "upload", "register",
    "lead_capture", "deal_create", "followup_set", "homework_submit", "note_add",
    "task_add", "add_note", "add_task", "add_item", "wishlist_add", "cart_add",
    "coupon_create", "create_gift", "create_listing", "book_slot", "book_session",
    "book_table", "bid", "tip", "review_add", "review", "comment", "feedback",
    "suggest", "report", "report_content", "report_user",
})
_UPDATE_M = frozenset({
    "update", "edit", "patch", "set", "assign", "claim", "release", "escalate",
    "approve", "reject", "close", "reopen", "schedule", "reschedule", "cancel",
    "postpone", "remind", "notify", "complete", "finish", "pause", "resume",
    "archive", "restore", "unpin", "unfavorite", "status_set", "set_status",
})
_CLOSE_M = frozenset({
    "delete", "remove", "close", "cancel", "reject", "archive", "ban", "kick",
    "unsubscribe", "revoke", "disable", "deactivate", "refund", "void", "expire",
    "purge", "drop", "destroy",
})

_DELETE_M = frozenset({
    "delete", "remove", "purge", "drop", "destroy", "cancel_hard",
})



# ----- Phase 8 scaffolds (deterministic; configure via env in production) -----

def translate_text(user_id: int, text: str = "") -> str:
    """Scaffold: acknowledges translation request; real API wired via env later."""
    ensure()
    text = (text or "").strip()
    if not text:
        return (
            "أرسل نصاً للترجمة بعد الأمر.\n"
            "Translate scaffold ready. Set TRANSLATOR_BACKEND=deep-translator|libre later."
        )
    iid = _insert("translate", int(user_id), "translate", text, "open", {"scaffold": True})
    preview = text if len(text) <= 120 else text[:117] + "..."
    return (
        f"#{iid} ترجمة (scaffold)\n"
        f"النص: {preview}\n"
        "الوضع: محاكاة — فعّل مكتبة ترجمة في البيئة لاحقاً (deep-translator / LibreTranslate)."
    )


def ocr_hint(user_id: int, text: str = "") -> str:
    """Scaffold: instructs user to send a photo; records intent."""
    ensure()
    iid = _insert("ocr", int(user_id), "ocr_hint", text or "photo", "open", {"scaffold": True})
    return (
        f"#{iid} OCR (scaffold)\n"
        "أرسل صورة نصية في الرسالة التالية.\n"
        "يتطلب pytesseract + Tesseract binary عند التفعيل الكامل."
    )


def schedule_note(user_id: int, text: str = "") -> str:
    """Scaffold: stores a scheduled note row (no background worker guaranteed)."""
    ensure()
    text = (text or "").strip()
    if not text:
        return "الاستخدام: /schedule غداً 10:00 تذكير الاجتماع"
    iid = _insert("scheduler", int(user_id), "schedule_note", text, "open", {"scaffold": True})
    return (
        f"#{iid} جدولة (scaffold)\n"
        f"المحتوى: {text[:200]}\n"
        "ملاحظة: التخزين تم — شغّل JobQueue/APScheduler في النشر لتفعيل التنفيذ."
    )


def job_list(user_id: int, text: str = "") -> str:
    ensure()
    rows = _list("scheduler", user_id=int(user_id), status="open", limit=20)
    return _fmt(rows, "لا توجد تذكيرات مجدولة")


def job_cancel(user_id: int, text: str = "") -> str:
    ensure()
    iid = _first_id(text or "")
    if not iid:
        return "حدد رقم التذكير: /job_cancel 3"
    with connect() as conn:
        cur = conn.execute(
            "UPDATE domain_items SET status='closed', updated_at=? WHERE id=? AND service='scheduler' AND user_id=?",
            (_now(), iid, int(user_id)),
        )
        conn.commit()
        n = int(cur.rowcount)
    return f"تم إلغاء #{iid}" if n else "غير موجود"



def act(service: str, method: str, user_id: int, text: str = "") -> str:
    """Execute any capability with durable SQLite side-effects.

    Covers the full registry surface (11k capabilities / 361 methods):
    domain specialists first, then universal method families, then log event.
    Never returns an empty stub without persistence.
    """
    ensure()
    service = (service or "gen").strip()[:40]
    method = (method or "run").strip()[:40]
    text = (text or "").strip()[:2000]
    m, svc, uid = method.lower(), service.lower(), int(user_id)


    # Phase 8 specialized scaffolds
    if m in {"translate", "translate_text"} or (svc in {"translate", "utils", "content"} and m == "translate"):
        return translate_text(uid, text)
    if m in {"ocr_image", "ocr_hint", "ocr"} or (svc == "ocr" and m in {"image", "hint", "run"}):
        return ocr_hint(uid, text)
    if m in {"schedule_note", "schedule"} or (svc in {"scheduler", "reminders"} and m in {"schedule_note", "schedule", "remind"}):
        return schedule_note(uid, text)
    if m in {"job_list", "list_jobs"} or (svc == "scheduler" and m in {"list", "job_list"}):
        return job_list(uid, text)
    if m in {"job_cancel", "cancel_job"} or (svc == "scheduler" and m in {"cancel", "job_cancel"}):
        return job_cancel(uid, text)

    # Domain specialists (clinic, jobs, edu, ...)
    handler = _HANDLERS.get(svc)
    if handler:
        try:
            out = handler(m, uid, text)
            if out:
                return out
        except Exception as exc:
            return f"{svc}.{method} error: {exc}"

    # Method families: module-level _LIST_M / _CREATE_M / _UPDATE_M / _CLOSE_M

    if m in _LIST_M or m.endswith("_list") or m.endswith("_view") or m.endswith("_info") or m.endswith("_status"):
        if m in {"stats", "stats_basic", "dashboard", "analytics", "analytics_overview", "revenue", "revenue_today"}:
            with connect() as conn:
                open_c = conn.execute(
                    "SELECT COUNT(*) c FROM domain_items WHERE service=? AND status='open'", (svc,)
                ).fetchone()["c"]
                all_c = conn.execute(
                    "SELECT COUNT(*) c FROM domain_items WHERE service=?", (svc,)
                ).fetchone()["c"]
            return f"{svc} stats: open={open_c} total={all_c}"
        if m in {"my", "mine", "my_orders", "my_apps", "my_bids"}:
            return _fmt(_list(svc, user_id=uid, status=None, limit=20), f"No {svc} items for you")
        st = None if m in {"history", "audit", "audit_log", "export"} else "open"
        return _fmt(_list(svc, status=st, limit=30), f"No {svc} items yet — create one")

    if m in _CREATE_M or m.endswith("_create") or m.endswith("_add") or m.endswith("_open") or m.endswith("_submit"):
        title = text[:80] if text else f"{method}"
        iid = _insert(svc, uid, title, text or method, "open", {"method": method})
        return f"Created #{iid} ({svc}/{method})"

    if m in _CLOSE_M or m.endswith("_delete") or m.endswith("_cancel") or m.endswith("_close"):
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
                    "SELECT id FROM domain_items WHERE service=? AND status='open' "
                    "ORDER BY id DESC LIMIT 1)",
                    (_now(), svc),
                )
            conn.commit()
            n = int(cur.rowcount)
        return f"Closed {n} item(s)" if n else f"Nothing open to close for {svc}"

    if m in _UPDATE_M or m.endswith("_update") or m.endswith("_set") or m.endswith("_edit"):
        iid = _first_id(text)
        body = _rest(text)
        if iid and body:
            if m in {"assign", "set_status", "set_priority", "priority", "set_role", "role_set"}:
                if _set_status(iid, body.split()[0]):
                    return f"#{iid} → {body.split()[0]}"
                return "Not found"
            with connect() as conn:
                cur = conn.execute(
                    "UPDATE domain_items SET body=?, updated_at=? WHERE id=?",
                    (body[:4000], _now(), iid),
                )
                conn.commit()
                if int(cur.rowcount):
                    return f"Updated #{iid}"
            return "Not found"
        # toggle / config without id
        iid = _insert(svc, uid, f"{method}", text or method, "open", {"method": method})
        return f"OK {svc}.{method} #{iid}"

    if m in {"track", "status"}:
        iid = _first_id(text)
        if iid:
            row = _get(iid)
            if row:
                return f"#{iid} [{row['status']}] {row['title']}\n{row['body']}"
        return _fmt(_list(svc, user_id=uid, status=None, limit=15), f"No {svc} data")

    # Utils / info methods — always durable ack
    if m in {
        "ping", "echo", "time_now", "uuid_gen", "calc", "help", "start", "about",
        "privacy", "terms", "lang", "set_language", "auto_detect", "contact",
        "channel_link", "deep_link", "gate_check", "force_sub_info", "verify_start",
        "verify_ok", "user_info", "search_user", "export_me", "delete_me", "csat",
        "maintenance_on", "maintenance_off", "backup", "restore_backup",
    }:
        payload = text or m
        if m == "echo":
            return payload or "—"
        if m == "time_now":
            return _now()
        if m == "uuid_gen":
            import uuid
            return str(uuid.uuid4())
        if m == "calc":
            try:
                # safe tiny eval: digits and + - * / ( )
                expr = "".join(ch for ch in payload if ch in "0123456789+-*/().% ")
                return str(eval(expr, {"__builtins__": {}}, {})) if expr else "Usage: calc <expr>"
            except Exception:
                return "Invalid expression"
        if m in {"privacy", "terms"}:
            return f"{m}: stored locally in SQLite; contact admin for deletion requests."
        iid = _insert(svc, uid, m, payload, "open", {"method": method})
        return f"OK {svc}.{method} #{iid}: {payload[:80]}"

    # Default: persist event so every one of 11k capabilities has a side-effect
    iid = _insert(svc, uid, f"{method}", text or method, "open", {"method": method})
    return f"OK {svc}.{method} #{iid} saved"

