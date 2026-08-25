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
        try:
            rows = conn.execute(
                "SELECT amount AS amt, note, created_at FROM wallet_ledger WHERE user_id=? "
                "ORDER BY id DESC LIMIT ?",
                (user_id, int(limit)),
            ).fetchall()
        except Exception:
            rows = conn.execute(
                "SELECT delta AS amt, note, created_at FROM wallet_ledger WHERE user_id=? "
                "ORDER BY id DESC LIMIT ?",
                (user_id, int(limit)),
            ).fetchall()
    if not rows:
        return f"الرصيد: {bal}\nلا حركات بعد."
    lines = [f"الرصيد: {bal}", "آخر الحركات:"]
    for r in rows:
        lines.append(f"• {r['created_at']}: {r['amt']} — {r['note'] or ''}")
    return "\n".join(lines)


