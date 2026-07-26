"""
ScalabilityRiskAnalyzer — Specification 018

Measures the design's ability to grow and identifies weak points
before project generation begins.

The analyzer detects:
* **Insufficient scalability** — the architecture cannot handle
  the expected user count or data volume.
* **No horizontal scaling** — the design is monolithic with no
  scaling strategy.
* **Stateful components** — stateful services block horizontal
  scaling.
* **No load balancing** — traffic is not distributed.
* **Database bottlenecks** — a single database is the scaling
  ceiling.

The analyzer does not write code, create files, or start the build.
It only measures and classifies scalability risks.
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
    DIMENSION_SCALABILITY,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    SEVERITY_LOW,
    PRIORITY_IMMEDIATE,
    PRIORITY_HIGH,
    PRIORITY_MEDIUM,
    PRIORITY_LOW,
)

_log = logging.getLogger("engine.risk_detection.scalability")


# ---------------------------------------------------------------------------#
# Thresholds
# ---------------------------------------------------------------------------#

SCALABILITY_SCORE_LOW = 0.4    # Below this, scalability is at risk.
SCALABILITY_SCORE_CRITICAL = 0.2  # Below this, it's critical.
MIN_SCALABILITY_TIER = "thousands"  # Must support at least thousands.

_TIER_RANK = {
    "thousands": 1,
    "tens_of_thousands": 2,
    "hundreds_of_thousands": 3,
    "millions": 4,
}


class ScalabilityRiskAnalyzer:
    """Detects scalability-level risks.

    The analyzer examines the project capability report
    (scalability score, max tier), architecture decisions,
    and technology selections to detect:
    * Insufficient scalability score.
    * No horizontal scaling strategy.
    * Stateful components blocking scaling.
    * No load balancing.
    * Database scalability bottlenecks.
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
        """Perform the scalability risk analysis.

        Args:
            cap_data: Project capability data.
            arch_data: Architecture decision data.
            tech_data: Technology selection data.
            req_data: Requirement normalization data.
            kb_data: Knowledge base data.

        Returns:
            A :class:`RiskDimensionResult` for the scalability
            dimension.
        """
        self.findings = []
        self.risks = []

        # ---- Insufficient scalability score ----
        self._detect_insufficient_scalability(cap_data)

        # ---- No horizontal scaling ----
        self._detect_no_horizontal_scaling(arch_data, tech_data)

        # ---- Stateful components ----
        self._detect_stateful_components(arch_data, tech_data)

        # ---- No load balancing ----
        self._detect_no_load_balancing(tech_data, arch_data)

        # ---- Database bottleneck ----
        self._detect_database_bottleneck(tech_data, arch_data)

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
        if cap_data.scalability_score > 0:
            details.append(
                f"Capability scalability score: "
                f"{cap_data.scalability_score:.2f}."
            )
        if cap_data.max_scalability_tier:
            details.append(
                f"Max scalability tier: "
                f"{cap_data.max_scalability_tier}."
            )
        details.append(
            f"Scalability risks detected: "
            f"{len(self.risks)} "
            f"(critical={critical}, high={high}, "
            f"medium={medium}, low={low})."
        )

        summary = (
            f"Scalability risk analysis: {len(self.risks)} "
            f"risk(s) detected."
        )

        return RiskDimensionResult(
            dimension=DIMENSION_SCALABILITY,
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
    # Insufficient scalability
    # ----------------------------------------------------------------- #

    def _detect_insufficient_scalability(
        self, cap_data: ProjectCapabilityData
    ) -> None:
        """Detect insufficient scalability score."""
        score = cap_data.scalability_score

        if score > 0 and score < SCALABILITY_SCORE_CRITICAL:
            severity = SEVERITY_CRITICAL
            priority = PRIORITY_IMMEDIATE
        elif score > 0 and score < SCALABILITY_SCORE_LOW:
            severity = SEVERITY_HIGH
            priority = PRIORITY_HIGH
        else:
            # Check the max tier.
            tier = cap_data.max_scalability_tier.lower()
            if tier and _TIER_RANK.get(tier, 0) < _TIER_RANK.get(
                MIN_SCALABILITY_TIER, 1
            ):
                severity = SEVERITY_HIGH
                priority = PRIORITY_HIGH
            else:
                return

        self._add_risk(
            risk_type="insufficient_scalability",
            severity=severity,
            title="Insufficient scalability score",
            description=(
                f"The capability analysis scalability score "
                f"({score:.2f}) is below the minimum "
                f"({SCALABILITY_SCORE_LOW}). The architecture "
                f"may not handle the expected user count or "
                f"data volume."
            ),
            cause=(
                "The architecture lacks scaling mechanisms "
                "(caching, queuing, horizontal scaling) or "
                "the scalability tier is too low."
            ),
            impact=(
                "Under growth, the system will degrade in "
                "performance, response time, and availability. "
                "Scaling vertically is expensive and has "
                "limits."
            ),
            suggested_fix=(
                "Add horizontal scaling, caching, and "
                "asynchronous processing. Select technologies "
                "that support higher scalability tiers."
            ),
            fix_priority=priority,
            affected_components=["architecture", "scalability"],
            reasoning=(
                f"scalability_score={score:.2f}, "
                f"max_tier={cap_data.max_scalability_tier}."
            ),
        )

    # ----------------------------------------------------------------- #
    # No horizontal scaling
    # ----------------------------------------------------------------- #

    def _detect_no_horizontal_scaling(
        self,
        arch_data: ArchitectureDecisionData,
        tech_data: TechnologySelectionData,
    ) -> None:
        """Detect lack of horizontal scaling strategy."""
        # Check for horizontal-scaling technologies.
        h_scale_tech = [
            t for t in tech_data.selected_technologies
            if any(
                kw in t.lower()
                for kw in (
                    "docker", "kubernetes", "k8s", "load",
                    "balancer", "celery", "rabbitmq", "kafka",
                )
            )
        ]

        if not h_scale_tech and arch_data.service_count <= 1:
            # Monolithic architecture with no scaling tech.
            self._add_risk(
                risk_type="no_horizontal_scaling",
                severity=SEVERITY_HIGH,
                title="No horizontal scaling strategy",
                description=(
                    "The architecture is monolithic "
                    f"({arch_data.service_count} service) "
                    "with no horizontal-scaling technologies "
                    "selected. The system cannot scale out."
                ),
                cause=(
                    "No containerisation, orchestration, or "
                    "message-queue technologies were selected "
                    "to enable horizontal scaling."
                ),
                impact=(
                    "The system scales only vertically "
                    "(bigger machine), which is expensive "
                    "and has hard limits."
                ),
                suggested_fix=(
                    "Adopt containerisation (Docker) and "
                    "orchestration (Kubernetes), and use "
                    "message queues for async work distribution."
                ),
                fix_priority=PRIORITY_HIGH,
                affected_components=["architecture", "services"],
                reasoning=(
                    f"no horizontal-scaling tech, "
                    f"{arch_data.service_count} service(s)."
                ),
            )

    # ----------------------------------------------------------------- #
    # Stateful components
    # ----------------------------------------------------------------- #

    def _detect_stateful_components(
        self,
        arch_data: ArchitectureDecisionData,
        tech_data: TechnologySelectionData,
    ) -> None:
        """Detect stateful components that block scaling."""
        stateful_tech = [
            t for t in tech_data.selected_technologies
            if any(
                kw in t.lower()
                for kw in ("session", "sqlite", "file storage")
            )
        ]

        # Check architecture for session-based communication.
        comm = arch_data.communication.lower()
        if "session" in comm:
            stateful_tech.append("session-based communication")

        if stateful_tech:
            self._add_risk(
                risk_type="stateful_components",
                severity=SEVERITY_MEDIUM,
                title="Stateful components block horizontal scaling",
                description=(
                    f"The architecture includes stateful "
                    f"components ({', '.join(stateful_tech)}). "
                    f"Stateful components cannot be "
                    f"horizontally scaled without session "
                    f"sharing."
                ),
                cause=(
                    "Stateful technologies or session-based "
                    "communication keep state on a single "
                    "instance."
                ),
                impact=(
                    "Stateful components prevent horizontal "
                    "scaling. A single instance becomes a "
                    "bottleneck under load."
                ),
                suggested_fix=(
                    "Move state to a shared store (Redis, "
                    "database) and adopt stateless service "
                    "design."
                ),
                fix_priority=PRIORITY_MEDIUM,
                affected_components=stateful_tech,
                reasoning=(
                    f"stateful: {', '.join(stateful_tech)}."
                ),
            )

    # ----------------------------------------------------------------- #
    # No load balancing
    # ----------------------------------------------------------------- #

    def _detect_no_load_balancing(
        self,
        tech_data: TechnologySelectionData,
        arch_data: ArchitectureDecisionData,
    ) -> None:
        """Detect lack of load balancing."""
        has_lb = any(
            kw in t.lower()
            for t in tech_data.selected_technologies
            for kw in ("load", "balancer", "nginx", "traefik", "haproxy")
        )

        if not has_lb and arch_data.service_count > 1:
            self._add_risk(
                risk_type="no_load_balancing",
                severity=SEVERITY_MEDIUM,
                title="No load balancing for multiple services",
                description=(
                    f"The architecture has "
                    f"{arch_data.service_count} services but "
                    f"no load-balancing technology. Traffic "
                    f"is not distributed across instances."
                ),
                cause=(
                    "No load balancer was selected to "
                    "distribute traffic across service "
                    "instances."
                ),
                impact=(
                    "Without load balancing, a single "
                    "instance handles all traffic, becoming "
                    "a bottleneck and single point of failure."
                ),
                suggested_fix=(
                    "Add a load balancer (Nginx, Traefik, "
                    "HAProxy) in front of the services."
                ),
                fix_priority=PRIORITY_MEDIUM,
                affected_components=["services", "network"],
                reasoning=(
                    f"no load balancer with "
                    f"{arch_data.service_count} services."
                ),
            )

    # ----------------------------------------------------------------- #
    # Database bottleneck
    # ----------------------------------------------------------------- #

    def _detect_database_bottleneck(
        self,
        tech_data: TechnologySelectionData,
        arch_data: ArchitectureDecisionData,
    ) -> None:
        """Detect database scalability bottlenecks."""
        db_techs = [
            t for t in tech_data.selected_technologies
            if any(
                kw in t.lower()
                for kw in ("sqlite", "mysql", "postgres", "postgresql", "mongodb")
            )
        ]

        # SQLite is a scaling bottleneck.
        has_sqlite = any(
            "sqlite" in t.lower() for t in db_techs
        )

        # No read replica / sharding tech.
        has_replica = any(
            kw in t.lower()
            for t in tech_data.selected_technologies
            for kw in ("replica", "shard", "cluster")
        )

        if has_sqlite:
            self._add_risk(
                risk_type="database_bottleneck",
                severity=SEVERITY_HIGH,
                title="SQLite database limits scalability",
                description=(
                    "SQLite is selected as the database. "
                    "SQLite is a file-based database that "
                    "does not support concurrent writes or "
                    "horizontal scaling."
                ),
                cause=(
                    "SQLite was selected instead of a "
                    "server-based database (PostgreSQL, MySQL)."
                ),
                impact=(
                    "SQLite limits concurrency and cannot "
                    "scale beyond a single machine. It is "
                    "the scaling ceiling."
                ),
                suggested_fix=(
                    "Replace SQLite with a server-based "
                    "database (PostgreSQL or MySQL) for "
                    "production workloads."
                ),
                fix_priority=PRIORITY_HIGH,
                affected_components=["database"],
                reasoning="SQLite selected — no horizontal scaling.",
            )
        elif db_techs and not has_replica and arch_data.service_count > 2:
            self._add_risk(
                risk_type="database_bottleneck",
                severity=SEVERITY_MEDIUM,
                title="Single database with no replication",
                description=(
                    f"A single database ({', '.join(db_techs)}) "
                    f"is selected with no replication or "
                    f"sharding. The database is the scaling "
                    f"ceiling."
                ),
                cause=(
                    "No read replicas or sharding "
                    "technologies were selected alongside "
                    "the primary database."
                ),
                impact=(
                    "A single database instance handles all "
                    "reads and writes, becoming a bottleneck "
                    "under growth."
                ),
                suggested_fix=(
                    "Add read replicas for read-heavy "
                    "workloads, and consider sharding for "
                    "very large datasets."
                ),
                fix_priority=PRIORITY_MEDIUM,
                affected_components=["database"],
                reasoning=(
                    f"single database ({', '.join(db_techs)}) "
                    f"with no replication."
                ),
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
        risk_id = f"scal_{risk_type}_{len(self.risks) + 1}"
        self.risks.append(RiskItem(
            risk_id=risk_id,
            dimension=DIMENSION_SCALABILITY,
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
            affected="scalability",
            resolution_hint=suggested_fix,
            category="scalability",
        ))

    @staticmethod
    def _calculate_score(risks: List[RiskItem]) -> float:
        """Calculate the scalability risk score (0.0-1.0)."""
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


__all__ = ["ScalabilityRiskAnalyzer"]
