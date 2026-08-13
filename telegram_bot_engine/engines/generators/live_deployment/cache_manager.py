"""CacheManager — TTL cache via shared module (DRY)."""
from __future__ import annotations

from ..common.ttl_cache import TtlCacheManager as CacheManager

__all__ = ["CacheManager"]
