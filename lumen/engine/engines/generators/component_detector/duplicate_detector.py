"""
Duplicate Detector — finds and merges duplicate components
(Specification 007).

The :class:`DuplicateDetector` is a stateless helper that the
:class:`ComponentDetectionEngine` calls during the *deduplication*
phase.  It scans the list of :class:`DetectedComponent` objects and
finds components that perform the same function — same name, same type
plus same source blueprint component, or same type plus same location —
and merges them into a single component.

Two components are considered **duplicates** when any of the following
is true:

1. They have the **same name** (case-insensitive).
2. They have the **same type** *and* the **same source blueprint
   component**.
3. They have the **same type** *and* the **same location** (file path)
   — only when the location is non-empty.

When duplicates are found, the detector:

* keeps the first component (by detection order),
* merges the metadata and reverse-dependency links of the duplicates
  into it,
* records a :class:`DetectionFinding` describing the merge,
* returns the merged list and the findings.

Components with an empty source blueprint component and empty location
are **never** merged by rules 2 and 3 — only by rule 1 (exact name
match) — to avoid falsely merging unrelated utility components.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from .registry import (
    DetectedComponent,
    DetectionFinding,
    SEVERITY_WARNING,
)


class DuplicateDetector:
    """Stateless helper that detects and merges duplicate components.

    The detector is called by the
    :class:`ComponentDetectionEngine` after the
    :class:`TypeDetector` has produced the initial list of components.
    It returns a deduplicated list and a list of findings describing
    any merges that occurred.
    """

    def detect(
        self,
        components: List[DetectedComponent],
    ) -> Tuple[List[DetectedComponent], List[DetectionFinding]]:
        """Detect and merge duplicate components.

        Parameters:
            components: The list of detected components.

        Returns:
            A tuple ``(merged, findings)`` where:

            * ``merged`` is the deduplicated list of
              :class:`DetectedComponent` objects.
            * ``findings`` is the list of
              :class:`DetectionFinding` objects describing merges.
        """
        if not components:
            return [], []

        findings: List[DetectionFinding] = []
        merged: List[DetectedComponent] = []

        # Three separate lookup tables, each mapping a key to the index
        # of the *keeper* component in ``merged``.
        by_name: Dict[str, int] = {}
        by_type_source: Dict[str, int] = {}
        by_type_location: Dict[str, int] = {}

        for comp in components:
            # Compute the three keys.
            name_key = comp.name.lower()

            type_source_key = ""
            if comp.source_blueprint_component:
                type_source_key = (
                    f"{comp.type}:{comp.source_blueprint_component.lower()}"
                )

            type_location_key = ""
            if comp.location:
                type_location_key = f"{comp.type}:{comp.location.lower()}"

            # Check all three tables for an existing keeper.
            dup_idx: int = -1

            if name_key in by_name:
                dup_idx = by_name[name_key]
            elif type_source_key and type_source_key in by_type_source:
                dup_idx = by_type_source[type_source_key]
            elif type_location_key and type_location_key in by_type_location:
                dup_idx = by_type_location[type_location_key]

            if dup_idx >= 0:
                # Merge this component into the keeper.
                keeper = merged[dup_idx]
                self._merge(keeper, comp)
                findings.append(DetectionFinding(
                    severity=SEVERITY_WARNING,
                    code="duplicate_component",
                    message=(
                        f"Component '{comp.name}' (type="
                        f"'{comp.type}') was merged into "
                        f"'{keeper.name}' — duplicate detected."
                    ),
                    affected=comp.name,
                    resolution_hint=(
                        f"Use '{keeper.name}' for all references to "
                        f"this component."
                    ),
                ))
            else:
                # New unique component — record it in all tables.
                idx = len(merged)
                merged.append(comp)
                by_name[name_key] = idx
                if type_source_key:
                    by_type_source[type_source_key] = idx
                if type_location_key:
                    by_type_location[type_location_key] = idx

        return merged, findings

    # -----------------------------------------------------------------#
    # Helpers
    # -----------------------------------------------------------------#

    @staticmethod
    def _merge(keeper: DetectedComponent, dup: DetectedComponent) -> None:
        """Merge the duplicate component into the keeper."""
        # Merge metadata.
        for k, v in dup.metadata.items():
            if k not in keeper.metadata:
                keeper.metadata[k] = v

        # Merge depended_by.
        for dep in dup.depended_by:
            if dep not in keeper.depended_by:
                keeper.add_dependent(dep)

        # Merge depends_on (add any deps from the duplicate that the
        # keeper does not already have).
        for dep in dup.depends_on:
            if dep not in keeper.depends_on:
                keeper.add_dependency(dep)


__all__ = ["DuplicateDetector"]
