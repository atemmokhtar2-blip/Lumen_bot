"""CacheManager — Specification 034"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .report_data import CacheInfo, CACHE_HIT, CACHE_MISS, CACHE_DISABLED


class CacheManager:
    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled
        self._store: Dict[str, Dict[str, Any]] = {}

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        if not self._enabled:
            return None
        entry = self._store.get(key)
        if entry is None:
            return None
        entry["hits"] = entry.get("hits", 0) + 1
        return entry.get("payload")

    def put(self, key: str, payload: Dict[str, Any]) -> CacheInfo:
        if not self._enabled:
            return CacheInfo(status=CACHE_DISABLED, key=key)
        now = datetime.now(timezone.utc).isoformat()
        existing = self._store.get(key)
        hits = (existing.get("hits", 0) + 1) if existing else 0
        self._store[key] = {
            "payload": payload,
            "created_at": now,
            "hits": hits,
        }
        return CacheInfo(status=CACHE_MISS, key=key, created_at=now, hits=hits)

    def info_for_hit(self, key: str) -> CacheInfo:
        e = self._store.get(key, {})
        return CacheInfo(
            status=CACHE_HIT,
            key=key,
            created_at=e.get("created_at", ""),
            hits=e.get("hits", 0),
        )


__all__ = ["CacheManager"]
