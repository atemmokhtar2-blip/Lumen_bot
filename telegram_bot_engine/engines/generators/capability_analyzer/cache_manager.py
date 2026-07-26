"""
CacheManager — Specification 017

Manages caching of the Project Capability Report for performance.
Caches the report based on a hash of the input data sources so
that the engine does not re-analyze when the inputs have not
changed.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, Dict, Optional

from .data_readers import (
    ArchitectureDecisionData,
    TechnologySelectionData,
    RequirementNormalizationData,
    IntelligenceGraphData,
    KnowledgeData,
)
from .report_data import (
    CacheInfo,
    ProjectCapabilityReport,
    CACHE_HIT,
    CACHE_MISS,
    CACHE_STALE,
    CACHE_DISABLED,
)

_log = logging.getLogger("engine.capability_analyzer.cache")


class CacheManager:
    """Manages caching of the Project Capability Report.

    Caches the report based on a hash of the input data sources.
    If the inputs have not changed, the cached report is returned
    instead of re-computing.
    """

    # Cache TTL in seconds (1 hour).
    _CACHE_TTL = 3600

    def __init__(self) -> None:
        self._cache: Dict[str, ProjectCapabilityReport] = {}
        self._cache_timestamps: Dict[str, float] = {}

    def get_cache_info(
        self,
        architecture_data: ArchitectureDecisionData,
        technology_data: TechnologySelectionData,
        requirement_data: RequirementNormalizationData,
        graph_data: IntelligenceGraphData,
        knowledge_data: KnowledgeData,
    ) -> CacheInfo:
        """Compute the cache info for the current inputs.

        Args:
            architecture_data: Architecture decision data.
            technology_data: Technology selection data.
            requirement_data: Requirement normalization data.
            graph_data: Intelligence graph data.
            knowledge_data: Knowledge base data.

        Returns:
            A :class:`CacheInfo` instance.
        """
        cache_key = self._compute_cache_key(
            architecture_data,
            technology_data,
            requirement_data,
            graph_data,
            knowledge_data,
        )

        info = CacheInfo(
            cache_key=cache_key,
        )

        # Check if the cache has an entry.
        if cache_key in self._cache:
            cached_at = self._cache_timestamps.get(cache_key, 0.0)
            now = time.time()
            age = now - cached_at

            if age > self._CACHE_TTL:
                info.status = CACHE_STALE
                info.cached_at = str(cached_at)
                info.inputs_hash = cache_key
            else:
                info.status = CACHE_HIT
                info.hit = True
                info.cached_at = str(cached_at)
                info.inputs_hash = cache_key
        else:
            info.status = CACHE_MISS
            info.inputs_hash = cache_key

        return info

    def get_cached(
        self, cache_info: CacheInfo
    ) -> Optional[ProjectCapabilityReport]:
        """Get the cached report if available.

        Args:
            cache_info: The cache info.

        Returns:
            The cached report, or None if not available.
        """
        if not cache_info.hit:
            return None

        key = cache_info.cache_key
        if key in self._cache:
            # Check TTL.
            cached_at = self._cache_timestamps.get(key, 0.0)
            if (time.time() - cached_at) <= self._CACHE_TTL:
                return self._cache[key]

        return None

    def store(
        self,
        cache_info: CacheInfo,
        report: ProjectCapabilityReport,
    ) -> None:
        """Store the report in the cache.

        Args:
            cache_info: The cache info.
            report: The Project Capability Report.
        """
        key = cache_info.cache_key
        self._cache[key] = report
        self._cache_timestamps[key] = time.time()

        # Mark the cache info as a hit so subsequent
        # get_cached() calls succeed.
        cache_info.hit = True
        cache_info.status = CACHE_HIT
        cache_info.cached_at = str(self._cache_timestamps[key])

        _log.info(
            "Project capability report cached",
            {"cache_key": key},
        )

    # ----------------------------------------------------------------- #
    # Private helpers
    # ----------------------------------------------------------------- #

    def _compute_cache_key(
        self,
        architecture_data: ArchitectureDecisionData,
        technology_data: TechnologySelectionData,
        requirement_data: RequirementNormalizationData,
        graph_data: IntelligenceGraphData,
        knowledge_data: KnowledgeData,
    ) -> str:
        """Compute a cache key from the input data.

        Args:
            architecture_data: Architecture decision data.
            technology_data: Technology selection data.
            requirement_data: Requirement normalization data.
            graph_data: Intelligence graph data.
            knowledge_data: Knowledge base data.

        Returns:
            A SHA-256 hash string.
        """
        parts = [
            f"arch:{architecture_data.decision_count}:"
            f"{architecture_data.pattern}:"
            f"{architecture_data.communication}",
            f"tech:{technology_data.selection_count}:"
            f"{technology_data.ready}",
            f"req:{requirement_data.requirement_count}",
            f"graph:{graph_data.node_count}:"
            f"{graph_data.edge_count}",
            f"kb:{len(getattr(knowledge_data, 'assumptions', []))}",
        ]
        raw = "|".join(parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:32]


__all__ = ["CacheManager"]
