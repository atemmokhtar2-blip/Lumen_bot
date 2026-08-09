"""Market services — production-safe SQLite logic for generated bots.

This module is copied into generated projects as app/services/market.py.
No fake payment success; balances cannot go negative via debit helpers.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from app.db import connect, init_db


def ensure() -> None:
    init_db()


def catalog() -> str:
    ensure()
    seed_demo_catalog()
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, title, price_cents, currency, stock FROM products "
            "WHERE active=1 ORDER BY id DESC LIMIT 50"
        ).fetchall()
    if not rows:
        return "No products yet. Admin: /addproduct Title|price_cents"
    return "\n".join(
        f"#{r['id']} {r['title']} — {r['price_cents']/100:.2f} {r['currency']} (stock {r['stock']})"
        for r in rows
    )


def add_item(admin_id: int, text: str) -> int:
    ensure()
    title, _, price = (text or "").partition("|")
    title = title.strip() or "Item"
    try:
        price_cents = int((price or "0").strip() or "0")
    except ValueError:
        price_cents = 0
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO products (title, price_cents) VALUES (?, ?)",
            (title[:200], max(0, price_cents)),
        )
        conn.commit()
        return int(cur.lastrowid)


def place_order(user_id: int, text: str) -> int:
    ensure()
    seed_demo_catalog()
    try:
        pid = int((text or "").split()[0])
    except Exception:
        return 0
    with connect() as conn:
        prod = conn.execute(
            "SELECT * FROM products WHERE id=? AND active=1", (pid,)
        ).fetchone()
        if not prod or int(prod["stock"]) <= 0:
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


def list_orders(only_open: bool = True) -> list[dict]:
    ensure()
    q = "SELECT * FROM orders"
    if only_open:
        q += " WHERE status IN ('pending','paid')"
    q += " ORDER BY id DESC LIMIT 40"
    with connect() as conn:
        return [dict(r) for r in conn.execute(q).fetchall()]


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


def points_balance(user_id: int) -> int:
    ensure()
    with connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(delta),0) AS b FROM point_ledger WHERE user_id=?",
            (user_id,),
        ).fetchone()
    return int(row["b"] if row else 0)


def points_credit(user_id: int, delta: int, reason: str = "") -> int:
    ensure()
    if int(delta) == 0:
        return points_balance(user_id)
    with connect() as conn:
        conn.execute(
            "INSERT INTO point_ledger (user_id, delta, reason) VALUES (?,?,?)",
            (user_id, int(delta), (reason or "")[:200]),
        )
        conn.commit()
    return points_balance(user_id)


def points_debit(user_id: int, amount: int, reason: str = "") -> bool:
    amount = abs(int(amount))
    if points_balance(user_id) < amount:
        return False
    points_credit(user_id, -amount, reason or "debit")
    return True


def leaderboard(limit: int = 10) -> list[tuple[int, int]]:
    ensure()
    with connect() as conn:
        rows = conn.execute(
            "SELECT user_id, SUM(delta) AS b FROM point_ledger "
            "GROUP BY user_id HAVING b>0 ORDER BY b DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [(int(r["user_id"]), int(r["b"])) for r in rows]


def list_plans() -> list[dict]:
    ensure()
    with connect() as conn:
        rows = conn.execute("SELECT * FROM plans WHERE active=1 ORDER BY id").fetchall()
        if not rows:
            conn.execute(
                "INSERT INTO plans (name, price_cents, duration_days) VALUES "
                "('Free',0,3650),('Pro',999,30)"
            )
            conn.commit()
            rows = conn.execute("SELECT * FROM plans WHERE active=1 ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def is_sub_active(user_id: int) -> bool:
    ensure()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM subscriptions WHERE user_id=? AND status='active' "
            "ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    if not row:
        return False
    ends = row["ends_at"] or ""
    return (not ends) or ends >= now


def grant_sub(user_id: int, plan_id: int) -> bool:
    ensure()
    list_plans()  # ensure default Free/Pro plans exist
    with connect() as conn:
        plan = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
        if not plan:
            return False
        days = int(plan["duration_days"] or 30)
        ends = (datetime.now(timezone.utc) + timedelta(days=days)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        conn.execute(
            "INSERT INTO subscriptions (user_id, plan_id, status, ends_at) "
            "VALUES (?,?, 'active', ?)",
            (user_id, plan_id, ends),
        )
        conn.commit()
    return True


def my_subscription(user_id: int) -> str:
    ensure()
    with connect() as conn:
        row = conn.execute(
            "SELECT s.*, p.name AS plan_name FROM subscriptions s "
            "LEFT JOIN plans p ON p.id=s.plan_id WHERE s.user_id=? "
            "ORDER BY s.id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    if not row:
        return "No subscription"
    return (
        f"plan={row['plan_name'] or row['plan_id']} "
        f"status={row['status']} ends={row['ends_at'] or '—'}"
    )


def list_contests() -> list[dict]:
    ensure()
    with connect() as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM contests WHERE status='open' ORDER BY id DESC LIMIT 20"
            ).fetchall()
        ]


def create_contest(title: str) -> int:
    ensure()
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO contests (title) VALUES (?)", ((title or "Contest")[:200],)
        )
        conn.commit()
        return int(cur.lastrowid)


def join_contest(user_id: int, contest_id: int) -> bool:
    ensure()
    with connect() as conn:
        c = conn.execute(
            "SELECT status FROM contests WHERE id=?", (contest_id,)
        ).fetchone()
        if not c or c["status"] != "open":
            return False
        try:
            conn.execute(
                "INSERT INTO contest_entries (contest_id, user_id) VALUES (?,?)",
                (contest_id, user_id),
            )
            conn.commit()
            return True
        except Exception:
            return False


def draw_winner(contest_id: int) -> int:
    """Deterministic winner: lowest user_id among entries (documented)."""
    ensure()
    with connect() as conn:
        rows = conn.execute(
            "SELECT user_id FROM contest_entries WHERE contest_id=?",
            (contest_id,),
        ).fetchall()
        if not rows:
            return 0
        winner = min(int(r["user_id"]) for r in rows)
        conn.execute(
            "UPDATE contests SET status='closed', winner_user_id=? WHERE id=?",
            (winner, contest_id),
        )
        conn.commit()
        return winner


def wallet_balance(user_id: int) -> int:
    ensure()
    with connect() as conn:
        row = conn.execute(
            "SELECT balance FROM wallets WHERE user_id=?", (user_id,)
        ).fetchone()
    return int(row["balance"]) if row else 0


def wallet_add(user_id: int, amount: int) -> int:
    ensure()
    with connect() as conn:
        conn.execute(
            "INSERT INTO wallets (user_id, balance) VALUES (?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET balance=balance+excluded.balance",
            (user_id, int(amount)),
        )
        conn.commit()
    return wallet_balance(user_id)


def referral_code(user_id: int) -> str:
    ensure()
    with connect() as conn:
        row = conn.execute(
            "SELECT code FROM referrals WHERE user_id=?", (user_id,)
        ).fetchone()
        if row:
            return str(row["code"])
        code = f"R{user_id}{secrets.token_hex(2).upper()}"
        conn.execute(
            "INSERT INTO referrals (user_id, code) VALUES (?,?)", (user_id, code)
        )
        conn.commit()
        return code


def daily_checkin(user_id: int) -> str:
    ensure()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM extras_kv WHERE user_id=? AND kind='checkin' AND body=? LIMIT 1",
            (user_id, today),
        ).fetchone()
        if row:
            return "Already checked in today"
        conn.execute(
            "INSERT INTO extras_kv (user_id, kind, body, status) VALUES (?,?,?, 'open')",
            (user_id, "checkin", today),
        )
        conn.commit()
    bal = points_credit(user_id, 1, "daily_checkin")
    return f"Check-in OK. Points={bal}"


def get_lang(user_id: int) -> str:
    ensure()
    with connect() as conn:
        row = conn.execute(
            "SELECT lang FROM user_lang WHERE user_id=?", (user_id,)
        ).fetchone()
    return (row["lang"] if row else "en") or "en"


def set_lang(user_id: int, lang: str) -> str:
    ensure()
    lang = (lang or "en").strip().lower()[:5]
    if lang not in {"en", "ar"}:
        lang = "en"
    with connect() as conn:
        conn.execute(
            "INSERT INTO user_lang (user_id, lang) VALUES (?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET lang=excluded.lang",
            (user_id, lang),
        )
        conn.commit()
    return lang


def create_coupon(code: str, percent: int) -> str:
    ensure()
    code = (code or "").strip().upper()[:32]
    percent = max(1, min(100, int(percent)))
    if not code:
        return ""
    with connect() as conn:
        conn.execute(
            "INSERT INTO extras_kv (user_id, kind, body, status) VALUES (0, 'coupon', ?, 'open')",
            (f"{code}|{percent}",),
        )
        conn.commit()
    return code


def apply_coupon(code: str) -> int:
    """Return discount percent or 0 if invalid."""
    ensure()
    code = (code or "").strip().upper()
    with connect() as conn:
        row = conn.execute(
            "SELECT body FROM extras_kv WHERE kind='coupon' AND status='open' AND body LIKE ?",
            (f"{code}|%",),
        ).fetchone()
    if not row:
        return 0
    try:
        return int(str(row["body"]).split("|", 1)[1])
    except Exception:
        return 0


def format_orders(items: list) -> str:
    if not items:
        return "No orders"
    return "\n".join(
        f"#{i.get('id')} user={i.get('user_id')} {i.get('status')} {i.get('amount_cents')}"
        for i in items
    )


def recommend_products(user_id: int = 0, limit: int = 5) -> str:
    """Simple intelligent ranking: in-stock products by lowest id (stable demo rank)."""
    ensure()
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, title, price_cents, currency, stock FROM products "
            "WHERE active=1 AND stock>0 ORDER BY stock DESC, id ASC LIMIT ?",
            (limit,),
        ).fetchall()
    if not rows:
        return catalog()
    return "Recommended:\n" + "\n".join(
        f"#{r['id']} {r['title']} — {r['price_cents']/100:.2f} {r['currency']}"
        for r in rows
    )


def claim_referral(user_id: int, code: str) -> bool:
    """Attach user to referrer once; credit both sides. Idempotent."""
    ensure()
    code = (code or "").strip()
    if not code:
        return False
    with connect() as conn:
        owner = conn.execute(
            "SELECT user_id FROM referrals WHERE code=?", (code,)
        ).fetchone()
        if not owner or int(owner["user_id"]) == user_id:
            return False
        mine = conn.execute(
            "SELECT invited_by FROM referrals WHERE user_id=?", (user_id,)
        ).fetchone()
        if mine and int(mine["invited_by"] or 0) > 0:
            return False
        # ensure row for invitee
        code_self = f"R{user_id}"
        existing = conn.execute(
            "SELECT code FROM referrals WHERE user_id=?", (user_id,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE referrals SET invited_by=? WHERE user_id=? AND (invited_by IS NULL OR invited_by=0)",
                (int(owner["user_id"]), user_id),
            )
        else:
            conn.execute(
                "INSERT INTO referrals (user_id, code, invited_by) VALUES (?,?,?)",
                (user_id, code_self, int(owner["user_id"])),
            )
        conn.execute(
            "UPDATE referrals SET rewards = rewards + 1 WHERE user_id=?",
            (int(owner["user_id"]),),
        )
        conn.commit()
    points_credit(int(owner["user_id"]), 10, "referral")
    points_credit(user_id, 5, "referral_join")
    return True


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


def seed_demo_catalog() -> int:
    """Insert a few demo products if catalog empty. Returns count added."""
    ensure()
    with connect() as conn:
        n = conn.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"]
        if int(n) > 0:
            return 0
        demo = [
            ("Starter Pack", 499, "USD", 50),
            ("Pro Pack", 1499, "USD", 30),
            ("VIP Access", 2999, "USD", 10),
        ]
        for title, price, cur, stock in demo:
            conn.execute(
                "INSERT INTO products (title, price_cents, currency, stock) VALUES (?,?,?,?)",
                (title, price, cur, stock),
            )
        conn.commit()
        return len(demo)


def start_trial(user_id: int, days: int = 7) -> str:
    """Grant a temporary trial subscription on plan #1 (or create Trial plan)."""
    ensure()
    days = max(1, min(30, int(days)))
    with connect() as conn:
        plan = conn.execute(
            "SELECT id FROM plans WHERE name='Trial' AND active=1 LIMIT 1"
        ).fetchone()
        if not plan:
            conn.execute(
                "INSERT INTO plans (name, price_cents, duration_days) VALUES ('Trial', 0, ?)",
                (days,),
            )
            conn.commit()
            plan = conn.execute(
                "SELECT id FROM plans WHERE name='Trial' ORDER BY id DESC LIMIT 1"
            ).fetchone()
        pid = int(plan["id"])
    if grant_sub(user_id, pid):
        return f"Trial active for {days} days"
    return "Trial failed"


def levels_for(user_id: int) -> str:
    """Simple level from points: every 50 points = 1 level."""
    bal = points_balance(user_id)
    level = bal // 50
    into = bal % 50
    return f"Level {level} ({into}/50 to next) — points={bal}"


def get_order(order_id: int) -> dict | None:
    ensure()
    with connect() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
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
    if mark_paid(oid, telegram_charge_id or ""):
        ensure()
        with connect() as conn:
            conn.execute(
                "UPDATE products SET stock = CASE WHEN stock>0 THEN stock-1 ELSE 0 END WHERE id=?",
                (int(order["product_id"]),),
            )
            conn.execute(
                "INSERT INTO payments (user_id, order_id, amount_cents, currency, provider_charge_id, payload) "
                "VALUES (?,?,?,?,?,?)",
                (
                    user_id,
                    oid,
                    int(order["amount_cents"]),
                    order.get("currency") or "USD",
                    (telegram_charge_id or "")[:200],
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


def cart_add(user_id: int, product_id: int, qty: int = 1) -> bool:
    ensure()
    seed_demo_catalog()
    qty = max(1, int(qty))
    prod = get_product(product_id)
    if not prod:
        return False
    with connect() as conn:
        conn.execute(
            "INSERT INTO cart_items (user_id, product_id, qty) VALUES (?,?,?) "
            "ON CONFLICT(user_id, product_id) DO UPDATE SET qty=qty+excluded.qty",
            (user_id, product_id, qty),
        )
        conn.commit()
    return True


def cart_view(user_id: int) -> str:
    ensure()
    with connect() as conn:
        rows = conn.execute(
            "SELECT c.product_id, c.qty, p.title, p.price_cents, p.currency "
            "FROM cart_items c LEFT JOIN products p ON p.id=c.product_id "
            "WHERE c.user_id=?",
            (user_id,),
        ).fetchall()
    if not rows:
        return "Cart empty"
    lines = []
    total = 0
    cur = "USD"
    for r in rows:
        line_total = int(r["price_cents"] or 0) * int(r["qty"])
        total += line_total
        cur = r["currency"] or cur
        lines.append(f"#{r['product_id']} {r['title']} x{r['qty']} = {line_total/100:.2f}")
    lines.append(f"Total: {total/100:.2f} {cur}")
    return "\n".join(lines)


def cart_clear(user_id: int) -> int:
    ensure()
    with connect() as conn:
        cur = conn.execute("DELETE FROM cart_items WHERE user_id=?", (user_id,))
        conn.commit()
        return int(cur.rowcount)


def cart_checkout(user_id: int) -> str:
    """Create pending orders for every cart line; clear cart on success."""
    ensure()
    seed_demo_catalog()
    with connect() as conn:
        rows = conn.execute(
            "SELECT product_id, qty FROM cart_items WHERE user_id=?",
            (user_id,),
        ).fetchall()
    if not rows:
        return "Cart empty — add items with /cartadd <product_id>"
    order_ids = []
    for r in rows:
        pid = int(r["product_id"])
        qty = int(r["qty"] or 1)
        for _ in range(max(1, qty)):
            oid = place_order(user_id, str(pid))
            if oid:
                order_ids.append(oid)
    cart_clear(user_id)
    if not order_ids:
        return "Checkout failed — no valid products"
    return f"Checkout OK — orders: {', '.join(f'#{i}' for i in order_ids)}"


def wishlist_add(user_id: int, product_id: int) -> str:
    ensure()
    seed_demo_catalog()
    prod = get_product(product_id)
    if not prod:
        return f"Product #{product_id} not found. /shop to list."
    with connect() as conn:
        conn.execute(
            "INSERT INTO extras_kv (user_id, kind, body, status) VALUES (?,?,?, 'open')",
            (user_id, "wishlist", f"{product_id}:{prod['title']}"),
        )
        conn.commit()
    return f"Wishlist + {prod['title']}"


def wishlist_view(user_id: int) -> str:
    ensure()
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, body FROM extras_kv WHERE user_id=? AND kind='wishlist' AND status='open' ORDER BY id DESC LIMIT 30",
            (user_id,),
        ).fetchall()
    if not rows:
        return "Wishlist empty"
    return "\n".join(f"#{r['id']} {r['body']}" for r in rows)


def refund_request(user_id: int, order_id: int) -> str:
    ensure()
    order = get_order(order_id)
    if not order or int(order["user_id"]) != int(user_id):
        return "Order not found"
    with connect() as conn:
        conn.execute(
            "INSERT INTO extras_kv (user_id, kind, body, status) VALUES (?,?,?, 'open')",
            (user_id, "refund", f"order:{order_id}"),
        )
        conn.commit()
    return f"Refund requested for order #{order_id} (pending staff review)"


def digital_deliver(user_id: int, order_id: int) -> str:
    ensure()
    order = get_order(order_id)
    if not order:
        return "Order not found"
    if order["status"] != "paid":
        return f"Order #{order_id} status={order['status']} — pay first"
    return f"Digital delivery for order #{order_id}: unlock code DL-{order_id}-{user_id % 10000:04d}"


def shipping_set(user_id: int, address: str) -> str:
    ensure()
    address = (address or "").strip()
    if len(address) < 5:
        return "Usage: send address text after the command"
    with connect() as conn:
        conn.execute(
            "INSERT INTO extras_kv (user_id, kind, body, status) VALUES (?,?,?, 'open')",
            (user_id, "shipping", address[:500]),
        )
        conn.commit()
    return "Shipping address saved"


def review_add(user_id: int, text: str) -> str:
    ensure()
    text = (text or "").strip()
    if len(text) < 2:
        return "Usage: /reviewadd <product_id> <text>"
    with connect() as conn:
        conn.execute(
            "INSERT INTO extras_kv (user_id, kind, body, status) VALUES (?,?,?, 'open')",
            (user_id, "review", text[:1000]),
        )
        conn.commit()
    return "Review saved — thank you"
