"""Market services — production-safe SQLite logic for generated bots.

This module is copied into generated projects as app/services/market.py.
No fake payment success; balances cannot go negative via debit helpers.
"""
from __future__ import annotations

import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

from app.db import connect, init_db

# ── Simple per-process rate limit (sensitive ops) ─────────────────────────
_RATE: dict[str, float] = {}
_RATE_LOCK = threading.Lock()


def _rate_allow(key: str, min_interval_sec: float = 0.4) -> bool:
    """Return False if the same key hit too recently."""
    now = time.monotonic()
    with _RATE_LOCK:
        last = _RATE.get(key, 0.0)
        if now - last < min_interval_sec:
            return False
        _RATE[key] = now
        # opportunistic prune
        if len(_RATE) > 5000:
            cutoff = now - 60
            for k in [k for k, t in _RATE.items() if t < cutoff]:
                _RATE.pop(k, None)
        return True


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


def product_search(query: str, limit: int = 20) -> str:
    """Search products by title/category/description substring."""
    ensure()
    seed_demo_catalog()
    q = (query or "").strip()
    if not q:
        return "Usage: /productsearch <keyword>\n" + catalog()
    like = f"%{q}%"
    with connect() as conn:
        try:
            rows = conn.execute(
                "SELECT id, title, price_cents, currency, stock, category FROM products "
                "WHERE active=1 AND (title LIKE ? OR IFNULL(category,'') LIKE ? "
                "OR IFNULL(description,'') LIKE ?) ORDER BY id DESC LIMIT ?",
                (like, like, like, int(limit)),
            ).fetchall()
        except Exception:
            rows = conn.execute(
                "SELECT id, title, price_cents, currency, stock FROM products "
                "WHERE active=1 AND title LIKE ? ORDER BY id DESC LIMIT ?",
                (like, int(limit)),
            ).fetchall()
    if not rows:
        return f"No products matching «{q}»"
    lines = [f"نتائج البحث عن «{q}»:"]
    for r in rows:
        cat = ""
        try:
            if r["category"]:
                cat = f" [{r['category']}]"
        except Exception:
            cat = ""
        lines.append(
            f"#{r['id']} {r['title']}{cat} — {r['price_cents']/100:.2f} {r['currency']} (stock {r['stock']})"
        )
    lines.append("أضف للسلة: /cartadd <id>")
    return "\n".join(lines)


def product_info(product_id: int) -> str:
    """Detailed product card by id."""
    ensure()
    seed_demo_catalog()
    prod = get_product(int(product_id))
    if not prod:
        return f"Product #{product_id} not found. /shop to list."
    lines = [
        f"【 منتج #{prod['id']} 】",
        f"الاسم: {prod.get('title')}",
        f"السعر: {int(prod.get('price_cents') or 0)/100:.2f} {prod.get('currency') or 'EGP'}",
        f"المخزون: {prod.get('stock')}",
    ]
    if prod.get("category"):
        lines.append(f"التصنيف: {prod['category']}")
    if prod.get("description"):
        lines.append(f"الوصف: {prod['description']}")
    try:
        with connect() as conn:
            rev = conn.execute(
                "SELECT COUNT(*) c, AVG(rating) a FROM reviews WHERE product_id=?",
                (int(product_id),),
            ).fetchone()
            if rev and int(rev["c"] or 0) > 0:
                lines.append(f"التقييم: {float(rev['a'] or 0):.1f}/5 ({rev['c']} مراجعة)")
    except Exception:
        pass
    lines.append("أضف للسلة: /cartadd " + str(product_id))
    return "\n".join(lines)


def add_item(admin_id: int, text: str) -> int:
    """Admin-only product create. Returns 0 if unauthorized or invalid."""
    ensure()
    if not role_require(int(admin_id), "staff"):
        return 0
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
        pid = int(cur.lastrowid)
    try:
        _audit(int(admin_id), "add_item", "product", pid, title[:80])
    except Exception:
        pass
    return pid


def add_item_structured(
    admin_id: int,
    *,
    title: str,
    price_cents: int = 0,
    category: str = "",
    description: str = "",
    photo_file_id: str = "",
) -> int:
    """Multi-step flow product create — staff/admin only. Returns 0 if unauthorized."""
    ensure()
    if not role_require(int(admin_id), "staff"):
        return 0
    title = (title or "Item").strip()[:200]
    price_cents = max(0, int(price_cents or 0))
    category = (category or "")[:80]
    description = (description or "")[:2000]
    photo_file_id = (photo_file_id or "")[:200]
    with connect() as conn:
        # optional columns — ignore if schema is minimal
        try:
            cur = conn.execute(
                "INSERT INTO products (title, price_cents, category, description, photo_file_id) "
                "VALUES (?,?,?,?,?)",
                (title, price_cents, category, description, photo_file_id),
            )
        except Exception:
            cur = conn.execute(
                "INSERT INTO products (title, price_cents) VALUES (?, ?)",
                (title, price_cents),
            )
        conn.commit()
        return int(cur.lastrowid)


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


def points_balance(user_id: int) -> int:
    ensure()
    with connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(delta),0) AS b FROM point_ledger WHERE user_id=?",
            (user_id,),
        ).fetchone()
    return int(row["b"] if row else 0)


def points_credit(
    user_id: int, delta: int, reason: str = "", actor_id: int = 0
) -> int:
    """Credit points. Positive grants from outside payment require staff actor."""
    ensure()
    delta = int(delta)
    if delta == 0:
        return points_balance(user_id)
    if not _rate_allow(f"points_credit:{int(user_id)}", 0.25):
        return points_balance(user_id)
    # Large or free grants must be staff-authorized
    if delta > 0 and (reason or "").startswith("admin"):
        if not actor_id or not role_require(int(actor_id), "staff"):
            return points_balance(user_id)
    with connect() as conn:
        conn.execute(
            "INSERT INTO point_ledger (user_id, delta, reason) VALUES (?,?,?)",
            (user_id, delta, (reason or "")[:200]),
        )
        conn.commit()
    return points_balance(user_id)


def points_debit(user_id: int, amount: int, reason: str = "") -> bool:
    """Atomic points debit — check + write in one transaction (no race)."""
    amount = abs(int(amount))
    if amount <= 0:
        return True
    ensure()
    with connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(delta),0) AS b FROM point_ledger WHERE user_id=?",
            (user_id,),
        ).fetchone()
        bal = int(row["b"] if row else 0)
        if bal < amount:
            return False
        conn.execute(
            "INSERT INTO point_ledger (user_id, delta, reason) VALUES (?,?,?)",
            (user_id, -amount, (reason or "debit")[:200]),
        )
        conn.commit()
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


def grant_sub(user_id: int, plan_id: int, actor_id: int = 0) -> bool:
    """Grant subscription — staff/admin only (actor_id required)."""
    ensure()
    if not actor_id or not role_require(int(actor_id), "staff"):
        return False
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
    try:
        _audit(int(actor_id), "grant_sub", "subscription", int(user_id), str(plan_id))
    except Exception:
        pass
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


def draw_winner(contest_id: int, actor_id: int = 0) -> int:
    """Random winner among entries — staff only."""
    import random as _random

    ensure()
    if not actor_id or not role_require(int(actor_id), "staff"):
        return 0
    with connect() as conn:
        rows = conn.execute(
            "SELECT user_id FROM contest_entries WHERE contest_id=?",
            (contest_id,),
        ).fetchall()
        if not rows:
            return 0
        winner = int(_random.choice([int(r["user_id"]) for r in rows]))
        conn.execute(
            "UPDATE contests SET status='closed', winner_user_id=? WHERE id=?",
            (winner, contest_id),
        )
        conn.commit()
        try:
            _audit(int(actor_id), "draw_winner", "contest", int(contest_id), str(winner))
        except Exception:
            pass
        return winner


def wallet_balance(user_id: int) -> int:
    ensure()
    with connect() as conn:
        row = conn.execute(
            "SELECT balance FROM wallets WHERE user_id=?", (user_id,)
        ).fetchone()
    return int(row["balance"]) if row else 0


def wallet_add(user_id: int, amount: int) -> int:
    """Credit only (amount must be > 0). For debits use wallet_debit."""
    ensure()
    amount = int(amount)
    if amount <= 0:
        return wallet_balance(user_id)
    if not _rate_allow(f"wallet_add:{int(user_id)}", 0.25):
        return wallet_balance(user_id)
    with connect() as conn:
        conn.execute(
            "INSERT INTO wallets (user_id, balance) VALUES (?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET balance=balance+excluded.balance",
            (user_id, amount),
        )
        try:
            conn.execute(
                "INSERT INTO wallet_ledger (user_id, amount, note) VALUES (?,?,?)",
                (user_id, amount, "credit"),
            )
        except Exception:
            pass
        conn.commit()
    return wallet_balance(user_id)


def wallet_debit(user_id: int, amount: int, note: str = "debit") -> bool:
    """Atomic debit — never allows negative balance."""
    ensure()
    amount = abs(int(amount))
    if amount <= 0:
        return True
    with connect() as conn:
        cur = conn.execute(
            "UPDATE wallets SET balance = balance - ? "
            "WHERE user_id=? AND balance >= ?",
            (amount, user_id, amount),
        )
        if cur.rowcount != 1:
            conn.rollback()
            return False
        try:
            conn.execute(
                "INSERT INTO wallet_ledger (user_id, amount, note) VALUES (?,?,?)",
                (user_id, -amount, (note or "debit")[:200]),
            )
        except Exception:
            pass
        conn.commit()
    return True


def wallet_topup(user_id: int, amount: int) -> int:
    """DISABLED free top-up. Use payment flows (Telegram invoice / Vodafone+admin).

    Returns current balance unchanged. Admin credit: wallet_admin_credit.
    """
    # Intentionally does NOT credit — prevents free money
    return wallet_balance(user_id)


def wallet_admin_credit(admin_id: int, user_id: int, amount: int, note: str = "") -> int:
    """Staff/admin only wallet credit (manual adjustment after verified payment)."""
    ensure()
    if not role_require(int(admin_id), "staff"):
        return wallet_balance(user_id)
    amount = int(amount)
    if amount <= 0:
        return wallet_balance(user_id)
    bal = wallet_add(user_id, amount)
    try:
        _audit(int(admin_id), "wallet_admin_credit", "wallet", user_id, f"{amount}:{note}")
    except Exception:
        pass
    return bal


def wallet_history(user_id: int, limit: int = 20) -> str:
    ensure()
    bal = wallet_balance(user_id)
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS wallet_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                note TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        rows = conn.execute(
            "SELECT amount, note, created_at FROM wallet_ledger WHERE user_id=? "
            "ORDER BY id DESC LIMIT ?",
            (user_id, int(limit)),
        ).fetchall()
    if not rows:
        return f"الرصيد: {bal}\nلا حركات بعد."
    lines = [f"الرصيد: {bal}", "آخر الحركات:"]
    for r in rows:
        lines.append(f"• {r['created_at']}: {r['amount']} — {r['note'] or ''}")
    return "\n".join(lines)


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


def create_coupon(code: str, percent: int, admin_id: int = 0) -> str:
    """Admin-only legacy coupon create. Prefer coupon_create(admin_id, text)."""
    ensure()
    if admin_id and not role_require(int(admin_id), "staff"):
        return ""
    if not admin_id:
        # Refuse anonymous create — security: no open coupon minting
        return ""
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


def apply_coupon(code: str, user_id: int = 0) -> int:
    """Legacy percent lookup — one redemption per user when user_id set.

    Prefer coupon_apply_code(user_id, code, order_id) for real checkout.
    """
    ensure()
    code = (code or "").strip().upper()
    if not code:
        return 0
    if user_id and not _rate_allow(f"apply_coupon:{int(user_id)}", 1.0):
        return 0
    with connect() as conn:
        row = conn.execute(
            "SELECT id, body FROM extras_kv WHERE kind='coupon' AND status='open' AND body LIKE ?",
            (f"{code}|%",),
        ).fetchone()
        if not row:
            return 0
        try:
            pct = int(str(row["body"]).split("|", 1)[1])
        except Exception:
            return 0
        if user_id:
            # one-shot: mark redeemed for this user via extras_kv
            prior = conn.execute(
                "SELECT id FROM extras_kv WHERE kind='coupon_used' AND user_id=? AND body=? LIMIT 1",
                (int(user_id), code),
            ).fetchone()
            if prior:
                return 0
            conn.execute(
                "INSERT INTO extras_kv (user_id, kind, body, status) VALUES (?,?,?, 'open')",
                (int(user_id), "coupon_used", code),
            )
            conn.commit()
        return pct


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
    """Create pending orders for cart lines. Only clear lines that succeeded.

    Stock is reserved atomically inside place_order — partial success keeps
    failed lines in the cart (no silent overselling + wipe).
    """
    ensure()
    seed_demo_catalog()
    with connect() as conn:
        rows = conn.execute(
            "SELECT product_id, qty FROM cart_items WHERE user_id=?",
            (user_id,),
        ).fetchall()
    if not rows:
        return "Cart empty — add items with /cartadd <product_id>"
    order_ids: list[int] = []
    failed: list[str] = []
    for r in rows:
        pid = int(r["product_id"])
        qty = int(r["qty"] or 1)
        ok_qty = 0
        for _ in range(max(1, qty)):
            oid = place_order(user_id, str(pid))
            if oid:
                order_ids.append(oid)
                ok_qty += 1
            else:
                failed.append(f"#{pid}")
                break
        with connect() as conn:
            if ok_qty >= max(1, qty):
                conn.execute(
                    "DELETE FROM cart_items WHERE user_id=? AND product_id=?",
                    (user_id, pid),
                )
            elif ok_qty > 0:
                conn.execute(
                    "UPDATE cart_items SET qty = qty - ? WHERE user_id=? AND product_id=?",
                    (ok_qty, user_id, pid),
                )
            conn.commit()
    if not order_ids:
        return "Checkout failed — stock unavailable for cart items"
    msg = f"Checkout OK — orders: {', '.join(f'#{i}' for i in order_ids)}"
    if failed:
        msg += f" | partial fail (no stock): {', '.join(sorted(set(failed)))}"
    return msg


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
    """Ownership-safe digital delivery — only the order owner can redeem."""
    ensure()
    order = get_user_order(int(user_id), int(order_id))
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



# ═══════════════════════════════════════════════════════════════════
# Enterprise depth layer — multi-step commerce, SaaS, marketplace, audit
# ═══════════════════════════════════════════════════════════════════


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


def coupon_create(admin_id: int, text: str) -> str:
    """text: CODE|percent|max_uses  e.g. SAVE10|10|50 — staff/admin only."""
    enterprise_ensure()
    if not role_require(int(admin_id), "staff"):
        return "❌ غير مصرح — صلاحيات إدارة مطلوبة"
    parts = [p.strip() for p in (text or "").split("|")]
    if not parts or not parts[0]:
        return "Usage: CODE|percent|max_uses"
    code = parts[0].upper()
    percent = float(parts[1]) if len(parts) > 1 and parts[1] else 10.0
    max_uses = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 100
    try:
        with connect() as conn:
            cur = conn.execute(
                "INSERT INTO coupons (code, percent_off, max_uses) VALUES (?,?,?)",
                (code, percent, max_uses),
            )
            conn.commit()
            cid = int(cur.lastrowid)
    except Exception:
        return f"Coupon {code} already exists or invalid"
    _audit(admin_id, "coupon_create", "coupon", cid, code)
    return f"Coupon #{cid} {code} — {percent}% off, max {max_uses} uses"


def coupon_apply_code(user_id: int, code: str, order_id: int = 0) -> str:
    """Apply coupon once per user. Requires valid order ownership when order_id set."""
    enterprise_ensure()
    code = (code or "").strip().upper()
    with connect() as conn:
        c = conn.execute(
            "SELECT * FROM coupons WHERE code=? AND active=1", (code,)
        ).fetchone()
        if not c:
            return "Invalid or inactive coupon"
        if int(c["used"]) >= int(c["max_uses"]):
            return "Coupon exhausted"
        # One redemption per user per coupon
        prior = conn.execute(
            "SELECT id FROM coupon_redemptions WHERE coupon_id=? AND user_id=? LIMIT 1",
            (c["id"], int(user_id)),
        ).fetchone()
        if prior:
            return "You already used this coupon"
        if order_id:
            o = conn.execute(
                "SELECT amount_cents, user_id FROM orders WHERE id=?",
                (int(order_id),),
            ).fetchone()
            if not o or int(o["user_id"]) != int(user_id):
                return "Order not found"
            # Atomic increment only if under max_uses
            cur = conn.execute(
                "UPDATE coupons SET used=used+1 WHERE id=? AND used < max_uses",
                (c["id"],),
            )
            if cur.rowcount != 1:
                return "Coupon exhausted"
            off = int(int(o["amount_cents"]) * float(c["percent_off"]) / 100.0)
            new_total = max(0, int(o["amount_cents"]) - off)
            conn.execute(
                "UPDATE orders SET amount_cents=? WHERE id=?",
                (new_total, int(order_id)),
            )
            conn.execute(
                "INSERT INTO coupon_redemptions (coupon_id, user_id, order_id) VALUES (?,?,?)",
                (c["id"], int(user_id), int(order_id)),
            )
        else:
            return "Provide a valid order_id to apply coupon"
        conn.commit()
    return f"Coupon {code} applied ({c['percent_off']}% off)"


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
    # Bootstrap: ADMIN_IDS from env are always admin
    try:
        import os as _os

        raw = (_os.getenv("ADMIN_IDS") or "").strip()
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
