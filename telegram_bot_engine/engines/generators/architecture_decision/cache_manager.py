"""
Cache manager — caches the architecture decision for performance.

The :class:`CacheManager` is the helper that caches the
Architecture Decision Report so the engine does not re-decide when
the input data sources have not changed.

The cache works by:

1. Computing a hash of the input data sources (the normalized
   requirement model, the intelligence graph, the requirement
   intelligence report, the semantic understanding report, and the
   knowledge base).
2. Checking if a cached report exists for that hash.
3. If a cache hit, return the cached report.
4. If a cache miss, compute the new report and store it in the
   cache.

The cache is an in-memory cache (a simple dictionary).  The cache
manager is designed to be used by the engine in a single generation
session — it does not persist across sessions.

This module is a pure processing component: it has no side effects
on the generation context.  It only manages an internal cache.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .report_data import (
    CACHE_DISABLED,
    CACHE_HIT,
    CACHE_MISS,
    CacheInfo,
    ArchitectureDecisionReport,
)


class CacheManager:
    """Manages the cache for the Architecture Decision Report.

    The cache manager computes a hash of the input data sources and
    checks if a cached report exists.  If the inputs have not
    changed, the cached report is returned.  Otherwise, the new
    report is computed and stored in the cache.
    """

    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled
        self._cache: Dict[str, ArchitectureDecisionReport] = {}

    def get_cache_info(
        self,
        requirement_data: Any,
        graph_data: Any,
        requirement_intelligence_data: Any,
        semantic_data: Any,
        knowledge_data: Any,
    ) -> CacheInfo:
        """Compute the cache info for the given inputs.

        This does **not** check the cache or return a cached report.
        It only computes the cache key and returns the
        :class:`CacheInfo` describing the cache state.

        Parameters:
            requirement_data: The normalized requirement data.
            graph_data: The intelligence graph data.
            requirement_intelligence_data: The requirement
                intelligence data.
            semantic_data: The semantic understanding data.
            knowledge_data: The knowledge base data.

        Returns:
            A :class:`CacheInfo` with the computed cache key and
            hash.
        """
        if not self._enabled:
            return CacheInfo(
                status=CACHE_DISABLED,
                cache_key="",
                inputs_hash="",
                hit=False,
            )

        cache_hash = self._compute_hash(
            requirement_data,
            graph_data,
            requirement_intelligence_data,
            semantic_data,
            knowledge_data,
        )
        cache_key = f"arch_{cache_hash[:16]}"

        hit = cache_key in self._cache

        return CacheInfo(
            status=CACHE_HIT if hit else CACHE_MISS,
            cache_key=cache_key,
            cached_at=datetime.now(timezone.utc).isoformat(),
            hit=hit,
            inputs_hash=cache_hash,
        )

    def get_cached(
        self,
        cache_info: CacheInfo,
    ) -> Optional[ArchitectureDecisionReport]:
        """Return the cached report if available, or None.

        Parameters:
            cache_info: The cache info from
                :meth:`get_cache_info`.

        Returns:
            The cached :class:`ArchitectureDecisionReport` if the
            cache was hit, or ``None``.
        """
        if not self._enabled:
            return None
        if not cache_info.hit:
            return None
        return self._cache.get(cache_info.cache_key)

    def store(
        self,
        cache_info: CacheInfo,
        report: ArchitectureDecisionReport,
    ) -> None:
        """Store the report in the cache.

        Parameters:
            cache_info: The cache info from
                :meth:`get_cache_info`.
            report: The report to cache.
        """
        if not self._enabled:
            return
        if not cache_info.cache_key:
            return
        self._cache[cache_info.cache_key] = report

    def clear(self) -> None:
        """Clear the entire cache."""
        self._cache.clear()

    @property
    def size(self) -> int:
        """The number of entries in the cache."""
        return len(self._cache)

    @property
    def enabled(self) -> bool:
        """Whether the cache is enabled."""
        return self._enabled

    # ----------------------------------------------------------------- #
    # Internal helpers
    # ----------------------------------------------------------------- #

    def _compute_hash(
        self,
        requirement_data: Any,
        graph_data: Any,
        requirement_intelligence_data: Any,
        semantic_data: Any,
        knowledge_data: Any,
    ) -> str:
        """Compute a hash of the input data sources.

        The hash is a SHA-256 hash of the JSON serialization of the
        data sources.  This ensures that if any of the data sources
        change, the hash changes and the cache is missed.
        """
        parts: List[str] = []

        for data in (
            requirement_data,
            graph_data,
            requirement_intelligence_data,
            semantic_data,
            knowledge_data,
        ):
            if data is None:
                continue
            if hasattr(data, "to_dict"):
                parts.append(json.dumps(
                    data.to_dict(),
                    sort_keys=True, default=str,
                ))
            elif isinstance(data, dict):
                parts.append(json.dumps(
                    data, sort_keys=True, default=str,
                ))

        combined = "|".join(parts)
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()


__all__ = ["CacheManager"]
