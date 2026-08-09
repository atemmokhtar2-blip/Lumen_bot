"""Advanced developer-partner layer — planning, versions, deep context."""

from .service import (
    AdvancedBrief,
    build_advanced_brief,
    maybe_snapshot_version,
    detect_advanced_intent,
)

__all__ = [
    "AdvancedBrief",
    "build_advanced_brief",
    "maybe_snapshot_version",
    "detect_advanced_intent",
]
