"""Egress proxy for call_external_api actions — SSRF + rate limit."""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections import defaultdict
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_BLOCKED_HOST_PATTERNS = (
    r"^localhost$",
    r"^127\.",
    r"^0\.0\.0\.0$",
    r"^10\.",
    r"^192\.168\.",
    r"^172\.(1[6-9]|2[0-9]|3[0-1])\.",
    r"^169\.254\.",
    r"metadata\.google",
    r"^100\.64\.",  # carrier-grade NAT
)

_lock = threading.Lock()
_hits: dict[str, list[float]] = defaultdict(list)


def _rate_limit(key: str, limit: int, window: float) -> bool:
    now = time.time()
    with _lock:
        bucket = _hits[key]
        _hits[key] = [t for t in bucket if now - t < window]
        if len(_hits[key]) >= limit:
            return False
        _hits[key].append(now)
        return True


def validate_egress_url(url: str) -> str:
    raw = (url or "").strip()
    if len(raw) > 2048:
        raise ValueError("api_url_too_long")
    if not raw.startswith("https://"):
        raise ValueError("api_url_must_be_https")
    if any(x in raw.lower() for x in ("@", "\\", "file:", "gopher:", "dict:")):
        raise ValueError("api_url_scheme_or_userinfo_blocked")
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("api_url_host_missing")
    for pat in _BLOCKED_HOST_PATTERNS:
        if re.search(pat, host, re.I):
            raise ValueError("api_url_ssrf_blocked")
    # block AWS metadata-style
    if host in {"169.254.169.254", "metadata", "metadata.google.internal"}:
        raise ValueError("api_url_ssrf_blocked")
    return raw


def proxy_request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float = 10.0,
    tenant_key: str = "global",
) -> dict[str, Any]:
    """Safe HTTP egress for infinite actions."""
    safe_url = validate_egress_url(url)
    limit = int(os.getenv("TBE_API_PROXY_RPM") or "30")
    if not _rate_limit(f"egress:{tenant_key}", limit, 60.0):
        return {"ok": False, "error": "api_proxy_rate_limited"}
    try:
        import requests
        resp = requests.request(
            method.upper(),
            safe_url,
            headers={k: v for k, v in (headers or {}).items() if k.lower() not in {"host", "authorization"} or True},
            json=json_body,
            timeout=timeout,
            allow_redirects=False,  # prevent redirect-to-internal SSRF
        )
        return {
            "ok": 200 <= resp.status_code < 300,
            "status": resp.status_code,
            "body": (resp.text or "")[:4000],
        }
    except Exception as exc:
        logger.warning("api proxy failed: %s", type(exc).__name__)
        return {"ok": False, "error": type(exc).__name__}
