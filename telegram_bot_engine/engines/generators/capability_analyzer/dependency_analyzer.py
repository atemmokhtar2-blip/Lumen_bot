"""
DependencyAnalyzer — Specification 017

Detects circular, unused, missing dependencies and dependency
conflicts in the project's architecture and technology selections.

The dependency analyzer does not write code, create files, install
libraries, or make build decisions.  It only analyses the
dependency health of the project.
"""

from __future__ import annotations

import logging
from typing import List

from .data_readers import (
    ArchitectureDecisionData,
    TechnologySelectionData,
    RequirementNormalizationData,
    IntelligenceGraphData,
    KnowledgeData,
)
from .report_data import (
    DependencyIssue,
    DependencyAnalysis,
    CapabilityFinding,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    SEVERITY_INFO,
    DIMENSION_DEPENDENCIES,
    DEP_ISSUE_CIRCULAR,
    DEP_ISSUE_UNUSED,
    DEP_ISSUE_MISSING,
    DEP_ISSUE_CONFLICT,
)

_log = logging.getLogger("engine.capability_analyzer.dependencies")


# ---------------------------------------------------------------------------#
# Known technology conflicts
# ---------------------------------------------------------------------------#
#
# Pairs of technologies that are known to conflict with each other.
# Each entry is (tech_a, tech_b, reason).

_KNOWN_CONFLICTS = [
    ("sqlite", "postgresql",
     "Both SQLite and PostgreSQL selected — choose one database."),
    ("sqlite", "mysql",
     "Both SQLite and MySQL selected — choose one database."),
    ("mysql", "postgresql",
     "Both MySQL and PostgreSQL selected — choose one database."),
    ("mongodb", "postgresql",
     "Mixing document and relational databases may cause "
     "data consistency issues."),
    ("celery", "kafka",
     "Celery and Kafka may overlap in background task processing."),
    ("redis", "memcached",
     "Both Redis and Memcached selected — choose one cache."),
    ("structlog", "loguru",
     "Both structlog and loguru selected — choose one logger."),
    ("pytest", "unittest",
     "Both pytest and unittest detected — standardize on one."),
]


class DependencyAnalyzer:
    """Detects circular, unused, missing dependencies and dependency
    conflicts.

    The analyzer examines:
    * The intelligence graph for circular dependencies.
    * The technology selections for conflicts and missing
      critical dependencies.
    * The architecture for unused or orphaned components.
    """

    def __init__(self) -> None:
        self.findings: List[CapabilityFinding] = []

    def analyze(
        self,
        arch_data: ArchitectureDecisionData,
        tech_data: TechnologySelectionData,
        req_data: RequirementNormalizationData,
        graph_data: IntelligenceGraphData,
        kb_data: KnowledgeData,
    ) -> DependencyAnalysis:
        """Perform the dependency analysis.

        Args:
            arch_data: Architecture decision data.
            tech_data: Technology selection data.
            req_data: Requirement normalization data.
            graph_data: Intelligence graph data.
            kb_data: Knowledge base data.

        Returns:
            A :class:`DependencyAnalysis` instance.
        """
        self.findings = []

        # ---- Count total dependencies ----
        total_deps = self._count_total_dependencies(
            arch_data, tech_data, graph_data
        )

        # ---- Detect circular dependencies ----
        circular = self._detect_circular(graph_data)

        # ---- Detect unused dependencies ----
        unused = self._detect_unused(arch_data, graph_data)

        # ---- Detect missing dependencies ----
        missing = self._detect_missing(arch_data, tech_data, req_data)

        # ---- Detect conflicts ----
        conflicts = self._detect_conflicts(tech_data)

        # ---- Build issues list ----
        issues = self._build_issues(
            circular, unused, missing, conflicts
        )

        # ---- Determine health ----
        is_healthy = (
            len(circular) == 0
            and len(conflicts) == 0
            and not any(
                i.severity == SEVERITY_ERROR for i in issues
            )
        )

        # ---- Score ----
        score = self._calculate_score(
            total_deps, len(circular), len(unused),
            len(missing), len(conflicts)
        )

        # ---- Summary and details ----
        details = []
        details.append(f"Total dependencies: {total_deps}")
        details.append(f"Circular dependencies: {len(circular)}")
        details.append(f"Unused dependencies: {len(unused)}")
        details.append(f"Missing dependencies: {len(missing)}")
        details.append(f"Conflicts: {len(conflicts)}")
        details.append(f"Healthy: {is_healthy}")

        if is_healthy:
            summary = (
                f"Dependency graph is healthy "
                f"({total_deps} dependencies, no issues)."
            )
        else:
            summary = (
                f"Dependency graph has issues: "
                f"{len(circular)} circular, {len(unused)} unused, "
                f"{len(missing)} missing, {len(conflicts)} conflicts."
            )

        # ---- Findings ----
        if len(circular) > 0:
            self.findings.append(CapabilityFinding(
                severity=SEVERITY_ERROR,
                code="circular_dependencies",
                message=(
                    f"{len(circular)} circular dependency/"
                    f"dependencies detected. Circular "
                    f"dependencies can cause deadlocks and "
                    f"prevent independent scaling."
                ),
                affected="dependencies",
                resolution_hint=(
                    "Break circular dependencies by "
                    "introducing interfaces, events, or "
                    "dependency inversion."
                ),
                category="dependencies",
            ))

        if len(conflicts) > 0:
            self.findings.append(CapabilityFinding(
                severity=SEVERITY_WARNING,
                code="dependency_conflicts",
                message=(
                    f"{len(conflicts)} technology conflict(s) "
                    f"detected in the technology selections."
                ),
                affected="dependencies",
                resolution_hint=(
                    "Resolve conflicting technology selections "
                    "by choosing one technology per category."
                ),
                category="dependencies",
            ))

        if len(missing) > 0:
            self.findings.append(CapabilityFinding(
                severity=SEVERITY_WARNING,
                code="missing_dependencies",
                message=(
                    f"{len(missing)} missing dependency/"
                    f"dependencies detected. The project may "
                    f"need additional components."
                ),
                affected="dependencies",
                resolution_hint=(
                    "Add the missing components or justify "
                    "their absence."
                ),
                category="dependencies",
            ))

        return DependencyAnalysis(
            total_dependencies=total_deps,
            circular_dependencies=circular,
            unused_dependencies=unused,
            missing_dependencies=missing,
            conflicts=conflicts,
            issues=issues,
            is_healthy=is_healthy,
            score=score,
            summary=summary,
            details=details,
        )

    # ----------------------------------------------------------------- #
    # Private helpers
    # ----------------------------------------------------------------- #

    def _count_total_dependencies(
        self,
        arch_data: ArchitectureDecisionData,
        tech_data: TechnologySelectionData,
        graph_data: IntelligenceGraphData,
    ) -> int:
        """Count the total number of dependencies in the project.

        Args:
            arch_data: Architecture decision data.
            tech_data: Technology selection data.
            graph_data: Intelligence graph data.

        Returns:
            The total dependency count.
        """
        # Graph edges represent dependencies.
        graph_deps = graph_data.edge_count

        # Technology selections are dependencies.
        tech_deps = tech_data.selection_count

        # Architecture modules/services have interdependencies.
        arch_deps = (
            arch_data.module_count
            + arch_data.service_count
        )

        return graph_deps + tech_deps + arch_deps

    def _detect_circular(
        self, graph_data: IntelligenceGraphData
    ) -> List[str]:
        """Detect circular dependencies from the intelligence graph.

        Args:
            graph_data: Intelligence graph data.

        Returns:
            A list of circular dependency descriptions.
        """
        circular: List[str] = []

        if graph_data.circular_count > 0:
            circular.append(
                f"{graph_data.circular_count} circular "
                f"dependency/dependencies detected in the "
                f"intelligence graph."
            )

        # Also check edges for back-references.
        edges = graph_data.edges
        if edges:
            # Build a simple adjacency list.
            adj: dict = {}
            for edge in edges:
                if isinstance(edge, dict):
                    src = edge.get("source", "")
                    tgt = edge.get("target", "")
                    if src and tgt:
                        adj.setdefault(src, []).append(tgt)

            # Simple cycle detection (limited).
            visited: set = set()
            for node in adj:
                if node in visited:
                    continue
                path: List[str] = []
                if self._has_cycle(node, adj, path, visited):
                    if path:
                        circular.append(
                            "Cycle detected: "
                            + " -> ".join(path)
                        )

        return circular

    def _has_cycle(
        self,
        node: str,
        adj: dict,
        path: List[str],
        visited: set,
    ) -> bool:
        """Check if there's a cycle starting from the given node.

        Uses a simple DFS with path tracking.

        Args:
            node: The current node.
            adj: The adjacency list.
            path: The current path.
            visited: The set of fully-visited nodes.

        Returns:
            True if a cycle is detected.
        """
        if node in path:
            return True
        if node in visited:
            return False

        path.append(node)
        for neighbor in adj.get(node, []):
            if self._has_cycle(neighbor, adj, path, visited):
                return True
        path.pop()
        visited.add(node)
        return False

    def _detect_unused(
        self,
        arch_data: ArchitectureDecisionData,
        graph_data: IntelligenceGraphData,
    ) -> List[str]:
        """Detect unused or orphaned dependencies.

        Args:
            arch_data: Architecture decision data.
            graph_data: Intelligence graph data.

        Returns:
            A list of unused dependency descriptions.
        """
        unused: List[str] = []

        # Check if there are nodes with no incoming edges
        # (orphaned components) — but only flag if there are many.
        if graph_data.node_count > 0 and graph_data.edge_count > 0:
            # Build a set of all nodes that are targets.
            targets: set = set()
            for edge in graph_data.edges:
                if isinstance(edge, dict):
                    tgt = edge.get("target", "")
                    if tgt:
                        targets.add(tgt)

            # Nodes that are never targets might be unused
            # (unless they're root/start nodes).
            all_nodes: set = set()
            for node in graph_data.nodes:
                if isinstance(node, dict):
                    nid = node.get("id", "")
                    if nid:
                        all_nodes.add(nid)

            # Only flag if there are orphaned nodes and the
            # graph is not tiny.
            orphaned = all_nodes - targets
            # Remove root nodes (those that have outgoing edges).
            sources: set = set()
            for edge in graph_data.edges:
                if isinstance(edge, dict):
                    src = edge.get("source", "")
                    if src:
                        sources.add(src)
            truly_orphaned = orphaned - sources

            if len(truly_orphaned) > 3:
                unused.append(
                    f"{len(truly_orphaned)} components have "
                    f"no incoming or outgoing edges — they "
                    f"may be unused."
                )

        # Check for unused modules.
        if arch_data.module_count > 0 and graph_data.node_count == 0:
            unused.append(
                "Architecture defines modules but the "
                "intelligence graph is empty — modules may "
                "be unused."
            )

        return unused

    def _detect_missing(
        self,
        arch_data: ArchitectureDecisionData,
        tech_data: TechnologySelectionData,
        req_data: RequirementNormalizationData,
    ) -> List[str]:
        """Detect missing dependencies.

        Args:
            arch_data: Architecture decision data.
            tech_data: Technology selection data.
            req_data: Requirement normalization data.

        Returns:
            A list of missing dependency descriptions.
        """
        missing: List[str] = []
        tech_list = [t.lower() for t in tech_data.selected_technologies]

        # Check for missing database when requirements mention data.
        has_db_req = any(
            isinstance(r, dict) and (
                "database" in str(r.get("name", "")).lower()
                or "storage" in str(r.get("name", "")).lower()
                or "persist" in str(r.get("description", "")).lower()
            )
            for r in req_data.requirements
        )
        if has_db_req and not any(
            t in tech_list
            for t in ("sqlite", "postgresql", "mysql", "mongodb")
        ):
            missing.append(
                "Requirements mention data storage but no "
                "database technology is selected."
            )

        # Check for missing cache when there are many requirements.
        if req_data.requirement_count > 10 and not any(
            t in tech_list for t in ("redis", "memcached")
        ):
            missing.append(
                "Project has many requirements but no caching "
                "layer — performance may degrade under load."
            )

        # Check for missing testing framework.
        if not any(
            t in tech_list
            for t in ("pytest", "unittest", "jest", "junit")
        ):
            if tech_data.available:
                missing.append(
                    "No testing framework detected in "
                    "technology selections."
                )

        return missing

    def _detect_conflicts(
        self, tech_data: TechnologySelectionData
    ) -> List[str]:
        """Detect technology conflicts.

        Args:
            tech_data: Technology selection data.

        Returns:
            A list of conflict descriptions.
        """
        conflicts: List[str] = []
        tech_list = [t.lower() for t in tech_data.selected_technologies]
        tech_set = set(tech_list)

        for tech_a, tech_b, reason in _KNOWN_CONFLICTS:
            if tech_a in tech_set and tech_b in tech_set:
                conflicts.append(reason)

        return conflicts

    def _build_issues(
        self,
        circular: List[str],
        unused: List[str],
        missing: List[str],
        conflicts: List[str],
    ) -> List[DependencyIssue]:
        """Build the list of DependencyIssue objects.

        Args:
            circular: Circular dependency descriptions.
            unused: Unused dependency descriptions.
            missing: Missing dependency descriptions.
            conflicts: Conflict descriptions.

        Returns:
            A list of :class:`DependencyIssue` objects.
        """
        issues: List[DependencyIssue] = []

        for desc in circular:
            issues.append(DependencyIssue(
                issue_type=DEP_ISSUE_CIRCULAR,
                component="dependency_graph",
                description=desc,
                severity=SEVERITY_ERROR,
                resolution=(
                    "Break the circular dependency by "
                    "introducing an interface, event, or "
                    "dependency inversion pattern."
                ),
            ))

        for desc in unused:
            issues.append(DependencyIssue(
                issue_type=DEP_ISSUE_UNUSED,
                component="orphaned_components",
                description=desc,
                severity=SEVERITY_WARNING,
                resolution=(
                    "Remove unused components or connect "
                    "them to the dependency graph."
                ),
            ))

        for desc in missing:
            issues.append(DependencyIssue(
                issue_type=DEP_ISSUE_MISSING,
                component="technology_stack",
                description=desc,
                severity=SEVERITY_WARNING,
                resolution=(
                    "Add the missing technology or justify "
                    "its absence."
                ),
            ))

        for desc in conflicts:
            issues.append(DependencyIssue(
                issue_type=DEP_ISSUE_CONFLICT,
                component="technology_selection",
                description=desc,
                severity=SEVERITY_WARNING,
                resolution=(
                    "Resolve the conflict by selecting one "
                    "technology per category."
                ),
            ))

        return issues

    def _calculate_score(
        self,
        total: int,
        circular_count: int,
        unused_count: int,
        missing_count: int,
        conflict_count: int,
    ) -> float:
        """Calculate the dependency health score.

        Args:
            total: Total dependencies.
            circular_count: Number of circular dependencies.
            unused_count: Number of unused dependencies.
            missing_count: Number of missing dependencies.
            conflict_count: Number of conflicts.

        Returns:
            A health score (0.0-1.0, higher = healthier).
        """
        if total == 0:
            return 1.0  # No dependencies = healthy by default.

        # Start at 1.0 and subtract penalties.
        score = 1.0
        score -= circular_count * 0.2  # Circular deps are severe.
        score -= conflict_count * 0.1
        score -= missing_count * 0.05
        score -= unused_count * 0.03

        return max(0.0, min(1.0, score))


__all__ = ["DependencyAnalyzer"]
