def submit_vodafone_payment(
    user_id: int,
    *,
    amount_cents: int,
    reference: str,
    photo_file_id: str = "",
) -> str:
    """Record Vodafone Cash proof — ALWAYS pending until admin approves.

    Never auto-credits. Rejects duplicate references. Admin uses vfcash_approve.
    """
    ensure()
    amount_cents = max(0, int(amount_cents or 0))
    reference = (reference or "").strip()[:40]
    photo_file_id = (photo_file_id or "")[:200]
    if amount_cents <= 0 or len(reference) < 6:
        return "❌ بيانات الدفع غير مكتملة"
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vodafone_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount_cents INTEGER NOT NULL,
                reference TEXT NOT NULL UNIQUE,
                photo_file_id TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        exists = conn.execute(
            "SELECT id, status FROM vodafone_payments WHERE reference=?",
            (reference,),
        ).fetchone()
        if exists:
            return f"❌ رقم العملية مستخدم من قبل (#{exists['id']} — {exists['status']})"
        cur = conn.execute(
            "INSERT INTO vodafone_payments (user_id, amount_cents, reference, photo_file_id, status) "
            "VALUES (?,?,?,?,?)",
            (user_id, amount_cents, reference, photo_file_id, "pending"),
        )
        pid = int(cur.lastrowid)
        conn.commit()
        return (
            f"⏳ تم تسجيل إثبات فودافون #{pid}\n"
            f"المبلغ: {amount_cents/100:.2f} · المرجع: {reference}\n"
            f"بانتظار مراجعة الإدارة (لا شحن تلقائي)."
        )


def vfcash_approve(admin_id: int, payment_id: int) -> str:
    """Staff/admin only — credit wallet after human verification."""
    ensure()
    if not role_require(int(admin_id), "staff"):
        return "❌ غير مصرح — صلاحيات إدارة مطلوبة"
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM vodafone_payments WHERE id=?", (payment_id,)
        ).fetchone()
        if not row:
            return "عملية غير موجودة"
        if row["status"] == "approved":
            return "معتمدة مسبقاً"
        conn.execute(
            "UPDATE vodafone_payments SET status='approved' WHERE id=? AND status='pending'",
            (payment_id,),
        )
        if conn.total_changes == 0:
            return "تعذر الاعتماد"
        uid = int(row["user_id"])
        amt = int(row["amount_cents"])
        conn.execute(
            "CREATE TABLE IF NOT EXISTS wallets (user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0)"
        )
        w = conn.execute("SELECT balance FROM wallets WHERE user_id=?", (uid,)).fetchone()
        if w:
            conn.execute(
                "UPDATE wallets SET balance=balance+? WHERE user_id=?", (amt, uid)
            )
        else:
            conn.execute(
                "INSERT INTO wallets (user_id, balance) VALUES (?, ?)", (uid, amt)
            )
        conn.commit()
    try:
        _audit(int(admin_id), "vfcash_approve", "vodafone", payment_id, str(amt))
    except Exception:
        pass
    return f"✅ اعتمدت عملية فودافون #{payment_id} وتم شحن المحفظة"


def place_order(user_id: int, text: str) -> int:
    """Create pending order with atomic stock reservation (prevents overselling)."""
    ensure()
    seed_demo_catalog()
    try:
        pid = int((text or "").split()[0])
    except Exception:
        return 0
    with connect() as conn:
        # Atomic: only decrement if stock still > 0
        cur = conn.execute(
            "UPDATE products SET stock = stock - 1 "
            "WHERE id=? AND active=1 AND stock > 0",
            (pid,),
        )
        if cur.rowcount != 1:
            conn.rollback()
            return 0
        prod = conn.execute(
            "SELECT * FROM products WHERE id=? AND active=1", (pid,)
        ).fetchone()
        if not prod:
            conn.rollback()
            return 0
        cur = conn.execute(
            "INSERT INTO orders (user_id, product_id, amount_cents, currency, status, payload) "
            "VALUES (?,?,?,?,?,?)",
            (
                user_id,
                pid,
                int(prod["price_cents"]),
                prod["currency"],
                "pending",
                f"order:{user_id}:{pid}",
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_orders(
    only_open: bool = True,
    *,
    user_id: int | None = None,
    admin_id: int = 0,
) -> list[dict]:
    """List orders. Non-admins only see their own rows (no IDOR)."""
    ensure()
    with connect() as conn:
        if admin_id and role_require(int(admin_id), "staff"):
            q = "SELECT * FROM orders"
            args: list = []
            if only_open:
                q += " WHERE status IN ('pending','paid')"
            q += " ORDER BY id DESC LIMIT 40"
            return [dict(r) for r in conn.execute(q, args).fetchall()]
        uid = int(user_id or 0)
        if not uid:
            return []
        q = "SELECT * FROM orders WHERE user_id=?"
        args = [uid]
        if only_open:
            q += " AND status IN ('pending','paid')"
        q += " ORDER BY id DESC LIMIT 40"
        return [dict(r) for r in conn.execute(q, args).fetchall()]


def my_orders(user_id: int) -> list[dict]:
    ensure()
    with connect() as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 20",
                (user_id,),
            ).fetchall()
        ]


def mark_paid(order_id: int, charge_id: str) -> bool:
    """Only transitions pending → paid. Never invents success."""
    ensure()
    with connect() as conn:
        cur = conn.execute(
            "UPDATE orders SET status='paid', charge_id=? WHERE id=? AND status='pending'",
            ((charge_id or "")[:200], order_id),
        )
        conn.commit()
        return cur.rowcount > 0


def cancel_order(user_id: int, order_id: int) -> bool:
    ensure()
    with connect() as conn:
        cur = conn.execute(
            "UPDATE orders SET status='cancelled' WHERE id=? AND user_id=? AND status='pending'",
            (order_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0


def track_order(user_id: int, order_id: int) -> str:
    ensure()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM orders WHERE id=? AND user_id=?",
            (order_id, user_id),
        ).fetchone()
    if not row:
        return "Order not found"
    return f"#{row['id']} status={row['status']} amount={row['amount_cents']} {row['currency']}"


def format_orders(items: list) -> str:
    if not items:
        return "No orders"
    return "\n".join(
        f"#{i.get('id')} user={i.get('user_id')} {i.get('status')} {i.get('amount_cents')}"
        for i in items
    )


def get_order(order_id: int) -> dict | None:
    """Internal lookup by id only — prefer get_user_order for user-facing paths."""
    ensure()
    with connect() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    return dict(row) if row else None


def get_user_order(user_id: int, order_id: int) -> dict | None:
    """Ownership-safe order fetch."""
    ensure()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM orders WHERE id=? AND user_id=?",
            (int(order_id), int(user_id)),
        ).fetchone()
    return dict(row) if row else None


def get_product(product_id: int) -> dict | None:
    ensure()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM products WHERE id=? AND active=1", (product_id,)
        ).fetchone()
    return dict(row) if row else None


def invoice_payload_for_order(order_id: int) -> str:
    """Stable payload embedded in Telegram invoice (max ~128 bytes)."""
    return f"order:{int(order_id)}"


def parse_order_payload(payload: str) -> int:
    payload = (payload or "").strip()
    if payload.startswith("order:"):
        try:
            return int(payload.split(":", 1)[1])
        except ValueError:
            return 0
    return 0


def fulfill_successful_payment(user_id: int, payload: str, telegram_charge_id: str) -> str:
    """Mark order paid only after Telegram successful_payment. Returns status text."""
    oid = parse_order_payload(payload)
    if not oid:
        return "Payment received (no order payload)."
    order = get_order(oid)
    if not order:
        return f"Payment received but order #{oid} missing."
    if int(order["user_id"]) != int(user_id):
        return "Payment user mismatch — contact support."
    if order["status"] == "paid":
        return f"Order #{oid} already paid."
    if (order["status"] or "") != "pending":
        return f"Order #{oid} not payable (status={order['status']})."
    charge = (telegram_charge_id or "").strip()
    if not charge:
        return "Missing telegram_payment_charge_id — refuse fulfill."
    # Reject replay of same charge id
    ensure()
    with connect() as conn:
        try:
            dup = conn.execute(
                "SELECT id FROM payments WHERE provider_charge_id=? LIMIT 1",
                (charge[:200],),
            ).fetchone()
            if dup:
                return "Charge already recorded."
        except Exception:
            pass
    if mark_paid(oid, charge):
        with connect() as conn:
            # Decrement stock only if product_id present
            try:
                pid = int(order.get("product_id") or 0)
                if pid:
                    conn.execute(
                        "UPDATE products SET stock = CASE WHEN stock>0 THEN stock-1 ELSE 0 END WHERE id=?",
                        (pid,),
                    )
            except Exception:
                pass
            conn.execute(
                "INSERT INTO payments (user_id, order_id, amount_cents, currency, provider_charge_id, payload) "
                "VALUES (?,?,?,?,?,?)",
                (
                    user_id,
                    oid,
                    int(order["amount_cents"]),
                    order.get("currency") or "USD",
                    charge[:200],
                    (payload or "")[:200],
                ),
            )
            conn.commit()
        points_credit(user_id, 1, f"purchase_order_{oid}")
        return f"Order #{oid} paid. Thank you!"
    return f"Could not mark order #{oid} paid (status={order['status']})."


def payment_history(user_id: int, limit: int = 20) -> str:
    ensure()
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, order_id, amount_cents, currency, provider_charge_id, created_at "
            "FROM payments WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    if not rows:
        return "No payments yet"
    return "\n".join(
        f"#{r['id']} order={r['order_id']} {r['amount_cents']/100:.2f} {r['currency']} "
        f"at {r['created_at']} charge={r['provider_charge_id'][:12]}"
        for r in rows
    )


def payment_receipt(user_id: int, payment_id: int) -> str:
    ensure()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM payments WHERE id=? AND user_id=?",
            (payment_id, user_id),
        ).fetchone()
    if not row:
        return "Receipt not found"
    return (
        f"Receipt #{row['id']}\nOrder: {row['order_id']}\n"
        f"Amount: {row['amount_cents']/100:.2f} {row['currency']}\n"
        f"Charge: {row['provider_charge_id']}\nTime: {row['created_at']}"
    )


