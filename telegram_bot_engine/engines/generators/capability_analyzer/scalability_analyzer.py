"""
ScalabilityAnalyzer — Specification 017

Checks whether the chosen architecture can support four scalability
tiers:
    1. Thousands of users         (1,000 – 9,999)
    2. Tens of thousands          (10,000 – 99,999)
    3. Hundreds of thousands      (100,000 – 999,999)
    4. Millions of users         (1,000,000+)

For each tier the analyzer evaluates the architecture pattern, the
communication style, the technology stack, and the database
choice, then produces a :class:`ScalabilityTier` verdict and an
overall :class:`ScalabilityAnalysis`.

The scalability analyzer does not write code, create files, or make
build decisions.  It only assesses scalability capability.
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
    ScalabilityTier,
    ScalabilityAnalysis,
    CapabilityFinding,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    DIMENSION_SCALABILITY,
    SCALE_THOUSANDS,
    SCALE_TENS_OF_THOUSANDS,
    SCALE_HUNDREDS_OF_THOUSANDS,
    SCALE_MILLIONS,
    SCALE_THRESHOLD_THOUSANDS,
    SCALE_THRESHOLD_TENS_OF_THOUSANDS,
    SCALE_THRESHOLD_HUNDREDS_OF_THOUSANDS,
    SCALE_THRESHOLD_MILLIONS,
    ALL_SCALE_TIERS,
)

_log = logging.getLogger("engine.capability_analyzer.scalability")


# ---------------------------------------------------------------------------#
# Architecture pattern scalability multipliers
# ---------------------------------------------------------------------------#
#
# Each architecture pattern has a base scalability factor that
# determines how well it scales.  Higher = better scaling.

_PATTERN_SCALE_FACTORS = {
    "monolith": 0.3,
    "layered": 0.5,
    "modular_monolith": 0.6,
    "microservices": 0.95,
    "event_driven": 0.9,
    "hexagonal": 0.7,
    "clean": 0.65,
    "default": 0.5,
}

# Communication pattern scalability factors.
_COMM_SCALE_FACTORS = {
    "sync": 0.3,
    "asynchronous": 0.8,
    "async": 0.8,
    "event": 0.9,
    "event_driven": 0.9,
    "hybrid": 0.75,
    "default": 0.5,
}

# Technology scalability factors — technologies that help or hurt
# scaling at different tiers.
_SCALING_TECH_BONUS = {
    # Caches
    "redis": 0.15,
    "memcached": 0.12,
    # Message queues
    "kafka": 0.2,
    "rabbitmq": 0.1,
    "celery": 0.08,
    # Databases (scalable)
    "postgresql": 0.1,
    "mongodb": 0.12,
    "elasticsearch": 0.1,
    # Non-scalable database
    "sqlite": -0.3,
}


class ScalabilityAnalyzer:
    """Checks whether the architecture can support each scalability
    tier.

    Evaluates the architecture pattern, communication style,
    technology stack, and database choice for each of the four
    tiers and produces a :class:`ScalabilityAnalysis`.
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
    ) -> ScalabilityAnalysis:
        """Perform the scalability analysis.

        Args:
            arch_data: Architecture decision data.
            tech_data: Technology selection data.
            req_data: Requirement normalization data.
            graph_data: Intelligence graph data.
            kb_data: Knowledge base data.

        Returns:
            A :class:`ScalabilityAnalysis` instance.
        """
        self.findings = []

        # ---- Compute base scalability factor ----
        base_factor = self._compute_base_factor(arch_data)

        # ---- Compute technology bonus ----
        tech_bonus = self._compute_tech_bonus(tech_data)

        # ---- Compute architecture robustness ----
        arch_robustness = self._compute_arch_robustness(
            arch_data, graph_data
        )

        # ---- Check each tier ----
        tiers: List[ScalabilityTier] = []
        tier_configs = [
            (SCALE_THOUSANDS, SCALE_THRESHOLD_THOUSANDS, 0.3),
            (SCALE_TENS_OF_THOUSANDS, SCALE_THRESHOLD_TENS_OF_THOUSANDS, 0.5),
            (SCALE_HUNDREDS_OF_THOUSANDS, SCALE_THRESHOLD_HUNDREDS_OF_THOUSANDS, 0.7),
            (SCALE_MILLIONS, SCALE_THRESHOLD_MILLIONS, 0.85),
        ]

        for tier_name, user_threshold, required_factor in tier_configs:
            tier = self._evaluate_tier(
                tier_name=tier_name,
                user_threshold=user_threshold,
                required_factor=required_factor,
                base_factor=base_factor,
                tech_bonus=tech_bonus,
                arch_robustness=arch_robustness,
                arch_data=arch_data,
                tech_data=tech_data,
            )
            tiers.append(tier)

        # ---- Max supported tier ----
        max_supported = ""
        for tier in tiers:
            if tier.supported:
                max_supported = tier.tier

        # ---- Overall score ----
        # The score reflects how far up the tier ladder the
        # architecture can go.
        supported_count = sum(1 for t in tiers if t.supported)
        score = supported_count / len(tiers) if tiers else 0.0

        # Also factor in the average confidence of supported tiers.
        if supported_count > 0:
            avg_confidence = (
                sum(t.confidence for t in tiers if t.supported)
                / supported_count
            )
            score = (score * 0.6) + (avg_confidence * 0.4)
        score = max(0.0, min(1.0, score))

        # ---- Summary and details ----
        details = []
        for tier in tiers:
            status = "supported" if tier.supported else "not supported"
            details.append(
                f"{tier.tier}: {status} "
                f"(confidence: {tier.confidence:.2f})"
            )

        if max_supported:
            summary = (
                f"Architecture can scale to {max_supported} "
                f"of users (score: {score:.2f})."
            )
        else:
            summary = (
                "Architecture does not meet minimum scalability "
                "requirements for any tier."
            )

        # ---- Findings ----
        if not max_supported:
            self.findings.append(CapabilityFinding(
                severity=SEVERITY_WARNING,
                code="no_scalability",
                message=(
                    "The architecture does not support any "
                    "scalability tier. This may indicate a "
                    "fundamental scalability limitation."
                ),
                affected="scalability",
                resolution_hint=(
                    "Consider a more scalable architecture "
                    "pattern (e.g., microservices, event-driven) "
                    "or add caching and message queue technologies."
                ),
                category="scalability",
            ))
        elif max_supported == SCALE_MILLIONS:
            self.findings.append(CapabilityFinding(
                severity=SEVERITY_INFO,
                code="high_scalability",
                message=(
                    "Architecture supports up to millions of "
                    "users. Excellent scalability."
                ),
                affected="scalability",
                category="scalability",
            ))

        # Check for non-scalable technology combinations.
        has_sqlite = any(
            t.lower() == "sqlite"
            for t in tech_data.selected_technologies
        )
        if has_sqlite and supported_count > 1:
            self.findings.append(CapabilityFinding(
                severity=SEVERITY_WARNING,
                code="sqlite_at_scale",
                message=(
                    "SQLite is selected but the architecture "
                    "claims to support higher tiers. SQLite is "
                    "not suitable for production at scale."
                ),
                affected="scalability",
                resolution_hint=(
                    "Replace SQLite with PostgreSQL or another "
                    "production-grade database."
                ),
                category="scalability",
            ))

        return ScalabilityAnalysis(
            tiers=tiers,
            max_supported_tier=max_supported,
            score=score,
            summary=summary,
            details=details,
        )

    # ----------------------------------------------------------------- #
    # Private helpers
    # ----------------------------------------------------------------- #

    def _compute_base_factor(
        self, arch_data: ArchitectureDecisionData
    ) -> float:
        """Compute the base scalability factor from the architecture
        pattern and communication style.

        Args:
            arch_data: Architecture decision data.

        Returns:
            A base scalability factor (0.0-1.0).
        """
        pattern = arch_data.pattern.lower() if arch_data.pattern else ""
        comm = arch_data.communication.lower() if arch_data.communication else ""

        pattern_factor = _PATTERN_SCALE_FACTORS.get(
            pattern, _PATTERN_SCALE_FACTORS["default"]
        )
        comm_factor = _COMM_SCALE_FACTORS.get(
            comm, _COMM_SCALE_FACTORS["default"]
        )

        # Combined factor: 60% pattern, 40% communication.
        base = (pattern_factor * 0.6) + (comm_factor * 0.4)
        return max(0.0, min(1.0, base))

    def _compute_tech_bonus(
        self, tech_data: TechnologySelectionData
    ) -> float:
        """Compute the technology bonus for scalability.

        Args:
            tech_data: Technology selection data.

        Returns:
            A bonus factor (can be negative for non-scalable tech).
        """
        bonus = 0.0
        for tech in tech_data.selected_technologies:
            tech_lower = tech.lower()
            for key, value in _SCALING_TECH_BONUS.items():
                if key in tech_lower:
                    bonus += value
                    break  # Only count each tech once

        # Cap the bonus.
        return max(-0.3, min(0.5, bonus))

    def _compute_arch_robustness(
        self,
        arch_data: ArchitectureDecisionData,
        graph_data: IntelligenceGraphData,
    ) -> float:
        """Compute the architecture robustness factor.

        More modules and services generally mean better
        separation of concerns, which aids scaling.  But too many
        can add overhead.

        Args:
            arch_data: Architecture decision data.
            graph_data: Intelligence graph data.

        Returns:
            A robustness factor (0.0-1.0).
        """
        module_count = arch_data.module_count
        service_count = arch_data.service_count
        if service_count == 0:
            service_count = graph_data.service_count

        # Microservice architectures with many services scale well.
        if service_count >= 5:
            return 0.9
        elif service_count >= 3:
            return 0.75
        elif service_count >= 1:
            return 0.6
        elif module_count >= 5:
            return 0.65
        elif module_count >= 2:
            return 0.5
        else:
            return 0.35

    def _evaluate_tier(
        self,
        tier_name: str,
        user_threshold: int,
        required_factor: float,
        base_factor: float,
        tech_bonus: float,
        arch_robustness: float,
        arch_data: ArchitectureDecisionData,
        tech_data: TechnologySelectionData,
    ) -> ScalabilityTier:
        """Evaluate whether the architecture supports a given tier.

        Args:
            tier_name: The tier name.
            user_threshold: The user count threshold for this tier.
            required_factor: The minimum combined factor needed.
            base_factor: The base scalability factor.
            tech_bonus: The technology bonus.
            arch_robustness: The architecture robustness factor.
            arch_data: Architecture decision data.
            tech_data: Technology selection data.

        Returns:
            A :class:`ScalabilityTier` instance.
        """
        # Combined scalability factor.
        combined = (
            (base_factor * 0.4)
            + (arch_robustness * 0.3)
            + (0.3 + tech_bonus)
        )
        combined = max(0.0, min(1.0, combined))

        # Confidence is the combined factor clamped.
        confidence = combined

        # Determine if this tier is supported.
        supported = combined >= required_factor

        # Build the user range string.
        if tier_name == SCALE_MILLIONS:
            user_range = "1,000,000+"
        elif tier_name == SCALE_HUNDREDS_OF_THOUSANDS:
            user_range = "100,000 - 999,999"
        elif tier_name == SCALE_TENS_OF_THOUSANDS:
            user_range = "10,000 - 99,999"
        else:
            user_range = "1,000 - 9,999"

        # Build reason and limitations.
        if supported:
            reason = (
                f"Architecture pattern '{arch_data.pattern or 'default'}' "
                f"with combined scalability factor {combined:.2f} "
                f"(required: {required_factor:.2f}) supports "
                f"this tier."
            )
            limitations = []
        else:
            reason = (
                f"Architecture pattern '{arch_data.pattern or 'default'}' "
                f"with combined scalability factor {combined:.2f} "
                f"does not meet the required factor "
                f"{required_factor:.2f} for this tier."
            )
            limitations = self._identify_limitations(
                tier_name, arch_data, tech_data
            )

        return ScalabilityTier(
            tier=tier_name,
            user_range=user_range,
            supported=supported,
            confidence=confidence,
            reason=reason,
            limitations=limitations,
        )

    def _identify_limitations(
        self,
        tier_name: str,
        arch_data: ArchitectureDecisionData,
        tech_data: TechnologySelectionData,
    ) -> List[str]:
        """Identify limitations preventing a tier from being supported.

        Args:
            tier_name: The tier name.
            arch_data: Architecture decision data.
            tech_data: Technology selection data.

        Returns:
            A list of limitation strings.
        """
        limitations = []
        pattern = arch_data.pattern.lower() if arch_data.pattern else ""

        # Pattern-based limitations.
        if tier_name in (SCALE_HUNDREDS_OF_THOUSANDS, SCALE_MILLIONS):
            if pattern in ("monolith", "layered"):
                limitations.append(
                    f"{arch_data.pattern} pattern does not "
                    f"scale well to {tier_name}."
                )
            if arch_data.service_count <= 1:
                limitations.append(
                    "Single-service architecture limits "
                    "horizontal scaling."
                )

        # Technology-based limitations.
        tech_list = [
            t.lower() for t in tech_data.selected_technologies
        ]
        if "sqlite" in tech_list:
            limitations.append(
                "SQLite is not suitable for high-concurrency "
                "workloads at this scale."
            )
        if tier_name == SCALE_MILLIONS:
            has_cache = any(
                t in tech_list for t in ("redis", "memcached")
            )
            if not has_cache:
                limitations.append(
                    "No caching layer detected. A cache is "
                    "essential at this scale."
                )
            has_queue = any(
                t in tech_list
                for t in ("kafka", "rabbitmq", "celery")
            )
            if not has_queue:
                limitations.append(
                    "No message queue detected. Asynchronous "
                    "processing is needed at this scale."
                )

        if not limitations:
            limitations.append(
                "Combined scalability factors are below the "
                "threshold for this tier."
            )

        return limitations


__all__ = ["ScalabilityAnalyzer"]
