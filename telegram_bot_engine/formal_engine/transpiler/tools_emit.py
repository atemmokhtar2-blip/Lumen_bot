
"""Emit tools.py from THIS request's tool list only — rebuilt every generation."""
from __future__ import annotations

import re

from typing import Any

from ..inference.engine import InferenceResult

def _classify_tool_primitive(tool: dict[str, Any]) -> str:
    blob = " ".join(str(tool.get(k) or "") for k in ("id", "title", "description", "input")).lower()
    if "dmarc" in blob: return "dns_txt_dmarc"
    if "spf" in blob: return "dns_txt_spf"
    if "mx" in blob: return "dns_mx"
    if "dns" in blob or "dns_a" in blob or "dns_lookup" in blob: return "dns_a"
    if "tls" in blob or "ssl" in blob: return "tls_cert"
    if "header" in blob or "hsts" in blob or "csp" in blob: return "http_headers"
    if "http" in blob and "status" in blob: return "http_status"
    if "robots" in blob: return "http_path:/robots.txt"
    if "sitemap" in blob: return "http_path:/sitemap.xml"
    if "whois" in blob: return "whois"
    if "ping" in blob: return "ping"
    if "password" in blob or "hash" in blob: return "password_strength"
    if "report" in blob or "pdf" in blob: return "report_text"
    if "http_status" in blob: return "http_status"
    if "security_headers" in blob: return "http_headers"
    return "echo_target"


def emit_tools_module(inf: InferenceResult) -> str:
    tools = list(getattr(inf, "dynamic_tools", None) or [])
    if not tools:
        # fallback: synthesize from defensive_tools ids
        for tid in list(getattr(inf, "defensive_tools", None) or []):
            tools.append({"id": tid, "title": tid, "input": "domain"})
    if not tools:
        return (
            '"""No tools in this user specification."""\n'
            "from __future__ import annotations\n\n"
            "def run_evidenced_checks(target: str) -> str:\n"
            "    return 'لا توجد أدوات مستنتجة من طلبك.'\n"
        )

    lines: list[str] = [
        '"""Tools rebuilt for this bot only — from the user request evidence."""',
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
        "def _clean_domain(raw: str) -> str:",
        "    t = (raw or '').strip()",
        "    t = t.replace('https://', '').replace('http://', '')",
        "    return t.split('/')[0].split(':')[0].strip().lower()",
        "",
        "def _as_url(raw: str) -> str:",
        "    t = (raw or '').strip()",
        "    if not t.startswith('http://') and not t.startswith('https://'):",
        "        t = 'https://' + t",
        "    return t",
        "",
        "def _http_get(url: str, path: str = '') -> dict[str, Any]:",
        "    u = _as_url(url)",
        "    if path:",
        "        u = u.rstrip('/') + path",
        "    req = urllib.request.Request(u, headers={'User-Agent': 'UserBot/1.0'})",
        "    try:",
        "        with urllib.request.urlopen(req, timeout=10) as resp:",
        "            body = resp.read(8000).decode('utf-8', 'ignore')",
        "            headers = {k.lower(): v for k, v in resp.headers.items()}",
        "            return {'ok': True, 'status': resp.status, 'headers': headers, 'body': body[:2000], 'url': u}",
        "    except Exception as exc:",
        "        return {'ok': False, 'error': str(exc), 'url': u}",
        "",
        "def _dns_a(domain: str) -> dict[str, Any]:",
        "    d = _clean_domain(domain)",
        "    out: list[str] = []",
        "    try:",
        "        for _f, _, _, _, addr in socket.getaddrinfo(d, None):",
        "            if addr[0] not in out:",
        "                out.append(addr[0])",
        "        return {'ok': True, 'records': out}",
        "    except Exception as exc:",
        "        return {'ok': False, 'error': str(exc)}",
        "",
        "def _dns_mx(domain: str) -> dict[str, Any]:",
        "    d = _clean_domain(domain)",
        "    if not _HAS_DNS:",
        "        return {'ok': False, 'error': 'dnspython required'}",
        "    try:",
        "        ans = dns.resolver.resolve(d, 'MX')",
        "        recs = sorted([(r.preference, str(r.exchange).rstrip('.')) for r in ans])",
        "        return {'ok': True, 'records': [f'{p} {h}' for p, h in recs]}",
        "    except Exception as exc:",
        "        return {'ok': False, 'error': str(exc)}",
        "",
        "def _dns_txt(name: str) -> dict[str, Any]:",
        "    if not _HAS_DNS:",
        "        return {'ok': False, 'error': 'dnspython required'}",
        "    try:",
        "        ans = dns.resolver.resolve(name, 'TXT')",
        "        recs = [b''.join(r.strings).decode('utf-8', 'ignore') for r in ans]",
        "        return {'ok': True, 'records': recs}",
        "    except Exception as exc:",
        "        return {'ok': False, 'error': str(exc)}",
        "",
        "def _tls(domain: str) -> dict[str, Any]:",
        "    d = _clean_domain(domain)",
        "    try:",
        "        ctx = ssl.create_default_context()",
        "        with socket.create_connection((d, 443), timeout=8) as sock:",
        "            with ctx.wrap_socket(sock, server_hostname=d) as ssock:",
        "                cert = ssock.getpeercert()",
        "                ver = ssock.version()",
        "        subj = dict(x[0] for x in (cert or {}).get('subject', ()))",
        "        issuer = dict(x[0] for x in (cert or {}).get('issuer', ()))",
        "        return {'ok': True, 'tls': ver, 'subject': subj.get('commonName') or subj,",
        "                'issuer': issuer.get('commonName') or issuer, 'notAfter': (cert or {}).get('notAfter')}",
        "    except Exception as exc:",
        "        return {'ok': False, 'error': str(exc)}",
        "",
        "def _password_strength(text: str) -> dict[str, Any]:",
        "    p = text or ''",
        "    score = 0",
        "    if len(p) >= 8: score += 1",
        "    if len(p) >= 12: score += 1",
        "    if re.search(r'[A-Z]', p): score += 1",
        "    if re.search(r'[a-z]', p): score += 1",
        "    if re.search(r'\\d', p): score += 1",
        "    if re.search(r'[^A-Za-z0-9]', p): score += 1",
        "    return {'ok': True, 'score': score, 'max': 6, 'length': len(p)}",
        "",
    ]

    # Per-tool wrappers from THIS request
    tool_ids: list[str] = []
    for tool in tools:
        tid = re.sub(r"[^a-z0-9_]", "_", str(tool.get("id") or "tool").lower()).strip("_")[:40]
        if not tid or tid in tool_ids:
            continue
        tool_ids.append(tid)
        prim = _classify_tool_primitive(tool)
        title = str(tool.get("title") or tid)
        lines.append(f"def tool_{tid}(target: str) -> dict[str, Any]:")
        lines.append(f"    # primitive={prim!r} title={title!r}")
        if prim == "dns_a":
            lines.append("    return _dns_a(target)")
        elif prim == "dns_mx":
            lines.append("    return _dns_mx(target)")
        elif prim == "dns_txt_spf":
            lines.append("    r = _dns_txt(_clean_domain(target))")
            lines.append("    if not r.get('ok'): return r")
            lines.append("    spf = [x for x in r.get('records') or [] if x.lower().startswith('v=spf1')]")
            lines.append("    return {'ok': True, 'records': spf or ['(no SPF)']}")
        elif prim == "dns_txt_dmarc":
            lines.append("    return _dns_txt('_dmarc.' + _clean_domain(target))")
        elif prim == "tls_cert":
            lines.append("    return _tls(target)")
        elif prim == "http_status":
            lines.append("    r = _http_get(target)")
            lines.append("    if not r.get('ok'): return r")
            lines.append("    return {'ok': True, 'status': r.get('status'), 'url': r.get('url')}")
        elif prim == "http_headers":
            lines.append("    r = _http_get(target)")
            lines.append("    if not r.get('ok'): return r")
            lines.append("    want = ['strict-transport-security','content-security-policy','x-frame-options',")
            lines.append("            'x-content-type-options','referrer-policy','permissions-policy']")
            lines.append("    h = r.get('headers') or {}")
            lines.append("    return {'ok': True, 'present': {k:h[k] for k in want if k in h},")
            lines.append("            'missing': [k for k in want if k not in h], 'status': r.get('status')}")
        elif prim.startswith("http_path:"):
            path = prim.split(":", 1)[1]
            lines.append(f"    return _http_get(target, {path!r})")
        elif prim == "password_strength":
            lines.append("    return _password_strength(target)")
        elif prim == "whois":
            lines.append("    # Safe limited WHOIS via DNS SOA only (no scraping packs)")
            lines.append("    d = _clean_domain(target)")
            lines.append("    if not _HAS_DNS: return {'ok': False, 'error': 'dnspython required for SOA'}")
            lines.append("    try:")
            lines.append("        ans = dns.resolver.resolve(d, 'SOA')")
            lines.append("        return {'ok': True, 'soa': [str(r) for r in ans]}")
            lines.append("    except Exception as exc:")
            lines.append("        return {'ok': False, 'error': str(exc)}")
        elif prim == "ping":
            lines.append("    d = _clean_domain(target)")
            lines.append("    try:")
            lines.append("        socket.getaddrinfo(d, None)")
            lines.append("        return {'ok': True, 'reachable_dns': True, 'host': d}")
            lines.append("    except Exception as exc:")
            lines.append("        return {'ok': False, 'error': str(exc)}")
        elif prim == "report_text":
            lines.append("    return {'ok': True, 'report': 'ملخص: ' + (target or '')}")
        else:
            lines.append("    return {'ok': True, 'target': target, 'note': 'tool registered from your request'}")
        lines.append("")

    # Runner executes only tools of THIS bot
    lines += [
        "def run_evidenced_checks(target: str) -> str:",
        "    t = (target or '').strip()",
        "    if not t:",
        "        return 'أدخل هدفاً.'",
        "    parts = ['نتائج: ' + t]",
    ]
    for tid in tool_ids:
        lines.append("    try:")
        lines.append(f"        r = tool_{tid}(t)")
        lines.append(f"        if r.get('ok'):")
        lines.append(f"            parts.append('{tid}: ' + str({{k:v for k,v in r.items() if k!='ok'}})[:500])")
        lines.append(f"        else:")
        lines.append(f"            parts.append('{tid} error: ' + str(r.get('error')))")
        lines.append("    except Exception as exc:")
        lines.append(f"        parts.append('{tid}: ' + str(exc))")
    lines += [
        "    return chr(10).join(parts)[:3500]",
        "",
    ]
    return "\n".join(lines) + "\n"
