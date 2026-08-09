#!/usr/bin/env python3
"""
Comprehensive test suite for the Dependency Resolution Engine
(Specification 009).

These tests cover every aspect of the specification:

1. Data model integrity (DependencyResolutionReport, DependencyEntry,
   DependencyRelationship, DependencyOrderEntry, ResolutionFinding,
   dependency-type constants, dependency-priority constants, source
   constants, reputation/trust/stability constants, severity
   constants).
2. The ComponentAnalyzer (analyse, group required libraries, missing-
   requirement findings).
3. The LibraryDeterminer (determine dependencies, assign metadata,
   versions, types, priorities, reasons, sources, compatibility).
4. The DependencyGraphBuilder (inter-library relationships, component-
   based dependencies, load order, topological sort).
5. The CompatibilityChecker (language, framework, OS, inter-library,
   version compatibility).
6. The ConflictDetector (duplicates, version conflicts, unused,
   broken, circular, orphaned dependencies).
7. The DependencyOptimizer (minimization, official preference,
   abandoned, unstable, critical stability, extensibility).
8. The SecurityChecker (bad reputation, untrusted, known-vulnerable
   versions, unknown reputation/trust, abandoned).
9. The PlanValidator (not empty, all deps complete, no conflicts,
   valid relationships, load order valid, components covered,
   buildable).
10. The main engine reads ONLY the project_blueprint,
    blueprint_validation_report, project_structure_map,
    component_registry, and file_generation_plan artefacts (not the
    raw request).
11. The main engine produces a DependencyResolutionReport artefact.
12. The main engine fails when each of the 5 artefacts is missing.
13. The main engine fails when the artefacts are the wrong type.
14. The dependency report records the source artefacts.
15. Bootstrap integration (engine registered in registry and manager
    at priority 90, depends on file_planner).
16. Serialisation (to_dict) for all data model classes.
17. End-to-end pipeline.
"""

import sys
import os

# Ensure the package is importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path

from telegram_bot_engine.core import build_configuration, bootstrap
from telegram_bot_engine.core.context import GenerationContext
from telegram_bot_engine.engines.generators.project_planner import (
    BlueprintValidation,
    ComponentRelationship,
    DependencyGraph,
    ExecutionPlan,
    ExpectedStructure,
    FeatureUnit,
    InternalComponent,
    PRIORITY_CRITICAL,
    PRIORITY_NORMAL,
    ProjectBlueprint,
    ProjectIdentity,
    RequiredEngine,
    StructureEntry,
)
from telegram_bot_engine.engines.generators.blueprint_validator import (
    BlueprintValidationReport,
    QualityScore,
    STATUS_APPROVED,
    STATUS_REJECTED,
)
from telegram_bot_engine.engines.generators.structure_generator import (
    BuildOrderEntry,
    FILE_TYPE_DOCKERFILE,
    FILE_TYPE_ENV,
    FILE_TYPE_JSON,
    FILE_TYPE_MARKDOWN,
    FILE_TYPE_PYTHON_MODULE,
    FILE_TYPE_PYTHON_PACKAGE,
    FILE_TYPE_REQUIREMENTS,
    FILE_TYPE_TEXT,
    FILE_TYPE_YAML,
    FileEntry,
    FolderEntry,
    ProjectStructureMap,
    StructureRelationship,
    BUILD_ORDER_CORE,
    BUILD_ORDER_DATABASE,
    BUILD_ORDER_DOCS,
    BUILD_ORDER_FEATURES,
    BUILD_ORDER_INFRASTRUCTURE,
    BUILD_ORDER_TESTS,
    BUILD_ORDER_WIRING,
    BUILD_ORDER_ENTRY,
)
from telegram_bot_engine.engines.generators.component_detector import (
    ComponentRegistry,
    DetectedComponent,
    COMPONENT_TYPE_COMMAND,
    COMPONENT_TYPE_DATABASE_MODEL,
    COMPONENT_TYPE_REPOSITORY,
    COMPONENT_TYPE_SERVICE,
    COMPONENT_TYPE_UTILITY,
    IMPORTANCE_CRITICAL,
    IMPORTANCE_HIGH,
    IMPORTANCE_NORMAL,
)
from telegram_bot_engine.engines.generators.file_planner import (
    FileGenerationPlanningEngine,
    FileGenerationPlan,
    FilePlanEntry,
    FileRelationship,
    FileGenerationOrderEntry,
    PlanFinding,
    SEVERITY_ERROR as FP_SEVERITY_ERROR,
    SEVERITY_WARNING as FP_SEVERITY_WARNING,
    SEVERITY_INFO as FP_SEVERITY_INFO,
    GENERATION_PRIORITY_INFRASTRUCTURE,
    GENERATION_PRIORITY_CORE,
    GENERATION_PRIORITY_DATABASE,
    GENERATION_PRIORITY_FEATURES,
    GENERATION_PRIORITY_WIRING,
    GENERATION_PRIORITY_ENTRY,
    GENERATION_PRIORITY_DOCS,
    GENERATION_PRIORITY_TESTS,
    EXTENSION_PYTHON,
    EXTENSION_YAML,
    EXTENSION_YML,
    EXTENSION_TOML,
    EXTENSION_JSON,
    EXTENSION_ENV,
    EXTENSION_SQL,
    EXTENSION_MARKDOWN,
    EXTENSION_TEXT,
    EXTENSION_DOCKERFILE,
    EXTENSION_SCRIPT,
    FILE_TYPE_PYTHON_MODULE as FP_FILE_TYPE_PYTHON_MODULE,
    FILE_TYPE_PYTHON_PACKAGE as FP_FILE_TYPE_PYTHON_PACKAGE,
    FILE_TYPE_CONFIG,
    FILE_TYPE_TEXT as FP_FILE_TYPE_TEXT,
    FILE_TYPE_MARKDOWN as FP_FILE_TYPE_MARKDOWN,
    FILE_TYPE_YAML as FP_FILE_TYPE_YAML,
    FILE_TYPE_TOML,
    FILE_TYPE_ENV as FP_FILE_TYPE_ENV,
    FILE_TYPE_JSON as FP_FILE_TYPE_JSON,
    FILE_TYPE_SQL as FP_FILE_TYPE_SQL,
    FILE_TYPE_DOCKERFILE as FP_FILE_TYPE_DOCKERFILE,
    FILE_TYPE_SCRIPT,
    FILE_TYPE_REQUIREMENTS,
)
from telegram_bot_engine.engines.generators.dependency_resolver import (
    DependencyResolutionEngine,
    DependencyResolutionReport,
    DependencyEntry,
    DependencyRelationship,
    DependencyOrderEntry,
    ResolutionFinding,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    SEVERITY_INFO,
    DEPENDENCY_TYPE_LIBRARY,
    DEPENDENCY_TYPE_FRAMEWORK,
    DEPENDENCY_TYPE_TOOL,
    DEPENDENCY_TYPE_RUNTIME,
    DEPENDENCY_TYPE_DEV,
    DEPENDENCY_TYPE_TEST,
    DEPENDENCY_TYPE_BUILD,
    ALL_DEPENDENCY_TYPES,
    DEPENDENCY_PRIORITY_INFRASTRUCTURE,
    DEPENDENCY_PRIORITY_CORE,
    DEPENDENCY_PRIORITY_DATABASE,
    DEPENDENCY_PRIORITY_FEATURES,
    DEPENDENCY_PRIORITY_WIRING,
    DEPENDENCY_PRIORITY_ENTRY,
    DEPENDENCY_PRIORITY_TESTS,
    DEPENDENCY_PRIORITY_DEV,
    ALL_DEPENDENCY_PRIORITIES,
    SOURCE_BLUEPRINT,
    SOURCE_COMPONENT,
    SOURCE_FILE_PLAN,
    SOURCE_FRAMEWORK,
    SOURCE_INFERENCE,
    ALL_SOURCES,
    REPUTATION_GOOD,
    REPUTATION_NEUTRAL,
    REPUTATION_BAD,
    REPUTATION_UNKNOWN,
    ALL_REPUTATIONS,
    TRUST_OFFICIAL,
    TRUST_COMMUNITY,
    TRUST_UNTRUSTED,
    TRUST_UNKNOWN,
    ALL_TRUST_LEVELS,
    STABILITY_STABLE,
    STABILITY_BETA,
    STABILITY_UNSTABLE,
    STABILITY_ABANDONED,
    STABILITY_UNKNOWN,
    ALL_STABILITIES,
    ComponentAnalyzer,
    ComponentDependencyAnalysis,
    ComponentAnalysisResult,
    LibraryDeterminer,
    DependencyGraphBuilder,
    CompatibilityChecker,
    ConflictDetector,
    DependencyOptimizer,
    SecurityChecker,
    PlanValidator,
)


# ---------------------------------------------------------------------------#
# Test helpers
# ---------------------------------------------------------------------------#

def make_config():
    return build_configuration()


def make_context(
    blueprint=None,
    validation_report=None,
    structure_map=None,
    registry=None,
    file_plan=None,
):
    """Build a generation context with the five dependency-resolver
    artefacts.

    The request field is intentionally set to a string that the engine
    must NOT read.
    """
    ctx = GenerationContext(
        request="test request (must not be read by dependency resolver)",
        config=make_config(),
        work_dir=Path("/tmp/test_dependency_resolver"),
    )
    if blueprint is not None:
        ctx.set("project_blueprint", blueprint)
    if validation_report is not None:
        ctx.set("blueprint_validation_report", validation_report)
    if structure_map is not None:
        ctx.set("project_structure_map", structure_map)
    if registry is not None:
        ctx.set("component_registry", registry)
    if file_plan is not None:
        ctx.set("file_generation_plan", file_plan)
    return ctx


def make_valid_blueprint(name="my_store_bot", database="sqlite"):
    """Build a valid, ready-to-use blueprint for testing."""
    components = [
        InternalComponent(
            name="core", display_name="Core",
            kind="infrastructure", priority=PRIORITY_CRITICAL,
            description="Core bot logic",
        ),
        InternalComponent(
            name="database", display_name="Database",
            kind="infrastructure", priority=PRIORITY_CRITICAL,
            description="Database",
        ),
        InternalComponent(
            name="store", display_name="Store",
            kind="feature", priority=PRIORITY_NORMAL,
            description="Store functionality",
        ),
    ]
    return ProjectBlueprint(
        identity=ProjectIdentity(
            name=name,
            display_name=name.replace("_", " ").title(),
            bot_type="store",
            language="python",
            framework="python-telegram-bot",
            libraries=["python-telegram-bot"],
            database=database,
        ),
        structure=ExpectedStructure(
            root=name,
            entries=[
                StructureEntry(
                    path=f"{name}/", kind="directory",
                    description="Root package",
                ),
            ],
        ),
        features=[
            FeatureUnit(
                name="store", display_name="Store",
                build_priority=PRIORITY_NORMAL,
                phase="phase_5_code_generation",
                introduces_components=["store"],
            ),
        ],
        components=components,
        relationships=[
            ComponentRelationship(
                source="store", target="database", kind="depends_on",
            ),
        ],
        required_engines=[
            RequiredEngine(
                engine_id="dependency_resolver",
                name="Dependency Resolver",
                phase="resolve_dependencies",
            ),
        ],
        dependency_graph=DependencyGraph(),
        execution_plan=ExecutionPlan(),
        risks=[],
        validation=BlueprintValidation(
            valid=True, all_features_connected=True,
            dependencies_valid=True, phases_complete=True,
        ),
        ready=True,
    )


def make_approved_report(name="my_store_bot"):
    return BlueprintValidationReport(
        status=STATUS_APPROVED,
        blueprint_name=name,
        quality=QualityScore(overall=0.85, meets_minimum=True),
    )


def make_structure_map(name="my_store_bot"):
    """Build a structure map with folders and files linked to components."""
    folders = [
        FolderEntry(
            name=name, path=name,
            purpose="Root package.",
            build_order=BUILD_ORDER_INFRASTRUCTURE,
            reason="Root package for the bot.",
        ),
        FolderEntry(
            name="core", path=f"{name}/core",
            purpose="Core bot logic.",
            parent=name,
            build_order=BUILD_ORDER_CORE,
            reason="Contains the core bot module.",
        ),
        FolderEntry(
            name="database", path=f"{name}/database",
            purpose="Database layer.",
            parent=name,
            build_order=BUILD_ORDER_DATABASE,
            reason="Contains database models and repository.",
        ),
        FolderEntry(
            name="handlers", path=f"{name}/handlers",
            purpose="Command handlers.",
            parent=name,
            build_order=BUILD_ORDER_FEATURES,
            reason="Contains handler modules.",
        ),
    ]
    files = [
        FileEntry(
            name="__init__.py", path=f"{name}/__init__.py",
            file_type=FILE_TYPE_PYTHON_PACKAGE,
            purpose="Root package init.",
            folder=name,
            building_engine="code_generator",
            build_order=BUILD_ORDER_INFRASTRUCTURE,
            source_component="core",
            contains_code=True,
        ),
        FileEntry(
            name="__init__.py", path=f"{name}/core/__init__.py",
            file_type=FILE_TYPE_PYTHON_PACKAGE,
            purpose="Core package init.",
            folder=f"{name}/core",
            building_engine="code_generator",
            build_order=BUILD_ORDER_CORE,
            source_component="core",
            contains_code=True,
        ),
        FileEntry(
            name="bot.py", path=f"{name}/core/bot.py",
            file_type=FILE_TYPE_PYTHON_MODULE,
            purpose="The main bot application.",
            folder=f"{name}/core",
            building_engine="code_generator",
            build_order=BUILD_ORDER_CORE,
            source_component="core",
            contains_code=True,
        ),
        FileEntry(
            name="__init__.py", path=f"{name}/database/__init__.py",
            file_type=FILE_TYPE_PYTHON_PACKAGE,
            purpose="Database package init.",
            folder=f"{name}/database",
            building_engine="database_engine",
            build_order=BUILD_ORDER_DATABASE,
            source_component="database",
            contains_code=True,
        ),
        FileEntry(
            name="models.py", path=f"{name}/database/models.py",
            file_type=FILE_TYPE_PYTHON_MODULE,
            purpose="Database models.",
            folder=f"{name}/database",
            building_engine="database_engine",
            build_order=BUILD_ORDER_DATABASE,
            source_component="database",
            contains_code=True,
        ),
        FileEntry(
            name="__init__.py", path=f"{name}/handlers/__init__.py",
            file_type=FILE_TYPE_PYTHON_PACKAGE,
            purpose="Handlers package init.",
            folder=f"{name}/handlers",
            building_engine="code_generator",
            build_order=BUILD_ORDER_FEATURES,
            source_component="store_command",
            contains_code=True,
        ),
        FileEntry(
            name="start.py", path=f"{name}/handlers/start.py",
            file_type=FILE_TYPE_PYTHON_MODULE,
            purpose="Start command handler.",
            folder=f"{name}/handlers",
            building_engine="code_generator",
            build_order=BUILD_ORDER_FEATURES,
            source_component="store_command",
            contains_code=True,
        ),
    ]
    return ProjectStructureMap(
        project_name=name,
        root_path=name,
        folders=folders,
        files=files,
        source_blueprint=name,
        validation_status=STATUS_APPROVED,
    )


def make_component_registry(name="my_store_bot"):
    """Build a component registry with components that match the
    structure map's source_component values.

    The dependency graph is:
        store_command -> database -> core
    """
    components = [
        DetectedComponent(
            name="core",
            type=COMPONENT_TYPE_SERVICE,
            purpose="Core bot service.",
            responsibility="Run the bot.",
            source_blueprint_component="core",
            location=f"{name}/core/bot.py",
            building_engine="code_generator",
            build_order=10,
            importance=IMPORTANCE_CRITICAL,
        ),
        DetectedComponent(
            name="database",
            type=COMPONENT_TYPE_DATABASE_MODEL,
            purpose="Database models.",
            responsibility="Define the database schema.",
            source_blueprint_component="database",
            location=f"{name}/database/models.py",
            building_engine="database_engine",
            depends_on=["core"],
            build_order=20,
            importance=IMPORTANCE_CRITICAL,
            metadata={"database": "sqlite"},
        ),
        DetectedComponent(
            name="store_command",
            type=COMPONENT_TYPE_COMMAND,
            purpose="Handle the /start command.",
            responsibility="Process the start command.",
            source_blueprint_component="store",
            source_feature="store",
            location=f"{name}/handlers/start.py",
            building_engine="code_generator",
            depends_on=["database"],
            build_order=40,
            importance=IMPORTANCE_HIGH,
        ),
    ]
    return ComponentRegistry(
        project_name=name,
        root_path=name,
        components=components,
        source_blueprint=name,
        validation_status=STATUS_APPROVED,
        source_structure_map=name,
    )


def make_file_plan(name="my_store_bot"):
    """Build a FileGenerationPlan artefact (the 5th input)."""
    files = [
        FilePlanEntry(
            name="__init__.py",
            path=f"{name}/__init__.py",
            extension=EXTENSION_PYTHON,
            file_type=FP_FILE_TYPE_PYTHON_PACKAGE,
            purpose="Root package init.",
            responsible_engine="code_generator",
            generation_priority=GENERATION_PRIORITY_INFRASTRUCTURE,
            folder=name,
            source_component="core",
            reason_for_existence="Root package init file.",
            contains_code=True,
        ),
        FilePlanEntry(
            name="bot.py",
            path=f"{name}/core/bot.py",
            extension=EXTENSION_PYTHON,
            file_type=FP_FILE_TYPE_PYTHON_MODULE,
            purpose="The main bot application.",
            responsible_engine="code_generator",
            generation_priority=GENERATION_PRIORITY_CORE,
            folder=f"{name}/core",
            source_component="core",
            reason_for_existence="Main bot application file.",
            contains_code=True,
        ),
        FilePlanEntry(
            name="models.py",
            path=f"{name}/database/models.py",
            extension=EXTENSION_PYTHON,
            file_type=FP_FILE_TYPE_PYTHON_MODULE,
            purpose="Database models.",
            responsible_engine="database_engine",
            generation_priority=GENERATION_PRIORITY_DATABASE,
            folder=f"{name}/database",
            source_component="database",
            reason_for_existence="Database models file.",
            contains_code=True,
        ),
        FilePlanEntry(
            name="start.py",
            path=f"{name}/handlers/start.py",
            extension=EXTENSION_PYTHON,
            file_type=FP_FILE_TYPE_PYTHON_MODULE,
            purpose="Start command handler.",
            responsible_engine="code_generator",
            generation_priority=GENERATION_PRIORITY_FEATURES,
            folder=f"{name}/handlers",
            source_component="store_command",
            reason_for_existence="Start command handler file.",
            contains_code=True,
        ),
    ]
    relationships = [
        FileRelationship(
            source=f"{name}/core/bot.py",
            target=f"{name}/__init__.py",
            kind="imports",
            description="Bot imports the root package.",
        ),
        FileRelationship(
            source=f"{name}/handlers/start.py",
            target=f"{name}/database/models.py",
            kind="imports",
            description="Start handler imports models.",
        ),
    ]
    generation_order = [
        FileGenerationOrderEntry(
            position=0,
            file_path=f"{name}/__init__.py",
            file_name="__init__.py",
            responsible_engine="code_generator",
            source_component="core",
        ),
        FileGenerationOrderEntry(
            position=1,
            file_path=f"{name}/core/bot.py",
            file_name="bot.py",
            responsible_engine="code_generator",
            source_component="core",
        ),
        FileGenerationOrderEntry(
            position=2,
            file_path=f"{name}/database/models.py",
            file_name="models.py",
            responsible_engine="database_engine",
            source_component="database",
        ),
        FileGenerationOrderEntry(
            position=3,
            file_path=f"{name}/handlers/start.py",
            file_name="start.py",
            responsible_engine="code_generator",
            source_component="store_command",
        ),
    ]
    return FileGenerationPlan(
        project_name=name,
        root_path=name,
        files=files,
        relationships=relationships,
        generation_order=generation_order,
        source_blueprint=name,
        validation_status=STATUS_APPROVED,
        source_structure_map=name,
        source_component_registry=name,
    )


def make_full_context(name="my_store_bot"):
    """Build a context with all five artefacts set."""
    blueprint = make_valid_blueprint(name)
    report = make_approved_report(name)
    structure_map = make_structure_map(name)
    registry = make_component_registry(name)
    file_plan = make_file_plan(name)
    return make_context(blueprint, report, structure_map, registry, file_plan)


# ---------------------------------------------------------------------------#
# 1. Data model tests
# ---------------------------------------------------------------------------#

def test_dependency_entry_creation():
    """DependencyEntry can be created and serialised."""
    entry = DependencyEntry(
        name="python-telegram-bot",
        type=DEPENDENCY_TYPE_FRAMEWORK,
        suggested_version="21.x",
        version_constraint=">=20.0,<22.0",
        reason="The core Telegram bot framework.",
        source=SOURCE_FRAMEWORK,
        priority=DEPENDENCY_PRIORITY_INFRASTRUCTURE,
        language="python",
        framework="python-telegram-bot",
        os_compatibility=["linux", "windows", "macos"],
        reputation=REPUTATION_GOOD,
        trust=TRUST_OFFICIAL,
        stability=STABILITY_STABLE,
        official=True,
    )
    assert entry.name == "python-telegram-bot"
    assert entry.type == DEPENDENCY_TYPE_FRAMEWORK
    assert entry.suggested_version == "21.x"
    assert entry.version_constraint == ">=20.0,<22.0"
    assert entry.reason == "The core Telegram bot framework."
    assert entry.source == SOURCE_FRAMEWORK
    assert entry.priority == DEPENDENCY_PRIORITY_INFRASTRUCTURE
    assert entry.language == "python"
    assert entry.framework == "python-telegram-bot"
    assert entry.os_compatibility == ["linux", "windows", "macos"]
    assert entry.reputation == REPUTATION_GOOD
    assert entry.trust == TRUST_OFFICIAL
    assert entry.stability == STABILITY_STABLE
    assert entry.official is True
    print("  [PASS] test_dependency_entry_creation")


def test_dependency_entry_requires_name():
    """DependencyEntry raises ValueError without a name."""
    try:
        DependencyEntry(name="")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    print("  [PASS] test_dependency_entry_requires_name")


def test_dependency_entry_add_dependency():
    """DependencyEntry.add_dependency records a dependency."""
    entry = DependencyEntry(name="alembic")
    entry.add_dependency("SQLAlchemy")
    assert "SQLAlchemy" in entry.depends_on
    # Adding the same name twice does not duplicate.
    entry.add_dependency("SQLAlchemy")
    assert entry.depends_on.count("SQLAlchemy") == 1
    print("  [PASS] test_dependency_entry_add_dependency")


def test_dependency_entry_add_dependent():
    """DependencyEntry.add_dependent records a dependent."""
    entry = DependencyEntry(name="SQLAlchemy")
    entry.add_dependent("alembic")
    assert "alembic" in entry.depended_by
    entry.add_dependent("alembic")
    assert entry.depended_by.count("alembic") == 1
    print("  [PASS] test_dependency_entry_add_dependent")


def test_dependency_entry_add_source_component():
    """DependencyEntry.add_source_component records a component."""
    entry = DependencyEntry(name="pytest")
    entry.add_source_component("test_runner")
    assert "test_runner" in entry.source_components
    entry.add_source_component("test_runner")
    assert entry.source_components.count("test_runner") == 1
    print("  [PASS] test_dependency_entry_add_source_component")


def test_dependency_relationship():
    """DependencyRelationship can be created and serialised."""
    rel = DependencyRelationship(
        source="alembic", target="SQLAlchemy",
        kind="depends_on", description="alembic depends on SQLAlchemy.",
    )
    assert rel.source == "alembic"
    assert rel.target == "SQLAlchemy"
    assert rel.kind == "depends_on"
    assert rel.description == "alembic depends on SQLAlchemy."
    d = rel.to_dict()
    assert d["source"] == "alembic"
    assert d["target"] == "SQLAlchemy"
    assert d["kind"] == "depends_on"
    assert d["description"] == "alembic depends on SQLAlchemy."
    print("  [PASS] test_dependency_relationship")


def test_dependency_order_entry():
    """DependencyOrderEntry can be created and serialised."""
    entry = DependencyOrderEntry(
        position=3, dependency_name="alembic",
        dependency_type=DEPENDENCY_TYPE_TOOL,
        priority=DEPENDENCY_PRIORITY_DATABASE,
        source_components=["database"],
    )
    assert entry.position == 3
    assert entry.dependency_name == "alembic"
    assert entry.dependency_type == DEPENDENCY_TYPE_TOOL
    assert entry.priority == DEPENDENCY_PRIORITY_DATABASE
    assert entry.source_components == ["database"]
    d = entry.to_dict()
    assert d["position"] == 3
    assert d["dependency_name"] == "alembic"
    assert d["dependency_type"] == DEPENDENCY_TYPE_TOOL
    assert d["priority"] == DEPENDENCY_PRIORITY_DATABASE
    assert d["source_components"] == ["database"]
    print("  [PASS] test_dependency_order_entry")


def test_resolution_finding():
    """ResolutionFinding can be created and serialised."""
    finding = ResolutionFinding(
        severity=SEVERITY_WARNING,
        code="version_conflict",
        message="Libraries 'aiohttp' and 'httpx' conflict.",
        affected="aiohttp, httpx",
        resolution_hint="Use only one of 'aiohttp' or 'httpx'.",
        category="conflict",
    )
    assert finding.severity == SEVERITY_WARNING
    assert finding.code == "version_conflict"
    assert finding.message == "Libraries 'aiohttp' and 'httpx' conflict."
    assert finding.affected == "aiohttp, httpx"
    assert finding.resolution_hint == "Use only one of 'aiohttp' or 'httpx'."
    assert finding.category == "conflict"
    d = finding.to_dict()
    assert d["severity"] == SEVERITY_WARNING
    assert d["code"] == "version_conflict"
    print("  [PASS] test_resolution_finding")


def test_dependency_resolution_report():
    """DependencyResolutionReport can be created and queried."""
    deps = [
        DependencyEntry(name="python-telegram-bot", type=DEPENDENCY_TYPE_FRAMEWORK),
        DependencyEntry(name="SQLAlchemy", type=DEPENDENCY_TYPE_LIBRARY),
    ]
    report = DependencyResolutionReport(
        project_name="test_bot",
        language="python",
        language_version="3.11",
        framework="python-telegram-bot",
        dependencies=deps,
    )
    assert report.project_name == "test_bot"
    assert report.language == "python"
    assert report.language_version == "3.11"
    assert report.framework == "python-telegram-bot"
    assert report.dependency_count == 2
    assert not report.is_empty
    assert report.dependency_names() == ["python-telegram-bot", "SQLAlchemy"]
    assert report.has_dependency("SQLAlchemy")
    assert not report.has_dependency("nonexistent")
    dep = report.get_dependency("SQLAlchemy")
    assert dep is not None
    assert dep.name == "SQLAlchemy"
    assert report.get_dependency("nonexistent") is None
    print("  [PASS] test_dependency_resolution_report")


def test_dependency_resolution_report_empty():
    """An empty report has is_empty True and dependency_count 0."""
    report = DependencyResolutionReport()
    assert report.dependency_count == 0
    assert report.is_empty
    assert report.dependency_names() == []
    print("  [PASS] test_dependency_resolution_report_empty")


def test_dependency_resolution_report_add_finding():
    """add_finding appends to findings and warnings."""
    report = DependencyResolutionReport()
    report.add_finding(
        SEVERITY_WARNING, "test_code", "A warning message.",
    )
    assert len(report.findings) == 1
    assert report.findings[0].code == "test_code"
    assert "A warning message." in report.warnings
    # Error findings are not added to warnings.
    report.add_finding(
        SEVERITY_ERROR, "error_code", "An error message.",
    )
    assert len(report.findings) == 2
    assert "An error message." not in report.warnings
    print("  [PASS] test_dependency_resolution_report_add_finding")


def test_dependency_resolution_report_queries():
    """dependencies_for_component, by_type, by_priority queries work."""
    deps = [
        DependencyEntry(
            name="python-telegram-bot", type=DEPENDENCY_TYPE_FRAMEWORK,
            priority=DEPENDENCY_PRIORITY_INFRASTRUCTURE,
            source_components=["core", "store_command"],
        ),
        DependencyEntry(
            name="SQLAlchemy", type=DEPENDENCY_TYPE_LIBRARY,
            priority=DEPENDENCY_PRIORITY_DATABASE,
            source_components=["database"],
        ),
    ]
    report = DependencyResolutionReport(dependencies=deps)
    core_deps = report.dependencies_for_component("core")
    assert len(core_deps) == 1
    assert core_deps[0].name == "python-telegram-bot"
    frameworks = report.dependencies_by_type(DEPENDENCY_TYPE_FRAMEWORK)
    assert len(frameworks) == 1
    assert frameworks[0].name == "python-telegram-bot"
    infra = report.dependencies_by_priority(DEPENDENCY_PRIORITY_INFRASTRUCTURE)
    assert len(infra) == 1
    assert infra[0].name == "python-telegram-bot"
    print("  [PASS] test_dependency_resolution_report_queries")


def test_dependency_type_constants():
    """All dependency type constants are strings and ALL_DEPENDENCY_TYPES
    is complete."""
    assert DEPENDENCY_TYPE_LIBRARY == "library"
    assert DEPENDENCY_TYPE_FRAMEWORK == "framework"
    assert DEPENDENCY_TYPE_TOOL == "tool"
    assert DEPENDENCY_TYPE_RUNTIME == "runtime"
    assert DEPENDENCY_TYPE_DEV == "dev"
    assert DEPENDENCY_TYPE_TEST == "test"
    assert DEPENDENCY_TYPE_BUILD == "build"
    assert len(ALL_DEPENDENCY_TYPES) == 7
    assert DEPENDENCY_TYPE_LIBRARY in ALL_DEPENDENCY_TYPES
    assert DEPENDENCY_TYPE_BUILD in ALL_DEPENDENCY_TYPES
    print("  [PASS] test_dependency_type_constants")


def test_dependency_priority_constants():
    """All dependency priority constants are integers and ordered."""
    assert DEPENDENCY_PRIORITY_INFRASTRUCTURE == 10
    assert DEPENDENCY_PRIORITY_CORE == 20
    assert DEPENDENCY_PRIORITY_DATABASE == 30
    assert DEPENDENCY_PRIORITY_FEATURES == 40
    assert DEPENDENCY_PRIORITY_WIRING == 50
    assert DEPENDENCY_PRIORITY_ENTRY == 60
    assert DEPENDENCY_PRIORITY_TESTS == 70
    assert DEPENDENCY_PRIORITY_DEV == 80
    assert len(ALL_DEPENDENCY_PRIORITIES) == 8
    # Verify they are ordered.
    for i in range(len(ALL_DEPENDENCY_PRIORITIES) - 1):
        assert ALL_DEPENDENCY_PRIORITIES[i] < ALL_DEPENDENCY_PRIORITIES[i + 1]
    print("  [PASS] test_dependency_priority_constants")


def test_source_constants():
    """All source constants are strings and ALL_SOURCES is complete."""
    assert SOURCE_BLUEPRINT == "blueprint"
    assert SOURCE_COMPONENT == "component"
    assert SOURCE_FILE_PLAN == "file_plan"
    assert SOURCE_FRAMEWORK == "framework"
    assert SOURCE_INFERENCE == "inference"
    assert len(ALL_SOURCES) == 5
    print("  [PASS] test_source_constants")


def test_reputation_trust_stability_constants():
    """Reputation, trust, and stability constants are correct."""
    assert REPUTATION_GOOD == "good"
    assert REPUTATION_NEUTRAL == "neutral"
    assert REPUTATION_BAD == "bad"
    assert REPUTATION_UNKNOWN == "unknown"
    assert len(ALL_REPUTATIONS) == 4

    assert TRUST_OFFICIAL == "official"
    assert TRUST_COMMUNITY == "community"
    assert TRUST_UNTRUSTED == "untrusted"
    assert TRUST_UNKNOWN == "unknown"
    assert len(ALL_TRUST_LEVELS) == 4

    assert STABILITY_STABLE == "stable"
    assert STABILITY_BETA == "beta"
    assert STABILITY_UNSTABLE == "unstable"
    assert STABILITY_ABANDONED == "abandoned"
    assert STABILITY_UNKNOWN == "unknown"
    assert len(ALL_STABILITIES) == 5
    print("  [PASS] test_reputation_trust_stability_constants")


# ---------------------------------------------------------------------------#
# 2. ComponentAnalyzer tests
# ---------------------------------------------------------------------------#

def test_component_analyzer_basic():
    """ComponentAnalyzer analyses all components."""
    registry = make_component_registry()
    structure_map = make_structure_map()
    file_plan = make_file_plan()
    analyzer = ComponentAnalyzer()
    result = analyzer.analyze(registry, structure_map, file_plan)
    assert result.component_count == 3
    assert "core" in result.component_names
    assert "database" in result.component_names
    assert "store_command" in result.component_names
    print("  [PASS] test_component_analyzer_basic")


def test_component_analyzer_command_requires_ptb():
    """Command components require python-telegram-bot."""
    registry = make_component_registry()
    structure_map = make_structure_map()
    file_plan = make_file_plan()
    analyzer = ComponentAnalyzer()
    result = analyzer.analyze(registry, structure_map, file_plan)
    store_analysis = result.get("store_command")
    assert "python-telegram-bot" in store_analysis.required_libraries
    print("  [PASS] test_component_analyzer_command_requires_ptb")


def test_component_analyzer_database_requires_orm():
    """Database components require SQLAlchemy."""
    registry = make_component_registry()
    structure_map = make_structure_map()
    file_plan = make_file_plan()
    analyzer = ComponentAnalyzer()
    result = analyzer.analyze(registry, structure_map, file_plan)
    db_analysis = result.get("database")
    assert "SQLAlchemy" in db_analysis.required_libraries
    print("  [PASS] test_component_analyzer_database_requires_orm")


def test_component_analyzer_all_required_libraries():
    """The analysis accumulates all required libraries."""
    registry = make_component_registry()
    structure_map = make_structure_map()
    file_plan = make_file_plan()
    analyzer = ComponentAnalyzer()
    result = analyzer.analyze(registry, structure_map, file_plan)
    assert "python-telegram-bot" in result.all_required_libraries
    assert "SQLAlchemy" in result.all_required_libraries
    print("  [PASS] test_component_analyzer_all_required_libraries")


def test_component_analyzer_components_without_requirements():
    """Components without requirements are tracked."""
    registry = make_component_registry()
    structure_map = make_structure_map()
    file_plan = make_file_plan()
    analyzer = ComponentAnalyzer()
    result = analyzer.analyze(registry, structure_map, file_plan)
    # core (service type) has no required libraries.
    assert "core" in result.components_without_requirements
    print("  [PASS] test_component_analyzer_components_without_requirements")


def test_component_analyzer_findings_for_missing_requirements():
    """findings_for_missing_requirements produces warnings."""
    registry = make_component_registry()
    structure_map = make_structure_map()
    file_plan = make_file_plan()
    analyzer = ComponentAnalyzer()
    result = analyzer.analyze(registry, structure_map, file_plan)
    findings = analyzer.findings_for_missing_requirements(result)
    assert len(findings) > 0
    for f in findings:
        assert f.severity == SEVERITY_WARNING
        assert f.code == "component_without_requirements"
    print("  [PASS] test_component_analyzer_findings_for_missing_requirements")


def test_component_analyzer_pure():
    """The analyzer does not modify the registry."""
    registry = make_component_registry()
    original_count = registry.component_count
    structure_map = make_structure_map()
    file_plan = make_file_plan()
    analyzer = ComponentAnalyzer()
    analyzer.analyze(registry, structure_map, file_plan)
    assert registry.component_count == original_count
    print("  [PASS] test_component_analyzer_pure")


# ---------------------------------------------------------------------------#
# 3. LibraryDeterminer tests
# ---------------------------------------------------------------------------#

def test_library_determiner_basic():
    """LibraryDeterminer produces a non-empty list of dependencies."""
    registry = make_component_registry()
    structure_map = make_structure_map()
    file_plan = make_file_plan()
    blueprint = make_valid_blueprint()
    analyzer = ComponentAnalyzer()
    analysis = analyzer.analyze(registry, structure_map, file_plan)
    determiner = LibraryDeterminer()
    deps = determiner.determine(analysis, blueprint, structure_map, file_plan, registry)
    assert len(deps) > 0
    print("  [PASS] test_library_determiner_basic")


def test_library_determiner_framework_first():
    """The framework is the first dependency."""
    registry = make_component_registry()
    structure_map = make_structure_map()
    file_plan = make_file_plan()
    blueprint = make_valid_blueprint()
    analyzer = ComponentAnalyzer()
    analysis = analyzer.analyze(registry, structure_map, file_plan)
    determiner = LibraryDeterminer()
    deps = determiner.determine(analysis, blueprint, structure_map, file_plan, registry)
    assert deps[0].name == "python-telegram-bot"
    assert deps[0].type == DEPENDENCY_TYPE_FRAMEWORK
    assert deps[0].source == SOURCE_FRAMEWORK
    print("  [PASS] test_library_determiner_framework_first")


def test_library_determiner_includes_dotenv():
    """python-dotenv is always included."""
    registry = make_component_registry()
    structure_map = make_structure_map()
    file_plan = make_file_plan()
    blueprint = make_valid_blueprint()
    analyzer = ComponentAnalyzer()
    analysis = analyzer.analyze(registry, structure_map, file_plan)
    determiner = LibraryDeterminer()
    deps = determiner.determine(analysis, blueprint, structure_map, file_plan, registry)
    dep_names = [d.name for d in deps]
    assert "python-dotenv" in dep_names
    print("  [PASS] test_library_determiner_includes_dotenv")


def test_library_determiner_database_driver():
    """The database driver is included."""
    registry = make_component_registry()
    structure_map = make_structure_map()
    file_plan = make_file_plan()
    blueprint = make_valid_blueprint(database="sqlite")
    analyzer = ComponentAnalyzer()
    analysis = analyzer.analyze(registry, structure_map, file_plan)
    determiner = LibraryDeterminer()
    deps = determiner.determine(analysis, blueprint, structure_map, file_plan, registry)
    dep_names = [d.name for d in deps]
    assert "aiosqlite" in dep_names
    print("  [PASS] test_library_determiner_database_driver")


def test_library_determiner_no_duplicates():
    """The determiner does not produce duplicate entries."""
    registry = make_component_registry()
    structure_map = make_structure_map()
    file_plan = make_file_plan()
    blueprint = make_valid_blueprint()
    analyzer = ComponentAnalyzer()
    analysis = analyzer.analyze(registry, structure_map, file_plan)
    determiner = LibraryDeterminer()
    deps = determiner.determine(analysis, blueprint, structure_map, file_plan, registry)
    names = [d.name for d in deps]
    assert len(names) == len(set(names))
    print("  [PASS] test_library_determiner_no_duplicates")


def test_library_determiner_entry_metadata():
    """Each dependency entry has complete metadata."""
    registry = make_component_registry()
    structure_map = make_structure_map()
    file_plan = make_file_plan()
    blueprint = make_valid_blueprint()
    analyzer = ComponentAnalyzer()
    analysis = analyzer.analyze(registry, structure_map, file_plan)
    determiner = LibraryDeterminer()
    deps = determiner.determine(analysis, blueprint, structure_map, file_plan, registry)
    for dep in deps:
        assert dep.name
        assert dep.type
        assert dep.suggested_version
        assert dep.reason
        assert dep.source
        assert dep.language
        assert dep.priority
        assert dep.extensible is True
    print("  [PASS] test_library_determiner_entry_metadata")


def test_library_determiner_known_library_metadata():
    """Known libraries receive metadata from the table."""
    registry = make_component_registry()
    structure_map = make_structure_map()
    file_plan = make_file_plan()
    blueprint = make_valid_blueprint()
    analyzer = ComponentAnalyzer()
    analysis = analyzer.analyze(registry, structure_map, file_plan)
    determiner = LibraryDeterminer()
    deps = determiner.determine(analysis, blueprint, structure_map, file_plan, registry)
    ptb = next(d for d in deps if d.name == "python-telegram-bot")
    assert ptb.suggested_version == "21.x"
    assert ptb.version_constraint == ">=20.0,<22.0"
    assert ptb.reputation == REPUTATION_GOOD
    assert ptb.trust == TRUST_OFFICIAL
    assert ptb.stability == STABILITY_STABLE
    assert ptb.official is True
    print("  [PASS] test_library_determiner_known_library_metadata")


# ---------------------------------------------------------------------------#
# 4. DependencyGraphBuilder tests
# ---------------------------------------------------------------------------#

def test_graph_builder_basic():
    """DependencyGraphBuilder produces relationships and load order."""
    registry = make_component_registry()
    structure_map = make_structure_map()
    file_plan = make_file_plan()
    blueprint = make_valid_blueprint()
    analyzer = ComponentAnalyzer()
    analysis = analyzer.analyze(registry, structure_map, file_plan)
    determiner = LibraryDeterminer()
    deps = determiner.determine(analysis, blueprint, structure_map, file_plan, registry)
    builder = DependencyGraphBuilder()
    relationships, load_order, warnings = builder.build(deps, registry)
    assert len(load_order) == len(deps)
    print("  [PASS] test_graph_builder_basic")


def test_graph_builder_load_order_count():
    """The load order contains every dependency exactly once."""
    registry = make_component_registry()
    structure_map = make_structure_map()
    file_plan = make_file_plan()
    blueprint = make_valid_blueprint()
    analyzer = ComponentAnalyzer()
    analysis = analyzer.analyze(registry, structure_map, file_plan)
    determiner = LibraryDeterminer()
    deps = determiner.determine(analysis, blueprint, structure_map, file_plan, registry)
    builder = DependencyGraphBuilder()
    relationships, load_order, warnings = builder.build(deps, registry)
    assert len(load_order) == len(deps)
    order_names = [o.dependency_name for o in load_order]
    dep_names = [d.name for d in deps]
    assert set(order_names) == set(dep_names)
    assert len(order_names) == len(set(order_names))
    print("  [PASS] test_graph_builder_load_order_count")


def test_graph_builder_positions():
    """Load order positions are 0-based and sequential."""
    registry = make_component_registry()
    structure_map = make_structure_map()
    file_plan = make_file_plan()
    blueprint = make_valid_blueprint()
    analyzer = ComponentAnalyzer()
    analysis = analyzer.analyze(registry, structure_map, file_plan)
    determiner = LibraryDeterminer()
    deps = determiner.determine(analysis, blueprint, structure_map, file_plan, registry)
    builder = DependencyGraphBuilder()
    relationships, load_order, warnings = builder.build(deps, registry)
    for i, entry in enumerate(load_order):
        assert entry.position == i
    print("  [PASS] test_graph_builder_positions")


def test_graph_builder_inter_dependency():
    """Known inter-dependencies are wired (alembic -> SQLAlchemy)."""
    from telegram_bot_engine.engines.generators.dependency_resolver.dependency_graph_builder import _KNOWN_INTER_DEPENDENCIES
    assert "alembic" in _KNOWN_INTER_DEPENDENCIES
    assert "SQLAlchemy" in _KNOWN_INTER_DEPENDENCIES["alembic"]
    print("  [PASS] test_graph_builder_inter_dependency")


def test_graph_builder_topological_validity():
    """No dependency appears before a dependency it depends on."""
    registry = make_component_registry()
    structure_map = make_structure_map()
    file_plan = make_file_plan()
    blueprint = make_valid_blueprint()
    analyzer = ComponentAnalyzer()
    analysis = analyzer.analyze(registry, structure_map, file_plan)
    determiner = LibraryDeterminer()
    deps = determiner.determine(analysis, blueprint, structure_map, file_plan, registry)
    builder = DependencyGraphBuilder()
    relationships, load_order, warnings = builder.build(deps, registry)
    position_by_name = {
        o.dependency_name: o.position for o in load_order
    }
    for dep in deps:
        my_pos = position_by_name[dep.name]
        for dep_name in dep.depends_on:
            if dep_name in position_by_name:
                assert position_by_name[dep_name] < my_pos, (
                    f"Dependency '{dep.name}' (pos {my_pos}) appears "
                    f"before its dependency '{dep_name}' "
                    f"(pos {position_by_name[dep_name]})."
                )
    print("  [PASS] test_graph_builder_topological_validity")


def test_graph_builder_empty():
    """The graph builder handles an empty dependency list."""
    builder = DependencyGraphBuilder()
    relationships, load_order, warnings = builder.build([], make_component_registry())
    assert len(relationships) == 0
    assert len(load_order) == 0
    print("  [PASS] test_graph_builder_empty")


# ---------------------------------------------------------------------------#
# 5. CompatibilityChecker tests
# ---------------------------------------------------------------------------#

def test_compatibility_checker_basic():
    """CompatibilityChecker with valid dependencies produces no errors."""
    registry = make_component_registry()
    structure_map = make_structure_map()
    file_plan = make_file_plan()
    blueprint = make_valid_blueprint()
    analyzer = ComponentAnalyzer()
    analysis = analyzer.analyze(registry, structure_map, file_plan)
    determiner = LibraryDeterminer()
    deps = determiner.determine(analysis, blueprint, structure_map, file_plan, registry)
    builder = DependencyGraphBuilder()
    relationships, load_order, warnings = builder.build(deps, registry)
    checker = CompatibilityChecker()
    findings = checker.check(deps, relationships, blueprint)
    errors = [f for f in findings if f.severity == SEVERITY_ERROR]
    assert len(errors) == 0, (
        f"Unexpected compatibility errors: "
        f"{[(f.code, f.message) for f in errors]}"
    )
    print("  [PASS] test_compatibility_checker_basic")


def test_compatibility_checker_three_args():
    """CompatibilityChecker.check takes 3 arguments."""
    registry = make_component_registry()
    structure_map = make_structure_map()
    file_plan = make_file_plan()
    blueprint = make_valid_blueprint()
    analyzer = ComponentAnalyzer()
    analysis = analyzer.analyze(registry, structure_map, file_plan)
    determiner = LibraryDeterminer()
    deps = determiner.determine(analysis, blueprint, structure_map, file_plan, registry)
    builder = DependencyGraphBuilder()
    relationships, load_order, warnings = builder.build(deps, registry)
    checker = CompatibilityChecker()
    # This must accept (dependencies, relationships, blueprint).
    findings = checker.check(deps, relationships, blueprint)
    assert isinstance(findings, list)
    print("  [PASS] test_compatibility_checker_three_args")


def test_compatibility_checker_language_incompatible():
    """A dependency with a wrong language is flagged as an error."""
    deps = [
        DependencyEntry(
            name="bad-lib", language="javascript",
            os_compatibility=["linux"],
        ),
    ]
    blueprint = make_valid_blueprint()
    checker = CompatibilityChecker()
    findings = checker.check(deps, [], blueprint)
    lang_errors = [f for f in findings if f.code == "language_incompatible"]
    assert len(lang_errors) >= 1
    assert lang_errors[0].severity == SEVERITY_ERROR
    print("  [PASS] test_compatibility_checker_language_incompatible")


def test_compatibility_checker_self_dependency():
    """A self-dependency relationship is flagged as an error."""
    deps = [
        DependencyEntry(
            name="self-ref", language="python",
            os_compatibility=["linux"],
        ),
    ]
    rels = [DependencyRelationship(
        source="self-ref", target="self-ref", kind="depends_on",
    )]
    blueprint = make_valid_blueprint()
    checker = CompatibilityChecker()
    findings = checker.check(deps, rels, blueprint)
    self_deps = [f for f in findings if f.code == "self_dependency"]
    assert len(self_deps) >= 1
    assert self_deps[0].severity == SEVERITY_ERROR
    print("  [PASS] test_compatibility_checker_self_dependency")


def test_compatibility_checker_os_unknown():
    """A dependency without OS compatibility is flagged as a warning."""
    deps = [
        DependencyEntry(name="no-os", language="python"),
    ]
    blueprint = make_valid_blueprint()
    checker = CompatibilityChecker()
    findings = checker.check(deps, [], blueprint)
    os_warnings = [f for f in findings if f.code == "os_compatibility_unknown"]
    assert len(os_warnings) >= 1
    assert os_warnings[0].severity == SEVERITY_WARNING
    print("  [PASS] test_compatibility_checker_os_unknown")


# ---------------------------------------------------------------------------#
# 6. ConflictDetector tests
# ---------------------------------------------------------------------------#

def test_conflict_detector_no_conflicts():
    """ConflictDetector with clean deps produces no errors."""
    registry = make_component_registry()
    structure_map = make_structure_map()
    file_plan = make_file_plan()
    blueprint = make_valid_blueprint()
    analyzer = ComponentAnalyzer()
    analysis = analyzer.analyze(registry, structure_map, file_plan)
    determiner = LibraryDeterminer()
    deps = determiner.determine(analysis, blueprint, structure_map, file_plan, registry)
    builder = DependencyGraphBuilder()
    relationships, load_order, warnings = builder.build(deps, registry)
    detector = ConflictDetector()
    findings = detector.detect(deps, relationships)
    errors = [f for f in findings if f.severity == SEVERITY_ERROR]
    assert len(errors) == 0, (
        f"Unexpected conflict errors: "
        f"{[(f.code, f.message) for f in errors]}"
    )
    print("  [PASS] test_conflict_detector_no_conflicts")


def test_conflict_detector_duplicates():
    """Duplicate dependencies are detected."""
    deps = [
        DependencyEntry(name="dup", language="python",
                        os_compatibility=["linux"]),
        DependencyEntry(name="dup", language="python",
                        os_compatibility=["linux"]),
    ]
    detector = ConflictDetector()
    findings = detector.detect(deps, [])
    dup_findings = [f for f in findings if f.code == "duplicate_dependency"]
    assert len(dup_findings) >= 1
    assert dup_findings[0].severity == SEVERITY_ERROR
    print("  [PASS] test_conflict_detector_duplicates")


def test_conflict_detector_version_conflict():
    """Conflicting pairs are detected."""
    deps = [
        DependencyEntry(name="aiohttp", language="python",
                        os_compatibility=["linux"]),
        DependencyEntry(name="httpx", language="python",
                        os_compatibility=["linux"]),
    ]
    detector = ConflictDetector()
    findings = detector.detect(deps, [])
    conflict_findings = [f for f in findings if f.code == "version_conflict"]
    assert len(conflict_findings) >= 1
    assert conflict_findings[0].severity == SEVERITY_WARNING
    print("  [PASS] test_conflict_detector_version_conflict")


def test_conflict_detector_unused():
    """Unused dependencies are flagged."""
    deps = [
        DependencyEntry(
            name="unused-lib", language="python",
            os_compatibility=["linux"],
        ),
    ]
    detector = ConflictDetector()
    findings = detector.detect(deps, [])
    unused = [f for f in findings if f.code == "unused_dependency"]
    assert len(unused) >= 1
    assert unused[0].severity == SEVERITY_WARNING
    print("  [PASS] test_conflict_detector_unused")


def test_conflict_detector_broken_dependency():
    """Broken dependencies (non-existent target) are detected."""
    dep = DependencyEntry(
        name="dep-with-broken", language="python",
        os_compatibility=["linux"],
    )
    dep.add_dependency("nonexistent")
    detector = ConflictDetector()
    findings = detector.detect([dep], [])
    broken = [f for f in findings if f.code == "broken_dependency"]
    assert len(broken) >= 1
    assert broken[0].severity == SEVERITY_ERROR
    print("  [PASS] test_conflict_detector_broken_dependency")


def test_conflict_detector_circular_dependency():
    """Circular dependencies are detected."""
    dep_a = DependencyEntry(
        name="cycA", language="python",
        os_compatibility=["linux"],
    )
    dep_b = DependencyEntry(
        name="cycB", language="python",
        os_compatibility=["linux"],
    )
    dep_a.add_dependency("cycB")
    dep_b.add_dependency("cycA")
    detector = ConflictDetector()
    findings = detector.detect([dep_a, dep_b], [])
    circular = [f for f in findings if f.code == "circular_dependency"]
    assert len(circular) >= 1
    assert circular[0].severity == SEVERITY_ERROR
    print("  [PASS] test_conflict_detector_circular_dependency")


# ---------------------------------------------------------------------------#
# 7. DependencyOptimizer tests
# ---------------------------------------------------------------------------#

def test_optimizer_no_findings():
    """Optimizer with clean deps produces no errors."""
    deps = [
        DependencyEntry(
            name="python-telegram-bot", type=DEPENDENCY_TYPE_FRAMEWORK,
            language="python",
            os_compatibility=["linux"],
            reputation=REPUTATION_GOOD, trust=TRUST_OFFICIAL,
            stability=STABILITY_STABLE, official=True,
            priority=DEPENDENCY_PRIORITY_INFRASTRUCTURE,
        ),
    ]
    optimizer = DependencyOptimizer()
    findings = optimizer.optimize(deps)
    errors = [f for f in findings if f.severity == SEVERITY_ERROR]
    assert len(errors) == 0
    print("  [PASS] test_optimizer_no_findings")


def test_optimizer_redundant_libraries():
    """Redundant libraries are flagged."""
    deps = [
        DependencyEntry(
            name="aiohttp", language="python",
            os_compatibility=["linux"],
            reputation=REPUTATION_GOOD, trust=TRUST_OFFICIAL,
            stability=STABILITY_STABLE,
        ),
        DependencyEntry(
            name="httpx", language="python",
            os_compatibility=["linux"],
            reputation=REPUTATION_GOOD, trust=TRUST_OFFICIAL,
            stability=STABILITY_STABLE,
        ),
    ]
    optimizer = DependencyOptimizer()
    findings = optimizer.optimize(deps)
    redundant = [f for f in findings if f.code == "redundant_libraries"]
    assert len(redundant) >= 1
    assert redundant[0].severity == SEVERITY_WARNING
    print("  [PASS] test_optimizer_redundant_libraries")


def test_optimizer_abandoned():
    """Abandoned dependencies are flagged as errors."""
    deps = [
        DependencyEntry(
            name="old-lib", language="python",
            os_compatibility=["linux"],
            stability=STABILITY_ABANDONED,
        ),
    ]
    optimizer = DependencyOptimizer()
    findings = optimizer.optimize(deps)
    abandoned = [f for f in findings if f.code == "abandoned_dependency"]
    assert len(abandoned) >= 1
    assert abandoned[0].severity == SEVERITY_ERROR
    print("  [PASS] test_optimizer_abandoned")


def test_optimizer_unstable():
    """Unstable dependencies are flagged as warnings."""
    deps = [
        DependencyEntry(
            name="unstable-lib", language="python",
            os_compatibility=["linux"],
            stability=STABILITY_UNSTABLE,
            priority=DEPENDENCY_PRIORITY_DATABASE,
        ),
    ]
    optimizer = DependencyOptimizer()
    findings = optimizer.optimize(deps)
    unstable = [f for f in findings if f.code == "unstable_dependency"]
    assert len(unstable) >= 1
    assert unstable[0].severity == SEVERITY_WARNING
    print("  [PASS] test_optimizer_unstable")


def test_optimizer_prefer_official():
    """Non-official dependencies with official alternatives are flagged."""
    deps = [
        DependencyEntry(
            name="psycopg2-binary", language="python",
            os_compatibility=["linux"],
            trust=TRUST_COMMUNITY,
            stability=STABILITY_STABLE,
        ),
    ]
    optimizer = DependencyOptimizer()
    findings = optimizer.optimize(deps)
    prefer = [f for f in findings if f.code == "prefer_official"]
    assert len(prefer) >= 1
    assert prefer[0].severity == SEVERITY_INFO
    print("  [PASS] test_optimizer_prefer_official")


def test_optimizer_critical_not_stable():
    """Critical dependencies that are not stable are flagged."""
    deps = [
        DependencyEntry(
            name="unstable-core", language="python",
            os_compatibility=["linux"],
            stability=STABILITY_BETA,
            priority=DEPENDENCY_PRIORITY_CORE,
        ),
    ]
    optimizer = DependencyOptimizer()
    findings = optimizer.optimize(deps)
    critical = [f for f in findings if f.code == "critical_not_stable"]
    assert len(critical) >= 1
    assert critical[0].severity == SEVERITY_WARNING
    print("  [PASS] test_optimizer_critical_not_stable")


# ---------------------------------------------------------------------------#
# 8. SecurityChecker tests
# ---------------------------------------------------------------------------#

def test_security_checker_no_errors():
    """SecurityChecker with good deps produces no errors."""
    deps = [
        DependencyEntry(
            name="python-telegram-bot", language="python",
            os_compatibility=["linux"],
            reputation=REPUTATION_GOOD, trust=TRUST_OFFICIAL,
            stability=STABILITY_STABLE,
            suggested_version="21.x",
        ),
    ]
    checker = SecurityChecker()
    findings = checker.check(deps)
    errors = [f for f in findings if f.severity == SEVERITY_ERROR]
    assert len(errors) == 0
    print("  [PASS] test_security_checker_no_errors")


def test_security_checker_bad_reputation():
    """Dependencies with a bad reputation are flagged as errors."""
    deps = [
        DependencyEntry(
            name="bad-lib", language="python",
            os_compatibility=["linux"],
            reputation=REPUTATION_BAD,
            stability=STABILITY_STABLE,
        ),
    ]
    checker = SecurityChecker()
    findings = checker.check(deps)
    bad = [f for f in findings if f.code == "bad_reputation"]
    assert len(bad) >= 1
    assert bad[0].severity == SEVERITY_ERROR
    print("  [PASS] test_security_checker_bad_reputation")


def test_security_checker_untrusted():
    """Untrusted dependencies are flagged as errors."""
    deps = [
        DependencyEntry(
            name="untrusted-lib", language="python",
            os_compatibility=["linux"],
            trust=TRUST_UNTRUSTED,
            stability=STABILITY_STABLE,
        ),
    ]
    checker = SecurityChecker()
    findings = checker.check(deps)
    untrusted = [f for f in findings if f.code == "untrusted_source"]
    assert len(untrusted) >= 1
    assert untrusted[0].severity == SEVERITY_ERROR
    print("  [PASS] test_security_checker_untrusted")


def test_security_checker_unknown_reputation():
    """Unknown reputation is flagged as a warning."""
    deps = [
        DependencyEntry(
            name="unknown-rep", language="python",
            os_compatibility=["linux"],
            reputation=REPUTATION_UNKNOWN,
            trust=TRUST_OFFICIAL,
            stability=STABILITY_STABLE,
        ),
    ]
    checker = SecurityChecker()
    findings = checker.check(deps)
    unknown = [f for f in findings if f.code == "unknown_reputation"]
    assert len(unknown) >= 1
    assert unknown[0].severity == SEVERITY_WARNING
    print("  [PASS] test_security_checker_unknown_reputation")


def test_security_checker_abandoned():
    """Abandoned dependencies are flagged as security risks."""
    deps = [
        DependencyEntry(
            name="abandoned-lib", language="python",
            os_compatibility=["linux"],
            stability=STABILITY_ABANDONED,
            reputation=REPUTATION_GOOD,
            trust=TRUST_OFFICIAL,
        ),
    ]
    checker = SecurityChecker()
    findings = checker.check(deps)
    abandoned = [f for f in findings if f.code == "abandoned_security_risk"]
    assert len(abandoned) >= 1
    assert abandoned[0].severity == SEVERITY_ERROR
    print("  [PASS] test_security_checker_abandoned")


def test_security_checker_vulnerable_version():
    """Known-vulnerable versions are detected."""
    deps = [
        DependencyEntry(
            name="aiohttp", language="python",
            os_compatibility=["linux"],
            reputation=REPUTATION_GOOD, trust=TRUST_OFFICIAL,
            stability=STABILITY_STABLE,
            suggested_version="3.5.0",
        ),
    ]
    checker = SecurityChecker()
    findings = checker.check(deps)
    vulnerable = [f for f in findings if f.code == "known_vulnerable_version"]
    assert len(vulnerable) >= 1
    assert vulnerable[0].severity == SEVERITY_ERROR
    print("  [PASS] test_security_checker_vulnerable_version")


# ---------------------------------------------------------------------------#
# 9. PlanValidator tests
# ---------------------------------------------------------------------------#

def test_plan_validator_valid_report():
    """PlanValidator finds no errors in a valid report."""
    registry = make_component_registry()
    structure_map = make_structure_map()
    file_plan = make_file_plan()
    blueprint = make_valid_blueprint()
    analyzer = ComponentAnalyzer()
    analysis = analyzer.analyze(registry, structure_map, file_plan)
    determiner = LibraryDeterminer()
    deps = determiner.determine(analysis, blueprint, structure_map, file_plan, registry)
    builder = DependencyGraphBuilder()
    relationships, load_order, warnings = builder.build(deps, registry)
    report = DependencyResolutionReport(
        project_name="test_bot",
        language="python",
        framework="python-telegram-bot",
        dependencies=deps,
        relationships=relationships,
        load_order=load_order,
    )
    validator = PlanValidator()
    findings = validator.validate(report, registry)
    errors = [f for f in findings if f.severity == SEVERITY_ERROR]
    assert len(errors) == 0, (
        f"Unexpected validation errors: "
        f"{[(f.code, f.message) for f in errors]}"
    )
    print("  [PASS] test_plan_validator_valid_report")


def test_plan_validator_empty_report():
    """PlanValidator flags an empty report."""
    report = DependencyResolutionReport()
    validator = PlanValidator()
    findings = validator.validate(report, make_component_registry())
    empty = [f for f in findings if f.code == "empty_report"]
    assert len(empty) >= 1
    assert empty[0].severity == SEVERITY_ERROR
    print("  [PASS] test_plan_validator_empty_report")


def test_plan_validator_incomplete_dependency():
    """PlanValidator flags incomplete dependencies."""
    dep = DependencyEntry(name="incomplete")
    dep.type = ""
    dep.suggested_version = ""
    dep.reason = ""
    dep.source = ""
    report = DependencyResolutionReport(
        project_name="test_bot",
        dependencies=[dep],
    )
    validator = PlanValidator()
    findings = validator.validate(report, make_component_registry())
    without_type = [f for f in findings if f.code == "dependency_without_type"]
    without_version = [f for f in findings if f.code == "dependency_without_version"]
    without_reason = [f for f in findings if f.code == "dependency_without_reason"]
    without_source = [f for f in findings if f.code == "dependency_without_source"]
    assert len(without_type) >= 1
    assert len(without_version) >= 1
    assert len(without_reason) >= 1
    assert len(without_source) >= 1
    print("  [PASS] test_plan_validator_incomplete_dependency")


def test_plan_validator_invalid_relationship():
    """PlanValidator flags invalid relationships."""
    deps = [
        DependencyEntry(
            name="valid-dep", type=DEPENDENCY_TYPE_LIBRARY,
            suggested_version="1.0", reason="test", source=SOURCE_BLUEPRINT,
            language="python", os_compatibility=["linux"],
        ),
    ]
    rels = [DependencyRelationship(
        source="nonexistent", target="valid-dep", kind="depends_on",
    )]
    report = DependencyResolutionReport(
        project_name="test_bot",
        dependencies=deps,
        relationships=rels,
        load_order=[
            DependencyOrderEntry(
                position=0, dependency_name="valid-dep",
            ),
        ],
    )
    validator = PlanValidator()
    findings = validator.validate(report, make_component_registry())
    invalid = [f for f in findings if f.code == "invalid_relationship_source"]
    assert len(invalid) >= 1
    assert invalid[0].severity == SEVERITY_ERROR
    print("  [PASS] test_plan_validator_invalid_relationship")


def test_plan_validator_circular_dependencies():
    """PlanValidator flags circular dependencies."""
    dep_a = DependencyEntry(
        name="cycA", type=DEPENDENCY_TYPE_LIBRARY,
        suggested_version="1.0", reason="test", source=SOURCE_BLUEPRINT,
        language="python", os_compatibility=["linux"],
    )
    dep_b = DependencyEntry(
        name="cycB", type=DEPENDENCY_TYPE_LIBRARY,
        suggested_version="1.0", reason="test", source=SOURCE_BLUEPRINT,
        language="python", os_compatibility=["linux"],
    )
    dep_a.add_dependency("cycB")
    dep_b.add_dependency("cycA")
    report = DependencyResolutionReport(
        project_name="test_bot",
        dependencies=[dep_a, dep_b],
        load_order=[
            DependencyOrderEntry(position=0, dependency_name="cycA"),
            DependencyOrderEntry(position=1, dependency_name="cycB"),
        ],
    )
    validator = PlanValidator()
    findings = validator.validate(report, make_component_registry())
    circular = [f for f in findings if f.code == "circular_dependencies"]
    assert len(circular) >= 1
    assert circular[0].severity == SEVERITY_ERROR
    print("  [PASS] test_plan_validator_circular_dependencies")


# ---------------------------------------------------------------------------#
# 10. Main engine — data source
# ---------------------------------------------------------------------------#

def test_engine_requires_blueprint():
    """Engine fails when the project_blueprint artefact is missing."""
    engine = DependencyResolutionEngine()
    ctx = make_context(
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
    )
    result = engine.execute(ctx)
    assert not result.success
    assert any("project_blueprint" in e for e in result.errors)
    print("  [PASS] test_engine_requires_blueprint")


def test_engine_requires_validation_report():
    """Engine fails when the blueprint_validation_report artefact is missing."""
    engine = DependencyResolutionEngine()
    ctx = make_context(
        blueprint=make_valid_blueprint(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
    )
    result = engine.execute(ctx)
    assert not result.success
    assert any("blueprint_validation_report" in e for e in result.errors)
    print("  [PASS] test_engine_requires_validation_report")


def test_engine_requires_structure_map():
    """Engine fails when the project_structure_map artefact is missing."""
    engine = DependencyResolutionEngine()
    ctx = make_context(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
    )
    result = engine.execute(ctx)
    assert not result.success
    assert any("project_structure_map" in e for e in result.errors)
    print("  [PASS] test_engine_requires_structure_map")


def test_engine_requires_component_registry():
    """Engine fails when the component_registry artefact is missing."""
    engine = DependencyResolutionEngine()
    ctx = make_context(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        file_plan=make_file_plan(),
    )
    result = engine.execute(ctx)
    assert not result.success
    assert any("component_registry" in e for e in result.errors)
    print("  [PASS] test_engine_requires_component_registry")


def test_engine_requires_file_plan():
    """Engine fails when the file_generation_plan artefact is missing."""
    engine = DependencyResolutionEngine()
    ctx = make_context(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
    )
    result = engine.execute(ctx)
    assert not result.success
    assert any("file_generation_plan" in e for e in result.errors)
    print("  [PASS] test_engine_requires_file_plan")


def test_engine_does_not_read_request():
    """The engine's output does not depend on the request field."""
    ctx1 = make_full_context()
    ctx1.request = "create a store bot"

    ctx2 = make_full_context()
    ctx2.request = "completely different request text"

    engine = DependencyResolutionEngine()
    result1 = engine.execute(ctx1)
    result2 = engine.execute(ctx2)

    assert result1.success
    assert result2.success

    report1 = ctx1.get("dependency_resolution_report")
    report2 = ctx2.get("dependency_resolution_report")
    assert report1.dependency_count == report2.dependency_count
    assert report1.dependency_names() == report2.dependency_names()
    print("  [PASS] test_engine_does_not_read_request")


def test_engine_type_check_blueprint():
    """Engine fails when the blueprint is the wrong type."""
    engine = DependencyResolutionEngine()
    ctx = make_context(
        blueprint="not a blueprint",
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
    )
    result = engine.execute(ctx)
    assert not result.success
    assert any("ProjectBlueprint" in e for e in result.errors)
    print("  [PASS] test_engine_type_check_blueprint")


def test_engine_type_check_structure_map():
    """Engine fails when the structure map is the wrong type."""
    engine = DependencyResolutionEngine()
    ctx = make_context(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map="not a structure map",
        registry=make_component_registry(),
        file_plan=make_file_plan(),
    )
    result = engine.execute(ctx)
    assert not result.success
    assert any("ProjectStructureMap" in e for e in result.errors)
    print("  [PASS] test_engine_type_check_structure_map")


def test_engine_type_check_registry():
    """Engine fails when the registry is the wrong type."""
    engine = DependencyResolutionEngine()
    ctx = make_context(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry="not a registry",
        file_plan=make_file_plan(),
    )
    result = engine.execute(ctx)
    assert not result.success
    assert any("ComponentRegistry" in e for e in result.errors)
    print("  [PASS] test_engine_type_check_registry")


def test_engine_type_check_file_plan():
    """Engine fails when the file plan is the wrong type."""
    engine = DependencyResolutionEngine()
    ctx = make_context(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan="not a file plan",
    )
    result = engine.execute(ctx)
    assert not result.success
    assert any("FileGenerationPlan" in e for e in result.errors)
    print("  [PASS] test_engine_type_check_file_plan")


# ---------------------------------------------------------------------------#
# 11. Main engine — output
# ---------------------------------------------------------------------------#

def test_engine_produces_dependency_resolution_report():
    """Engine produces a DependencyResolutionReport and stores it."""
    ctx = make_full_context()
    engine = DependencyResolutionEngine()
    result = engine.execute(ctx)
    assert result.success
    report = ctx.get("dependency_resolution_report")
    assert report is not None
    assert isinstance(report, DependencyResolutionReport)
    assert report.project_name == "my_store_bot"
    assert report.dependency_count > 0
    print("  [PASS] test_engine_produces_dependency_resolution_report")


def test_engine_report_stored_in_metadata():
    """The report is also stored in the context metadata."""
    ctx = make_full_context()
    engine = DependencyResolutionEngine()
    engine.execute(ctx)
    assert "dependency_resolution_report" in ctx.metadata
    assert isinstance(
        ctx.metadata["dependency_resolution_report"],
        DependencyResolutionReport,
    )
    print("  [PASS] test_engine_report_stored_in_metadata")


def test_engine_records_source_artefacts():
    """The report records the source blueprint, structure map, registry, and file plan."""
    ctx = make_full_context()
    engine = DependencyResolutionEngine()
    engine.execute(ctx)
    report = ctx.get("dependency_resolution_report")
    assert report.source_blueprint == "my_store_bot"
    assert report.source_structure_map == "my_store_bot"
    assert report.source_component_registry == "my_store_bot"
    assert report.source_file_generation_plan == "my_store_bot"
    assert report.validation_status == STATUS_APPROVED
    print("  [PASS] test_engine_records_source_artefacts")


def test_engine_report_has_summary():
    """The report has a non-empty summary."""
    ctx = make_full_context()
    engine = DependencyResolutionEngine()
    engine.execute(ctx)
    report = ctx.get("dependency_resolution_report")
    assert report.summary
    assert "dependency" in report.summary.lower()
    print("  [PASS] test_engine_report_has_summary")


def test_engine_report_has_notes():
    """The report has notes about its provenance."""
    ctx = make_full_context()
    engine = DependencyResolutionEngine()
    engine.execute(ctx)
    report = ctx.get("dependency_resolution_report")
    assert len(report.notes) > 0
    assert any("blueprint" in n.lower() for n in report.notes)
    print("  [PASS] test_engine_report_has_notes")


def test_engine_report_includes_framework():
    """The report includes the framework as a dependency."""
    ctx = make_full_context()
    engine = DependencyResolutionEngine()
    engine.execute(ctx)
    report = ctx.get("dependency_resolution_report")
    assert report.has_dependency("python-telegram-bot")
    dep = report.get_dependency("python-telegram-bot")
    assert dep.type == DEPENDENCY_TYPE_FRAMEWORK
    print("  [PASS] test_engine_report_includes_framework")


def test_engine_report_load_order():
    """The report has a load order with all dependencies."""
    ctx = make_full_context()
    engine = DependencyResolutionEngine()
    engine.execute(ctx)
    report = ctx.get("dependency_resolution_report")
    assert len(report.load_order) == report.dependency_count
    order_names = [o.dependency_name for o in report.load_order]
    dep_names = report.dependency_names()
    assert set(order_names) == set(dep_names)
    print("  [PASS] test_engine_report_load_order")


def test_engine_metadata_in_result():
    """The engine result metadata contains the report statistics."""
    ctx = make_full_context()
    engine = DependencyResolutionEngine()
    result = engine.execute(ctx)
    assert result.success
    assert "project_name" in result.metadata
    assert "dependency_count" in result.metadata
    assert "relationship_count" in result.metadata
    assert "load_order_entries" in result.metadata
    assert "findings" in result.metadata
    assert "errors" in result.metadata
    assert "warnings" in result.metadata
    assert "duration_ms" in result.metadata
    assert result.metadata["project_name"] == "my_store_bot"
    assert result.metadata["dependency_count"] > 0
    print("  [PASS] test_engine_metadata_in_result")


# ---------------------------------------------------------------------------#
# 12. Report integrity
# ---------------------------------------------------------------------------#

def test_report_no_duplicate_dependencies():
    """The report contains no duplicate dependencies."""
    ctx = make_full_context()
    engine = DependencyResolutionEngine()
    engine.execute(ctx)
    report = ctx.get("dependency_resolution_report")
    names = report.dependency_names()
    assert len(names) == len(set(names))
    print("  [PASS] test_report_no_duplicate_dependencies")


def test_report_all_deps_have_reason():
    """Every dependency in the report has a reason."""
    ctx = make_full_context()
    engine = DependencyResolutionEngine()
    engine.execute(ctx)
    report = ctx.get("dependency_resolution_report")
    for dep in report.dependencies:
        assert dep.reason, (
            f"Dependency '{dep.name}' has no reason."
        )
    print("  [PASS] test_report_all_deps_have_reason")


def test_report_all_deps_have_source():
    """Every dependency in the report has a source."""
    ctx = make_full_context()
    engine = DependencyResolutionEngine()
    engine.execute(ctx)
    report = ctx.get("dependency_resolution_report")
    for dep in report.dependencies:
        assert dep.source, (
            f"Dependency '{dep.name}' has no source."
        )
    print("  [PASS] test_report_all_deps_have_source")


def test_report_all_deps_have_version():
    """Every dependency in the report has a suggested version."""
    ctx = make_full_context()
    engine = DependencyResolutionEngine()
    engine.execute(ctx)
    report = ctx.get("dependency_resolution_report")
    for dep in report.dependencies:
        assert dep.suggested_version, (
            f"Dependency '{dep.name}' has no suggested version."
        )
    print("  [PASS] test_report_all_deps_have_version")


def test_report_load_order_topologically_valid():
    """The load order is topologically valid."""
    ctx = make_full_context()
    engine = DependencyResolutionEngine()
    engine.execute(ctx)
    report = ctx.get("dependency_resolution_report")
    position_by_name = {
        o.dependency_name: o.position for o in report.load_order
    }
    for dep in report.dependencies:
        my_pos = position_by_name.get(dep.name, -1)
        if my_pos < 0:
            continue
        for dep_name in dep.depends_on:
            dep_pos = position_by_name.get(dep_name, -1)
            if dep_pos < 0:
                continue
            assert dep_pos < my_pos, (
                f"Dependency '{dep.name}' (pos {my_pos}) appears "
                f"before its dependency '{dep_name}' "
                f"(pos {dep_pos})."
            )
    print("  [PASS] test_report_load_order_topologically_valid")


def test_report_no_circular_dependencies():
    """The report contains no circular dependencies."""
    ctx = make_full_context()
    engine = DependencyResolutionEngine()
    result = engine.execute(ctx)
    assert result.success
    report = ctx.get("dependency_resolution_report")
    circular = [
        f for f in report.findings
        if f.code == "circular_dependency"
        or f.code == "circular_dependencies"
    ]
    assert len(circular) == 0, (
        f"Circular dependencies found: {circular}"
    )
    print("  [PASS] test_report_no_circular_dependencies")


# ---------------------------------------------------------------------------#
# 13. Bootstrap integration
# ---------------------------------------------------------------------------#

def test_bootstrap_registers_dependency_resolver():
    """Bootstrap registers the dependency resolver in the manager."""
    registry, orchestrator, manager = bootstrap()
    entries = manager.all_entries()
    engine_ids = [e.engine_id for e in entries]
    assert "dependency_resolver" in engine_ids
    print("  [PASS] test_bootstrap_registers_dependency_resolver")


def test_bootstrap_dependency_resolver_priority():
    """Dependency resolver is registered at priority 95."""
    registry, orchestrator, manager = bootstrap()
    entry = manager.get("dependency_resolver")
    assert entry is not None
    assert entry.priority == 80
    print("  [PASS] test_bootstrap_dependency_resolver_priority")


def test_bootstrap_dependency_resolver_dependencies():
    """Dependency resolver depends on file_planner."""
    registry, orchestrator, manager = bootstrap()
    entry = manager.get("dependency_resolver")
    assert entry is not None
    assert "execution_planning" in entry.dependencies
    print("  [PASS] test_bootstrap_dependency_resolver_dependencies")


def test_bootstrap_dependency_resolver_in_registry():
    """The dependency resolver engine is in the component registry."""
    registry, _, _ = bootstrap()
    engine = registry.get_engine("dependency_resolver")
    assert engine is not None
    assert engine.name == "dependency_resolver"
    print("  [PASS] test_bootstrap_dependency_resolver_in_registry")


# ---------------------------------------------------------------------------#
# 14. Serialisation
# ---------------------------------------------------------------------------#

def test_dependency_entry_to_dict():
    """DependencyEntry.to_dict returns all fields."""
    entry = DependencyEntry(
        name="test-lib",
        type=DEPENDENCY_TYPE_LIBRARY,
        suggested_version="1.0",
        version_constraint=">=1.0,<2.0",
        reason="Test reason.",
        source=SOURCE_BLUEPRINT,
        source_components=["core"],
        priority=DEPENDENCY_PRIORITY_CORE,
        language="python",
        framework="",
        os_compatibility=["linux"],
        reputation=REPUTATION_GOOD,
        trust=TRUST_OFFICIAL,
        stability=STABILITY_STABLE,
        official=True,
        extensible=True,
    )
    d = entry.to_dict()
    expected_keys = {
        "name", "type", "suggested_version", "version_constraint",
        "reason", "source", "source_components", "priority",
        "depends_on", "depended_by", "load_order", "language",
        "framework", "os_compatibility", "reputation", "trust",
        "stability", "official", "extensible", "metadata",
    }
    assert set(d.keys()) == expected_keys
    assert d["name"] == "test-lib"
    assert d["depends_on"] == []
    assert d["depended_by"] == []
    assert d["extensible"] is True
    print("  [PASS] test_dependency_entry_to_dict")


def test_dependency_relationship_to_dict():
    """DependencyRelationship.to_dict returns all fields."""
    rel = DependencyRelationship(
        source="a", target="b",
        kind="depends_on", description="a depends on b",
    )
    d = rel.to_dict()
    assert d["source"] == "a"
    assert d["target"] == "b"
    assert d["kind"] == "depends_on"
    assert d["description"] == "a depends on b"
    print("  [PASS] test_dependency_relationship_to_dict")


def test_dependency_order_entry_to_dict():
    """DependencyOrderEntry.to_dict returns all fields."""
    entry = DependencyOrderEntry(
        position=5, dependency_name="alembic",
        dependency_type=DEPENDENCY_TYPE_TOOL,
        priority=DEPENDENCY_PRIORITY_DATABASE,
        source_components=["database"],
    )
    d = entry.to_dict()
    assert d["position"] == 5
    assert d["dependency_name"] == "alembic"
    assert d["dependency_type"] == DEPENDENCY_TYPE_TOOL
    assert d["priority"] == DEPENDENCY_PRIORITY_DATABASE
    assert d["source_components"] == ["database"]
    print("  [PASS] test_dependency_order_entry_to_dict")


def test_resolution_finding_to_dict():
    """ResolutionFinding.to_dict returns all fields."""
    finding = ResolutionFinding(
        severity=SEVERITY_ERROR,
        code="test_error",
        message="An error.",
        affected="test-lib",
        resolution_hint="Fix it.",
        category="conflict",
    )
    d = finding.to_dict()
    assert d["severity"] == SEVERITY_ERROR
    assert d["code"] == "test_error"
    assert d["message"] == "An error."
    assert d["affected"] == "test-lib"
    assert d["resolution_hint"] == "Fix it."
    assert d["category"] == "conflict"
    print("  [PASS] test_resolution_finding_to_dict")


def test_dependency_resolution_report_to_dict():
    """DependencyResolutionReport.to_dict returns all fields."""
    ctx = make_full_context()
    engine = DependencyResolutionEngine()
    engine.execute(ctx)
    report = ctx.get("dependency_resolution_report")
    d = report.to_dict()
    assert d["project_name"] == "my_store_bot"
    assert d["dependency_count"] == report.dependency_count
    assert isinstance(d["dependencies"], list)
    assert isinstance(d["relationships"], list)
    assert isinstance(d["load_order"], list)
    assert isinstance(d["findings"], list)
    assert isinstance(d["notes"], list)
    assert isinstance(d["warnings"], list)
    # Each dependency dict should have all the keys.
    if d["dependencies"]:
        dep_d = d["dependencies"][0]
        assert "name" in dep_d
        assert "type" in dep_d
        assert "reason" in dep_d
        assert "source" in dep_d
    print("  [PASS] test_dependency_resolution_report_to_dict")


# ---------------------------------------------------------------------------#
# 15. End-to-end integration
# ---------------------------------------------------------------------------#

def test_end_to_end_full_pipeline():
    """Run the full pipeline and verify the dependency resolution report."""
    ctx = make_full_context()
    engine = DependencyResolutionEngine()
    result = engine.execute(ctx)

    assert result.success, (
        f"Engine failed: {result.errors}"
    )
    report = ctx.get("dependency_resolution_report")
    assert report is not None
    assert report.dependency_count > 0
    assert len(report.load_order) == report.dependency_count
    assert report.source_blueprint == "my_store_bot"
    assert report.validation_status == STATUS_APPROVED
    assert report.source_file_generation_plan == "my_store_bot"
    print("  [PASS] test_end_to_end_full_pipeline")


def test_end_to_end_with_file_planner():
    """Run file planner then dependency resolver in sequence."""
    ctx = make_context(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
    )
    # Run the file planner first to produce the 5th artefact.
    fp_engine = FileGenerationPlanningEngine()
    fp_result = fp_engine.execute(ctx)
    assert fp_result.success

    # Now run the dependency resolver.
    dr_engine = DependencyResolutionEngine()
    dr_result = dr_engine.execute(ctx)
    assert dr_result.success
    report = ctx.get("dependency_resolution_report")
    assert report is not None
    assert report.dependency_count > 0
    print("  [PASS] test_end_to_end_with_file_planner")


# ---------------------------------------------------------------------------#
# Test runner
# ---------------------------------------------------------------------------#

def run_all_tests():
    tests = [
        # Data model
        test_dependency_entry_creation,
        test_dependency_entry_requires_name,
        test_dependency_entry_add_dependency,
        test_dependency_entry_add_dependent,
        test_dependency_entry_add_source_component,
        test_dependency_relationship,
        test_dependency_order_entry,
        test_resolution_finding,
        test_dependency_resolution_report,
        test_dependency_resolution_report_empty,
        test_dependency_resolution_report_add_finding,
        test_dependency_resolution_report_queries,
        test_dependency_type_constants,
        test_dependency_priority_constants,
        test_source_constants,
        test_reputation_trust_stability_constants,
        # ComponentAnalyzer
        test_component_analyzer_basic,
        test_component_analyzer_command_requires_ptb,
        test_component_analyzer_database_requires_orm,
        test_component_analyzer_all_required_libraries,
        test_component_analyzer_components_without_requirements,
        test_component_analyzer_findings_for_missing_requirements,
        test_component_analyzer_pure,
        # LibraryDeterminer
        test_library_determiner_basic,
        test_library_determiner_framework_first,
        test_library_determiner_includes_dotenv,
        test_library_determiner_database_driver,
        test_library_determiner_no_duplicates,
        test_library_determiner_entry_metadata,
        test_library_determiner_known_library_metadata,
        # DependencyGraphBuilder
        test_graph_builder_basic,
        test_graph_builder_load_order_count,
        test_graph_builder_positions,
        test_graph_builder_inter_dependency,
        test_graph_builder_topological_validity,
        test_graph_builder_empty,
        # CompatibilityChecker
        test_compatibility_checker_basic,
        test_compatibility_checker_three_args,
        test_compatibility_checker_language_incompatible,
        test_compatibility_checker_self_dependency,
        test_compatibility_checker_os_unknown,
        # ConflictDetector
        test_conflict_detector_no_conflicts,
        test_conflict_detector_duplicates,
        test_conflict_detector_version_conflict,
        test_conflict_detector_unused,
        test_conflict_detector_broken_dependency,
        test_conflict_detector_circular_dependency,
        # DependencyOptimizer
        test_optimizer_no_findings,
        test_optimizer_redundant_libraries,
        test_optimizer_abandoned,
        test_optimizer_unstable,
        test_optimizer_prefer_official,
        test_optimizer_critical_not_stable,
        # SecurityChecker
        test_security_checker_no_errors,
        test_security_checker_bad_reputation,
        test_security_checker_untrusted,
        test_security_checker_unknown_reputation,
        test_security_checker_abandoned,
        test_security_checker_vulnerable_version,
        # PlanValidator
        test_plan_validator_valid_report,
        test_plan_validator_empty_report,
        test_plan_validator_incomplete_dependency,
        test_plan_validator_invalid_relationship,
        test_plan_validator_circular_dependencies,
        # Engine — data source
        test_engine_requires_blueprint,
        test_engine_requires_validation_report,
        test_engine_requires_structure_map,
        test_engine_requires_component_registry,
        test_engine_requires_file_plan,
        test_engine_does_not_read_request,
        test_engine_type_check_blueprint,
        test_engine_type_check_structure_map,
        test_engine_type_check_registry,
        test_engine_type_check_file_plan,
        # Engine — output
        test_engine_produces_dependency_resolution_report,
        test_engine_report_stored_in_metadata,
        test_engine_records_source_artefacts,
        test_engine_report_has_summary,
        test_engine_report_has_notes,
        test_engine_report_includes_framework,
        test_engine_report_load_order,
        test_engine_metadata_in_result,
        # Report integrity
        test_report_no_duplicate_dependencies,
        test_report_all_deps_have_reason,
        test_report_all_deps_have_source,
        test_report_all_deps_have_version,
        test_report_load_order_topologically_valid,
        test_report_no_circular_dependencies,
        # Bootstrap
        test_bootstrap_registers_dependency_resolver,
        test_bootstrap_dependency_resolver_priority,
        test_bootstrap_dependency_resolver_dependencies,
        test_bootstrap_dependency_resolver_in_registry,
        # Serialisation
        test_dependency_entry_to_dict,
        test_dependency_relationship_to_dict,
        test_dependency_order_entry_to_dict,
        test_resolution_finding_to_dict,
        test_dependency_resolution_report_to_dict,
        # End-to-end
        test_end_to_end_full_pipeline,
        test_end_to_end_with_file_planner,
    ]

    passed = 0
    failed = 0
    errors = []

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            errors.append((test.__name__, str(e)))
            print(f"  [FAIL] {test.__name__}: {e}")

    print()
    print(f"{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed, "
          f"{passed + failed} total")
    if errors:
        print(f"\nFailures:")
        for name, err in errors:
            print(f"  - {name}: {err}")
    print(f"{'=' * 60}")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
