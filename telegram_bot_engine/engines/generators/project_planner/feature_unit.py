"""
Feature Breakdown \u2014 each feature becomes an independent planning unit
(Specification 004).

The Project Planning Engine takes every :class:`Feature` from the
analysis report and converts it into a :class:`FeatureUnit` \u2014 a
self-contained planning unit that carries everything the rest of the
system needs to know about that feature:

* its identity (name, display name, description),
* its build priority,
* the components it introduces,
* the components/other features it depends on,
* the execution phase it belongs to,
* whether it can be built in parallel with other units.

A :class:`FeatureUnit` is **independent**: it never merges with another
feature.  If the user describes "warning and mute system" the analyzer
produces two :class:`Feature` objects and the planner produces two
:class:`FeatureUnit` objects.

The unit is a plain data container \u2014 no logic lives here.  The
planning engine populates it; downstream engines read it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Build priority levels
# ---------------------------------------------------------------------------

PRIORITY_CRITICAL = 10
PRIORITY_HIGH = 20
PRIORITY_NORMAL = 30
PRIORITY_LOW = 40
PRIORITY_DEFERRED = 50


@dataclass
class FeatureUnit:
    """A single feature broken down into an independent planning unit.

    Attributes:
        name: Machine name (e.g. ``"admin_panel"``).
        display_name: Human-readable name (e.g. ``"Admin Panel"``).
        description: What the feature does.
        source_feature: The name of the analysis :class:`Feature` this
            unit was derived from.
        build_priority: Numeric build priority.  Lower values are built
            first.  Use the ``PRIORITY_*`` constants.
        phase: The execution phase this feature belongs to (e.g.
            ``"phase_3_database"``, ``"phase_5_code_generation"``).
        introduces_components: The internal component names this
            feature introduces (e.g. ``["admin_panel"]``).
        depends_on_components: Internal component names this feature's
            components depend on.
        depends_on_features: Other feature unit names this one depends
            on.
        parallel_safe: ``True`` when this feature can be built in
            parallel with other features in the same phase.
        requires_database: ``True`` when this feature needs the
            database component.
        requires_config: ``True`` when this feature needs configuration
            entries (env vars, settings).
        confidence: 0.0\u20131.0 confidence carried over from the
            analysis feature.
        metadata: Free-form extra information.
    """

    name: str
    display_name: str = ""
    description: str = ""
    source_feature: str = ""
    build_priority: int = PRIORITY_NORMAL
    phase: str = ""
    introduces_components: List[str] = field(default_factory=list)
    depends_on_components: List[str] = field(default_factory=list)
    depends_on_features: List[str] = field(default_factory=list)
    parallel_safe: bool = True
    requires_database: bool = False
    requires_config: bool = False
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("FeatureUnit requires a non-empty name.")

    @property
    def is_critical(self) -> bool:
        return self.build_priority <= PRIORITY_CRITICAL

    @property
    def is_deferred(self) -> bool:
        return self.build_priority >= PRIORITY_DEFERRED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "source_feature": self.source_feature,
            "build_priority": self.build_priority,
            "phase": self.phase,
            "introduces_components": list(self.introduces_components),
            "depends_on_components": list(self.depends_on_components),
            "depends_on_features": list(self.depends_on_features),
            "parallel_safe": self.parallel_safe,
            "requires_database": self.requires_database,
            "requires_config": self.requires_config,
            "confidence": self.confidence,
            "metadata": dict(self.metadata),
        }


__all__ = [
    "FeatureUnit",
    "PRIORITY_CRITICAL",
    "PRIORITY_HIGH",
    "PRIORITY_NORMAL",
    "PRIORITY_LOW",
    "PRIORITY_DEFERRED",
]
