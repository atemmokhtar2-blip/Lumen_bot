"""
Interface & Contract Blueprint data model (Specification 023).

Designs all interfaces and contracts that govern communication
between modules and components before any code is written.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


SOURCE_EXECUTION_PLAN = "execution_plan"
SOURCE_PROJECT_STRUCTURE = "project_structure_blueprint"
SOURCE_MODULE_ARCHITECTURE = "module_architecture_blueprint"
SOURCE_COMPONENT_ARCHITECTURE = "component_architecture_blueprint"
SOURCE_ARCHITECTURE_DECISION = "architecture_decision_report"

ALL_SOURCES = (
    SOURCE_EXECUTION_PLAN,
    SOURCE_PROJECT_STRUCTURE,
    SOURCE_MODULE_ARCHITECTURE,
    SOURCE_COMPONENT_ARCHITECTURE,
    SOURCE_ARCHITECTURE_DECISION,
)

SCOPE_MODULE = "module"
SCOPE_COMPONENT = "component"
SCOPE_SERVICE = "service"
SCOPE_REPOSITORY = "repository"
SCOPE_EXTERNAL = "external"
SCOPE_PLUGIN = "plugin"
SCOPE_OTHER = "other"

ALL_SCOPES = (
    SCOPE_MODULE, SCOPE_COMPONENT, SCOPE_SERVICE,
    SCOPE_REPOSITORY, SCOPE_EXTERNAL, SCOPE_PLUGIN, SCOPE_OTHER,
)

COMM_ALLOWED = "allowed"
COMM_FORBIDDEN = "forbidden"
COMM_VIA_INTERFACE = "via_interface"
COMM_VIA_EVENT = "via_event"

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

CONFLICT_DUPLICATE_INTERFACE = "duplicate_interface"
CONFLICT_DUPLICATE_CONTRACT = "duplicate_contract"
CONFLICT_MISSING_CONTRACT = "missing_contract"
CONFLICT_STRONG_COUPLING = "strong_coupling"
CONFLICT_DIRECT_ACCESS = "direct_access"
CONFLICT_CIRCULAR_COMM = "circular_communication"
CONFLICT_INCOMPATIBLE = "incompatible_contract"

ALL_CONFLICT_TYPES = (
    CONFLICT_DUPLICATE_INTERFACE,
    CONFLICT_DUPLICATE_CONTRACT,
    CONFLICT_MISSING_CONTRACT,
    CONFLICT_STRONG_COUPLING,
    CONFLICT_DIRECT_ACCESS,
    CONFLICT_CIRCULAR_COMM,
    CONFLICT_INCOMPATIBLE,
)

RULE_NO_CRITICAL_CONFLICTS = "no_critical_conflicts"
RULE_NO_DUPLICATES = "no_duplicates"
RULE_ALL_CONTRACTS_DEFINED = "all_contracts_defined"
RULE_NO_STRONG_COUPLING = "no_strong_coupling"
RULE_ARCHITECTURE_COMPLETE = "architecture_complete"
RULE_SUFFICIENT_CONFIDENCE = "sufficient_confidence"

ALL_QUALITY_RULES = (
    RULE_NO_CRITICAL_CONFLICTS,
    RULE_NO_DUPLICATES,
    RULE_ALL_CONTRACTS_DEFINED,
    RULE_NO_STRONG_COUPLING,
    RULE_ARCHITECTURE_COMPLETE,
    RULE_SUFFICIENT_CONFIDENCE,
)

CACHE_HIT = "hit"
CACHE_MISS = "miss"
CACHE_DISABLED = "disabled"

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"
CONFIDENCE_HIGH_THRESHOLD = 0.85
CONFIDENCE_MEDIUM_THRESHOLD = 0.60

VERDICT_READY = "ready"
VERDICT_READY_WITH_WARNINGS = "ready_with_warnings"
VERDICT_NOT_READY = "not_ready"

ALL_VERDICTS = (VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY)


@dataclass
class MethodSignature:
    name: str
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "errors": list(self.errors),
            "description": self.description,
        }


@dataclass
class InterfaceContract:
    """A formal contract attached to an interface."""

    contract_id: str
    name: str
    purpose: str = ""
    preconditions: List[str] = field(default_factory=list)
    postconditions: List[str] = field(default_factory=list)
    invariants: List[str] = field(default_factory=list)
    error_codes: List[str] = field(default_factory=list)
    usage_rules: List[str] = field(default_factory=list)
    data_types: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "name": self.name,
            "purpose": self.purpose,
            "preconditions": list(self.preconditions),
            "postconditions": list(self.postconditions),
            "invariants": list(self.invariants),
            "error_codes": list(self.error_codes),
            "usage_rules": list(self.usage_rules),
            "data_types": dict(self.data_types),
        }


@dataclass
class InterfaceDescriptor:
    """A single interface that governs communication."""

    interface_id: str
    name: str
    scope: str = SCOPE_COMPONENT
    purpose: str = ""
    provider_id: str = ""          # component or module that implements it
    consumer_ids: List[str] = field(default_factory=list)
    methods: List[MethodSignature] = field(default_factory=list)
    contract_id: str = ""
    version: str = "1.0"
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "interface_id": self.interface_id,
            "name": self.name,
            "scope": self.scope,
            "purpose": self.purpose,
            "provider_id": self.provider_id,
            "consumer_ids": list(self.consumer_ids),
            "methods": [m.to_dict() for m in self.methods],
            "contract_id": self.contract_id,
            "version": self.version,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
        }


@dataclass
class CommunicationRule:
    """Who may talk to whom and how."""

    rule_id: str
    from_id: str
    to_id: str
    mode: str = COMM_VIA_INTERFACE          # allowed / forbidden / via_interface / via_event
    interface_id: str = ""
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "from_id": self.from_id,
            "to_id": self.to_id,
            "mode": self.mode,
            "interface_id": self.interface_id,
            "reason": self.reason,
        }


@dataclass
class DependencyRule:
    """Isolation rule that prevents strong/hidden coupling."""

    rule_id: str
    description: str
    forbidden_pattern: str = ""
    severity: str = SEVERITY_HIGH

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "description": self.description,
            "forbidden_pattern": self.forbidden_pattern,
            "severity": self.severity,
        }


@dataclass
class InterfaceConflict:
    conflict_id: str
    conflict_type: str
    severity: str = SEVERITY_HIGH
    message: str = ""
    affected_ids: List[str] = field(default_factory=list)
    resolution_hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "conflict_type": self.conflict_type,
            "severity": self.severity,
            "message": self.message,
            "affected_ids": list(self.affected_ids),
            "resolution_hint": self.resolution_hint,
        }


@dataclass
class InterfaceFinding:
    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "quality"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "affected": self.affected,
            "resolution_hint": self.resolution_hint,
            "category": self.category,
        }


@dataclass
class CacheInfo:
    status: str = CACHE_MISS
    key: str = ""
    created_at: str = ""
    hits: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "key": self.key,
            "created_at": self.created_at,
            "hits": self.hits,
        }


@dataclass
class InterfaceProvenance:
    engine_name: str = "interface_contract_planning"
    engine_version: str = "1.0.0"
    sources_used: List[str] = field(default_factory=list)
    sources_missing: List[str] = field(default_factory=list)
    generated_at: str = ""
    confidence: float = 0.0
    confidence_level: str = CONFIDENCE_LOW

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_name": self.engine_name,
            "engine_version": self.engine_version,
            "sources_used": list(self.sources_used),
            "sources_missing": list(self.sources_missing),
            "generated_at": self.generated_at,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level,
        }


@dataclass
class InterfaceContractBlueprint:
    """Complete Interface & Contract Blueprint."""

    blueprint_id: str = ""
    interfaces: List[InterfaceDescriptor] = field(default_factory=list)
    contracts: List[InterfaceContract] = field(default_factory=list)
    communication_rules: List[CommunicationRule] = field(default_factory=list)
    dependency_rules: List[DependencyRule] = field(default_factory=list)
    conflicts: List[InterfaceConflict] = field(default_factory=list)
    findings: List[InterfaceFinding] = field(default_factory=list)
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: InterfaceProvenance = field(default_factory=InterfaceProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "blueprint_id": self.blueprint_id,
            "interfaces": [i.to_dict() for i in self.interfaces],
            "contracts": [c.to_dict() for c in self.contracts],
            "communication_rules": [r.to_dict() for r in self.communication_rules],
            "dependency_rules": [r.to_dict() for r in self.dependency_rules],
            "conflicts": [c.to_dict() for c in self.conflicts],
            "findings": [f.to_dict() for f in self.findings],
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_EXECUTION_PLAN",
    "SOURCE_PROJECT_STRUCTURE",
    "SOURCE_MODULE_ARCHITECTURE",
    "SOURCE_COMPONENT_ARCHITECTURE",
    "SOURCE_ARCHITECTURE_DECISION",
    "ALL_SOURCES",
    "SCOPE_MODULE",
    "SCOPE_COMPONENT",
    "SCOPE_SERVICE",
    "SCOPE_REPOSITORY",
    "SCOPE_EXTERNAL",
    "SCOPE_PLUGIN",
    "SCOPE_OTHER",
    "ALL_SCOPES",
    "COMM_ALLOWED",
    "COMM_FORBIDDEN",
    "COMM_VIA_INTERFACE",
    "COMM_VIA_EVENT",
    "SEVERITY_CRITICAL",
    "SEVERITY_HIGH",
    "SEVERITY_MEDIUM",
    "SEVERITY_LOW",
    "CONFLICT_DUPLICATE_INTERFACE",
    "CONFLICT_DUPLICATE_CONTRACT",
    "CONFLICT_MISSING_CONTRACT",
    "CONFLICT_STRONG_COUPLING",
    "CONFLICT_DIRECT_ACCESS",
    "CONFLICT_CIRCULAR_COMM",
    "CONFLICT_INCOMPATIBLE",
    "ALL_CONFLICT_TYPES",
    "RULE_NO_CRITICAL_CONFLICTS",
    "RULE_NO_DUPLICATES",
    "RULE_ALL_CONTRACTS_DEFINED",
    "RULE_NO_STRONG_COUPLING",
    "RULE_ARCHITECTURE_COMPLETE",
    "RULE_SUFFICIENT_CONFIDENCE",
    "ALL_QUALITY_RULES",
    "CACHE_HIT",
    "CACHE_MISS",
    "CACHE_DISABLED",
    "CONFIDENCE_HIGH",
    "CONFIDENCE_MEDIUM",
    "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD",
    "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY",
    "VERDICT_READY_WITH_WARNINGS",
    "VERDICT_NOT_READY",
    "ALL_VERDICTS",
    "MethodSignature",
    "InterfaceContract",
    "InterfaceDescriptor",
    "CommunicationRule",
    "DependencyRule",
    "InterfaceConflict",
    "InterfaceFinding",
    "CacheInfo",
    "InterfaceProvenance",
    "InterfaceContractBlueprint",
]
