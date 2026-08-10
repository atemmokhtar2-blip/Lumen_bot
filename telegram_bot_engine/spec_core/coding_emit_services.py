"""Emit service modules (moderation, tasks, notes, tickets, security, extras, content, welcome)."""
from __future__ import annotations

from .schema import BotSpec

def _emit_moderation() -> str:
    return '''"""Moderation service — Telegram admin APIs."""
from __future__ import annotations

from telegram import ChatPermissions
from telegram.ext import ContextTypes


async def ban_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> None:
    await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)


async def unban_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> None:
    await context.bot.unban_chat_member(chat_id=chat_id, user_id=user_id)


async def mute_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> None:
    perms = ChatPermissions(can_send_messages=False)
    await context.bot.restrict_chat_member(chat_id=chat_id, user_id=user_id, permissions=perms)


async def unmute_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> None:
    perms = ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
    )
    await context.bot.restrict_chat_member(chat_id=chat_id, user_id=user_id, permissions=perms)


async def kick_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> None:
    await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
    await context.bot.unban_chat_member(chat_id=chat_id, user_id=user_id)


async def warn_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> str:
    return f"warned:{user_id}"


async def promote_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> None:
    await context.bot.promote_chat_member(
        chat_id=chat_id,
        user_id=user_id,
        can_manage_chat=True,
        can_delete_messages=True,
        can_restrict_members=True,
        can_invite_users=True,
        can_pin_messages=True,
        can_promote_members=False,
        can_change_info=False,
        can_manage_video_chats=False,
    )


async def demote_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> None:
    await context.bot.promote_chat_member(
        chat_id=chat_id,
        user_id=user_id,
        can_manage_chat=False,
        can_delete_messages=False,
        can_restrict_members=False,
        can_invite_users=False,
        can_pin_messages=False,
        can_promote_members=False,
        can_change_info=False,
        can_manage_video_chats=False,
    )


async def pin_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int) -> None:
    await context.bot.pin_chat_message(chat_id=chat_id, message_id=message_id)


async def delete_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int) -> None:
    await context.bot.delete_message(chat_id=chat_id, message_id=message_id)


async def lock_chat(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    perms = ChatPermissions(can_send_messages=False)
    await context.bot.set_chat_permissions(chat_id=chat_id, permissions=perms)


async def unlock_chat(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    perms = ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
    )
    await context.bot.set_chat_permissions(chat_id=chat_id, permissions=perms)
'''


def _emit_tasks() -> str:
    return '''"""Tasks service — sqlite-backed personal tasks."""
from __future__ import annotations

from app.db import connect, init_db


def ensure() -> None:
    init_db()


def add_task(user_id: int, title: str, description: str = "", priority: str = "medium") -> int:
    ensure()
    priority = priority if priority in {"high", "medium", "low"} else "medium"
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO tasks (user_id, title, description, priority, done) VALUES (?, ?, ?, ?, 0)",
            (user_id, title, description, priority),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_tasks(user_id: int, only_open: bool = True) -> list[dict]:
    ensure()
    q = "SELECT id, title, description, priority, done FROM tasks WHERE user_id = ?"
    if only_open:
        q += " AND done = 0"
    q += " ORDER BY id DESC"
    with connect() as conn:
        rows = conn.execute(q, (user_id,)).fetchall()
    return [dict(r) for r in rows]


def done_task(user_id: int, task_id: int) -> bool:
    ensure()
    with connect() as conn:
        cur = conn.execute(
            "UPDATE tasks SET done = 1 WHERE id = ? AND user_id = ?",
            (task_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0


def delete_task(user_id: int, task_id: int) -> bool:
    ensure()
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM tasks WHERE id = ? AND user_id = ?",
            (task_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0


def clear_tasks(user_id: int) -> int:
    ensure()
    with connect() as conn:
        cur = conn.execute("DELETE FROM tasks WHERE user_id = ? AND done = 1", (user_id,))
        conn.commit()
        return int(cur.rowcount)
'''



def _emit_notes() -> str:
    return '''"""Notes service — personal notes in sqlite."""
from __future__ import annotations

from app.db import connect, init_db


def ensure() -> None:
    init_db()


def add_note(user_id: int, body: str) -> int:
    ensure()
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO notes (user_id, body) VALUES (?, ?)",
            (user_id, body),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_notes(user_id: int) -> list[dict]:
    ensure()
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, body FROM notes WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_note(user_id: int, note_id: int) -> bool:
    ensure()
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM notes WHERE id = ? AND user_id = ?",
            (note_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0
'''



def _emit_content(spec: BotSpec) -> str:
    rules = "التزم بالاحترام. ممنوع السبام والإعلانات." if (spec.bot.language or "ar").startswith("ar") else "Be respectful. No spam."
    about = spec.bot.description or spec.bot.name
    return (
        '"""Static content helpers."""\n'
        "from __future__ import annotations\n\n"
        f"RULES_TEXT = {rules!r}\n"
        f"ABOUT_TEXT = {about!r}\n\n"
        "def rules() -> str:\n"
        "    return RULES_TEXT\n\n"
        "def about() -> str:\n"
        "    return ABOUT_TEXT\n\n"
        "def faq() -> str:\n"
        "    return (\n"
        '        "الأسئلة الشائعة:\\n"\n'
        '        "- /start للبداية\\n"\n'
        '        "- /help للأوامر\\n"\n'
        '        "- للمساعدة تواصل مع المشرف"\n'
        "    )\n"
    )



def _emit_welcome() -> str:
    return (
        '"""Welcome service — per-chat auto-welcome for new members."""\n'
        "from __future__ import annotations\n\n"
        "from app.db import connect, init_db\n\n"
        'DEFAULT_MESSAGE = "أهلاً {name} 👋 نورت المجموعة!"\n\n'
        "def ensure() -> None:\n"
        "    init_db()\n\n"
        "def set_message(chat_id: int, message: str) -> None:\n"
        "    ensure()\n"
        "    with connect() as conn:\n"
        "        conn.execute(\n"
        '            """\n'
        "            INSERT INTO welcome_settings (chat_id, enabled, message) VALUES (?, 1, ?)\n"
        "            ON CONFLICT(chat_id) DO UPDATE SET message = excluded.message, enabled = 1\n"
        '            """,\n'
        "            (chat_id, message),\n"
        "        )\n"
        "        conn.commit()\n\n"
        "def toggle(chat_id: int) -> bool:\n"
        "    ensure()\n"
        "    with connect() as conn:\n"
        "        row = conn.execute(\n"
        '            "SELECT enabled FROM welcome_settings WHERE chat_id = ?", (chat_id,)\n'
        "        ).fetchone()\n"
        "        if row is None:\n"
        "            conn.execute(\n"
        '                "INSERT INTO welcome_settings (chat_id, enabled, message) VALUES (?, 1, ?)",\n'
        "                (chat_id, DEFAULT_MESSAGE),\n"
        "            )\n"
        "            conn.commit()\n"
        "            return True\n"
        "        new_val = 0 if int(row['enabled']) else 1\n"
        "        conn.execute(\n"
        '            "UPDATE welcome_settings SET enabled = ? WHERE chat_id = ?",\n'
        "            (new_val, chat_id),\n"
        "        )\n"
        "        conn.commit()\n"
        "        return bool(new_val)\n\n"
        "def get_settings(chat_id: int) -> dict:\n"
        "    ensure()\n"
        "    with connect() as conn:\n"
        "        row = conn.execute(\n"
        '            "SELECT enabled, message FROM welcome_settings WHERE chat_id = ?",\n'
        "            (chat_id,),\n"
        "        ).fetchone()\n"
        "    if row is None:\n"
        '        return {"enabled": True, "message": DEFAULT_MESSAGE}\n'
        "    return {\n"
        "        'enabled': bool(int(row['enabled'])),\n"
        "        'message': row['message'] or DEFAULT_MESSAGE,\n"
        "    }\n\n"
        "def format_welcome(chat_id: int, name: str) -> str | None:\n"
        "    cfg = get_settings(chat_id)\n"
        "    if not cfg['enabled']:\n"
        "        return None\n"
        "    msg = cfg['message'] or DEFAULT_MESSAGE\n"
        "    return msg.replace('{name}', name).replace('{NAME}', name)\n"
    )


def _emit_tickets() -> str:
    return (
        '"""Support tickets service — open/close/list/reply with sqlite."""\n'
        "from __future__ import annotations\n\n"
        "from app.db import connect, init_db\n\n"
        "def ensure() -> None:\n"
        "    init_db()\n\n"
        "def open_ticket(user_id: int, subject: str, chat_id: int = 0) -> int:\n"
        "    ensure()\n"
        '    subject = (subject or "").strip() or "بدون عنوان"\n'
        "    with connect() as conn:\n"
        "        cur = conn.execute(\n"
        '            "INSERT INTO tickets (user_id, chat_id, subject, status) VALUES (?, ?, ?, \'open\')",\n'
        "            (user_id, chat_id, subject[:200]),\n"
        "        )\n"
        "        tid = int(cur.lastrowid)\n"
        "        conn.execute(\n"
        '            "INSERT INTO ticket_messages (ticket_id, user_id, is_staff, body) VALUES (?, ?, 0, ?)",\n'
        "            (tid, user_id, subject),\n"
        "        )\n"
        "        conn.commit()\n"
        "        return tid\n\n"
        "def close_ticket(ticket_id: int, user_id: int | None = None, staff: bool = False) -> bool:\n"
        "    ensure()\n"
        "    with connect() as conn:\n"
        '        row = conn.execute("SELECT user_id, status FROM tickets WHERE id = ?", (ticket_id,)).fetchone()\n'
        "        if row is None:\n"
        "            return False\n"
        "        if not staff and user_id is not None and int(row['user_id']) != int(user_id):\n"
        "            return False\n"
        "        if row['status'] == 'closed':\n"
        "            return True\n"
        '        conn.execute("UPDATE tickets SET status = \'closed\' WHERE id = ?", (ticket_id,))\n'
        "        conn.commit()\n"
        "        return True\n\n"
        "def list_tickets(user_id: int | None = None, only_open: bool = True, limit: int = 20) -> list[dict]:\n"
        "    ensure()\n"
        '    q = "SELECT id, user_id, subject, status, created_at FROM tickets WHERE 1=1"\n'
        "    params: list = []\n"
        "    if user_id is not None:\n"
        '        q += " AND user_id = ?"\n'
        "        params.append(user_id)\n"
        "    if only_open:\n"
        '        q += " AND status = \'open\'"\n'
        '    q += " ORDER BY id DESC LIMIT ?"\n'
        "    params.append(limit)\n"
        "    with connect() as conn:\n"
        "        rows = conn.execute(q, params).fetchall()\n"
        "    return [dict(r) for r in rows]\n\n"
        "def my_tickets(user_id: int) -> list[dict]:\n"
        "    return list_tickets(user_id=user_id, only_open=True)\n\n"
        "def reply_ticket(ticket_id: int, user_id: int, body: str, staff: bool = False) -> bool:\n"
        "    ensure()\n"
        '    body = (body or "").strip()\n'
        "    if not body:\n"
        "        return False\n"
        "    with connect() as conn:\n"
        '        row = conn.execute("SELECT id, status FROM tickets WHERE id = ?", (ticket_id,)).fetchone()\n'
        "        if row is None or row['status'] == 'closed':\n"
        "            return False\n"
        "        conn.execute(\n"
        '            "INSERT INTO ticket_messages (ticket_id, user_id, is_staff, body) VALUES (?, ?, ?, ?)",\n'
        "            (ticket_id, user_id, 1 if staff else 0, body),\n"
        "        )\n"
        "        conn.commit()\n"
        "        return True\n\n"
        "def ticket_status(ticket_id: int) -> dict | None:\n"
        "    ensure()\n"
        "    with connect() as conn:\n"
        "        row = conn.execute(\n"
        '            "SELECT id, user_id, subject, status, created_at FROM tickets WHERE id = ?",\n'
        "            (ticket_id,),\n"
        "        ).fetchone()\n"
        "        if row is None:\n"
        "            return None\n"
        "        msgs = conn.execute(\n"
        '            "SELECT user_id, is_staff, body, created_at FROM ticket_messages WHERE ticket_id = ? ORDER BY id ASC LIMIT 10",\n'
        "            (ticket_id,),\n"
        "        ).fetchall()\n"
        "    data = dict(row)\n"
        "    data['messages'] = [dict(m) for m in msgs]\n"
        "    return data\n"
    )



def _emit_security() -> str:
    return (
        '"""Defensive security ops — reports, awareness, and passive domain checks.\n'
        "\n"
        "No offensive / exploit tooling. Network helpers use stdlib only.\n"
        '"""\n'
        "from __future__ import annotations\n\n"
        "import re\n"
        "import socket\n"
        "import ssl\n"
        "from urllib.parse import urlparse\n"
        "from urllib.request import Request, urlopen\n\n"
        "from app.db import connect, init_db\n\n"
        "CHECKLIST = (\n"
        '    "1) لا تشارك كلمات المرور أو رموز التحقق\\n"\n'
        '    "2) راجع الروابط قبل الفتح\\n"\n'
        '    "3) فعّل التحقق بخطوتين\\n"\n'
        '    "4) بلّغ فورًا عن أي رسالة مشبوهة\\n"\n'
        '    "5) حدّث التطبيقات باستمرار"\n'
        ")\n\n"
        "TIPS = (\n"
        '    "• استخدم كلمات مرور فريدة لكل خدمة\\n"\n'
        '    "• فعّل 2FA / مفاتيح المرور\\n"\n'
        '    "• لا تفتح مرفقات غير متوقعة\\n"\n'
        '    "• راجع صلاحيات التطبيقات دوريًا"\n'
        ")\n\n"
        "PASSWORD_TIPS = (\n"
        '    "• 12+ حرف مع تنوع (أحرف/أرقام/رموز)\\n"\n'
        '    "• لا تعِد استخدام نفس كلمة المرور\\n"\n'
        '    "• مدير كلمات مرور موثوق أفضل من الذاكرة\\n"\n'
        '    "• غيّر فوريًا بعد أي تسريب معروف"\n'
        ")\n\n"
        "_HOST_RE = re.compile(r\"^[a-zA-Z0-9](?:[a-zA-Z0-9\\-\\.]{0,251}[a-zA-Z0-9])?$\")\n\n"
        "def ensure() -> None:\n"
        "    init_db()\n\n"
        "def _clean_host(raw: str) -> str:\n"
        "    t = (raw or '').strip().lower()\n"
        "    if '://' in t:\n"
        "        t = urlparse(t).hostname or t\n"
        "    t = t.split('/')[0].split('?')[0].strip().strip('.')\n"
        "    if t.startswith('www.'):\n"
        "        t = t[4:]\n"
        "    if not t or not _HOST_RE.match(t) or len(t) > 253:\n"
        "        return ''\n"
        "    return t\n\n"
        "def report(user_id: int, kind: str, body: str) -> int:\n"
        "    ensure()\n"
        '    kind = (kind or "incident").strip()[:40]\n'
        '    body = (body or "").strip() or "—"\n'
        "    with connect() as conn:\n"
        "        cur = conn.execute(\n"
        '            "INSERT INTO security_reports (user_id, kind, body, status) VALUES (?, ?, ?, \'open\')",\n'
        "            (user_id, kind, body[:2000]),\n"
        "        )\n"
        "        conn.commit()\n"
        "        return int(cur.lastrowid)\n\n"
        "def list_reports(only_open: bool = True, limit: int = 20) -> list[dict]:\n"
        "    ensure()\n"
        '    q = "SELECT id, user_id, kind, body, status, created_at FROM security_reports"\n'
        "    if only_open:\n"
        "        q += \" WHERE status = 'open'\"\n"
        "    q += \" ORDER BY id DESC LIMIT ?\"\n"
        "    with connect() as conn:\n"
        "        rows = conn.execute(q, (limit,)).fetchall()\n"
        "    return [dict(r) for r in rows]\n\n"
        "def close_report(report_id: int) -> bool:\n"
        "    ensure()\n"
        "    with connect() as conn:\n"
        '        cur = conn.execute("UPDATE security_reports SET status = \'closed\' WHERE id = ?", (report_id,))\n'
        "        conn.commit()\n"
        "        return cur.rowcount > 0\n\n"
        "def checklist() -> str:\n"
        "    return CHECKLIST\n\n"
        "def tips() -> str:\n"
        "    return TIPS\n\n"
        "def password_tips() -> str:\n"
        "    return PASSWORD_TIPS\n\n"
        "def dns_check(host: str) -> str:\n"
        "    h = _clean_host(host)\n"
        "    if not h:\n"
        "        return 'أدخل نطاقًا صالحًا: /dns example.com'\n"
        "    lines = [f'DNS overview — {h}']\n"
        "    try:\n"
        "        infos = socket.getaddrinfo(h, None)\n"
        "        seen: set[str] = set()\n"
        "        for info in infos:\n"
        "            ip = info[4][0]\n"
        "            if ip in seen:\n"
        "                continue\n"
        "            seen.add(ip)\n"
        "            fam = 'AAAA' if ':' in ip else 'A'\n"
        "            lines.append(f'  {fam}: {ip}')\n"
        "            if len(seen) >= 8:\n"
        "                break\n"
        "        if not seen:\n"
        "            lines.append('  (no A/AAAA resolved)')\n"
        "    except socket.gaierror as exc:\n"
        "        lines.append(f'  resolve error: {exc}')\n"
        "    except Exception as exc:\n"
        "        lines.append(f'  error: {exc}')\n"
        "    lines.append('Note: passive lookup only (stdlib).')\n"
        "    return '\\n'.join(lines)\n\n"
        "def mx_check(host: str) -> str:\n"
        "    # Stdlib cannot query MX RRset without dnspython; give honest guidance + A lookup.\n"
        "    h = _clean_host(host)\n"
        "    if not h:\n"
        "        return 'أدخل نطاقًا صالحًا: /mx example.com'\n"
        "    base = dns_check(h)\n"
        "    return (\n"
        "        base + '\\n\\nMX tip: use dig/nslookup for MX/SPF/DMARC records. '\n"
        "        'This bot does passive A/AAAA only (no external DNS libs).'\n"
        "    )\n\n"
        "def tls_check(host: str) -> str:\n"
        "    h = _clean_host(host)\n"
        "    if not h:\n"
        "        return 'أدخل نطاقًا صالحًا: /tls example.com'\n"
        "    try:\n"
        "        ctx = ssl.create_default_context()\n"
        "        with socket.create_connection((h, 443), timeout=8) as sock:\n"
        "            with ctx.wrap_socket(sock, server_hostname=h) as ssock:\n"
        "                cert = ssock.getpeercert()\n"
        "                ver = ssock.version()\n"
        "        subject = dict(x[0] for x in (cert or {}).get('subject', ()) )\n"
        "        issuer = dict(x[0] for x in (cert or {}).get('issuer', ()) )\n"
        "        not_after = (cert or {}).get('notAfter', '?')\n"
        "        cn = subject.get('commonName') or subject.get('organizationName') or '?'\n"
        "        iss = issuer.get('commonName') or issuer.get('organizationName') or '?'\n"
        "        return (\n"
        "            f'TLS overview — {h}\\n'\n"
        "            f'  protocol: {ver}\\n'\n"
        "            f'  subject CN: {cn}\\n'\n"
        "            f'  issuer: {iss}\\n'\n"
        "            f'  notAfter: {not_after}\\n'\n"
        "            'Passive certificate read only.'\n"
        "        )\n"
        "    except Exception as exc:\n"
        "        return f'TLS check failed for {h}: {exc}'\n\n"
        "def http_check(host: str) -> str:\n"
        "    h = _clean_host(host)\n"
        "    if not h:\n"
        "        return 'أدخل نطاقًا صالحًا: /httpstatus example.com'\n"
        "    url = f'https://{h}/'\n"
        "    try:\n"
        "        req = Request(url, method='GET', headers={'User-Agent': 'SecBot/1.0'})\n"
        "        with urlopen(req, timeout=8) as resp:  # noqa: S310 — host validated\n"
        "            code = getattr(resp, 'status', None) or resp.getcode()\n"
        "            return f'HTTP {code} — {url}'\n"
        "    except Exception as exc:\n"
        "        return f'HTTP probe failed for {h}: {exc}'\n\n"
        "def headers_check(host: str) -> str:\n"
        "    h = _clean_host(host)\n"
        "    if not h:\n"
        "        return 'أدخل نطاقًا صالحًا: /headers example.com'\n"
        "    url = f'https://{h}/'\n"
        "    interesting = (\n"
        "        'strict-transport-security', 'content-security-policy',\n"
        "        'x-frame-options', 'x-content-type-options', 'referrer-policy',\n"
        "        'permissions-policy', 'server',\n"
        "    )\n"
        "    try:\n"
        "        req = Request(url, method='GET', headers={'User-Agent': 'SecBot/1.0'})\n"
        "        with urlopen(req, timeout=8) as resp:  # noqa: S310\n"
        "            hdrs = {k.lower(): v for k, v in resp.headers.items()}\n"
        "        lines = [f'Security headers — {h}']\n"
        "        for key in interesting:\n"
        "            val = hdrs.get(key)\n"
        "            lines.append(f'  {key}: {val if val else \"(missing)\"}')\n"
        "        return '\\n'.join(lines)\n"
        "    except Exception as exc:\n"
        "        return f'Headers probe failed for {h}: {exc}'\n\n"
        "def domain_overview(host: str) -> str:\n"
        "    h = _clean_host(host)\n"
        "    if not h:\n"
        "        return 'أدخل نطاقًا صالحًا: /domainscan example.com'\n"
        "    parts = [\n"
        "        dns_check(h),\n"
        "        '',\n"
        "        tls_check(h),\n"
        "        '',\n"
        "        http_check(h),\n"
        "        '',\n"
        "        headers_check(h),\n"
        "    ]\n"
        "    return '\\n'.join(parts)\n"
    )



def _emit_extras() -> str:
    """Shared lightweight services: shop/booking/crm/reminders/community/edu/hr/utils/gate."""
    return (
        '"""Market extras — lightweight product modules (deterministic)."""\n'
        "from __future__ import annotations\n\n"
        "import random\n"
        "from datetime import datetime, timezone\n"
        "from app.db import connect, init_db\n\n"
        "def ensure() -> None:\n"
        "    init_db()\n\n"
        "def _add(user_id: int, kind: str, body: str, status: str = 'open') -> int:\n"
        "    ensure()\n"
        "    with connect() as conn:\n"
        "        cur = conn.execute(\n"
        '            "INSERT INTO extras_kv (user_id, kind, body, status) VALUES (?, ?, ?, ?)",\n'
        "            (user_id, kind, body[:2000], status),\n"
        "        )\n"
        "        conn.commit()\n"
        "        return int(cur.lastrowid)\n\n"
        "def _list(kind: str, user_id: int | None = None, only_open: bool = False, limit: int = 30) -> list[dict]:\n"
        "    ensure()\n"
        '    q = "SELECT id, user_id, kind, body, status, created_at FROM extras_kv WHERE kind = ?"\n'
        "    params: list = [kind]\n"
        "    if user_id is not None:\n"
        '        q += " AND user_id = ?"\n'
        "        params.append(user_id)\n"
        "    if only_open:\n"
        '        q += " AND status = \'open\'"\n'
        '    q += " ORDER BY id DESC LIMIT ?"\n'
        "    params.append(limit)\n"
        "    with connect() as conn:\n"
        "        return [dict(r) for r in conn.execute(q, params).fetchall()]\n\n"
        "def _close(item_id: int, kind: str | None = None) -> bool:\n"
        "    ensure()\n"
        "    with connect() as conn:\n"
        "        if kind:\n"
        '            cur = conn.execute("UPDATE extras_kv SET status = \'closed\' WHERE id = ? AND kind = ?", (item_id, kind))\n'
        "        else:\n"
        '            cur = conn.execute("UPDATE extras_kv SET status = \'closed\' WHERE id = ?", (item_id,))\n'
        "        conn.commit()\n"
        "        return cur.rowcount > 0\n\n"
        "# shop\n"
        "def catalog() -> str:\n"
        "    items = _list('product')\n"
        "    if not items:\n"
        "        return 'لا منتجات بعد'\n"
        "    return '\\n'.join(f\"#{i['id']} {i['body']}\" for i in items)\n\n"
        "def add_item(admin_id: int, title: str) -> int:\n"
        "    return _add(admin_id, 'product', title, 'open')\n\n"
        "def place_order(user_id: int, text: str) -> int:\n"
        "    return _add(user_id, 'order', text)\n\n"
        "def list_orders() -> list[dict]:\n"
        "    return _list('order', only_open=True)\n\n"
        "# booking\n"
        "def book_slot(user_id: int, slot: str) -> int:\n"
        "    return _add(user_id, 'booking', slot)\n\n"
        "def list_bookings(user_id: int) -> list[dict]:\n"
        "    return _list('booking', user_id=user_id, only_open=True)\n\n"
        "def cancel_booking(user_id: int, item_id: int) -> bool:\n"
        "    ensure()\n"
        "    with connect() as conn:\n"
        '        cur = conn.execute("UPDATE extras_kv SET status = \'closed\' WHERE id = ? AND user_id = ? AND kind = \'booking\'", (item_id, user_id))\n'
        "        conn.commit()\n"
        "        return cur.rowcount > 0\n\n"
        "def admin_list_bookings() -> list[dict]:\n"
        "    return _list('booking', only_open=True)\n\n"
        "# crm\n"
        "def lead_capture(user_id: int, text: str) -> int:\n"
        "    return _add(user_id, 'lead', text)\n\n"
        "def lead_list() -> list[dict]:\n"
        "    return _list('lead', only_open=True)\n\n"
        "# reminders\n"
        "def set_reminder(user_id: int, text: str) -> int:\n"
        "    return _add(user_id, 'reminder', text)\n\n"
        "def list_reminders(user_id: int) -> list[dict]:\n"
        "    return _list('reminder', user_id=user_id, only_open=True)\n\n"
        "def clear_reminders(user_id: int) -> int:\n"
        "    ensure()\n"
        "    with connect() as conn:\n"
        '        cur = conn.execute("UPDATE extras_kv SET status = \'closed\' WHERE user_id = ? AND kind = \'reminder\' AND status = \'open\'", (user_id,))\n'
        "        conn.commit()\n"
        "        return int(cur.rowcount)\n\n"
        "# community\n"
        "def feedback(user_id: int, text: str) -> int:\n"
        "    return _add(user_id, 'feedback', text)\n\n"
        "def suggest(user_id: int, text: str) -> int:\n"
        "    return _add(user_id, 'suggest', text)\n\n"
        "def report_user(user_id: int, text: str) -> int:\n"
        "    return _add(user_id, 'user_report', text)\n\n"
        "def poll_create(admin_id: int, text: str) -> int:\n"
        "    return _add(admin_id, 'poll', text)\n\n"
        "# edu / hr\n"
        "def course_list() -> str:\n"
        "    items = _list('course')\n"
        "    return '\\n'.join(f\"#{i['id']} {i['body']}\" for i in items) if items else 'لا دورات'\n\n"
        "def enroll(user_id: int, text: str) -> int:\n"
        "    return _add(user_id, 'enroll', text)\n\n"
        "def quiz_start() -> str:\n"
        "    return 'اختبار سريع: ما أقوى ممارسة أمنية؟ أ) مشاركة كلمة المرور ب) 2FA — اكتب إجابتك كرسالة'\n\n"
        "def leave_request(user_id: int, text: str) -> int:\n"
        "    return _add(user_id, 'leave', text)\n\n"
        "def leave_list() -> list[dict]:\n"
        "    return _list('leave', only_open=True)\n\n"
        "def checkin(user_id: int) -> int:\n"
        "    return _add(user_id, 'checkin', datetime.now(timezone.utc).isoformat())\n\n"
        "# gate / utils\n"
        "def verify_start() -> str:\n"
        "    return 'للتحقق أرسل: أنا لست روبوت'\n\n"
        "def verify_ok(text: str) -> bool:\n"
        "    return 'لست روبوت' in (text or '') or 'not a robot' in (text or '').lower()\n\n"
        "def force_sub_info() -> str:\n"
        "    return 'الاشتراك الإجباري: أضف قناتك هنا من الإعدادات لاحقًا. هذه نسخة معلوماتية.'\n\n"
        "def calc(expr: str) -> str:\n"
        "    allowed = set('0123456789+-*/(). %')\n"
        "    e = ''.join(ch for ch in (expr or '') if ch in allowed)\n"
        "    if not e:\n"
        "        return 'تعبير غير صالح'\n"
        "    try:\n"
        "        return str(eval(e, {'__builtins__': {}}, {}))  # noqa: S307 — filtered charset only\n"
        "    except Exception:\n"
        "        return 'تعذر الحساب'\n\n"
        "def time_now() -> str:\n"
        "    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')\n\n"
        "def echo(text: str) -> str:\n"
        "    return text or '—'\n\n"
        "def random_pick(text: str) -> str:\n"
        "    parts = [p.strip() for p in (text or '').split(',') if p.strip()]\n"
        "    return random.choice(parts) if parts else 'أدخل عناصر مفصولة بفاصلة'\n\n"
        "def short_note(user_id: int, text: str) -> int:\n"
        "    return _add(user_id, 'short_note', text)\n\n"
        "def stats_basic() -> str:\n"
        "    ensure()\n"
        "    with connect() as conn:\n"
        '        n = conn.execute("SELECT COUNT(*) AS c FROM extras_kv").fetchone()["c"]\n'
        "    return f'سجلات extras: {n}'\n"
    )


