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


