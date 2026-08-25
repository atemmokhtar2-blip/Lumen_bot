def referral_code(user_id: int) -> str:
    ensure()
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS referrals (
                user_id INTEGER PRIMARY KEY,
                code TEXT NOT NULL UNIQUE,
                invited_by INTEGER NOT NULL DEFAULT 0,
                rewards INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.commit()
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


