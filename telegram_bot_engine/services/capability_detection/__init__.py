"""Capability Detection Engine (Phase 1 — Dynamic Tool Builder foundation).

Deterministic detection over the existing CAPABILITIES registry.
No web research, no LLM, no invented keys.

Public API:
  detect_capabilities(request) -> DetectionReport
  detect_status(request) -> DetectionStatus
  can_satisfy(request) -> bool
  search_capabilities(query) -> ranked hits
"""
from __future__ import annotations

from .engine import can_satisfy, detect_capabilities, detect_status
from .models import DetectionReport, DetectionStatus, GapItem, MatchedCapability
from .search import nearest_keys_for_phrase, search_by_category, search_capabilities

__all__ = [
    "DetectionStatus",
    "MatchedCapability",
    "GapItem",
    "DetectionReport",
    "detect_capabilities",
    "detect_status",
    "can_satisfy",
    "search_capabilities",
    "search_by_category",
    "nearest_keys_for_phrase",
]
