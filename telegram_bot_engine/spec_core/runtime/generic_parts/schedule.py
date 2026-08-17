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



