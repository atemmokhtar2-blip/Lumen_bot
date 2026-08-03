"""
PhasePlanner — Specification 019

Responsible for partitioning the overall work into the standard
execution phases and assigning candidate tasks to each phase.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .report_data import (
    ExecutionPhase,
    ExecutionTask,
    PHASE_FOUNDATION,
    PHASE_CORE_SYSTEM,
    PHASE_FEATURES,
    PHASE_INTEGRATIONS,
    PHASE_TESTING,
    PHASE_OPTIMIZATION,
    PHASE_DEPLOYMENT_PREPARATION,
    ALL_PHASES,
    PHASE_ORDER,
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_MEDIUM,
    PRIORITY_LOW,
    TASK_STATUS_PENDING,
)
from .data_readers import (
    RequirementNormalizationData,
    ArchitectureDecisionData,
    TechnologySelectionData,
    RiskAnalysisData,
    ProjectCapabilityData,
    KnowledgeData,
)

_log = logging.getLogger("engine.execution_planning.phase_planner")


class PhasePlanner:
    """Creates the ordered list of execution phases and seeds them
    with high-level tasks derived from upstream artefacts.
    """

    def __init__(self) -> None:
        self.findings: List[Any] = []

    def plan(
        self,
        req_data: RequirementNormalizationData,
        arch_data: ArchitectureDecisionData,
        tech_data: TechnologySelectionData,
        risk_data: RiskAnalysisData,
        cap_data: ProjectCapabilityData,
        kb_data: KnowledgeData,
    ) -> List[ExecutionPhase]:
        """Build the ordered list of ExecutionPhase objects.

        Returns:
            A list of phases sorted by their natural order.
        """
        self.findings = []
        phases: List[ExecutionPhase] = []

        # ------------------------------------------------------------------ #
        # 1. Create the canonical phase shells
        # ------------------------------------------------------------------ #
        phase_definitions = [
            (PHASE_FOUNDATION, "Foundation",
             "Project scaffolding, configuration, core infrastructure and logging."),
            (PHASE_CORE_SYSTEM, "Core System",
             "Core domain logic, main handlers, state management and internal APIs."),
            (PHASE_FEATURES, "Features",
             "User-facing features and business capabilities."),
            (PHASE_INTEGRATIONS, "Integrations",
             "External services, third-party APIs, databases and messaging."),
            (PHASE_TESTING, "Testing",
             "Unit, integration, end-to-end and regression test suites."),
            (PHASE_OPTIMIZATION, "Optimization",
             "Performance tuning, caching, resource optimisation."),
            (PHASE_DEPLOYMENT_PREPARATION, "Deployment Preparation",
             "Packaging, environment configuration, CI/CD and deployment artefacts."),
        ]

        phase_map: Dict[str, ExecutionPhase] = {}
        for phase_id, name, description in phase_definitions:
            phase = ExecutionPhase(
                phase_id=phase_id,
                name=name,
                description=description,
                order=PHASE_ORDER.get(phase_id, 0),
                depends_on_phases=self._default_phase_dependencies(phase_id),
            )
            phase_map[phase_id] = phase
            phases.append(phase)

        # ------------------------------------------------------------------ #
        # 2. Seed tasks from available artefacts
        # ------------------------------------------------------------------ #
        self._seed_foundation_tasks(phase_map[PHASE_FOUNDATION], tech_data, arch_data)
        self._seed_core_tasks(phase_map[PHASE_CORE_SYSTEM], arch_data, req_data)
        self._seed_feature_tasks(phase_map[PHASE_FEATURES], req_data, cap_data)
        self._seed_integration_tasks(phase_map[PHASE_INTEGRATIONS], tech_data, arch_data)
        self._seed_testing_tasks(phase_map[PHASE_TESTING], req_data, risk_data)
        self._seed_optimization_tasks(phase_map[PHASE_OPTIMIZATION], risk_data, cap_data)
        self._seed_deployment_tasks(phase_map[PHASE_DEPLOYMENT_PREPARATION], tech_data)

        # ------------------------------------------------------------------ #
        # 3. Sort and return
        # ------------------------------------------------------------------ #
        phases.sort(key=lambda p: p.order)
        _log.info(
            "PhasePlanner produced %d phases with a total of %d tasks",
            len(phases),
            sum(len(p.tasks) for p in phases),
        )
        return phases

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _default_phase_dependencies(self, phase_id: str) -> List[str]:
        """Return the default predecessor phases for a given phase."""
        order = list(ALL_PHASES)
        try:
            idx = order.index(phase_id)
            if idx == 0:
                return []
            return [order[idx - 1]]
        except ValueError:
            return []

    def _make_task(
        self,
        task_id: str,
        name: str,
        phase: str,
        description: str = "",
        priority: str = PRIORITY_MEDIUM,
        depends_on: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
    ) -> ExecutionTask:
        return ExecutionTask(
            task_id=task_id,
            name=name,
            description=description,
            phase=phase,
            priority=priority,
            depends_on=depends_on or [],
            status=TASK_STATUS_PENDING,
            tags=tags or [],
        )

    def _seed_foundation_tasks(
        self,
        phase: ExecutionPhase,
        tech_data: TechnologySelectionData,
        arch_data: ArchitectureDecisionData,
    ) -> None:
        phase.tasks.append(self._make_task(
            "task.foundation.project_structure",
            "Create project structure",
            PHASE_FOUNDATION,
            "Generate the root package layout, configuration files and entry points.",
            PRIORITY_CRITICAL,
            tags=["structure", "bootstrap"],
        ))
        phase.tasks.append(self._make_task(
            "task.foundation.configuration",
            "Setup configuration system",
            PHASE_FOUNDATION,
            "Create centralised configuration, environment handling and defaults.",
            PRIORITY_CRITICAL,
            depends_on=["task.foundation.project_structure"],
            tags=["config"],
        ))
        phase.tasks.append(self._make_task(
            "task.foundation.logging",
            "Setup logging infrastructure",
            PHASE_FOUNDATION,
            "Configure structured logging, log levels and handlers.",
            PRIORITY_HIGH,
            depends_on=["task.foundation.configuration"],
            tags=["logging"],
        ))
        if tech_data.available and tech_data.language:
            phase.tasks.append(self._make_task(
                "task.foundation.language_runtime",
                f"Prepare {tech_data.language} runtime",
                PHASE_FOUNDATION,
                f"Ensure the {tech_data.language} runtime and packaging tools are ready.",
                PRIORITY_HIGH,
                depends_on=["task.foundation.project_structure"],
                tags=["runtime", tech_data.language.lower()],
            ))

    def _seed_core_tasks(
        self,
        phase: ExecutionPhase,
        arch_data: ArchitectureDecisionData,
        req_data: RequirementNormalizationData,
    ) -> None:
        phase.tasks.append(self._make_task(
            "task.core.domain_models",
            "Implement domain models",
            PHASE_CORE_SYSTEM,
            "Define the core domain entities and value objects.",
            PRIORITY_CRITICAL,
            tags=["domain", "models"],
        ))
        phase.tasks.append(self._make_task(
            "task.core.handlers",
            "Implement core handlers",
            PHASE_CORE_SYSTEM,
            "Create the main request/command handlers for the bot.",
            PRIORITY_CRITICAL,
            depends_on=["task.core.domain_models"],
            tags=["handlers"],
        ))
        phase.tasks.append(self._make_task(
            "task.core.state_management",
            "Implement state management",
            PHASE_CORE_SYSTEM,
            "Build conversation state and session management.",
            PRIORITY_HIGH,
            depends_on=["task.core.domain_models"],
            tags=["state"],
        ))
        if arch_data.available and arch_data.architecture_style:
            phase.tasks.append(self._make_task(
                "task.core.architecture_wiring",
                f"Wire {arch_data.architecture_style} architecture",
                PHASE_CORE_SYSTEM,
                f"Connect components according to the chosen {arch_data.architecture_style} style.",
                PRIORITY_HIGH,
                depends_on=["task.core.handlers"],
                tags=["architecture"],
            ))

    def _seed_feature_tasks(
        self,
        phase: ExecutionPhase,
        req_data: RequirementNormalizationData,
        cap_data: ProjectCapabilityData,
    ) -> None:
        # Always create a placeholder feature task.
        phase.tasks.append(self._make_task(
            "task.features.core_commands",
            "Implement core bot commands",
            PHASE_FEATURES,
            "Implement the essential user-facing commands.",
            PRIORITY_HIGH,
            tags=["commands", "features"],
        ))

        # Derive additional feature tasks from requirements when available.
        if req_data.available and req_data.features:
            for idx, feature in enumerate(req_data.features[:12]):  # safety limit
                name = ""
                if isinstance(feature, dict):
                    name = feature.get("name") or feature.get("title") or f"feature_{idx}"
                else:
                    name = str(feature)
                safe_id = "".join(c if c.isalnum() or c in "_-" else "_" for c in name.lower())[:40]
                phase.tasks.append(self._make_task(
                    f"task.features.{safe_id}",
                    f"Implement feature: {name}",
                    PHASE_FEATURES,
                    f"Build the feature '{name}' as derived from normalised requirements.",
                    PRIORITY_MEDIUM,
                    depends_on=["task.features.core_commands"],
                    tags=["feature", safe_id],
                ))

    def _seed_integration_tasks(
        self,
        phase: ExecutionPhase,
        tech_data: TechnologySelectionData,
        arch_data: ArchitectureDecisionData,
    ) -> None:
        phase.tasks.append(self._make_task(
            "task.integrations.database",
            "Integrate database layer",
            PHASE_INTEGRATIONS,
            "Connect the chosen database / ORM and create repositories.",
            PRIORITY_HIGH,
            tags=["database", "integration"],
        ))
        if tech_data.available and tech_data.database:
            phase.tasks[-1].description = (
                f"Integrate {tech_data.database} and create the data-access layer."
            )
            phase.tasks[-1].tags.append(tech_data.database.lower())

        phase.tasks.append(self._make_task(
            "task.integrations.external_apis",
            "Integrate external APIs",
            PHASE_INTEGRATIONS,
            "Wire any third-party HTTP / webhook integrations.",
            PRIORITY_MEDIUM,
            depends_on=["task.integrations.database"],
            tags=["api", "integration"],
        ))

    def _seed_testing_tasks(
        self,
        phase: ExecutionPhase,
        req_data: RequirementNormalizationData,
        risk_data: RiskAnalysisData,
    ) -> None:
        phase.tasks.append(self._make_task(
            "task.testing.unit",
            "Write unit tests",
            PHASE_TESTING,
            "Create unit tests for domain logic and handlers.",
            PRIORITY_HIGH,
            tags=["unit", "testing"],
        ))
        phase.tasks.append(self._make_task(
            "task.testing.integration",
            "Write integration tests",
            PHASE_TESTING,
            "Create integration tests covering database and external services.",
            PRIORITY_HIGH,
            depends_on=["task.testing.unit"],
            tags=["integration", "testing"],
        ))
        phase.tasks.append(self._make_task(
            "task.testing.e2e",
            "Write end-to-end tests",
            PHASE_TESTING,
            "Create end-to-end scenarios that exercise the full bot flow.",
            PRIORITY_MEDIUM,
            depends_on=["task.testing.integration"],
            tags=["e2e", "testing"],
        ))
        if risk_data.available and risk_data.critical_count > 0:
            phase.tasks.append(self._make_task(
                "task.testing.risk_regression",
                "Add risk-focused regression tests",
                PHASE_TESTING,
                "Create regression tests targeting previously identified critical risks.",
                PRIORITY_CRITICAL,
                depends_on=["task.testing.unit"],
                tags=["risk", "regression"],
            ))

    def _seed_optimization_tasks(
        self,
        phase: ExecutionPhase,
        risk_data: RiskAnalysisData,
        cap_data: ProjectCapabilityData,
    ) -> None:
        phase.tasks.append(self._make_task(
            "task.optimization.performance",
            "Performance optimisation",
            PHASE_OPTIMIZATION,
            "Profile and optimise hot paths identified during analysis.",
            PRIORITY_MEDIUM,
            tags=["performance"],
        ))
        phase.tasks.append(self._make_task(
            "task.optimization.caching",
            "Introduce caching where beneficial",
            PHASE_OPTIMIZATION,
            "Add caching layers for expensive or frequently accessed data.",
            PRIORITY_MEDIUM,
            depends_on=["task.optimization.performance"],
            tags=["cache"],
        ))
        if cap_data.available and cap_data.scalability_score < 0.5:
            phase.tasks.append(self._make_task(
                "task.optimization.scalability",
                "Scalability hardening",
                PHASE_OPTIMIZATION,
                "Address low scalability score with horizontal-scaling readiness.",
                PRIORITY_HIGH,
                tags=["scalability"],
            ))

    def _seed_deployment_tasks(
        self,
        phase: ExecutionPhase,
        tech_data: TechnologySelectionData,
    ) -> None:
        phase.tasks.append(self._make_task(
            "task.deployment.packaging",
            "Package the application",
            PHASE_DEPLOYMENT_PREPARATION,
            "Create installable package / container image.",
            PRIORITY_HIGH,
            tags=["packaging", "deployment"],
        ))
        phase.tasks.append(self._make_task(
            "task.deployment.env_config",
            "Prepare environment configuration",
            PHASE_DEPLOYMENT_PREPARATION,
            "Generate environment templates and secrets placeholders.",
            PRIORITY_HIGH,
            depends_on=["task.deployment.packaging"],
            tags=["env", "deployment"],
        ))
        phase.tasks.append(self._make_task(
            "task.deployment.ci_cd",
            "Setup CI/CD pipeline stubs",
            PHASE_DEPLOYMENT_PREPARATION,
            "Provide basic CI/CD configuration for continuous delivery.",
            PRIORITY_MEDIUM,
            depends_on=["task.deployment.packaging"],
            tags=["ci", "cd"],
        ))


__all__ = ["PhasePlanner"]
