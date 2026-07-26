"""
ResourceRiskAnalyzer — Specification 018

Detects resource-level risks before project generation begins.

The analyzer detects:
* **CPU-bound** — the design has computationally intensive
  operations on the request path.
* **Memory-bound** — the estimated memory consumption is too high.
* **Disk-bound** — the design involves heavy disk I/O.
* **Network-bound** — the design has excessive network round-trips.
* **Cost overrun** — the selected technologies or architecture
  pattern may lead to unexpected infrastructure costs.

The analyzer does not write code, create files, or start the build.
It only detects and classifies resource risks.
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
    DIMENSION_RESOURCE,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    SEVERITY_LOW,
    RES_RISK_CPU_BOUND,
    RES_RISK_MEMORY_BOUND,
    RES_RISK_DISK_BOUND,
    RES_RISK_NETWORK_BOUND,
    RES_RISK_COST_OVERRUN,
    PRIORITY_IMMEDIATE,
    PRIORITY_HIGH,
    PRIORITY_MEDIUM,
    PRIORITY_LOW,
)

_log = logging.getLogger("engine.risk_detection.resource")


# ---------------------------------------------------------------------------#
# Thresholds and keyword sets
# ---------------------------------------------------------------------------#

# Memory thresholds (in MB).
MEMORY_CRITICAL_MB = 2048       # Above 2 GB is critical.
MEMORY_HIGH_MB = 1024           # Above 1 GB is high risk.
MEMORY_MEDIUM_MB = 512          # Above 512 MB is medium risk.

# File count thresholds.
FILE_COUNT_HIGH = 500           # Above 500 files is a lot.
FILE_COUNT_CRITICAL = 2000      # Above 2000 files is critical.

# CPU-intensive technology keywords.
_CPU_INTENSIVE_KEYWORDS = (
    "tensorflow", "pytorch", "opencv", "numpy", "scipy",
    "pandas", "image", "video", "ml", "ai", "model",
    "render", "compute", "cryptomin", "ffmpeg",
)

# Disk I/O intensive keywords.
_DISK_INTENSIVE_KEYWORDS = (
    "sqlite", "file storage", "elasticsearch", "log",
    "backup", "archive", "etl", "data lake",
)

# Network-intensive technology keywords.
_NETWORK_INTENSIVE_KEYWORDS = (
    "http", "grpc", "rest", "api", "webhook", "graphql",
    "websocket", "stream", "sync",
)

# Cost-intensive technology / infrastructure keywords.
_COST_INTENSIVE_KEYWORDS = (
    "aws", "azure", "gcp", "kubernetes", "eks", "gke",
    "cloud", "managed", "premium", "enterprise",
    "dynamodb", "aurora", "redshift", "snowflake",
)


class ResourceRiskAnalyzer:
    """Detects resource-level risks.

    The analyzer examines the project capability report
    (memory, file count), technology selections, and
    architecture to detect:
    * CPU-bound operations.
    * High memory consumption.
    * Disk I/O bottlenecks.
    * Network round-trip overhead.
    * Cost overrun potential.
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
        """Perform the resource risk analysis.

        Args:
            cap_data: Project capability data.
            arch_data: Architecture decision data.
            tech_data: Technology selection data.
            req_data: Requirement normalization data.
            kb_data: Knowledge base data.

        Returns:
            A :class:`RiskDimensionResult` for the resource
            dimension.
        """
        self.findings = []
        self.risks = []

        # ---- CPU-bound ----
        self._detect_cpu_bound(tech_data, cap_data)

        # ---- Memory-bound ----
        self._detect_memory_bound(cap_data)

        # ---- Disk-bound ----
        self._detect_disk_bound(tech_data, cap_data)

        # ---- Network-bound ----
        self._detect_network_bound(arch_data, tech_data)

        # ---- Cost overrun ----
        self._detect_cost_overrun(tech_data, arch_data)

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
        if cap_data.available:
            details.append(
                f"Estimated memory: "
                f"{cap_data.estimated_memory_mb} MB."
            )
            details.append(
                f"Estimated file count: {cap_data.file_count}."
            )
            details.append(
                f"Stress score: {cap_data.stress_score:.2f}."
            )
        details.append(
            f"Resource risks detected: {len(self.risks)} "
            f"(critical={critical}, high={high}, "
            f"medium={medium}, low={low})."
        )

        summary = (
            f"Resource risk analysis: {len(self.risks)} "
            f"risk(s) detected."
        )

        return RiskDimensionResult(
            dimension=DIMENSION_RESOURCE,
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
    # CPU-bound
    # ----------------------------------------------------------------- #

    def _detect_cpu_bound(
        self,
        tech_data: TechnologySelectionData,
        cap_data: ProjectCapabilityData,
    ) -> None:
        """Detect CPU-bound operations."""
        if not tech_data.available:
            return

        cpu_techs = [
            t for t in tech_data.selected_technologies
            if any(
                kw in t.lower() for kw in _CPU_INTENSIVE_KEYWORDS
            )
        ]

        if not cpu_techs:
            return

        # Check if CPU-intensive techs are on the request path
        # (indicated by low stress score from cap report).
        on_request_path = (
            cap_data.available and cap_data.stress_score > 0
            and cap_data.stress_score < 0.5
        )

        if on_request_path:
            severity = SEVERITY_HIGH
            priority = PRIORITY_HIGH
        else:
            severity = SEVERITY_MEDIUM
            priority = PRIORITY_MEDIUM

        self._add_risk(
            risk_type=RES_RISK_CPU_BOUND,
            severity=severity,
            title="CPU-intensive operations detected",
            description=(
                f"The technology stack includes CPU-intensive "
                f"technologies ({', '.join(cpu_techs)}. "
                + (
                    "These appear to be on the request path "
                    "(low stress score), which will degrade "
                    "response time."
                    if on_request_path
                    else "These may consume significant CPU "
                    "resources."
                )
            ),
            cause=(
                "CPU-intensive technologies (machine learning, "
                "image/video processing, heavy computation) were "
                "selected."
            ),
            impact=(
                "CPU-bound operations can saturate the CPU, "
                "degrading response time and throughput. Under "
                "load, the system may become unresponsive."
            ),
            suggested_fix=(
                "Move CPU-intensive operations to background "
                "workers or separate services. Use async "
                "processing with a task queue (Celery, "
                "RQ). Offload to GPU or specialized hardware "
                "if needed."
            ),
            fix_priority=priority,
            affected_components=cpu_techs,
            reasoning=(
                f"cpu_techs={cpu_techs}, "
                f"on_request_path={on_request_path}."
            ),
        )

    # ----------------------------------------------------------------- #
    # Memory-bound
    # ----------------------------------------------------------------- #

    def _detect_memory_bound(
        self, cap_data: ProjectCapabilityData
    ) -> None:
        """Detect high memory consumption."""
        if not cap_data.available:
            return

        mem = cap_data.estimated_memory_mb

        if mem > MEMORY_CRITICAL_MB:
            severity = SEVERITY_CRITICAL
            priority = PRIORITY_IMMEDIATE
        elif mem > MEMORY_HIGH_MB:
            severity = SEVERITY_HIGH
            priority = PRIORITY_HIGH
        elif mem > MEMORY_MEDIUM_MB:
            severity = SEVERITY_MEDIUM
            priority = PRIORITY_MEDIUM
        else:
            return

        self._add_risk(
            risk_type=RES_RISK_MEMORY_BOUND,
            severity=severity,
            title=f"High memory consumption ({mem} MB)",
            description=(
                f"The estimated memory consumption is {mem} MB, "
                f"which is "
                f"{'critically ' if mem > MEMORY_CRITICAL_MB else ''}"
                f"above the recommended threshold. High memory "
                f"usage can lead to OOM errors and limits the "
                f"number of concurrent instances."
            ),
            cause=(
                "The architecture or technology stack requires "
                "a large memory footprint, possibly due to "
                "in-memory data processing, large caches, or "
                "heavyweight frameworks."
            ),
            impact=(
                "High memory consumption limits the number of "
                "concurrent instances per machine, increases "
                "infrastructure cost, and risks out-of-memory "
                "errors under load."
            ),
            suggested_fix=(
                "Reduce in-memory data structures. Use streaming "
                "and pagination for large datasets. Profile "
                "memory usage and optimize hot paths. Consider "
                "memory-efficient alternatives for data-heavy "
                "processing."
            ),
            fix_priority=priority,
            affected_components=["memory", "runtime"],
            reasoning=f"estimated_memory_mb={mem}.",
        )

    # ----------------------------------------------------------------- #
    # Disk-bound
    # ----------------------------------------------------------------- #

    def _detect_disk_bound(
        self,
        tech_data: TechnologySelectionData,
        cap_data: ProjectCapabilityData,
    ) -> None:
        """Detect disk I/O bottlenecks."""
        if not tech_data.available:
            return

        disk_techs = [
            t for t in tech_data.selected_technologies
            if any(
                kw in t.lower() for kw in _DISK_INTENSIVE_KEYWORDS
            )
        ]

        file_count = cap_data.file_count if cap_data.available else 0

        if disk_techs and file_count > FILE_COUNT_HIGH:
            severity = (
                SEVERITY_HIGH
                if file_count > FILE_COUNT_CRITICAL
                else SEVERITY_MEDIUM
            )
            priority = (
                PRIORITY_HIGH
                if severity == SEVERITY_HIGH
                else PRIORITY_MEDIUM
            )

            self._add_risk(
                risk_type=RES_RISK_DISK_BOUND,
                severity=severity,
                title="Disk I/O bottleneck risk",
                description=(
                    f"The technology stack includes disk I/O "
                    f"intensive technologies "
                    f"({', '.join(disk_techs)}) and the "
                    f"estimated file count is {file_count}. "
                    f"Heavy disk I/O can become a bottleneck "
                    f"under load."
                ),
                cause=(
                    "Disk I/O intensive technologies were "
                    "selected alongside a high file count, "
                    "creating disk-bound workloads."
                ),
                impact=(
                    "Disk I/O bottlenecks slow down read/write "
                    "operations, increasing latency and "
                    "reducing throughput. Disk contention can "
                    "degrade the entire system."
                ),
                suggested_fix=(
                    "Use SSDs for disk-intensive workloads. "
                    "Implement caching to reduce disk reads. "
                    "Batch writes to reduce I/O operations. "
                    "Consider memory-mapped files or database "
                    "indices to reduce disk scans."
                ),
                fix_priority=priority,
                affected_components=disk_techs,
                reasoning=(
                    f"disk_techs={disk_techs}, "
                    f"file_count={file_count}."
                ),
            )

    # ----------------------------------------------------------------- #
    # Network-bound
    # ----------------------------------------------------------------- #

    def _detect_network_bound(
        self,
        arch_data: ArchitectureDecisionData,
        tech_data: TechnologySelectionData,
    ) -> None:
        """Detect excessive network round-trips."""
        if not arch_data.available or not tech_data.available:
            return

        # Count network-intensive technologies.
        net_techs = [
            t for t in tech_data.selected_technologies
            if any(
                kw in t.lower() for kw in _NETWORK_INTENSIVE_KEYWORDS
            )
        ]

        # If there are many services using network communication,
        # and no async/batching tech, it's a risk.
        has_async = any(
            kw in t.lower()
            for t in tech_data.selected_technologies
            for kw in ("async", "celery", "rabbitmq", "kafka", "queue")
        )

        if (
            arch_data.service_count > 2
            and len(net_techs) > arch_data.service_count
            and not has_async
        ):
            self._add_risk(
                risk_type=RES_RISK_NETWORK_BOUND,
                severity=SEVERITY_MEDIUM,
                title="Excessive network round-trips",
                description=(
                    f"The architecture has "
                    f"{arch_data.service_count} services with "
                    f"{len(net_techs)} network-oriented "
                    f"technologies but no async/batching "
                    f"technology. Synchronous network calls "
                    f"between services add latency."
                ),
                cause=(
                    "Multiple services communicate synchronously "
                    "over the network without batching or "
                    "async processing."
                ),
                impact=(
                    "Synchronous inter-service calls add "
                    "cumulative latency. Under load, network "
                    "round-trips become a bottleneck, "
                    "increasing response time and the risk of "
                    "cascading timeouts."
                ),
                suggested_fix=(
                    "Batch network calls where possible. Use "
                    "async communication (message queues) for "
                    "non-critical paths. Implement circuit "
                    "breakers and retries with backoff. "
                    "Cache responses to reduce round-trips."
                ),
                fix_priority=PRIORITY_MEDIUM,
                affected_components=["services", "network"],
                reasoning=(
                    f"service_count={arch_data.service_count}, "
                    f"net_techs={len(net_techs)}, "
                    f"has_async={has_async}."
                ),
            )

    # ----------------------------------------------------------------- #
    # Cost overrun
    # ----------------------------------------------------------------- #

    def _detect_cost_overrun(
        self,
        tech_data: TechnologySelectionData,
        arch_data: ArchitectureDecisionData,
    ) -> None:
        """Detect potential cost overrun risks."""
        if not tech_data.available:
            return

        cost_techs = [
            t for t in tech_data.selected_technologies
            if any(
                kw in t.lower() for kw in _COST_INTENSIVE_KEYWORDS
            )
        ]

        if not cost_techs:
            return

        # If more than 5 cost-intensive technologies, it's high risk.
        if len(cost_techs) >= 5:
            severity = SEVERITY_MEDIUM
            priority = PRIORITY_MEDIUM
        else:
            return

        self._add_risk(
            risk_type=RES_RISK_COST_OVERRUN,
            severity=severity,
            title="Potential infrastructure cost overrun",
            description=(
                f"The technology stack includes "
                f"{len(cost_techs)} cost-intensive technologies "
                f"({', '.join(cost_techs)}). Cloud-managed "
                f"services and enterprise-tier tools can lead "
                f"to unexpected infrastructure costs as the "
                f"project scales."
            ),
            cause=(
                "Many cloud-managed or enterprise-tier "
                "technologies were selected, which carry "
                "per-request, per-hour, or per-GB pricing that "
                "scales with usage."
            ),
            impact=(
                "Cloud-managed services can lead to unexpected "
                "costs as traffic and data volume grow. Without "
                "cost monitoring, the project may exceed its "
                "infrastructure budget."
            ),
            suggested_fix=(
                "Set up cost monitoring and billing alerts. "
                "Evaluate open-source alternatives for "
                "non-critical components. Use auto-scaling to "
                "reduce idle costs. Regularly review the cloud "
                "bill and optimize resource allocation."
            ),
            fix_priority=priority,
            affected_components=cost_techs,
            reasoning=f"cost_techs={cost_techs}.",
        )

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
        risk_id = f"res_{risk_type}_{len(self.risks) + 1}"
        self.risks.append(RiskItem(
            risk_id=risk_id,
            dimension=DIMENSION_RESOURCE,
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
            affected="resource",
            resolution_hint=suggested_fix,
            category="resource",
        ))

    @staticmethod
    def _calculate_score(risks: List[RiskItem]) -> float:
        """Calculate the resource risk score (0.0-1.0)."""
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


__all__ = ["ResourceRiskAnalyzer"]
