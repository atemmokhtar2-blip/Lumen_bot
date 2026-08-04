"""
Relation Analyzer — builds the dependency graph between detected
components (Specification 007).

The :class:`RelationAnalyzer` is a stateless helper that the
:class:`ComponentDetectionEngine` calls during the *relations* phase.
It takes the list of :class:`DetectedComponent` objects produced by the
:class:`TypeDetector` and:

1. resolves each component's ``depends_on`` list to *actual* detected
   component names (filtering out references to blueprint components
   that did not produce a detected component),
2. records the reverse ``depended_by`` links,
3. builds the list of :class:`ComponentDependencyEdge` objects that
   describe the wiring between components,
4. detects dangling dependencies (a component depends on a name that is
   not in the registry).

The analyzer does **not** create new components or modify the
blueprint.  It only wires the existing detected components together.
"""

from __future__ import annotations

from typing import Dict, List, Set, Tuple

from .registry import (
    ComponentDependencyEdge,
    DetectedComponent,
    SEVERITY_WARNING,
)


class RelationAnalyzer:
    """Stateless helper that builds the dependency graph of components.

    The analyzer is called by the
    :class:`ComponentDetectionEngine` after the
    :class:`TypeDetector` has produced the initial list of detected
    components.  It resolves dependencies, records reverse links, and
    produces the relationship edges.
    """

    def analyze(
        self,
        components: List[DetectedComponent],
    ) -> Tuple[List[ComponentDependencyEdge], List[str]]:
        """Analyze the relationships between detected components.

        Parameters:
            components: The list of detected components (mutated in
                place to fill in ``depended_by`` and clean
                ``depends_on``).

        Returns:
            A tuple ``(edges, warnings)`` where:

            * ``edges`` is the list of
              :class:`ComponentDependencyEdge` objects.
            * ``warnings`` is a list of warning messages about dangling
              dependencies.
        """
        # Build a name → component lookup.
        by_name: Dict[str, DetectedComponent] = {
            c.name: c for c in components
        }
        all_names: Set[str] = set(by_name.keys())

        edges: List[ComponentDependencyEdge] = []
        warnings: List[str] = []

        # Resolve depends_on and record reverse links.
        for comp in components:
            resolved: List[str] = []
            for dep in comp.depends_on:
                if dep in all_names:
                    if dep not in resolved:
                        resolved.append(dep)
                    # Record the reverse link.
                    dep_comp = by_name[dep]
                    if comp.name not in dep_comp.depended_by:
                        dep_comp.add_dependent(comp.name)
                    edges.append(ComponentDependencyEdge(
                        source=comp.name,
                        target=dep,
                        kind="depends_on",
                        description=(
                            f"{comp.name} depends on {dep}."
                        ),
                    ))
                else:
                    # Dangling dependency — the component depends on a
                    # name that is not in the registry.
                    warnings.append(
                        f"Component '{comp.name}' depends on "
                        f"'{dep}' which is not in the registry "
                        f"(dangling dependency)."
                    )
            # Replace depends_on with the resolved list.
            # Drop self-dependencies — they are never valid.
            comp.depends_on = [d for d in resolved if d != comp.name]

        return edges, warnings


__all__ = ["RelationAnalyzer"]
