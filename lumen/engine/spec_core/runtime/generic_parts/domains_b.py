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


