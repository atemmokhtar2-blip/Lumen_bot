"""
ArchitectureRiskAnalyzer — Specification 018

Detects architecture-level risks before project generation begins:

* **Poor project partitioning** — too few or too many layers,
  uneven module sizes, god modules, missing layering.
* **Circular dependencies** — modules/services that depend on
  each other in a cycle, blocking clean extension.
* **Excessive coupling** — a module depending on too many other
  modules, making the system brittle to change.
* **Weak extensibility** — the architecture cannot easily
  accommodate new features or modules.

The analyzer does not write code, create files, or start the build.
It only detects and classifies architecture risks.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from .data_readers import (
    ProjectCapabilityData,
    ArchitectureDecisionData,
    TechnologySelectionData,
    RequirementNormalizationData,
    KnowledgeData,
)
from .report_data import (
    RiskItem,
    RiskDimensionResult,
    RiskFinding,
    DIMENSION_ARCHITECTURE,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    SEVERITY_LOW,
    ARCH_RISK_POOR_PARTITIONING,
    ARCH_RISK_CIRCULAR_DEPENDENCIES,
    ARCH_RISK_EXCESSIVE_COUPLING,
    ARCH_RISK_WEAK_EXTENSIBILITY,
    PRIORITY_IMMEDIATE,
    PRIORITY_HIGH,
    PRIORITY_MEDIUM,
    PRIORITY_LOW,
)

_log = logging.getLogger("engine.risk_detection.architecture")


# ---------------------------------------------------------------------------#
# Thresholds
# ---------------------------------------------------------------------------#

MIN_LAYERS = 2              # At least 2 layers for clean separation.
MAX_LAYERS = 10            # More than 10 layers is over-engineered.
MIN_MODULES = 1            # At least one module.
GOD_MODULE_THRESHOLD = 8   # A module with > 8 responsibilities is a god module.
COUPLING_THRESHOLD = 5     # A module depending on > 5 others is over-coupled.
COUPLING_CRITICAL = 10     # A module depending on > 10 others is critical.
EXTENSIBILITY_SCORE_MIN = 0.4  # Below this the extensibility is weak.


class ArchitectureRiskAnalyzer:
    """Detects architecture-level risks.

    The analyzer examines the architecture decision data, project
    capability report, and requirements to detect:
    * Poor project partitioning (god modules, missing layers,
      uneven distribution).
    * Circular dependencies.
    * Excessive coupling between modules.
    * Weak extensibility.
    """

    def __init__(self) -> None:
        self.findings: List[RiskFinding] = []
        self.risks: List[RiskItem] = []

    def analyze(
        self,
        cap_data: ProjectCapabilityData,
        arch_data: ArchitectureDecisionData,
        tech_data: TechnologySelectionData,
        req_data: RequirementNormalizationData,
        kb_data: KnowledgeData,
    ) -> RiskDimensionResult:
        """Perform the architecture risk analysis.

        Args:
            cap_data: Project capability data.
            arch_data: Architecture decision data.
            tech_data: Technology selection data.
            req_data: Requirement normalization data.
            kb_data: Knowledge base data.

        Returns:
            A :class:`RiskDimensionResult` for the architecture
            dimension.
        """
        self.findings = []
        self.risks = []

        # ---- Poor partitioning ----
        self._detect_poor_partitioning(
            arch_data, req_data, cap_data
        )

        # ---- Circular dependencies ----
        self._detect_circular_dependencies(arch_data, cap_data)

        # ---- Excessive coupling ----
        self._detect_excessive_coupling(arch_data)

        # ---- Weak extensibility ----
        self._detect_weak_extensibility(arch_data, req_data)

        # ---- Build the dimension result ----
        critical = sum(
            1 for r in self.risks if r.severity == SEVERITY_CRITICAL
        )
        high = sum(
            1 for r in self.risks if r.severity == SEVERITY_HIGH
        )
        medium = sum(
            1 for r in self.risks if r.severity == SEVERITY_MEDIUM
        )
        low = sum(
            1 for r in self.risks if r.severity == SEVERITY_LOW
        )

        score = self._calculate_score(self.risks)

        details: List[str] = []
        if arch_data.layers:
            details.append(
                f"Architecture layers: {len(arch_data.layers)} "
                f"({', '.join(arch_data.layers)})."
            )
        details.append(
            f"Modules: {arch_data.module_count}, "
            f"Services: {arch_data.service_count}."
        )
        if cap_data.circular_dependencies > 0:
            details.append(
                f"Capability report flagged "
                f"{cap_data.circular_dependencies} circular "
                f"dependencies."
            )
        details.append(
            f"Architecture risks detected: "
            f"{len(self.risks)} "
            f"(critical={critical}, high={high}, "
            f"medium={medium}, low={low})."
        )

        summary = (
            f"Architecture risk analysis: {len(self.risks)} risk(s) "
            f"detected across 4 architecture risk types."
        )

        return RiskDimensionResult(
            dimension=DIMENSION_ARCHITECTURE,
            risk_count=len(self.risks),
            critical_count=critical,
            high_count=high,
            medium_count=medium,
            low_count=low,
            score=score,
            summary=summary,
            details=details,
            risks=list(self.risks),
        )

    # ----------------------------------------------------------------- #
    # Poor partitioning
    # ----------------------------------------------------------------- #

    def _detect_poor_partitioning(
        self,
        arch_data: ArchitectureDecisionData,
        req_data: RequirementNormalizationData,
        cap_data: ProjectCapabilityData,
    ) -> None:
        """Detect poor project partitioning risks."""
        layer_count = len(arch_data.layers)
        module_count = arch_data.module_count
        req_count = req_data.requirement_count

        # Missing layering.
        if layer_count < MIN_LAYERS and module_count > 0:
            self._add_risk(
                risk_type=ARCH_RISK_POOR_PARTITIONING,
                severity=SEVERITY_HIGH,
                title="Insufficient architectural layering",
                description=(
                    f"The architecture has only {layer_count} "
                    f"layer(s), below the minimum of "
                    f"{MIN_LAYERS}. Without clear layering, "
                    f"concerns are mixed and the system is hard "
                    f"to maintain and test."
                ),
                cause=(
                    "The architecture decision did not define "
                    "enough layers to separate concerns (e.g. "
                    "presentation, business logic, data access)."
                ),
                impact=(
                    "Mixed concerns make the codebase brittle, "
                    "hard to test, and resistant to change. "
                    "A change in one area ripples to unrelated "
                    "areas."
                ),
                suggested_fix=(
                    "Define at least presentation, business-logic, "
                    "and data-access layers. Enforce the layering "
                    "with dependency rules and module boundaries."
                ),
                fix_priority=PRIORITY_HIGH,
                affected_components=["architecture", "layers"],
                reasoning=(
                    f"{layer_count} layer(s) < minimum "
                    f"{MIN_LAYERS} with {module_count} module(s)."
                ),
            )

        # Over-engineered layering.
        if layer_count > MAX_LAYERS:
            self._add_risk(
                risk_type=ARCH_RISK_POOR_PARTITIONING,
                severity=SEVERITY_MEDIUM,
                title="Over-engineered layering",
                description=(
                    f"The architecture has {layer_count} layers, "
                    f"exceeding the recommended maximum of "
                    f"{MAX_LAYERS}. Excessive layering adds "
                    f"indirection and complexity without benefit."
                ),
                cause=(
                    "Too many layers were defined, likely by "
                    "over-decomposing the architecture."
                ),
                impact=(
                    "Increased complexity, more boilerplate, "
                    "and slower development without clear benefit."
                ),
                suggested_fix=(
                    "Consolidate related layers. Aim for 3-6 "
                    "well-defined layers with clear "
                    "responsibilities."
                ),
                fix_priority=PRIORITY_MEDIUM,
                affected_components=["architecture", "layers"],
                reasoning=(
                    f"{layer_count} layers > maximum {MAX_LAYERS}."
                ),
            )

        # God module detection.
        god_modules = self._detect_god_modules(arch_data)
        if god_modules:
            self._add_risk(
                risk_type=ARCH_RISK_POOR_PARTITIONING,
                severity=SEVERITY_HIGH,
                title="God module(s) detected",
                description=(
                    f"{len(god_modules)} module(s) have an "
                    f"excessive number of responsibilities "
                    f"(>{GOD_MODULE_THRESHOLD}), indicating poor "
                    f"partitioning."
                ),
                cause=(
                    "A single module accumulates too many "
                    "responsibilities instead of being split "
                    "into cohesive, single-responsibility modules."
                ),
                impact=(
                    "God modules are hard to test, hard to "
                    "maintain, and prone to bugs. They violate "
                    "the single-responsibility principle."
                ),
                suggested_fix=(
                    "Split each god module into smaller, "
                    "cohesive modules with a single "
                    "responsibility each."
                ),
                fix_priority=PRIORITY_HIGH,
                affected_components=god_modules,
                reasoning=(
                    f"{len(god_modules)} module(s) with > "
                    f"{GOD_MODULE_THRESHOLD} responsibilities."
                ),
            )

        # No modules at all with requirements.
        if module_count == 0 and req_count > 0:
            self._add_risk(
                risk_type=ARCH_RISK_POOR_PARTITIONING,
                severity=SEVERITY_CRITICAL,
                title="No modules defined despite requirements",
                description=(
                    f"The architecture has {req_count} "
                    f"requirement(s) but no modules. The project "
                    f"is not partitioned at all."
                ),
                cause=(
                    "The architecture decision did not define "
                    "any modules to implement the requirements."
                ),
                impact=(
                    "Without modules, the project cannot be "
                    "built in a structured, maintainable way. "
                    "All logic would be in a single monolithic "
                    "file."
                ),
                suggested_fix=(
                    "Define modules that group related "
                    "requirements and assign clear "
                    "responsibilities to each."
                ),
                fix_priority=PRIORITY_IMMEDIATE,
                affected_components=["architecture", "modules"],
                reasoning=(
                    f"0 modules for {req_count} requirement(s)."
                ),
            )

    def _detect_god_modules(
        self, arch_data: ArchitectureDecisionData
    ) -> List[str]:
        """Detect modules with too many responsibilities."""
        god_modules: List[str] = []
        for m in arch_data.modules:
            if isinstance(m, dict):
                name = m.get("name", "") or m.get("id", "")
                responsibilities = m.get("responsibilities", [])
                if isinstance(responsibilities, list):
                    if len(responsibilities) > GOD_MODULE_THRESHOLD:
                        if name:
                            god_modules.append(name)
                else:
                    # If responsibilities is a string, count commas.
                    if isinstance(responsibilities, str):
                        count = len(
                            [
                                r for r in responsibilities.split(",")
                                if r.strip()
                            ]
                        )
                        if count > GOD_MODULE_THRESHOLD:
                            if name:
                                god_modules.append(name)
        return god_modules

    # ----------------------------------------------------------------- #
    # Circular dependencies
    # ----------------------------------------------------------------- #

    def _detect_circular_dependencies(
        self,
        arch_data: ArchitectureDecisionData,
        cap_data: ProjectCapabilityData,
    ) -> None:
        """Detect circular dependencies between modules."""
        # Primary source: the capability report already flagged
        # circular dependencies.
        circ_count = cap_data.circular_dependencies

        # Also inspect module dependencies directly.
        direct_circ = self._detect_module_cycles(arch_data)
        total_circ = max(circ_count, len(direct_circ))

        if total_circ > 0:
            severity = (
                SEVERITY_CRITICAL if total_circ >= 3
                else SEVERITY_HIGH
            )
            self._add_risk(
                risk_type=ARCH_RISK_CIRCULAR_DEPENDENCIES,
                severity=severity,
                title=(
                    f"{total_circ} circular "
                    f"dependency/dependencies detected"
                ),
                description=(
                    f"The architecture contains {total_circ} "
                    f"circular dependency/dependencies. Circular "
                    f"dependencies prevent clean module "
                    f"separation and make the system impossible "
                    f"to test or extend in isolation."
                ),
                cause=(
                    "Two or more modules depend on each other "
                    "directly or transitively, forming a cycle."
                ),
                impact=(
                    "Circular dependencies block independent "
                    "compilation, testing, and extension. They "
                    "are a leading cause of architectural decay."
                ),
                suggested_fix=(
                    "Break the cycle by introducing an interface "
                    "or abstraction, applying dependency "
                    "inversion, or extracting a shared module."
                ),
                fix_priority=(
                    PRIORITY_IMMEDIATE
                    if severity == SEVERITY_CRITICAL
                    else PRIORITY_HIGH
                ),
                affected_components=direct_circ or ["modules"],
                reasoning=(
                    f"{total_circ} circular "
                    f"dependency/dependencies found "
                    f"(capability={circ_count}, "
                    f"direct={len(direct_circ)})."
                ),
            )

    def _detect_module_cycles(
        self, arch_data: ArchitectureDecisionData
    ) -> List[str]:
        """Detect circular dependencies using DFS on module graph."""
        # Build adjacency list from module dependencies.
        graph: Dict[str, List[str]] = {}
        for m in arch_data.modules:
            if isinstance(m, dict):
                name = m.get("name", "") or m.get("id", "")
                if not name:
                    continue
                deps = m.get("dependencies", [])
                if isinstance(deps, list):
                    graph[name] = [
                        d for d in deps if isinstance(d, str)
                    ]
                else:
                    graph[name] = []

        if not graph:
            return []

        cycles: List[str] = []
        visited: set = set()
        rec_stack: set = set()

        def _dfs(node: str, path: List[str]) -> None:
            if node in rec_stack:
                # Found a cycle.
                cycle_start = path.index(node)
                cycle = path[cycle_start:] + [node]
                cycles.append(" -> ".join(cycle))
                return
            if node in visited:
                return
            visited.add(node)
            rec_stack.add(node)
            for neighbour in graph.get(node, []):
                _dfs(neighbour, path + [node])
            rec_stack.discard(node)

        for node in graph:
            if node not in visited:
                _dfs(node, [])

        return cycles

    # ----------------------------------------------------------------- #
    # Excessive coupling
    # ----------------------------------------------------------------- #

    def _detect_excessive_coupling(
        self, arch_data: ArchitectureDecisionData
    ) -> None:
        """Detect modules with excessive coupling."""
        over_coupled: List[str] = []
        critical_coupled: List[str] = []

        for m in arch_data.modules:
            if isinstance(m, dict):
                name = m.get("name", "") or m.get("id", "")
                if not name:
                    continue
                deps = m.get("dependencies", [])
                dep_count = (
                    len(deps) if isinstance(deps, list) else 0
                )
                if dep_count > COUPLING_CRITICAL:
                    critical_coupled.append(name)
                elif dep_count > COUPLING_THRESHOLD:
                    over_coupled.append(name)

        if critical_coupled:
            self._add_risk(
                risk_type=ARCH_RISK_EXCESSIVE_COUPLING,
                severity=SEVERITY_HIGH,
                title=(
                    f"Critical coupling in "
                    f"{len(critical_coupled)} module(s)"
                ),
                description=(
                    f"{len(critical_coupled)} module(s) depend "
                    f"on more than {COUPLING_CRITICAL} other "
                    f"modules, indicating critical over-coupling."
                ),
                cause=(
                    "Modules depend on too many other modules, "
                    "violating loose-coupling principles."
                ),
                impact=(
                    "Highly coupled modules are brittle: a change "
                    "in any dependency ripples through the entire "
                    "system."
                ),
                suggested_fix=(
                    "Reduce coupling by introducing interfaces, "
                    "applying the dependency-inversion principle, "
                    "or splitting over-coupled modules."
                ),
                fix_priority=PRIORITY_HIGH,
                affected_components=critical_coupled,
                reasoning=(
                    f"{len(critical_coupled)} module(s) with > "
                    f"{COUPLING_CRITICAL} dependencies."
                ),
            )

        if over_coupled:
            self._add_risk(
                risk_type=ARCH_RISK_EXCESSIVE_COUPLING,
                severity=SEVERITY_MEDIUM,
                title=(
                    f"Excessive coupling in "
                    f"{len(over_coupled)} module(s)"
                ),
                description=(
                    f"{len(over_coupled)} module(s) depend on "
                    f"more than {COUPLING_THRESHOLD} other "
                    f"modules, indicating excessive coupling."
                ),
                cause=(
                    "Modules depend on too many other modules."
                ),
                impact=(
                    "Over-coupled modules are harder to test, "
                    "maintain, and change independently."
                ),
                suggested_fix=(
                    "Reduce the number of direct dependencies "
                    "by introducing abstractions or "
                    "reorganising module boundaries."
                ),
                fix_priority=PRIORITY_MEDIUM,
                affected_components=over_coupled,
                reasoning=(
                    f"{len(over_coupled)} module(s) with > "
                    f"{COUPLING_THRESHOLD} dependencies."
                ),
            )

    # ----------------------------------------------------------------- #
    # Weak extensibility
    # ----------------------------------------------------------------- #

    def _detect_weak_extensibility(
        self,
        arch_data: ArchitectureDecisionData,
        req_data: RequirementNormalizationData,
    ) -> None:
        """Detect weak extensibility risks."""
        # Extensibility is weak when:
        # 1. No interfaces or abstractions are defined.
        # 2. The communication pattern is tightly coupled.
        # 3. No extension points (plugins, hooks) are present.

        has_interfaces = self._has_interfaces(arch_data)
        has_extension_points = self._has_extension_points(
            arch_data, req_data
        )

        score = 0.0
        if has_interfaces:
            score += 0.4
        if has_extension_points:
            score += 0.3
        if arch_data.communication and (
            "event" in arch_data.communication.lower()
            or "async" in arch_data.communication.lower()
            or "message" in arch_data.communication.lower()
        ):
            score += 0.3

        if score < EXTENSIBILITY_SCORE_MIN:
            severity = (
                SEVERITY_HIGH if score < 0.2 else SEVERITY_MEDIUM
            )
            self._add_risk(
                risk_type=ARCH_RISK_WEAK_EXTENSIBILITY,
                severity=severity,
                title="Weak extensibility",
                description=(
                    f"The architecture's extensibility score "
                    f"({score:.2f}) is below the minimum "
                    f"({EXTENSIBILITY_SCORE_MIN:.2f}). The "
                    f"architecture lacks interfaces, extension "
                    f"points, or decoupled communication."
                ),
                cause=(
                    "The architecture does not define interfaces, "
                    "extension points, or a decoupled "
                    "communication pattern to accommodate "
                    "future features."
                ),
                impact=(
                    "Adding new features requires modifying core "
                    "modules, increasing the risk of regression "
                    "and slowing down development."
                ),
                suggested_fix=(
                    "Introduce interfaces for key modules, "
                    "add plugin or hook extension points, and "
                    "adopt an event-driven or async "
                    "communication pattern."
                ),
                fix_priority=(
                    PRIORITY_HIGH if severity == SEVERITY_HIGH
                    else PRIORITY_MEDIUM
                ),
                affected_components=["architecture"],
                reasoning=(
                    f"Extensibility score {score:.2f} < "
                    f"{EXTENSIBILITY_SCORE_MIN:.2f} "
                    f"(interfaces={has_interfaces}, "
                    f"extension_points={has_extension_points})."
                ),
            )

    def _has_interfaces(
        self, arch_data: ArchitectureDecisionData
    ) -> bool:
        """Check if the architecture defines interfaces."""
        for d in arch_data.decisions:
            if isinstance(d, dict):
                domain = d.get("domain", "")
                if domain in ("interfaces", "contracts", "api"):
                    return True
                selected = str(d.get("selected", "")).lower()
                if "interface" in selected or "contract" in selected:
                    return True
        return False

    def _has_extension_points(
        self,
        arch_data: ArchitectureDecisionData,
        req_data: RequirementNormalizationData,
    ) -> bool:
        """Check if the architecture has extension points."""
        # Check for plugin/hook mentions in decisions.
        for d in arch_data.decisions:
            if isinstance(d, dict):
                selected = str(d.get("selected", "")).lower()
                if "plugin" in selected or "hook" in selected:
                    return True
        # Check for extension-point requirements.
        for req in req_data.requirements:
            if isinstance(req, dict):
                desc = str(req.get("description", "")).lower()
                name = str(req.get("name", "")).lower()
                if "plugin" in desc or "extension" in desc:
                    return True
                if "hook" in name or "extensible" in desc:
                    return True
        return False

    # ----------------------------------------------------------------- #
    # Helpers
    # ----------------------------------------------------------------- #

    def _add_risk(
        self,
        risk_type: str,
        severity: str,
        title: str,
        description: str,
        cause: str,
        impact: str,
        suggested_fix: str,
        fix_priority: str,
        affected_components: List[str],
        reasoning: str,
    ) -> None:
        """Add a risk item and a matching finding."""
        risk_id = f"arch_{risk_type}_{len(self.risks) + 1}"
        self.risks.append(RiskItem(
            risk_id=risk_id,
            dimension=DIMENSION_ARCHITECTURE,
            risk_type=risk_type,
            severity=severity,
            title=title,
            description=description,
            cause=cause,
            impact=impact,
            suggested_fix=suggested_fix,
            fix_priority=fix_priority,
            affected_components=list(affected_components),
            reasoning=reasoning,
        ))
        self.findings.append(RiskFinding(
            severity=severity,
            code=risk_id,
            message=title,
            affected="architecture",
            resolution_hint=suggested_fix,
            category="architecture",
        ))

    @staticmethod
    def _calculate_score(risks: List[RiskItem]) -> float:
        """Calculate the architecture risk score (0.0-1.0).

        Higher score = more risky.
        """
        if not risks:
            return 0.0
        scores = {
            SEVERITY_CRITICAL: 1.0,
            SEVERITY_HIGH: 0.75,
            SEVERITY_MEDIUM: 0.5,
            SEVERITY_LOW: 0.25,
        }
        total = sum(scores.get(r.severity, 0.25) for r in risks)
        # Normalise: a single critical = 1.0, saturate at 3 risks.
        return min(1.0, total / 2.0)


__all__ = ["ArchitectureRiskAnalyzer"]
