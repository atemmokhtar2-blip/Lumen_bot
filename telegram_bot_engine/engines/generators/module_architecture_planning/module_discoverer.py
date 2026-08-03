"""
ModuleDiscoverer — Specification 021

Discovers all required modules (Core, Business, Infrastructure,
Integration, Support, Testing) from upstream artefacts and assigns
clear responsibilities.
"""

from __future__ import annotations

import logging
from typing import List

from .report_data import (
    ModuleDescriptor,
    ModuleInterface,
    CATEGORY_CORE,
    CATEGORY_BUSINESS,
    CATEGORY_INFRASTRUCTURE,
    CATEGORY_INTEGRATION,
    CATEGORY_SUPPORT,
    CATEGORY_TESTING,
    COMM_INTERFACE,
    COMM_EVENT,
)
from .data_readers import (
    ExecutionPlanData,
    ProjectStructureData,
    ArchitectureDecisionData,
    RequirementNormalizationData,
    TechnologySelectionData,
)

_log = logging.getLogger("engine.module_architecture_planning.module_discoverer")


class ModuleDiscoverer:
    """Produces the initial list of ModuleDescriptor objects."""

    def discover(
        self,
        exec_data: ExecutionPlanData,
        struct_data: ProjectStructureData,
        arch_data: ArchitectureDecisionData,
        req_data: RequirementNormalizationData,
        tech_data: TechnologySelectionData,
    ) -> List[ModuleDescriptor]:
        modules: List[ModuleDescriptor] = []

        # ------------------------------------------------------------------ #
        # Core modules (always present)
        # ------------------------------------------------------------------ #
        modules.append(ModuleDescriptor(
            module_id="mod.core.domain",
            name="Domain Models",
            category=CATEGORY_CORE,
            purpose="Hold pure domain entities and value objects",
            responsibility="Define and protect the core business concepts",
            boundaries="Must not depend on infrastructure or presentation layers",
            inputs=["raw domain data"],
            outputs=["domain entities", "value objects"],
            interfaces=[ModuleInterface(
                interface_id="iface.domain",
                name="IDomainModels",
                description="Public domain model API",
                methods=["create_entity", "validate"],
            )],
            communication_rules=[COMM_INTERFACE],
            folder_path="core/models",
            tags=["core", "domain"],
        ))

        modules.append(ModuleDescriptor(
            module_id="mod.core.handlers",
            name="Handlers",
            category=CATEGORY_CORE,
            purpose="Receive and dispatch Telegram updates",
            responsibility="Translate incoming updates into application commands",
            boundaries="Must not contain business logic; only routing and adaptation",
            inputs=["Telegram Update"],
            outputs=["application commands", "callback events"],
            interfaces=[ModuleInterface(
                interface_id="iface.handlers",
                name="IHandlers",
                description="Handler registration and dispatch",
                methods=["register", "dispatch"],
            )],
            depends_on=["mod.core.domain"],
            communication_rules=[COMM_INTERFACE, COMM_EVENT],
            folder_path="handlers",
            tags=["core", "handlers"],
        ))

        modules.append(ModuleDescriptor(
            module_id="mod.core.services",
            name="Application Services",
            category=CATEGORY_CORE,
            purpose="Orchestrate use-cases",
            responsibility="Coordinate domain objects to fulfil user intentions",
            boundaries="Must not talk to the database or external APIs directly",
            inputs=["application commands"],
            outputs=["domain events", "results"],
            interfaces=[ModuleInterface(
                interface_id="iface.services",
                name="IApplicationServices",
                description="Use-case entry points",
                methods=["execute"],
            )],
            depends_on=["mod.core.domain"],
            communication_rules=[COMM_INTERFACE],
            folder_path="services",
            tags=["core", "services"],
        ))

        # ------------------------------------------------------------------ #
        # Infrastructure
        # ------------------------------------------------------------------ #
        modules.append(ModuleDescriptor(
            module_id="mod.infra.persistence",
            name="Persistence",
            category=CATEGORY_INFRASTRUCTURE,
            purpose="Persist and retrieve domain entities",
            responsibility="Implement repositories and unit-of-work",
            boundaries="Must not contain business rules",
            inputs=["domain entities"],
            outputs=["persisted entities", "query results"],
            interfaces=[ModuleInterface(
                interface_id="iface.persistence",
                name="IRepositories",
                description="Repository contracts",
                methods=["save", "get", "delete", "list"],
            )],
            depends_on=["mod.core.domain"],
            communication_rules=[COMM_INTERFACE],
            folder_path="database",
            tags=["infrastructure", "persistence"],
        ))

        modules.append(ModuleDescriptor(
            module_id="mod.infra.config",
            name="Configuration",
            category=CATEGORY_INFRASTRUCTURE,
            purpose="Centralised configuration",
            responsibility="Load and expose application settings",
            boundaries="Must not perform I/O beyond reading config sources",
            inputs=["environment variables", "config files"],
            outputs=["Settings object"],
            interfaces=[ModuleInterface(
                interface_id="iface.config",
                name="IConfig",
                description="Settings access",
                methods=["get", "reload"],
            )],
            communication_rules=[COMM_INTERFACE],
            folder_path="configs",
            tags=["infrastructure", "config"],
        ))

        # ------------------------------------------------------------------ #
        # Integration
        # ------------------------------------------------------------------ #
        modules.append(ModuleDescriptor(
            module_id="mod.integration.telegram",
            name="Telegram Adapter",
            category=CATEGORY_INTEGRATION,
            purpose="Talk to the Telegram Bot API",
            responsibility="Send messages, manage webhooks / polling",
            boundaries="Must not contain domain logic",
            inputs=["outbound messages", "API calls"],
            outputs=["Telegram responses", "update streams"],
            interfaces=[ModuleInterface(
                interface_id="iface.telegram",
                name="ITelegramClient",
                description="Telegram Bot API client",
                methods=["send_message", "answer_callback", "get_updates"],
            )],
            depends_on=["mod.infra.config"],
            communication_rules=[COMM_INTERFACE],
            folder_path="integrations/telegram",
            tags=["integration", "telegram"],
        ))

        # ------------------------------------------------------------------ #
        # Support
        # ------------------------------------------------------------------ #
        modules.append(ModuleDescriptor(
            module_id="mod.support.logging",
            name="Logging",
            category=CATEGORY_SUPPORT,
            purpose="Structured logging",
            responsibility="Provide a unified logging facade",
            boundaries="Must not decide what to log; only how",
            inputs=["log records"],
            outputs=["formatted log output"],
            interfaces=[ModuleInterface(
                interface_id="iface.logging",
                name="ILogger",
                description="Logging facade",
                methods=["debug", "info", "warning", "error"],
            )],
            communication_rules=[COMM_INTERFACE],
            folder_path="utils",
            tags=["support", "logging"],
        ))

        modules.append(ModuleDescriptor(
            module_id="mod.support.utils",
            name="Utilities",
            category=CATEGORY_SUPPORT,
            purpose="Shared pure helpers",
            responsibility="Provide side-effect-free utility functions",
            boundaries="Must not depend on any other project module",
            inputs=["primitive values"],
            outputs=["transformed values"],
            interfaces=[ModuleInterface(
                interface_id="iface.utils",
                name="IUtils",
                description="Utility helpers",
                methods=["*"],
            )],
            communication_rules=[COMM_INTERFACE],
            folder_path="utils",
            tags=["support", "utils"],
        ))

        # ------------------------------------------------------------------ #
        # Testing
        # ------------------------------------------------------------------ #
        modules.append(ModuleDescriptor(
            module_id="mod.testing.unit",
            name="Unit Tests",
            category=CATEGORY_TESTING,
            purpose="Verify individual units in isolation",
            responsibility="Contain unit-test suites for core and services",
            boundaries="Must not hit real external systems",
            inputs=["test fixtures"],
            outputs=["test results"],
            depends_on=["mod.core.domain", "mod.core.services"],
            communication_rules=[COMM_INTERFACE],
            folder_path="tests",
            tags=["testing", "unit"],
        ))

        # ------------------------------------------------------------------ #
        # Business / feature modules from requirements
        # ------------------------------------------------------------------ #
        if req_data.available and req_data.features:
            for idx, feature in enumerate(req_data.features[:10]):
                name = ""
                if isinstance(feature, dict):
                    name = feature.get("name") or feature.get("title") or f"Feature {idx}"
                else:
                    name = str(feature)
                safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in name.lower())[:30]
                modules.append(ModuleDescriptor(
                    module_id=f"mod.business.{safe}",
                    name=name,
                    category=CATEGORY_BUSINESS,
                    purpose=f"Implement the '{name}' feature",
                    responsibility=f"Own all behaviour related to '{name}'",
                    boundaries="Must not own infrastructure or cross-feature logic",
                    inputs=[f"{name} commands"],
                    outputs=[f"{name} results", f"{name} events"],
                    interfaces=[ModuleInterface(
                        interface_id=f"iface.business.{safe}",
                        name=f"I{safe.title().replace('_', '')}",
                        description=f"Public API for {name}",
                        methods=["execute"],
                    )],
                    depends_on=["mod.core.domain", "mod.core.services"],
                    communication_rules=[COMM_INTERFACE, COMM_EVENT],
                    folder_path=f"modules/{safe}",
                    tags=["business", "feature", safe],
                ))

        # If structure blueprint already listed modules, prefer / merge them
        if struct_data.available and struct_data.modules:
            existing_ids = {m.module_id for m in modules}
            for m in struct_data.modules:
                if not isinstance(m, dict):
                    continue
                mid = m.get("module_id") or m.get("id") or ""
                if mid and mid not in existing_ids:
                    modules.append(ModuleDescriptor(
                        module_id=mid,
                        name=m.get("name") or mid,
                        category=CATEGORY_BUSINESS,
                        purpose=m.get("description") or "",
                        responsibility=m.get("description") or "",
                        folder_path=m.get("folder_path") or "",
                        tags=["from_structure"],
                    ))

        _log.info("ModuleDiscoverer produced %d modules", len(modules))
        return modules


__all__ = ["ModuleDiscoverer"]
