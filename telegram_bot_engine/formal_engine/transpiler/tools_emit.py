"""
Emit tools.py from THIS request's tool list only.

No domain packs: every tool id comes from the formal contract (commands/tools).
Primitives below are generic I/O helpers selected only when the tool id/title
itself contains matching tokens — they do not invent tools.
"""
from __future__ import annotations

import re
from typing import Any

from ..inference.engine import InferenceResult


def _safe_ident(tid: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]", "_", (tid or "").strip().lower()).strip("_")
    if not s or not s[0].isalpha():
        s = "tool_" + (s or "x")
    return s[:48]


def _classify_primitive(tool: dict[str, Any]) -> str:
    blob = " ".join(str(tool.get(k) or "") for k in ("id", "title", "description", "input")).lower()
    if "dmarc" in blob:
        return "dns_txt_dmarc"
    if "spf" in blob:
        return "dns_txt_spf"
    if re.search(r"\bmx\b", blob):
        return "dns_mx"
    if "dns" in blob:
        return "dns_a"
    if "tls" in blob or "ssl" in blob:
        return "tls_cert"
    if "header" in blob or "hsts" in blob or "csp" in blob:
        return "http_headers"
    if "http" in blob and "status" in blob:
        return "http_status"
    if "password" in blob and ("strength" in blob or "check" in blob):
        return "password_strength"
    if "ping" in blob:
        return "ping"
    # Generic action — no invented domain logic
    return "record"


def emit_tools_module(inf: InferenceResult) -> str:
    tools = [t for t in (getattr(inf, "dynamic_tools", None) or []) if isinstance(t, dict)]
    # Always ensure every non-structural command has a tool entry
    seen = {str(t.get("id") or "").lower() for t in tools}
    for c in getattr(inf, "commands", None) or []:
        name = (getattr(c, "name", None) or "").strip().lower()
        if not name or name in ("start", "help") or name in seen:
            continue
        tools.append({
            "id": name,
            "title": getattr(c, "description", None) or name,
            "input": "value",
            "source": "command",
        })
        seen.add(name)

    if not tools:
        return (
            '"""No tools declared for this bot."""\n'
            "from __future__ import annotations\n\n"
            "TOOL_IDS: list[str] = []\n\n"
            "def run_tool(tool_id: str, target: str = \"\") -> str:\n"
            "    return \"لا توجد أدوات مربوطة.\"\n\n"
            "def run_evidenced_checks(target: str) -> str:\n"
            "    return run_tool(\"\", target)\n"
        )

    lines: list[str] = [
        '"""Tools for this bot only — bound to contract commands/tools."""',
        "from __future__ import annotations",
        "",
        "import re",
        "import socket",
        "import ssl",
        "import urllib.request",
        "from typing import Any",
        "",
        "try:",
        "    import dns.resolver  # type: ignore",
        "    _HAS_DNS = True",
        "except Exception:",
        "    dns = None  # type: ignore",
        "    _HAS_DNS = False",
        "",
        "def _clean_host(raw: str) -> str:",
        "    t = (raw or '').strip()",
        "    t = re.sub(r'^https?://', '', t, flags=re.I)",
        "    t = t.split('/')[0].split('?')[0].strip().lower()",
        "    return t",
        "",
        "def _dns_a(domain: str) -> dict[str, Any]:",
        "    d = _clean_host(domain)",
        "    if not d:",
        "        return {'ok': False, 'error': 'empty_host'}",
        "    try:",
        "        infos = socket.getaddrinfo(d, None)",
        "        addrs = sorted({i[4][0] for i in infos})",
        "        return {'ok': True, 'host': d, 'addresses': addrs}",
        "    except Exception as exc:",
        "        return {'ok': False, 'error': str(exc)}",
        "",
        "def _dns_mx(domain: str) -> dict[str, Any]:",
        "    d = _clean_host(domain)",
        "    if not _HAS_DNS:",
        "        return {'ok': False, 'error': 'dnspython_required'}",
        "    try:",
        "        ans = dns.resolver.resolve(d, 'MX')",
        "        return {'ok': True, 'mx': [str(r.exchange).rstrip('.') for r in ans]}",
        "    except Exception as exc:",
        "        return {'ok': False, 'error': str(exc)}",
        "",
        "def _dns_txt(domain: str, prefix: str) -> dict[str, Any]:",
        "    d = _clean_host(domain)",
        "    if not _HAS_DNS:",
        "        return {'ok': False, 'error': 'dnspython_required'}",
        "    name = d if prefix == 'spf' else ('_dmarc.' + d if prefix == 'dmarc' else d)",
        "    try:",
        "        ans = dns.resolver.resolve(name, 'TXT')",
        "        recs = [b''.join(r.strings).decode('utf-8', 'ignore') for r in ans]",
        "        if prefix == 'spf':",
        "            recs = [x for x in recs if 'spf' in x.lower()]",
        "        return {'ok': True, 'records': recs}",
        "    except Exception as exc:",
        "        return {'ok': False, 'error': str(exc)}",
        "",
        "def _tls_cert(domain: str) -> dict[str, Any]:",
        "    d = _clean_host(domain)",
        "    try:",
        "        ctx = ssl.create_default_context()",
        "        with socket.create_connection((d, 443), timeout=8) as sock:",
        "            with ctx.wrap_socket(sock, server_hostname=d) as ssock:",
        "                cert = ssock.getpeercert()",
        "        return {'ok': True, 'subject': dict(x[0] for x in (cert or {}).get('subject', ())), 'issuer': dict(x[0] for x in (cert or {}).get('issuer', ())), 'notAfter': (cert or {}).get('notAfter')}",
        "    except Exception as e:",
        "        return {'ok': False, 'error': str(e)}",
        "",
        "def _http_status(url: str) -> dict[str, Any]:",
        "    u = (url or '').strip()",
        "    if u and not u.startswith('http'):",
        "        u = 'https://' + u",
        "    try:",
        "        req = urllib.request.Request(u, method='GET', headers={'User-Agent': 'ContractBot/1.0'})",
        "        with urllib.request.urlopen(req, timeout=10) as resp:",
        "            return {'ok': True, 'status': resp.status, 'url': u}",
        "    except Exception as e:",
        "        return {'ok': False, 'error': str(e)}",
        "",
        "def _http_headers(url: str) -> dict[str, Any]:",
        "    u = (url or '').strip()",
        "    if u and not u.startswith('http'):",
        "        u = 'https://' + u",
        "    try:",
        "        req = urllib.request.Request(u, method='GET', headers={'User-Agent': 'ContractBot/1.0'})",
        "        with urllib.request.urlopen(req, timeout=10) as resp:",
        "            keys = ('strict-transport-security', 'content-security-policy', 'x-frame-options', 'x-content-type-options')",
        "            hdrs = {k: resp.headers.get(k) for k in keys if resp.headers.get(k)}",
        "            return {'ok': True, 'status': resp.status, 'headers': hdrs}",
        "    except Exception as e:",
        "        return {'ok': False, 'error': str(e)}",
        "",
        "def _password_strength(text: str) -> dict[str, Any]:",
        "    t = text or ''",
        "    score = 0",
        "    if len(t) >= 8: score += 1",
        "    if re.search(r'[A-Z]', t): score += 1",
        "    if re.search(r'[a-z]', t): score += 1",
        "    if re.search(r'\\d', t): score += 1",
        "    if re.search(r'[^A-Za-z0-9]', t): score += 1",
        "    return {'ok': True, 'score': score, 'max': 5, 'length': len(t)}",
        "",
        "def _ping(host: str) -> dict[str, Any]:",
        "    d = _clean_host(host)",
        "    try:",
        "        socket.getaddrinfo(d, None)",
        "        return {'ok': True, 'host': d, 'resolves': True}",
        "    except Exception as e:",
        "        return {'ok': False, 'error': str(e)}",
        "",
        "def _record(action: str, target: str) -> dict[str, Any]:",
        "    return {'ok': True, 'action': action, 'input': (target or '')[:500]}",
        "",
    ]

    tool_ids: list[str] = []
    for t in tools:
        tid = _safe_ident(str(t.get("id") or "tool"))
        if tid in tool_ids:
            continue
        tool_ids.append(tid)
        prim = _classify_primitive(t)
        lines.append(f"def tool_{tid}(target: str = '') -> dict[str, Any]:")
        lines.append(f"    \"\"\"Bound to contract tool `{tid}`.\"\"\"")
        if prim == "dns_a":
            lines.append("    return _dns_a(target)")
        elif prim == "dns_mx":
            lines.append("    return _dns_mx(target)")
        elif prim == "dns_txt_spf":
            lines.append("    return _dns_txt(target, 'spf')")
        elif prim == "dns_txt_dmarc":
            lines.append("    return _dns_txt(target, 'dmarc')")
        elif prim == "tls_cert":
            lines.append("    return _tls_cert(target)")
        elif prim == "http_status":
            lines.append("    return _http_status(target)")
        elif prim == "http_headers":
            lines.append("    return _http_headers(target)")
        elif prim == "password_strength":
            lines.append("    return _password_strength(target)")
        elif prim == "ping":
            lines.append("    return _ping(target)")
        else:
            lines.append(f"    return _record({tid!r}, target)")
        lines.append("")

    ids_repr = repr(tool_ids)
    lines += [
        f"TOOL_IDS: list[str] = {ids_repr}",
        "",
        "def run_tool(tool_id: str, target: str = '') -> str:",
        "    tid = (tool_id or '').strip().lower()",
        "    fn = globals().get('tool_' + re.sub(r'[^a-z0-9_]', '_', tid))",
        "    if not callable(fn):",
        "        return 'أداة غير معروفة: ' + tid",
        "    try:",
        "        r = fn(target)",
        "    except Exception as exc:",
        "        return 'خطأ: ' + str(exc)",
        "    if not isinstance(r, dict):",
        "        return str(r)[:3500]",
        "    if not r.get('ok', True):",
        "        return 'فشل: ' + str(r.get('error') or r)[:3500]",
        "    body = {k: v for k, v in r.items() if k != 'ok'}",
        "    return (tid + ': ' + str(body))[:3500]",
        "",
        "def run_evidenced_checks(target: str) -> str:",
        "    parts = []",
        "    for tid in TOOL_IDS:",
        "        parts.append(run_tool(tid, target))",
        "    return chr(10).join(parts)[:3500] if parts else 'لا أدوات.'",
        "",
    ]
    return "\n".join(lines) + "\n"
