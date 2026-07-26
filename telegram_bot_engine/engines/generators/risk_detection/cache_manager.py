"""
CacheManager — Specification 018

Manages caching of the Risk Analysis Report for performance.

Caches the report based on a SHA-256 hash of the five input data
sources so that the engine does not re-analyze when the inputs
have not changed.

The cache key is computed from:
    * Project Capability Report data.
    * Architecture Decision Report data.
    * Technology Selection Report data.
    * Normalized Requirement Model data.
    * Knowledge Base data.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, Dict, Optional

from .data_readers import (
    ProjectCapabilityData,
    ArchitectureDecisionData,
    TechnologySelectionData,
    RequirementNormalizationData,
    KnowledgeData,
)
from .report_data import (
    CacheInfo,
    RiskAnalysisReport,
    CACHE_HIT,
    CACHE_MISS,
    CACHE_STALE,
    CACHE_DISABLED,
)

_log = logging.getLogger("engine.risk_detection.cache")


class CacheManager:
    """Manages caching of the Risk Analysis Report.

    Caches the report based on a hash of the five input data
    sources.  If the inputs have not changed, the cached report
    is returned instead of re-computing.
    """

    # Cache TTL in seconds (1 hour).
    _CACHE_TTL = 3600

    def __init__(self) -> None:
        self._cache: Dict[str, RiskAnalysisReport] = {}
        self._cache_timestamps: Dict[str, float] = {}

    def get_cache_info(
        self,
        capability_data: ProjectCapabilityData,
        architecture_data: ArchitectureDecisionData,
        technology_data: TechnologySelectionData,
        requirement_data: RequirementNormalizationData,
        knowledge_data: KnowledgeData,
    ) -> CacheInfo:
        """Compute the cache info for the current inputs.

        Args:
            capability_data: Project capability data.
            architecture_data: Architecture decision data.
            technology_data: Technology selection data.
            requirement_data: Requirement normalization data.
            knowledge_data: Knowledge base data.

        Returns:
            A :class:`CacheInfo` instance.
        """
        cache_key = self._compute_cache_key(
            capability_data,
            architecture_data,
            technology_data,
            requirement_data,
            knowledge_data,
        )

        info = CacheInfo(cache_key=cache_key)

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
    ) -> Optional[RiskAnalysisReport]:
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
        report: RiskAnalysisReport,
    ) -> None:
        """Store the report in the cache.

        Args:
            cache_info: The cache info.
            report: The Risk Analysis Report.
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
            "Risk analysis report cached",
            {"cache_key": key},
        )

    # ----------------------------------------------------------------- #
    # Private helpers
    # ----------------------------------------------------------------- #

    def _compute_cache_key(
        self,
        capability_data: ProjectCapabilityData,
        architecture_data: ArchitectureDecisionData,
        technology_data: TechnologySelectionData,
        requirement_data: RequirementNormalizationData,
        knowledge_data: KnowledgeData,
    ) -> str:
        """Compute a cache key from the input data.

        Args:
            capability_data: Project capability data.
            architecture_data: Architecture decision data.
            technology_data: Technology selection data.
            requirement_data: Requirement normalization data.
            knowledge_data: Knowledge base data.

        Returns:
            A SHA-256 hash string.
        """
        parts = [
            f"cap:{capability_data.ready}:"
            f"{capability_data.verdict}:"
            f"{capability_data.complexity_level}:"
            f"{capability_data.total_elements}:"
            f"{capability_data.scalability_score}:"
            f"{capability_data.dependency_health}",
            f"arch:{architecture_data.decision_count}:"
            f"{architecture_data.pattern}:"
            f"{architecture_data.module_count}:"
            f"{architecture_data.service_count}:"
            f"{architecture_data.communication}",
            f"tech:{technology_data.selection_count}:"
            f"{technology_data.ready}:"
            f"{len(technology_data.selected_technologies)}",
            f"req:{requirement_data.requirement_count}:"
            f"{len(requirement_data.non_functional)}:"
            f"{len(requirement_data.functional)}",
            f"kb:{len(getattr(knowledge_data, 'assumptions', []))}:"
            f"{len(getattr(knowledge_data, 'domain_rules', []))}",
        ]
        raw = "|".join(parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:32]


__all__ = ["CacheManager"]
