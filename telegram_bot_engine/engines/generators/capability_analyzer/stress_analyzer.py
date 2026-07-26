"""
StressAnalyzer — Specification 017

Simulates high load on the architecture to identify bottlenecks,
sensitive components, and improvement points.

The stress analyzer does not write code, create files, or make
build decisions.  It only simulates load and identifies stress
points.
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
    Bottleneck,
    ArchitectureStressAnalysis,
    CapabilityFinding,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    DIMENSION_STRESS,
    LOAD_LIGHT,
    LOAD_MODERATE,
    LOAD_HEAVY,
    LOAD_PEAK,
    BOTTLENECK_CRITICAL,
    BOTTLENECK_MAJOR,
    BOTTLENECK_MINOR,
    BOTTLENECK_NONE,
)

_log = logging.getLogger("engine.capability_analyzer.stress")


# ---------------------------------------------------------------------------#
# Load level thresholds
# ---------------------------------------------------------------------------#
#
# Each load level corresponds to a number of concurrent users and
# requests per second.

_LOAD_THRESHOLDS = {
    LOAD_LIGHT: {"users": 100, "rps": 50, "required_factor": 0.2},
    LOAD_MODERATE: {"users": 1000, "rps": 200, "required_factor": 0.4},
    LOAD_HEAVY: {"users": 10000, "rps": 1000, "required_factor": 0.6},
    LOAD_PEAK: {"users": 100000, "rps": 5000, "required_factor": 0.8},
}

# Architecture pattern load tolerance.
_PATTERN_LOAD_TOLERANCE = {
    "monolith": 0.3,
    "layered": 0.4,
    "modular_monolith": 0.5,
    "microservices": 0.9,
    "event_driven": 0.85,
    "hexagonal": 0.6,
    "clean": 0.55,
    "default": 0.4,
}


class StressAnalyzer:
    """Simulates high load on the architecture and identifies
    bottlenecks, sensitive components, and improvement points.

    The analyzer estimates:
    * The maximum load level the architecture can sustain.
    * The maximum concurrent users.
    * The maximum requests per second.
    * Bottlenecks that limit performance.
    * Sensitive components that need careful handling.
    * Improvement points to increase throughput.
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
    ) -> ArchitectureStressAnalysis:
        """Perform the architecture stress analysis.

        Args:
            arch_data: Architecture decision data.
            tech_data: Technology selection data.
            req_data: Requirement normalization data.
            graph_data: Intelligence graph data.
            kb_data: Knowledge base data.

        Returns:
            An :class:`ArchitectureStressAnalysis` instance.
        """
        self.findings = []

        # ---- Compute the base load tolerance ----
        base_tolerance = self._compute_base_tolerance(arch_data)

        # ---- Compute technology load modifiers ----
        tech_modifier = self._compute_tech_modifier(tech_data)

        # ---- Compute complexity penalty ----
        complexity_penalty = self._compute_complexity_penalty(graph_data)

        # ---- Combined load factor ----
        combined = (
            (base_tolerance * 0.5)
            + (tech_modifier * 0.35)
            + (complexity_penalty * 0.15)
        )
        combined = max(0.0, min(1.0, combined))

        # ---- Determine max load level ----
        max_load = LOAD_LIGHT
        for level in [LOAD_PEAK, LOAD_HEAVY, LOAD_MODERATE, LOAD_LIGHT]:
            threshold = _LOAD_THRESHOLDS[level]["required_factor"]
            if combined >= threshold:
                max_load = level
                break

        # ---- Estimate max concurrent users and RPS ----
        max_users = self._estimate_max_users(combined, arch_data)
        max_rps = self._estimate_max_rps(combined, tech_data)

        # ---- Identify bottlenecks ----
        bottlenecks = self._identify_bottlenecks(
            arch_data, tech_data, graph_data, max_load
        )

        # ---- Identify sensitive components ----
        sensitive = self._identify_sensitive_components(
            arch_data, graph_data
        )

        # ---- Improvement points ----
        improvements = self._generate_improvements(
            arch_data, tech_data, bottlenecks
        )

        # ---- Score (higher = more robust) ----
        # Score is based on the max load level achieved.
        load_scores = {
            LOAD_LIGHT: 0.25,
            LOAD_MODERATE: 0.5,
            LOAD_HEAVY: 0.75,
            LOAD_PEAK: 1.0,
        }
        score = load_scores.get(max_load, 0.0)
        # Factor in bottleneck penalties.
        critical_count = sum(
            1 for b in bottlenecks
            if b.severity == BOTTLENECK_CRITICAL
        )
        major_count = sum(
            1 for b in bottlenecks
            if b.severity == BOTTLENECK_MAJOR
        )
        score -= (critical_count * 0.15) + (major_count * 0.05)
        score = max(0.0, min(1.0, score))

        # ---- Summary and details ----
        details = []
        details.append(
            f"Max load level: {max_load}"
        )
        details.append(
            f"Max concurrent users: {max_users}"
        )
        details.append(
            f"Max requests/second: {max_rps:.0f}"
        )
        details.append(
            f"Bottlenecks identified: {len(bottlenecks)}"
        )
        details.append(
            f"Sensitive components: {len(sensitive)}"
        )

        summary = (
            f"Architecture can sustain {max_load} load "
            f"({max_users} concurrent users, {max_rps:.0f} rps) "
            f"with {len(bottlenecks)} bottleneck(s)."
        )

        # ---- Findings ----
        if max_load in (LOAD_LIGHT, LOAD_MODERATE) and not arch_data.available:
            self.findings.append(CapabilityFinding(
                severity=SEVERITY_INFO,
                code="stress_defaults",
                message=(
                    "Architecture data was not available. "
                    "Stress analysis is based on defaults."
                ),
                affected="architecture_stress",
                resolution_hint=(
                    "Ensure the architecture decision report "
                    "is available for accurate stress analysis."
                ),
                category="stress",
            ))

        critical_bottlenecks = [
            b for b in bottlenecks
            if b.severity == BOTTLENECK_CRITICAL
        ]
        if critical_bottlenecks:
            self.findings.append(CapabilityFinding(
                severity=SEVERITY_WARNING,
                code="critical_bottlenecks",
                message=(
                    f"{len(critical_bottlenecks)} critical "
                    f"bottleneck(s) identified that may "
                    f"prevent the architecture from handling "
                    f"high load."
                ),
                affected="architecture_stress",
                resolution_hint=(
                    "Address critical bottlenecks before "
                    "proceeding with generation."
                ),
                category="stress",
            ))

        return ArchitectureStressAnalysis(
            load_level=max_load,
            bottlenecks=bottlenecks,
            sensitive_components=sensitive,
            improvement_points=improvements,
            max_concurrent_users=max_users,
            max_requests_per_second=max_rps,
            score=score,
            summary=summary,
            details=details,
        )

    # ----------------------------------------------------------------- #
    # Private helpers
    # ----------------------------------------------------------------- #

    def _compute_base_tolerance(
        self, arch_data: ArchitectureDecisionData
    ) -> float:
        """Compute the base load tolerance from the architecture
        pattern.

        Args:
            arch_data: Architecture decision data.

        Returns:
            A load tolerance factor (0.0-1.0).
        """
        pattern = arch_data.pattern.lower() if arch_data.pattern else ""
        return _PATTERN_LOAD_TOLERANCE.get(
            pattern, _PATTERN_LOAD_TOLERANCE["default"]
        )

    def _compute_tech_modifier(
        self, tech_data: TechnologySelectionData
    ) -> float:
        """Compute the technology load modifier.

        Technologies like caches, queues, and async frameworks
        improve load handling.

        Args:
            tech_data: Technology selection data.

        Returns:
            A modifier (0.0-1.0).
        """
        tech_list = [t.lower() for t in tech_data.selected_technologies]
        modifier = 0.3  # Base

        # Caching improves throughput.
        if any(t in tech_list for t in ("redis", "memcached")):
            modifier += 0.15

        # Message queues improve async processing.
        if any(t in tech_list for t in ("kafka", "rabbitmq")):
            modifier += 0.2

        # Async frameworks.
        if any(
            t in tech_list
            for t in ("celery", "asyncio", "aiohttp")
        ):
            modifier += 0.1

        # Non-scalable databases hurt.
        if "sqlite" in tech_list:
            modifier -= 0.15

        return max(0.0, min(1.0, modifier))

    def _compute_complexity_penalty(
        self, graph_data: IntelligenceGraphData
    ) -> float:
        """Compute a penalty based on project complexity.

        More complex projects (more components, more circular
        dependencies) are harder to scale under load.

        Args:
            graph_data: Intelligence graph data.

        Returns:
            A penalty factor (0.0-1.0, higher = more robust).
        """
        # Start at 1.0 (no penalty).
        penalty = 1.0

        # Circular dependencies are a major penalty.
        if graph_data.circular_count > 0:
            penalty -= min(0.3, graph_data.circular_count * 0.1)

        # Very high component count adds overhead.
        if graph_data.component_count > 50:
            penalty -= 0.1
        elif graph_data.component_count > 100:
            penalty -= 0.2

        return max(0.0, min(1.0, penalty))

    def _estimate_max_users(
        self, combined: float, arch_data: ArchitectureDecisionData
    ) -> int:
        """Estimate the maximum concurrent users.

        Args:
            combined: The combined load factor.
            arch_data: Architecture decision data.

        Returns:
            An estimated max concurrent user count.
        """
        # Base users from the combined factor.
        base = int(combined * 50000)

        # Adjust for service count (more services = more capacity).
        service_count = max(arch_data.service_count, 1)
        if service_count >= 5:
            base = int(base * 1.5)
        elif service_count >= 3:
            base = int(base * 1.2)

        return max(100, base)

    def _estimate_max_rps(
        self, combined: float, tech_data: TechnologySelectionData
    ) -> float:
        """Estimate the maximum requests per second.

        Args:
            combined: The combined load factor.
            tech_data: Technology selection data.

        Returns:
            An estimated max RPS.
        """
        base = combined * 3000.0

        tech_list = [t.lower() for t in tech_data.selected_technologies]
        if any(t in tech_list for t in ("redis", "memcached")):
            base *= 1.5
        if any(t in tech_list for t in ("kafka", "rabbitmq")):
            base *= 1.3
        if "sqlite" in tech_list:
            base *= 0.5

        return max(10.0, base)

    def _identify_bottlenecks(
        self,
        arch_data: ArchitectureDecisionData,
        tech_data: TechnologySelectionData,
        graph_data: IntelligenceGraphData,
        max_load: str,
    ) -> List[Bottleneck]:
        """Identify bottlenecks in the architecture.

        Args:
            arch_data: Architecture decision data.
            tech_data: Technology selection data.
            graph_data: Intelligence graph data.
            max_load: The max load level.

        Returns:
            A list of :class:`Bottleneck` objects.
        """
        bottlenecks: List[Bottleneck] = []
        tech_list = [t.lower() for t in tech_data.selected_technologies]
        pattern = arch_data.pattern.lower() if arch_data.pattern else ""

        # --- Database bottleneck ---
        if "sqlite" in tech_list:
            bottlenecks.append(Bottleneck(
                component="database",
                severity=BOTTLENECK_CRITICAL,
                load_level=LOAD_MODERATE,
                description=(
                    "SQLite has write locking that limits "
                    "concurrent writes."
                ),
                impact=(
                    "Database becomes a write bottleneck "
                    "under moderate load."
                ),
                improvement=(
                    "Migrate to PostgreSQL or MySQL for "
                    "concurrent write support."
                ),
            ))
        elif not any(
            t in tech_list
            for t in ("postgresql", "mysql", "mongodb")
        ):
            bottlenecks.append(Bottleneck(
                component="database",
                severity=BOTTLENECK_MAJOR,
                load_level=LOAD_HEAVY,
                description=(
                    "No production-grade database detected."
                ),
                impact=(
                    "Data persistence may become a "
                    "bottleneck under heavy load."
                ),
                improvement=(
                    "Select a production-grade database "
                    "(PostgreSQL, MySQL, MongoDB)."
                ),
            ))

        # --- Caching bottleneck ---
        if not any(t in tech_list for t in ("redis", "memcached")):
            if max_load in (LOAD_HEAVY, LOAD_PEAK):
                bottlenecks.append(Bottleneck(
                    component="cache",
                    severity=BOTTLENECK_MAJOR,
                    load_level=LOAD_HEAVY,
                    description=(
                        "No caching layer detected."
                    ),
                    impact=(
                        "Every request hits the database "
                        "directly, limiting throughput."
                    ),
                    improvement=(
                        "Add Redis or Memcached for caching "
                        "hot data."
                    ),
                ))

        # --- Monolith bottleneck ---
        if pattern == "monolith" and max_load in (LOAD_HEAVY, LOAD_PEAK):
            bottlenecks.append(Bottleneck(
                component="application",
                severity=BOTTLENECK_MAJOR,
                load_level=LOAD_HEAVY,
                description=(
                    "Monolithic architecture limits "
                    "horizontal scaling."
                ),
                impact=(
                    "Cannot scale individual components "
                    "independently under heavy load."
                ),
                improvement=(
                    "Consider modular monolith or "
                    "microservices for independent scaling."
                ),
            ))

        # --- Circular dependency bottleneck ---
        if graph_data.circular_count > 0:
            severity = (
                BOTTLENECK_CRITICAL
                if graph_data.circular_count > 3
                else BOTTLENECK_MAJOR
            )
            bottlenecks.append(Bottleneck(
                component="dependency_graph",
                severity=severity,
                load_level=LOAD_MODERATE,
                description=(
                    f"{graph_data.circular_count} circular "
                    f"dependency/dependencies detected."
                ),
                impact=(
                    "Circular dependencies can cause "
                    "deadlocks and prevent independent "
                    "scaling."
                ),
                improvement=(
                    "Break circular dependencies by "
                    "introducing interfaces or event-based "
                    "communication."
                ),
            ))

        # --- No background processing ---
        if not any(
            t in tech_list
            for t in ("celery", "kafka", "rabbitmq")
        ):
            if max_load in (LOAD_HEAVY, LOAD_PEAK):
                bottlenecks.append(Bottleneck(
                    component="background_processing",
                    severity=BOTTLENECK_MINOR,
                    load_level=LOAD_HEAVY,
                    description=(
                        "No message queue or background "
                        "task system detected."
                    ),
                    impact=(
                        "Long-running tasks block the "
                        "main thread under heavy load."
                    ),
                    improvement=(
                        "Add Celery, Kafka, or RabbitMQ "
                        "for asynchronous processing."
                    ),
                ))

        return bottlenecks

    def _identify_sensitive_components(
        self,
        arch_data: ArchitectureDecisionData,
        graph_data: IntelligenceGraphData,
    ) -> List[str]:
        """Identify sensitive components that need careful handling.

        Args:
            arch_data: Architecture decision data.
            graph_data: Intelligence graph data.

        Returns:
            A list of sensitive component names.
        """
        sensitive: List[str] = []

        # Database is always sensitive.
        sensitive.append("database")

        # Authentication/authorization services.
        if arch_data.service_count > 0:
            sensitive.append("authentication_service")

        # Communication layer.
        if arch_data.communication:
            sensitive.append("communication_layer")

        # High-degree nodes in the graph (many dependencies).
        if graph_data.node_count > 0:
            # If there are many edges relative to nodes, there
            # are likely hub components.
            if graph_data.edge_count > graph_data.node_count * 2:
                sensitive.append("high_coupling_components")

        # External integrations.
        if graph_data.component_count > 10:
            sensitive.append("external_integrations")

        return sensitive

    def _generate_improvements(
        self,
        arch_data: ArchitectureDecisionData,
        tech_data: TechnologySelectionData,
        bottlenecks: List[Bottleneck],
    ) -> List[str]:
        """Generate improvement suggestions.

        Args:
            arch_data: Architecture decision data.
            tech_data: Technology selection data.
            bottlenecks: The identified bottlenecks.

        Returns:
            A list of improvement suggestions.
        """
        improvements: List[str] = []
        tech_list = [t.lower() for t in tech_data.selected_technologies]

        # From bottlenecks.
        for b in bottlenecks:
            if b.improvement:
                improvements.append(b.improvement)

        # General improvements.
        if not any(t in tech_list for t in ("redis", "memcached")):
            improvements.append(
                "Add a caching layer (Redis/Memcached) to "
                "reduce database load."
            )

        if not any(
            t in tech_list for t in ("kafka", "rabbitmq", "celery")
        ):
            improvements.append(
                "Introduce a message queue for asynchronous "
                "processing of long-running tasks."
            )

        if arch_data.pattern.lower() in ("monolith", "layered"):
            improvements.append(
                "Consider migrating to a modular monolith "
                "or microservices architecture for better "
                "scalability."
            )

        # Deduplicate.
        seen = set()
        unique = []
        for imp in improvements:
            if imp not in seen:
                seen.add(imp)
                unique.append(imp)

        return unique


__all__ = ["StressAnalyzer"]
