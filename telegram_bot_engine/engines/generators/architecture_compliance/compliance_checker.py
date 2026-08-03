"""
ComplianceChecker — Specification 037 (ULTRA CRITICAL)

Compares implementation artefacts against architecture blueprints.
Detects layer bypasses, SOLID violations, dependency issues and drift.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Dict, List, Set, Tuple

from .data_readers import GenericData
from .report_data import (
    ComplianceUnit, ArchitectureViolation, RefactoringSuggestion,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW,
    STATUS_OPEN,
    VIO_LAYER_BYPASS, VIO_MISSING_MODULE, VIO_MISSING_COMPONENT,
    VIO_MISSING_INTERFACE, VIO_CONTRACT_BREAK, VIO_UNEXPECTED_DEPENDENCY,
    VIO_CIRCULAR_DEPENDENCY, VIO_STRONG_COUPLING, VIO_SRP, VIO_DIP,
    VIO_RESPONSIBILITY, VIO_INTERFACE_MISUSE, VIO_ARCHITECTURE_DRIFT,
)

_log = logging.getLogger("engine.architecture_compliance.checker")

# Heuristic layer names (lower layers should not import higher ones)
_LAYER_ORDER = ("domain", "core", "application", "service", "infrastructure", "presentation", "api", "bot", "handlers", "ui")


class ComplianceChecker:
    """Architecture compliance checker + refactoring suggestions."""

    def check(
        self,
        perf_data: GenericData,
        sec_data: GenericData,
        arch_data: GenericData,
        comp_data: GenericData,
        iface_data: GenericData,
        mod_data: GenericData,
        bl_data: GenericData,
    ) -> Tuple[
        List[ComplianceUnit],
        List[ArchitectureViolation],
        List[RefactoringSuggestion],
        float,
        float,
    ]:
        units: List[ComplianceUnit] = []
        violations: List[ArchitectureViolation] = []
        refactorings: List[RefactoringSuggestion] = []

        # Planned artefacts from blueprints
        planned_modules = self._names(mod_data, ("name", "module_name", "id"))
        planned_components = self._names(comp_data, ("name", "component_name", "id"))
        planned_interfaces = self._names(iface_data, ("name", "interface_name", "id"))

        # Implemented units from code reports
        impl_units = self._collect_impl_units(perf_data, sec_data, bl_data)

        # --- Module / component presence ---
        impl_names = {u["name"].lower() for u in impl_units if u.get("name")}
        for m in planned_modules:
            if m.lower() not in impl_names and not self._fuzzy_present(m, impl_names):
                violations.append(ArchitectureViolation(
                    violation_id=str(uuid.uuid4())[:8],
                    violation_type=VIO_MISSING_MODULE,
                    severity=SEVERITY_HIGH,
                    message=f"Planned module '{m}' not found in implementation.",
                    location=m,
                    expected=m,
                    actual="missing",
                    resolution_hint="Ensure module is generated or update architecture blueprint.",
                ))

        for c in planned_components:
            if c.lower() not in impl_names and not self._fuzzy_present(c, impl_names):
                violations.append(ArchitectureViolation(
                    violation_id=str(uuid.uuid4())[:8],
                    violation_type=VIO_MISSING_COMPONENT,
                    severity=SEVERITY_HIGH,
                    message=f"Planned component '{c}' not found in implementation.",
                    location=c,
                    expected=c,
                    actual="missing",
                    resolution_hint="Generate the component or revise the component blueprint.",
                ))

        for i in planned_interfaces:
            # interfaces may appear as Protocol/ABC names in code
            if i.lower() not in impl_names and not self._fuzzy_present(i, impl_names):
                violations.append(ArchitectureViolation(
                    violation_id=str(uuid.uuid4())[:8],
                    violation_type=VIO_MISSING_INTERFACE,
                    severity=SEVERITY_MEDIUM,
                    message=f"Planned interface '{i}' not clearly present.",
                    location=i,
                    expected=i,
                    actual="missing_or_unnamed",
                    resolution_hint="Expose the interface as Protocol/ABC as designed.",
                ))

        # --- Per-unit SOLID / responsibility / dependency heuristics ---
        for u in impl_units:
            uid = u.get("unit_id") or u.get("name") or str(uuid.uuid4())[:8]
            name = u.get("name") or uid
            code = u.get("source_code") or ""
            unit_violations: List[ArchitectureViolation] = []
            solid = 100.0

            # SRP: too many public methods / mixed concerns
            method_count = len(re.findall(r"""^\s+def\s+\w+""", code, re.MULTILINE))
            if method_count > 12:
                v = ArchitectureViolation(
                    violation_id=str(uuid.uuid4())[:8],
                    violation_type=VIO_SRP,
                    severity=SEVERITY_HIGH,
                    message=f"Class/module '{name}' has {method_count} methods — possible SRP violation.",
                    location=name,
                    unit_id=str(uid),
                    expected="<= 12 cohesive methods",
                    actual=f"{method_count} methods",
                    resolution_hint="Split into focused collaborators.",
                )
                unit_violations.append(v)
                solid -= 15

            # Responsibility overload: handles + db + network in one unit
            concerns = 0
            if re.search(r"""(?:send_message|reply_text|callback|handler)""", code, re.I):
                concerns += 1
            if re.search(r"""(?:execute\(|session\.|cursor\.|SELECT |INSERT )""", code, re.I):
                concerns += 1
            if re.search(r"""(?:requests\.|httpx\.|aiohttp|urllib)""", code, re.I):
                concerns += 1
            if re.search(r"""(?:open\(|Path\(|json\.load|yaml\.)""", code, re.I):
                concerns += 1
            if concerns >= 3:
                v = ArchitectureViolation(
                    violation_id=str(uuid.uuid4())[:8],
                    violation_type=VIO_RESPONSIBILITY,
                    severity=SEVERITY_HIGH,
                    message=f"'{name}' mixes {concerns} infrastructure concerns.",
                    location=name,
                    unit_id=str(uid),
                    expected="single responsibility / layered access",
                    actual=f"{concerns} concerns in one unit",
                    resolution_hint="Extract handlers, repositories and clients into separate layers.",
                )
                unit_violations.append(v)
                solid -= 15

            # DIP: concrete imports of infrastructure inside domain-like names
            if re.search(r"""(?:domain|core|entity|model)""", name, re.I):
                if re.search(r"""(?:import requests|from telegram|import sqlite3|import psycopg)""", code, re.I):
                    v = ArchitectureViolation(
                        violation_id=str(uuid.uuid4())[:8],
                        violation_type=VIO_DIP,
                        severity=SEVERITY_CRITICAL,
                        message=f"Domain-like unit '{name}' depends on concrete infrastructure.",
                        location=name,
                        unit_id=str(uid),
                        expected="depend on abstractions",
                        actual="concrete infra import",
                        resolution_hint="Inject interfaces; move adapters to infrastructure layer.",
                    )
                    unit_violations.append(v)
                    solid -= 25

            # Layer bypass: presentation importing db directly
            if re.search(r"""(?:handler|bot|api|presentation|ui)""", name, re.I):
                if re.search(r"""(?:cursor\.execute|session\.query|sqlite3|psycopg)""", code, re.I):
                    v = ArchitectureViolation(
                        violation_id=str(uuid.uuid4())[:8],
                        violation_type=VIO_LAYER_BYPASS,
                        severity=SEVERITY_CRITICAL,
                        message=f"Presentation/handler '{name}' accesses database directly.",
                        location=name,
                        unit_id=str(uid),
                        expected="go through application/service layer",
                        actual="direct DB access",
                        resolution_hint="Route data access through a repository/service.",
                    )
                    unit_violations.append(v)
                    solid -= 25

            # Strong coupling: many cross-imports
            imports = re.findall(r"""^(?:from|import)\s+([\w.]+)""", code, re.MULTILINE)
            if len(imports) > 15:
                v = ArchitectureViolation(
                    violation_id=str(uuid.uuid4())[:8],
                    violation_type=VIO_STRONG_COUPLING,
                    severity=SEVERITY_MEDIUM,
                    message=f"'{name}' has {len(imports)} imports — possible strong coupling.",
                    location=name,
                    unit_id=str(uid),
                    expected="focused dependency set",
                    actual=f"{len(imports)} imports",
                    resolution_hint="Reduce surface area; introduce facades where needed.",
                )
                unit_violations.append(v)
                solid -= 10

            # Interface misuse: empty Protocol/ABC body with concrete logic mixed
            if re.search(r"""class\s+\w+\s*\(\s*(?:Protocol|ABC)""", code):
                if re.search(r"""(?:requests\.|sqlite3|send_message)""", code, re.I):
                    v = ArchitectureViolation(
                        violation_id=str(uuid.uuid4())[:8],
                        violation_type=VIO_INTERFACE_MISUSE,
                        severity=SEVERITY_HIGH,
                        message=f"Interface/ABC '{name}' contains concrete infrastructure logic.",
                        location=name,
                        unit_id=str(uid),
                        expected="abstract contract only",
                        actual="concrete side effects in interface",
                        resolution_hint="Keep interfaces pure; move logic to implementations.",
                    )
                    unit_violations.append(v)
                    solid -= 15

            solid = max(0.0, solid)
            violations.extend(unit_violations)
            units.append(ComplianceUnit(
                unit_id=str(uid),
                name=name,
                unit_kind=u.get("kind") or "class",
                compliant=len(unit_violations) == 0,
                violation_count=len(unit_violations),
                solid_score=solid,
                notes=f"violations={len(unit_violations)}",
            ))

            if unit_violations:
                refactorings.append(self._suggest(name, unit_violations))

        # Circular dependency heuristic from import names among units
        graph = self._import_graph(impl_units)
        cycles = self._find_cycles(graph)
        for cycle in cycles[:5]:
            violations.append(ArchitectureViolation(
                violation_id=str(uuid.uuid4())[:8],
                violation_type=VIO_CIRCULAR_DEPENDENCY,
                severity=SEVERITY_CRITICAL,
                message=f"Circular dependency: {' -> '.join(cycle)}",
                location=" -> ".join(cycle),
                expected="acyclic dependency graph",
                actual="cycle detected",
                resolution_hint="Break the cycle with an interface or intermediate module.",
            ))

        # Drift: architecture decisions present but no matching impl signal
        if arch_data.available and arch_data.items and not impl_units:
            violations.append(ArchitectureViolation(
                violation_id=str(uuid.uuid4())[:8],
                violation_type=VIO_ARCHITECTURE_DRIFT,
                severity=SEVERITY_HIGH,
                message="Architecture decisions exist but no implementation units were found.",
                location="project",
                expected="implementation aligned with decisions",
                actual="empty implementation set",
                resolution_hint="Ensure upstream generation engines produced code artefacts.",
            ))

        compliance, solid_avg = self._scores(units, violations)
        _log.info(
            "ComplianceChecker: units=%d violations=%d compliance=%.1f solid=%.1f",
            len(units), len(violations), compliance, solid_avg,
        )
        return units, violations, refactorings, compliance, solid_avg

    def self_review(
        self,
        units: List[ComplianceUnit],
        violations: List[ArchitectureViolation],
    ) -> Tuple[bool, List[ArchitectureViolation]]:
        open_crit = [
            v for v in violations
            if v.severity == SEVERITY_CRITICAL and v.status == STATUS_OPEN
        ]
        # Re-flag non-compliant units still carrying open criticals
        residual = list(open_crit)
        passed = len(residual) == 0
        return passed, residual

    def _collect_impl_units(
        self,
        perf_data: GenericData,
        sec_data: GenericData,
        bl_data: GenericData,
    ) -> List[Dict]:
        units: List[Dict] = []
        seen: Set[str] = set()

        def add(items: List[Dict], code_keys: Tuple[str, ...], name_keys: Tuple[str, ...]) -> None:
            for it in items or []:
                name = ""
                for k in name_keys:
                    if it.get(k):
                        name = str(it[k])
                        break
                if not name:
                    name = str(it.get("unit_id") or it.get("method_id") or "")
                key = name.lower()
                if not key or key in seen:
                    continue
                seen.add(key)
                code = ""
                for k in code_keys:
                    if it.get(k):
                        code = str(it[k])
                        break
                units.append({
                    "unit_id": it.get("unit_id") or it.get("method_id") or name,
                    "name": name,
                    "source_code": code,
                    "kind": it.get("kind") or "class",
                })

        if perf_data.available:
            add(perf_data.items, ("optimized_code", "original_code", "source_code"),
                ("class_name", "method_name", "name", "unit_id"))
        if sec_data.available:
            add(sec_data.items, ("secured_code", "original_code", "source_code"),
                ("class_name", "method_name", "name", "unit_id"))
        if bl_data.available:
            add(bl_data.items, ("source_code",),
                ("class_name", "method_name", "name", "method_id"))
        return units

    def _names(self, data: GenericData, keys: Tuple[str, ...]) -> List[str]:
        names: List[str] = []
        if not data.available:
            return names
        for it in data.items or []:
            for k in keys:
                if it.get(k):
                    names.append(str(it[k]))
                    break
        return names

    def _fuzzy_present(self, planned: str, impl: Set[str]) -> bool:
        p = planned.lower().replace("_", "").replace("-", "")
        for i in impl:
            ii = i.replace("_", "").replace("-", "")
            if p in ii or ii in p:
                return True
        return False

    def _import_graph(self, units: List[Dict]) -> Dict[str, Set[str]]:
        names = {u["name"] for u in units if u.get("name")}
        graph: Dict[str, Set[str]] = {n: set() for n in names}
        for u in units:
            src = u.get("name") or ""
            code = u.get("source_code") or ""
            for m in re.findall(r"""(?:from|import)\s+([\w.]+)""", code):
                tail = m.split(".")[-1]
                for n in names:
                    if n != src and (n == tail or n.lower() == tail.lower()):
                        graph.setdefault(src, set()).add(n)
        return graph

    def _find_cycles(self, graph: Dict[str, Set[str]]) -> List[List[str]]:
        cycles: List[List[str]] = []
        visited: Set[str] = set()
        stack: List[str] = []

        def dfs(node: str) -> None:
            if node in stack:
                i = stack.index(node)
                cycles.append(stack[i:] + [node])
                return
            if node in visited:
                return
            visited.add(node)
            stack.append(node)
            for nxt in graph.get(node, ()):
                dfs(nxt)
            stack.pop()

        for n in list(graph.keys()):
            dfs(n)
        return cycles

    def _suggest(
        self,
        target: str,
        unit_violations: List[ArchitectureViolation],
    ) -> RefactoringSuggestion:
        steps: List[str] = []
        types = {v.violation_type for v in unit_violations}
        if VIO_SRP in types or VIO_RESPONSIBILITY in types:
            steps.append("Extract cohesive collaborators (one concern per class).")
        if VIO_DIP in types or VIO_LAYER_BYPASS in types:
            steps.append("Introduce interfaces and move infrastructure to adapters.")
        if VIO_STRONG_COUPLING in types:
            steps.append("Reduce imports; add a facade for cross-cutting needs.")
        if VIO_INTERFACE_MISUSE in types:
            steps.append("Keep Protocol/ABC free of concrete side effects.")
        if not steps:
            steps.append("Align implementation with the architecture blueprint.")
        priority = SEVERITY_CRITICAL if any(
            v.severity == SEVERITY_CRITICAL for v in unit_violations
        ) else SEVERITY_HIGH
        return RefactoringSuggestion(
            suggestion_id=str(uuid.uuid4())[:8],
            target=target,
            violation_ids=[v.violation_id for v in unit_violations],
            description=f"Refactor '{target}' to restore architecture compliance.",
            steps=steps,
            priority=priority,
        )

    def _scores(
        self,
        units: List[ComplianceUnit],
        violations: List[ArchitectureViolation],
    ) -> Tuple[float, float]:
        if not units and not violations:
            return 100.0, 100.0
        open_v = [v for v in violations if v.status == STATUS_OPEN]
        penalty = 0.0
        for v in open_v:
            if v.severity == SEVERITY_CRITICAL:
                penalty += 20
            elif v.severity == SEVERITY_HIGH:
                penalty += 10
            elif v.severity == SEVERITY_MEDIUM:
                penalty += 5
            else:
                penalty += 2
        compliance = max(0.0, 100.0 - penalty)
        solid = (
            sum(u.solid_score for u in units) / len(units)
            if units else 100.0
        )
        return compliance, solid


__all__ = ["ComplianceChecker"]
