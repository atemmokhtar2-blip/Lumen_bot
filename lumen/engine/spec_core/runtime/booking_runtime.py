"""Booking + clinic appointments — real slot conflict checks, not generic_kv.

Copied into generated bots as app/services/booking.py and/or clinic.py.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone

from app.db import connect, init_db

# Fixed demo slots (local wall-clock); production bots can override via admin seed.
_DEFAULT_SLOTS = ("10:00", "12:00", "14:00", "16:00", "18:00")


def ensure() -> None:
    init_db()
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL DEFAULT 0,
                slot_ts INTEGER NOT NULL DEFAULT 0,
                slot_label TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                kind TEXT NOT NULL DEFAULT 'booking',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS clinic_appts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL DEFAULT 0,
                slot_ts INTEGER NOT NULL DEFAULT 0,
                slot_label TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_bookings_slot ON bookings(slot_ts, status);
            CREATE INDEX IF NOT EXISTS idx_clinic_slot ON clinic_appts(slot_ts, status);
            """
        )
        for stmt in (
            "ALTER TABLE bookings ADD COLUMN slot_ts INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE bookings ADD COLUMN slot_label TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE bookings ADD COLUMN kind TEXT NOT NULL DEFAULT 'booking'",
            "ALTER TABLE clinic_appts ADD COLUMN slot_ts INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE clinic_appts ADD COLUMN slot_label TEXT NOT NULL DEFAULT ''",
        ):
            try:
                conn.execute(stmt)
            except Exception:
                pass
        # If still missing slot_ts (corrupt partial table), rebuild empty tables
        for table in ("bookings", "clinic_appts"):
            cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if cols and "slot_ts" not in cols:
                conn.execute(f"ALTER TABLE {table} RENAME TO {table}_legacy")
                # re-run create via executescript path: create fresh
                if table == "bookings":
                    conn.execute(
                        "CREATE TABLE IF NOT EXISTS bookings ("
                        "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
                        "chat_id INTEGER NOT NULL DEFAULT 0, slot_ts INTEGER NOT NULL DEFAULT 0, "
                        "slot_label TEXT NOT NULL DEFAULT '', body TEXT NOT NULL DEFAULT '', "
                        "status TEXT NOT NULL DEFAULT 'open', kind TEXT NOT NULL DEFAULT 'booking', "
                        "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
                    )
                else:
                    conn.execute(
                        "CREATE TABLE IF NOT EXISTS clinic_appts ("
                        "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
                        "chat_id INTEGER NOT NULL DEFAULT 0, slot_ts INTEGER NOT NULL DEFAULT 0, "
                        "slot_label TEXT NOT NULL DEFAULT '', body TEXT NOT NULL DEFAULT '', "
                        "status TEXT NOT NULL DEFAULT 'open', "
                        "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
                    )
        conn.commit()


def _parse_slot(text: str) -> tuple[str, int]:
    """Parse 'غداً 10:00' / '2026-08-27 14:30' → (label, unix_ts)."""
    raw = (text or "").strip()
    now = datetime.now().astimezone()
    # HH:MM
    m = re.search(r"\b(\d{1,2}):(\d{2})\b", raw)
    hh, mm = 10, 0
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
        hh = max(0, min(23, hh))
        mm = max(0, min(59, mm))
    day_offset = 1  # default tomorrow
    if re.search(r"اليوم|today", raw, re.I):
        day_offset = 0
    elif re.search(r"بعد\s*غد|day\s*after", raw, re.I):
        day_offset = 2
    elif re.search(r"غدا|tomorrow", raw, re.I):
        day_offset = 1
    target = (now + timedelta(days=day_offset)).replace(
        hour=hh, minute=mm, second=0, microsecond=0
    )
    if target.timestamp() <= now.timestamp():
        target = target + timedelta(days=1)
    label = target.strftime("%Y-%m-%d %H:%M")
    body = re.sub(r"\b(\d{1,2}):(\d{2})\b", "", raw)
    body = re.sub(r"غداً|غدا|اليوم|بعد غد|tomorrow|today|day after", "", body, flags=re.I)
    body = body.strip(" -–—,:،") or "موعد"
    return f"{label} — {body}", int(target.timestamp())


def available_slots(kind: str = "booking", days: int = 2) -> str:
    ensure()
    now = datetime.now().astimezone()
    lines = ["المواعيد المتاحة:"]
    table = "clinic_appts" if kind == "clinic" else "bookings"
    with connect() as conn:
        for d in range(0, max(1, days) + 1):
            day = (now + timedelta(days=d)).date()
            for hhmm in _DEFAULT_SLOTS:
                hh, mm = map(int, hhmm.split(":"))
                ts = int(
                    datetime(day.year, day.month, day.day, hh, mm, tzinfo=now.tzinfo).timestamp()
                )
                if ts <= time.time():
                    continue
                taken = conn.execute(
                    f"SELECT COUNT(*) c FROM {table} WHERE slot_ts=? AND status='open'",
                    (ts,),
                ).fetchone()["c"]
                mark = "❌ محجوز" if int(taken) else "✅ متاح"
                lines.append(f"• {day.isoformat()} {hhmm} — {mark}")
    lines.append("احجز: أرسل الوقت مع الوصف (مثال: غداً 10:00 كشف)")
    return "\n".join(lines)


def book_slot(user_id: int, text: str, chat_id: int = 0, *, kind: str = "booking") -> str:
    ensure()
    label, slot_ts = _parse_slot(text)
    table = "clinic_appts" if kind == "clinic" else "bookings"
    with connect() as conn:
        taken = conn.execute(
            f"SELECT id FROM {table} WHERE slot_ts=? AND status='open' LIMIT 1",
            (int(slot_ts),),
        ).fetchone()
        if taken:
            return f"❌ الموعد محجوز مسبقاً. اختر وقتاً آخر:\n{available_slots(kind)}"
        if kind == "clinic":
            cur = conn.execute(
                "INSERT INTO clinic_appts (user_id, chat_id, slot_ts, slot_label, body, status) "
                "VALUES (?,?,?,?,?,?)",
                (int(user_id), int(chat_id or user_id), int(slot_ts), label, label, "open"),
            )
        else:
            cur = conn.execute(
                "INSERT INTO bookings (user_id, chat_id, slot_ts, slot_label, body, status, kind) "
                "VALUES (?,?,?,?,?,?,?)",
                (int(user_id), int(chat_id or user_id), int(slot_ts), label, label, "open", kind),
            )
        conn.commit()
        return f"✅ تم الحجز #{int(cur.lastrowid)}\n{label}"


def cancel_slot(user_id: int, text: str, *, kind: str = "booking") -> str:
    ensure()
    try:
        aid = int((text or "").strip().split()[0])
    except (ValueError, IndexError):
        return "الاستخدام: /cancel <رقم_الموعد>"
    table = "clinic_appts" if kind == "clinic" else "bookings"
    with connect() as conn:
        cur = conn.execute(
            f"UPDATE {table} SET status='cancelled' WHERE id=? AND user_id=? AND status='open'",
            (aid, int(user_id)),
        )
        conn.commit()
        return "✅ تم إلغاء الموعد" if cur.rowcount else "❌ الموعد غير موجود أو ملغى"


def my_slots(user_id: int, *, kind: str = "booking") -> str:
    ensure()
    table = "clinic_appts" if kind == "clinic" else "bookings"
    with connect() as conn:
        rows = conn.execute(
            f"SELECT id, slot_label, body, status FROM {table} "
            f"WHERE user_id=? AND status='open' ORDER BY slot_ts ASC, id ASC",
            (int(user_id),),
        ).fetchall()
    if not rows:
        return "لا مواعيد مفتوحة"
    return "\n".join(f"#{r['id']} {r['slot_label'] or r['body']}" for r in rows)


# ── Public aliases matching existing handler method names ──
def book(user_id: int, text: str = "", chat_id: int = 0) -> str:
    return book_slot(user_id, text, chat_id, kind="booking")


def slots(user_id: int = 0, text: str = "") -> str:
    return available_slots("booking")


def cancel(user_id: int, text: str = "") -> str:
    return cancel_slot(user_id, text, kind="booking")


def my_appointments(user_id: int, text: str = "") -> str:
    return my_slots(user_id, kind="booking")


def act(entity: str, method: str, user_id: int, text: str = "") -> str:
    m = (method or "").lower()
    if m in {"book", "book_slot", "add", "create"}:
        kind = "clinic" if (entity or "").lower() == "clinic" else "booking"
        return book_slot(user_id, text, kind=kind)
    if m in {"slots", "list_slots"}:
        kind = "clinic" if (entity or "").lower() == "clinic" else "booking"
        return available_slots(kind)
    if m in {"cancel", "cancel_booking"}:
        kind = "clinic" if (entity or "").lower() == "clinic" else "booking"
        return cancel_slot(user_id, text, kind=kind)
    if m in {"my_appointments", "my", "list", "list_bookings"}:
        kind = "clinic" if (entity or "").lower() == "clinic" else "booking"
        return my_slots(user_id, kind=kind)
    return f"{method} is not available in this bot build"


# Clinic-facing wrappers (same runtime, kind=clinic)
def clinic_book(user_id: int, text: str = "", chat_id: int = 0) -> str:
    return book_slot(user_id, text, chat_id, kind="clinic")


def clinic_slots(user_id: int = 0, text: str = "") -> str:
    return available_slots("clinic")


def clinic_cancel(user_id: int, text: str = "") -> str:
    return cancel_slot(user_id, text, kind="clinic")


def clinic_my(user_id: int, text: str = "") -> str:
    return my_slots(user_id, kind="clinic")
