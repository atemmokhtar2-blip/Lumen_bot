"""Simple TTL cache (used by live_deployment and similar)."""
from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple


class TtlCacheManager:
    def __init__(self, ttl_seconds: float = 300.0) -> None:
        self._ttl = float(ttl_seconds)
        self._store: Dict[str, Tuple[float, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        item = self._store.get(key)
        if not item:
            return None
        ts, value = item
        if time.time() - ts > self._ttl:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.time(), value)

    def clear(self) -> None:
        self._store.clear()


# Alias expected by live_deployment
CacheManager = TtlCacheManager
