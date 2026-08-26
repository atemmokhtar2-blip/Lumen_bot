"""Emit reminders + booking + clinic — booking/clinic from deep runtime."""
from __future__ import annotations

from pathlib import Path

from ..schema import BotSpec


def _booking_source() -> str:
    path = Path(__file__).resolve().parents[1] / "runtime" / "booking_runtime.py"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"booking_runtime missing: {path}")


def _emit_booking_service() -> str:
    return _booking_source()


def _emit_clinic_service() -> str:
    """Clinic uses same runtime with kind=clinic wrappers exposed at module level."""
    src = _booking_source()
    # Alias primary names so existing handlers calling clinic.book/slots work
    aliases = """

# ── Handler-compatible clinic module surface ──────────────────────────
book = clinic_book
slots = clinic_slots
cancel = clinic_cancel
my_appointments = clinic_my
"""
    return src + aliases


def _emit_reminders_service() -> str:
    """Keep working reminders emitter (time parse + due_ts) — not generic_kv."""
    return (
        '"""Reminders service — parse relative times, list due, mark fired."""\n'
        "from __future__ import annotations\n\n"
        "import re\n"
        "import time\n"
        "from datetime import datetime, timedelta, timezone\n\n"
        "from app.db import connect, init_db\n\n\n"
        "def ensure() -> None:\n"
        "    init_db()\n"
        "    with connect() as conn:\n"
        "        conn.execute(\n"
        "            'CREATE TABLE IF NOT EXISTS reminders ('\n"
        "            'id INTEGER PRIMARY KEY AUTOINCREMENT, '\n"
        "            'user_id INTEGER NOT NULL, '\n"
        "            'chat_id INTEGER NOT NULL DEFAULT 0, '\n"
        "            'body TEXT NOT NULL, '\n"
        "            'due_ts INTEGER NOT NULL, '\n"
        "            'fired INTEGER NOT NULL DEFAULT 0, '\n"
        "            'created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)'\n"
        "        )\n"
        "        conn.commit()\n\n\n"
        "def _parse_due(text: str):\n"
        "    raw = (text or '').strip()\n"
        "    now = int(time.time())\n"
        "    due = now + 3600\n"
        "    body = raw\n"
        "    m = re.search(\n"
        "        r'(?:بعد|in)\\s+(\\d+)\\s*(دقيقة|دقائق|minute|minutes|m|ساعة|ساعات|hour|hours|h|يوم|أيام|day|days|d)?',\n"
        "        raw, re.I,\n"
        "    )\n"
        "    if m:\n"
        "        n = int(m.group(1))\n"
        "        unit = (m.group(2) or 'm').lower()\n"
        "        if unit in {'دقيقة', 'دقائق', 'minute', 'minutes', 'm'}:\n"
        "            due = now + n * 60\n"
        "        elif unit in {'ساعة', 'ساعات', 'hour', 'hours', 'h'}:\n"
        "            due = now + n * 3600\n"
        "        else:\n"
        "            due = now + n * 86400\n"
        "        body = (raw[: m.start()] + raw[m.end():]).strip(' -–—,:،') or raw\n"
        "    m2 = re.search(r'\\b(\\d{1,2}):(\\d{2})\\s*(am|pm)?\\b', raw, re.I)\n"
        "    if m2:\n"
        "        hh, mm = int(m2.group(1)), int(m2.group(2))\n"
        "        ap = (m2.group(3) or '').lower()\n"
        "        if ap == 'pm' and hh < 12:\n"
        "            hh += 12\n"
        "        if ap == 'am' and hh == 12:\n"
        "            hh = 0\n"
        "        dt = datetime.now(timezone.utc).astimezone()\n"
        "        target = dt.replace(hour=min(hh, 23), minute=min(mm, 59), second=0, microsecond=0)\n"
        "        if target.timestamp() <= dt.timestamp():\n"
        "            target = target + timedelta(days=1)\n"
        "        due = int(target.timestamp())\n"
        "        body = (raw[: m2.start()] + raw[m2.end():]).strip(' -–—,:،') or raw\n"
        "    if not body:\n"
        "        body = raw or 'تذكير'\n"
        "    return body[:500], due\n\n\n"
        "def set_reminder(user_id: int, text: str, chat_id: int = 0) -> int:\n"
        "    ensure()\n"
        "    body, due_ts = _parse_due(text)\n"
        "    with connect() as conn:\n"
        "        cur = conn.execute(\n"
        "            'INSERT INTO reminders (user_id, chat_id, body, due_ts, fired) VALUES (?, ?, ?, ?, 0)',\n"
        "            (int(user_id), int(chat_id or user_id), body, int(due_ts)),\n"
        "        )\n"
        "        conn.commit()\n"
        "        return int(cur.lastrowid)\n\n\n"
        "def list_reminders(user_id: int) -> list:\n"
        "    ensure()\n"
        "    with connect() as conn:\n"
        "        rows = conn.execute(\n"
        "            'SELECT id, body, due_ts, fired FROM reminders '\n"
        "            'WHERE user_id = ? AND fired = 0 ORDER BY due_ts ASC, id ASC',\n"
        "            (int(user_id),),\n"
        "        ).fetchall()\n"
        "    out = []\n"
        "    for r in rows:\n"
        "        d = dict(r)\n"
        "        due = int(d.get('due_ts') or 0)\n"
        "        d['remain_min'] = max(0, due - int(time.time())) // 60\n"
        "        out.append(d)\n"
        "    return out\n\n\n"
        "def clear_reminders(user_id: int) -> int:\n"
        "    ensure()\n"
        "    with connect() as conn:\n"
        "        cur = conn.execute(\n"
        "            'UPDATE reminders SET fired = 1 WHERE user_id = ? AND fired = 0',\n"
        "            (int(user_id),),\n"
        "        )\n"
        "        conn.commit()\n"
        "        return int(cur.rowcount)\n\n\n"
        "def list_due_reminders(now_ts=None, limit: int = 50):\n"
        "    ensure()\n"
        "    now = int(now_ts or time.time())\n"
        "    with connect() as conn:\n"
        "        rows = conn.execute(\n"
        "            'SELECT id, user_id, chat_id, body, due_ts FROM reminders '\n"
        "            'WHERE fired = 0 AND due_ts <= ? ORDER BY due_ts ASC LIMIT ?',\n"
        "            (now, int(limit)),\n"
        "        ).fetchall()\n"
        "    return [dict(r) for r in rows]\n\n\n"
        "def mark_reminder_fired(reminder_id: int) -> bool:\n"
        "    ensure()\n"
        "    with connect() as conn:\n"
        "        cur = conn.execute(\n"
        "            'UPDATE reminders SET fired = 1 WHERE id = ? AND fired = 0',\n"
        "            (int(reminder_id),),\n"
        "        )\n"
        "        conn.commit()\n"
        "        return cur.rowcount > 0\n\n\n"
        "def format_reminders(items) -> str:\n"
        "    if not items:\n"
        "        return 'لا تذكيرات'\n"
        "    return '\\n'.join(\n"
        "        f\"#{i['id']} بعد {i.get('remain_min', '?')} د — {i.get('body', '')}\" for i in items\n"
        "    )\n"
    )
