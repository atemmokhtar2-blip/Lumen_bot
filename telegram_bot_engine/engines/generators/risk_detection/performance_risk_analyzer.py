"""
PerformanceRiskAnalyzer — Specification 018

Detects performance-level risks before project generation begins:

* **Potential bottlenecks** — synchronous calls on the hot path,
  N+1 query patterns, un-indexed lookups, single-threaded
  processing of parallel workloads.
* **High memory consumption** — large in-memory data structures,
  unbounded caches, full-table loads, image/file processing in
  memory.
* **Slow operations** — I/O-bound operations without async,
  expensive computations on the request path, lack of caching.
* **Unnecessary repetition** — redundant computation, repeated
  database queries, duplicate processing of the same data.

The analyzer does not write code, create files, or start the build.
It only detects and classifies performance risks.
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
    DIMENSION_PERFORMANCE,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    SEVERITY_LOW,
    PERF_RISK_BOTTLENECK,
    PERF_RISK_HIGH_MEMORY,
    PERF_RISK_SLOW_OPERATION,
    PERF_RISK_UNNECESSARY_REPETITION,
    PRIORITY_IMMEDIATE,
    PRIORITY_HIGH,
    PRIORITY_MEDIUM,
    PRIORITY_LOW,
)

_log = logging.getLogger("engine.risk_detection.performance")


# ---------------------------------------------------------------------------#
# Thresholds
# ---------------------------------------------------------------------------#

MEMORY_CRITICAL_MB = 1024    # > 1 GB is critical.
MEMORY_HIGH_MB = 512         # > 512 MB is high.
STRESS_SCORE_LOW = 0.4       # Below this, performance is at risk.
SCALABILITY_SCORE_LOW = 0.4  # Below this, growth is at risk.
BOTTLENECK_CRITICAL_COUNT = 3  # 3+ bottlenecks = critical.


class PerformanceRiskAnalyzer:
    """Detects performance-level risks.

    The analyzer examines the project capability report (stress
    score, bottlenecks, memory estimates), architecture decisions,
    technology selections, and requirements to detect:
    * Bottlenecks on the hot path.
    * High memory consumption patterns.
    * Slow synchronous operations.
    * Unnecessary repetition.
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
        """Perform the performance risk analysis.

        Args:
            cap_data: Project capability data.
            arch_data: Architecture decision data.
            tech_data: Technology selection data.
            req_data: Requirement normalization data.
            kb_data: Knowledge base data.

        Returns:
            A :class:`RiskDimensionResult` for the performance
            dimension.
        """
        self.findings = []
        self.risks = []

        # ---- Bottlenecks ----
        self._detect_bottlenecks(cap_data, arch_data)

        # ---- High memory ----
        self._detect_high_memory(cap_data, tech_data, req_data)

        # ---- Slow operations ----
        self._detect_slow_operations(
            cap_data, arch_data, tech_data, req_data
        )

        # ---- Unnecessary repetition ----
        self._detect_unnecessary_repetition(
            cap_data, req_data
        )

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
        if cap_data.stress_score > 0:
            details.append(
                f"Capability stress score: "
                f"{cap_data.stress_score:.2f}."
            )
        if cap_data.estimated_memory_mb > 0:
            details.append(
                f"Estimated memory: "
                f"{cap_data.estimated_memory_mb} MB."
            )
        if cap_data.bottlenecks:
            details.append(
                f"Bottlenecks from capability report: "
                f"{len(cap_data.bottlenecks)}."
            )
        details.append(
            f"Performance risks detected: "
            f"{len(self.risks)} "
            f"(critical={critical}, high={high}, "
            f"medium={medium}, low={low})."
        )

        summary = (
            f"Performance risk analysis: {len(self.risks)} risk(s) "
            f"detected across 4 performance risk types."
        )

        return RiskDimensionResult(
            dimension=DIMENSION_PERFORMANCE,
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
    # Bottlenecks
    # ----------------------------------------------------------------- #

    def _detect_bottlenecks(
        self,
        cap_data: ProjectCapabilityData,
        arch_data: ArchitectureDecisionData,
    ) -> None:
        """Detect potential bottlenecks."""
        bottleneck_count = len(cap_data.bottlenecks)

        # If the capability report already found bottlenecks,
        # classify them.
        if bottleneck_count >= BOTTLENECK_CRITICAL_COUNT:
            severity = SEVERITY_CRITICAL
            priority = PRIORITY_IMMEDIATE
        elif bottleneck_count > 0:
            severity = SEVERITY_HIGH
            priority = PRIORITY_HIGH
        elif cap_data.stress_score > 0 and (
            cap_data.stress_score < STRESS_SCORE_LOW
        ):
            # Low stress score with no explicit bottlenecks.
            severity = SEVERITY_HIGH
            priority = PRIORITY_HIGH
        else:
            return

        affected: List[str] = []
        for b in cap_data.bottlenecks:
            if isinstance(b, dict):
                comp = b.get("component", "")
                if comp:
                    affected.append(comp)

        if not affected:
            affected = ["hot_path"]

        self._add_risk(
            risk_type=PERF_RISK_BOTTLENECK,
            severity=severity,
            title=(
                f"{bottleneck_count} bottleneck(s) on the hot path"
                if bottleneck_count > 0
                else "Low stress score indicates bottlenecks"
            ),
            description=(
                f"The capability analysis identified "
                f"{bottleneck_count} bottleneck(s) "
                f"(stress score {cap_data.stress_score:.2f}). "
                f"Bottlenecks on the hot path degrade "
                f"response time and throughput."
                if bottleneck_count > 0
                else (
                    f"The architecture stress score "
                    f"({cap_data.stress_score:.2f}) is below "
                    f"the minimum ({STRESS_SCORE_LOW}), "
                    f"indicating potential bottlenecks."
                )
            ),
            cause=(
                "Synchronous processing of I/O-bound or "
                "CPU-bound work on the request path, or "
                "a single-threaded design for a parallel "
                "workload."
            ),
            impact=(
                "Bottlenecks increase latency, reduce "
                "throughput, and degrade user experience "
                "under load."
            ),
            suggested_fix=(
                "Offload expensive work to background tasks, "
                "introduce caching, parallelise independent "
                "operations, and use async I/O."
            ),
            fix_priority=priority,
            affected_components=affected,
            reasoning=(
                f"bottlenecks={bottleneck_count}, "
                f"stress_score={cap_data.stress_score:.2f}."
            ),
        )

    # ----------------------------------------------------------------- #
    # High memory
    # ----------------------------------------------------------------- #

    def _detect_high_memory(
        self,
        cap_data: ProjectCapabilityData,
        tech_data: TechnologySelectionData,
        req_data: RequirementNormalizationData,
    ) -> None:
        """Detect high memory consumption risks."""
        mem_mb = cap_data.estimated_memory_mb

        if mem_mb > MEMORY_CRITICAL_MB:
            severity = SEVERITY_CRITICAL
            priority = PRIORITY_IMMEDIATE
        elif mem_mb > MEMORY_HIGH_MB:
            severity = SEVERITY_HIGH
            priority = PRIORITY_HIGH
        else:
            # Check for technologies that imply high memory.
            high_mem_tech = self._detect_high_mem_tech(tech_data)
            if high_mem_tech:
                severity = SEVERITY_MEDIUM
                priority = PRIORITY_MEDIUM
                self._add_risk(
                    risk_type=PERF_RISK_HIGH_MEMORY,
                    severity=severity,
                    title=(
                        "High-memory technologies selected"
                    ),
                    description=(
                        f"The technology selection includes "
                        f"high-memory technologies: "
                        f"{', '.join(high_mem_tech)}. These may "
                        f"consume significant memory under load."
                    ),
                    cause=(
                        "Technologies like in-memory databases, "
                        "large ML models, or image processing "
                        "libraries have high memory footprints."
                    ),
                    impact=(
                        "High memory consumption can lead to "
                        "OOM errors, slow garbage collection, "
                        "and increased hosting costs."
                    ),
                    suggested_fix=(
                        "Use streaming or chunked processing, "
                        "optimise data structures, and plan "
                        "memory allocation carefully."
                    ),
                    fix_priority=priority,
                    affected_components=high_mem_tech,
                    reasoning=(
                        f"High-memory technologies: "
                        f"{', '.join(high_mem_tech)}."
                    ),
                )
            return

        self._add_risk(
            risk_type=PERF_RISK_HIGH_MEMORY,
            severity=severity,
            title=(
                f"High memory consumption "
                f"({mem_mb} MB estimated)"
            ),
            description=(
                f"The capability analysis estimates "
                f"{mem_mb} MB of memory usage, which "
                f"exceeds the {'critical' if severity == SEVERITY_CRITICAL else 'high'} "
                f"threshold "
                f"({MEMORY_CRITICAL_MB if severity == SEVERITY_CRITICAL else MEMORY_HIGH_MB} MB)."
            ),
            cause=(
                "Large in-memory data structures, unbounded "
                "caches, or full-table loads from the database."
            ),
            impact=(
                "High memory consumption can cause OOM errors, "
                "slow garbage collection, and increased "
                "infrastructure costs."
            ),
            suggested_fix=(
                "Use streaming, pagination, and bounded caches. "
                "Avoid loading entire datasets into memory. "
                "Consider a memory profiler during development."
            ),
            fix_priority=priority,
            affected_components=["memory", "resources"],
            reasoning=(
                f"estimated_memory={mem_mb} MB > "
                f"threshold="
                f"{MEMORY_CRITICAL_MB if severity == SEVERITY_CRITICAL else MEMORY_HIGH_MB}."
            ),
        )

    def _detect_high_mem_tech(
        self, tech_data: TechnologySelectionData
    ) -> List[str]:
        """Detect technologies with high memory footprints."""
        high_mem_keywords = (
            "tensorflow", "pytorch", "torch", "transformers",
            "elasticsearch", "opencv", "numpy", "pandas",
            "pillow", "pil",
        )
        found: List[str] = []
        for tech in tech_data.selected_technologies:
            name_lower = tech.lower()
            for kw in high_mem_keywords:
                if kw in name_lower:
                    found.append(tech)
                    break
        return found

    # ----------------------------------------------------------------- #
    # Slow operations
    # ----------------------------------------------------------------- #

    def _detect_slow_operations(
        self,
        cap_data: ProjectCapabilityData,
        arch_data: ArchitectureDecisionData,
        tech_data: TechnologySelectionData,
        req_data: RequirementNormalizationData,
    ) -> None:
        """Detect slow synchronous operations."""
        # If the architecture uses synchronous communication for
        # I/O-bound work, it's a slow-operation risk.
        comm = arch_data.communication.lower()
        has_async = (
            "async" in comm or "event" in comm
            or "message" in comm or "queue" in comm
        )

        # Check if caching technology is selected.
        has_cache = any(
            kw in t.lower()
            for t in tech_data.selected_technologies
            for kw in ("redis", "memcached", "cache")
        )

        if not has_async and arch_data.service_count > 2:
            # Multiple services with synchronous communication.
            self._add_risk(
                risk_type=PERF_RISK_SLOW_OPERATION,
                severity=SEVERITY_HIGH,
                title=(
                    "Synchronous inter-service communication"
                ),
                description=(
                    f"The architecture uses synchronous "
                    f"communication ('{arch_data.communication}') "
                    f"between {arch_data.service_count} "
                    f"services. Synchronous calls block the "
                    f"request thread and compound latency."
                ),
                cause=(
                    "Inter-service communication is synchronous "
                    "rather than asynchronous/event-driven."
                ),
                impact=(
                    "Each service call adds latency to the "
                    "request path. Under load, the system "
                    "becomes slow and may time out."
                ),
                suggested_fix=(
                    "Adopt async messaging (event bus, message "
                    "queue) for inter-service communication. "
                    "Use async I/O for database and external "
                    "calls."
                ),
                fix_priority=PRIORITY_HIGH,
                affected_components=["services", "communication"],
                reasoning=(
                    f"synchronous communication with "
                    f"{arch_data.service_count} services."
                ),
            )

        if not has_cache and req_has_data_heavy(req_data):
            self._add_risk(
                risk_type=PERF_RISK_SLOW_OPERATION,
                severity=SEVERITY_MEDIUM,
                title="No caching layer for data-heavy operations",
                description=(
                    "The technology selection does not include "
                    "a caching layer, but the requirements "
                    "imply data-heavy operations. Without "
                    "caching, repeated queries hit the database "
                    "directly."
                ),
                cause=(
                    "No cache technology (Redis, Memcached) "
                    "was selected despite data-heavy "
                    "requirements."
                ),
                impact=(
                    "Repeated database queries slow down "
                    "response time and increase database load."
                ),
                suggested_fix=(
                    "Add a caching layer (Redis or Memcached) "
                    "for frequently accessed data."
                ),
                fix_priority=PRIORITY_MEDIUM,
                affected_components=["database", "cache"],
                reasoning=(
                    "No cache technology selected with "
                    "data-heavy requirements."
                ),
            )

    # ----------------------------------------------------------------- #
    # Unnecessary repetition
    # ----------------------------------------------------------------- #

    def _detect_unnecessary_repetition(
        self,
        cap_data: ProjectCapabilityData,
        req_data: RequirementNormalizationData,
    ) -> None:
        """Detect unnecessary repetition risks."""
        # Repetition risks arise when:
        # 1. Multiple requirements share the same operation
        #    without deduplication.
        # 2. The architecture has no caching.
        # 3. There are duplicate functional requirements.

        duplicate_reqs = self._detect_duplicate_requirements(
            req_data
        )

        if duplicate_reqs:
            self._add_risk(
                risk_type=PERF_RISK_UNNECESSARY_REPETITION,
                severity=SEVERITY_MEDIUM,
                title=(
                    f"{len(duplicate_reqs)} duplicate "
                    f"requirement(s) detected"
                ),
                description=(
                    f"{len(duplicate_reqs)} requirement(s) "
                    f"appear to be duplicates, indicating "
                    f"potential unnecessary repetition in "
                    f"the implementation."
                ),
                cause=(
                    "Requirements were not deduplicated during "
                    "normalization, leading to repeated "
                    "implementation of the same logic."
                ),
                impact=(
                    "Duplicate logic wastes development effort, "
                    "increases code size, and creates "
                    "maintenance burden."
                ),
                suggested_fix=(
                    "Deduplicate requirements during "
                    "normalization. Consolidate duplicate "
                    "logic into shared modules."
                ),
                fix_priority=PRIORITY_MEDIUM,
                affected_components=["requirements"],
                reasoning=(
                    f"{len(duplicate_reqs)} duplicate "
                    f"requirement(s) found."
                ),
            )

    def _detect_duplicate_requirements(
        self, req_data: RequirementNormalizationData
    ) -> List[str]:
        """Detect duplicate requirements by name."""
        names: List[str] = []
        for req in req_data.requirements:
            if isinstance(req, dict):
                name = req.get("name", "") or req.get("id", "")
                if name:
                    names.append(name)

        seen: set = set()
        duplicates: List[str] = []
        for name in names:
            if name in seen:
                duplicates.append(name)
            else:
                seen.add(name)
        return duplicates

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
        risk_id = f"perf_{risk_type}_{len(self.risks) + 1}"
        self.risks.append(RiskItem(
            risk_id=risk_id,
            dimension=DIMENSION_PERFORMANCE,
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
            affected="performance",
            resolution_hint=suggested_fix,
            category="performance",
        ))

    @staticmethod
    def _calculate_score(risks: List[RiskItem]) -> float:
        """Calculate the performance risk score (0.0-1.0)."""
        if not risks:
            return 0.0
        scores = {
            SEVERITY_CRITICAL: 1.0,
            SEVERITY_HIGH: 0.75,
            SEVERITY_MEDIUM: 0.5,
            SEVERITY_LOW: 0.25,
        }
        total = sum(scores.get(r.severity, 0.25) for r in risks)
        return min(1.0, total / 2.0)


def req_has_data_heavy(
    req_data: RequirementNormalizationData,
) -> bool:
    """Check if requirements imply data-heavy operations."""
    keywords = (
        "search", "query", "report", "analytics", "export",
        "import", "batch", "bulk", "list", "table",
    )
    for req in req_data.requirements:
        if isinstance(req, dict):
            desc = str(req.get("description", "")).lower()
            name = str(req.get("name", "")).lower()
            for kw in keywords:
                if kw in desc or kw in name:
                    return True
    return False


__all__ = ["PerformanceRiskAnalyzer"]
