"""Shared in-memory report cache used by multiple generator engines."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Type


def build_report_cache_manager(
    CacheInfo: Type[Any],
    CACHE_HIT: str,
    CACHE_MISS: str,
    CACHE_DISABLED: str,
    *,
    value_key: str = "report",
) -> Type[Any]:
    """Factory: domain-specific CacheInfo constants → concrete CacheManager class."""

    class CacheManager:
        def __init__(self, enabled: bool = True) -> None:
            self._enabled = enabled
            self._store: Dict[str, Dict[str, Any]] = {}

        def make_key(self, *payloads: Any) -> str:
            h = hashlib.sha256()
            for p in payloads:
                try:
                    data = (
                        p.to_dict()
                        if hasattr(p, "to_dict")
                        else (p if isinstance(p, dict) else {"r": repr(p)})
                    )
                    h.update(json.dumps(data, sort_keys=True, default=str).encode())
                except Exception:
                    h.update(repr(p).encode())
            return h.hexdigest()

        def get(self, key: str) -> Optional[Dict[str, Any]]:
            if not self._enabled:
                return None
            entry = self._store.get(key)
            if entry is None:
                return None
            entry["hits"] = entry.get("hits", 0) + 1
            return entry.get(value_key)

        def put(self, key: str, value: Dict[str, Any]) -> Any:
            info = CacheInfo(
                status=CACHE_DISABLED if not self._enabled else CACHE_MISS,
                key=key,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            if self._enabled:
                self._store[key] = {
                    value_key: value,
                    "created_at": info.created_at,
                    "hits": 0,
                }
            return info

        def info_for_hit(self, key: str) -> Any:
            entry = self._store.get(key, {})
            return CacheInfo(
                status=CACHE_HIT,
                key=key,
                created_at=entry.get("created_at", ""),
                hits=entry.get("hits", 0),
            )

    CacheManager.__name__ = "CacheManager"
    return CacheManager
