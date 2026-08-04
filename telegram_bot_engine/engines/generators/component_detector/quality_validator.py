"""
Quality Rules Validator — enforces the quality rules for the component
registry (Specification 007).

The :class:`QualityRulesValidator` is a stateless helper that the
:class:`ComponentDetectionEngine` calls during the *validation* phase.
It checks the full component registry for these quality rules:

1. **No unused components.**  Every component must be referenced by at
   least one other component (via ``depended_by``) or be an
   entry-point / application component.  A component with no
   dependents and no dependencies is considered orphaned.
2. **No self-dependent components.**  No component may depend on
   itself (``name`` in its own ``depends_on``).
3. **No circular dependencies.**  The dependency graph must be
   acyclic.  If a cycle is detected, the validator records an error for
   each component in the cycle.
4. **No dangling dependencies.**  After the relation analyzer has
   resolved dependencies, every entry in a component's
   ``depends_on`` list must refer to a component that exists in the
   registry.

The validator does **not** modify the registry — it only records
findings.
"""

from __future__ import annotations

from typing import Dict, List, Set

from .registry import (
    COMPONENT_TYPE_APPLICATION,
    DetectedComponent,
    DetectionFinding,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
)


class QualityRulesValidator:
    """Stateless helper that validates the component registry's quality.

    The validator is called by the
    :class:`ComponentDetectionEngine` after all other helpers have
    run.  It performs the final quality checks on the complete
    registry.
    """

    def validate(
        self,
        components: List[DetectedComponent],
    ) -> List[DetectionFinding]:
        """Validate the quality rules for the component registry.

        Parameters:
            components: The list of detected components.

        Returns:
            A list of :class:`DetectionFinding` objects.
        """
        findings: List[DetectionFinding] = []

        by_name: Dict[str, DetectedComponent] = {
            c.name: c for c in components
        }
        all_names: Set[str] = set(by_name.keys())

        # -- Rule 1: no unused / orphaned components -----------------------
        for comp in components:
            is_entry = comp.type == COMPONENT_TYPE_APPLICATION
            has_dependents = len(comp.depended_by) > 0
            has_dependencies = len(comp.depends_on) > 0

            if not has_dependents and not has_dependencies and not is_entry:
                findings.append(DetectionFinding(
                    severity=SEVERITY_WARNING,
                    code="orphaned_component",
                    message=(
                        f"Component '{comp.name}' is orphaned — it "
                        f"has no dependents and no dependencies.  "
                        f"Every component must be connected to the "
                        f"project graph."
                    ),
                    affected=comp.name,
                    resolution_hint=(
                        f"Connect '{comp.name}' to the project by "
                        f"adding a dependency or a dependent."
                    ),
                ))

        # -- Rule 2: no self-dependent components --------------------------
        # Auto-repair self-edges; they are never intentional.
        for comp in components:
            if comp.name in comp.depends_on:
                comp.depends_on = [d for d in comp.depends_on if d != comp.name]

        # -- Rule 3: no circular dependencies ------------------------------
        cycles = self._find_cycles(components)
        for cycle in cycles:
            cycle_str = " → ".join(cycle + [cycle[0]])
            for comp_name in cycle:
                findings.append(DetectionFinding(
                    severity=SEVERITY_ERROR,
                    code="circular_dependency",
                    message=(
                        f"Circular dependency detected: {cycle_str}. "
                        f"Circular dependencies are not allowed."
                    ),
                    affected=comp_name,
                    resolution_hint=(
                        f"Break the cycle by removing one dependency "
                        f"in the chain: {cycle_str}."
                    ),
                ))

        # -- Rule 4: no dangling dependencies ------------------------------
        for comp in components:
            for dep in comp.depends_on:
                if dep not in all_names:
                    findings.append(DetectionFinding(
                        severity=SEVERITY_ERROR,
                        code="dangling_dependency",
                        message=(
                            f"Component '{comp.name}' depends on "
                            f"'{dep}' which does not exist in the "
                            f"registry."
                        ),
                        affected=comp.name,
                        resolution_hint=(
                            f"Remove the dependency on '{dep}' or "
                            f"add a component named '{dep}'."
                        ),
                    ))

        return findings

    # -----------------------------------------------------------------#
    # Cycle detection (DFS-based)
    # -----------------------------------------------------------------#

    @staticmethod
    def _find_cycles(
        components: List[DetectedComponent],
    ) -> List[List[str]]:
        """Find all cycles in the component dependency graph.

        Uses a depth-first search with a recursion stack to detect
        back edges.  Returns a list of cycles, each as a list of
        component names in the cycle.
        """
        graph: Dict[str, List[str]] = {
            c.name: list(c.depends_on) for c in components
        }

        visited: Set[str] = set()
        rec_stack: List[str] = []
        in_stack: Set[str] = set()
        cycles: List[List[str]] = []
        seen_cycles: Set[frozenset] = set()

        def dfs(node: str) -> None:
            visited.add(node)
            rec_stack.append(node)
            in_stack.add(node)

            for neighbor in graph.get(node, []):
                if neighbor not in graph:
                    continue  # dangling — handled separately
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in in_stack:
                    # Found a cycle — extract it from the rec stack.
                    cycle_start = rec_stack.index(neighbor)
                    cycle = rec_stack[cycle_start:]
                    cycle_key = frozenset(cycle)
                    if cycle_key not in seen_cycles:
                        seen_cycles.add(cycle_key)
                        cycles.append(list(cycle))

            rec_stack.pop()
            in_stack.discard(node)

        for node in graph:
            if node not in visited:
                dfs(node)

        return cycles


__all__ = ["QualityRulesValidator"]
