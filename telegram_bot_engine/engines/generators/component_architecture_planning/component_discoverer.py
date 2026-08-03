"""
ComponentDiscoverer — Specification 022

For every module, discovers the required components (controllers, services,
repositories, adapters, validators, helpers, factories, strategies, etc.).
"""

from __future__ import annotations

import logging
from typing import List

from .report_data import (
    ComponentDescriptor,
    ComponentInterface,
    KIND_CONTROLLER,
    KIND_SERVICE,
    KIND_MANAGER,
    KIND_REPOSITORY,
    KIND_ADAPTER,
    KIND_VALIDATOR,
    KIND_HELPER,
    KIND_UTILITY,
    KIND_FACTORY,
    KIND_STRATEGY,
    KIND_PROVIDER,
    COMM_INTERFACE,
)
from .data_readers import ModuleArchitectureData, ArchitectureDecisionData

_log = logging.getLogger("engine.component_architecture_planning.component_discoverer")


class ComponentDiscoverer:
    def discover(
        self,
        mod_data: ModuleArchitectureData,
        arch_data: ArchitectureDecisionData,
    ) -> List[ComponentDescriptor]:
        components: List[ComponentDescriptor] = []
        modules = mod_data.modules if mod_data.available else []

        # Fallback minimal module list if upstream missing
        if not modules:
            modules = [
                {"module_id": "mod.core.domain", "name": "Domain", "category": "core"},
                {"module_id": "mod.core.handlers", "name": "Handlers", "category": "core"},
                {"module_id": "mod.core.services", "name": "Services", "category": "core"},
                {"module_id": "mod.infra.persistence", "name": "Persistence", "category": "infrastructure"},
                {"module_id": "mod.integration.telegram", "name": "Telegram", "category": "integration"},
            ]

        for m in modules:
            if not isinstance(m, dict):
                continue
            mid = m.get("module_id") or m.get("id") or ""
            mname = m.get("name") or mid
            cat = (m.get("category") or "").lower()

            if "domain" in mid or cat == "core" and "model" in mname.lower():
                components.extend(self._domain_components(mid, mname))
            elif "handler" in mid or "handler" in mname.lower():
                components.extend(self._handler_components(mid, mname))
            elif "service" in mid or cat == "core":
                components.extend(self._service_components(mid, mname))
            elif "persist" in mid or "database" in mid or cat == "infrastructure":
                components.extend(self._persistence_components(mid, mname))
            elif "telegram" in mid or cat == "integration":
                components.extend(self._integration_components(mid, mname))
            elif cat == "business":
                components.extend(self._business_components(mid, mname))
            elif cat == "support":
                components.extend(self._support_components(mid, mname))
            elif cat == "testing":
                components.extend(self._testing_components(mid, mname))
            else:
                components.extend(self._generic_components(mid, mname))

        _log.info("ComponentDiscoverer produced %d components", len(components))
        return components

    def _iface(self, cid: str, name: str, methods: List[str]) -> ComponentInterface:
        return ComponentInterface(interface_id=f"iface.{cid}", name=name, methods=methods)

    def _domain_components(self, mid: str, mname: str) -> List[ComponentDescriptor]:
        return [
            ComponentDescriptor(
                component_id=f"{mid}.entity",
                name=f"{mname} Entity",
                kind=KIND_SERVICE,
                module_id=mid,
                purpose="Domain entity definitions",
                responsibility="Hold pure domain state and invariants",
                boundaries="No I/O, no infrastructure",
                interfaces=[self._iface(f"{mid}.entity", "IEntity", ["validate"])],
                communication_rules=[COMM_INTERFACE],
                reusable=True,
                tags=["domain", "entity"],
            ),
            ComponentDescriptor(
                component_id=f"{mid}.factory",
                name=f"{mname} Factory",
                kind=KIND_FACTORY,
                module_id=mid,
                purpose="Create domain objects",
                responsibility="Construct valid domain entities",
                depends_on=[f"{mid}.entity"],
                interfaces=[self._iface(f"{mid}.factory", "IFactory", ["create"])],
                communication_rules=[COMM_INTERFACE],
                reusable=True,
                tags=["domain", "factory"],
            ),
        ]

    def _handler_components(self, mid: str, mname: str) -> List[ComponentDescriptor]:
        return [
            ComponentDescriptor(
                component_id=f"{mid}.controller",
                name=f"{mname} Controller",
                kind=KIND_CONTROLLER,
                module_id=mid,
                purpose="Receive Telegram updates",
                responsibility="Route updates to the correct service",
                boundaries="No business logic",
                interfaces=[self._iface(f"{mid}.controller", "IController", ["handle"])],
                communication_rules=[COMM_INTERFACE],
                tags=["handler", "controller"],
            ),
            ComponentDescriptor(
                component_id=f"{mid}.validator",
                name=f"{mname} Input Validator",
                kind=KIND_VALIDATOR,
                module_id=mid,
                purpose="Validate incoming payloads",
                responsibility="Reject malformed updates early",
                interfaces=[self._iface(f"{mid}.validator", "IValidator", ["validate"])],
                communication_rules=[COMM_INTERFACE],
                reusable=True,
                tags=["handler", "validator"],
            ),
        ]

    def _service_components(self, mid: str, mname: str) -> List[ComponentDescriptor]:
        return [
            ComponentDescriptor(
                component_id=f"{mid}.service",
                name=f"{mname} Service",
                kind=KIND_SERVICE,
                module_id=mid,
                purpose="Orchestrate use-cases",
                responsibility="Coordinate domain objects to fulfil intentions",
                interfaces=[self._iface(f"{mid}.service", "IService", ["execute"])],
                communication_rules=[COMM_INTERFACE],
                tags=["service"],
            ),
            ComponentDescriptor(
                component_id=f"{mid}.manager",
                name=f"{mname} Manager",
                kind=KIND_MANAGER,
                module_id=mid,
                purpose="Manage lifecycle of related objects",
                responsibility="Track and coordinate multiple related entities",
                depends_on=[f"{mid}.service"],
                interfaces=[self._iface(f"{mid}.manager", "IManager", ["start", "stop"])],
                communication_rules=[COMM_INTERFACE],
                tags=["manager"],
            ),
        ]

    def _persistence_components(self, mid: str, mname: str) -> List[ComponentDescriptor]:
        return [
            ComponentDescriptor(
                component_id=f"{mid}.repository",
                name=f"{mname} Repository",
                kind=KIND_REPOSITORY,
                module_id=mid,
                purpose="Persist and retrieve entities",
                responsibility="CRUD operations against the data store",
                boundaries="No business rules",
                interfaces=[self._iface(f"{mid}.repository", "IRepository", ["save", "get", "delete", "list"])],
                communication_rules=[COMM_INTERFACE],
                tags=["persistence", "repository"],
            ),
            ComponentDescriptor(
                component_id=f"{mid}.adapter",
                name=f"{mname} DB Adapter",
                kind=KIND_ADAPTER,
                module_id=mid,
                purpose="Adapt the concrete database driver",
                responsibility="Translate repository calls to driver-specific API",
                depends_on=[f"{mid}.repository"],
                interfaces=[self._iface(f"{mid}.adapter", "IDBAdapter", ["execute"])],
                communication_rules=[COMM_INTERFACE],
                tags=["persistence", "adapter"],
            ),
        ]

    def _integration_components(self, mid: str, mname: str) -> List[ComponentDescriptor]:
        return [
            ComponentDescriptor(
                component_id=f"{mid}.adapter",
                name=f"{mname} Adapter",
                kind=KIND_ADAPTER,
                module_id=mid,
                purpose="Talk to external system",
                responsibility="Translate internal commands to external API calls",
                interfaces=[self._iface(f"{mid}.adapter", "IExternalAdapter", ["send", "receive"])],
                communication_rules=[COMM_INTERFACE],
                tags=["integration", "adapter"],
            ),
            ComponentDescriptor(
                component_id=f"{mid}.provider",
                name=f"{mname} Provider",
                kind=KIND_PROVIDER,
                module_id=mid,
                purpose="Provide configured client instances",
                responsibility="Create and configure external clients",
                interfaces=[self._iface(f"{mid}.provider", "IProvider", ["get_client"])],
                communication_rules=[COMM_INTERFACE],
                reusable=True,
                tags=["integration", "provider"],
            ),
        ]

    def _business_components(self, mid: str, mname: str) -> List[ComponentDescriptor]:
        return [
            ComponentDescriptor(
                component_id=f"{mid}.service",
                name=f"{mname} Service",
                kind=KIND_SERVICE,
                module_id=mid,
                purpose=f"Implement {mname} feature logic",
                responsibility=f"Own all behaviour related to {mname}",
                interfaces=[self._iface(f"{mid}.service", "IFeatureService", ["execute"])],
                communication_rules=[COMM_INTERFACE],
                tags=["business", "service"],
            ),
            ComponentDescriptor(
                component_id=f"{mid}.strategy",
                name=f"{mname} Strategy",
                kind=KIND_STRATEGY,
                module_id=mid,
                purpose="Encapsulate variable algorithms",
                responsibility="Allow swapping behaviour without changing the service",
                interfaces=[self._iface(f"{mid}.strategy", "IStrategy", ["apply"])],
                communication_rules=[COMM_INTERFACE],
                reusable=True,
                tags=["business", "strategy"],
            ),
        ]

    def _support_components(self, mid: str, mname: str) -> List[ComponentDescriptor]:
        return [
            ComponentDescriptor(
                component_id=f"{mid}.helper",
                name=f"{mname} Helper",
                kind=KIND_HELPER,
                module_id=mid,
                purpose="Pure helper functions",
                responsibility="Side-effect-free utilities",
                interfaces=[self._iface(f"{mid}.helper", "IHelper", ["*"])],
                communication_rules=[COMM_INTERFACE],
                reusable=True,
                tags=["support", "helper"],
            ),
            ComponentDescriptor(
                component_id=f"{mid}.utility",
                name=f"{mname} Utility",
                kind=KIND_UTILITY,
                module_id=mid,
                purpose="Shared low-level utilities",
                responsibility="Provide reusable pure functions",
                interfaces=[self._iface(f"{mid}.utility", "IUtility", ["*"])],
                communication_rules=[COMM_INTERFACE],
                reusable=True,
                tags=["support", "utility"],
            ),
        ]

    def _testing_components(self, mid: str, mname: str) -> List[ComponentDescriptor]:
        return [
            ComponentDescriptor(
                component_id=f"{mid}.suite",
                name=f"{mname} Test Suite",
                kind=KIND_OTHER,
                module_id=mid,
                purpose="Unit / integration test suite",
                responsibility="Verify module behaviour in isolation",
                tags=["testing"],
            ),
        ]

    def _generic_components(self, mid: str, mname: str) -> List[ComponentDescriptor]:
        return [
            ComponentDescriptor(
                component_id=f"{mid}.service",
                name=f"{mname} Service",
                kind=KIND_SERVICE,
                module_id=mid,
                purpose=f"Core logic for {mname}",
                responsibility=f"Implement {mname} behaviour",
                interfaces=[self._iface(f"{mid}.service", "IService", ["execute"])],
                communication_rules=[COMM_INTERFACE],
                tags=["generic"],
            ),
        ]


__all__ = ["ComponentDiscoverer"]
