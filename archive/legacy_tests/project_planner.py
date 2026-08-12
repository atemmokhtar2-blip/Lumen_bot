#!/usr/bin/env python3
"""
Comprehensive test suite for the Project Planning Engine (Specification 004).

These tests cover every aspect of the specification:

1. Data model integrity (FeatureUnit, DependencyGraph, ExecutionPlan,
   BlueprintRisk, BlueprintValidation, ProjectBlueprint).
2. The planning engine reads ONLY the analysis_report (not the raw
   request).
3. Feature breakdown (each feature → independent FeatureUnit).
4. Internal component generation with priorities.
5. Component relationships.
6. Dependency graph (topological levels, parallel groups, cycle
   detection, dangling dependencies).
7. Execution plan (8 phases, order locked, phase assignment).
8. Risk detection (conflicts, missing, missing phases, incomplete deps).
9. Validation (all features connected, all deps valid, all phases
   complete).
10. Bootstrap integration (engine registered in registry and manager).
"""

import sys
import os

# Ensure the package is importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from typing import List

from telegram_bot_engine.core import build_configuration, bootstrap
from telegram_bot_engine.core.context import GenerationContext
from telegram_bot_engine.engines.generators.analyzer import (
    AnalysisReport,
    BotTypeEntry,
    Conflict,
    Feature,
    MissingInfo,
    Relationship,
    Technology,
)
from telegram_bot_engine.engines.generators.project_planner import (
    BlueprintRisk,
    BlueprintValidation,
    BlueprintValidator,
    ComponentRelationship,
    DEFAULT_PHASES,
    DependencyGraph,
    DependencyNode,
    ExecutionPhase,
    ExecutionPlan,
    ExpectedStructure,
    FeatureUnit,
    InternalComponent,
    PhaseDefinition,
    PhaseStatus,
    PRIORITY_CRITICAL,
    PRIORITY_DEFERRED,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_NORMAL,
    ProjectBlueprint,
    ProjectIdentity,
    ProjectPlanningEngine,
    RequiredEngine,
    RiskDetector,
    StructureEntry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_config():
    return build_configuration()


def make_context(report=None):
    ctx = GenerationContext(
        request="test request (not read by planner)",
        config=make_config(),
        work_dir=Path("/tmp/test"),
    )
    if report is not None:
        ctx.set("analysis_report", report)
    return ctx


def make_store_report():
    """A typical store-bot analysis report with 3 features + SQLite."""
    return AnalysisReport(
        raw_request="I want a store bot with admin panel and payment using SQLite",
        cleaned_request="store bot with admin panel and payment using sqlite",
        project_name="My Store Bot",
        bot_types=[
            BotTypeEntry(
                type="store",
                display_name="Store Bot",
                priority=10,
                confidence=0.9,
                evidence=["store"],
            ),
        ],
        description="A store bot with admin panel and payment using SQLite.",
        features=[
            Feature(
                name="admin_panel",
                display_name="Admin Panel",
                description="Manage the store.",
                keywords=["admin"],
                confidence=0.9,
            ),
            Feature(
                name="payment_integration",
                display_name="Payment Integration",
                description="Process payments.",
                keywords=["payment"],
                confidence=0.85,
            ),
            Feature(
                name="database",
                display_name="Database",
                description="Store data in SQLite.",
                keywords=["database", "sqlite"],
                confidence=0.95,
            ),
        ],
        technologies=[
            Technology(
                category="language",
                name="Python",
                role="primary",
                explicit=True,
                confidence=1.0,
            ),
            Technology(
                category="database",
                name="SQLite",
                role="primary_storage",
                explicit=True,
                confidence=1.0,
            ),
            Technology(
                category="framework",
                name="python-telegram-bot",
                role="bot_framework",
                explicit=False,
                confidence=0.8,
            ),
        ],
        ready=True,
    )


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.failures: List[str] = []

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        if condition:
            self.passed += 1
        else:
            self.failed += 1
            self.failures.append(f"{name}: {detail}" if detail else name)
            print(f"  FAIL: {name}" + (f" — {detail}" if detail else ""))

    def run_group(self, name: str, fn) -> None:
        print(f"\n{'=' * 70}")
        print(f"  {name}")
        print(f"{'=' * 70}")
        fn()

    def summary(self) -> None:
        print(f"\n{'=' * 70}")
        print(f"  RESULTS: {self.passed} passed, {self.failed} failed")
        print(f"{'=' * 70}")
        if self.failures:
            print("\nFailures:")
            for f in self.failures:
                print(f"  - {f}")
        else:
            print("\nAll tests passed! ✅")


t = TestRunner()


# ---------------------------------------------------------------------------
# Group 1: Data Model — FeatureUnit
# ---------------------------------------------------------------------------

def test_feature_unit():
    # Construction with all fields.
    unit = FeatureUnit(
        name="admin_panel",
        display_name="Admin Panel",
        description="Manage the store.",
        source_feature="admin_panel",
        build_priority=PRIORITY_HIGH,
        phase="generate_code",
        introduces_components=["admin_panel"],
        depends_on_components=["database"],
        depends_on_features=["database"],
        parallel_safe=True,
        requires_database=True,
        requires_config=True,
        confidence=0.9,
        metadata={"keywords": ["admin"]},
    )
    t.check("FU-01: construction", unit.name == "admin_panel")
    t.check("FU-02: display_name", unit.display_name == "Admin Panel")
    t.check("FU-03: priority", unit.build_priority == PRIORITY_HIGH)
    t.check("FU-04: introduces_components", unit.introduces_components == ["admin_panel"])
    t.check("FU-05: depends_on_components", "database" in unit.depends_on_components)

    # is_critical and is_deferred properties.
    critical = FeatureUnit(name="db", build_priority=PRIORITY_CRITICAL)
    t.check("FU-06: is_critical (priority 10)", critical.is_critical is True)
    t.check("FU-07: is_deferred (priority 10)", critical.is_deferred is False)

    deferred = FeatureUnit(name="late", build_priority=PRIORITY_DEFERRED)
    t.check("FU-08: is_deferred (priority 50)", deferred.is_deferred is True)
    t.check("FU-09: not is_critical (priority 50)", deferred.is_critical is False)

    normal = FeatureUnit(name="feat", build_priority=PRIORITY_NORMAL)
    t.check("FU-10: normal not critical", normal.is_critical is False)
    t.check("FU-11: normal not deferred", normal.is_deferred is False)

    # Empty name raises.
    try:
        FeatureUnit(name="")
        t.check("FU-12: empty name raises", False, "no exception")
    except ValueError:
        t.check("FU-12: empty name raises", True)

    # Default values.
    default_unit = FeatureUnit(name="test")
    t.check("FU-13: default parallel_safe", default_unit.parallel_safe is True)
    t.check("FU-14: default requires_database", default_unit.requires_database is False)
    t.check("FU-15: default confidence", default_unit.confidence == 1.0)
    t.check("FU-16: default priority", default_unit.build_priority == PRIORITY_NORMAL)

    # to_dict.
    d = unit.to_dict()
    t.check("FU-17: to_dict has name", d["name"] == "admin_panel")
    t.check("FU-18: to_dict has priority", d["build_priority"] == PRIORITY_HIGH)
    t.check("FU-19: to_dict has components", d["introduces_components"] == ["admin_panel"])

    # Priority constants.
    t.check("FU-20: PRIORITY_CRITICAL < PRIORITY_HIGH", PRIORITY_CRITICAL < PRIORITY_HIGH)
    t.check("FU-21: PRIORITY_HIGH < PRIORITY_NORMAL", PRIORITY_HIGH < PRIORITY_NORMAL)
    t.check("FU-22: PRIORITY_NORMAL < PRIORITY_LOW", PRIORITY_NORMAL < PRIORITY_LOW)
    t.check("FU-23: PRIORITY_LOW < PRIORITY_DEFERRED", PRIORITY_LOW < PRIORITY_DEFERRED)


# ---------------------------------------------------------------------------
# Group 2: Data Model — DependencyGraph
# ---------------------------------------------------------------------------

def test_dependency_graph():
    graph = DependencyGraph()

    # Empty graph.
    t.check("DG-01: empty count", graph.count() == 0)
    t.check("DG-02: empty roots", graph.roots() == [])
    t.check("DG-03: empty has_cycle", graph.has_cycle() is False)
    t.check("DG-04: empty dangling", graph.dangling_dependencies() == [])

    # Add nodes.
    graph.add_node("config_loader", kind="component", priority=10)
    graph.add_node("logger", kind="component", priority=20, dependencies=["config_loader"])
    graph.add_node("database", kind="component", priority=10, dependencies=["config_loader"])
    graph.add_node("admin_panel", kind="feature", priority=20)

    t.check("DG-05: count after add", graph.count() == 4)
    t.check("DG-06: get existing", graph.get("config_loader") is not None)
    t.check("DG-07: get missing", graph.get("nonexistent") is None)

    # Add edges.
    graph.add_edge("logger", "config_loader")
    graph.add_edge("database", "config_loader")
    graph.add_edge("admin_panel", "database")

    t.check("DG-08: logger deps", "config_loader" in graph.dependencies_of("logger"))
    t.check("DG-09: config_loader dependents", "logger" in graph.dependents_of("config_loader"))
    t.check("DG-10: database dependents", "admin_panel" in graph.dependents_of("database"))

    # Roots and leaves.
    root_names = [n.name for n in graph.roots()]
    t.check("DG-11: roots include config_loader", "config_loader" in root_names)
    t.check("DG-12: roots exclude logger", "logger" not in root_names)

    leaf_names = [n.name for n in graph.leaves()]
    t.check("DG-13: leaves include admin_panel", "admin_panel" in leaf_names)

    # No cycle.
    t.check("DG-14: no cycle", graph.has_cycle() is False)

    # Dangling dependencies.
    graph2 = DependencyGraph()
    graph2.add_node("A", dependencies=["B"])
    t.check("DG-15: dangling B", "B" in graph2.dangling_dependencies())
    t.check("DG-16: has_cycle with dangling (not cycle)", graph2.has_cycle() is False)

    # Cycle detection.
    graph3 = DependencyGraph()
    graph3.add_node("A")
    graph3.add_node("B")
    graph3.add_edge("A", "B")
    graph3.add_edge("B", "A")
    t.check("DG-17: cycle detected", graph3.has_cycle() is True)

    # Compute levels.
    levels = graph.compute_levels()
    t.check("DG-18: config_loader level 0", levels["config_loader"] == 0)
    t.check("DG-19: logger level 1", levels["logger"] == 1)
    t.check("DG-20: database level 1", levels["database"] == 1)
    t.check("DG-21: admin_panel level 2", levels["admin_panel"] == 2)

    # Parallel groups.
    groups = graph.parallel_groups()
    t.check("DG-22: group 0 has config_loader", "config_loader" in groups[0])
    t.check("DG-23: group 1 has logger and database",
            "logger" in groups[1] and "database" in groups[1])
    t.check("DG-24: group 2 has admin_panel", "admin_panel" in groups[2])

    # Build order.
    order = graph.build_order()
    t.check("DG-25: build_order starts with config_loader", order[0] == "config_loader")
    t.check("DG-26: build_order ends with admin_panel", order[-1] == "admin_panel")
    t.check("DG-27: build_order has all 4", len(order) == 4)

    # can_build_in_parallel.
    t.check("DG-28: logger and database can parallel",
            graph.can_build_in_parallel("logger", "database") is True)
    t.check("DG-29: admin_panel and database cannot parallel",
            graph.can_build_in_parallel("admin_panel", "database") is False)

    # depends_on (transitive).
    t.check("DG-30: admin_panel depends_on config_loader (transitive)",
            graph.depends_on("admin_panel", "config_loader") is True)
    t.check("DG-31: config_loader does not depend_on admin_panel",
            graph.depends_on("config_loader", "admin_panel") is False)

    # Idempotent add_node.
    graph.add_node("config_loader", priority=999)
    t.check("DG-32: idempotent add (same count)", graph.count() == 4)
    t.check("DG-33: idempotent add (priority preserved)",
            graph.get("config_loader").priority == 10)

    # deferred_nodes with cycle.
    t.check("DG-34: deferred_nodes in cycle graph", sorted(graph3.deferred_nodes()) == ["A", "B"])

    # to_dict.
    d = graph.to_dict()
    t.check("DG-35: to_dict has nodes", len(d["nodes"]) == 4)
    t.check("DG-36: to_dict has build_order", "build_order" in d)
    t.check("DG-37: to_dict has parallel_groups", "parallel_groups" in d)


# ---------------------------------------------------------------------------
# Group 3: Data Model — ExecutionPlan
# ---------------------------------------------------------------------------

def test_execution_plan():
    # DEFAULT_PHASES.
    t.check("EP-01: 8 default phases", len(DEFAULT_PHASES) == 8)
    expected_names = [
        "project_setup", "create_structure", "build_database",
        "create_files", "generate_code", "wire_components",
        "review", "export",
    ]
    t.check("EP-02: phase names match spec", [p.name for p in DEFAULT_PHASES] == expected_names)
    t.check("EP-03: phase numbers 1-8",
            [p.number for p in DEFAULT_PHASES] == list(range(1, 9)))

    # Phase 3 is skippable (database optional).
    t.check("EP-04: phase 3 skippable", DEFAULT_PHASES[2].skippable is True)
    # Phases 1, 2, 6, 7, 8 are not skippable.
    for i in [0, 1, 5, 6, 7]:
        t.check(f"EP-05.{i}: phase {i+1} not skippable",
                DEFAULT_PHASES[i].skippable is False)

    # Phases 3, 4, 5 can_parallel.
    t.check("EP-06: phase 3 can_parallel", DEFAULT_PHASES[2].can_parallel is True)
    t.check("EP-07: phase 4 can_parallel", DEFAULT_PHASES[3].can_parallel is True)
    t.check("EP-08: phase 5 can_parallel", DEFAULT_PHASES[4].can_parallel is True)
    # Phase 1 cannot parallel.
    t.check("EP-09: phase 1 cannot parallel", DEFAULT_PHASES[0].can_parallel is False)

    # PhaseStatus enum.
    t.check("EP-10: PENDING value", PhaseStatus.PENDING.value == "pending")
    t.check("EP-11: COMPLETED value", PhaseStatus.COMPLETED.value == "completed")
    t.check("EP-12: SKIPPED value", PhaseStatus.SKIPPED.value == "skipped")

    # ExecutionPhase properties.
    phase = ExecutionPhase(number=1, name="test", description="test phase")
    t.check("EP-13: default status is PENDING", phase.status == PhaseStatus.PENDING)
    t.check("EP-14: is_pending", phase.is_pending is True)
    t.check("EP-15: not is_completed", phase.is_completed is False)
    phase.status = PhaseStatus.COMPLETED
    t.check("EP-16: is_completed after set", phase.is_completed is True)

    # ExecutionPlan defaults.
    plan = ExecutionPlan()
    t.check("EP-17: empty plan not complete", plan.is_complete() is False)
    t.check("EP-18: default order_locked", plan.order_locked is True)

    # Build a complete plan with all 8 phases having tasks.
    phases = []
    for pd in DEFAULT_PHASES:
        phases.append(ExecutionPhase(
            number=pd.number, name=pd.name, description=pd.description,
            can_parallel=pd.can_parallel, skippable=pd.skippable,
            components=["task"],
        ))
    complete_plan = ExecutionPlan(phases=phases, order_locked=True)
    t.check("EP-19: complete plan is_complete", complete_plan.is_complete() is True)
    t.check("EP-20: all_phases_have_tasks", complete_plan.all_phases_have_tasks() is True)
    t.check("EP-21: phases_are_contiguous", complete_plan.phases_are_contiguous() is True)

    # Plan with non-contiguous phases.
    non_contiguous = ExecutionPlan(phases=[
        ExecutionPhase(number=1, name="a", components=["x"]),
        ExecutionPhase(number=3, name="b", components=["y"]),
    ])
    t.check("EP-22: non-contiguous not complete", non_contiguous.is_complete() is False)
    t.check("EP-23: non-contiguous not contiguous", non_contiguous.phases_are_contiguous() is False)

    # Plan with a phase that has no tasks and is not skippable.
    incomplete = ExecutionPlan(phases=[
        ExecutionPhase(number=1, name="a", components=["x"]),
        ExecutionPhase(number=2, name="b"),  # no tasks, not skippable
    ])
    t.check("EP-24: incomplete (empty phase) not complete", incomplete.is_complete() is False)
    t.check("EP-25: not all phases have tasks", incomplete.all_phases_have_tasks() is False)

    # Plan with a skippable empty phase is OK.
    skippable_plan = ExecutionPlan(phases=[
        ExecutionPhase(number=1, name="a", components=["x"]),
        ExecutionPhase(number=2, name="b", skippable=True),  # no tasks but skippable
    ])
    t.check("EP-26: skippable empty phase has tasks (skippable)",
            skippable_plan.all_phases_have_tasks() is True)

    # get_phase and get_phase_by_number.
    t.check("EP-27: get_phase by name",
            complete_plan.get_phase("review") is not None)
    t.check("EP-28: get_phase_by_number",
            complete_plan.get_phase_by_number(8).name == "export")
    t.check("EP-29: phase_names property",
            complete_plan.phase_names == expected_names)

    # Order not locked → not complete.
    unlocked = ExecutionPlan(phases=phases, order_locked=False)
    t.check("EP-30: unlocked plan not complete", unlocked.is_complete() is False)


# ---------------------------------------------------------------------------
# Group 4: Data Model — ProjectBlueprint, Identity, Structure
# ---------------------------------------------------------------------------

def test_blueprint_data_model():
    # ProjectIdentity.
    identity = ProjectIdentity(
        name="my_bot",
        display_name="My Bot",
        bot_type="store",
        language="python",
        language_version="3.11",
        framework="python-telegram-bot",
        libraries=["python-telegram-bot>=20.7"],
        database="sqlite",
    )
    t.check("BP-01: identity name", identity.name == "my_bot")
    t.check("BP-02: identity bot_type", identity.bot_type == "store")
    t.check("BP-03: identity database", identity.database == "sqlite")
    t.check("BP-04: identity to_dict", identity.to_dict()["name"] == "my_bot")

    # Default identity.
    default_identity = ProjectIdentity()
    t.check("BP-05: default language", default_identity.language == "python")
    t.check("BP-06: default framework", default_identity.framework == "python-telegram-bot")
    t.check("BP-07: default bot_type", default_identity.bot_type == "general")

    # StructureEntry and ExpectedStructure.
    entry1 = StructureEntry(path="src/", kind="directory", description="source")
    entry2 = StructureEntry(path="main.py", kind="file", description="entry point")
    structure = ExpectedStructure(root="my_bot", entries=[entry1, entry2])
    t.check("BP-08: structure root", structure.root == "my_bot")
    t.check("BP-09: structure directories", len(structure.directories()) == 1)
    t.check("BP-10: structure files", len(structure.files()) == 1)
    t.check("BP-11: structure dir path", structure.directories()[0].path == "src/")

    # InternalComponent.
    comp = InternalComponent(
        name="admin_panel",
        display_name="Admin Panel",
        kind="feature",
        priority=PRIORITY_HIGH,
        description="Manage the store.",
        source_feature="admin_panel",
        dependencies=["database"],
    )
    t.check("BP-12: component name", comp.name == "admin_panel")
    t.check("BP-13: component kind", comp.kind == "feature")
    t.check("BP-14: component deps", "database" in comp.dependencies)
    t.check("BP-15: component to_dict", comp.to_dict()["name"] == "admin_panel")

    # ComponentRelationship.
    rel = ComponentRelationship(
        source="admin_panel", target="database",
        kind="depends_on", description="admin uses db",
    )
    t.check("BP-16: relationship source", rel.source == "admin_panel")
    t.check("BP-17: relationship target", rel.target == "database")

    # RequiredEngine.
    engine = RequiredEngine(
        engine_id="code_generator",
        name="Code Generator",
        purpose="Generate code.",
        phase="generate_code",
        priority=10,
    )
    t.check("BP-18: required engine id", engine.engine_id == "code_generator")
    t.check("BP-19: required engine phase", engine.phase == "generate_code")

    # BlueprintRisk.
    risk = BlueprintRisk(
        kind="conflict", description="Two databases",
        severity="error", affected="database",
        resolution_hint="Choose one.",
    )
    t.check("BP-20: risk kind", risk.kind == "conflict")
    t.check("BP-21: risk severity", risk.severity == "error")

    # BlueprintValidation.
    validation = BlueprintValidation()
    t.check("BP-22: default validation valid=False", validation.valid is False)
    t.check("BP-23: default all_features_connected=False", validation.all_features_connected is False)
    t.check("BP-24: default errors empty", validation.errors == [])

    # ProjectBlueprint.
    blueprint = ProjectBlueprint()
    t.check("BP-25: default ready=False", blueprint.ready is False)
    t.check("BP-26: default features empty", blueprint.features == [])
    t.check("BP-27: default components empty", blueprint.components == [])
    t.check("BP-28: is_valid property", blueprint.is_valid is False)
    t.check("BP-29: has_errors property", blueprint.has_errors is False)
    t.check("BP-30: feature_names empty", blueprint.feature_names == [])
    t.check("BP-31: component_names empty", blueprint.component_names == [])

    # With data.
    blueprint.identity = identity
    blueprint.features = [FeatureUnit(name="admin_panel")]
    blueprint.components = [comp]
    t.check("BP-32: feature_names", blueprint.feature_names == ["admin_panel"])
    t.check("BP-33: component_names", blueprint.component_names == ["admin_panel"])
    t.check("BP-34: get_component", blueprint.get_component("admin_panel") is not None)
    t.check("BP-35: get_component missing", blueprint.get_component("nope") is None)
    t.check("BP-36: get_feature", blueprint.get_feature("admin_panel") is not None)
    t.check("BP-37: get_feature missing", blueprint.get_feature("nope") is None)

    # has_errors with error risk.
    blueprint.risks = [risk]
    t.check("BP-38: has_errors True", blueprint.has_errors is True)

    # to_dict.
    d = blueprint.to_dict()
    t.check("BP-39: to_dict has identity", "identity" in d)
    t.check("BP-40: to_dict has features", "features" in d)
    t.check("BP-41: to_dict has components", "components" in d)


# ---------------------------------------------------------------------------
# Group 5: Planning Engine — Source Isolation
# ---------------------------------------------------------------------------

def test_source_isolation():
    engine = ProjectPlanningEngine()

    # No analysis_report → fails.
    ctx = make_context(report=None)
    result = engine.execute(ctx)
    t.check("SI-01: no report → failure", result.success is False)
    t.check("SI-02: no report → error message mentions analysis_report",
            "analysis_report" in result.errors[0])
    t.check("SI-03: no blueprint stored", ctx.has("project_blueprint") is False)

    # The engine must NOT read the raw request.
    # We verify by giving a context with a request but no analysis_report.
    ctx2 = make_context(report=None)
    ctx2.request = "a completely different request that should be ignored"
    result2 = engine.execute(ctx2)
    t.check("SI-04: engine ignores raw request", result2.success is False)
    t.check("SI-05: error is about missing analysis_report not about request",
            "analysis_report" in result2.errors[0])


# ---------------------------------------------------------------------------
# Group 6: Planning Engine — Happy Path (Store Bot)
# ---------------------------------------------------------------------------

def test_happy_path():
    engine = ProjectPlanningEngine()
    report = make_store_report()
    ctx = make_context(report)
    result = engine.execute(ctx)

    t.check("HP-01: success", result.success is True)
    t.check("HP-02: no errors", result.errors == [])

    bp = ctx.get("project_blueprint")
    t.check("HP-03: blueprint stored", bp is not None)
    t.check("HP-04: blueprint ready", bp.ready is True)

    # Identity.
    t.check("HP-05: identity name", bp.identity.name == "my_store_bot")
    t.check("HP-06: identity bot_type", bp.identity.bot_type == "store")
    t.check("HP-07: identity language", bp.identity.language == "python")
    t.check("HP-08: identity database", bp.identity.database == "sqlite")
    t.check("HP-09: identity has framework in libraries",
            any("python-telegram-bot" in lib for lib in bp.identity.libraries))
    t.check("HP-10: identity has SQLAlchemy for sqlite",
            any("SQLAlchemy" in lib for lib in bp.identity.libraries))

    # Structure.
    t.check("HP-11: structure root matches identity", bp.structure.root == bp.identity.name)
    t.check("HP-12: structure has entries", len(bp.structure.entries) > 0)
    t.check("HP-13: structure has database model file",
            any("models" in e.path for e in bp.structure.entries))

    # Features.
    t.check("HP-14: 3 features", len(bp.features) == 3)
    t.check("HP-15: feature names", set(bp.feature_names) == {"admin_panel", "payment_integration", "database"})

    # Each feature is independent (has its own FeatureUnit).
    for unit in bp.features:
        t.check(f"HP-16: {unit.name} has name", unit.name != "")
        t.check(f"HP-17: {unit.name} has phase", unit.phase != "")
        t.check(f"HP-18: {unit.name} has introduces_components", len(unit.introduces_components) > 0)
        t.check(f"HP-19: {unit.name} is parallel_safe", unit.parallel_safe is True)

    # Components.
    t.check("HP-20: has config_loader", "config_loader" in bp.component_names)
    t.check("HP-21: has logger", "logger" in bp.component_names)
    t.check("HP-22: has database", "database" in bp.component_names)
    t.check("HP-23: has admin_panel", "admin_panel" in bp.component_names)
    t.check("HP-24: has payment_integration", "payment_integration" in bp.component_names)

    # Component priorities.
    config_comp = bp.get_component("config_loader")
    t.check("HP-25: config_loader is critical", config_comp.priority == PRIORITY_CRITICAL)
    logger_comp = bp.get_component("logger")
    t.check("HP-26: logger is high", logger_comp.priority == PRIORITY_HIGH)
    db_comp = bp.get_component("database")
    t.check("HP-27: database is critical", db_comp.priority == PRIORITY_CRITICAL)
    t.check("HP-28: database depends on config_loader", "config_loader" in db_comp.dependencies)
    t.check("HP-29: logger depends on config_loader", "config_loader" in logger_comp.dependencies)

    # Relationships.
    t.check("HP-30: has relationships", len(bp.relationships) > 0)
    rel_pairs = {(r.source, r.target) for r in bp.relationships}
    t.check("HP-31: logger→config_loader relationship", ("logger", "config_loader") in rel_pairs)
    t.check("HP-32: database→config_loader relationship", ("database", "config_loader") in rel_pairs)

    # Dependency graph.
    t.check("HP-33: graph has nodes", bp.dependency_graph.count() > 0)
    t.check("HP-34: no cycle", bp.dependency_graph.has_cycle() is False)
    t.check("HP-35: no dangling", bp.dependency_graph.dangling_dependencies() == [])
    t.check("HP-36: build_order is not empty", len(bp.dependency_graph.build_order()) > 0)
    t.check("HP-37: parallel_groups not empty", len(bp.dependency_graph.parallel_groups()) > 0)

    # Required engines.
    engine_ids = [e.engine_id for e in bp.required_engines]
    t.check("HP-38: has project_setup_engine", "project_setup_engine" in engine_ids)
    t.check("HP-39: has structure_builder_engine", "structure_builder_engine" in engine_ids)
    t.check("HP-40: has database_engine", "database_engine" in engine_ids)
    t.check("HP-41: has code_generator_engine", "code_generator_engine" in engine_ids)
    t.check("HP-42: has wiring_engine", "wiring_engine" in engine_ids)
    t.check("HP-43: has review_engine", "review_engine" in engine_ids)
    t.check("HP-44: has export_engine", "export_engine" in engine_ids)
    t.check("HP-45: 8 required engines", len(bp.required_engines) == 8)

    # Execution plan.
    plan = bp.execution_plan
    t.check("HP-46: 8 phases", len(plan.phases) == 8)
    t.check("HP-47: order_locked", plan.order_locked is True)
    t.check("HP-48: is_complete", plan.is_complete() is True)
    t.check("HP-49: phases contiguous", plan.phases_are_contiguous() is True)
    t.check("HP-50: all phases have tasks", plan.all_phases_have_tasks() is True)

    # Phase assignments.
    phase1 = plan.get_phase_by_number(1)
    t.check("HP-51: phase 1 has project_setup_engine", "project_setup_engine" in phase1.engines)
    t.check("HP-52: phase 1 has config_loader", "config_loader" in phase1.components)

    phase2 = plan.get_phase_by_number(2)
    t.check("HP-53: phase 2 has structure_builder_engine", "structure_builder_engine" in phase2.engines)

    phase3 = plan.get_phase_by_number(3)
    t.check("HP-54: phase 3 has database_engine", "database_engine" in phase3.engines)
    t.check("HP-55: phase 3 has database component", "database" in phase3.components)

    phase5 = plan.get_phase_by_number(5)
    t.check("HP-56: phase 5 has code_generator_engine", "code_generator_engine" in phase5.engines)
    t.check("HP-57: phase 5 has admin_panel", "admin_panel" in phase5.components)

    # Validation.
    t.check("HP-58: validation valid", bp.validation.valid is True)
    t.check("HP-59: all_features_connected", bp.validation.all_features_connected is True)
    t.check("HP-60: dependencies_valid", bp.validation.dependencies_valid is True)
    t.check("HP-61: phases_complete", bp.validation.phases_complete is True)

    # No error-severity risks.
    error_risks = [r for r in bp.risks if r.severity == "error"]
    t.check("HP-62: no error risks", len(error_risks) == 0)

    # Parallel design.
    t.check("HP-63: parallel_design has parallel_phases",
            "parallel_phases" in plan.parallel_design)
    t.check("HP-64: parallel_design has sequential_phases",
            "sequential_phases" in plan.parallel_design)


# ---------------------------------------------------------------------------
# Group 7: Risk Detection
# ---------------------------------------------------------------------------

def test_risk_detection():
    engine = ProjectPlanningEngine()

    # Conflict risk → blueprint rejected.
    report = make_store_report()
    report.conflicts = [
        Conflict(
            kind="conflicting_choice",
            description="Two databases selected: SQLite and PostgreSQL.",
            items=["SQLite", "PostgreSQL"],
            severity="error",
            resolution_hint="Choose one database.",
        ),
    ]
    report.ready = False
    ctx = make_context(report)
    result = engine.execute(ctx)
    t.check("RD-01: conflict → failure", result.success is False)
    bp = ctx.get("project_blueprint")
    t.check("RD-02: blueprint not ready", bp.ready is False)
    conflict_risks = [r for r in bp.risks if r.kind == "conflict"]
    t.check("RD-03: conflict risk detected", len(conflict_risks) > 0)
    t.check("RD-04: conflict risk is error", conflict_risks[0].severity == "error")
    t.check("RD-05: validation invalid", bp.validation.valid is False)

    # Missing required info → blueprint rejected.
    report2 = make_store_report()
    report2.missing_info = [
        MissingInfo(field="bot_token", question="What is the bot token?", required=True),
    ]
    report2.ready = False
    ctx2 = make_context(report2)
    result2 = engine.execute(ctx2)
    t.check("RD-06: missing info → failure", result2.success is False)
    bp2 = ctx2.get("project_blueprint")
    t.check("RD-07: blueprint not ready (missing)", bp2.ready is False)
    missing_risks = [r for r in bp2.risks if r.kind == "missing"]
    t.check("RD-08: missing risk detected", len(missing_risks) > 0)
    t.check("RD-09: missing risk is error", missing_risks[0].severity == "error")
    t.check("RD-10: missing risk affected is bot_token", missing_risks[0].affected == "bot_token")

    # Optional missing info → only warning, not error.
    report3 = make_store_report()
    report3.missing_info = [
        MissingInfo(field="webhook_url", question="Webhook URL?", required=False, default=""),
    ]
    ctx3 = make_context(report3)
    result3 = engine.execute(ctx3)
    t.check("RD-11: optional missing → success", result3.success is True)
    bp3 = ctx3.get("project_blueprint")
    t.check("RD-12: optional missing → ready", bp3.ready is True)
    # The optional missing info should NOT produce an error risk.
    missing_risks3 = [r for r in bp3.risks if r.kind == "missing"]
    t.check("RD-13: optional missing produces no error risks",
            all(r.severity != "error" for r in missing_risks3) or len(missing_risks3) == 0)

    # RiskDetector directly.
    detector = RiskDetector()
    from telegram_bot_engine.engines.generators.project_planner import ExecutionPlan as EP
    empty_plan = EP(phases=[
        ExecutionPhase(number=1, name="a", description=""),  # no tasks, not skippable
    ])
    risks = detector.detect(
        conflicts=[], missing_info=[], feature_units=[],
        components=[], dependency_graph=DependencyGraph(),
        execution_plan=empty_plan,
    )
    missing_phase_risks = [r for r in risks if r.kind == "missing_phase"]
    t.check("RD-14: missing_phase risk for empty non-skippable phase",
            len(missing_phase_risks) > 0)
    t.check("RD-15: missing_phase risk is warning", missing_phase_risks[0].severity == "warning")


# ---------------------------------------------------------------------------
# Group 8: Validation — All Three Checks
# ---------------------------------------------------------------------------

def test_validation():
    validator = BlueprintValidator()

    # Check 1: all features connected.
    # Single feature → trivially connected.
    graph1 = DependencyGraph()
    graph1.add_node("feature_a")
    graph1.add_node("comp_a")
    graph1.add_edge("feature_a", "comp_a")
    result1 = validator._check_features_connected(
        [FeatureUnit(name="feature_a", introduces_components=["comp_a"])],
        graph1,
    )
    t.check("VAL-01: single feature connected", result1 is True)

    # Feature not in graph and not connected via components.
    # Need 2+ features — single feature is trivially connected.
    graph2 = DependencyGraph()
    graph2.add_node("other")
    graph2.add_node("comp_other")
    graph2.add_edge("other", "comp_other")
    result2 = validator._check_features_connected(
        [
            FeatureUnit(name="other", introduces_components=["comp_other"]),
            FeatureUnit(name="orphan", introduces_components=["nonexistent"]),
        ],
        graph2,
    )
    t.check("VAL-02: orphan feature not connected (multiple features)",
            result2 is False)

    # Check 2: all dependencies valid — cycle.
    graph3 = DependencyGraph()
    graph3.add_node("A")
    graph3.add_node("B")
    graph3.add_edge("A", "B")
    graph3.add_edge("B", "A")
    result3 = validator._check_dependencies_valid(graph3)
    t.check("VAL-03: cycle → invalid deps", result3 is False)

    # Check 2: all dependencies valid — dangling.
    graph4 = DependencyGraph()
    graph4.add_node("A", dependencies=["B"])
    result4 = validator._check_dependencies_valid(graph4)
    t.check("VAL-04: dangling → invalid deps", result4 is False)

    # Check 2: all dependencies valid — clean graph.
    graph5 = DependencyGraph()
    graph5.add_node("A")
    graph5.add_node("B")
    graph5.add_edge("B", "A")
    result5 = validator._check_dependencies_valid(graph5)
    t.check("VAL-05: clean graph → valid deps", result5 is True)

    # Check 3: phases complete.
    # Complete plan (all 8 phases with tasks).
    complete_phases = []
    for pd in DEFAULT_PHASES:
        complete_phases.append(ExecutionPhase(
            number=pd.number, name=pd.name, description=pd.description,
            can_parallel=pd.can_parallel, skippable=pd.skippable,
            components=["task"],
        ))
    complete_plan = ExecutionPlan(phases=complete_phases, order_locked=True)
    result6 = validator._check_phases_complete(complete_plan)
    t.check("VAL-06: complete plan → phases complete", result6 is True)

    # Incomplete plan (missing a phase).
    incomplete_plan = ExecutionPlan(phases=complete_phases[:7], order_locked=True)
    result7 = validator._check_phases_complete(incomplete_plan)
    t.check("VAL-07: 7 phases → not complete", result7 is False)

    # Full validate with error risks → invalid.
    graph6 = DependencyGraph()
    graph6.add_node("A")
    graph6.add_node("B")
    graph6.add_edge("B", "A")
    validation = validator.validate(
        feature_units=[FeatureUnit(name="A"), FeatureUnit(name="B")],
        dependency_graph=graph6,
        execution_plan=complete_plan,
        risks=[BlueprintRisk(kind="conflict", description="err", severity="error")],
    )
    t.check("VAL-08: error risk → invalid", validation.valid is False)

    # Full validate with only warning risks → valid.
    graph7 = DependencyGraph()
    graph7.add_node("A")
    validation2 = validator.validate(
        feature_units=[FeatureUnit(name="A")],
        dependency_graph=graph7,
        execution_plan=complete_plan,
        risks=[BlueprintRisk(kind="missing", description="warn", severity="warning")],
    )
    t.check("VAL-09: warning risk only → valid", validation2.valid is True)
    t.check("VAL-10: warning collected", len(validation2.warnings) > 0)

    # Empty features → trivially connected.
    validation3 = validator.validate(
        feature_units=[],
        dependency_graph=DependencyGraph(),
        execution_plan=complete_plan,
        risks=[],
    )
    t.check("VAL-11: empty features → connected", validation3.all_features_connected is True)


# ---------------------------------------------------------------------------
# Group 9: Feature Breakdown — Independence
# ---------------------------------------------------------------------------

def test_feature_independence():
    engine = ProjectPlanningEngine()

    # Warning + mute → two independent features.
    report = AnalysisReport(
        raw_request="warning and mute system",
        cleaned_request="warning and mute system",
        project_name="Group Admin Bot",
        bot_types=[BotTypeEntry(type="group_admin", display_name="Group Admin", priority=10)],
        description="A group admin bot with warning and mute.",
        features=[
            Feature(name="warning_system", display_name="Warning System",
                    description="Warn users.", keywords=["warning"], confidence=0.9),
            Feature(name="mute_system", display_name="Mute System",
                    description="Mute users.", keywords=["mute"], confidence=0.85),
        ],
        ready=True,
    )
    ctx = make_context(report)
    result = engine.execute(ctx)
    t.check("FI-01: success", result.success is True)
    bp = ctx.get("project_blueprint")

    # Two independent FeatureUnits — never merged.
    t.check("FI-02: 2 features (not merged)", len(bp.features) == 2)
    t.check("FI-03: warning_system present", "warning_system" in bp.feature_names)
    t.check("FI-04: mute_system present", "mute_system" in bp.feature_names)

    # Each introduces its own component.
    warning = bp.get_feature("warning_system")
    mute = bp.get_feature("mute_system")
    t.check("FI-05: warning introduces warning_system component",
            "warning_system" in warning.introduces_components)
    t.check("FI-06: mute introduces mute_system component",
            "mute_system" in mute.introduces_components)
    t.check("FI-07: warning component != mute component",
            warning.introduces_components != mute.introduces_components)

    # Feature-to-component mapping.
    t.check("FI-08: warning maps to warning_system",
            warning.introduces_components[0] == "warning_system")
    t.check("FI-09: mute maps to mute_system",
            mute.introduces_components[0] == "mute_system")


# ---------------------------------------------------------------------------
# Group 10: Empty / Minimal Bot
# ---------------------------------------------------------------------------

def test_minimal_bot():
    engine = ProjectPlanningEngine()

    # No features at all.
    report = AnalysisReport(
        raw_request="simple bot",
        cleaned_request="simple bot",
        project_name="Simple Bot",
        description="A simple bot.",
        ready=True,
    )
    ctx = make_context(report)
    result = engine.execute(ctx)
    t.check("MB-01: minimal bot success", result.success is True)
    bp = ctx.get("project_blueprint")
    t.check("MB-02: minimal bot ready", bp.ready is True)

    # Still has core infrastructure.
    t.check("MB-03: has config_loader", "config_loader" in bp.component_names)
    t.check("MB-04: has logger", "logger" in bp.component_names)
    t.check("MB-05: no database (not needed)", "database" not in bp.component_names)

    # Execution plan is still complete.
    t.check("MB-06: plan complete", bp.execution_plan.is_complete() is True)

    # No database_engine required.
    engine_ids = [e.engine_id for e in bp.required_engines]
    t.check("MB-07: no database_engine (no db needed)", "database_engine" not in engine_ids)
    t.check("MB-08: 7 required engines (no db)", len(bp.required_engines) == 7)

    # Validation passes.
    t.check("MB-09: validation valid", bp.validation.valid is True)


# ---------------------------------------------------------------------------
# Group 11: Bootstrap Integration
# ---------------------------------------------------------------------------

def test_bootstrap_integration():
    registry, orchestrator, manager = bootstrap()

    # Registry has project_planner.
    engine_names = [e.name for e in registry.engines()]
    t.check("BI-01: registry has project_planner", "project_planner" in engine_names)
    t.check("BI-02: registry has 14 engines", len(registry.engines()) == 14)

    # Manager has project_planner.
    t.check("BI-03: manager count is 14", manager.count() == 14)
    states = manager.states()
    t.check("BI-04: manager has project_planner", "project_planner" in states)
    t.check("BI-05: project_planner state is registered",
            states["project_planner"] == "registered")

    # Queue order includes project_planner.
    queue = manager.queue_order()
    queue_ids = [q.engine_id for q in queue]
    t.check("BI-06: queue includes project_planner", "project_planner" in queue_ids)
    t.check("BI-07: queue has 14 items", len(queue) == 14)

    # Project planner has correct priority (40).
    planner_item = [q for q in queue if q.engine_id == "project_planner"][0]
    t.check("BI-08: project_planner priority 40", planner_item.priority == 40)

    # Project planner depends on analyzer.
    t.check("BI-09: project_planner depends on analyzer",
            "analyzer" in planner_item.dependencies)

    # Project planner instance is the correct type.
    entry = manager.get("project_planner")
    t.check("BI-10: entry is not None", entry is not None)
    t.check("BI-11: entry name is project_planner", entry.name == "project_planner")
    t.check("BI-12: entry version is 1.0.0", entry.version == "1.0.0")

    # All Spec 003 tests still pass (manager integrity).
    t.check("BI-13: manager not failed", manager.is_failed() is False)


# ---------------------------------------------------------------------------
# Group 12: End-to-End with Manager
# ---------------------------------------------------------------------------

def test_end_to_end_with_manager():
    """Run the project planner through the Core Engine Manager.

    The project planner depends on the analyzer, so we run the analyzer
    first (it has no dependencies) to complete it, then run the planner.
    """
    registry, orchestrator, manager = bootstrap()

    # Build a context with a raw request for the analyzer.
    # Include "polling" so the analyzer doesn't flag update_mode as
    # missing required info (which would cause the blueprint to fail).
    config = build_configuration()
    ctx = GenerationContext(
        request="I want a store bot using polling that manages products "
                "and orders using SQLite database",
        config=config,
        work_dir=Path("/tmp/test"),
    )

    # Run the analyzer first (no dependencies) to produce analysis_report.
    manager.load("analyzer")
    manager.initialize("analyzer")
    manager.mark_ready("analyzer")
    analyzer_result = manager.run_engine("analyzer", ctx)
    t.check("EE-01a: analyzer run success", analyzer_result.success is True)
    t.check("EE-01b: analysis_report stored", ctx.has("analysis_report") is True)

    # Now run the project planner (depends on analyzer, now completed).
    manager.load("project_planner")
    manager.initialize("project_planner")
    manager.mark_ready("project_planner")
    result = manager.run_engine("project_planner", ctx)
    t.check("EE-01: manager run_engine success", result.success is True)
    t.check("EE-02: blueprint stored after manager run", ctx.has("project_blueprint") is True)

    bp = ctx.get("project_blueprint")
    t.check("EE-03: blueprint ready after manager run", bp.ready is True)
    t.check("EE-04: manager not failed", manager.is_failed() is False)

    # The planner state should be completed.
    states = manager.states()
    t.check("EE-05: project_planner is completed", states["project_planner"] == "completed")


# ---------------------------------------------------------------------------
# Group 13: Database-Specific Behaviors
# ---------------------------------------------------------------------------

def test_database_variants():
    engine = ProjectPlanningEngine()

    # PostgreSQL.
    report_pg = AnalysisReport(
        raw_request="bot with postgres",
        cleaned_request="bot with postgres",
        project_name="PG Bot",
        features=[Feature(name="database", display_name="Database", confidence=0.9)],
        technologies=[
            Technology(category="database", name="PostgreSQL", role="primary", explicit=True),
        ],
        ready=True,
    )
    ctx_pg = make_context(report_pg)
    engine.execute(ctx_pg)
    bp_pg = ctx_pg.get("project_blueprint")
    t.check("DB-01: postgres database name", bp_pg.identity.database == "postgresql")
    t.check("DB-02: postgres has SQLAlchemy",
            any("SQLAlchemy" in lib for lib in bp_pg.identity.libraries))
    t.check("DB-03: postgres has psycopg2",
            any("psycopg2" in lib for lib in bp_pg.identity.libraries))

    # MySQL.
    report_mysql = AnalysisReport(
        raw_request="bot with mysql",
        cleaned_request="bot with mysql",
        project_name="MySQL Bot",
        features=[Feature(name="database", display_name="Database", confidence=0.9)],
        technologies=[
            Technology(category="database", name="MySQL", role="primary", explicit=True),
        ],
        ready=True,
    )
    ctx_mysql = make_context(report_mysql)
    engine.execute(ctx_mysql)
    bp_mysql = ctx_mysql.get("project_blueprint")
    t.check("DB-04: mysql database name", bp_mysql.identity.database == "mysql")
    t.check("DB-05: mysql has SQLAlchemy",
            any("SQLAlchemy" in lib for lib in bp_mysql.identity.libraries))
    t.check("DB-06: mysql has PyMySQL",
            any("PyMySQL" in lib for lib in bp_mysql.identity.libraries))

    # No database.
    report_no_db = AnalysisReport(
        raw_request="simple echo bot",
        cleaned_request="simple echo bot",
        project_name="Echo Bot",
        features=[Feature(name="commands", display_name="Commands", confidence=0.9)],
        ready=True,
    )
    ctx_no_db = make_context(report_no_db)
    engine.execute(ctx_no_db)
    bp_no_db = ctx_no_db.get("project_blueprint")
    t.check("DB-07: no database → empty string", bp_no_db.identity.database == "")
    t.check("DB-08: no database component", "database" not in bp_no_db.component_names)
    t.check("DB-09: no database_engine required",
            "database_engine" not in [e.engine_id for e in bp_no_db.required_engines])


# ---------------------------------------------------------------------------
# Group 14: Arabic Project Name Slugification
# ---------------------------------------------------------------------------

def test_arabic_slugification():
    engine = ProjectPlanningEngine()

    # Arabic project name.
    report = AnalysisReport(
        raw_request="بوت المتجر",
        cleaned_request="بوت المتجر",
        project_name="بوت المتجر",
        features=[Feature(name="admin", display_name="Admin", confidence=0.9)],
        ready=True,
    )
    ctx = make_context(report)
    result = engine.execute(ctx)
    t.check("AR-01: arabic name success", result.success is True)
    bp = ctx.get("project_blueprint")
    # The slug should be ASCII-safe (not Arabic characters).
    t.check("AR-02: arabic name → ascii slug",
            all(ord(c) < 128 for c in bp.identity.name.replace("_", "")))
    t.check("AR-03: slug is non-empty", bp.identity.name != "")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    t.run_group("Group 1: FeatureUnit Data Model", test_feature_unit)
    t.run_group("Group 2: DependencyGraph", test_dependency_graph)
    t.run_group("Group 3: ExecutionPlan", test_execution_plan)
    t.run_group("Group 4: Blueprint Data Model", test_blueprint_data_model)
    t.run_group("Group 5: Source Isolation (no raw request)", test_source_isolation)
    t.run_group("Group 6: Happy Path (Store Bot)", test_happy_path)
    t.run_group("Group 7: Risk Detection", test_risk_detection)
    t.run_group("Group 8: Validation (Three Checks)", test_validation)
    t.run_group("Group 9: Feature Independence", test_feature_independence)
    t.run_group("Group 10: Minimal Bot", test_minimal_bot)
    t.run_group("Group 11: Bootstrap Integration", test_bootstrap_integration)
    t.run_group("Group 12: End-to-End with Manager", test_end_to_end_with_manager)
    t.run_group("Group 13: Database Variants", test_database_variants)
    t.run_group("Group 14: Arabic Slugification", test_arabic_slugification)
    t.summary()

    return 0 if t.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
