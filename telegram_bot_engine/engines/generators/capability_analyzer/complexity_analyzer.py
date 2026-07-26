"""
ComplexityAnalyzer — Specification 017

Measures the project's structural complexity by counting the
architectural elements: modules, services, components, classes,
functions, interfaces, background tasks, and external integrations.

The complexity analyzer does not write code, create files, or make
build decisions.  It only measures and classifies the complexity.
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
    ComplexityAnalysis,
    AnalysisResult,
    CapabilityFinding,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    DIMENSION_COMPLEXITY,
    COMPLEXITY_TRIVIAL,
    COMPLEXITY_LOW,
    COMPLEXITY_MODERATE,
    COMPLEXITY_HIGH,
    COMPLEXITY_VERY_HIGH,
    COMPLEXITY_THRESHOLD_TRIVIAL,
    COMPLEXITY_THRESHOLD_LOW,
    COMPLEXITY_THRESHOLD_MODERATE,
    COMPLEXITY_THRESHOLD_HIGH,
    SOURCE_ARCHITECTURE_DECISION,
)

_log = logging.getLogger("engine.capability_analyzer.complexity")


class ComplexityAnalyzer:
    """Measures the structural complexity of the project.

    Counts the architectural elements (modules, services, components,
    classes, functions, interfaces, background tasks, external
    integrations) and classifies the overall complexity level.
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
    ) -> ComplexityAnalysis:
        """Perform the complexity analysis.

        Args:
            arch_data: Architecture decision data.
            tech_data: Technology selection data.
            req_data: Requirement normalization data.
            graph_data: Intelligence graph data.
            kb_data: Knowledge base data.

        Returns:
            A :class:`ComplexityAnalysis` instance.
        """
        self.findings = []

        # ---- Count modules ----
        module_count = arch_data.module_count

        # ---- Count services ----
        service_count = arch_data.service_count
        if service_count == 0:
            service_count = graph_data.service_count

        # ---- Count components ----
        component_count = graph_data.component_count

        # ---- Count classes ----
        # Estimate classes from modules and components.
        # Each module typically contains 2-5 classes; each component
        # is roughly 1-3 classes.
        class_count = module_count * 3 + component_count * 2

        # ---- Count functions ----
        # Estimate functions from classes and requirements.
        # Each class has ~3-8 functions; each requirement adds ~1-2.
        class_count_safe = max(class_count, 1)
        function_count = (
            class_count_safe * 5 + req_data.requirement_count * 2
        )

        # ---- Count interfaces ----
        # Interfaces come from API endpoints and message contracts.
        # Estimate from services and requirements.
        interface_count = service_count * 4 + req_data.requirement_count

        # ---- Count background tasks ----
        # Estimate from the architecture pattern and requirements.
        # Async/event-driven patterns tend to have more background tasks.
        background_task_count = self._estimate_background_tasks(
            arch_data, req_data
        )

        # ---- Count external integrations ----
        # Estimate from requirements and technologies.
        external_integration_count = self._estimate_external_integrations(
            req_data, tech_data
        )

        # ---- Total elements ----
        total_elements = (
            module_count
            + service_count
            + component_count
            + class_count
            + function_count
            + interface_count
            + background_task_count
            + external_integration_count
        )

        # ---- Complexity level ----
        complexity_level = self._classify_complexity(total_elements)

        # ---- Score (0.0-1.0, higher = more complex) ----
        score = self._calculate_score(total_elements)

        # ---- Summary and details ----
        details = []
        if module_count:
            details.append(f"{module_count} modules")
        if service_count:
            details.append(f"{service_count} services")
        if component_count:
            details.append(f"{component_count} components")
        if class_count:
            details.append(f"{class_count} classes (estimated)")
        if function_count:
            details.append(f"{function_count} functions (estimated)")
        if interface_count:
            details.append(f"{interface_count} interfaces (estimated)")
        if background_task_count:
            details.append(
                f"{background_task_count} background tasks (estimated)"
            )
        if external_integration_count:
            details.append(
                f"{external_integration_count} external integrations"
            )

        summary = (
            f"Project complexity: {complexity_level} "
            f"({total_elements} total elements)."
        )

        # ---- Findings ----
        if total_elements > COMPLEXITY_THRESHOLD_HIGH:
            self.findings.append(CapabilityFinding(
                severity=SEVERITY_WARNING,
                code="high_complexity",
                message=(
                    f"Project has very high complexity "
                    f"({total_elements} elements). This may "
                    f"impact build time and maintainability."
                ),
                affected="complexity",
                resolution_hint=(
                    "Consider splitting into smaller modules or "
                    "reducing external integrations."
                ),
                category="complexity",
            ))
        elif total_elements == 0:
            self.findings.append(CapabilityFinding(
                severity=SEVERITY_INFO,
                code="no_complexity_data",
                message=(
                    "No architectural elements detected. "
                    "Complexity analysis is based on defaults."
                ),
                affected="complexity",
                resolution_hint=(
                    "Ensure the architecture decision and "
                    "intelligence graph are available."
                ),
                category="complexity",
            ))

        return ComplexityAnalysis(
            module_count=module_count,
            service_count=service_count,
            component_count=component_count,
            class_count=class_count,
            function_count=function_count,
            interface_count=interface_count,
            background_task_count=background_task_count,
            external_integration_count=external_integration_count,
            total_elements=total_elements,
            complexity_level=complexity_level,
            score=score,
            summary=summary,
            details=details,
        )

    # ----------------------------------------------------------------- #
    # Private helpers
    # ----------------------------------------------------------------- #

    def _estimate_background_tasks(
        self,
        arch_data: ArchitectureDecisionData,
        req_data: RequirementNormalizationData,
    ) -> int:
        """Estimate the number of background tasks.

        Async/event-driven architectures tend to have more
        background tasks (scheduled jobs, workers, listeners).
        """
        base = 1  # At least one (the main bot loop).

        # Async patterns add more background tasks.
        comm = arch_data.communication.lower()
        if "async" in comm or "event" in comm:
            base += 2

        # Each non-functional requirement may add a background task.
        non_func_count = len(req_data.non_functional)
        base += non_func_count

        return base

    def _estimate_external_integrations(
        self,
        req_data: RequirementNormalizationData,
        tech_data: TechnologySelectionData,
    ) -> int:
        """Estimate the number of external integrations.

        External integrations include third-party APIs, webhooks,
        payment gateways, and external services.
        """
        # Base: one for each selected technology that implies an
        # external service (database, cache, queue, storage).
        base = 0
        for tech_name in tech_data.selected_technologies:
            name_lower = tech_name.lower()
            if any(
                kw in name_lower
                for kw in (
                    "redis", "rabbitmq", "kafka", "s3",
                    "elasticsearch", "postgres", "mysql",
                    "mongodb", "memcached",
                )
            ):
                base += 1

        # Each requirement that mentions "integration" or "external"
        # adds an integration.
        for req in req_data.requirements:
            if isinstance(req, dict):
                desc = str(req.get("description", "")).lower()
                name = str(req.get("name", "")).lower()
                if "integration" in desc or "external" in desc:
                    base += 1
                if "webhook" in name or "webhook" in desc:
                    base += 1

        return base

    def _classify_complexity(self, total: int) -> str:
        """Classify the complexity level by total element count.

        Args:
            total: The total number of elements.

        Returns:
            The complexity level string.
        """
        if total <= COMPLEXITY_THRESHOLD_TRIVIAL:
            return COMPLEXITY_TRIVIAL
        if total <= COMPLEXITY_THRESHOLD_LOW:
            return COMPLEXITY_LOW
        if total <= COMPLEXITY_THRESHOLD_MODERATE:
            return COMPLEXITY_MODERATE
        if total <= COMPLEXITY_THRESHOLD_HIGH:
            return COMPLEXITY_HIGH
        return COMPLEXITY_VERY_HIGH

    def _calculate_score(self, total: int) -> float:
        """Calculate the complexity score (0.0-1.0).

        Higher score means more complex.  The score is a logarithmic
        scale so that very large projects don't saturate at 1.0.

        Args:
            total: The total number of elements.

        Returns:
            The complexity score.
        """
        if total <= 0:
            return 0.0
        # Logarithmic: score = log10(total + 1) / 3, capped at 1.0.
        import math
        score = math.log10(total + 1) / 3.0
        return max(0.0, min(1.0, score))


__all__ = ["ComplexityAnalyzer"]
