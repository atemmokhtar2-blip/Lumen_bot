"""Single Redis connection entry — production TLS enforced.

Every process must obtain Redis via ``connect_redis`` (or ``connect_redis_url``).
Direct ``redis.Redis.from_url`` in application code is forbidden for new call sites.
"""
from __future__ import annotations

from typing import Any


def connect_redis_url(url: str | None = None, **kwargs: Any):
    """Connect with production TLS policy applied to the URL."""
    import redis

    from lumen.platform.prod_security_gate import enforce_redis_url_or_raise
    from lumen.platform.runtime_config import redis_url as _cfg_url

    raw = (url or _cfg_url() or "").strip()
    if not raw:
        raise RuntimeError("REDIS_URL is required")
    raw = enforce_redis_url_or_raise(raw)
    return redis.Redis.from_url(raw, **kwargs)


def connect_redis(**kwargs: Any):
    """Connect using runtime_config redis_url() + TLS policy."""
    return connect_redis_url(None, **kwargs)


__all__ = ["connect_redis", "connect_redis_url"]
