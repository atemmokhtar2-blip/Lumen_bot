"""
IntelligentPlanner — Specification 029 v2.0

Builds generation context, units, adaptive queue, rules, style,
runs a dry simulation, detects circulars, scores intelligence,
and defines rollback points.
"""

from __future__ import annotations

import logging
from typing import List, Tuple

from .report_data import (
    GenerationContext, GenerationUnit, QueueEntry, GenerationRule, StyleRules,
    SimulationReport, SimulationFinding, RollbackPoint, IntelligenceScore,
    PlanConflict,
    UNIT_FILE, UNIT_CLASS, UNIT_CONFIG, UNIT_TEST, UNIT_INTERFACE, UNIT_DOC,
    RULE_CLEAN_CODE, RULE_SOLID, RULE_DRY, RULE_KISS, RULE_YAGNI,
    RULE_CLEAN_ARCH, RULE_LAYER_SEP, RULE_DI, RULE_NAMING,
    RULE_ERROR_HANDLING, RULE_LOGGING, RULE_DOCS, RULE_TESTING,
    RULE_SECURITY, RULE_PERFORMANCE,
    SCORE_MAINTAINABILITY, SCORE_SCALABILITY, SCORE_SECURITY,
    SCORE_PERFORMANCE, SCORE_COMPLEXITY, SCORE_RELIABILITY, SCORE_ARCHITECTURE,
    CONFLICT_CIRCULAR, CONFLICT_ORDER, CONFLICT_DUPLICATE, CONFLICT_EMPTY,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
)
from .data_readers import GenericData

_log = logging.getLogger("engine.code_generation_planning.intelligent_planner")


class IntelligentPlanner:
    def plan(
        self,
        strategy_data: GenericData,
        structure_data: GenericData,
        mod_data: GenericData,
        comp_data: GenericData,
        iface_data: GenericData,
        res_data: GenericData,
        session_data: GenericData,
    ) -> Tuple[
        GenerationContext,
        List[GenerationUnit],
        List[QueueEntry],
        List[str],
        List[GenerationRule],
        StyleRules,
        SimulationReport,
        List[RollbackPoint],
        List[IntelligenceScore],
        float,
        List[PlanConflict],
    ]:
        # ---- Context ----
        modules = []
        if mod_data.available:
            for m in mod_data.items:
                if isinstance(m, dict):
                    modules.append(m.get("module_id") or m.get("name") or "")
        components = []
        if comp_data.available:
            for c in comp_data.items:
                if isinstance(c, dict):
                    components.append(c.get("component_id") or c.get("name") or "")
        interfaces = []
        if iface_data.available:
            for i in iface_data.items:
                if isinstance(i, dict):
                    interfaces.append(i.get("interface_id") or i.get("name") or "")
        deps = []
        if res_data.available:
            for d in res_data.items:
                if isinstance(d, dict):
                    deps.append(d.get("name") or d.get("dep_id") or "")

        context = GenerationContext(
            project_goal="Generate a maintainable Telegram bot from blueprints",
            modules=[m for m in modules if m],
            components=[c for c in components if c],
            interfaces=[i for i in interfaces if i],
            dependencies=[d for d in deps if d],
            architecture_style="layered clean architecture",
            notes="Context built from all upstream blueprints",
        )

        # ---- Units from strategy items + canonical scaffold ----
        units: List[GenerationUnit] = []
        order = 0
        items = strategy_data.items if strategy_data.available else []
        if not items and strategy_data.raw:
            items = strategy_data.raw.get("items") or []

        for it in items:
            if not isinstance(it, dict):
                continue
            order += 1
            path = it.get("path") or ""
            name = it.get("name") or it.get("item_id") or f"unit-{order}"
            itype = (it.get("item_type") or "file").lower()
            kind = UNIT_FILE
            if itype in ("config",):
                kind = UNIT_CONFIG
            elif itype in ("test",):
                kind = UNIT_TEST
            elif itype in ("documentation", "doc"):
                kind = UNIT_DOC
            elif itype in ("module", "component"):
                kind = UNIT_FILE
            contents = []
            if kind == UNIT_FILE and path.endswith(".py"):
                contents = ["module docstring", "imports", "public API"]
            units.append(GenerationUnit(
                unit_id=f"unit.{it.get('item_id') or order}",
                name=name,
                kind=kind,
                path=path,
                purpose=it.get("description") or f"Generate {name}",
                responsibility=f"Own the content of {path or name}",
                contents=contents,
                depends_on=list(it.get("depends_on") or []),
                order=order,
                phase=it.get("stage") or "",
                extension_points=["hooks", "plugins"] if "core" in path else [],
            ))

        if not units:
            defaults = [
                ("requirements.txt", UNIT_FILE, "foundation", ["dependency list"]),
                ("telegram_bot/__init__.py", UNIT_FILE, "foundation", ["package marker"]),
                ("telegram_bot/configs/settings.py", UNIT_CONFIG, "configuration",
                 ["Settings class", "load_env()"]),
                ("telegram_bot/core/models.py", UNIT_FILE, "core",
                 ["Domain entities", "Value objects"]),
                ("telegram_bot/handlers/__init__.py", UNIT_FILE, "core",
                 ["Handler registry"]),
                ("telegram_bot/services/__init__.py", UNIT_FILE, "core",
                 ["Service interfaces"]),
                ("telegram_bot/integrations/telegram.py", UNIT_FILE, "integration",
                 ["TelegramAdapter", "send()", "receive()"]),
                ("tests/test_handlers.py", UNIT_TEST, "testing",
                 ["test_handle_message", "test_validation"]),
                ("README.md", UNIT_DOC, "documentation", ["overview", "setup", "usage"]),
            ]
            for path, kind, phase, contents in defaults:
                order += 1
                units.append(GenerationUnit(
                    unit_id=f"unit.default.{order}",
                    name=path.split("/")[-1],
                    kind=kind,
                    path=path,
                    purpose=f"Generate {path}",
                    responsibility=f"Own {path}",
                    contents=contents,
                    order=order,
                    phase=phase,
                ))

        # Enrich context with file lists
        paths = [u.path for u in units if u.path]
        context.prior_files = paths[: max(1, len(paths) // 3)]
        context.upcoming_files = paths[max(1, len(paths) // 3):]

        # ---- Adaptive queue ----
        queue: List[QueueEntry] = []
        generation_order: List[str] = []
        for idx, u in enumerate(sorted(units, key=lambda x: x.order)):
            complexity = "low"
            if u.kind in (UNIT_CLASS, UNIT_INTERFACE) or len(u.contents) > 3:
                complexity = "high"
            elif u.kind in (UNIT_FILE, UNIT_CONFIG):
                complexity = "medium"
            queue.append(QueueEntry(
                entry_id=f"q.{u.unit_id}",
                unit_id=u.unit_id,
                position=idx + 1,
                waits_for=list(u.depends_on),
                estimated_complexity=complexity,
                adaptive=True,
            ))
            generation_order.append(u.unit_id)

        # ---- Generation rules ----
        rules = [
            GenerationRule(RULE_CLEAN_CODE, "Clean Code",
                           "Readable, intentional, small functions", True, "design"),
            GenerationRule(RULE_SOLID, "SOLID",
                           "SRP, OCP, LSP, ISP, DIP", True, "design"),
            GenerationRule(RULE_DRY, "DRY",
                           "No duplicated logic across units", True, "design"),
            GenerationRule(RULE_KISS, "KISS",
                           "Prefer simple solutions", True, "design"),
            GenerationRule(RULE_YAGNI, "YAGNI",
                           "Do not generate unused abstractions", True, "design"),
            GenerationRule(RULE_CLEAN_ARCH, "Clean Architecture",
                           "Domain independent of infrastructure", True, "architecture"),
            GenerationRule(RULE_LAYER_SEP, "Layer Separation",
                           "Handlers → Services → Domain → Infra", True, "architecture"),
            GenerationRule(RULE_DI, "Dependency Injection",
                           "Depend on interfaces, inject implementations", True, "architecture"),
            GenerationRule(RULE_NAMING, "Naming Convention",
                           "snake_case functions, PascalCase classes", True, "style"),
            GenerationRule(RULE_ERROR_HANDLING, "Error Handling",
                           "Typed domain errors; never swallow exceptions", True, "reliability"),
            GenerationRule(RULE_LOGGING, "Logging Rules",
                           "Structured logs; never log secrets", True, "ops"),
            GenerationRule(RULE_DOCS, "Documentation Rules",
                           "Public APIs have docstrings", True, "docs"),
            GenerationRule(RULE_TESTING, "Testing Rules",
                           "Every service has at least one unit test", True, "quality"),
            GenerationRule(RULE_SECURITY, "Security Rules",
                           "Tokens only from env; validate all inputs", True, "security"),
            GenerationRule(RULE_PERFORMANCE, "Performance Rules",
                           "Avoid N+1; prefer async I/O where applicable", True, "performance"),
        ]

        style = StyleRules()

        # ---- Circular detection ----
        conflicts: List[PlanConflict] = []
        unit_ids = {u.unit_id for u in units}
        graph = {u.unit_id: [d for d in u.depends_on if d in unit_ids] for u in units}
        for cycle in self._find_cycles(graph):
            conflicts.append(PlanConflict(
                conflict_id=f"cycle_{'_'.join(cycle[:3])}",
                conflict_type=CONFLICT_CIRCULAR,
                severity=SEVERITY_CRITICAL,
                message=f"Circular dependency among units: {' → '.join(cycle + [cycle[0]])}",
                affected_ids=list(cycle),
                resolution_hint="Break the cycle with an interface or shared types module.",
            ))

        # Duplicate paths
        seen_paths = {}
        for u in units:
            if not u.path:
                continue
            if u.path in seen_paths:
                conflicts.append(PlanConflict(
                    conflict_id=f"dup_{u.unit_id}",
                    conflict_type=CONFLICT_DUPLICATE,
                    severity=SEVERITY_HIGH,
                    message=f"Duplicate path '{u.path}'.",
                    affected_ids=[u.unit_id, seen_paths[u.path]],
                    resolution_hint="Ensure each path is generated once.",
                ))
            else:
                seen_paths[u.path] = u.unit_id

        # Empty units
        for u in units:
            if not u.path and not u.contents:
                conflicts.append(PlanConflict(
                    conflict_id=f"empty_{u.unit_id}",
                    conflict_type=CONFLICT_EMPTY,
                    severity=SEVERITY_MEDIUM,
                    message=f"Unit '{u.name}' has no path and no contents.",
                    affected_ids=[u.unit_id],
                    resolution_hint="Assign a path or planned contents.",
                ))

        # Order violations
        pos = {uid: i for i, uid in enumerate(generation_order)}
        for u in units:
            for dep in u.depends_on:
                if dep in pos and u.unit_id in pos and pos[dep] > pos[u.unit_id]:
                    conflicts.append(PlanConflict(
                        conflict_id=f"order_{u.unit_id}_{dep}",
                        conflict_type=CONFLICT_ORDER,
                        severity=SEVERITY_CRITICAL,
                        message=f"Unit '{u.unit_id}' ordered before dependency '{dep}'.",
                        affected_ids=[u.unit_id, dep],
                        resolution_hint="Reorder queue so dependencies come first.",
                    ))

        # ---- Simulation (dry run over the queue) ----
        sim_findings: List[SimulationFinding] = []
        for q in queue:
            unit = next((u for u in units if u.unit_id == q.unit_id), None)
            if unit is None:
                sim_findings.append(SimulationFinding(
                    finding_id=f"sim.missing.{q.unit_id}",
                    severity=SEVERITY_CRITICAL,
                    message=f"Queue entry references missing unit '{q.unit_id}'.",
                    unit_id=q.unit_id,
                    resolution_hint="Remove orphan queue entry or create the unit.",
                ))
                continue
            for dep in unit.depends_on:
                if dep.startswith("unit.") and dep not in unit_ids:
                    sim_findings.append(SimulationFinding(
                        finding_id=f"sim.dep.{unit.unit_id}.{dep}",
                        severity=SEVERITY_HIGH,
                        message=f"Unit '{unit.unit_id}' waits for unknown '{dep}'.",
                        unit_id=unit.unit_id,
                        resolution_hint="Declare the dependency unit or drop the edge.",
                    ))
        critical_sim = sum(1 for f in sim_findings if f.severity == SEVERITY_CRITICAL)
        simulation = SimulationReport(
            passed=critical_sim == 0,
            findings=sim_findings,
            units_simulated=len(queue),
            errors_found=len(sim_findings),
        )

        # ---- Rollback points (every ~3 units + end of each phase) ----
        rollbacks: List[RollbackPoint] = []
        for idx, u in enumerate(sorted(units, key=lambda x: x.order)):
            if (idx + 1) % 3 == 0 or idx == len(units) - 1:
                rollbacks.append(RollbackPoint(
                    point_id=f"rb.{u.unit_id}",
                    after_unit_id=u.unit_id,
                    description=f"Resume after generating {u.name}",
                    position=idx + 1,
                ))

        # ---- Intelligence scores ----
        n_units = max(1, len(units))
        n_rules = len(rules)
        n_conflicts = len([c for c in conflicts if c.severity == SEVERITY_CRITICAL])
        scores = [
            IntelligenceScore(SCORE_MAINTAINABILITY, min(100, 70 + n_rules), "Rules enforced"),
            IntelligenceScore(SCORE_SCALABILITY, 85 if any(u.extension_points for u in units) else 70,
                              "Extension points present"),
            IntelligenceScore(SCORE_SECURITY, 90, "Security + logging rules active"),
            IntelligenceScore(SCORE_PERFORMANCE, 80, "Async-friendly stack assumed"),
            IntelligenceScore(SCORE_COMPLEXITY, max(40, 100 - n_units * 2), "Unit count penalty"),
            IntelligenceScore(SCORE_RELIABILITY, 95 if simulation.passed else 60,
                              "Simulation result"),
            IntelligenceScore(SCORE_ARCHITECTURE, max(50, 100 - n_conflicts * 15),
                              "Critical conflict penalty"),
        ]
        overall = round(sum(s.score for s in scores) / len(scores), 1)

        _log.info(
            "IntelligentPlanner: units=%d queue=%d conflicts=%d score=%.1f sim_passed=%s",
            len(units), len(queue), len(conflicts), overall, simulation.passed,
        )
        return (
            context, units, queue, generation_order, rules, style,
            simulation, rollbacks, scores, overall, conflicts,
        )

    def _find_cycles(self, graph: dict) -> List[List[str]]:
        cycles: List[List[str]] = []
        visited, stack, path = set(), set(), []

        def dfs(n: str) -> None:
            if n in stack:
                try:
                    cycles.append(path[path.index(n):])
                except ValueError:
                    cycles.append([n])
                return
            if n in visited:
                return
            visited.add(n)
            stack.add(n)
            path.append(n)
            for nb in graph.get(n, []):
                dfs(nb)
            path.pop()
            stack.discard(n)

        for node in list(graph):
            if node not in visited:
                dfs(node)
        return cycles


__all__ = ["IntelligentPlanner"]
