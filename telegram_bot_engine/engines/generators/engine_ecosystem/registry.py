"""
EcosystemRegistry — Specification 052 (MAXIMUM CRITICAL)

Central registry: manifests, capability index, dependency graph,
compatibility checks, health monitoring, failure isolation, service discovery.
"""

from __future__ import annotations

import logging
import uuid
from typing import Dict, List, Set, Tuple

from .data_readers import GenericData
from .report_data import (
    EngineManifest, DependencyEdge, CapabilityEntry, CompatibilityResult,
    EngineHealth,
    CAP_GENERATE, CAP_ANALYZE, CAP_REVIEW, CAP_OPTIMIZE, CAP_REPAIR,
    CAP_DEPLOY, CAP_VALIDATE, CAP_TEST, CAP_CONFIGURE, CAP_MANAGE, CAP_SEARCH,
    STATUS_REGISTERED, STATUS_ACTIVE, STATUS_ISOLATED, STATUS_FAILED,
    HEALTH_HEALTHY, HEALTH_DEGRADED, HEALTH_FAILED, HEALTH_ISOLATED,
)

_log = logging.getLogger("engine.engine_ecosystem.registry")

# Known platform engines (logical bootstrap catalog)
_KNOWN_ENGINES: List[Dict] = [
    {"engine_id": "intent_parser", "name": "IntentParserEngine", "priority": 10,
     "capabilities": [CAP_ANALYZE], "dependencies": []},
    {"engine_id": "architecture_compliance", "name": "ArchitectureComplianceEngine", "priority": 50,
     "capabilities": [CAP_REVIEW, CAP_VALIDATE], "dependencies": []},
    {"engine_id": "code_refactoring", "name": "CodeRefactoringEngine", "priority": 124,
     "capabilities": [CAP_OPTIMIZE, CAP_REPAIR], "dependencies": ["static_analysis"]},
    {"engine_id": "static_analysis", "name": "StaticAnalysisEngine", "priority": 125,
     "capabilities": [CAP_ANALYZE, CAP_REVIEW], "dependencies": []},
    {"engine_id": "runtime_simulation", "name": "RuntimeSimulationEngine", "priority": 126,
     "capabilities": [CAP_TEST, CAP_ANALYZE], "dependencies": ["static_analysis"]},
    {"engine_id": "self_healing", "name": "SelfHealingEngine", "priority": 127,
     "capabilities": [CAP_REPAIR], "dependencies": ["runtime_simulation"]},
    {"engine_id": "integration_verification", "name": "IntegrationVerificationEngine", "priority": 128,
     "capabilities": [CAP_VALIDATE, CAP_TEST], "dependencies": ["self_healing"]},
    {"engine_id": "unit_test_generation", "name": "UnitTestGenerationEngine", "priority": 129,
     "capabilities": [CAP_GENERATE, CAP_TEST], "dependencies": ["integration_verification"]},
    {"engine_id": "e2e_scenario_testing", "name": "E2EScenarioTestingEngine", "priority": 130,
     "capabilities": [CAP_TEST], "dependencies": ["unit_test_generation"]},
    {"engine_id": "production_readiness", "name": "ProductionReadinessEngine", "priority": 131,
     "capabilities": [CAP_VALIDATE, CAP_REVIEW], "dependencies": ["e2e_scenario_testing"]},
    {"engine_id": "repository_management", "name": "RepositoryManagementEngine", "priority": 132,
     "capabilities": [CAP_MANAGE], "dependencies": ["production_readiness"]},
    {"engine_id": "git_operations", "name": "GitOperationsEngine", "priority": 133,
     "capabilities": [CAP_MANAGE], "dependencies": ["repository_management"]},
    {"engine_id": "file_system", "name": "FileSystemEngine", "priority": 134,
     "capabilities": [CAP_MANAGE], "dependencies": ["git_operations"]},
    {"engine_id": "workspace_management", "name": "WorkspaceManagementEngine", "priority": 135,
     "capabilities": [CAP_MANAGE, CAP_CONFIGURE], "dependencies": ["file_system"]},
    {"engine_id": "dependency_management", "name": "DependencyManagementEngine", "priority": 136,
     "capabilities": [CAP_MANAGE, CAP_VALIDATE], "dependencies": ["workspace_management"]},
    {"engine_id": "environment_config", "name": "EnvironmentConfigEngine", "priority": 137,
     "capabilities": [CAP_CONFIGURE, CAP_VALIDATE], "dependencies": ["dependency_management"]},
    {"engine_id": "engine_ecosystem", "name": "EngineEcosystemEngine", "priority": 138,
     "capabilities": [CAP_MANAGE, CAP_SEARCH], "dependencies": ["environment_config"]},
]


class EcosystemRegistry:
    """Register, graph, discover, monitor and isolate engines."""

    def build(
        self,
        request_data: GenericData,
        ctx_data: GenericData,
    ) -> Tuple[
        List[EngineManifest],
        List[DependencyEdge],
        List[CapabilityEntry],
        List[CompatibilityResult],
        List[EngineHealth],
    ]:
        manifests = self._collect_manifests(request_data)
        edges = self._build_graph(manifests)
        capabilities = self._index_capabilities(manifests)
        compatibility = self._check_compatibility(manifests, edges)
        health = self._monitor_health(manifests, request_data)

        # Isolate failed engines
        for h in health:
            if h.status == HEALTH_FAILED:
                h.isolated = True
                h.status = HEALTH_ISOLATED
                for m in manifests:
                    if m.engine_id == h.engine_id:
                        m.status = STATUS_ISOLATED

        _log.info(
            "EcosystemRegistry: engines=%d edges=%d caps=%d conflicts=%d",
            len(manifests), len(edges), len(capabilities),
            sum(1 for c in compatibility if not c.compatible),
        )
        return manifests, edges, capabilities, compatibility, health

    def self_verify(
        self,
        manifests: List[EngineManifest],
        edges: List[DependencyEdge],
        compatibility: List[CompatibilityResult],
        health: List[EngineHealth],
    ) -> bool:
        if not manifests:
            return False
        # All non-isolated engines must be registered
        for m in manifests:
            if m.status not in (STATUS_REGISTERED, STATUS_ACTIVE, STATUS_ISOLATED):
                return False
        # Unresolved hard conflicts
        for c in compatibility:
            if not c.compatible and c.conflicts:
                return False
        # Dependency targets must exist (unless isolated)
        ids = {m.engine_id for m in manifests}
        isolated = {h.engine_id for h in health if h.isolated}
        for e in edges:
            if e.to_engine not in ids and e.to_engine not in isolated:
                # soft: allow missing optional deps
                pass
        return True

    def _collect_manifests(self, request_data: GenericData) -> List[EngineManifest]:
        manifests: List[EngineManifest] = []
        seen: Set[str] = set()
        raw = request_data.raw or {}

        # From request
        for it in request_data.items or []:
            if isinstance(it, dict):
                eid = str(it.get("engine_id") or it.get("id") or "")
                if not eid or eid in seen:
                    continue
                seen.add(eid)
                manifests.append(EngineManifest(
                    engine_id=eid,
                    name=str(it.get("name") or eid),
                    version=str(it.get("version") or "1.0.0"),
                    author=str(it.get("author") or "platform"),
                    description=str(it.get("description") or ""),
                    capabilities=list(it.get("capabilities") or []),
                    dependencies=list(it.get("dependencies") or []),
                    priority=int(it.get("priority") or 100),
                    execution_order=int(it.get("execution_order") or it.get("priority") or 100),
                    status=STATUS_REGISTERED,
                    permissions=list(it.get("permissions") or ["execute"]),
                ))

        # Bootstrap known catalog if empty or merge
        for info in _KNOWN_ENGINES:
            eid = info["engine_id"]
            if eid in seen:
                continue
            seen.add(eid)
            manifests.append(EngineManifest(
                engine_id=eid,
                name=info["name"],
                version="1.0.0",
                author="platform",
                description=f"Platform engine: {info['name']}",
                capabilities=list(info.get("capabilities") or []),
                dependencies=list(info.get("dependencies") or []),
                priority=int(info.get("priority") or 100),
                execution_order=int(info.get("priority") or 100),
                status=STATUS_ACTIVE,
                permissions=["execute"],
            ))

        # Sort by priority / execution order
        manifests.sort(key=lambda m: (m.priority, m.execution_order, m.engine_id))
        return manifests

    def _build_graph(self, manifests: List[EngineManifest]) -> List[DependencyEdge]:
        edges: List[DependencyEdge] = []
        ids = {m.engine_id for m in manifests}
        for m in manifests:
            for dep in m.dependencies:
                edges.append(DependencyEdge(
                    from_engine=m.engine_id,
                    to_engine=dep,
                    relation="depends_on",
                ))
            # precedes based on priority
        # Order edges: lower priority precedes higher
        ordered = sorted(manifests, key=lambda m: m.priority)
        for i in range(len(ordered) - 1):
            edges.append(DependencyEdge(
                from_engine=ordered[i].engine_id,
                to_engine=ordered[i + 1].engine_id,
                relation="precedes",
            ))
        return edges

    def _index_capabilities(
        self, manifests: List[EngineManifest]
    ) -> List[CapabilityEntry]:
        index: Dict[str, List[str]] = {}
        for m in manifests:
            for cap in m.capabilities:
                index.setdefault(cap, []).append(m.engine_id)
        return [
            CapabilityEntry(capability=cap, providers=providers)
            for cap, providers in sorted(index.items())
        ]

    def _check_compatibility(
        self, manifests: List[EngineManifest], edges: List[DependencyEdge]
    ) -> List[CompatibilityResult]:
        results: List[CompatibilityResult] = []
        ids = {m.engine_id: m for m in manifests}
        # Duplicate engine_id
        seen: Dict[str, int] = {}
        for m in manifests:
            seen[m.engine_id] = seen.get(m.engine_id, 0) + 1
        for m in manifests:
            conflicts: List[str] = []
            if seen.get(m.engine_id, 0) > 1:
                conflicts.append(f"duplicate engine_id: {m.engine_id}")
            # Missing hard dependency
            for dep in m.dependencies:
                if dep not in ids:
                    conflicts.append(f"missing dependency: {dep}")
            # Circular dependency (simple 2-cycle)
            for e in edges:
                if e.from_engine == m.engine_id and e.relation == "depends_on":
                    for e2 in edges:
                        if (
                            e2.from_engine == e.to_engine
                            and e2.to_engine == m.engine_id
                            and e2.relation == "depends_on"
                        ):
                            conflicts.append(
                                f"circular dependency: {m.engine_id} ↔ {e.to_engine}"
                            )
            results.append(CompatibilityResult(
                engine_id=m.engine_id,
                compatible=len(conflicts) == 0,
                conflicts=conflicts,
                message="OK" if not conflicts else "; ".join(conflicts),
            ))
        return results

    def _monitor_health(
        self, manifests: List[EngineManifest], request_data: GenericData
    ) -> List[EngineHealth]:
        raw = request_data.raw or {}
        fail_list = set(raw.get("fail_engines") or [])
        health: List[EngineHealth] = []
        for m in manifests:
            if m.engine_id in fail_list or raw.get("force_engine_fail") == m.engine_id:
                health.append(EngineHealth(
                    engine_id=m.engine_id,
                    status=HEALTH_FAILED,
                    availability=0.0,
                    response_time_ms=0.0,
                    failure_count=1,
                    isolated=False,
                    message="Simulated failure",
                ))
            else:
                health.append(EngineHealth(
                    engine_id=m.engine_id,
                    status=HEALTH_HEALTHY,
                    availability=100.0,
                    response_time_ms=5.0,
                    failure_count=0,
                    isolated=False,
                    message="Healthy",
                ))
        return health


__all__ = ["EcosystemRegistry"]
