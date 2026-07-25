"""
Cache manager \u2014 caches the normalized model for performance.

The :class:`CacheManager` is the helper that caches the normalized
requirement model so the engine does not re-normalize when the
requirements have not changed.

The cache works by:
1. Computing a hash of the input requirements (the requirement
   intelligence report + the semantic understanding report + the
   user request).
2. Checking if a cached model exists for that hash.
3. If a cache hit, return the cached model.
4. If a cache miss, compute the new model and store it in the cache.

The cache is an in-memory cache (a simple dictionary).  The cache
manager is designed to be used by the engine in a single
generation session \u2014 it does not persist across sessions.

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
    NormalizedRequirement,
    NormalizationReport,
)


class CacheManager:
    """Manages the cache for the normalized requirement model.

    The cache manager computes a hash of the input requirements and
    checks if a cached model exists.  If the requirements have not
    changed, the cached model is returned.  Otherwise, the new model
    is computed and stored in the cache.
    """

    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled
        self._cache: Dict[str, NormalizationReport] = {}

    def get_cache_info(
        self,
        requirement_intelligence_data: Any,
        semantic_understanding_data: Any,
        request_data: Any,
    ) -> CacheInfo:
        """Compute the cache info for the given inputs.

        This does **not** check the cache or return a cached model.
        It only computes the cache key and returns the
        :class:`CacheInfo` describing the cache state.

        Parameters:
            requirement_intelligence_data: The requirement
                intelligence data (or None).
            semantic_understanding_data: The semantic
                understanding data (or None).
            request_data: The request data (or None).

        Returns:
            A :class:`CacheInfo` with the computed cache key and
            hash.
        """
        if not self._enabled:
            return CacheInfo(
                status=CACHE_DISABLED,
                cache_key="",
                requirements_hash="",
                hit=False,
            )

        cache_hash = self._compute_hash(
            requirement_intelligence_data,
            semantic_understanding_data,
            request_data,
        )
        cache_key = f"norm_{cache_hash[:16]}"

        hit = cache_key in self._cache

        return CacheInfo(
            status=CACHE_HIT if hit else CACHE_MISS,
            cache_key=cache_key,
            cached_at=datetime.now(timezone.utc).isoformat(),
            hit=hit,
            requirements_hash=cache_hash,
        )

    def get_cached(
        self,
        cache_info: CacheInfo,
    ) -> Optional[NormalizationReport]:
        """Return the cached model if available, or None.

        Parameters:
            cache_info: The cache info from :meth:`get_cache_info`.

        Returns:
            The cached :class:`NormalizationReport` if the cache
            was hit, or ``None``.
        """
        if not self._enabled:
            return None
        if not cache_info.hit:
            return None
        return self._cache.get(cache_info.cache_key)

    def store(
        self,
        cache_info: CacheInfo,
        report: NormalizationReport,
    ) -> None:
        """Store the normalized model in the cache.

        Parameters:
            cache_info: The cache info from :meth:`get_cache_info`.
            report: The normalized model to cache.
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
        requirement_intelligence_data: Any,
        semantic_understanding_data: Any,
        request_data: Any,
    ) -> str:
        """Compute a hash of the input data sources.

        The hash is a SHA-256 hash of the JSON serialization of the
        three data sources.  This ensures that if any of the data
        sources change, the hash changes and the cache is missed.
        """
        parts: List[str] = []

        if requirement_intelligence_data is not None:
            if hasattr(requirement_intelligence_data, "to_dict"):
                parts.append(json.dumps(
                    requirement_intelligence_data.to_dict(),
                    sort_keys=True, default=str,
                ))
            elif isinstance(requirement_intelligence_data, dict):
                parts.append(json.dumps(
                    requirement_intelligence_data,
                    sort_keys=True, default=str,
                ))

        if semantic_understanding_data is not None:
            if hasattr(semantic_understanding_data, "to_dict"):
                parts.append(json.dumps(
                    semantic_understanding_data.to_dict(),
                    sort_keys=True, default=str,
                ))
            elif isinstance(semantic_understanding_data, dict):
                parts.append(json.dumps(
                    semantic_understanding_data,
                    sort_keys=True, default=str,
                ))

        if request_data is not None:
            if hasattr(request_data, "to_dict"):
                parts.append(json.dumps(
                    request_data.to_dict(),
                    sort_keys=True, default=str,
                ))
            elif isinstance(request_data, dict):
                parts.append(json.dumps(
                    request_data,
                    sort_keys=True, default=str,
                ))
            elif isinstance(request_data, str):
                parts.append(request_data)

        combined = "|".join(parts)
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()


__all__ = ["CacheManager"]
