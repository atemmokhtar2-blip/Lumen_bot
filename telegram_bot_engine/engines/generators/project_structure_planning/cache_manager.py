"""CacheManager — thin domain wrapper over shared report cache (DRY)."""
from __future__ import annotations

from ..common.report_cache import build_report_cache_manager
from .report_data import CacheInfo, CACHE_HIT, CACHE_MISS, CACHE_DISABLED

CacheManager = build_report_cache_manager(
    CacheInfo,
    CACHE_HIT,
    CACHE_MISS,
    CACHE_DISABLED,
    value_key='blueprint',
)

__all__ = ["CacheManager"]
