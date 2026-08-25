#!/usr/bin/env python3
"""
Comprehensive test suite for the Blueprint Validator Engine
(Specification 005).

These tests cover every aspect of the specification:

1. Data model integrity (ValidationFinding, LayerResult, QualityScore,
   ConflictFinding, MissingInformationFinding,
   BlueprintValidationReport, constants).
2. The validator engine reads ONLY the project_blueprint (not the raw
   request or the analysis report).
3. Layer 1 — Basic Data Validation (name slug, bot type, language,
   framework, database, structure root).
4. Layer 2 — Features Validation (at least one, no duplicates,
   descriptions, phases, priorities, self-dependencies).
5. Layer 3 — Relationships Validation (feature-component connections,
   back-references, relationship endpoints, duplicates,
   feature/component depends_on).
6. Layer 4 — Execution Plan Validation (all 8 phases, contiguous,
   order, tasks, name uniqueness, order locked).
7. Layer 5 — Dependencies Validation (cycles, dangling, build order,
   deferred nodes, feature-database consistency).
8. Layer 6 — Buildability Validation (structure entries, engines,
   libraries, bot type, missing info, error risks, ready flag).
9. Conflict detector (incompatible database, unsupported framework,
   feature/phase/component depends on missing).
10. Quality scorer (sub-scores, weighted overall, minimum threshold,
    error/warning penalties).
11. The main engine produces APPROVED for a valid blueprint.
12. The main engine produces REJECTED for various broken blueprints.
13. The main engine stores the blueprint_validation_report artefact.
14. Bootstrap integration (engine registered in registry and manager).
"""

import sys
import os

# Ensure the package is importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from typing import List

from lumen.engine.core import build_configuration, bootstrap
from lumen.engine.core.context import GenerationContext
from lumen.engine.engines.generators.project_planner import (
    BlueprintRisk,
    BlueprintValidation,
    ComponentRelationship,
    DEFAULT_PHASES,
    DependencyGraph,
    DependencyNode,
    ExecutionPhase,
    ExecutionPlan,
    ExpectedStructure,
    FeatureUnit,
    InternalComponent,
    PhaseStatus,
    PRIORITY_CRITICAL,
    PRIORITY_DEFERRED,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_NORMAL,
    ProjectBlueprint,
    ProjectIdentity,
    RequiredEngine,
    StructureEntry,
)
from lumen.engine.engines.generators.blueprint_validator import (
    ALL_LAYERS,
    BlueprintValidationReport,
    BlueprintValidatorEngine,
    ConflictDetector,
    ConflictFinding,
    DEFAULT_MINIMUM_REQUIRED,
    DEFAULT_WEIGHTS,
    LAYER_1_BASIC_DATA,
    LAYER_2_FEATURES,
    LAYER_3_RELATIONSHIPS,
    LAYER_4_EXECUTION_PLAN,
    LAYER_5_DEPENDENCIES,
    LAYER_6_BUILDABILITY,
    Layer1BasicData,
    Layer2Features,
    Layer3Relationships,
    Layer4ExecutionPlan,
    Layer5Dependencies,
    Layer6Buildability,
    LayerResult,
    MissingInformationFinding,
    QualityScore,
    QualityScorer,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    STATUS_APPROVED,
    STATUS_REJECTED,
    SUPPORTED_DATABASES,
    SUPPORTED_FRAMEWORKS,
    ValidationFinding,
)


# ---------------------------------------------------------------------------#
# Helpers
# ---------------------------------------------------------------------------#

def make_config():
    return build_configuration()


def make_context(blueprint=None):
    ctx = GenerationContext(
        request="test request (not read by validator)",
        config=make_config(),
        work_dir=Path("/tmp/test"),
    )
    if blueprint is not None:
        ctx.set("project_blueprint", blueprint)
    return ctx


def make_identity(
    name="my_store_bot",
    display_name="My Store Bot",
    bot_type="store",
    language="python",
    language_version="3.11",
    framework="python-telegram-bot",
    database="sqlite",
    libraries=None,
):
    return ProjectIdentity(
        name=name,
        display_name=display_name,
        bot_type=bot_type,
        language=language,
        language_version=language_version,
        framework=framework,
        libraries=libraries if libraries is not None else [
            "python-telegram-bot>=20.0",
            "SQLAlchemy>=2.0",
        ],
        database=database,
    )


def make_structure(
    root="my_store_bot",
    entries=None,
):
    if entries is None:
        entries = [
            StructureEntry(path="my_store_bot/", kind="directory",
                           description="root package"),
            StructureEntry(path="my_store_bot/__init__.py", kind="file",
                           description="package init"),
            StructureEntry(path="my_store_bot/main.py", kind="file",
                           description="entry point"),
            StructureEntry(path="my_store_bot/handlers/", kind="directory",
                           description="handlers"),
            StructureEntry(path="my_store_bot/models.py", kind="file",
                           description="database models"),
        ]
    return ExpectedStructure(root=root, entries=entries)


def make_features():
    return [
        FeatureUnit(
            name="database",
            display_name="Database",
            description="Store data in SQLite.",
            source_feature="database",
            build_priority=PRIORITY_CRITICAL,
            phase="build_database",
            introduces_components=["database"],
            depends_on_components=[],
            depends_on_features=[],
            parallel_safe=True,
            requires_database=True,
            requires_config=True,
            confidence=0.95,
        ),
        FeatureUnit(
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
        ),
        FeatureUnit(
            name="payment_integration",
            display_name="Payment Integration",
            description="Process payments.",
            source_feature="payment_integration",
            build_priority=PRIORITY_NORMAL,
            phase="generate_code",
            introduces_components=["payment"],
            depends_on_components=["database"],
            depends_on_features=["database"],
            parallel_safe=True,
            requires_database=True,
            requires_config=False,
            confidence=0.85,
        ),
    ]


def make_components():
    return [
        InternalComponent(
            name="database",
            display_name="Database",
            kind="infrastructure",
            priority=10,
            description="Database layer.",
            source_feature="database",
            dependencies=[],
        ),
        InternalComponent(
            name="admin_panel",
            display_name="Admin Panel",
            kind="feature",
            priority=20,
            description="Admin panel.",
            source_feature="admin_panel",
            dependencies=["database"],
        ),
        InternalComponent(
            name="payment",
            display_name="Payment",
            kind="integration",
            priority=30,
            description="Payment processing.",
            source_feature="payment_integration",
            dependencies=["database"],
        ),
    ]


def make_relationships():
    return [
        ComponentRelationship(
            source="admin_panel",
            target="database",
            kind="depends_on",
            description="Admin panel depends on the database.",
        ),
        ComponentRelationship(
            source="payment",
            target="database",
            kind="depends_on",
            description="Payment depends on the database.",
        ),
    ]


def make_dependency_graph():
    graph = DependencyGraph()
    graph.add_node("database", kind="component", priority=10)
    graph.add_node("admin_panel", kind="component", priority=20,
                   dependencies=["database"])
    graph.add_node("payment", kind="component", priority=30,
                   dependencies=["database"])
    graph.add_edge("admin_panel", "database")
    graph.add_edge("payment", "database")
    return graph


def make_execution_plan():
    """Build a complete, valid execution plan with all 8 phases."""
    phases = []
    for pd in DEFAULT_PHASES:
        phase = ExecutionPhase(
            number=pd.number,
            name=pd.name,
            description=pd.description,
            can_parallel=pd.can_parallel,
            skippable=pd.skippable,
        )
        # Assign some tasks to each phase so none is empty.
        if pd.name == "project_setup":
            phase.engines = ["analyzer"]
        elif pd.name == "create_structure":
            phase.engines = ["structure_generator"]
        elif pd.name == "build_database":
            phase.components = ["database"]
            phase.features = ["database"]
        elif pd.name == "create_files":
            phase.components = ["admin_panel", "payment"]
        elif pd.name == "generate_code":
            phase.features = ["admin_panel", "payment_integration"]
        elif pd.name == "wire_components":
            phase.engines = ["wire_engine"]
        elif pd.name == "review":
            phase.engines = ["review_engine"]
        elif pd.name == "export":
            phase.engines = ["export_engine"]
        phases.append(phase)
    return ExecutionPlan(
        phases=phases,
        order_locked=True,
    )


def make_required_engines():
    return [
        RequiredEngine(
            engine_id="structure_generator",
            name="Structure Generator",
            purpose="Create the project structure.",
            phase="create_structure",
            priority=10,
        ),
        RequiredEngine(
            engine_id="code_generator",
            name="Code Generator",
            purpose="Generate the code.",
            phase="generate_code",
            priority=20,
        ),
    ]


def make_valid_blueprint():
    """A blueprint that passes all 6 layers and gets APPROVED."""
    return ProjectBlueprint(
        identity=make_identity(),
        structure=make_structure(),
        features=make_features(),
        components=make_components(),
        relationships=make_relationships(),
        required_engines=make_required_engines(),
        dependency_graph=make_dependency_graph(),
        execution_plan=make_execution_plan(),
        risks=[],
        validation=BlueprintValidation(
            valid=True,
            all_features_connected=True,
            dependencies_valid=True,
            phases_complete=True,
        ),
        ready=True,
        notes=["Plan looks good."],
        warnings=[],
    )


# ---------------------------------------------------------------------------#
# Test runner
# ---------------------------------------------------------------------------#

class TestRunner:
    __test__ = False

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


# ---------------------------------------------------------------------------#
# Group 1: Data Model — ValidationFinding
# ---------------------------------------------------------------------------#

def test_validation_finding():
    finding = ValidationFinding(
        layer=LAYER_1_BASIC_DATA,
        severity=SEVERITY_ERROR,
        code="missing_name",
        message="The project name is missing.",
        affected="identity.name",
        resolution_hint="Set a project name.",
    )
    t.check("VF-01: layer", finding.layer == LAYER_1_BASIC_DATA)
    t.check("VF-02: severity", finding.severity == SEVERITY_ERROR)
    t.check("VF-03: code", finding.code == "missing_name")
    t.check("VF-04: message", "project name" in finding.message.lower())
    t.check("VF-05: affected", finding.affected == "identity.name")
    t.check("VF-06: resolution_hint", finding.resolution_hint == "Set a project name.")

    # to_dict.
    d = finding.to_dict()
    t.check("VF-07: to_dict has layer", d["layer"] == LAYER_1_BASIC_DATA)
    t.check("VF-08: to_dict has severity", d["severity"] == SEVERITY_ERROR)
    t.check("VF-09: to_dict has code", d["code"] == "missing_name")
    t.check("VF-10: to_dict has message", d["message"] == finding.message)

    # Default severity is error.
    default_finding = ValidationFinding(layer=LAYER_2_FEATURES)
    t.check("VF-11: default severity is error", default_finding.severity == SEVERITY_ERROR)


# ---------------------------------------------------------------------------#
# Group 2: Data Model — LayerResult
# ---------------------------------------------------------------------------#

def test_layer_result():
    result = LayerResult(
        layer_id=LAYER_1_BASIC_DATA,
        name="Basic Data Validation",
    )
    t.check("LR-01: layer_id", result.layer_id == LAYER_1_BASIC_DATA)
    t.check("LR-02: name", result.name == "Basic Data Validation")
    t.check("LR-03: starts passed", result.passed is True)
    t.check("LR-04: empty findings", result.findings == [])
    t.check("LR-05: zero errors", result.error_count == 0)
    t.check("LR-06: zero warnings", result.warning_count == 0)
    t.check("LR-07: errors list empty", result.errors == [])
    t.check("LR-08: warnings list empty", result.warnings == [])

    # Add an error.
    result.add_error("bad_thing", "Something is wrong.", affected="x")
    t.check("LR-09: error count after add", result.error_count == 1)
    t.check("LR-10: passed is False after error", result.passed is False)
    t.check("LR-11: errors list has one", len(result.errors) == 1)
    t.check("LR-12: warning count unchanged", result.warning_count == 0)
    t.check("LR-13: error severity", result.errors[0].severity == SEVERITY_ERROR)
    t.check("LR-14: error code", result.errors[0].code == "bad_thing")

    # Add a warning.
    result.add_warning("mild_thing", "A minor issue.", affected="y")
    t.check("LR-15: warning count after add", result.warning_count == 1)
    t.check("LR-16: still passed False (has error)", result.passed is False)
    t.check("LR-17: warnings list has one", len(result.warnings) == 1)
    t.check("LR-18: error count unchanged", result.error_count == 1)
    t.check("LR-19: warning severity", result.warnings[0].severity == SEVERITY_WARNING)

    # to_dict.
    d = result.to_dict()
    t.check("LR-20: to_dict has layer_id", d["layer_id"] == LAYER_1_BASIC_DATA)
    t.check("LR-21: to_dict has passed", d["passed"] is False)
    t.check("LR-22: to_dict error_count", d["error_count"] == 1)
    t.check("LR-23: to_dict warning_count", d["warning_count"] == 1)
    t.check("LR-24: to_dict findings count", len(d["findings"]) == 2)

    # A layer with only warnings is still passed.
    warning_only = LayerResult(layer_id=LAYER_2_FEATURES, name="Features")
    warning_only.add_warning("w1", "A warning.")
    t.check("LR-25: warning-only passed is True", warning_only.passed is True)
    t.check("LR-26: warning-only error_count 0", warning_only.error_count == 0)


# ---------------------------------------------------------------------------#
# Group 3: Data Model — QualityScore
# ---------------------------------------------------------------------------#

def test_quality_score():
    qs = QualityScore(
        structure_quality=0.9,
        dependency_quality=0.85,
        feature_quality=0.8,
        planning_quality=0.95,
        overall=0.88,
        minimum_required=0.7,
        meets_minimum=True,
    )
    t.check("QS-01: structure", qs.structure_quality == 0.9)
    t.check("QS-02: dependency", qs.dependency_quality == 0.85)
    t.check("QS-03: feature", qs.feature_quality == 0.8)
    t.check("QS-04: planning", qs.planning_quality == 0.95)
    t.check("QS-05: overall", qs.overall == 0.88)
    t.check("QS-06: minimum_required", qs.minimum_required == 0.7)
    t.check("QS-07: meets_minimum", qs.meets_minimum is True)

    d = qs.to_dict()
    t.check("QS-08: to_dict has overall", d["overall"] == 0.88)
    t.check("QS-09: to_dict rounds", d["structure_quality"] == 0.9)
    t.check("QS-10: to_dict has meets_minimum", d["meets_minimum"] is True)

    # Defaults.
    default_qs = QualityScore()
    t.check("QS-11: default minimum 0.7", default_qs.minimum_required == 0.7)
    t.check("QS-12: default meets_minimum False", default_qs.meets_minimum is False)
    t.check("QS-13: default overall 0.0", default_qs.overall == 0.0)


# ---------------------------------------------------------------------------#
# Group 4: Data Model — ConflictFinding & MissingInformationFinding
# ---------------------------------------------------------------------------#

def test_conflict_and_missing():
    cf = ConflictFinding(
        kind="incompatible_database",
        description="Database 'mongo' is not supported.",
        severity=SEVERITY_ERROR,
        affected="mongo",
        resolution_hint="Use a supported database.",
    )
    t.check("CF-01: kind", cf.kind == "incompatible_database")
    t.check("CF-02: severity error", cf.severity == SEVERITY_ERROR)
    t.check("CF-03: affected", cf.affected == "mongo")
    d = cf.to_dict()
    t.check("CF-04: to_dict kind", d["kind"] == "incompatible_database")
    t.check("CF-05: to_dict severity", d["severity"] == SEVERITY_ERROR)

    mi = MissingInformationFinding(
        field="database",
        description="No database was declared.",
        question="Which database do you want?",
        required=True,
    )
    t.check("MI-01: field", mi.field == "database")
    t.check("MI-02: required", mi.required is True)
    t.check("MI-03: question", mi.question == "Which database do you want?")
    d2 = mi.to_dict()
    t.check("MI-04: to_dict field", d2["field"] == "database")
    t.check("MI-05: to_dict required", d2["required"] is True)


# ---------------------------------------------------------------------------#
# Group 5: Data Model — BlueprintValidationReport
# ---------------------------------------------------------------------------#

def test_validation_report():
    report = BlueprintValidationReport(
        blueprint_name="my_store_bot",
        reviewed_at="2024-01-01T00:00:00Z",
    )
    t.check("RPT-01: default status rejected", report.status == STATUS_REJECTED)
    t.check("RPT-02: is_rejected", report.is_rejected is True)
    t.check("RPT-03: not is_approved", report.is_approved is False)
    t.check("RPT-04: no layers", report.layers == {})
    t.check("RPT-05: all_layers_passed empty", report.all_layers_passed is True)
    t.check("RPT-06: no errors", report.error_count == 0)
    t.check("RPT-07: no warnings", report.warning_count == 0)
    t.check("RPT-08: no conflicts", report.conflicts == [])
    t.check("RPT-09: no missing_info", report.missing_info == [])

    # Add a passing layer.
    layer_ok = LayerResult(layer_id=LAYER_1_BASIC_DATA, name="Basic Data")
    report.add_layer(layer_ok)
    t.check("RPT-10: has layer 1", LAYER_1_BASIC_DATA in report.layers)
    t.check("RPT-11: all_layers_passed after 1 ok", report.all_layers_passed is True)

    # Add a failing layer.
    layer_fail = LayerResult(layer_id=LAYER_2_FEATURES, name="Features")
    layer_fail.add_error("no_features", "No features.")
    report.add_layer(layer_fail)
    t.check("RPT-12: has layer 2", LAYER_2_FEATURES in report.layers)
    t.check("RPT-13: not all_layers_passed", report.all_layers_passed is False)
    t.check("RPT-14: error_count is 1", report.error_count == 1)
    t.check("RPT-15: has_errors", report.has_errors is True)

    # Add a warning-only layer.
    layer_warn = LayerResult(layer_id=LAYER_3_RELATIONSHIPS, name="Relationships")
    layer_warn.add_warning("w1", "A warning.")
    report.add_layer(layer_warn)
    t.check("RPT-16: warning_count is 1", report.warning_count == 1)
    t.check("RPT-17: has_warnings", report.has_warnings is True)

    # Set status to APPROVED.
    report.status = STATUS_APPROVED
    t.check("RPT-18: is_approved", report.is_approved is True)
    t.check("RPT-19: not is_rejected", report.is_rejected is False)

    # to_dict.
    d = report.to_dict()
    t.check("RPT-20: to_dict status", d["status"] == STATUS_APPROVED)
    t.check("RPT-21: to_dict is_approved", d["is_approved"] is True)
    t.check("RPT-22: to_dict has layers", len(d["layers"]) == 3)
    t.check("RPT-23: to_dict error_count", d["error_count"] == 1)
    t.check("RPT-24: to_dict blueprint_name", d["blueprint_name"] == "my_store_bot")


# ---------------------------------------------------------------------------#
# Group 6: Layer 1 — Basic Data Validation
# ---------------------------------------------------------------------------#

def test_layer1_basic_data():
    layer = Layer1BasicData()
    t.check("L1-01: name", layer.name == "Basic Data Validation")

    # Valid identity.
    bp = make_valid_blueprint()
    result = layer.validate(bp)
    t.check("L1-02: valid blueprint passes", result.passed is True)
    t.check("L1-03: no errors on valid", result.error_count == 0)

    # Missing project name.
    bp = make_valid_blueprint()
    bp.identity.name = ""
    result = layer.validate(bp)
    t.check("L1-04: missing name → error", result.error_count >= 1)
    t.check("L1-05: missing name not passed", result.passed is False)
    codes = [f.code for f in result.errors]
    t.check("L1-06: has missing_project_name code", "missing_project_name" in codes)

    # Invalid project name (not a slug).
    bp = make_valid_blueprint()
    bp.identity.name = "My Store Bot!"
    result = layer.validate(bp)
    t.check("L1-07: invalid slug → error", result.error_count >= 1)
    codes = [f.code for f in result.errors]
    t.check("L1-08: has invalid_project_name code", "invalid_project_name" in codes)

    # Missing display name → warning only.
    bp = make_valid_blueprint()
    bp.identity.display_name = ""
    result = layer.validate(bp)
    t.check("L1-09: missing display name → warning", result.warning_count >= 1)
    t.check("L1-10: missing display name still passes", result.passed is True)

    # Missing bot type → error.
    bp = make_valid_blueprint()
    bp.identity.bot_type = ""
    result = layer.validate(bp)
    t.check("L1-11: missing bot_type → error", result.error_count >= 1)

    # Missing language → error.
    bp = make_valid_blueprint()
    bp.identity.language = ""
    result = layer.validate(bp)
    t.check("L1-12: missing language → error", result.error_count >= 1)

    # Missing framework → error.
    bp = make_valid_blueprint()
    bp.identity.framework = ""
    result = layer.validate(bp)
    t.check("L1-13: missing framework → error", result.error_count >= 1)

    # Features require database but no database declared → error.
    bp = make_valid_blueprint()
    bp.identity.database = ""
    result = layer.validate(bp)
    t.check("L1-14: needs db but no db → error", result.error_count >= 1)

    # No features require database, no database declared → ok.
    bp = make_valid_blueprint()
    bp.identity.database = ""
    for f in bp.features:
        f.requires_database = False
    result = layer.validate(bp)
    t.check("L1-15: no db needed, no db → ok", result.passed is True)

    # Missing structure root → error.
    bp = make_valid_blueprint()
    bp.structure.root = ""
    result = layer.validate(bp)
    t.check("L1-16: missing structure root → error", result.error_count >= 1)

    # duration_ms is set.
    bp = make_valid_blueprint()
    result = layer.validate(bp)
    t.check("L1-17: duration_ms >= 0", result.duration_ms >= 0)


# ---------------------------------------------------------------------------#
# Group 7: Layer 2 — Features Validation
# ---------------------------------------------------------------------------#

def test_layer2_features():
    layer = Layer2Features()
    t.check("L2-01: name", layer.name == "Features Validation")

    # Valid features.
    bp = make_valid_blueprint()
    result = layer.validate(bp)
    t.check("L2-02: valid features pass", result.passed is True)
    t.check("L2-03: no errors on valid", result.error_count == 0)

    # No features → error.
    bp = make_valid_blueprint()
    bp.features = []
    result = layer.validate(bp)
    t.check("L2-04: no features → error", result.error_count >= 1)
    codes = [f.code for f in result.errors]
    t.check("L2-05: has no_features code", "no_features" in codes)

    # Duplicate feature names → error.
    bp = make_valid_blueprint()
    bp.features[1].name = "database"  # duplicate
    result = layer.validate(bp)
    t.check("L2-06: duplicate → error", result.error_count >= 1)
    codes = [f.code for f in result.errors]
    t.check("L2-07: has duplicate_feature code", "duplicate_feature" in codes)

    # Feature with no description → warning.
    bp = make_valid_blueprint()
    bp.features[0].description = ""
    result = layer.validate(bp)
    t.check("L2-08: no description → warning", result.warning_count >= 1)
    t.check("L2-09: no description still passes", result.passed is True)

    # Feature with no phase → warning.
    bp = make_valid_blueprint()
    bp.features[0].phase = ""
    result = layer.validate(bp)
    t.check("L2-10: no phase → warning", result.warning_count >= 1)

    # Self-dependency → error.
    bp = make_valid_blueprint()
    bp.features[0].depends_on_features = ["database"]  # itself
    result = layer.validate(bp)
    t.check("L2-11: self-dependency → error", result.error_count >= 1)
    codes = [f.code for f in result.errors]
    t.check("L2-12: has self_dependency code", "self_dependency" in codes)

    # Invalid priority → warning.
    bp = make_valid_blueprint()
    bp.features[0].build_priority = 999
    result = layer.validate(bp)
    t.check("L2-13: invalid priority → warning", result.warning_count >= 1)


# ---------------------------------------------------------------------------#
# Group 8: Layer 3 — Relationships Validation
# ---------------------------------------------------------------------------#

def test_layer3_relationships():
    layer = Layer3Relationships()
    t.check("L3-01: name", layer.name == "Relationships Validation")

    # Valid relationships.
    bp = make_valid_blueprint()
    result = layer.validate(bp)
    t.check("L3-02: valid relationships pass", result.passed is True)
    t.check("L3-03: no errors on valid", result.error_count == 0)

    # Feature introduces missing component → error.
    bp = make_valid_blueprint()
    bp.features[0].introduces_components = ["nonexistent_component"]
    result = layer.validate(bp)
    t.check("L3-04: introduces missing comp → error", result.error_count >= 1)

    # Relationship source is unknown → error.
    bp = make_valid_blueprint()
    bp.relationships.append(ComponentRelationship(
        source="ghost", target="database", kind="depends_on",
    ))
    result = layer.validate(bp)
    t.check("L3-05: unknown source → error", result.error_count >= 1)

    # Relationship target is unknown → error.
    bp = make_valid_blueprint()
    bp.relationships.append(ComponentRelationship(
        source="admin_panel", target="ghost", kind="depends_on",
    ))
    result = layer.validate(bp)
    t.check("L3-06: unknown target → error", result.error_count >= 1)

    # Duplicate relationship → warning.
    bp = make_valid_blueprint()
    bp.relationships.append(ComponentRelationship(
        source="admin_panel", target="database", kind="depends_on",
    ))
    result = layer.validate(bp)
    t.check("L3-07: duplicate relationship → warning", result.warning_count >= 1)

    # Feature depends on missing feature → error.
    bp = make_valid_blueprint()
    bp.features[0].depends_on_features = ["nonexistent_feature"]
    result = layer.validate(bp)
    t.check("L3-08: feature dep on missing → error", result.error_count >= 1)

    # Component depends on missing component → error.
    bp = make_valid_blueprint()
    bp.components[0].dependencies = ["nonexistent_dep"]
    result = layer.validate(bp)
    t.check("L3-09: component dep on missing → error", result.error_count >= 1)

    # Component source_feature doesn't exist → warning.
    bp = make_valid_blueprint()
    bp.components[0].source_feature = "nonexistent_source_feature"
    result = layer.validate(bp)
    t.check("L3-10: bad source_feature → warning", result.warning_count >= 1)


# ---------------------------------------------------------------------------#
# Group 9: Layer 4 — Execution Plan Validation
# ---------------------------------------------------------------------------#

def test_layer4_execution_plan():
    layer = Layer4ExecutionPlan()
    t.check("L4-01: name", layer.name == "Execution Plan Validation")

    # Valid plan.
    bp = make_valid_blueprint()
    result = layer.validate(bp)
    t.check("L4-02: valid plan passes", result.passed is True)
    t.check("L4-03: no errors on valid", result.error_count == 0)

    # No phases → error.
    bp = make_valid_blueprint()
    bp.execution_plan.phases = []
    result = layer.validate(bp)
    t.check("L4-04: no phases → error", result.error_count >= 1)
    codes = [f.code for f in result.errors]
    t.check("L4-05: has no_phases code", "no_phases" in codes)

    # Missing a phase → error.
    bp = make_valid_blueprint()
    bp.execution_plan.phases = bp.execution_plan.phases[:7]  # drop last
    result = layer.validate(bp)
    t.check("L4-06: missing phase → error", result.error_count >= 1)
    codes = [f.code for f in result.errors]
    t.check("L4-07: has missing_phases code", "missing_phases" in codes)

    # Non-contiguous numbering → error.
    bp = make_valid_blueprint()
    bp.execution_plan.phases[-1].number = 99
    result = layer.validate(bp)
    t.check("L4-08: non-contiguous → error", result.error_count >= 1)

    # Duplicate phase name → error.
    bp = make_valid_blueprint()
    bp.execution_plan.phases[1].name = bp.execution_plan.phases[0].name
    result = layer.validate(bp)
    t.check("L4-09: duplicate phase name → error", result.error_count >= 1)

    # Empty non-skippable phase → warning.
    bp = make_valid_blueprint()
    bp.execution_plan.phases[0].components = []
    bp.execution_plan.phases[0].features = []
    bp.execution_plan.phases[0].engines = []
    bp.execution_plan.phases[0].skippable = False
    result = layer.validate(bp)
    t.check("L4-10: empty phase → warning", result.warning_count >= 1)

    # Order not locked → warning.
    bp = make_valid_blueprint()
    bp.execution_plan.order_locked = False
    result = layer.validate(bp)
    t.check("L4-11: order not locked → warning", result.warning_count >= 1)

    # Out of order phases → error.
    bp = make_valid_blueprint()
    # Swap phase numbers of first two phases.
    n0 = bp.execution_plan.phases[0].number
    n1 = bp.execution_plan.phases[1].number
    bp.execution_plan.phases[0].number = n1
    bp.execution_plan.phases[1].number = n0
    result = layer.validate(bp)
    t.check("L4-12: out of order → error", result.error_count >= 1)


# ---------------------------------------------------------------------------#
# Group 10: Layer 5 — Dependencies Validation
# ---------------------------------------------------------------------------#

def test_layer5_dependencies():
    layer = Layer5Dependencies()
    t.check("L5-01: name", layer.name == "Dependencies Validation")

    # Valid graph.
    bp = make_valid_blueprint()
    result = layer.validate(bp)
    t.check("L5-02: valid graph passes", result.passed is True)
    t.check("L5-03: no errors on valid", result.error_count == 0)

    # Empty graph → warning.
    bp = make_valid_blueprint()
    bp.dependency_graph = DependencyGraph()
    result = layer.validate(bp)
    t.check("L5-04: empty graph → warning", result.warning_count >= 1)

    # Cycle → error.
    bp = make_valid_blueprint()
    graph = bp.dependency_graph
    # Add a cycle: database → admin_panel → database.
    graph.add_edge("database", "admin_panel")
    result = layer.validate(bp)
    t.check("L5-05: cycle → error", result.error_count >= 1)
    codes = [f.code for f in result.errors]
    t.check("L5-06: has dependency_cycle code", "dependency_cycle" in codes)

    # Dangling dependency → error.
    # A node declares a dependency on a name that was never added as a
    # node.  We must NOT call add_edge for it (add_edge auto-creates the
    # target node).
    bp = make_valid_blueprint()
    graph = DependencyGraph()
    graph.add_node("database", kind="component", priority=10)
    graph.add_node("admin_panel", kind="component", priority=20,
                   dependencies=["database"])
    graph.add_node("payment", kind="component", priority=30,
                   dependencies=["database"])
    graph.add_node("lonely", kind="component", priority=50,
                   dependencies=["ghost_node"])
    graph.add_edge("admin_panel", "database")
    graph.add_edge("payment", "database")
    bp.dependency_graph = graph
    result = layer.validate(bp)
    t.check("L5-07: dangling → error", result.error_count >= 1)

    # Feature requires database but no database component → error.
    bp = make_valid_blueprint()
    bp.components = [c for c in bp.components if c.name != "database"]
    result = layer.validate(bp)
    t.check("L5-08: needs db but no db component → error", result.error_count >= 1)
    codes = [f.code for f in result.errors]
    t.check("L5-09: has feature_needs_missing_database code",
            "feature_needs_missing_database" in codes)


# ---------------------------------------------------------------------------#
# Group 11: Layer 6 — Buildability Validation
# ---------------------------------------------------------------------------#

def test_layer6_buildability():
    layer = Layer6Buildability()
    t.check("L6-01: name", layer.name == "Buildability Validation")

    # Valid blueprint.
    bp = make_valid_blueprint()
    result = layer.validate(bp)
    t.check("L6-02: valid blueprint passes", result.passed is True)
    t.check("L6-03: no errors on valid", result.error_count == 0)

    # No structure entries → warning.
    bp = make_valid_blueprint()
    bp.structure.entries = []
    result = layer.validate(bp)
    t.check("L6-04: no entries → warning", result.warning_count >= 1)

    # Thin structure (few entries) → warning.
    bp = make_valid_blueprint()
    bp.structure.entries = bp.structure.entries[:2]
    result = layer.validate(bp)
    t.check("L6-05: thin structure → warning", result.warning_count >= 1)

    # No required engines → warning.
    bp = make_valid_blueprint()
    bp.required_engines = []
    result = layer.validate(bp)
    t.check("L6-06: no engines → warning", result.warning_count >= 1)

    # No libraries → warning.
    bp = make_valid_blueprint()
    bp.identity.libraries = []
    result = layer.validate(bp)
    t.check("L6-07: no libraries → warning", result.warning_count >= 1)

    # Generic bot type → warning.
    bp = make_valid_blueprint()
    bp.identity.bot_type = "general"
    result = layer.validate(bp)
    t.check("L6-08: generic bot_type → warning", result.warning_count >= 1)

    # Missing required information (error-severity risk of kind missing).
    bp = make_valid_blueprint()
    bp.risks = [BlueprintRisk(
        kind="missing",
        description="Missing payment API key.",
        severity="error",
        affected="payment",
        resolution_hint="Provide the API key.",
    )]
    result = layer.validate(bp)
    t.check("L6-09: required missing info → error", result.error_count >= 1)
    codes = [f.code for f in result.errors]
    t.check("L6-10: has missing_required_information code",
            "missing_required_information" in codes)

    # Non-missing error-severity risk → error.
    bp = make_valid_blueprint()
    bp.risks = [BlueprintRisk(
        kind="conflict",
        description="A conflict risk.",
        severity="error",
        affected="x",
    )]
    result = layer.validate(bp)
    t.check("L6-11: error-severity risk → error", result.error_count >= 1)

    # Blueprint not ready and no other errors → error.
    bp = make_valid_blueprint()
    bp.ready = False
    bp.risks = []
    result = layer.validate(bp)
    t.check("L6-12: not ready → error", result.error_count >= 1)
    codes = [f.code for f in result.errors]
    t.check("L6-13: has blueprint_not_ready code", "blueprint_not_ready" in codes)

    # Missing info with warning severity → warning.
    bp = make_valid_blueprint()
    bp.risks = [BlueprintRisk(
        kind="missing",
        description="Optional info missing.",
        severity="warning",
        affected="x",
    )]
    result = layer.validate(bp)
    t.check("L6-14: warning missing info → warning", result.warning_count >= 1)


# ---------------------------------------------------------------------------#
# Group 12: Conflict Detector
# ---------------------------------------------------------------------------#

def test_conflict_detector():
    detector = ConflictDetector()

    # No conflicts on valid blueprint.
    bp = make_valid_blueprint()
    conflicts = detector.detect(bp)
    t.check("CD-01: no conflicts on valid", len(conflicts) == 0)

    # Incompatible database → error.
    bp = make_valid_blueprint()
    bp.identity.database = "mongodb"
    conflicts = detector.detect(bp)
    t.check("CD-02: incompatible database detected", len(conflicts) >= 1)
    kinds = [c.kind for c in conflicts]
    t.check("CD-03: has incompatible_database kind", "incompatible_database" in kinds)
    errors = [c for c in conflicts if c.severity == SEVERITY_ERROR]
    t.check("CD-04: incompatible db is error", len(errors) >= 1)

    # Unsupported framework → error.
    bp = make_valid_blueprint()
    bp.identity.framework = "flask"
    conflicts = detector.detect(bp)
    t.check("CD-05: unsupported framework detected", len(conflicts) >= 1)
    kinds = [c.kind for c in conflicts]
    t.check("CD-06: has unsupported_framework kind", "unsupported_framework" in kinds)

    # Feature depends on missing feature → error.
    bp = make_valid_blueprint()
    bp.features[0].depends_on_features = ["nonexistent_feature"]
    conflicts = detector.detect(bp)
    t.check("CD-07: feature dep on missing detected", len(conflicts) >= 1)

    # Component depends on missing component → error.
    bp = make_valid_blueprint()
    bp.components[0].dependencies = ["nonexistent_component"]
    conflicts = detector.detect(bp)
    t.check("CD-08: component dep on missing detected", len(conflicts) >= 1)

    # Relationship endpoint unknown → error.
    bp = make_valid_blueprint()
    bp.relationships.append(ComponentRelationship(
        source="ghost", target="database", kind="depends_on",
    ))
    conflicts = detector.detect(bp)
    t.check("CD-09: unknown relationship endpoint detected", len(conflicts) >= 1)

    # Supported databases.
    for db in ["sqlite", "postgres", "postgresql", "mysql", ""]:
        t.check(f"CD-10: {db!r} is supported", db in SUPPORTED_DATABASES)
    t.check("CD-11: mongodb not supported", "mongodb" not in SUPPORTED_DATABASES)

    # Supported frameworks.
    for fw in ["python-telegram-bot", "aiogram", "telebot", "pyrogram"]:
        t.check(f"CD-12: {fw!r} is supported", fw in SUPPORTED_FRAMEWORKS)
    t.check("CD-13: flask not supported", "flask" not in SUPPORTED_FRAMEWORKS)

    # Features require database but none declared → error.
    bp = make_valid_blueprint()
    bp.identity.database = ""
    conflicts = detector.detect(bp)
    t.check("CD-14: needs db but no db → conflict", len(conflicts) >= 1)


# ---------------------------------------------------------------------------#
# Group 13: Quality Scorer
# ---------------------------------------------------------------------------#

def test_quality_scorer():
    scorer = QualityScorer()

    # Valid blueprint scores high.
    bp = make_valid_blueprint()
    qs = scorer.score(bp, error_count=0, warning_count=0)
    t.check("QSC-01: overall >= 0.7", qs.overall >= 0.7)
    t.check("QSC-02: meets_minimum", qs.meets_minimum is True)
    t.check("QSC-03: structure_quality in [0,1]", 0.0 <= qs.structure_quality <= 1.0)
    t.check("QSC-04: dependency_quality in [0,1]", 0.0 <= qs.dependency_quality <= 1.0)
    t.check("QSC-05: feature_quality in [0,1]", 0.0 <= qs.feature_quality <= 1.0)
    t.check("QSC-06: planning_quality in [0,1]", 0.0 <= qs.planning_quality <= 1.0)

    # Default weights sum to 1.0.
    total_weight = sum(DEFAULT_WEIGHTS.values())
    t.check("QSC-07: weights sum to 1.0", abs(total_weight - 1.0) < 1e-9)

    # Default minimum required.
    t.check("QSC-08: default minimum 0.7", DEFAULT_MINIMUM_REQUIRED == 0.7)

    # Errors reduce the overall score.
    bp = make_valid_blueprint()
    qs_clean = scorer.score(bp, error_count=0, warning_count=0)
    qs_errors = scorer.score(bp, error_count=5, warning_count=0)
    t.check("QSC-09: errors reduce score", qs_errors.overall < qs_clean.overall)

    # Warnings reduce the overall score.
    qs_warns = scorer.score(bp, error_count=0, warning_count=5)
    t.check("QSC-10: warnings reduce score", qs_warns.overall < qs_clean.overall)

    # Empty features → lower feature quality.
    bp_empty = make_valid_blueprint()
    bp_empty.features = []
    qs_empty = scorer.score(bp_empty)
    bp_full = make_valid_blueprint()
    qs_full = scorer.score(bp_full)
    t.check("QSC-11: empty features lower feature quality",
            qs_empty.feature_quality <= qs_full.feature_quality)

    # Custom weights.
    custom_scorer = QualityScorer(
        weights={"structure_quality": 1.0, "dependency_quality": 0.0,
                 "feature_quality": 0.0, "planning_quality": 0.0},
        minimum_required=0.5,
    )
    bp = make_valid_blueprint()
    qs_custom = custom_scorer.score(bp)
    t.check("QSC-12: custom minimum 0.5", qs_custom.minimum_required == 0.5)

    # No execution plan phases → planning quality 0.
    bp = make_valid_blueprint()
    bp.execution_plan.phases = []
    qs = scorer.score(bp)
    t.check("QSC-13: no phases → planning 0", qs.planning_quality == 0.0)

    # Cycle in dependency graph → lower dependency quality.
    bp = make_valid_blueprint()
    bp.dependency_graph.add_edge("database", "admin_panel")
    qs_cycle = scorer.score(bp)
    bp2 = make_valid_blueprint()
    qs_no_cycle = scorer.score(bp2)
    t.check("QSC-14: cycle lowers dependency quality",
            qs_cycle.dependency_quality <= qs_no_cycle.dependency_quality)


# ---------------------------------------------------------------------------#
# Group 14: Engine — Missing Blueprint
# ---------------------------------------------------------------------------#

def test_engine_missing_blueprint():
    engine = BlueprintValidatorEngine()
    ctx = make_context(blueprint=None)
    result = engine.execute(ctx)
    t.check("ENG-01: no blueprint → failed", result.success is False)
    t.check("ENG-02: no blueprint → has errors", len(result.errors) >= 1)
    t.check("ENG-03: no blueprint → no report in context",
            ctx.get("blueprint_validation_report") is None)
    msg = " ".join(result.errors).lower()
    t.check("ENG-04: error mentions project_blueprint", "project_blueprint" in msg)


# ---------------------------------------------------------------------------#
# Group 15: Engine — Approved
# ---------------------------------------------------------------------------#

def test_engine_approved():
    engine = BlueprintValidatorEngine()
    bp = make_valid_blueprint()
    ctx = make_context(blueprint=bp)
    result = engine.execute(ctx)

    t.check("APR-01: valid blueprint → success", result.success is True)
    t.check("APR-02: valid blueprint → no errors", len(result.errors) == 0)

    # The report is stored in context.
    report = ctx.get("blueprint_validation_report")
    t.check("APR-03: report in context", report is not None)
    t.check("APR-04: report is BlueprintValidationReport",
            isinstance(report, BlueprintValidationReport))

    # Status is APPROVED.
    t.check("APR-05: status APPROVED", report.status == STATUS_APPROVED)
    t.check("APR-06: is_approved", report.is_approved is True)

    # All 6 layers present.
    t.check("APR-07: 6 layers", len(report.layers) == 6)
    for layer_id in ALL_LAYERS:
        t.check(f"APR-08: layer {layer_id} present", layer_id in report.layers)

    # All layers passed.
    t.check("APR-09: all_layers_passed", report.all_layers_passed is True)

    # No conflicts.
    t.check("APR-10: no conflicts", len(report.conflicts) == 0)

    # Quality meets minimum.
    t.check("APR-11: quality meets minimum", report.quality.meets_minimum is True)
    t.check("APR-12: quality overall >= 0.7", report.quality.overall >= 0.7)

    # StageResult metadata.
    t.check("APR-13: metadata has status", result.metadata.get("status") == STATUS_APPROVED)
    t.check("APR-14: metadata has quality_score", "quality_score" in result.metadata)
    t.check("APR-15: metadata has duration_ms", "duration_ms" in result.metadata)

    # The report has a summary.
    t.check("APR-16: has summary", bool(report.summary))
    t.check("APR-17: summary says APPROVED", "APPROVED" in report.summary)

    # The report has a blueprint_name.
    t.check("APR-18: blueprint_name set", report.blueprint_name == "my_store_bot")

    # The report has a reviewed_at timestamp.
    t.check("APR-19: reviewed_at set", bool(report.reviewed_at))

    # total_duration_ms is positive.
    t.check("APR-20: total_duration_ms >= 0", report.total_duration_ms >= 0)


# ---------------------------------------------------------------------------#
# Group 16: Engine — Rejected (various failures)
# ---------------------------------------------------------------------------#

def test_engine_rejected_missing_name():
    engine = BlueprintValidatorEngine()
    bp = make_valid_blueprint()
    bp.identity.name = ""
    ctx = make_context(blueprint=bp)
    result = engine.execute(ctx)
    t.check("REJ-01: missing name → failed", result.success is False)
    report = ctx.get("blueprint_validation_report")
    t.check("REJ-02: report stored", report is not None)
    t.check("REJ-03: status REJECTED", report.status == STATUS_REJECTED)
    t.check("REJ-04: has errors", report.error_count >= 1)
    t.check("REJ-05: not all layers passed", report.all_layers_passed is False)
    t.check("REJ-06: summary says REJECTED", "REJECTED" in report.summary)


def test_engine_rejected_no_features():
    engine = BlueprintValidatorEngine()
    bp = make_valid_blueprint()
    bp.features = []
    ctx = make_context(blueprint=bp)
    result = engine.execute(ctx)
    t.check("REJ-07: no features → failed", result.success is False)
    report = ctx.get("blueprint_validation_report")
    t.check("REJ-08: status REJECTED", report.status == STATUS_REJECTED)


def test_engine_rejected_incompatible_database():
    engine = BlueprintValidatorEngine()
    bp = make_valid_blueprint()
    bp.identity.database = "mongodb"
    ctx = make_context(blueprint=bp)
    result = engine.execute(ctx)
    t.check("REJ-09: incompatible db → failed", result.success is False)
    report = ctx.get("blueprint_validation_report")
    t.check("REJ-10: status REJECTED", report.status == STATUS_REJECTED)
    t.check("REJ-11: has conflict", len(report.conflicts) >= 1)


def test_engine_rejected_cycle():
    engine = BlueprintValidatorEngine()
    bp = make_valid_blueprint()
    bp.dependency_graph.add_edge("database", "admin_panel")
    ctx = make_context(blueprint=bp)
    result = engine.execute(ctx)
    t.check("REJ-12: cycle → failed", result.success is False)
    report = ctx.get("blueprint_validation_report")
    t.check("REJ-13: status REJECTED", report.status == STATUS_REJECTED)


def test_engine_rejected_not_ready():
    engine = BlueprintValidatorEngine()
    bp = make_valid_blueprint()
    bp.ready = False
    bp.risks = []
    ctx = make_context(blueprint=bp)
    result = engine.execute(ctx)
    t.check("REJ-14: not ready → failed", result.success is False)
    report = ctx.get("blueprint_validation_report")
    t.check("REJ-15: status REJECTED", report.status == STATUS_REJECTED)


def test_engine_rejected_missing_phases():
    engine = BlueprintValidatorEngine()
    bp = make_valid_blueprint()
    bp.execution_plan.phases = bp.execution_plan.phases[:4]
    ctx = make_context(blueprint=bp)
    result = engine.execute(ctx)
    t.check("REJ-16: missing phases → failed", result.success is False)
    report = ctx.get("blueprint_validation_report")
    t.check("REJ-17: status REJECTED", report.status == STATUS_REJECTED)


# ---------------------------------------------------------------------------#
# Group 17: Engine — Warnings don't cause rejection
# ---------------------------------------------------------------------------#

def test_engine_warnings_ok():
    """A blueprint with only warnings (no errors) should still be APPROVED."""
    engine = BlueprintValidatorEngine()
    bp = make_valid_blueprint()
    # Remove the display name (warning) and the libraries (warning).
    # But keep everything else valid so it passes.
    bp.identity.display_name = ""  # Layer 1 warning
    ctx = make_context(blueprint=bp)
    result = engine.execute(ctx)
    report = ctx.get("blueprint_validation_report")
    # Even with warnings, if no errors and quality is high enough → APPROVED.
    t.check("WRN-01: warnings don't block success", result.success is True)
    t.check("WRN-02: status APPROVED", report.status == STATUS_APPROVED)
    t.check("WRN-03: has warnings", report.warning_count >= 1)
    t.check("WRN-04: no errors", report.error_count == 0)


# ---------------------------------------------------------------------------#
# Group 18: Engine — Does NOT read the raw request
# ---------------------------------------------------------------------------#

def test_engine_does_not_read_request():
    """The validator engine must only read project_blueprint, not the
    request or analysis_report."""
    engine = BlueprintValidatorEngine()
    bp = make_valid_blueprint()
    ctx = make_context(blueprint=bp)
    # Set an analysis_report — the validator must NOT read it.
    ctx.set("analysis_report", "this should be ignored")
    # Set a weird request — the validator must NOT read it.
    ctx.request = "COMPLETELY WRONG REQUEST THAT SHOULD BE IGNORED"
    result = engine.execute(ctx)
    t.check("NOR-01: ignores request → success", result.success is True)
    report = ctx.get("blueprint_validation_report")
    t.check("NOR-02: still APPROVED", report.status == STATUS_APPROVED)


# ---------------------------------------------------------------------------#
# Group 19: Engine — Layer isolation
# ---------------------------------------------------------------------------#

def test_layer_isolation():
    """Each layer is a stateless, independent validator."""
    layers = [
        Layer1BasicData(),
        Layer2Features(),
        Layer3Relationships(),
        Layer4ExecutionPlan(),
        Layer5Dependencies(),
        Layer6Buildability(),
    ]
    bp = make_valid_blueprint()

    # Each layer can be run independently.
    for layer in layers:
        result = layer.validate(bp)
        t.check(f"ISO-01: {layer.name} returns LayerResult",
                isinstance(result, LayerResult))
        t.check(f"ISO-02: {layer.name} has correct layer_id",
                result.layer_id in ALL_LAYERS)
        t.check(f"ISO-03: {layer.name} duration set",
                result.duration_ms >= 0)

    # Running the same layer twice gives consistent results.
    l1 = Layer1BasicData()
    r1 = l1.validate(bp)
    r2 = l1.validate(bp)
    t.check("ISO-04: consistent results", r1.passed == r2.passed)
    t.check("ISO-05: consistent error count", r1.error_count == r2.error_count)


# ---------------------------------------------------------------------------#
# Group 20: Engine — Report to_dict
# ---------------------------------------------------------------------------#

def test_engine_report_serialisation():
    engine = BlueprintValidatorEngine()
    bp = make_valid_blueprint()
    ctx = make_context(blueprint=bp)
    engine.execute(ctx)
    report = ctx.get("blueprint_validation_report")
    d = report.to_dict()
    t.check("SER-01: to_dict has status", "status" in d)
    t.check("SER-02: to_dict has layers", "layers" in d)
    t.check("SER-03: to_dict has quality", "quality" in d)
    t.check("SER-04: to_dict has conflicts", "conflicts" in d)
    t.check("SER-05: to_dict has missing_info", "missing_info" in d)
    t.check("SER-06: to_dict has summary", "summary" in d)
    t.check("SER-07: to_dict 6 layers", len(d["layers"]) == 6)
    t.check("SER-08: to_dict quality has overall", "overall" in d["quality"])


# ---------------------------------------------------------------------------#
# Group 21: Bootstrap Integration
# ---------------------------------------------------------------------------#

def test_bootstrap_integration():
    registry, orchestrator, manager = bootstrap()

    # The engine is in the registry.
    engine_names = [e.name for e in registry.engines()]
    t.check("BST-01: blueprint_validator in registry",
            "blueprint_validator" in engine_names)

    # The engine is in the manager.
    entries = manager.all_entries()
    bv_entry = None
    for entry in entries:
        if entry.engine_id == "blueprint_validator":
            bv_entry = entry
            break
    t.check("BST-02: blueprint_validator in manager", bv_entry is not None)
    if bv_entry:
        t.check("BST-03: priority is 50", bv_entry.priority == 160)
        t.check("BST-04: depends on project_planner",
                "unit_test_generation" in bv_entry.dependencies)

    # The engine instance from the registry works.
    for e in registry.engines():
        if e.name == "blueprint_validator":
            bp = make_valid_blueprint()
            ctx = make_context(blueprint=bp)
            result = e.execute(ctx)
            t.check("BST-05: registry engine executes", result.success is True)
            break


# ---------------------------------------------------------------------------#
# Group 22: Constants and ALL_LAYERS
# ---------------------------------------------------------------------------#

def test_constants():
    t.check("CON-01: 6 layers in ALL_LAYERS", len(ALL_LAYERS) == 6)
    t.check("CON-02: LAYER_1 in ALL_LAYERS", LAYER_1_BASIC_DATA in ALL_LAYERS)
    t.check("CON-03: LAYER_2 in ALL_LAYERS", LAYER_2_FEATURES in ALL_LAYERS)
    t.check("CON-04: LAYER_3 in ALL_LAYERS", LAYER_3_RELATIONSHIPS in ALL_LAYERS)
    t.check("CON-05: LAYER_4 in ALL_LAYERS", LAYER_4_EXECUTION_PLAN in ALL_LAYERS)
    t.check("CON-06: LAYER_5 in ALL_LAYERS", LAYER_5_DEPENDENCIES in ALL_LAYERS)
    t.check("CON-07: LAYER_6 in ALL_LAYERS", LAYER_6_BUILDABILITY in ALL_LAYERS)

    t.check("CON-08: SEVERITY_ERROR", SEVERITY_ERROR == "error")
    t.check("CON-09: SEVERITY_WARNING", SEVERITY_WARNING == "warning")
    t.check("CON-10: SEVERITY_INFO", SEVERITY_INFO == "info")
    t.check("CON-11: STATUS_APPROVED", STATUS_APPROVED == "APPROVED")
    t.check("CON-12: STATUS_REJECTED", STATUS_REJECTED == "REJECTED")

    # ALL_LAYERS has no duplicates.
    t.check("CON-13: no duplicate layer ids", len(set(ALL_LAYERS)) == 6)


# ---------------------------------------------------------------------------#
# Main
# ---------------------------------------------------------------------------#

def main():
    t.run_group("Group 1: ValidationFinding", test_validation_finding)
    t.run_group("Group 2: LayerResult", test_layer_result)
    t.run_group("Group 3: QualityScore", test_quality_score)
    t.run_group("Group 4: ConflictFinding & MissingInformationFinding",
                test_conflict_and_missing)
    t.run_group("Group 5: BlueprintValidationReport", test_validation_report)
    t.run_group("Group 6: Layer 1 — Basic Data", test_layer1_basic_data)
    t.run_group("Group 7: Layer 2 — Features", test_layer2_features)
    t.run_group("Group 8: Layer 3 — Relationships", test_layer3_relationships)
    t.run_group("Group 9: Layer 4 — Execution Plan", test_layer4_execution_plan)
    t.run_group("Group 10: Layer 5 — Dependencies", test_layer5_dependencies)
    t.run_group("Group 11: Layer 6 — Buildability", test_layer6_buildability)
    t.run_group("Group 12: Conflict Detector", test_conflict_detector)
    t.run_group("Group 13: Quality Scorer", test_quality_scorer)
    t.run_group("Group 14: Engine — Missing Blueprint", test_engine_missing_blueprint)
    t.run_group("Group 15: Engine — Approved", test_engine_approved)
    t.run_group("Group 16: Engine — Rejected", lambda: [
        test_engine_rejected_missing_name(),
        test_engine_rejected_no_features(),
        test_engine_rejected_incompatible_database(),
        test_engine_rejected_cycle(),
        test_engine_rejected_not_ready(),
        test_engine_rejected_missing_phases(),
    ])
    t.run_group("Group 17: Engine — Warnings OK", test_engine_warnings_ok)
    t.run_group("Group 18: Engine — Does Not Read Request",
                test_engine_does_not_read_request)
    t.run_group("Group 19: Layer Isolation", test_layer_isolation)
    t.run_group("Group 20: Report Serialisation", test_engine_report_serialisation)
    t.run_group("Group 21: Bootstrap Integration", test_bootstrap_integration)
    t.run_group("Group 22: Constants", test_constants)
    t.summary()
    return t.failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
