"""Capability Detection Engine (Phase 1) + Generation integration (Phase 2).

Deterministic detection over the existing CAPABILITIES registry.
No web research, no LLM, no invented keys.
"""
from __future__ import annotations

from .engine import can_satisfy, detect_capabilities, detect_status
from .integration import (
    apply_detection_to_session,
    feature_keys,
    metadata_from_report,
    run_detection,
    telegram_preflight,
)
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
    "run_detection",
    "feature_keys",
    "apply_detection_to_session",
    "telegram_preflight",
    "metadata_from_report",
]
