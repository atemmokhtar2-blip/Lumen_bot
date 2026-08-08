"""
Defensive network/HTTP tools — structural ontology only.

NOT a CyberGuard / security-bot template.
Maps surface language → concrete check functions the transpiler may emit
only when the user's text evidences that check.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class DefensiveTool:
    id: str
    surface_forms: tuple[str, ...]
    needs: str  # "domain" | "url"
    description: str = ""


DEFENSIVE_TOOLS: tuple[DefensiveTool, ...] = (
    DefensiveTool(
        id="dns_a",
        surface_forms=("dns", "dns records", "dns record", "سجلات dns", "سجل dns", "a record"),
        needs="domain",
        description="Resolve A/AAAA records",
    ),
    DefensiveTool(
        id="mx",
        surface_forms=("mx", "mx records", "mx record", "سجلات mx", "mail exchange"),
        needs="domain",
        description="Resolve MX records",
    ),
    DefensiveTool(
        id="spf",
        surface_forms=("spf", "spf record", "سجل spf"),
        needs="domain",
        description="Fetch SPF TXT",
    ),
    DefensiveTool(
        id="dmarc",
        surface_forms=("dmarc", "dmarc record", "سجل dmarc"),
        needs="domain",
        description="Fetch DMARC TXT",
    ),
    DefensiveTool(
        id="tls_info",
        surface_forms=(
            "tls", "ssl", "tls/ssl", "tls certificate", "ssl certificate",
            "شهادة", "tls information", "ssl information",
        ),
        needs="domain",
        description="TLS certificate metadata",
    ),
    DefensiveTool(
        id="http_status",
        surface_forms=("http status", "status code", "حالة http", "http status code"),
        needs="url",
        description="HTTP response status",
    ),
    DefensiveTool(
        id="security_headers",
        surface_forms=(
            "security headers", "security header", "headers",
            "رؤوس الأمن", "هيدرز", "hsts", "csp",
        ),
        needs="url",
        description="Common security response headers",
    ),
)


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    s = s.replace("ة", "ه").replace("ى", "ي")
    return s


def resolve_defensive_tools(*texts: str) -> list[str]:
    """Return tool ids evidenced in text (word-boundary aware for short tokens)."""
    blob = _norm(" ".join(t for t in texts if t))
    if not blob:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for tool in DEFENSIVE_TOOLS:
        for form in tool.surface_forms:
            nf = _norm(form)
            if not nf:
                continue
            if len(nf) <= 3:
                hit = bool(re.search(rf"(?<!\w){re.escape(nf)}(?!\w)", blob))
            else:
                hit = nf in blob
            if hit:
                if tool.id not in seen:
                    seen.add(tool.id)
                    found.append(tool.id)
                break
    return found


def tools_by_ids(ids: list[str]) -> list[DefensiveTool]:
    by = {t.id: t for t in DEFENSIVE_TOOLS}
    return [by[i] for i in ids if i in by]
