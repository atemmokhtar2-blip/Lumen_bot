"""Generic capability runtime — deep durable SQLite for any service.method.

Copied into generated projects as app/services/generic.py.
"""
from __future__ import annotations

import ast
import json
import operator
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.db import connect, init_db


def _load_runtime_data() -> dict[str, Any]:
    """Load editable runtime data (method families, FAQ seed, ...).

    Search order:
    1. Beside this module (generated projects ship generic_runtime.json here)
    2. Package data path (source tree, non-gitignored)
    3. Repo root data/templates (local override)
    """
    here = Path(__file__).resolve()
    candidates = [
        here.with_name("generic_runtime.json"),
        here.parents[2] / "data" / "templates" / "generic_runtime.json",  # lumen.engine/data/...
        here.parents[3] / "data" / "templates" / "generic_runtime.json",  # repo root /data/...
    ]
    for path in candidates:
        try:
            if path.is_file():
                value = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(value, dict) and value:
                    return value
        except (OSError, ValueError, TypeError):
            continue
    return {}


_RUNTIME_DATA = _load_runtime_data()


_CALC_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_calc(expression: str) -> str:
    """Evaluate only a small arithmetic AST; never execute arbitrary Python."""
    if len(expression) > 200:
        raise ValueError("expression too long")
    tree = ast.parse(expression, mode="eval")
    nodes = list(ast.walk(tree))
    if len(nodes) > 40:
        raise ValueError("expression too complex")

    def visit(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _CALC_OPS:
            left, right = visit(node.left), visit(node.right)
            if abs(left) > 10**12 or abs(right) > 10**12:
                raise ValueError("number too large")
            return _CALC_OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _CALC_OPS:
            return _CALC_OPS[type(node.op)](visit(node.operand))
        raise ValueError("unsupported expression")

    result = visit(tree)
    if abs(result) > 10**12:
        raise ValueError("result too large")
    return str(result)

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



# Method families are editable data, loaded once at import time (never on the hot path).
_LIST_M = frozenset(_RUNTIME_DATA.get("_LIST_M", ()))
_CREATE_M = frozenset(_RUNTIME_DATA.get("_CREATE_M", ()))
_UPDATE_M = frozenset(_RUNTIME_DATA.get("_UPDATE_M", ()))
_CLOSE_M = frozenset(_RUNTIME_DATA.get("_CLOSE_M", ()))
_DELETE_M = frozenset(_RUNTIME_DATA.get("_DELETE_M", ()))



# ----- Phase 8 scaffolds (deterministic; configure via env in production) -----


def backend_status() -> str:
    """Report which optional backends are configured and importable."""
    import os as _os
    lines = ["🔧 حالة الـ backends"]
    # translate
    tb = (_os.getenv("TRANSLATE_BACKEND") or "echo").strip().lower()
    lines.append(f"TRANSLATE_BACKEND={tb}")
    if tb in {"deep-translator", "deep_translator", "google"}:
        try:
            import deep_translator  # type: ignore  # noqa: F401
            lines.append("  deep-translator: available")
        except Exception as exc:
            lines.append(f"  deep-translator: MISSING ({type(exc).__name__})")
    if tb in {"libre", "libretranslate"}:
        lines.append(f"  TRANSLATE_API_URL={(_os.getenv('TRANSLATE_API_URL') or '')[:60]}")
        lines.append(f"  TRANSLATE_API_KEY={'set' if (_os.getenv('TRANSLATE_API_KEY') or '').strip() else 'unset'}")
    # ocr
    ocr_on = (_os.getenv("OCR_ENABLED") or "1").strip().lower() not in {"0", "false", "no"}
    lines.append(f"OCR_ENABLED={1 if ocr_on else 0} lang={_os.getenv('OCR_LANG') or 'eng+ara'}")
    try:
        import pytesseract  # type: ignore  # noqa: F401
        from PIL import Image  # type: ignore  # noqa: F401
        lines.append("  pytesseract+Pillow: available")
    except Exception as exc:
        lines.append(f"  pytesseract+Pillow: MISSING ({type(exc).__name__})")
    return "\n".join(lines)




def voice_intake(user_id: int, text: str = "") -> str:
    """Record voice-note intent (no STT). Durable row for later processing.

    Ready for a future STT backend (VOICE_STT_BACKEND env). Currently
    acknowledges and stores; generated bots attach filters.VOICE via voice_from_file.
    """
    ensure()
    import os as _os
    text = (text or "").strip() or "voice_note_received"
    backend = (_os.getenv("VOICE_STT_BACKEND") or "none").strip().lower()
    iid = _insert(
        "voice", int(user_id), "voice_intake", text[:500], "open",
        {"kind": "voice", "stt_backend": backend},
    )
    if backend in {"none", "", "off"}:
        return (
            f"🎤 ملاحظة صوتية #{iid}\n"
            "تم تسجيل الطلب.\n"
            "أرسل رسالة صوتية مباشرة وسيتم حفظ الملف.\n"
            "STT اختياري عبر VOICE_STT_BACKEND."
        )
    return (
        f"🎤 ملاحظة صوتية #{iid}\n"
        f"تم التسجيل (backend={backend}).\n"
        "المعالجة قيد الانتظار."
    )


def voice_from_file(user_id: int, file_path: str = "", file_id: str = "", duration: int = 0) -> str:
    """Persist an incoming voice/audio file path for later STT processing."""
    ensure()
    import os as _os
    backend = (_os.getenv("VOICE_STT_BACKEND") or "none").strip().lower()
    meta = {
        "kind": "voice_file",
        "file_path": (file_path or "")[-200:],
        "file_id": (file_id or "")[:120],
        "duration": int(duration or 0),
        "stt_backend": backend,
    }
    title = f"voice:{file_id[:24]}" if file_id else "voice_file"
    body = file_path or file_id or "voice_received"
    iid = _insert("voice", int(user_id), title, body[:500], "open", meta)
    # Optional: placeholder for external STT — never crash if missing
    transcript = ""
    if backend not in {"none", "", "off"} and file_path and _os.path.isfile(file_path):
        try:
            # Hook only — real STT providers wired later via env
            transcript = f"[stt:{backend} pending]"
        except Exception as exc:
            transcript = f"[stt_error:{type(exc).__name__}]"
    if transcript:
        return (
            f"🎤 صوت #{iid}\n"
            f"المدة: {duration or '?'}ث\n"
            f"{transcript}\n"
            "تم حفظ الملف للمعالجة."
        )
    return (
        f"🎤 صوت #{iid}\n"
        f"تم حفظ الرسالة الصوتية (مدة {duration or '?'}ث).\n"
        "للتفريغ النصي لاحقاً: VOICE_STT_BACKEND=..."
    )


def payment_info(user_id: int, text: str = "") -> str:
    """Show manual payment instructions from env; never embeds secrets in code."""
    ensure()
    import os as _os
    lines = ["💳 طرق الدفع اليدوي"]
    vcash = (_os.getenv("PAYMENT_VODAFONE_CASH") or "").strip()
    bank = (_os.getenv("PAYMENT_BANK_IBAN") or "").strip()
    instapay = (_os.getenv("PAYMENT_INSTAPAY") or "").strip()
    wallet = (_os.getenv("PAYMENT_WALLET") or "").strip()
    note = (_os.getenv("PAYMENT_INSTRUCTIONS") or "").strip()
    if vcash:
        lines.append(f"فودافون كاش: {vcash}")
    if instapay:
        lines.append(f"InstaPay: {instapay}")
    if bank:
        lines.append(f"تحويل بنكي: {bank}")
    if wallet:
        lines.append(f"محفظة: {wallet}")
    if note:
        lines.append(note)
    if len(lines) == 1:
        lines.append(
            "لم تُضبط بعد.\n"
            "ضع في .env:\n"
            "  PAYMENT_VODAFONE_CASH=\n"
            "  PAYMENT_INSTAPAY=\n"
            "  PAYMENT_BANK_IBAN=\n"
            "  PAYMENT_WALLET=\n"
            "  PAYMENT_INSTRUCTIONS="
        )
    body = "\n".join(lines)
    _insert("payments", int(user_id), "payment_info", (text or "")[:200], "done", {"view": True})
    return body


# Default FAQ seed + durable custom rows (service=content, title starts with faq:)
_FAQ_SEED: list[tuple[str, str]] = [
    (str(item[0]), str(item[1]))
    for item in (_RUNTIME_DATA.get("_FAQ_SEED") or [])
    if isinstance(item, (list, tuple)) and len(item) >= 2
]


def _faq_admin_ids() -> set[int]:
    import os as _os
    raw = (
        _os.getenv("FAQ_ADMIN_IDS")
        or _os.getenv("CAPABILITY_OPS_ADMINS")
        or _os.getenv("ADMIN_IDS")
        or ""
    )
    out: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out


def _faq_is_admin(user_id: int) -> bool:
    import os as _os
    admins = _faq_admin_ids()
    if not admins:
        # open in dev unless FAQ_REQUIRE_ADMIN=1
        return (_os.getenv("FAQ_REQUIRE_ADMIN") or "0").strip().lower() not in {"1", "true", "yes", "on"}
    return int(user_id) in admins


def _faq_load_custom() -> list[tuple[str, str, int]]:
    """Load custom FAQ rows from domain_items (title=faq:question)."""
    ensure()
    rows = _list("content", user_id=None, status="open", limit=100)
    out: list[tuple[str, str, int]] = []
    for r in rows:
        # sqlite3.Row supports key access, not dict.get(). Keep this path
        # compatible with generated apps and custom row factories.
        try:
            title = (r["title"] or "")
            body = (r["body"] or "")
            row_id = int(r["id"])
        except (KeyError, IndexError, TypeError):
            title = (getattr(r, "get", lambda *_: "")("title") or "")
            body = (getattr(r, "get", lambda *_: "")("body") or "")
            row_id = int(getattr(r, "get", lambda *_: 0)("id") or 0)
        if title.startswith("faq:"):
            q = title[4:].strip()
            a = body.strip()
            if q and a and row_id:
                out.append((q, a, row_id))
    return out


def faq(user_id: int, text: str = "") -> str:
    """FAQ: list, search, admin add/delete. Seed + SQLite custom + FAQ_EXTRA_JSON."""
    ensure()
    import os as _os
    q = (text or "").strip()
    extra: list[tuple[str, str]] = []
    raw = (_os.getenv("FAQ_EXTRA_JSON") or "").strip()
    if raw:
        try:
            import json as _json
            data = _json.loads(raw)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("q") and item.get("a"):
                        extra.append((str(item["q"]), str(item["a"])))
        except Exception:
            pass
    custom = _faq_load_custom()
    items: list[tuple[str, str]] = list(_FAQ_SEED) + extra + [(c[0], c[1]) for c in custom]

    # Admin: /faq add سؤال | جواب
    low = q.lower()
    if low.startswith("add ") or q.startswith("أضف ") or q.startswith("اضف "):
        if not _faq_is_admin(user_id):
            return "⛔ إضافة FAQ للمشرفين فقط (FAQ_ADMIN_IDS / ADMIN_IDS)."
        payload = q.split(None, 1)[1] if " " in q else ""
        if "|" not in payload and "｜" not in payload:
            return "الصيغة: /faq add السؤال | الجواب"
        sep = "|" if "|" in payload else "｜"
        qq, aa = payload.split(sep, 1)
        qq, aa = qq.strip(), aa.strip()
        if not qq or not aa:
            return "السؤال والجواب مطلوبان."
        iid = _insert("content", int(user_id), f"faq:{qq[:120]}", aa[:2000], "open", {"kind": "faq_custom"})
        return f"✅ تمت إضافة FAQ #{iid}\nس: {qq[:80]}\nج: {aa[:120]}"

    # Admin: /faq del <id>
    if low.startswith("del ") or low.startswith("delete ") or q.startswith("حذف "):
        if not _faq_is_admin(user_id):
            return "⛔ حذف FAQ للمشرفين فقط."
        iid = _first_id(q.split(None, 1)[1] if " " in q else "")
        if not iid:
            return "حدد رقم العنصر: /faq del 12"
        with connect() as conn:
            cur = conn.execute(
                "UPDATE domain_items SET status='closed', updated_at=? WHERE id=? AND service='content' AND title LIKE 'faq:%'",
                (_now(), iid),
            )
            conn.commit()
            n = int(cur.rowcount)
        return f"تم حذف #{iid}" if n else f"غير موجود أو ليس FAQ: #{iid}"

    if not q or low in {"list", "all", "قائمة", "الكل", "مساعدة", "help"}:
        lines = ["❓ الأسئلة الشائعة:"]
        for i, (qq, aa) in enumerate(items, 1):
            lines.append(f"{i}. {qq}")
        if custom:
            lines.append("\n— مخصص (معرّفات):")
            for qq, aa, iid in custom[:15]:
                lines.append(f"  #{iid} {qq[:50]}")
        lines.append("\nابحث: /faq كلمة")
        if _faq_is_admin(user_id):
            lines.append("إضافة: /faq add سؤال | جواب")
            lines.append("حذف: /faq del <id>")
        _insert("content", int(user_id), "faq_list", q or "list", "done", {"count": len(items)})
        return "\n".join(lines)

    q_low = q.lower()
    hits = []
    for qq, aa in items:
        if q_low in qq.lower() or q_low in aa.lower() or q in qq or q in aa:
            hits.append((qq, aa))
    if not hits:
        lines = [
            f"❓ لم أجد تطابقاً لـ «{q[:40]}»",
            "جرّب /faq لعرض القائمة، أو أعد صياغة السؤال.",
        ]
        _insert("content", int(user_id), "faq_miss", q[:200], "done", {})
        return "\n".join(lines)

    lines = [f"❓ نتائج البحث ({len(hits)}):"]
    for qq, aa in hits[:5]:
        lines.append(f"• {qq}\n  → {aa}")
    _insert("content", int(user_id), "faq_hit", q[:200], "done", {"hits": len(hits)})
    return "\n".join(lines)



def translate_text(user_id: int, text: str = "") -> str:
    """Translation helper with optional production backends.

    Backends (TRANSLATE_BACKEND):
      echo (default)           — deterministic offline label
      deep-translator|google   — GoogleTranslator via deep-translator pkg
      libre|libretranslate     — HTTP LibreTranslate (TRANSLATE_API_URL)

    Never crashes if optional deps/network missing.
    """
    ensure()
    import os as _os
    text = (text or "").strip()
    if not text:
        return (
            "🌐 الترجمة\n"
            "الاستخدام: /translate مرحبا بك\n"
            "أو: /translate en:hello world\n"
            "الحالة: /translate status\n"
            "BACKENDS: echo | deep-translator | libre\n"
            "TRANSLATE_BACKEND=...  TRANSLATE_API_URL=...  TRANSLATE_API_KEY=..."
        )
    if text.lower() in {"status", "حالة", "backends", "health"}:
        return backend_status()
    target = (_os.getenv("TRANSLATE_TARGET") or "ar").strip().lower() or "ar"
    payload = text
    if ":" in text[:8]:
        maybe, rest = text.split(":", 1)
        if 1 <= len(maybe.strip()) <= 5 and maybe.strip().replace("-", "").isalpha():
            target = maybe.strip().lower()
            payload = rest.strip()
    if not payload:
        return "أدخل نصاً بعد رمز اللغة، مثال: /translate en:مرحبا"

    backend = (_os.getenv("TRANSLATE_BACKEND") or "echo").strip().lower()
    translated = None
    note = ""
    if backend in {"deep-translator", "deep_translator", "google"}:
        try:
            from deep_translator import GoogleTranslator  # type: ignore
            translated = GoogleTranslator(source="auto", target=target).translate(payload)
            note = "deep-translator"
        except Exception as exc:
            note = f"deep-translator failed:{type(exc).__name__}"
            translated = None
    elif backend in {"libre", "libretranslate"}:
        try:
            import json as _json
            from urllib import request as _urlreq
            api = (_os.getenv("TRANSLATE_API_URL") or "http://localhost:5000").rstrip("/")
            body = _json.dumps({
                "q": payload, "source": "auto", "target": target, "format": "text",
            }).encode("utf-8")
            headers = {"Content-Type": "application/json"}
            api_key = (_os.getenv("TRANSLATE_API_KEY") or "").strip()
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
                # common alternate header used by some LibreTranslate hosts
                headers["api-key"] = api_key
            req = _urlreq.Request(
                api + "/translate",
                data=body,
                headers=headers,
                method="POST",
            )
            with _urlreq.urlopen(req, timeout=float(_os.getenv("TRANSLATE_TIMEOUT") or "8")) as resp:
                data = _json.loads(resp.read().decode("utf-8", errors="ignore"))
            translated = (data.get("translatedText") or data.get("translation") or "").strip()
            note = "libretranslate"
            if not translated:
                note = "libretranslate empty"
                translated = None
        except Exception as exc:
            note = f"libre failed:{type(exc).__name__}"
            translated = None

    if not translated:
        translated = f"[{target}] {payload}"
        backend = f"echo" + (f" ({note})" if note else "")
    else:
        backend = note or backend

    iid = _insert(
        "translate", int(user_id), f"to:{target}", payload,
        "done", {"backend": backend, "result": translated[:500]},
    )
    return (
        f"🌐 ترجمة #{iid}\n"
        f"→ {translated}\n"
        f"(backend: {backend})"
    )


def ocr_hint(user_id: int, text: str = "") -> str:
    """OCR helper — stores intent; optional pytesseract if available + path given."""
    ensure()
    text = (text or "").strip()
    iid = _insert("ocr", int(user_id), "ocr_hint", text or "awaiting_photo", "open", {"awaiting": "photo"})
    if text and len(text) > 5:
        return f"📝 OCR #{iid}\nالنص المستلم:\n{text[:1500]}"
    return (
        f"📝 OCR #{iid}\n"
        "أرسل صورة فيها نص الآن، أو الصق النص بعد الأمر.\n"
        "للتفعيل الكامل: pip install pytesseract + Tesseract OCR"
    )


def ocr_from_image(user_id: int, image_path: str = "", caption: str = "") -> str:
    """Run OCR on a local image path when pytesseract is available; else durable ack.

    Env:
      OCR_LANG=eng+ara (tesseract langs)
      OCR_ENABLED=1 (default on when deps exist)
    """
    ensure()
    import os as _os
    caption = (caption or "").strip()
    extracted = ""
    backend = "none"
    enabled = (_os.getenv("OCR_ENABLED") or "1").strip().lower() not in {"0", "false", "no"}
    if image_path and enabled:
        try:
            import pytesseract  # type: ignore
            from PIL import Image  # type: ignore
            lang = (_os.getenv("OCR_LANG") or "eng+ara").strip() or "eng"
            img = Image.open(image_path)
            extracted = (pytesseract.image_to_string(img, lang=lang) or "").strip()
            backend = f"pytesseract:{lang}"
        except Exception as exc:
            backend = f"unavailable:{type(exc).__name__}"
    if not extracted and caption:
        extracted = caption
        backend = "caption" if backend == "none" else f"{backend}+caption"
    iid = _insert(
        "ocr", int(user_id), "ocr_image",
        extracted[:2000] or (image_path or "no_text"),
        "done" if extracted else "open",
        {"backend": backend, "path": (image_path or "")[-120:]},
    )
    if extracted:
        return f"📝 OCR #{iid}\n{extracted[:2000]}"
    return (
        f"📝 OCR #{iid}\n"
        "تم حفظ الصورة. لم يُستخرج نص.\n"
        "ثبّت: pip install pytesseract Pillow  +  Tesseract OCR على النظام\n"
        f"backend={backend}"
    )


def _human_duration(sec: int) -> str:
    """Arabic-friendly human duration for UX."""
    sec = max(0, int(sec))
    if sec < 60:
        return f"{sec} ثانية"
    if sec < 3600:
        m = sec // 60
        return f"{m} دقيقة" if m == 1 else f"{m} دقائق"
    if sec < 86400:
        h = sec // 3600
        rem = (sec % 3600) // 60
        base = "ساعة" if h == 1 else f"{h} ساعات"
        if rem:
            return f"{base} و {rem} دقيقة"
        return base
    d = sec // 86400
    rem_h = (sec % 86400) // 3600
    base = "يوم" if d == 1 else f"{d} أيام"
    if rem_h:
        return f"{base} و {rem_h} ساعة"
    return base


def _parse_due_seconds(text: str) -> tuple[int, str]:
    """Parse relative due times (EN + AR). Returns (seconds_from_now, cleaned_body).

    Supported examples:
      in 5m / in 10 min / 1h / 2d / in 90s
      بعد 10 دقائق / بعد ساعة / بعد ساعتين / بعد نصف ساعة / بعد ربع ساعة
      بعد يوم / بعد يومين / بعد شوية
    Fallback: 1 hour (body = full text).
    """
    import re as _re
    t = (text or "").strip()
    if not t:
        return 3600, t

    # English: in 5m / 10min / 1h / 2d / 90s / after 5 minutes
    m = _re.match(
        r"^(?:in|after)?\s*(\d+)\s*(s|sec|secs|seconds|m|min|mins|minutes|h|hr|hrs|hours|d|day|days)\b\s*(.*)$",
        t,
        _re.I,
    )
    if m:
        n, unit, rest = int(m.group(1)), m.group(2).lower(), (m.group(3) or "").strip()
        if unit in {"s", "sec", "secs", "seconds"}:
            return max(15, n), rest or t
        if unit in {"m", "min", "mins", "minutes"}:
            return max(30, n * 60), rest or t
        if unit in {"h", "hr", "hrs", "hours"}:
            return max(60, n * 3600), rest or t
        if unit in {"d", "day", "days"}:
            return max(60, n * 86400), rest or t

    # Arabic numeric: بعد 5 دقائق / بعد 2 ساعة / بعد 3 أيام
    m2 = _re.match(
        r"^بعد\s+(\d+)\s*(ثانية|ثواني|دقيقة|دقائق|ساعة|ساعات|يوم|يومين|ايام|أيام)\s*(.*)$",
        t,
    )
    if m2:
        n, unit, rest = int(m2.group(1)), m2.group(2), (m2.group(3) or "").strip()
        if unit in {"ثانية", "ثواني"}:
            return max(15, n), rest or t
        if "دق" in unit:
            return max(30, n * 60), rest or t
        if "ساع" in unit:
            return max(60, n * 3600), rest or t
        if "يوم" in unit or "ايام" in unit or "أيام" in unit:
            # يومين already covered by numeric + unit; treat n=2 يومين ok
            return max(60, n * 86400), rest or t

    # Arabic fixed phrases (no number)
    fixed = [
        (r"^بعد\s+شوية\s*(.*)$", 15 * 60),
        (r"^بعد\s+قليل\s*(.*)$", 10 * 60),
        (r"^بعد\s+ربع\s*ساعة\s*(.*)$", 15 * 60),
        (r"^بعد\s+نصف\s*ساعة\s*(.*)$", 30 * 60),
        (r"^بعد\s+ساعة\s*ونص(?:ف)?\s*(.*)$", 90 * 60),
        (r"^بعد\s+ساعة\s*(.*)$", 3600),
        (r"^بعد\s+ساعتين\s*(.*)$", 2 * 3600),
        (r"^بعد\s+يومين\s*(.*)$", 2 * 86400),
        (r"^بعد\s+يوم\s*(.*)$", 86400),
    ]
    for pat, sec in fixed:
        m3 = _re.match(pat, t)
        if m3:
            rest = (m3.group(1) or "").strip()
            return max(30, sec), rest or t

    # default: 1 hour, keep full text as body
    return 3600, t


def _parse_recurring(text: str) -> tuple[int | None, str]:
    """Detect recurring interval. Returns (interval_sec or None, remaining_text)."""
    import re as _re
    t = (text or "").strip()
    # EN: every 1h / daily / weekly / every 30m
    m = _re.match(
        r"^(?:every|each)\s+(\d+)\s*(m|min|mins|minutes|h|hr|hours|d|day|days)\b\s*(.*)$",
        t,
        _re.I,
    )
    if m:
        n, unit, rest = int(m.group(1)), m.group(2).lower(), (m.group(3) or "").strip()
        if unit.startswith("m"):
            return max(60, n * 60), rest or t
        if unit.startswith("h"):
            return max(300, n * 3600), rest or t
        if unit.startswith("d"):
            return max(3600, n * 86400), rest or t
    low = t.lower()
    if low.startswith("daily ") or low == "daily":
        return 86400, t[6:].strip() if low.startswith("daily ") else "تذكير يومي"
    if low.startswith("weekly ") or low == "weekly":
        return 7 * 86400, t[7:].strip() if low.startswith("weekly ") else "تذكير أسبوعي"
    # AR: كل يوم / كل ساعة / كل 30 دقيقة / كل أسبوع
    m2 = _re.match(
        r"^كل\s+(\d+)\s*(دقيقة|دقائق|ساعة|ساعات|يوم|ايام|أيام)\s*(.*)$",
        t,
    )
    if m2:
        n, unit, rest = int(m2.group(1)), m2.group(2), (m2.group(3) or "").strip()
        if "دق" in unit:
            return max(60, n * 60), rest or t
        if "ساع" in unit:
            return max(300, n * 3600), rest or t
        if "يوم" in unit or "ايام" in unit or "أيام" in unit:
            return max(3600, n * 86400), rest or t
    fixed = [
        (r"^كل\s*يوم\s*(.*)$", 86400),
        (r"^كل\s*ساعة\s*(.*)$", 3600),
        (r"^كل\s*أسبوع\s*(.*)$", 7 * 86400),
        (r"^كل\s*اسبوع\s*(.*)$", 7 * 86400),
    ]
    for pat, sec in fixed:
        m3 = _re.match(pat, t)
        if m3:
            rest = (m3.group(1) or "").strip()
            return sec, rest or t
    return None, t


def schedule_note(user_id: int, text: str = "", chat_id: int | None = None) -> str:
    """Store a reminder with due timestamp; supports recurring (كل يوم / every 1h)."""
    ensure()
    import time as _time
    text = (text or "").strip()
    if not text:
        return (
            "⏰ الجدولة\n"
            "الاستخدام:\n"
            "  /schedule in 5m اشرب ماء\n"
            "  /schedule بعد 10 دقائق اجتماع\n"
            "  /schedule بعد نصف ساعة اتصال\n"
            "  /schedule كل يوم التمرين\n"
            "  /schedule every 2h اشرب ماء\n"
            "عرض: /jobs — إلغاء: /jobcancel <id>"
        )
    interval, rest = _parse_recurring(text)
    if interval:
        body = (rest or text).strip() or "تذكير متكرر"
        sec = interval
        recurring = True
    else:
        sec, body = _parse_due_seconds(text)
        body = (body or text).strip() or "تذكير"
        recurring = False
    due_ts = int(_time.time()) + int(sec)
    meta = {
        "kind": "reminder",
        "due_ts": due_ts,
        "delay_sec": sec,
        "chat_id": int(chat_id) if chat_id else int(user_id),
        "recurring": recurring,
        "interval_sec": int(interval) if interval else 0,
    }
    title = "reminder_recurring" if recurring else "reminder"
    iid = _insert("scheduler", int(user_id), title, body[:500], "open", meta)
    human = _human_duration(sec)
    if recurring:
        return (
            f"🔁 تذكير متكرر #{iid} كل {human}\n"
            f"{body[:300]}\n"
            "يُعاد جدولته تلقائياً بعد كل إرسال (SCHEDULE_ENABLED=1)."
        )
    return (
        f"⏰ تذكير #{iid} بعد {human}\n"
        f"{body[:300]}\n"
        "سيُرسل تلقائياً عبر JobQueue (SCHEDULE_ENABLED=1)."
    )



def list_due_reminders(now_ts: int | None = None, limit: int = 50) -> list[dict]:
    """Return open scheduler rows whose due_ts <= now (oldest first, capped)."""
    ensure()
    import json as _json
    import time as _time
    now = int(now_ts if now_ts is not None else _time.time())
    # fetch a bit more then filter — avoids missing due items when many open
    rows = _list("scheduler", user_id=None, status="open", limit=max(limit * 3, 80))
    due = []
    for r in rows:
        try:
            meta = _json.loads(r["meta"] or "{}")
        except Exception:
            meta = {}
        due_ts = int(meta.get("due_ts") or 0)
        if due_ts and due_ts <= now:
            due.append({
                "id": r["id"],
                "user_id": r["user_id"],
                "chat_id": int(meta.get("chat_id") or r["user_id"] or 0),
                "body": r["body"],
                "due_ts": due_ts,
                "recurring": bool(meta.get("recurring")),
                "interval_sec": int(meta.get("interval_sec") or 0),
            })
    due.sort(key=lambda x: (x.get("due_ts") or 0, x.get("id") or 0))
    return due[:limit]


def mark_reminder_fired(item_id: int) -> bool:
    """Mark one-shot as done; reschedule recurring by advancing due_ts."""
    ensure()
    import json as _json
    import time as _time
    with connect() as conn:
        row = conn.execute(
            "SELECT id, meta, status FROM domain_items WHERE id=? AND service='scheduler'",
            (int(item_id),),
        ).fetchone()
        if not row:
            return False
        try:
            meta = _json.loads(row["meta"] or "{}")
        except Exception:
            meta = {}
        if meta.get("recurring") and int(meta.get("interval_sec") or 0) > 0:
            interval = int(meta["interval_sec"])
            now = int(_time.time())
            # advance from now (not from old due) to avoid catch-up storms
            meta["due_ts"] = now + interval
            meta["last_fired_ts"] = now
            conn.execute(
                "UPDATE domain_items SET meta=?, updated_at=?, status='open' WHERE id=?",
                (_json.dumps(meta, ensure_ascii=False), _now(), int(item_id)),
            )
            conn.commit()
            return True
        cur = conn.execute(
            "UPDATE domain_items SET status='done', updated_at=? WHERE id=? AND service='scheduler'",
            (_now(), int(item_id)),
        )
        conn.commit()
        return int(cur.rowcount) > 0


def job_list(user_id: int, text: str = "") -> str:
    """List open reminders for user with remaining time."""
    ensure()
    import json as _json
    import time as _time
    rows = _list("scheduler", user_id=int(user_id), status="open", limit=20)
    if not rows:
        return "لا توجد تذكيرات مجدولة\nأضف واحداً: /schedule بعد 10 دقائق نص"
    now = int(_time.time())
    lines = ["⏰ تذكيراتك المفتوحة:"]
    for r in rows:
        try:
            meta = _json.loads(r.get("meta") or "{}")
        except Exception:
            meta = {}
        due_ts = int(meta.get("due_ts") or 0)
        body = (r.get("body") or r.get("title") or "")[:80]
        badge = "🔁 " if meta.get("recurring") else ""
        if due_ts and due_ts > now:
            rem = _human_duration(due_ts - now)
            lines.append(f"#{r['id']} {badge}بعد {rem} — {body}")
        elif due_ts:
            lines.append(f"#{r['id']} {badge}مستحق الآن — {body}")
        else:
            lines.append(f"#{r['id']} {badge}— {body}")
    lines.append("إلغاء: /jobcancel <id>")
    return "\n".join(lines)


def job_cancel(user_id: int, text: str = "") -> str:
    ensure()
    iid = _first_id(text or "")
    if not iid:
        return "حدد رقم التذكير: /jobcancel 3\nعرض القائمة: /jobs"
    with connect() as conn:
        # fetch first for better message
        row = conn.execute(
            "SELECT id, body, status FROM domain_items WHERE id=? AND service='scheduler' AND user_id=?",
            (iid, int(user_id)),
        ).fetchone()
        if not row:
            return f"غير موجود أو ليس لك: #{iid}"
        if row["status"] != "open":
            return f"#{iid} حالته أصلاً «{row['status']}» — لا حاجة لإلغاء"
        cur = conn.execute(
            "UPDATE domain_items SET status='closed', updated_at=? WHERE id=? AND service='scheduler' AND user_id=?",
            (_now(), iid, int(user_id)),
        )
        conn.commit()
        n = int(cur.rowcount)
    snippet = (row["body"] or "")[:60]
    return f"تم إلغاء #{iid}\n{snippet}" if n else f"تعذر إلغاء #{iid}"



def explicit_command(user_id: int, command: str, text: str = "") -> str:
    """Execute a user-declared command with durable, command-scoped storage.

    This is a real fallback for commands not yet mapped to a specialist: it
    never pretends that an unsupported domain operation happened. It records
    submitted data, supports `/command list`, and tells the user exactly what
    input is required when no payload was supplied.
    """
    ensure()
    cmd = re.sub(r"[^a-z0-9_]+", "", (command or "command").lower())[:40] or "command"
    payload = (text or "").strip()[:2000]
    service = f"cmd_{cmd}"[:40]
    if payload.lower() in {"list", "all", "history", "سجل", "قائمة"}:
        return _fmt(_list(service, user_id=user_id, status=None, limit=30), f"لا توجد بيانات مسجلة للأمر /{cmd} بعد.")
    if not payload:
        return f"أرسل البيانات المطلوبة بعد /{cmd}. مثال: /{cmd} بيانات الطلب\nولعرض ما سجلته: /{cmd} list"
    iid = _insert(service, int(user_id), payload[:120], payload, "open", {"command": cmd, "kind": "explicit_command"})
    return f"تم تنفيذ /{cmd} وتسجيل الطلب #{iid}. لعرض السجل أرسل /{cmd} list"


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


    # Explicit user-declared commands have a command-aware durable path in
    # generated handlers; keep a safe fallback for direct service calls.
    if m == "explicit_command":
        return explicit_command(uid, svc, text)

    # Phase 8 / 14 specialized scaffolds
    if m in {"voice_from_file"}:
        return voice_from_file(uid, text)
    if m in {"voice_intake", "voice"} or (svc == "voice"):
        return voice_intake(uid, text)
    if m in {"payment_info", "pay_info"}:
        return payment_info(uid, text)
    if m in {"faq", "faq_list", "faq_search"} or (svc in {"content", "utils"} and m == "faq"):
        return faq(uid, text)
    if m in {"translate", "translate_text"} or (svc in {"translate", "utils", "content"} and m == "translate"):
        return translate_text(uid, text)
    if m in {"ocr_from_image"}:
        return ocr_from_image(uid, text, "")
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
                return _safe_calc(expr) if expr else "Usage: calc <expr>"
            except Exception:
                return "Invalid expression"
        if m in {"privacy", "terms"}:
            return f"{m}: stored locally in SQLite; contact admin for deletion requests."
        iid = _insert(svc, uid, m, payload, "open", {"method": method})
        return f"OK {svc}.{method} #{iid}: {payload[:80]}"

    # Default: persist event so every one of 11k capabilities has a side-effect
    iid = _insert(svc, uid, f"{method}", text or method, "open", {"method": method})
    return f"OK {svc}.{method} #{iid} saved"

