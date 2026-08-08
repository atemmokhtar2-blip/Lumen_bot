"""Emit defensive tool modules from evidenced tool ids only — no bot templates."""
from __future__ import annotations

from typing import Any

from ..inference.engine import InferenceResult


def _py(val: Any) -> str:
    return repr(val)


def emit_tools_module(inf: InferenceResult) -> str:
    ids = list(getattr(inf, "defensive_tools", None) or [])
    if not ids:
        return (
            '"""No defensive tools evidenced."""\n'
            "from __future__ import annotations\n\n"
            "def run_evidenced_checks(target: str) -> str:\n"
            "    return 'لا توجد فحوصات مستنتجة من المواصفة.'\n"
        )
    lines: list[str] = [
        '"""Defensive checks from evidenced tool ids only."""',
        "from __future__ import annotations",
        "",
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
    ]
    need = set(ids)
    if "dns_a" in need:
        lines += [
            "def tool_dns_a(domain: str) -> dict[str, Any]:",
            "    d = _clean_domain(domain)",
            "    out: list[str] = []",
            "    try:",
            "        for _fam, _, _, _, addr in socket.getaddrinfo(d, None):",
            "            ip = addr[0]",
            "            if ip not in out:",
            "                out.append(ip)",
            "    except Exception as exc:",
            "        return {'ok': False, 'error': str(exc)}",
            "    return {'ok': True, 'records': out}",
            "",
        ]
    if "mx" in need:
        lines += [
            "def tool_mx(domain: str) -> dict[str, Any]:",
            "    d = _clean_domain(domain)",
            "    if not _HAS_DNS:",
            "        return {'ok': False, 'error': 'dnspython not installed'}",
            "    try:",
            "        ans = dns.resolver.resolve(d, 'MX')",
            "        recs = sorted([(r.preference, str(r.exchange).rstrip('.')) for r in ans])",
            "        return {'ok': True, 'records': [f'{p} {h}' for p, h in recs]}",
            "    except Exception as exc:",
            "        return {'ok': False, 'error': str(exc)}",
            "",
        ]
    if "spf" in need:
        lines += [
            "def tool_spf(domain: str) -> dict[str, Any]:",
            "    d = _clean_domain(domain)",
            "    if not _HAS_DNS:",
            "        return {'ok': False, 'error': 'dnspython not installed'}",
            "    try:",
            "        ans = dns.resolver.resolve(d, 'TXT')",
            "        spf = []",
            "        for r in ans:",
            "            s = b''.join(r.strings).decode('utf-8', 'ignore')",
            "            if s.lower().startswith('v=spf1'):",
            "                spf.append(s)",
            "        return {'ok': True, 'records': spf or ['(no SPF)']}",
            "    except Exception as exc:",
            "        return {'ok': False, 'error': str(exc)}",
            "",
        ]
    if "dmarc" in need:
        lines += [
            "def tool_dmarc(domain: str) -> dict[str, Any]:",
            "    d = _clean_domain(domain)",
            "    if not _HAS_DNS:",
            "        return {'ok': False, 'error': 'dnspython not installed'}",
            "    try:",
            "        ans = dns.resolver.resolve('_dmarc.' + d, 'TXT')",
            "        recs = [b''.join(r.strings).decode('utf-8', 'ignore') for r in ans]",
            "        return {'ok': True, 'records': recs or ['(no DMARC)']}",
            "    except Exception as exc:",
            "        return {'ok': False, 'error': str(exc)}",
            "",
        ]
    if "tls_info" in need:
        lines += [
            "def tool_tls_info(domain: str) -> dict[str, Any]:",
            "    d = _clean_domain(domain)",
            "    try:",
            "        ctx = ssl.create_default_context()",
            "        with socket.create_connection((d, 443), timeout=8) as sock:",
            "            with ctx.wrap_socket(sock, server_hostname=d) as ssock:",
            "                cert = ssock.getpeercert()",
            "                ver = ssock.version()",
            "        subj = dict(x[0] for x in (cert or {}).get('subject', ()))",
            "        issuer = dict(x[0] for x in (cert or {}).get('issuer', ()))",
            "        return {",
            "            'ok': True,",
            "            'tls_version': ver,",
            "            'subject': subj.get('commonName') or subj,",
            "            'issuer': issuer.get('commonName') or issuer,",
            "            'notAfter': (cert or {}).get('notAfter'),",
            "        }",
            "    except Exception as exc:",
            "        return {'ok': False, 'error': str(exc)}",
            "",
        ]
    if "http_status" in need or "security_headers" in need:
        lines += [
            "def _fetch(url: str) -> dict[str, Any]:",
            "    u = _as_url(url)",
            "    req = urllib.request.Request(u, headers={'User-Agent': 'DefensiveBot/1.0'})",
            "    try:",
            "        with urllib.request.urlopen(req, timeout=10) as resp:",
            "            headers = {k.lower(): v for k, v in resp.headers.items()}",
            "            return {'ok': True, 'url': u, 'status': resp.status, 'headers': headers}",
            "    except Exception as exc:",
            "        return {'ok': False, 'error': str(exc), 'url': u}",
            "",
        ]
    if "http_status" in need:
        lines += [
            "def tool_http_status(url: str) -> dict[str, Any]:",
            "    r = _fetch(url)",
            "    if not r.get('ok'):",
            "        return r",
            "    return {'ok': True, 'status': r.get('status'), 'url': r.get('url')}",
            "",
        ]
    if "security_headers" in need:
        lines += [
            "def tool_security_headers(url: str) -> dict[str, Any]:",
            "    r = _fetch(url)",
            "    if not r.get('ok'):",
            "        return r",
            "    want = [",
            "        'strict-transport-security', 'content-security-policy',",
            "        'x-frame-options', 'x-content-type-options',",
            "        'referrer-policy', 'permissions-policy',",
            "    ]",
            "    h = r.get('headers') or {}",
            "    present = {k: h[k] for k in want if k in h}",
            "    missing = [k for k in want if k not in h]",
            "    return {'ok': True, 'present': present, 'missing': missing, 'status': r.get('status')}",
            "",
        ]
    # runner
    lines += [
        "def run_evidenced_checks(target: str) -> str:",
        "    t = (target or '').strip()",
        "    if not t:",
        "        return 'أدخل هدفاً صالحاً.'",
        "    parts: list[str] = ['نتائج الفحص لـ: ' + t]",
    ]
    labels = {
        "dns_a": "DNS",
        "mx": "MX",
        "spf": "SPF",
        "dmarc": "DMARC",
        "tls_info": "TLS",
        "http_status": "HTTP",
        "security_headers": "Headers",
    }
    for tid in ids:
        lab = labels.get(tid, tid)
        lines.append(f"    try:")
        lines.append(f"        r = tool_{tid}(t)")
        lines.append(f"        if r.get('ok'):")
        lines.append(f"            detail = {{k: v for k, v in r.items() if k != 'ok'}}")
        lines.append(f"            parts.append('{lab}: ' + str(detail)[:600])")
        lines.append(f"        else:")
        lines.append(f"            parts.append('{lab} error: ' + str(r.get('error')))")
        lines.append(f"    except Exception as exc:")
        lines.append(f"        parts.append('{lab}: ' + str(exc))")
    lines += [
        "    return chr(10).join(parts)[:3500]",
        "",
    ]
    return "\n".join(lines) + "\n"
