"""
InterfaceDiscoverer — Specification 023

Discovers all required interfaces from components/modules and
builds formal contracts + communication rules.
"""

from __future__ import annotations

import logging
from typing import List, Tuple

from .report_data import (
    InterfaceDescriptor,
    InterfaceContract,
    CommunicationRule,
    DependencyRule,
    MethodSignature,
    SCOPE_COMPONENT,
    SCOPE_MODULE,
    SCOPE_SERVICE,
    SCOPE_REPOSITORY,
    SCOPE_EXTERNAL,
    COMM_VIA_INTERFACE,
    COMM_FORBIDDEN,
    SEVERITY_HIGH,
)
from .data_readers import (
    ComponentArchitectureData,
    ModuleArchitectureData,
    ArchitectureDecisionData,
)

_log = logging.getLogger("engine.interface_contract_planning.interface_discoverer")


class InterfaceDiscoverer:
    def discover(
        self,
        comp_data: ComponentArchitectureData,
        mod_data: ModuleArchitectureData,
        arch_data: ArchitectureDecisionData,
    ) -> Tuple[List[InterfaceDescriptor], List[InterfaceContract], List[CommunicationRule], List[DependencyRule]]:
        interfaces: List[InterfaceDescriptor] = []
        contracts: List[InterfaceContract] = []
        rules: List[CommunicationRule] = []
        dep_rules: List[DependencyRule] = []

        components = comp_data.components if comp_data.available else []
        # Fallback minimal set
        if not components:
            components = [
                {"component_id": "mod.core.handlers.controller", "name": "Handlers Controller", "kind": "controller", "module_id": "mod.core.handlers"},
                {"component_id": "mod.core.services.service", "name": "Services Service", "kind": "service", "module_id": "mod.core.services"},
                {"component_id": "mod.infra.persistence.repository", "name": "Persistence Repository", "kind": "repository", "module_id": "mod.infra.persistence"},
                {"component_id": "mod.integration.telegram.adapter", "name": "Telegram Adapter", "kind": "adapter", "module_id": "mod.integration.telegram"},
            ]

        for c in components:
            if not isinstance(c, dict):
                continue
            cid = c.get("component_id") or ""
            cname = c.get("name") or cid
            kind = (c.get("kind") or "").lower()
            mid = c.get("module_id") or ""

            # Re-use interfaces already declared on the component
            existing = c.get("interfaces") or []
            if existing and isinstance(existing, list):
                for ei in existing:
                    if not isinstance(ei, dict):
                        continue
                    iid = ei.get("interface_id") or f"iface.{cid}"
                    iname = ei.get("name") or f"I{cname.replace(' ', '')}"
                    methods = []
                    for m in ei.get("methods") or []:
                        if isinstance(m, str):
                            methods.append(MethodSignature(name=m))
                        elif isinstance(m, dict):
                            methods.append(MethodSignature(
                                name=m.get("name") or "method",
                                inputs=m.get("inputs") or [],
                                outputs=m.get("outputs") or [],
                                errors=m.get("errors") or [],
                            ))
                    contract_id = f"contract.{iid}"
                    interfaces.append(InterfaceDescriptor(
                        interface_id=iid,
                        name=iname,
                        scope=self._scope(kind),
                        purpose=ei.get("description") or f"Public interface of {cname}",
                        provider_id=cid,
                        methods=methods or [MethodSignature(name="execute")],
                        contract_id=contract_id,
                        tags=[kind, mid],
                    ))
                    contracts.append(self._default_contract(contract_id, iname, kind))
            else:
                # Synthesise a default interface
                iid = f"iface.{cid}"
                iname = f"I{''.join(p.title() for p in cname.replace('-', ' ').split())}"
                contract_id = f"contract.{iid}"
                methods = self._default_methods(kind)
                interfaces.append(InterfaceDescriptor(
                    interface_id=iid,
                    name=iname,
                    scope=self._scope(kind),
                    purpose=f"Public interface of {cname}",
                    provider_id=cid,
                    methods=methods,
                    contract_id=contract_id,
                    tags=[kind, mid],
                ))
                contracts.append(self._default_contract(contract_id, iname, kind))

            # Communication rule: consumers must go via interface
            rules.append(CommunicationRule(
                rule_id=f"rule.via.{cid}",
                from_id="*",
                to_id=cid,
                mode=COMM_VIA_INTERFACE,
                interface_id=f"iface.{cid}",
                reason=f"All access to {cname} must go through its interface",
            ))

        # Global dependency isolation rules
        dep_rules.extend([
            DependencyRule(
                rule_id="dep.no_direct_repo",
                description="Handlers must not access repositories directly",
                forbidden_pattern="handler -> repository",
                severity=SEVERITY_HIGH,
            ),
            DependencyRule(
                rule_id="dep.no_circular",
                description="No circular communication between components",
                forbidden_pattern="A -> B -> A",
                severity=SEVERITY_HIGH,
            ),
            DependencyRule(
                rule_id="dep.no_infra_in_domain",
                description="Domain components must not depend on infrastructure",
                forbidden_pattern="domain -> infrastructure",
                severity=SEVERITY_HIGH,
            ),
            DependencyRule(
                rule_id="dep.external_via_adapter",
                description="External systems only reachable via adapters",
                forbidden_pattern="* -> external (direct)",
                severity=SEVERITY_HIGH,
            ),
        ])

        # Forbid direct access from handlers to persistence
        rules.append(CommunicationRule(
            rule_id="rule.forbid.handler_repo",
            from_id="*.handler*",
            to_id="*.repository*",
            mode=COMM_FORBIDDEN,
            reason="Handlers must not talk to repositories directly; use services",
        ))

        _log.info(
            "InterfaceDiscoverer: %d interfaces, %d contracts, %d rules",
            len(interfaces), len(contracts), len(rules),
        )
        return interfaces, contracts, rules, dep_rules

    def _scope(self, kind: str) -> str:
        if kind in ("service", "manager"):
            return SCOPE_SERVICE
        if kind == "repository":
            return SCOPE_REPOSITORY
        if kind in ("adapter", "provider"):
            return SCOPE_EXTERNAL
        return SCOPE_COMPONENT

    def _default_methods(self, kind: str) -> List[MethodSignature]:
        if kind == "repository":
            return [
                MethodSignature("save", ["entity"], ["entity"], ["PersistenceError"]),
                MethodSignature("get", ["id"], ["entity | None"], ["NotFoundError"]),
                MethodSignature("delete", ["id"], ["bool"], ["PersistenceError"]),
                MethodSignature("list", ["filter?"], ["List[entity]"], []),
            ]
        if kind == "controller":
            return [MethodSignature("handle", ["update"], ["result"], ["ValidationError"])]
        if kind == "adapter":
            return [
                MethodSignature("send", ["payload"], ["response"], ["ExternalError"]),
                MethodSignature("receive", [], ["payload"], ["ExternalError"]),
            ]
        if kind == "validator":
            return [MethodSignature("validate", ["data"], ["bool"], ["ValidationError"])]
        if kind == "factory":
            return [MethodSignature("create", ["**kwargs"], ["instance"], ["CreationError"])]
        return [MethodSignature("execute", ["command"], ["result"], ["DomainError"])]

    def _default_contract(self, contract_id: str, name: str, kind: str) -> InterfaceContract:
        return InterfaceContract(
            contract_id=contract_id,
            name=f"Contract for {name}",
            purpose=f"Formal contract governing the {name} interface",
            preconditions=["Caller must be an authorised consumer", "Inputs must be valid"],
            postconditions=["Outputs match declared types", "No side-effects beyond documented ones"],
            invariants=["Interface version remains backward-compatible within major version"],
            error_codes=self._errors_for(kind),
            usage_rules=[
                "Always call through the interface, never the concrete class",
                "Do not cache mutable state returned by the interface unless documented",
            ],
            data_types={"id": "str", "entity": "DomainEntity", "result": "Any"},
        )

    def _errors_for(self, kind: str) -> List[str]:
        base = ["UnexpectedError"]
        if kind == "repository":
            return base + ["PersistenceError", "NotFoundError", "ConflictError"]
        if kind == "controller":
            return base + ["ValidationError", "UnauthorizedError"]
        if kind == "adapter":
            return base + ["ExternalError", "TimeoutError"]
        return base + ["DomainError"]


__all__ = ["InterfaceDiscoverer"]
