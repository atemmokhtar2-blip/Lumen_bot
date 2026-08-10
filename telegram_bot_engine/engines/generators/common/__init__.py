"""Shared helpers for generator engines (DRY)."""
from .report_cache import build_report_cache_manager
from .ttl_cache import TtlCacheManager

__all__ = ["build_report_cache_manager", "TtlCacheManager"]
