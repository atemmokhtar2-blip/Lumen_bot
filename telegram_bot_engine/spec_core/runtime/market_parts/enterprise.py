def enterprise_ensure() -> None:
    """Extra tables for complex production-like flows."""
    ensure()
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS coupons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                percent_off REAL NOT NULL DEFAULT 0,
                amount_off_cents INTEGER NOT NULL DEFAULT 0,
                max_uses INTEGER NOT NULL DEFAULT 100,
                used INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                expires_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS coupon_redemptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                coupon_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                order_id INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS order_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                actor_id INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS affiliates (
                user_id INTEGER PRIMARY KEY,
                parent_id INTEGER NOT NULL DEFAULT 0,
                code TEXT NOT NULL UNIQUE,
                rate_percent REAL NOT NULL DEFAULT 10,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS affiliate_earnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                affiliate_id INTEGER NOT NULL,
                from_user INTEGER NOT NULL,
                order_id INTEGER NOT NULL,
                amount_cents INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS vendors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS vendor_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vendor_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                commission_percent REAL NOT NULL DEFAULT 15
            );
            CREATE TABLE IF NOT EXISTS saas_tenants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                plan TEXT NOT NULL DEFAULT 'free',
                seats INTEGER NOT NULL DEFAULT 3,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS saas_members (
                tenant_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL DEFAULT 'member',
                PRIMARY KEY (tenant_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_id INTEGER NOT NULL DEFAULT 0,
                action TEXT NOT NULL,
                entity TEXT NOT NULL DEFAULT '',
                entity_id INTEGER NOT NULL DEFAULT 0,
                detail TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                order_id INTEGER NOT NULL DEFAULT 0,
                amount_cents INTEGER NOT NULL,
                currency TEXT NOT NULL DEFAULT 'USD',
                status TEXT NOT NULL DEFAULT 'open',
                due_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS stock_moves (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                delta INTEGER NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                actor_id INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                rule TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS sla_tickets (
                ticket_id INTEGER PRIMARY KEY,
                priority TEXT NOT NULL DEFAULT 'normal',
                assignee INTEGER NOT NULL DEFAULT 0,
                due_at TEXT,
                breached INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        conn.commit()


def _audit(actor_id: int, action: str, entity: str = "", entity_id: int = 0, detail: str = "") -> None:
    enterprise_ensure()
    with connect() as conn:
        conn.execute(
            "INSERT INTO audit_log (actor_id, action, entity, entity_id, detail) VALUES (?,?,?,?,?)",
            (int(actor_id), action[:80], entity[:40], int(entity_id), detail[:500]),
        )
        conn.commit()


def order_set_status(order_id: int, status: str, actor_id: int = 0, note: str = "") -> str:
    """Order state machine: pending→paid→processing→shipped→delivered|refunded|cancelled."""
    enterprise_ensure()
    if not actor_id or not role_require(int(actor_id), "staff"):
        return "❌ غير مصرح — للموظفين/الأدمن فقط"
    allowed = {
        "pending": {"paid", "cancelled"},
        "open": {"paid", "cancelled"},
        "paid": {"processing", "refunded", "cancelled"},
        "processing": {"shipped", "cancelled"},
        "shipped": {"delivered", "refunded"},
        "delivered": {"refunded"},
        "cancelled": set(),
        "refunded": set(),
    }
    status = (status or "").strip().lower()
    with connect() as conn:
        row = conn.execute("SELECT id, status, user_id FROM orders WHERE id=?", (int(order_id),)).fetchone()
        if not row:
            return f"Order #{order_id} not found"
        cur = (row["status"] or "pending").lower()
        nxt = allowed.get(cur, set())
        if status not in nxt and status != cur:
            return f"Invalid transition {cur} → {status}. Allowed: {', '.join(sorted(nxt)) or 'none'}"
        conn.execute("UPDATE orders SET status=? WHERE id=?", (status, int(order_id)))
        conn.execute(
            "INSERT INTO order_events (order_id, status, note, actor_id) VALUES (?,?,?,?)",
            (int(order_id), status, note[:200], int(actor_id)),
        )
        # Restore reserved stock on cancel/refund (stock was reserved at place_order)
        if status in {"cancelled", "refunded"} and cur not in {"cancelled", "refunded"}:
            try:
                o = conn.execute(
                    "SELECT product_id, stock_reserved FROM orders WHERE id=?",
                    (int(order_id),),
                ).fetchone()
                if o and int(o["product_id"] or 0) and int(o["stock_reserved"] or 1):
                    conn.execute(
                        "UPDATE products SET stock = stock + 1 WHERE id=?",
                        (int(o["product_id"]),),
                    )
                    conn.execute(
                        "UPDATE orders SET stock_reserved=0 WHERE id=?",
                        (int(order_id),),
                    )
                    conn.execute(
                        "INSERT INTO stock_moves (product_id, delta, reason, actor_id) VALUES (?,?,?,?)",
                        (int(o["product_id"]), 1, f"restore_{status}_order_{order_id}", int(actor_id)),
                    )
            except Exception:
                pass
        conn.commit()
    _audit(actor_id, "order_status", "order", order_id, f"{cur}->{status}")
    return f"Order #{order_id}: {cur} → {status}"


def order_timeline(order_id: int) -> str:
    enterprise_ensure()
    with connect() as conn:
        o = conn.execute("SELECT id, user_id, status, amount_cents FROM orders WHERE id=?", (int(order_id),)).fetchone()
        if not o:
            return "Order not found"
        ev = conn.execute(
            "SELECT status, note, actor_id, created_at FROM order_events WHERE order_id=? ORDER BY id",
            (int(order_id),),
        ).fetchall()
    lines = [f"Order #{o['id']} user={o['user_id']} status={o['status']} total={o['amount_cents']}"]
    for e in ev:
        lines.append(f"  · {e['created_at']} {e['status']} by={e['actor_id']} {e['note']}")
    return "\n".join(lines) if len(lines) > 1 else lines[0] + "\n  (no events yet)"


def stock_adjust(product_id: int, delta: int, actor_id: int = 0, reason: str = "") -> str:
    enterprise_ensure()
    if not actor_id or not role_require(int(actor_id), "staff"):
        return "❌ غير مصرح — للموظفين/الأدمن فقط"
    with connect() as conn:
        row = conn.execute("SELECT id, title, stock FROM products WHERE id=?", (int(product_id),)).fetchone()
        if not row:
            return "Product not found"
        new_stock = int(row["stock"] or 0) + int(delta)
        if new_stock < 0:
            return f"Stock would go negative ({new_stock})"
        conn.execute("UPDATE products SET stock=? WHERE id=?", (new_stock, int(product_id)))
        conn.execute(
            "INSERT INTO stock_moves (product_id, delta, reason, actor_id) VALUES (?,?,?,?)",
            (int(product_id), int(delta), reason[:120], int(actor_id)),
        )
        conn.commit()
    _audit(actor_id, "stock_adjust", "product", product_id, f"delta={delta}")
    return f"{row['title']}: stock {row['stock']} → {new_stock}"


def stock_low(threshold: int = 5) -> str:
    enterprise_ensure()
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, title, stock FROM products WHERE active=1 AND stock<=? ORDER BY stock ASC LIMIT 30",
            (int(threshold),),
        ).fetchall()
    if not rows:
        return f"No products at or below stock {threshold}"
    return "Low stock:\n" + "\n".join(f"#{r['id']} {r['title']} stock={r['stock']}" for r in rows)


def affiliate_register(user_id: int, parent_code: str = "") -> str:
    enterprise_ensure()
    code = f"AFF{user_id}"
    parent_id = 0
    with connect() as conn:
        if parent_code:
            p = conn.execute("SELECT user_id FROM affiliates WHERE code=?", (parent_code.strip().upper(),)).fetchone()
            if p:
                parent_id = int(p["user_id"])
        existing = conn.execute("SELECT code FROM affiliates WHERE user_id=?", (int(user_id),)).fetchone()
        if existing:
            return f"Already registered: {existing['code']} (parent={parent_id})"
        conn.execute(
            "INSERT INTO affiliates (user_id, parent_id, code) VALUES (?,?,?)",
            (int(user_id), parent_id, code),
        )
        conn.commit()
    _audit(user_id, "affiliate_register", "affiliate", user_id, code)
    return f"Affiliate code {code}" + (f" under parent {parent_id}" if parent_id else "")


def affiliate_credit_for_order(order_id: int) -> str:
    """2-level affiliate: direct 10%, parent of affiliate 2%."""
    enterprise_ensure()
    try:
        with connect() as conn:
            o = conn.execute(
                "SELECT id, user_id, amount_cents, status FROM orders WHERE id=?",
                (int(order_id),),
            ).fetchone()
            if not o or (o["status"] or "") not in {
                "paid",
                "processing",
                "shipped",
                "delivered",
            }:
                return "Order not eligible"
            # Idempotent: skip if already credited for this order
            try:
                prior = conn.execute(
                    "SELECT id FROM affiliate_earnings WHERE order_id=? LIMIT 1",
                    (int(order_id),),
                ).fetchone()
                if prior:
                    return "Already credited"
            except Exception:
                return "Affiliate tables not ready"
            try:
                ref = conn.execute(
                    "SELECT referrer_id FROM referrals WHERE referred_id=? LIMIT 1",
                    (int(o["user_id"]),),
                ).fetchone()
            except Exception:
                return "Referrals table not ready"
            if not ref:
                return "No referrer"
            aff_id = int(ref["referrer_id"])
            total = int(o["amount_cents"] or 0)
            direct = int(total * 0.10)
            conn.execute(
                "INSERT INTO affiliate_earnings (affiliate_id, from_user, order_id, amount_cents, status) "
                "VALUES (?,?,?,?, 'pending')",
                (aff_id, int(o["user_id"]), int(order_id), direct),
            )
            parent = conn.execute(
                "SELECT parent_id FROM affiliates WHERE user_id=?", (aff_id,)
            ).fetchone()
            lvl2 = 0
            if parent and int(parent["parent_id"] or 0):
                lvl2 = int(total * 0.02)
                conn.execute(
                    "INSERT INTO affiliate_earnings (affiliate_id, from_user, order_id, amount_cents, status) "
                    "VALUES (?,?,?,?, 'pending')",
                    (int(parent["parent_id"]), int(o["user_id"]), int(order_id), lvl2),
                )
            conn.commit()
        return f"Affiliate credited: L1={direct} cents" + (f" L2={lvl2} cents" if lvl2 else "")
    except Exception:
        return "Affiliate credit failed"


def affiliate_stats(user_id: int) -> str:
    enterprise_ensure()
    with connect() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) c, COALESCE(SUM(amount_cents),0) s FROM affiliate_earnings WHERE affiliate_id=? GROUP BY status",
            (int(user_id),),
        ).fetchall()
        code = conn.execute("SELECT code, parent_id FROM affiliates WHERE user_id=?", (int(user_id),)).fetchone()
    if not code:
        return "Not an affiliate — register first"
    lines = [f"Code {code['code']} parent={code['parent_id']}"]
    for r in rows:
        lines.append(f"  {r['status']}: n={r['c']} sum={r['s']} cents")
    return "\n".join(lines) if len(lines) > 1 else lines[0] + "\n  No earnings yet"


def vendor_register(owner_id: int, name: str) -> str:
    enterprise_ensure()
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO vendors (owner_id, name) VALUES (?,?)",
            (int(owner_id), (name or "Vendor")[:80]),
        )
        conn.commit()
        vid = int(cur.lastrowid)
    _audit(owner_id, "vendor_register", "vendor", vid, name)
    return f"Vendor #{vid} ({name}) active"


def vendor_list() -> str:
    enterprise_ensure()
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, owner_id, name, status FROM vendors ORDER BY id DESC LIMIT 40"
        ).fetchall()
    if not rows:
        return "No vendors"
    return "\n".join(f"#{r['id']} {r['name']} owner={r['owner_id']} [{r['status']}]" for r in rows)


def vendor_attach_product(vendor_id: int, product_id: int, commission: float = 15.0) -> str:
    enterprise_ensure()
    with connect() as conn:
        v = conn.execute("SELECT id FROM vendors WHERE id=?", (int(vendor_id),)).fetchone()
        p = conn.execute("SELECT id, title FROM products WHERE id=?", (int(product_id),)).fetchone()
        if not v or not p:
            return "Vendor or product not found"
        conn.execute(
            "INSERT INTO vendor_products (vendor_id, product_id, commission_percent) VALUES (?,?,?)",
            (int(vendor_id), int(product_id), float(commission)),
        )
        conn.commit()
    return f"Product #{product_id} linked to vendor #{vendor_id} ({commission}% commission)"


def saas_create_tenant(owner_id: int, name: str, plan: str = "free") -> str:
    enterprise_ensure()
    seats = {"free": 3, "pro": 25, "enterprise": 200}.get((plan or "free").lower(), 3)
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO saas_tenants (owner_id, name, plan, seats) VALUES (?,?,?,?)",
            (int(owner_id), (name or "Workspace")[:80], plan.lower(), seats),
        )
        tid = int(cur.lastrowid)
        conn.execute(
            "INSERT INTO saas_members (tenant_id, user_id, role) VALUES (?,?, 'owner')",
            (tid, int(owner_id)),
        )
        conn.commit()
    _audit(owner_id, "saas_create", "tenant", tid, plan)
    return f"Tenant #{tid} plan={plan} seats={seats}"


def saas_add_member(
    tenant_id: int, user_id: int, role: str = "member", actor_id: int = 0
) -> str:
    """Add member — actor must be owner/admin of the tenant or platform staff."""
    enterprise_ensure()
    if not actor_id:
        return "actor required"
    with connect() as conn:
        t = conn.execute(
            "SELECT seats, name, owner_id FROM saas_tenants WHERE id=?",
            (int(tenant_id),),
        ).fetchone()
        if not t:
            return "Tenant not found"
        is_owner = int(t["owner_id"] or 0) == int(actor_id) if "owner_id" in t.keys() else False
        is_member_admin = False
        try:
            m = conn.execute(
                "SELECT role FROM saas_members WHERE tenant_id=? AND user_id=?",
                (int(tenant_id), int(actor_id)),
            ).fetchone()
            is_member_admin = bool(m and str(m["role"]).lower() in {"owner", "admin"})
        except Exception:
            pass
        if not (is_owner or is_member_admin or role_require(int(actor_id), "staff")):
            return "Not authorized for this tenant"
        n = conn.execute(
            "SELECT COUNT(*) c FROM saas_members WHERE tenant_id=?", (int(tenant_id),)
        ).fetchone()["c"]
        if int(n) >= int(t["seats"]):
            return f"Seat limit reached ({t['seats']}) — upgrade plan"
        conn.execute(
            "INSERT OR REPLACE INTO saas_members (tenant_id, user_id, role) VALUES (?,?,?)",
            (int(tenant_id), int(user_id), (role or "member")[:20]),
        )
        conn.commit()
    return f"User {user_id} added to {t['name']} as {role}"


def saas_tenant_info(tenant_id: int) -> str:
    enterprise_ensure()
    with connect() as conn:
        t = conn.execute("SELECT * FROM saas_tenants WHERE id=?", (int(tenant_id),)).fetchone()
        if not t:
            return "Tenant not found"
        members = conn.execute(
            "SELECT user_id, role FROM saas_members WHERE tenant_id=?", (int(tenant_id),)
        ).fetchall()
    lines = [
        f"Tenant #{t['id']} {t['name']} plan={t['plan']} seats={t['seats']} status={t['status']}",
        "Members:",
    ]
    for m in members:
        lines.append(f"  user={m['user_id']} role={m['role']}")
    return "\n".join(lines)


def invoice_create(user_id: int, amount_cents: int, order_id: int = 0, currency: str = "USD") -> str:
    enterprise_ensure()
    due = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d")
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO invoices (user_id, order_id, amount_cents, currency, due_at) VALUES (?,?,?,?,?)",
            (int(user_id), int(order_id), int(amount_cents), currency, due),
        )
        conn.commit()
        iid = int(cur.lastrowid)
    _audit(user_id, "invoice_create", "invoice", iid, str(amount_cents))
    return f"Invoice #{iid}: {amount_cents/100:.2f} {currency} due {due}"


def invoice_list(user_id: int = 0) -> str:
    enterprise_ensure()
    with connect() as conn:
        if user_id:
            rows = conn.execute(
                "SELECT id, amount_cents, currency, status, due_at FROM invoices WHERE user_id=? ORDER BY id DESC LIMIT 30",
                (int(user_id),),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, user_id, amount_cents, currency, status, due_at FROM invoices ORDER BY id DESC LIMIT 40"
            ).fetchall()
    if not rows:
        return "No invoices"
    return "\n".join(
        f"#{r['id']} {r['amount_cents']/100:.2f} {r['currency']} [{r['status']}] due={r['due_at']}"
        for r in rows
    )


def invoice_pay(invoice_id: int, user_id: int) -> str:
    """Do NOT mark paid without a real payment provider callback.

    Returns instructions only. Actual status change happens via
    Telegram successful_payment handler or admin confirm.
    """
    enterprise_ensure()
    with connect() as conn:
        inv = conn.execute("SELECT * FROM invoices WHERE id=?", (int(invoice_id),)).fetchone()
        if not inv:
            return "Invoice not found"
        if inv["status"] == "paid":
            return "Already paid"
        if int(inv["user_id"]) != int(user_id):
            return "Not your invoice"
    return (
        f"Invoice #{invoice_id} is unpaid. "
        "Use Telegram Payments (/buy) or submit Vodafone proof (/vfcash) — "
        "status changes only after verified payment."
    )


def analytics_dashboard(admin_id: int = 0) -> str:
    """Staff-only aggregate metrics (no public revenue leak)."""
    enterprise_ensure()
    if not admin_id or not role_require(int(admin_id), "staff"):
        return "❌ Analytics — للأدمن فقط"
    with connect() as conn:
        products = conn.execute("SELECT COUNT(*) c FROM products WHERE active=1").fetchone()["c"]
        orders = conn.execute("SELECT COUNT(*) c FROM orders").fetchone()["c"]
        paid = conn.execute("SELECT COUNT(*) c FROM orders WHERE status IN ('paid','processing','shipped','delivered')").fetchone()["c"]
        revenue = conn.execute(
            "SELECT COALESCE(SUM(amount_cents),0) s FROM orders WHERE status IN ('paid','processing','shipped','delivered')"
        ).fetchone()["s"]
        refunds = conn.execute("SELECT COUNT(*) c FROM orders WHERE status='refunded'").fetchone()["c"]
        wallets = conn.execute("SELECT COALESCE(SUM(balance),0) s FROM wallets").fetchone()["s"]
        try:
            subs = conn.execute(
                "SELECT COUNT(*) c FROM subscriptions WHERE date(expires_at) >= date('now')"
            ).fetchone()["c"]
        except Exception:
            try:
                subs = conn.execute("SELECT COUNT(*) c FROM subscriptions").fetchone()["c"]
            except Exception:
                subs = 0
        low = conn.execute("SELECT COUNT(*) c FROM products WHERE active=1 AND stock<=5").fetchone()["c"]
        coupons_used = conn.execute("SELECT COALESCE(SUM(used),0) s FROM coupons").fetchone()["s"]
        tenants = conn.execute("SELECT COUNT(*) c FROM saas_tenants").fetchone()["c"]
        vendors = conn.execute("SELECT COUNT(*) c FROM vendors").fetchone()["c"]
    return (
        "Analytics dashboard\n"
        f"Products={products} LowStock={low}\n"
        f"Orders={orders} PaidLike={paid} Refunds={refunds}\n"
        f"RevenueCents={revenue} WalletSum={wallets}\n"
        f"Subs≈{subs} CouponsUsed={coupons_used}\n"
        f"Vendors={vendors} SaaSTenants={tenants}"
    )


def audit_tail(limit: int = 20) -> str:
    enterprise_ensure()
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, actor_id, action, entity, entity_id, detail, created_at FROM audit_log ORDER BY id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
    if not rows:
        return "Audit log empty"
    return "\n".join(
        f"#{r['id']} {r['created_at']} actor={r['actor_id']} {r['action']} {r['entity']}#{r['entity_id']} {r['detail'][:40]}"
        for r in rows
    )


def broadcast_segment_count(rule: str = "all") -> str:
    """Simple segments: all | paid | wallet | sub"""
    enterprise_ensure()
    with connect() as conn:
        if rule == "paid":
            n = conn.execute("SELECT COUNT(DISTINCT user_id) c FROM orders WHERE status IN ('paid','delivered')").fetchone()["c"]
        elif rule == "wallet":
            n = conn.execute("SELECT COUNT(*) c FROM wallets WHERE balance>0").fetchone()["c"]
        elif rule == "sub":
            try:
                n = conn.execute("SELECT COUNT(DISTINCT user_id) c FROM subscriptions").fetchone()["c"]
            except Exception:
                n = 0
        else:
            n = conn.execute("SELECT COUNT(DISTINCT user_id) c FROM point_ledger").fetchone()["c"]
    return f"Segment '{rule}' size ≈ {n} users (dry-run count — send via admin tools)"


def role_grant(actor_id: int, user_id: int, role: str) -> str:
    """RBAC-lite: only admin/owner can grant roles."""
    enterprise_ensure()
    if not actor_id or not role_require(int(actor_id), "admin"):
        return "❌ غير مصرح — للأدمن فقط"
    role = (role or "member").lower()
    if role not in {"admin", "staff", "vendor", "member", "owner"}:
        return "Roles: admin|staff|vendor|member|owner"
    # Prevent privilege self-escalation to owner without existing owner
    if role == "owner" and role_of(int(actor_id)) != "owner":
        # allow platform ADMIN_IDS only
        if role_of(int(actor_id)) not in {"admin", "owner"}:
            return "Cannot grant owner"
    with connect() as conn:
        conn.execute(
            "INSERT INTO extras_kv (user_id, kind, body, status) VALUES (?,?,?, 'open')",
            (int(user_id), "role", role),
        )
        conn.commit()
    _audit(actor_id, "role_grant", "user", user_id, role)
    return f"User {user_id} granted role={role}"


def role_of(user_id: int) -> str:
    enterprise_ensure()
    # Bootstrap: ADMIN_IDS and ADMIN_USER_IDS (config.py) are always admin
    try:
        import os as _os

        raw = (
            (_os.getenv("ADMIN_IDS") or "")
            + ","
            + (_os.getenv("ADMIN_USER_IDS") or "")
        ).strip()
        if raw:
            admins = {int(x) for x in raw.replace(";", ",").split(",") if x.strip().isdigit()}
            if int(user_id) in admins:
                return "admin"
    except Exception:
        pass
    with connect() as conn:
        row = conn.execute(
            "SELECT body FROM extras_kv WHERE user_id=? AND kind='role' AND status='open' ORDER BY id DESC LIMIT 1",
            (int(user_id),),
        ).fetchone()
    return row["body"] if row else "member"


def role_require(user_id: int, minimum: str = "staff") -> bool:
    order = ["member", "vendor", "staff", "admin", "owner"]
    cur = role_of(user_id)
    try:
        return order.index(cur) >= order.index(minimum)
    except ValueError:
        return False



def ux_wrap(title: str, body: str, hints: list[str] | None = None) -> str:
    """Never return a bare/fragile one-liner without next-step hints."""
    body = (body or "").strip() or "لا توجد بيانات بعد."
    hints = hints or []
    lines = [f"【 {title} 】", body]
    if hints:
        lines.append("")
        lines.append("التالي:")
        for h in hints[:5]:
            lines.append(f"• {h}")
    return "\n".join(lines)
