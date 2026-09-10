"""Edge WAF / reverse-proxy presence check (Phase D).

When the API is public on the internet, production should sit behind the
provider's official WAF (Cloudflare, AWS WAF, GCP Cloud Armor, Azure WAF).

This middleware does not replace a real WAF — it refuses direct origin hits
when required so traffic is forced through the edge.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("lumen.api.edge_waf")


def _truthy(name: str, default: str = "0") -> bool:
    return (os.getenv(name) or default).strip().lower() in {"1", "true", "yes", "on"}


def edge_waf_required() -> bool:
    if (os.getenv("TBE_REQUIRE_EDGE_WAF") or "").strip() != "":
        return _truthy("TBE_REQUIRE_EDGE_WAF", "0")
    try:
        from lumen.platform.prod_security_gate import is_production_runtime

        if is_production_runtime():
            return not _truthy("TBE_EDGE_WAF_OPTIONAL", "0")
    except Exception:
        pass
    return False


def _provider() -> str:
    return (os.getenv("TBE_EDGE_WAF_PROVIDER") or "cloudflare").strip().lower()


def _has_edge_mark(request: Any) -> bool:
    """Detect that the request came through a known edge / WAF."""
    prov = _provider()
    headers = getattr(request, "headers", {}) or {}
    path = getattr(request, "path", "") or ""
    peer = getattr(request, "remote", "") or ""

    if prov in {"cloudflare", "cf"}:
        if headers.get("CF-Ray") or headers.get("cf-ray"):
            return True
        if headers.get("CF-Connecting-IP") or headers.get("cf-connecting-ip"):
            return True
    if prov in {"aws", "aws_waf", "cloudfront"}:
        if headers.get("X-Amz-Cf-Id") or headers.get("X-Amzn-Trace-Id"):
            return True
    if prov in {"gcp", "cloud_armor", "google"}:
        if headers.get("Via") and "google" in (headers.get("Via") or "").lower():
            return True
        if headers.get("X-Cloud-Trace-Context"):
            return True
    if prov in {"azure", "front_door"}:
        if headers.get("X-Azure-Ref") or headers.get("X-FD-HealthProbe"):
            return True

    expected = (os.getenv("TBE_EDGE_WAF_SECRET") or "").strip()
    if expected:
        got = (headers.get("X-Lumen-Edge-Token") or headers.get("X-Edge-Token") or "").strip()
        if got and got == expected:
            return True

    if peer in {"127.0.0.1", "::1"} and path in {"/ready", "/health", "/metrics"}:
        return True
    return False


async def edge_waf_middleware(request, handler):
    """aiohttp middleware — registered as bare coroutine (aiohttp wraps it)."""
    from aiohttp import web

    if not edge_waf_required():
        return await handler(request)
    if request.path in {"/ready", "/health"}:
        return await handler(request)
    if _has_edge_mark(request):
        return await handler(request)
    logger.warning(
        "edge_waf_rejected path=%s peer=%s provider=%s",
        request.path,
        request.remote,
        _provider(),
    )
    return web.json_response(
        {
            "ok": False,
            "error": "edge_waf_required",
            "detail": (
                "Direct origin access denied. Place the API behind the provider WAF "
                f"({_provider()}) or set TBE_EDGE_WAF_SECRET / TBE_EDGE_WAF_OPTIONAL=1."
            ),
        },
        status=403,
    )


__all__ = ["edge_waf_middleware", "edge_waf_required", "_has_edge_mark"]
