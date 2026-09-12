"""Shared helpers for GitHub App integration (no secrets in logs)."""
from __future__ import annotations

import base64
import logging
import os
from typing import Any

from lumen.platform.redis_client import connect_redis_url

logger = logging.getLogger(__name__)


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def github_redis():
    """Short-lived Redis client for GitHub state/activity (or None)."""
    try:
        from lumen.platform.runtime_config import redis_url as _ru
        url = (_ru() or "").strip()
    except Exception:
        url = (os.getenv("REDIS_URL") or os.getenv("JOB_REDIS_URL") or "").strip()
    if not url:
        return None
    try:
        import redis  # noqa: F401
        r = connect_redis_url(
            url,
            decode_responses=True,
            socket_connect_timeout=float(os.getenv("REDIS_CONNECT_TIMEOUT") or "2"),
            socket_timeout=float(os.getenv("REDIS_SOCKET_TIMEOUT") or "3"),
        )
        r.ping()
        return r
    except Exception:
        return None


# back-compat private names
_b64url = b64url
_b64url_decode = b64url_decode
_redis = github_redis

__all__ = [
    "b64url", "b64url_decode", "github_redis",
    "_b64url", "_b64url_decode", "_redis",
]
