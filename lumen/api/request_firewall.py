"""Application-layer request firewall (OWASP API4/API8 style).

Not a network WAF — runs inside the API process before handlers:
  - blocks path traversal / null bytes / oversize URL
  - blocks common injection probes in path + query
  - fail-closed on malformed requests

Reference posture: OWASP API Security Top 10 2023 (resource consumption,
misconfiguration) + Telegram webhook secret-token practice.
"""
from __future__ import annotations

import logging
import re
from aiohttp import web

logger = logging.getLogger("lumen.api.firewall")

# Max URL length (path + query) — refuse probing / buffer abuse
_MAX_URL_CHARS = 2048

# Path traversal and encoding tricks (decoded path checked by aiohttp; also raw)
_TRAVERSAL = re.compile(
    r"(?i)(%2e%2e|%252e|%c0%ae|\.\./|\.\.\\|/\.\.|\\\.\.)"
)

# Probe patterns that never belong in API path/query for this product
_PROBE = re.compile(
    r"(?i)("
    r"<script|javascript:|vbscript:|data:text/html|"
    r"\bunion\s+select\b|\bdrop\s+table\b|\bsleep\s*\(|\bbenchmark\s*\(|"
    r"\$\{jndi:|%24%7bjndi|"
    r"/etc/passwd|/proc/self|/windows/system32|file://|gopher://|dict://|"
    r"\x00|%00"
    r")"
)

# Endpoints that legitimately carry larger/ freer text in body only — path still filtered
_SKIP_PATH_PREFIXES = (
    "/health",
    "/ready",
    "/metrics",  # auth handled separately
)


@web.middleware
async def request_firewall_middleware(request: web.Request, handler):
    path = request.path or "/"
    raw_url = str(request.rel_url) if request.rel_url is not None else path

    if len(raw_url) > _MAX_URL_CHARS:
        logger.warning("firewall_url_too_long len=%s path=%s", len(raw_url), path[:80])
        return web.json_response({"ok": False, "error": "request_rejected"}, status=414)

    if "\x00" in path or "\x00" in raw_url:
        return web.json_response({"ok": False, "error": "request_rejected"}, status=400)

    if _TRAVERSAL.search(raw_url) or _TRAVERSAL.search(path):
        logger.warning("firewall_traversal path=%s", path[:120])
        return web.json_response({"ok": False, "error": "request_rejected"}, status=400)

    # Skip probe scan only for pure health — still scan API routes
    if not any(path == p or path.startswith(p + "/") for p in ("/health", "/ready")):
        if _PROBE.search(path) or _PROBE.search(raw_url):
            logger.warning("firewall_probe path=%s", path[:120])
            return web.json_response({"ok": False, "error": "request_rejected"}, status=400)

    # Method allowlist for unexpected verbs on API
    if request.method not in {
        "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"
    }:
        return web.json_response({"ok": False, "error": "method_not_allowed"}, status=405)

    return await handler(request)


__all__ = ["request_firewall_middleware"]
