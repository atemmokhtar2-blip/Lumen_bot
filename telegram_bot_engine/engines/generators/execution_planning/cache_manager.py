"""
CacheManager — Specification 019

Provides a simple SHA-256 based cache for the Execution Plan so that
identical upstream artefacts do not trigger a full re-computation.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .report_data import (
    CacheInfo,
    CACHE_HIT,
    CACHE_MISS,
    CACHE_STALE,
    CACHE_DISABLED,
)

_log = logging.getLogger("engine.execution_planning.cache_manager")


class CacheManager:
    """In-memory cache for ExecutionPlan objects keyed by a content hash
    of the six upstream data sources.
    """

    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled
        self._store: Dict[str, Dict[str, Any]] = {}
        self._hits = 0

    def make_key(self, *source_payloads: Any) -> str:
        """Compute a deterministic cache key from the given payloads."""
        hasher = hashlib.sha256()
        for payload in source_payloads:
            try:
                if hasattr(payload, "to_dict"):
                    data = payload.to_dict()
                elif isinstance(payload, dict):
                    data = payload
                else:
                    data = {"repr": repr(payload)}
                serialised = json.dumps(data, sort_keys=True, default=str)
            except Exception:
                serialised = repr(payload)
            hasher.update(serialised.encode("utf-8"))
        return hasher.hexdigest()

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Return a cached plan dict or None on miss."""
        if not self._enabled:
            return None
        entry = self._store.get(key)
        if entry is None:
            return None
        self._hits += 1
        entry["hits"] = entry.get("hits", 0) + 1
        _log.debug("Cache HIT for key %s…", key[:12])
        return entry.get("plan")

    def put(self, key: str, plan_dict: Dict[str, Any]) -> CacheInfo:
        """Store a plan and return the corresponding CacheInfo."""
        info = CacheInfo(
            status=CACHE_MISS if self._enabled else CACHE_DISABLED,
            key=key,
            created_at=datetime.now(timezone.utc).isoformat(),
            hits=0,
        )
        if not self._enabled:
            return info

        self._store[key] = {
            "plan": plan_dict,
            "created_at": info.created_at,
            "hits": 0,
        }
        info.status = CACHE_MISS  # first write is always a miss
        return info

    def info_for_hit(self, key: str) -> CacheInfo:
        entry = self._store.get(key, {})
        return CacheInfo(
            status=CACHE_HIT,
            key=key,
            created_at=entry.get("created_at", ""),
            hits=entry.get("hits", 0),
        )

    def clear(self) -> None:
        self._store.clear()
        self._hits = 0


__all__ = ["CacheManager"]
