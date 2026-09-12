"""Edge WAF enforcement (Phase D) — real, not header-theater.

CF-Ray / CF-Connecting-IP alone are spoofable if the origin is reachable.
Production therefore requires one of:
  1) TBE_EDGE_WAF_SECRET  — shared secret injected by the edge (recommended)
  2) TBE_EDGE_WAF_OPTIONAL=1  — explicit operator opt-out (logged)

When the secret is set, only requests presenting it are accepted (constant-time).
Provider headers (CF-Ray, etc.) are additional signals, never sufficient alone in prod.
"""
from __future__ import annotations

import hmac
import logging
import os
from typing import Any

logger = logging.getLogger("lumen.api.edge_waf")


from lumen.platform.envutil import env_flag as _truthy


def edge_waf_required() -> bool:
    if (os.getenv("TBE_REQUIRE_EDGE_WAF") or "").strip() != "":
        return _truthy("TBE_REQUIRE_EDGE_WAF", "0")
    try:
        from lumen.platform.prod_security_gate import is_production_runtime

        if is_production_runtime():
            # Optional only with explicit dual-ACK (not a loose boolean)
            opt = (os.getenv("TBE_EDGE_WAF_OPTIONAL") or "").strip()
            ack = (os.getenv("TBE_EDGE_WAF_OPTIONAL_ACK") or "").strip()
            if opt in {"1", "true", "yes", "on"} and ack == "I_ACCEPT_PUBLIC_ORIGIN_WITHOUT_EDGE_WAF":
                return False
            return True
    except Exception:
        pass
    return False


def _provider() -> str:
    return (os.getenv("TBE_EDGE_WAF_PROVIDER") or "cloudflare").strip().lower()


def _edge_secret() -> str:
    return (os.getenv("TBE_EDGE_WAF_SECRET") or "").strip()


def _has_valid_secret(request: Any) -> bool:
    expected = _edge_secret()
    if not expected:
        return False
    headers = getattr(request, "headers", {}) or {}
    got = (
        headers.get("X-Lumen-Edge-Token")
        or headers.get("X-Edge-Token")
        or headers.get("X-Lumen-WAF-Token")
        or ""
    ).strip()
    if not got:
        return False
    return hmac.compare_digest(got, expected)


def _has_provider_mark(request: Any) -> bool:
    """Soft signal only — never sufficient alone in production."""
    prov = _provider()
    headers = getattr(request, "headers", {}) or {}
    if prov in {"cloudflare", "cf"}:
        if headers.get("CF-Ray") or headers.get("cf-ray"):
            return True
        if headers.get("CF-Connecting-IP") or headers.get("cf-connecting-ip"):
            return True
    if prov in {"aws", "aws_waf", "cloudfront"}:
        if headers.get("X-Amz-Cf-Id") or headers.get("X-Amzn-Trace-Id"):
            return True
    if prov in {"gcp", "cloud_armor", "google"}:
        if headers.get("X-Cloud-Trace-Context"):
            return True
    if prov in {"azure", "front_door"}:
        if headers.get("X-Azure-Ref"):
            return True
    return False


def _has_edge_mark(request: Any) -> bool:
    path = getattr(request, "path", "") or ""
    peer = getattr(request, "remote", "") or ""
    if peer in {"127.0.0.1", "::1"} and path in {"/ready", "/health", "/metrics"}:
        return True

    secret_ok = _has_valid_secret(request)
    if secret_ok:
        return True

    # Production: secret is mandatory unless explicitly optional
    try:
        from lumen.platform.prod_security_gate import is_production_runtime

        if is_production_runtime() and edge_waf_required():
            if not _edge_secret():
                # Misconfiguration: required but no secret → reject (fail closed)
                logger.error("edge_waf: production requires TBE_EDGE_WAF_SECRET")
                return False
            return False  # secret set but not presented
    except Exception:
        pass

    # Dev: allow provider marks without secret
    return _has_provider_mark(request)


async def edge_waf_middleware(request, handler):
    from aiohttp import web

    if not edge_waf_required():
        return await handler(request)
    if request.path in {"/ready", "/health"}:
        return await handler(request)
    if _has_edge_mark(request):
        return await handler(request)
    logger.warning(
        "edge_waf_rejected path=%s peer=%s provider=%s has_secret_cfg=%s",
        request.path,
        request.remote,
        _provider(),
        bool(_edge_secret()),
    )
    return web.json_response(
        {
            "ok": False,
            "error": "edge_waf_required",
            "detail": (
                "Origin is protected. Configure the provider WAF to inject "
                "X-Lumen-Edge-Token matching TBE_EDGE_WAF_SECRET, or set "
                "TBE_EDGE_WAF_OPTIONAL=1 only if the API is not public."
            ),
        },
        status=403,
    )


__all__ = ["edge_waf_middleware", "edge_waf_required", "_has_edge_mark"]
