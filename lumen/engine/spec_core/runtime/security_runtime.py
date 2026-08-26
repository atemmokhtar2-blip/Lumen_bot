"""Defensive security ops — reports, awareness, and passive domain checks.

No offensive / exploit tooling. Network helpers use stdlib only.
"""
from __future__ import annotations

import re
import socket
import ssl
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.db import connect, init_db

CHECKLIST = (
    "1) لا تشارك كلمات المرور أو رموز التحقق\n"
    "2) راجع الروابط قبل الفتح\n"
    "3) فعّل التحقق بخطوتين\n"
    "4) بلّغ فورًا عن أي رسالة مشبوهة\n"
    "5) حدّث التطبيقات باستمرار"
)

TIPS = (
    "• استخدم كلمات مرور فريدة لكل خدمة\n"
    "• فعّل 2FA / مفاتيح المرور\n"
    "• لا تفتح مرفقات غير متوقعة\n"
    "• راجع صلاحيات التطبيقات دوريًا"
)

PASSWORD_TIPS = (
    "• 12+ حرف مع تنوع (أحرف/أرقام/رموز)\n"
    "• لا تعِد استخدام نفس كلمة المرور\n"
    "• مدير كلمات مرور موثوق أفضل من الذاكرة\n"
    "• غيّر فوريًا بعد أي تسريب معروف"
)

_HOST_RE = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9\-\.]{0,251}[a-zA-Z0-9])?$")

def ensure() -> None:
    init_db()

def _clean_host(raw: str) -> str:
    t = (raw or '').strip().lower()
    if '://' in t:
        t = urlparse(t).hostname or t
    t = t.split('/')[0].split('?')[0].strip().strip('.')
    if t.startswith('www.'):
        t = t[4:]
    if not t or not _HOST_RE.match(t) or len(t) > 253:
        return ''
    return t

def report(user_id: int, kind: str, body: str) -> int:
    ensure()
    kind = (kind or "incident").strip()[:40]
    body = (body or "").strip() or "—"
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO security_reports (user_id, kind, body, status) VALUES (?, ?, ?, 'open')",
            (user_id, kind, body[:2000]),
        )
        conn.commit()
        return int(cur.lastrowid)

def list_reports(only_open: bool = True, limit: int = 20) -> list[dict]:
    ensure()
    q = "SELECT id, user_id, kind, body, status, created_at FROM security_reports"
    if only_open:
        q += " WHERE status = 'open'"
    q += " ORDER BY id DESC LIMIT ?"
    with connect() as conn:
        rows = conn.execute(q, (limit,)).fetchall()
    return [dict(r) for r in rows]

def close_report(report_id: int) -> bool:
    ensure()
    with connect() as conn:
        cur = conn.execute("UPDATE security_reports SET status = 'closed' WHERE id = ?", (report_id,))
        conn.commit()
        return cur.rowcount > 0

def checklist() -> str:
    return CHECKLIST

def tips() -> str:
    return TIPS

def password_tips() -> str:
    return PASSWORD_TIPS

def dns_check(host: str) -> str:
    h = _clean_host(host)
    if not h:
        return 'أدخل نطاقًا صالحًا: /dns example.com'
    lines = [f'DNS overview — {h}']
    try:
        infos = socket.getaddrinfo(h, None)
        seen: set[str] = set()
        for info in infos:
            ip = info[4][0]
            if ip in seen:
                continue
            seen.add(ip)
            fam = 'AAAA' if ':' in ip else 'A'
            lines.append(f'  {fam}: {ip}')
            if len(seen) >= 8:
                break
        if not seen:
            lines.append('  (no A/AAAA resolved)')
    except socket.gaierror as exc:
        lines.append(f'  resolve error: {exc}')
    except Exception as exc:
        lines.append(f'  error: {exc}')
    lines.append('Note: passive lookup only (stdlib).')
    return '\n'.join(lines)

def mx_check(host: str) -> str:
    # Stdlib cannot query MX RRset without dnspython; give honest guidance + A lookup.
    h = _clean_host(host)
    if not h:
        return 'أدخل نطاقًا صالحًا: /mx example.com'
    base = dns_check(h)
    return (
        base + '\n\nMX tip: use dig/nslookup for MX/SPF/DMARC records. '
        'This bot does passive A/AAAA only (no external DNS libs).'
    )

def tls_check(host: str) -> str:
    h = _clean_host(host)
    if not h:
        return 'أدخل نطاقًا صالحًا: /tls example.com'
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((h, 443), timeout=8) as sock:
            with ctx.wrap_socket(sock, server_hostname=h) as ssock:
                cert = ssock.getpeercert()
                ver = ssock.version()
        subject = dict(x[0] for x in (cert or {}).get('subject', ()) )
        issuer = dict(x[0] for x in (cert or {}).get('issuer', ()) )
        not_after = (cert or {}).get('notAfter', '?')
        cn = subject.get('commonName') or subject.get('organizationName') or '?'
        iss = issuer.get('commonName') or issuer.get('organizationName') or '?'
        return (
            f'TLS overview — {h}\n'
            f'  protocol: {ver}\n'
            f'  subject CN: {cn}\n'
            f'  issuer: {iss}\n'
            f'  notAfter: {not_after}\n'
            'Passive certificate read only.'
        )
    except Exception as exc:
        return f'TLS check failed for {h}: {exc}'

def http_check(host: str) -> str:
    h = _clean_host(host)
    if not h:
        return 'أدخل نطاقًا صالحًا: /httpstatus example.com'
    url = f'https://{h}/'
    try:
        req = Request(url, method='GET', headers={'User-Agent': 'SecBot/1.0'})
        with urlopen(req, timeout=8) as resp:  # noqa: S310 — host validated
            code = getattr(resp, 'status', None) or resp.getcode()
            return f'HTTP {code} — {url}'
    except Exception as exc:
        return f'HTTP probe failed for {h}: {exc}'

def headers_check(host: str) -> str:
    h = _clean_host(host)
    if not h:
        return 'أدخل نطاقًا صالحًا: /headers example.com'
    url = f'https://{h}/'
    interesting = (
        'strict-transport-security', 'content-security-policy',
        'x-frame-options', 'x-content-type-options', 'referrer-policy',
        'permissions-policy', 'server',
    )
    try:
        req = Request(url, method='GET', headers={'User-Agent': 'SecBot/1.0'})
        with urlopen(req, timeout=8) as resp:  # noqa: S310
            hdrs = {k.lower(): v for k, v in resp.headers.items()}
        lines = [f'Security headers — {h}']
        for key in interesting:
            val = hdrs.get(key)
            lines.append(f'  {key}: {val if val else "(missing)"}')
        return '\n'.join(lines)
    except Exception as exc:
        return f'Headers probe failed for {h}: {exc}'

def domain_overview(host: str) -> str:
    h = _clean_host(host)
    if not h:
        return 'أدخل نطاقًا صالحًا: /domainscan example.com'
    parts = [
        dns_check(h),
        '',
        tls_check(h),
        '',
        http_check(h),
        '',
        headers_check(h),
    ]
    return '\n'.join(parts)
