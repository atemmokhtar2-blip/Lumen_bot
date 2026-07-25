"""
Architecture selector — makes all architectural decisions.

The :class:`ArchitectureSelector` is the core processing component
of the Architecture Decision Engine.  It takes the five analysis
results (size, scalability, performance, security, maintainability)
and the reader data, and makes all eight architectural decisions:

1. **Layers** — which architectural layers the project needs.
2. **Modules** — which modules the project needs (with their
   layers, responsibilities, and dependencies).
3. **Services** — which services the project needs (with their
   responsibilities, communication, and dependencies).
4. **Dependency structure** — flat, layered, hierarchical, or graph.
5. **Project layout** — feature-based, layer-based, domain-based,
   or hybrid.
6. **Communication pattern** — synchronous, asynchronous,
   event-driven, or hybrid.
7. **Error handling strategy** — centralized, distributed,
   layer-specific, or result-type.
8. **Configuration strategy** — static, environment, file-based,
   or hybrid.

Every decision has a reason, an analysis, an impact, and at least
one rejected alternative.  This is the "decision validation"
requirement of the specification.

This module is a pure processing component: it has no side effects
and does not modify the generation context.
"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    ArchitectureDecision,
    ModuleSpec,
    ServiceSpec,
    RejectedAlternative,
    AnalysisResult,
    DIMENSION_SIZE,
    DIMENSION_SCALABILITY,
    DIMENSION_PERFORMANCE,
    DIMENSION_SECURITY,
    DIMENSION_MAINTAINABILITY,
    DECISION_LAYERS,
    DECISION_MODULES,
    DECISION_SERVICES,
    DECISION_DEPENDENCY_STRUCTURE,
    DECISION_PROJECT_LAYOUT,
    DECISION_COMMUNICATION,
    DECISION_ERROR_HANDLING,
    DECISION_CONFIGURATION,
    PATTERN_BY_SIZE,
    PATTERN_MONOLITH,
    PATTERN_LAYERED,
    PATTERN_MODULAR_MONOLITH,
    PATTERN_MICROSERVICES,
    PATTERN_EVENT_DRIVEN,
    PATTERN_HEXAGONAL,
    LAYER_PRESENTATION,
    LAYER_BUSINESS,
    LAYER_DATA_ACCESS,
    LAYER_INFRASTRUCTURE,
    LAYER_INTEGRATION,
    LAYER_CACHING,
    LAYER_MESSAGING,
    COMM_SYNC,
    COMM_ASYNC,
    COMM_EVENT,
    COMM_HYBRID,
    ERROR_CENTRALIZED,
    ERROR_DISTRIBUTED,
    ERROR_LAYER_SPECIFIC,
    ERROR_RESULT_TYPE,
    CONFIG_STATIC,
    CONFIG_ENVIRONMENT,
    CONFIG_FILE_BASED,
    CONFIG_HYBRID,
    DEP_FLAT,
    DEP_LAYERED,
    DEP_HIERARCHICAL,
    DEP_GRAPH,
    LAYOUT_FEATURE_BASED,
    LAYOUT_LAYER_BASED,
    LAYOUT_DOMAIN_BASED,
    LAYOUT_HYBRID,
    SIZE_TINY,
    SIZE_SMALL,
    SIZE_MEDIUM,
    SIZE_LARGE,
    SIZE_VERY_LARGE,
    SOURCE_NORMALIZED_REQUIREMENTS,
    SOURCE_INTELLIGENCE_GRAPH,
    SOURCE_SEMANTIC_UNDERSTANDING,
)
from .intelligence_graph_reader import IntelligenceGraphData
from .requirement_normalization_reader import RequirementNormalizationData
from .requirement_intelligence_reader import RequirementIntelligenceData
from .semantic_understanding_reader import SemanticUnderstandingData


class ArchitectureSelector:
    """Makes all architectural decisions.

    The selector uses the five analysis results and the reader data
    to make the eight architectural decisions, the module
    specifications, and the service specifications.
    """

    def select(
        self,
        analyses: List[AnalysisResult],
        graph_data: IntelligenceGraphData,
        requirement_data: RequirementNormalizationData,
        requirement_intelligence_data: RequirementIntelligenceData,
        semantic_data: SemanticUnderstandingData,
    ) -> Tuple[
        List[ArchitectureDecision],
        List[ModuleSpec],
        List[ServiceSpec],
    ]:
        """Make all architectural decisions.

        Parameters:
            analyses: The five analysis results.
            graph_data: The intelligence graph data.
            requirement_data: The normalized requirement model.
            requirement_intelligence_data: The requirement
                intelligence data.
            semantic_data: The semantic understanding data.

        Returns:
            A tuple of (decisions, modules, services).
        """
        size_analysis = self._get_analysis(
            analyses, DIMENSION_SIZE
        )
        scalability_analysis = self._get_analysis(
            analyses, DIMENSION_SCALABILITY
        )
        performance_analysis = self._get_analysis(
            analyses, DIMENSION_PERFORMANCE
        )
        security_analysis = self._get_analysis(
            analyses, DIMENSION_SECURITY
        )
        maintainability_analysis = self._get_analysis(
            analyses, DIMENSION_MAINTAINABILITY
        )

        size_tier = (
            size_analysis.level if size_analysis else SIZE_SMALL
        )

        decisions: List[ArchitectureDecision] = []
        decisions.append(
            self._select_layers(
                size_tier,
                security_analysis,
                performance_analysis,
                semantic_data,
            )
        )
        decisions.append(
            self._select_dependency_structure(
                size_tier,
                graph_data,
                maintainability_analysis,
            )
        )
        decisions.append(
            self._select_project_layout(
                size_tier,
                maintainability_analysis,
                requirement_data,
            )
        )
        decisions.append(
            self._select_communication(
                size_tier,
                performance_analysis,
                graph_data,
            )
        )
        decisions.append(
            self._select_error_handling(
                size_tier,
                maintainability_analysis,
            )
        )
        decisions.append(
            self._select_configuration(size_tier, size_analysis)
        )

        modules = self._select_modules(
            size_tier,
            graph_data,
            requirement_data,
            decisions,
        )
        services = self._select_services(
            size_tier,
            graph_data,
            performance_analysis,
            decisions,
        )

        # The modules and services decisions reference the built
        # lists, so we add them after building.
        decisions.append(
            self._select_modules_decision(
                modules, size_tier, maintainability_analysis
            )
        )
        decisions.append(
            self._select_services_decision(
                services, size_tier, performance_analysis
            )
        )

        return decisions, modules, services

    # ----------------------------------------------------------------- #
    # Decision: layers
    # ----------------------------------------------------------------- #

    def _select_layers(
        self,
        size_tier: str,
        security_analysis: AnalysisResult,
        performance_analysis: AnalysisResult,
        semantic_data: SemanticUnderstandingData,
    ) -> ArchitectureDecision:
        """Select the architectural layers."""
        layers: List[str] = []
        reason_parts: List[str] = []
        analysis_parts: List[str] = []

        # All projects need presentation and business layers.
        layers.append(LAYER_PRESENTATION)
        layers.append(LAYER_BUSINESS)
        analysis_parts.append(
            "Every project needs a presentation layer and a "
            "business layer."
        )

        # All projects need data access and infrastructure.
        layers.append(LAYER_DATA_ACCESS)
        layers.append(LAYER_INFRASTRUCTURE)
        analysis_parts.append(
            "Data access and infrastructure layers are fundamental "
            "for any project that persists or manages resources."
        )

        # Integration layer for medium+ projects.
        if size_tier in (
            SIZE_MEDIUM, SIZE_LARGE, SIZE_VERY_LARGE
        ):
            layers.append(LAYER_INTEGRATION)
            analysis_parts.append(
                "An integration layer is needed for medium and "
                "larger projects that integrate with external "
                "services."
            )

        # Caching layer for performance-sensitive projects.
        if performance_analysis and performance_analysis.level == "high":
            layers.append(LAYER_CACHING)
            analysis_parts.append(
                "A caching layer is needed because the performance "
                f"analysis scored {performance_analysis.score:.2f} "
                "(high)."
            )
        elif size_tier in (SIZE_LARGE, SIZE_VERY_LARGE):
            layers.append(LAYER_CACHING)
            analysis_parts.append(
                "A caching layer is recommended for large and very "
                "large projects."
            )

        # Messaging layer for very large or event-driven projects.
        if size_tier == SIZE_VERY_LARGE:
            layers.append(LAYER_MESSAGING)
            analysis_parts.append(
                "A messaging layer is needed for very large "
                "projects that require asynchronous communication "
                "between components."
            )

        reason_parts.append(
            f"Selected {len(layers)} layers based on size tier "
            f"({size_tier}), performance "
            f"({performance_analysis.level if performance_analysis else 'unknown'}), "
            f"and project needs."
        )
        reason = " ".join(reason_parts)
        analysis = " ".join(analysis_parts)
        impact = (
            f"The selected layers provide clear separation of "
            f"concerns and support {size_tier}-scale projects."
        )

        rejected: List[RejectedAlternative] = []
        if LAYER_CACHING in layers:
            rejected.append(RejectedAlternative(
                name="No caching layer",
                reason=(
                    "A caching layer was included because the "
                    "performance analysis or project size "
                    "indicates performance-sensitive operations."
                ),
                impact=(
                    "Omitting caching would risk performance "
                    "bottlenecks under load."
                ),
            ))
        if LAYER_MESSAGING in layers:
            rejected.append(RejectedAlternative(
                name="No messaging layer",
                reason=(
                    "A messaging layer was included because the "
                    "project is very large and needs asynchronous "
                    "inter-component communication."
                ),
                impact=(
                    "Omitting messaging would force all "
                    "communication to be synchronous, limiting "
                    "scalability."
                ),
            ))
        if LAYER_INTEGRATION in layers:
            rejected.append(RejectedAlternative(
                name="No integration layer",
                reason=(
                    "An integration layer was included because "
                    "the project is medium or larger and likely "
                    "integrates with external services."
                ),
                impact=(
                    "Omitting the integration layer would mix "
                    "external-service code with business logic, "
                    "reducing maintainability."
                ),
            ))
        if not rejected:
            rejected.append(RejectedAlternative(
                name="Minimal (presentation + business only)",
                reason=(
                    "A minimal two-layer architecture was "
                    "rejected because data access and "
                    "infrastructure are fundamental."
                ),
                impact=(
                    "Without data access and infrastructure "
                    "layers, persistence and resource management "
                    "would be mixed into business logic."
                ),
            ))

        source = (
            SOURCE_SEMANTIC_UNDERSTANDING
            if semantic_data.available
            else SOURCE_NORMALIZED_REQUIREMENTS
        )

        return ArchitectureDecision(
            domain=DECISION_LAYERS,
            selected=", ".join(layers),
            reason=reason,
            analysis=analysis,
            impact=impact,
            rejected_alternatives=rejected,
            source_artefact=source,
            confidence=0.8,
        )

    # ----------------------------------------------------------------- #
    # Decision: dependency structure
    # ----------------------------------------------------------------- #

    def _select_dependency_structure(
        self,
        size_tier: str,
        graph_data: IntelligenceGraphData,
        maintainability_analysis: AnalysisResult,
    ) -> ArchitectureDecision:
        """Select the dependency structure."""
        if size_tier in (SIZE_TINY, SIZE_SMALL):
            selected = DEP_FLAT
            reason = (
                f"A flat dependency structure is sufficient for "
                f"a {size_tier} project with few components."
            )
        elif size_tier == SIZE_MEDIUM:
            selected = DEP_LAYERED
            reason = (
                "A layered dependency structure is appropriate "
                "for a medium project where components are "
                "organized into layers."
            )
        elif size_tier == SIZE_LARGE:
            selected = DEP_HIERARCHICAL
            reason = (
                "A hierarchical dependency structure is needed "
                "for a large project with many modules organized "
                "into a tree of dependencies."
            )
        else:
            selected = DEP_GRAPH
            reason = (
                "A graph dependency structure is needed for a "
                "very large project where dependencies form a "
                "complex network rather than a tree."
            )

        circular_count = (
            graph_data.circular_count if graph_data.available else 0
        )
        analysis = (
            f"The dependency structure is driven by the size tier "
            f"({size_tier}) and the graph structure "
            f"({graph_data.component_count if graph_data.available else 0} "
            f"components, {circular_count} circular dependencies)."
        )

        maint_score = (
            maintainability_analysis.score
            if maintainability_analysis else 0.0
        )
        impact = (
            f"The {selected} dependency structure supports the "
            f"project's maintainability score of "
            f"{maint_score:.2f}."
        )

        rejected: List[RejectedAlternative] = []
        all_structures = [
            (DEP_FLAT, "Flat", "simple but does not scale"),
            (DEP_LAYERED, "Layered", "good for medium projects"),
            (DEP_HIERARCHICAL, "Hierarchical", "good for large projects"),
            (DEP_GRAPH, "Graph", "needed for very large projects"),
        ]
        for name, label, _desc in all_structures:
            if name != selected:
                if selected == DEP_FLAT and name in (
                    DEP_LAYERED, DEP_HIERARCHICAL, DEP_GRAPH
                ):
                    rejected.append(RejectedAlternative(
                        name=f"{label} structure",
                        reason=(
                            f"A {label.lower()} structure is "
                            f"over-engineered for a {size_tier} "
                            f"project."
                        ),
                        impact=(
                            "Over-structuring would add complexity "
                            "without benefit."
                        ),
                    ))
                else:
                    rejected.append(RejectedAlternative(
                        name=f"{label} structure",
                        reason=(
                            f"A {label.lower()} structure does not "
                            f"match the {size_tier} project size."
                        ),
                        impact=(
                            "An under-structured architecture would "
                            "not support the project's scale."
                        ),
                    ))

        return ArchitectureDecision(
            domain=DECISION_DEPENDENCY_STRUCTURE,
            selected=selected,
            reason=reason,
            analysis=analysis,
            impact=impact,
            rejected_alternatives=rejected,
            source_artefact=SOURCE_INTELLIGENCE_GRAPH,
            confidence=0.85,
        )

    # ----------------------------------------------------------------- #
    # Decision: project layout
    # ----------------------------------------------------------------- #

    def _select_project_layout(
        self,
        size_tier: str,
        maintainability_analysis: AnalysisResult,
        requirement_data: RequirementNormalizationData,
    ) -> ArchitectureDecision:
        """Select the project layout."""
        if size_tier in (SIZE_TINY, SIZE_SMALL):
            selected = LAYOUT_LAYER_BASED
            reason = (
                f"A layer-based layout is clear and sufficient "
                f"for a {size_tier} project."
            )
        elif size_tier == SIZE_MEDIUM:
            selected = LAYOUT_FEATURE_BASED
            reason = (
                "A feature-based layout groups code by feature, "
                "improving discoverability for medium projects."
            )
        else:
            selected = LAYOUT_DOMAIN_BASED
            reason = (
                f"A domain-based layout is needed for {size_tier} "
                f"projects to keep domain logic cohesive."
            )

        analysis = (
            f"The layout is driven by the size tier "
            f"({size_tier}) and the maintainability need."
        )

        if size_tier in (SIZE_LARGE, SIZE_VERY_LARGE):
            selected = LAYOUT_HYBRID
            reason = (
                f"A hybrid layout (domain-based with feature-based "
                f"grouping) is needed for {size_tier} projects to "
                f"balance domain cohesion and feature discoverability."
            )
            analysis = (
                f"The hybrid layout combines domain-based and "
                f"feature-based approaches for {size_tier} "
                f"projects."
            )

        if maintainability_analysis is not None:
            _maint_score = maintainability_analysis.score
        else:
            _maint_score = 0.0
        impact = (
            f"The {selected} layout supports maintainability "
            f"score of "
            f"{_maint_score:.2f} "
            f"by keeping related code together."
        )

        rejected: List[RejectedAlternative] = []
        all_layouts = [
            (LAYOUT_LAYER_BASED, "Layer-based"),
            (LAYOUT_FEATURE_BASED, "Feature-based"),
            (LAYOUT_DOMAIN_BASED, "Domain-based"),
            (LAYOUT_HYBRID, "Hybrid"),
        ]
        for name, label in all_layouts:
            if name != selected:
                rejected.append(RejectedAlternative(
                    name=f"{label} layout",
                    reason=(
                        f"The {label.lower()} layout does not "
                        f"match the {size_tier} project size."
                    ),
                    impact=(
                        "A mismatched layout would reduce code "
                        "discoverability and maintainability."
                    ),
                ))

        return ArchitectureDecision(
            domain=DECISION_PROJECT_LAYOUT,
            selected=selected,
            reason=reason,
            analysis=analysis,
            impact=impact,
            rejected_alternatives=rejected,
            source_artefact=SOURCE_NORMALIZED_REQUIREMENTS,
            confidence=0.8,
        )

    # ----------------------------------------------------------------- #
    # Decision: communication pattern
    # ----------------------------------------------------------------- #

    def _select_communication(
        self,
        size_tier: str,
        performance_analysis: AnalysisResult,
        graph_data: IntelligenceGraphData,
    ) -> ArchitectureDecision:
        """Select the communication pattern."""
        if size_tier in (SIZE_TINY, SIZE_SMALL):
            selected = COMM_SYNC
            reason = (
                f"Synchronous communication is simplest and "
                f"sufficient for a {size_tier} project."
            )
        elif size_tier == SIZE_MEDIUM:
            selected = COMM_HYBRID
            reason = (
                "A hybrid communication pattern (sync for "
                "request-response, async for long-running) is "
                "appropriate for a medium project."
            )
        elif size_tier == SIZE_LARGE:
            selected = COMM_HYBRID
            reason = (
                "A hybrid communication pattern balances "
                "simplicity and scalability for a large project."
            )
        else:
            selected = COMM_EVENT
            reason = (
                "Event-driven communication is needed for a "
                "very large project to decouple components."
            )

        perf_level = (
            performance_analysis.level
            if performance_analysis else "unknown"
        )
        analysis = (
            f"The communication pattern is driven by the size tier "
            f"({size_tier}) and performance level ({perf_level})."
        )

        impact = (
            f"The {selected} communication pattern supports the "
            f"project's scalability and performance needs."
        )

        rejected: List[RejectedAlternative] = []
        all_comms = [
            (COMM_SYNC, "Synchronous"),
            (COMM_ASYNC, "Asynchronous"),
            (COMM_EVENT, "Event-driven"),
            (COMM_HYBRID, "Hybrid"),
        ]
        for name, label in all_comms:
            if name != selected:
                rejected.append(RejectedAlternative(
                    name=f"{label} communication",
                    reason=(
                        f"The {label.lower()} pattern does not "
                        f"match the {size_tier} project size "
                        f"and performance needs."
                    ),
                    impact=(
                        "A mismatched communication pattern would "
                        "either add unnecessary complexity or limit "
                        "scalability."
                    ),
                ))

        return ArchitectureDecision(
            domain=DECISION_COMMUNICATION,
            selected=selected,
            reason=reason,
            analysis=analysis,
            impact=impact,
            rejected_alternatives=rejected,
            source_artefact=SOURCE_INTELLIGENCE_GRAPH,
            confidence=0.8,
        )

    # ----------------------------------------------------------------- #
    # Decision: error handling strategy
    # ----------------------------------------------------------------- #

    def _select_error_handling(
        self,
        size_tier: str,
        maintainability_analysis: AnalysisResult,
    ) -> ArchitectureDecision:
        """Select the error handling strategy."""
        if size_tier in (SIZE_TINY, SIZE_SMALL):
            selected = ERROR_CENTRALIZED
            reason = (
                f"A centralized error handling strategy is "
                f"simplest and sufficient for a {size_tier} "
                f"project."
            )
        elif size_tier == SIZE_MEDIUM:
            selected = ERROR_LAYER_SPECIFIC
            reason = (
                "A layer-specific error handling strategy is "
                "appropriate for a medium project where each "
                "layer has different error semantics."
            )
        elif size_tier == SIZE_LARGE:
            selected = ERROR_RESULT_TYPE
            reason = (
                "A result-type error handling strategy (returning "
                "Result objects instead of raising) is appropriate "
                "for a large project to make errors explicit."
            )
        else:
            selected = ERROR_DISTRIBUTED
            reason = (
                "A distributed error handling strategy is needed "
                "for a very large project where each service "
                "handles its own errors."
            )

        maint_score = (
            maintainability_analysis.score
            if maintainability_analysis else 0.0
        )
        analysis = (
            f"The error handling strategy is driven by the size "
            f"tier ({size_tier}) and maintainability need "
            f"(score {maint_score:.2f})."
        )

        impact = (
            f"The {selected} strategy balances simplicity and "
            f"explicitness for a {size_tier} project."
        )

        rejected: List[RejectedAlternative] = []
        all_errors = [
            (ERROR_CENTRALIZED, "Centralized"),
            (ERROR_DISTRIBUTED, "Distributed"),
            (ERROR_LAYER_SPECIFIC, "Layer-specific"),
            (ERROR_RESULT_TYPE, "Result-type"),
        ]
        for name, label in all_errors:
            if name != selected:
                rejected.append(RejectedAlternative(
                    name=f"{label} error handling",
                    reason=(
                        f"The {label.lower()} strategy does not "
                        f"match the {size_tier} project size."
                    ),
                    impact=(
                        "A mismatched error handling strategy "
                        "would either over-simplify or over-"
                        "complicate error management."
                    ),
                ))

        return ArchitectureDecision(
            domain=DECISION_ERROR_HANDLING,
            selected=selected,
            reason=reason,
            analysis=analysis,
            impact=impact,
            rejected_alternatives=rejected,
            source_artefact=SOURCE_NORMALIZED_REQUIREMENTS,
            confidence=0.8,
        )

    # ----------------------------------------------------------------- #
    # Decision: configuration strategy
    # ----------------------------------------------------------------- #

    def _select_configuration(
        self,
        size_tier: str,
        size_analysis: AnalysisResult,
    ) -> ArchitectureDecision:
        """Select the configuration strategy."""
        if size_tier in (SIZE_TINY, SIZE_SMALL):
            selected = CONFIG_ENVIRONMENT
            reason = (
                f"An environment-based configuration strategy is "
                f"simple, secure, and sufficient for a "
                f"{size_tier} project."
            )
        elif size_tier == SIZE_MEDIUM:
            selected = CONFIG_FILE_BASED
            reason = (
                "A file-based configuration strategy is "
                "appropriate for a medium project with multiple "
                "configuration groups."
            )
        else:
            selected = CONFIG_HYBRID
            reason = (
                f"A hybrid configuration strategy (environment "
                f"for secrets, file-based for the rest) is "
                f"needed for {size_tier} projects."
            )

        analysis = (
            f"The configuration strategy is driven by the size "
            f"tier ({size_tier}) and the number of "
            f"configuration groups."
        )

        impact = (
            f"The {selected} strategy balances security (secrets "
            f"in environment) and flexibility (file-based) for a "
            f"{size_tier} project."
        )

        rejected: List[RejectedAlternative] = []
        all_configs = [
            (CONFIG_STATIC, "Static"),
            (CONFIG_ENVIRONMENT, "Environment"),
            (CONFIG_FILE_BASED, "File-based"),
            (CONFIG_HYBRID, "Hybrid"),
        ]
        for name, label in all_configs:
            if name != selected:
                if selected != CONFIG_STATIC and name == CONFIG_STATIC:
                    rejected.append(RejectedAlternative(
                        name=f"{label} configuration",
                        reason=(
                            "Static configuration is inflexible "
                            "and requires code changes to update "
                            "values."
                        ),
                        impact=(
                            "Static configuration would make "
                            "deployment and environment management "
                            "difficult."
                        ),
                    ))
                else:
                    rejected.append(RejectedAlternative(
                        name=f"{label} configuration",
                        reason=(
                            f"The {label.lower()} strategy does "
                            f"not match the {size_tier} project "
                            f"size."
                        ),
                        impact=(
                            "A mismatched configuration strategy "
                            "would either over-simplify or over-"
                            "complicate configuration management."
                        ),
                    ))

        return ArchitectureDecision(
            domain=DECISION_CONFIGURATION,
            selected=selected,
            reason=reason,
            analysis=analysis,
            impact=impact,
            rejected_alternatives=rejected,
            source_artefact=SOURCE_NORMALIZED_REQUIREMENTS,
            confidence=0.8,
        )

    # ----------------------------------------------------------------- #
    # Modules
    # ----------------------------------------------------------------- #

    def _select_modules(
        self,
        size_tier: str,
        graph_data: IntelligenceGraphData,
        requirement_data: RequirementNormalizationData,
        decisions: List[ArchitectureDecision],
    ) -> List[ModuleSpec]:
        """Build the module specifications.

        The modules are derived from the selected layers and the
        requirements/categories.  Each module belongs to a layer and
        has a responsibility.
        """
        modules: List[ModuleSpec] = []

        # Presentation layer module(s).
        modules.append(ModuleSpec(
            name="presentation",
            layer=LAYER_PRESENTATION,
            responsibility=(
                "Handles user interaction, input validation, "
                "and response formatting."
            ),
            dependencies=["business"],
        ))

        # Business layer module(s).
        business_deps = ["data_access", "infrastructure"]
        modules.append(ModuleSpec(
            name="business",
            layer=LAYER_BUSINESS,
            responsibility=(
                "Implements business logic, use cases, and "
                "domain rules."
            ),
            dependencies=business_deps,
        ))

        # Data access layer module.
        modules.append(ModuleSpec(
            name="data_access",
            layer=LAYER_DATA_ACCESS,
            responsibility=(
                "Manages data persistence, queries, and "
                "repository operations."
            ),
            dependencies=["infrastructure"],
        ))

        # Infrastructure layer module.
        modules.append(ModuleSpec(
            name="infrastructure",
            layer=LAYER_INFRASTRUCTURE,
            responsibility=(
                "Provides cross-cutting infrastructure: logging, "
                "configuration, error handling."
            ),
            dependencies=[],
        ))

        # Integration layer module (if selected).
        layers_decision = self._get_decision(
            decisions, DECISION_LAYERS
        )
        selected_layers = (
            layers_decision.selected
            if layers_decision
            else ""
        )
        if LAYER_INTEGRATION in selected_layers:
            modules.append(ModuleSpec(
                name="integration",
                layer=LAYER_INTEGRATION,
                responsibility=(
                    "Handles external service integration: APIs, "
                    "webhooks, third-party services."
                ),
                dependencies=["business"],
            ))

        # Caching layer module (if selected).
        if LAYER_CACHING in selected_layers:
            modules.append(ModuleSpec(
                name="caching",
                layer=LAYER_CACHING,
                responsibility=(
                    "Manages cache storage, invalidation, and "
                    "retrieval for performance-sensitive data."
                ),
                dependencies=["data_access"],
            ))

        # Messaging layer module (if selected).
        if LAYER_MESSAGING in selected_layers:
            modules.append(ModuleSpec(
                name="messaging",
                layer=LAYER_MESSAGING,
                responsibility=(
                    "Handles asynchronous message passing, queues, "
                    "and event publishing."
                ),
                dependencies=["business"],
            ))

        # For medium+ projects, split the business layer into
        # domain modules based on requirement categories.
        if (
            size_tier in (SIZE_MEDIUM, SIZE_LARGE, SIZE_VERY_LARGE)
            and requirement_data.available
        ):
            cat_counts = requirement_data.category_counts
            for category in cat_counts:
                if not category:
                    continue
                module_name = str(category).strip().lower().replace(
                    " ", "_"
                )
                if module_name and module_name not in (
                    m.name for m in modules
                ):
                    modules.append(ModuleSpec(
                        name=f"business_{module_name}",
                        layer=LAYER_BUSINESS,
                        responsibility=(
                            f"Implements business logic for the "
                            f"{category} domain."
                        ),
                        dependencies=["data_access", "infrastructure"],
                    ))

        return modules

    # ----------------------------------------------------------------- #
    # Services
    # ----------------------------------------------------------------- #

    def _select_services(
        self,
        size_tier: str,
        graph_data: IntelligenceGraphData,
        performance_analysis: AnalysisResult,
        decisions: List[ArchitectureDecision],
    ) -> List[ServiceSpec]:
        """Build the service specifications.

        For small projects, there is typically a single service.
        For larger projects, the business logic is split into
        multiple services.
        """
        services: List[ServiceSpec] = []

        if size_tier in (SIZE_TINY, SIZE_SMALL):
            # Single service for small projects.
            services.append(ServiceSpec(
                name="application",
                responsibility=(
                    "Handles all application logic: business "
                    "rules, data access, and integration."
                ),
                communication=COMM_SYNC,
                dependencies=[],
            ))
            return services

        # For medium+ projects, split into core services.
        comm_decision = self._get_decision(
            decisions, DECISION_COMMUNICATION
        )
        comm_pattern = (
            comm_decision.selected if comm_decision else COMM_SYNC
        )

        services.append(ServiceSpec(
            name="core_service",
            responsibility=(
                "Handles core business logic and orchestration."
            ),
            communication=comm_pattern,
            dependencies=[],
        ))

        services.append(ServiceSpec(
            name="data_service",
            responsibility=(
                "Handles data persistence and repository "
                "operations."
            ),
            communication=COMM_SYNC,
            dependencies=[],
        ))

        # For large/very large projects, add more services.
        if size_tier in (SIZE_LARGE, SIZE_VERY_LARGE):
            services.append(ServiceSpec(
                name="integration_service",
                responsibility=(
                    "Handles external service integration."
                ),
                communication=comm_pattern,
                dependencies=["core_service"],
            ))

            if LAYER_CACHING in (
                self._get_decision(decisions, DECISION_LAYERS).selected
                if self._get_decision(decisions, DECISION_LAYERS)
                else ""
            ):
                services.append(ServiceSpec(
                    name="cache_service",
                    responsibility=(
                        "Handles cache management and retrieval."
                    ),
                    communication=COMM_SYNC,
                    dependencies=["data_service"],
                ))

        if size_tier == SIZE_VERY_LARGE:
            services.append(ServiceSpec(
                name="messaging_service",
                responsibility=(
                    "Handles asynchronous messaging and event "
                    "dispatch."
                ),
                communication=COMM_EVENT,
                dependencies=["core_service"],
            ))

        return services

    # ----------------------------------------------------------------- #
    # Decision: modules (references the built module list)
    # ----------------------------------------------------------------- #

    def _select_modules_decision(
        self,
        modules: List[ModuleSpec],
        size_tier: str,
        maintainability_analysis: AnalysisResult,
    ) -> ArchitectureDecision:
        """Create the modules decision referencing the built list."""
        module_names = [m.name for m in modules]
        layer_counts: dict = {}
        for m in modules:
            layer_counts[m.layer] = (
                layer_counts.get(m.layer, 0) + 1
            )

        reason = (
            f"Selected {len(modules)} modules organized across "
            f"{len(layer_counts)} layers for a {size_tier} project."
        )
        analysis = (
            f"Modules are derived from the selected layers and "
            f"requirement categories.  Layer distribution: "
            f"{layer_counts}."
        )
        maint_score = (
            maintainability_analysis.score
            if maintainability_analysis else 0.0
        )
        impact = (
            f"The module structure supports maintainability "
            f"score of "
            f"{maint_score:.2f} "
            f"by grouping related responsibilities."
        )

        rejected: List[RejectedAlternative] = []
        if len(modules) > 4:
            rejected.append(RejectedAlternative(
                name="Single module (monolith)",
                reason=(
                    "A single-module monolith was rejected "
                    "because the project size "
                    f"({size_tier}) requires separation of "
                    "concerns."
                ),
                impact=(
                    "A monolith would mix all responsibilities "
                    "into one module, reducing maintainability."
                ),
            ))
        else:
            rejected.append(RejectedAlternative(
                name="Many small modules (one per feature)",
                reason=(
                    "Splitting into one module per feature was "
                    "rejected because the project size "
                    f"({size_tier}) does not justify the overhead."
                ),
                impact=(
                    "Over-splitting would add module management "
                    "overhead without benefit."
                ),
            ))

        return ArchitectureDecision(
            domain=DECISION_MODULES,
            selected=", ".join(module_names),
            reason=reason,
            analysis=analysis,
            impact=impact,
            rejected_alternatives=rejected,
            source_artefact=SOURCE_NORMALIZED_REQUIREMENTS,
            confidence=0.8,
        )

    # ----------------------------------------------------------------- #
    # Decision: services (references the built service list)
    # ----------------------------------------------------------------- #

    def _select_services_decision(
        self,
        services: List[ServiceSpec],
        size_tier: str,
        performance_analysis: AnalysisResult,
    ) -> ArchitectureDecision:
        """Create the services decision referencing the built list."""
        service_names = [s.name for s in services]

        reason = (
            f"Selected {len(services)} services for a "
            f"{size_tier} project."
        )
        analysis = (
            f"Services are derived from the size tier and "
            f"performance analysis "
            f"(level: {performance_analysis.level if performance_analysis else 'unknown'})."
        )
        impact = (
            f"The service structure supports the project's "
            f"scalability and performance needs."
        )

        rejected: List[RejectedAlternative] = []
        if len(services) > 1:
            rejected.append(RejectedAlternative(
                name="Single service (monolith)",
                reason=(
                    f"A single-service monolith was rejected "
                    f"because the {size_tier} project requires "
                    f"service separation."
                ),
                impact=(
                    "A monolith would limit scalability and "
                    "make independent deployment impossible."
                ),
            ))
        else:
            rejected.append(RejectedAlternative(
                name="Multiple services (microservices)",
                reason=(
                    "A microservice architecture was rejected "
                    f"because the {size_tier} project does not "
                    "justify the operational overhead."
                ),
                impact=(
                    "Microservices would add deployment and "
                    "communication overhead without benefit."
                ),
            ))

        return ArchitectureDecision(
            domain=DECISION_SERVICES,
            selected=", ".join(service_names),
            reason=reason,
            analysis=analysis,
            impact=impact,
            rejected_alternatives=rejected,
            source_artefact=SOURCE_INTELLIGENCE_GRAPH,
            confidence=0.8,
        )

    # ----------------------------------------------------------------- #
    # Internal helpers
    # ----------------------------------------------------------------- #

    @staticmethod
    def _get_analysis(
        analyses: List[AnalysisResult], dimension: str
    ) -> AnalysisResult:
        """Return the analysis for the given dimension, or None."""
        for a in analyses:
            if a.dimension == dimension:
                return a
        return None

    @staticmethod
    def _get_decision(
        decisions: List[ArchitectureDecision], domain: str
    ) -> ArchitectureDecision:
        """Return the decision for the given domain, or None."""
        for d in decisions:
            if d.domain == domain:
                return d
        return None


__all__ = ["ArchitectureSelector"]
