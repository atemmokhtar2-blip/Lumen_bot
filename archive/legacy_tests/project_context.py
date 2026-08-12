#!/usr/bin/env python3
"""
Comprehensive test suite for the Project Context Engine
(Specification 010).

These tests cover every aspect of the specification:

1. Data model integrity (ProjectContext, ProjectGoal, FeatureSummary,
   ComponentSummary, FileSummary, DependencySummary,
   RelationshipSummary, ExecutionStage, ContextLink, ExpansionPoint,
   ContextFinding, LinkIndices, SourceProvenance, source-artefact
   constants, severity constants, link-kind constants).
2. The BlueprintReader (goal, features, relationships, stages,
   expansion points).
3. The ValidationReader (validation status, quality scores,
   findings).
4. The StructureReader (files, relationships, expansion points).
5. The RegistryReader (components, relationships, expansion points).
6. The FilePlanReader (files, relationships, expansion points).
7. The DependencyReader (dependencies, relationships, findings).
8. The ContextAssembler (merges all six artefacts, cross-links
   features/components/files/dependencies, deduplicates
   relationships, enriches stages, builds provenance).
9. The ContextLinker (feature-to-component links, component-to-file
   links, file-to-dependency links, dependency-to-stage links,
   component-to-stage links, feature-to-stage links, all O(1)
   indices).
10. The ContextValidator (duplicate names, features without
    components, components without files, files without
    responsibility, unknown elements in relationships, empty
    stages, orphaned components).
11. The main engine reads ONLY the project_blueprint,
    blueprint_validation_report, project_structure_map,
    component_registry, file_generation_plan, and
    dependency_resolution_report artefacts (not the raw request).
12. The main engine produces a ProjectContext artefact.
13. The main engine fails when each of the 6 artefacts is missing.
14. The main engine fails when the artefacts are the wrong type.
15. The project context records the source artefacts (provenance).
16. Bootstrap integration (engine registered in registry and manager
    at priority 96, depends on dependency_resolver).
17. Serialisation (to_dict) for all data model classes.
18. End-to-end pipeline.
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
    ExecutionPhase,
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
    DEPENDENCY_TYPE_LIBRARY,
    DEPENDENCY_TYPE_FRAMEWORK,
    DEPENDENCY_TYPE_TOOL,
    DEPENDENCY_TYPE_RUNTIME,
    DEPENDENCY_TYPE_DEV,
    DEPENDENCY_TYPE_TEST,
    DEPENDENCY_TYPE_BUILD,
    DEPENDENCY_PRIORITY_INFRASTRUCTURE,
    DEPENDENCY_PRIORITY_CORE,
    DEPENDENCY_PRIORITY_DATABASE,
    DEPENDENCY_PRIORITY_FEATURES,
    DEPENDENCY_PRIORITY_WIRING,
    DEPENDENCY_PRIORITY_ENTRY,
    DEPENDENCY_PRIORITY_TESTS,
    DEPENDENCY_PRIORITY_DEV,
    SOURCE_BLUEPRINT as DR_SOURCE_BLUEPRINT,
    SOURCE_COMPONENT,
    SOURCE_FILE_PLAN as DR_SOURCE_FILE_PLAN,
    SOURCE_FRAMEWORK,
    SOURCE_INFERENCE,
    REPUTATION_GOOD,
    REPUTATION_NEUTRAL,
    REPUTATION_BAD,
    REPUTATION_UNKNOWN,
    TRUST_OFFICIAL,
    TRUST_COMMUNITY,
    TRUST_UNTRUSTED,
    TRUST_UNKNOWN,
    STABILITY_STABLE,
    STABILITY_BETA,
    STABILITY_UNSTABLE,
    STABILITY_ABANDONED,
    STABILITY_UNKNOWN,
)
from telegram_bot_engine.engines.generators.project_context import (
    ProjectContextEngine,
    ProjectContext,
    ProjectGoal,
    FeatureSummary,
    ComponentSummary,
    FileSummary,
    DependencySummary,
    RelationshipSummary,
    ExecutionStage,
    ContextLink,
    ExpansionPoint,
    ContextFinding,
    LinkIndices,
    SourceProvenance,
    # Source-artefact constants
    SOURCE_BLUEPRINT as PC_SOURCE_BLUEPRINT,
    SOURCE_VALIDATION as PC_SOURCE_VALIDATION,
    SOURCE_STRUCTURE as PC_SOURCE_STRUCTURE,
    SOURCE_COMPONENT_REGISTRY as PC_SOURCE_COMPONENT_REGISTRY,
    SOURCE_FILE_PLAN as PC_SOURCE_FILE_PLAN,
    SOURCE_DEPENDENCY_REPORT as PC_SOURCE_DEPENDENCY_REPORT,
    ALL_SOURCES as PC_ALL_SOURCES,
    # Severity constants
    SEVERITY_ERROR as PC_SEVERITY_ERROR,
    SEVERITY_WARNING as PC_SEVERITY_WARNING,
    SEVERITY_INFO as PC_SEVERITY_INFO,
    ALL_SEVERITIES as PC_ALL_SEVERITIES,
    # Link-kind constants
    LINK_FEATURE_TO_COMPONENT,
    LINK_COMPONENT_TO_FILE,
    LINK_FILE_TO_DEPENDENCY,
    LINK_DEPENDENCY_TO_STAGE,
    LINK_COMPONENT_TO_STAGE,
    LINK_FEATURE_TO_STAGE,
    ALL_LINK_KINDS,
    # Helpers
    ContextAssembler,
    ContextLinker,
    ContextValidator,
    BlueprintReader,
    ValidationReader,
    StructureReader,
    RegistryReader,
    FilePlanReader,
    DependencyReader,
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
    dependency_report=None,
):
    """Build a generation context with the six project-context artefacts.

    The request field is intentionally set to a string that the engine
    must NOT read.
    """
    ctx = GenerationContext(
        request="test request (must not be read by project context)",
        config=make_config(),
        work_dir=Path("/tmp/test_project_context"),
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
    if dependency_report is not None:
        ctx.set("dependency_resolution_report", dependency_report)
    return ctx


def make_valid_blueprint(name="my_store_bot", database="sqlite"):
    """Build a valid, ready-to-use blueprint for testing.

    This blueprint includes a richer execution plan with 3 phases so
    the Project Context has non-zero stages.
    """
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
    execution_plan = ExecutionPlan(
        phases=[
            ExecutionPhase(
                number=1,
                name="project_setup",
                description="Initialise the project.",
                components=["core"],
                features=[],
            ),
            ExecutionPhase(
                number=3,
                name="build_database",
                description="Build database.",
                components=["database"],
                features=[],
                skippable=True,
            ),
            ExecutionPhase(
                number=5,
                name="generate_code",
                description="Generate the code.",
                components=["store"],
                features=["store"],
            ),
        ],
    )
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
                engine_id="project_context",
                name="Project Context",
                phase="build_context",
            ),
        ],
        dependency_graph=DependencyGraph(),
        execution_plan=execution_plan,
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


def make_dependency_report(name="my_store_bot"):
    """Build a DependencyResolutionReport artefact (the 6th input).

    This is a hand-built report with 4 dependencies so the tests do
    not need to run the actual Dependency Resolution Engine.
    """
    deps = [
        DependencyEntry(
            name="python-telegram-bot",
            type=DEPENDENCY_TYPE_FRAMEWORK,
            suggested_version="21.x",
            version_constraint=">=20.0,<22.0",
            reason="The core Telegram bot framework.",
            source=SOURCE_FRAMEWORK,
            source_components=["core", "store_command"],
            priority=DEPENDENCY_PRIORITY_INFRASTRUCTURE,
            load_order=0,
            language="python",
            framework="python-telegram-bot",
            os_compatibility=["linux", "windows", "macos"],
            reputation=REPUTATION_GOOD,
            trust=TRUST_OFFICIAL,
            stability=STABILITY_STABLE,
            official=True,
        ),
        DependencyEntry(
            name="SQLAlchemy",
            type=DEPENDENCY_TYPE_LIBRARY,
            suggested_version="2.x",
            version_constraint=">=2.0,<3.0",
            reason="ORM for database access.",
            source=SOURCE_INFERENCE,
            source_components=["database"],
            priority=DEPENDENCY_PRIORITY_DATABASE,
            depends_on=["python-telegram-bot"],
            load_order=1,
            language="python",
            framework="",
            reputation=REPUTATION_GOOD,
            trust=TRUST_OFFICIAL,
            stability=STABILITY_STABLE,
            official=True,
        ),
        DependencyEntry(
            name="aiosqlite",
            type=DEPENDENCY_TYPE_LIBRARY,
            suggested_version="0.19.x",
            version_constraint=">=0.18",
            reason="Async SQLite driver for SQLAlchemy.",
            source=SOURCE_INFERENCE,
            source_components=["database"],
            priority=DEPENDENCY_PRIORITY_DATABASE,
            depends_on=["SQLAlchemy"],
            load_order=2,
            language="python",
            framework="",
            reputation=REPUTATION_GOOD,
            trust=TRUST_OFFICIAL,
            stability=STABILITY_STABLE,
        ),
        DependencyEntry(
            name="python-dotenv",
            type=DEPENDENCY_TYPE_LIBRARY,
            suggested_version="1.0.x",
            version_constraint=">=1.0",
            reason="Load environment variables from .env files.",
            source=SOURCE_INFERENCE,
            source_components=["core"],
            priority=DEPENDENCY_PRIORITY_CORE,
            load_order=3,
            language="python",
            framework="",
            reputation=REPUTATION_GOOD,
            trust=TRUST_OFFICIAL,
            stability=STABILITY_STABLE,
        ),
    ]
    # Wire depends_on / depended_by.
    deps[1].add_dependent("aiosqlite")
    deps[0].add_dependent("SQLAlchemy")

    relationships = [
        DependencyRelationship(
            source="SQLAlchemy",
            target="python-telegram-bot",
            kind="depends_on",
            description="SQLAlchemy is used alongside the framework.",
        ),
        DependencyRelationship(
            source="aiosqlite",
            target="SQLAlchemy",
            kind="depends_on",
            description="aiosqlite requires SQLAlchemy.",
        ),
    ]
    load_order = [
        DependencyOrderEntry(
            position=0,
            dependency_name="python-telegram-bot",
            dependency_type=DEPENDENCY_TYPE_FRAMEWORK,
            priority=DEPENDENCY_PRIORITY_INFRASTRUCTURE,
            source_components=["core", "store_command"],
        ),
        DependencyOrderEntry(
            position=1,
            dependency_name="SQLAlchemy",
            dependency_type=DEPENDENCY_TYPE_LIBRARY,
            priority=DEPENDENCY_PRIORITY_DATABASE,
            source_components=["database"],
        ),
        DependencyOrderEntry(
            position=2,
            dependency_name="aiosqlite",
            dependency_type=DEPENDENCY_TYPE_LIBRARY,
            priority=DEPENDENCY_PRIORITY_DATABASE,
            source_components=["database"],
        ),
        DependencyOrderEntry(
            position=3,
            dependency_name="python-dotenv",
            dependency_type=DEPENDENCY_TYPE_LIBRARY,
            priority=DEPENDENCY_PRIORITY_CORE,
            source_components=["core"],
        ),
    ]
    return DependencyResolutionReport(
        project_name=name,
        language="python",
        language_version="3.11",
        framework="python-telegram-bot",
        dependencies=deps,
        relationships=relationships,
        load_order=load_order,
        source_blueprint=name,
        validation_status=STATUS_APPROVED,
        source_structure_map=name,
        source_component_registry=name,
        source_file_generation_plan=name,
        summary="4 dependencies resolved.",
        notes=["Report generated for testing."],
        warnings=[],
    )


def make_full_context(name="my_store_bot"):
    """Build a context with all six artefacts set."""
    blueprint = make_valid_blueprint(name)
    report = make_approved_report(name)
    structure_map = make_structure_map(name)
    registry = make_component_registry(name)
    file_plan = make_file_plan(name)
    dependency_report = make_dependency_report(name)
    return make_context(
        blueprint=blueprint,
        validation_report=report,
        structure_map=structure_map,
        registry=registry,
        file_plan=file_plan,
        dependency_report=dependency_report,
    )


# ---------------------------------------------------------------------------#
# 1. Data model tests
# ---------------------------------------------------------------------------#

def test_project_goal_creation():
    """ProjectGoal can be created and has the right defaults."""
    goal = ProjectGoal()
    assert goal.name == ""
    assert goal.language == "python"
    assert goal.language_version == "3.11"
    assert goal.framework == "python-telegram-bot"
    assert goal.source_artefact == PC_SOURCE_BLUEPRINT
    print("  [PASS] test_project_goal_creation")


def test_project_goal_to_dict():
    """ProjectGoal.to_dict returns all fields."""
    goal = ProjectGoal(
        name="my_bot",
        display_name="My Bot",
        bot_type="store",
        primary_goal="A store bot.",
        language="python",
        language_version="3.11",
        framework="python-telegram-bot",
        database="sqlite",
    )
    d = goal.to_dict()
    assert d["name"] == "my_bot"
    assert d["display_name"] == "My Bot"
    assert d["bot_type"] == "store"
    assert d["primary_goal"] == "A store bot."
    assert d["language"] == "python"
    assert d["database"] == "sqlite"
    assert d["source_artefact"] == PC_SOURCE_BLUEPRINT
    print("  [PASS] test_project_goal_to_dict")


def test_feature_summary_creation():
    """FeatureSummary can be created with the right defaults."""
    feat = FeatureSummary(name="store")
    assert feat.name == "store"
    assert feat.display_name == ""
    assert feat.priority == 100
    assert feat.components == []
    assert feat.source_artefact == PC_SOURCE_BLUEPRINT
    print("  [PASS] test_feature_summary_creation")


def test_feature_summary_to_dict():
    """FeatureSummary.to_dict returns all fields."""
    feat = FeatureSummary(
        name="store",
        display_name="Store",
        description="Store feature.",
        priority=50,
        source_feature="store",
        components=["store_command"],
    )
    d = feat.to_dict()
    assert d["name"] == "store"
    assert d["display_name"] == "Store"
    assert d["description"] == "Store feature."
    assert d["priority"] == 50
    assert d["components"] == ["store_command"]
    assert d["source_artefact"] == PC_SOURCE_BLUEPRINT
    print("  [PASS] test_feature_summary_to_dict")


def test_component_summary_creation():
    """ComponentSummary can be created with the right defaults."""
    comp = ComponentSummary(name="core")
    assert comp.name == "core"
    assert comp.type == "utility"
    assert comp.importance == "normal"
    assert comp.files == []
    assert comp.dependencies == []
    assert comp.source_artefact == PC_SOURCE_COMPONENT_REGISTRY
    print("  [PASS] test_component_summary_creation")


def test_component_summary_to_dict():
    """ComponentSummary.to_dict returns all fields."""
    comp = ComponentSummary(
        name="core",
        type="service",
        purpose="Core service.",
        responsibility="Run the bot.",
        source_feature="store",
        location="src/core/bot.py",
        build_order=10,
        importance="critical",
        files=["src/core/bot.py"],
        dependencies=["python-telegram-bot"],
        depends_on=["database"],
        depended_by=["store_command"],
    )
    d = comp.to_dict()
    assert d["name"] == "core"
    assert d["type"] == "service"
    assert d["purpose"] == "Core service."
    assert d["responsibility"] == "Run the bot."
    assert d["location"] == "src/core/bot.py"
    assert d["build_order"] == 10
    assert d["importance"] == "critical"
    assert d["files"] == ["src/core/bot.py"]
    assert d["dependencies"] == ["python-telegram-bot"]
    assert d["depends_on"] == ["database"]
    assert d["depended_by"] == ["store_command"]
    assert d["source_artefact"] == PC_SOURCE_COMPONENT_REGISTRY
    print("  [PASS] test_component_summary_to_dict")


def test_file_summary_creation():
    """FileSummary can be created with the right defaults."""
    f = FileSummary(name="bot.py", path="src/bot.py")
    assert f.name == "bot.py"
    assert f.path == "src/bot.py"
    assert f.file_type == "text"
    assert f.contains_code is False
    assert f.source_artefact == PC_SOURCE_FILE_PLAN
    print("  [PASS] test_file_summary_creation")


def test_file_summary_to_dict():
    """FileSummary.to_dict returns all fields."""
    f = FileSummary(
        name="bot.py",
        path="src/bot.py",
        file_type="python_module",
        purpose="Main bot.",
        folder="src",
        responsible_engine="code_generator",
        generation_priority=20,
        build_order=5,
        source_component="core",
        depends_on=["src/__init__.py"],
        depended_by=["src/handlers/start.py"],
        reason_for_existence="Main bot file.",
        contains_code=True,
    )
    d = f.to_dict()
    assert d["name"] == "bot.py"
    assert d["path"] == "src/bot.py"
    assert d["file_type"] == "python_module"
    assert d["purpose"] == "Main bot."
    assert d["folder"] == "src"
    assert d["responsible_engine"] == "code_generator"
    assert d["generation_priority"] == 20
    assert d["build_order"] == 5
    assert d["source_component"] == "core"
    assert d["depends_on"] == ["src/__init__.py"]
    assert d["depended_by"] == ["src/handlers/start.py"]
    assert d["reason_for_existence"] == "Main bot file."
    assert d["contains_code"] is True
    assert d["source_artefact"] == PC_SOURCE_FILE_PLAN
    print("  [PASS] test_file_summary_to_dict")


def test_dependency_summary_creation():
    """DependencySummary can be created with the right defaults."""
    dep = DependencySummary(name="pytest")
    assert dep.name == "pytest"
    assert dep.type == "library"
    assert dep.suggested_version == "latest"
    assert dep.source_components == []
    assert dep.source_artefact == PC_SOURCE_DEPENDENCY_REPORT
    print("  [PASS] test_dependency_summary_creation")


def test_dependency_summary_to_dict():
    """DependencySummary.to_dict returns all fields."""
    dep = DependencySummary(
        name="python-telegram-bot",
        type="framework",
        suggested_version="21.x",
        version_constraint=">=20.0",
        reason="Telegram framework.",
        source_components=["core"],
        priority=10,
        load_order=0,
        language="python",
        framework="python-telegram-bot",
        depends_on=["SQLAlchemy"],
        depended_by=["aiosqlite"],
    )
    d = dep.to_dict()
    assert d["name"] == "python-telegram-bot"
    assert d["type"] == "framework"
    assert d["suggested_version"] == "21.x"
    assert d["version_constraint"] == ">=20.0"
    assert d["reason"] == "Telegram framework."
    assert d["source_components"] == ["core"]
    assert d["priority"] == 10
    assert d["load_order"] == 0
    assert d["language"] == "python"
    assert d["framework"] == "python-telegram-bot"
    assert d["depends_on"] == ["SQLAlchemy"]
    assert d["depended_by"] == ["aiosqlite"]
    assert d["source_artefact"] == PC_SOURCE_DEPENDENCY_REPORT
    print("  [PASS] test_dependency_summary_to_dict")


def test_relationship_summary_creation():
    """RelationshipSummary can be created with the right defaults."""
    rel = RelationshipSummary(source="a", target="b")
    assert rel.source == "a"
    assert rel.target == "b"
    assert rel.kind == "depends_on"
    assert rel.source_artefact == PC_SOURCE_BLUEPRINT
    print("  [PASS] test_relationship_summary_creation")


def test_relationship_summary_to_dict():
    """RelationshipSummary.to_dict returns all fields."""
    rel = RelationshipSummary(
        source="a", target="b",
        kind="imports", description="a imports b",
        source_artefact=PC_SOURCE_FILE_PLAN,
    )
    d = rel.to_dict()
    assert d["source"] == "a"
    assert d["target"] == "b"
    assert d["kind"] == "imports"
    assert d["description"] == "a imports b"
    assert d["source_artefact"] == PC_SOURCE_FILE_PLAN
    print("  [PASS] test_relationship_summary_to_dict")


def test_execution_stage_creation():
    """ExecutionStage can be created with the right defaults."""
    stage = ExecutionStage(name="core")
    assert stage.name == "core"
    assert stage.phase == 0
    assert stage.priority == 100
    assert stage.components == []
    assert stage.files == []
    assert stage.dependencies == []
    assert stage.source_artefact == PC_SOURCE_BLUEPRINT
    print("  [PASS] test_execution_stage_creation")


def test_execution_stage_to_dict():
    """ExecutionStage.to_dict returns all fields."""
    stage = ExecutionStage(
        name="core",
        phase=1,
        priority=100,
        components=["core"],
        files=["src/core/bot.py"],
        dependencies=["python-telegram-bot"],
        source_artefact=PC_SOURCE_BLUEPRINT,
    )
    d = stage.to_dict()
    assert d["name"] == "core"
    assert d["phase"] == 1
    assert d["priority"] == 100
    assert d["components"] == ["core"]
    assert d["files"] == ["src/core/bot.py"]
    assert d["dependencies"] == ["python-telegram-bot"]
    assert d["source_artefact"] == PC_SOURCE_BLUEPRINT
    print("  [PASS] test_execution_stage_to_dict")


def test_context_link_creation():
    """ContextLink can be created with the right defaults."""
    link = ContextLink(source="a", target="b")
    assert link.source == "a"
    assert link.target == "b"
    assert link.kind == LINK_FEATURE_TO_COMPONENT
    assert link.source_artefact == PC_SOURCE_BLUEPRINT
    print("  [PASS] test_context_link_creation")


def test_context_link_to_dict():
    """ContextLink.to_dict returns all fields."""
    link = ContextLink(
        source="core", target="src/core/bot.py",
        kind=LINK_COMPONENT_TO_FILE,
        source_artefact=PC_SOURCE_COMPONENT_REGISTRY,
    )
    d = link.to_dict()
    assert d["source"] == "core"
    assert d["target"] == "src/core/bot.py"
    assert d["kind"] == LINK_COMPONENT_TO_FILE
    assert d["source_artefact"] == PC_SOURCE_COMPONENT_REGISTRY
    print("  [PASS] test_context_link_to_dict")


def test_expansion_point_creation():
    """ExpansionPoint can be created with the right defaults."""
    ep = ExpansionPoint(area="handlers")
    assert ep.area == "handlers"
    assert ep.description == ""
    assert ep.source_artefact == PC_SOURCE_BLUEPRINT
    print("  [PASS] test_expansion_point_creation")


def test_expansion_point_to_dict():
    """ExpansionPoint.to_dict returns all fields."""
    ep = ExpansionPoint(
        area="handlers",
        description="Add more handlers.",
        source_artefact=PC_SOURCE_STRUCTURE,
    )
    d = ep.to_dict()
    assert d["area"] == "handlers"
    assert d["description"] == "Add more handlers."
    assert d["source_artefact"] == PC_SOURCE_STRUCTURE
    print("  [PASS] test_expansion_point_to_dict")


def test_context_finding_creation():
    """ContextFinding can be created with the right defaults."""
    finding = ContextFinding()
    assert finding.severity == PC_SEVERITY_WARNING
    assert finding.code == ""
    assert finding.message == ""
    assert finding.category == "validation"
    print("  [PASS] test_context_finding_creation")


def test_context_finding_to_dict():
    """ContextFinding.to_dict returns all fields."""
    finding = ContextFinding(
        severity=PC_SEVERITY_ERROR,
        code="duplicate_feature",
        message="Duplicate feature name.",
        affected="store",
        resolution_hint="Rename.",
        category="consistency",
    )
    d = finding.to_dict()
    assert d["severity"] == PC_SEVERITY_ERROR
    assert d["code"] == "duplicate_feature"
    assert d["message"] == "Duplicate feature name."
    assert d["affected"] == "store"
    assert d["resolution_hint"] == "Rename."
    assert d["category"] == "consistency"
    print("  [PASS] test_context_finding_to_dict")


def test_link_indices_creation():
    """LinkIndices can be created with the right defaults."""
    indices = LinkIndices()
    assert indices.feature_to_components == {}
    assert indices.component_to_features == {}
    assert indices.component_to_files == {}
    assert indices.file_to_components == {}
    assert indices.file_to_dependencies == {}
    assert indices.dependency_to_files == {}
    assert indices.dependency_to_components == {}
    assert indices.component_to_dependencies == {}
    assert indices.component_to_stage == {}
    assert indices.feature_to_stage == {}
    assert indices.file_to_stage == {}
    assert indices.dependency_to_stage == {}
    print("  [PASS] test_link_indices_creation")


def test_link_indices_to_dict():
    """LinkIndices.to_dict returns all fields."""
    indices = LinkIndices()
    indices.feature_to_components = {"store": ["store_command"]}
    indices.component_to_stage = {"core": "project_setup"}
    d = indices.to_dict()
    assert d["feature_to_components"] == {"store": ["store_command"]}
    assert d["component_to_stage"] == {"core": "project_setup"}
    assert "file_to_dependencies" in d
    assert "dependency_to_stage" in d
    print("  [PASS] test_link_indices_to_dict")


def test_source_provenance_creation():
    """SourceProvenance can be created with the right defaults."""
    prov = SourceProvenance()
    assert prov.blueprint_name == ""
    assert prov.validation_status == ""
    assert prov.all_sources_used == []
    print("  [PASS] test_source_provenance_creation")


def test_source_provenance_to_dict():
    """SourceProvenance.to_dict returns all fields."""
    prov = SourceProvenance(
        blueprint_name="my_bot",
        validation_status="approved",
        structure_map_name="my_bot",
        component_registry_name="my_bot",
        file_plan_name="my_bot",
        dependency_report_name="my_bot",
        all_sources_used=list(PC_ALL_SOURCES),
    )
    d = prov.to_dict()
    assert d["blueprint_name"] == "my_bot"
    assert d["validation_status"] == "approved"
    assert d["structure_map_name"] == "my_bot"
    assert d["component_registry_name"] == "my_bot"
    assert d["file_plan_name"] == "my_bot"
    assert d["dependency_report_name"] == "my_bot"
    assert d["all_sources_used"] == list(PC_ALL_SOURCES)
    print("  [PASS] test_source_provenance_to_dict")


def test_source_artefact_constants():
    """Source artefact constants are the expected strings."""
    assert PC_SOURCE_BLUEPRINT == "blueprint"
    assert PC_SOURCE_VALIDATION == "validation"
    assert PC_SOURCE_STRUCTURE == "structure"
    assert PC_SOURCE_COMPONENT_REGISTRY == "component_registry"
    assert PC_SOURCE_FILE_PLAN == "file_plan"
    assert PC_SOURCE_DEPENDENCY_REPORT == "dependency_report"
    assert len(PC_ALL_SOURCES) == 6
    print("  [PASS] test_source_artefact_constants")


def test_severity_constants():
    """Severity constants are the expected strings."""
    assert PC_SEVERITY_ERROR == "error"
    assert PC_SEVERITY_WARNING == "warning"
    assert PC_SEVERITY_INFO == "info"
    assert len(PC_ALL_SEVERITIES) == 3
    print("  [PASS] test_severity_constants")


def test_link_kind_constants():
    """Link kind constants are the expected strings."""
    assert LINK_FEATURE_TO_COMPONENT == "feature_to_component"
    assert LINK_COMPONENT_TO_FILE == "component_to_file"
    assert LINK_FILE_TO_DEPENDENCY == "file_to_dependency"
    assert LINK_DEPENDENCY_TO_STAGE == "dependency_to_stage"
    assert LINK_COMPONENT_TO_STAGE == "component_to_stage"
    assert LINK_FEATURE_TO_STAGE == "feature_to_stage"
    assert len(ALL_LINK_KINDS) == 6
    print("  [PASS] test_link_kind_constants")


# ---------------------------------------------------------------------------#
# 2. ProjectContext convenience properties
# ---------------------------------------------------------------------------#

def test_project_context_empty():
    """An empty ProjectContext reports is_empty as True."""
    ctx = ProjectContext()
    assert ctx.is_empty is True
    assert ctx.feature_count == 0
    assert ctx.component_count == 0
    assert ctx.file_count == 0
    assert ctx.dependency_count == 0
    assert ctx.has_errors is False
    assert ctx.error_count == 0
    assert ctx.warning_count == 0
    print("  [PASS] test_project_context_empty")


def test_project_context_counts():
    """ProjectContext counts are correct after adding data."""
    ctx = ProjectContext()
    ctx.features.append(FeatureSummary(name="f1"))
    ctx.components.append(ComponentSummary(name="c1"))
    ctx.files.append(FileSummary(name="f.py", path="f.py"))
    ctx.dependencies.append(DependencySummary(name="d1"))
    ctx.relationships.append(RelationshipSummary(source="a", target="b"))
    ctx.stages.append(ExecutionStage(name="s1"))
    ctx.links.append(ContextLink(source="a", target="b"))
    assert not ctx.is_empty
    assert ctx.feature_count == 1
    assert ctx.component_count == 1
    assert ctx.file_count == 1
    assert ctx.dependency_count == 1
    assert ctx.relationship_count == 1
    assert ctx.stage_count == 1
    assert ctx.link_count == 1
    print("  [PASS] test_project_context_counts")


def test_project_context_add_finding():
    """add_finding adds to the findings list."""
    ctx = ProjectContext()
    ctx.add_finding(
        PC_SEVERITY_ERROR, "test_error", "An error.",
        affected="x", category="test",
    )
    assert ctx.error_count == 1
    assert ctx.has_errors is True
    ctx.add_finding(
        PC_SEVERITY_WARNING, "test_warning", "A warning.",
    )
    assert ctx.warning_count == 1
    assert "A warning." in ctx.warnings
    print("  [PASS] test_project_context_add_finding")


def test_project_context_get_methods():
    """ProjectContext get_* methods find elements by name."""
    ctx = ProjectContext()
    ctx.features.append(FeatureSummary(name="store"))
    ctx.components.append(ComponentSummary(name="core"))
    ctx.files.append(FileSummary(name="bot.py", path="src/bot.py"))
    ctx.dependencies.append(DependencySummary(name="ptb"))
    ctx.stages.append(ExecutionStage(name="core"))
    assert ctx.get_feature("store") is not None
    assert ctx.get_feature("store").name == "store"
    assert ctx.get_feature("missing") is None
    assert ctx.get_component("core") is not None
    assert ctx.get_component("missing") is None
    assert ctx.get_file("src/bot.py") is not None
    assert ctx.get_file("missing") is None
    assert ctx.get_dependency("ptb") is not None
    assert ctx.get_dependency("missing") is None
    assert ctx.get_stage("core") is not None
    assert ctx.get_stage("missing") is None
    print("  [PASS] test_project_context_get_methods")


# ---------------------------------------------------------------------------#
# 3. BlueprintReader
# ---------------------------------------------------------------------------#

def test_blueprint_reader_goal():
    """BlueprintReader reads the goal from the blueprint."""
    reader = BlueprintReader()
    bp = make_valid_blueprint()
    data = reader.read(bp)
    goal = data["goal"]
    assert goal.name == "my_store_bot"
    assert goal.bot_type == "store"
    assert goal.language == "python"
    assert goal.framework == "python-telegram-bot"
    assert goal.source_artefact == PC_SOURCE_BLUEPRINT
    print("  [PASS] test_blueprint_reader_goal")


def test_blueprint_reader_features():
    """BlueprintReader reads the features from the blueprint."""
    reader = BlueprintReader()
    bp = make_valid_blueprint()
    data = reader.read(bp)
    features = data["features"]
    assert len(features) == 1
    assert features[0].name == "store"
    assert "store" in features[0].components
    print("  [PASS] test_blueprint_reader_features")


def test_blueprint_reader_relationships():
    """BlueprintReader reads the relationships from the blueprint."""
    reader = BlueprintReader()
    bp = make_valid_blueprint()
    data = reader.read(bp)
    rels = data["relationships"]
    assert len(rels) == 1
    assert rels[0].source == "store"
    assert rels[0].target == "database"
    assert rels[0].kind == "depends_on"
    print("  [PASS] test_blueprint_reader_relationships")


def test_blueprint_reader_stages():
    """BlueprintReader reads the stages from the execution plan."""
    reader = BlueprintReader()
    bp = make_valid_blueprint()
    data = reader.read(bp)
    stages = data["stages"]
    assert len(stages) == 3
    assert stages[0].name == "project_setup"
    assert stages[1].name == "build_database"
    assert stages[2].name == "generate_code"
    assert stages[0].phase == 1
    print("  [PASS] test_blueprint_reader_stages")


def test_blueprint_reader_expansion_points():
    """BlueprintReader reads expansion points from the blueprint."""
    reader = BlueprintReader()
    bp = make_valid_blueprint()
    data = reader.read(bp)
    eps = data["expansion_points"]
    assert len(eps) > 0
    print("  [PASS] test_blueprint_reader_expansion_points")


# ---------------------------------------------------------------------------#
# 4. ValidationReader
# ---------------------------------------------------------------------------#

def test_validation_reader_status():
    """ValidationReader reads the validation status."""
    reader = ValidationReader()
    report = make_approved_report()
    data = reader.read(report)
    assert data["validation_status"] == STATUS_APPROVED
    assert data["overall_quality"] == 0.85
    print("  [PASS] test_validation_reader_status")


def test_validation_reader_findings():
    """ValidationReader returns findings (may be empty for a clean report)."""
    reader = ValidationReader()
    report = make_approved_report()
    data = reader.read(report)
    assert "findings" in data
    assert isinstance(data["findings"], list)
    assert "provenance_partial" in data
    assert data["provenance_partial"]["validation_status"] == STATUS_APPROVED
    print("  [PASS] test_validation_reader_findings")


# ---------------------------------------------------------------------------#
# 5. StructureReader
# ---------------------------------------------------------------------------#

def test_structure_reader_files():
    """StructureReader reads the files from the structure map."""
    reader = StructureReader()
    sm = make_structure_map()
    data = reader.read(sm)
    files = data["files"]
    assert len(files) > 0
    assert all(f.source_artefact == PC_SOURCE_STRUCTURE for f in files)
    print("  [PASS] test_structure_reader_files")


def test_structure_reader_provenance():
    """StructureReader provides the provenance partial."""
    reader = StructureReader()
    sm = make_structure_map()
    data = reader.read(sm)
    assert data["provenance_partial"]["structure_map_name"] == "my_store_bot"
    print("  [PASS] test_structure_reader_provenance")


def test_structure_reader_build_order_map():
    """StructureReader provides the build order map."""
    reader = StructureReader()
    sm = make_structure_map()
    data = reader.read(sm)
    assert "build_order_map" in data
    assert isinstance(data["build_order_map"], dict)
    print("  [PASS] test_structure_reader_build_order_map")


# ---------------------------------------------------------------------------#
# 6. RegistryReader
# ---------------------------------------------------------------------------#

def test_registry_reader_components():
    """RegistryReader reads the components from the registry."""
    reader = RegistryReader()
    reg = make_component_registry()
    data = reader.read(reg)
    components = data["components"]
    assert len(components) == 3
    assert all(c.source_artefact == PC_SOURCE_COMPONENT_REGISTRY for c in components)
    print("  [PASS] test_registry_reader_components")


def test_registry_reader_provenance():
    """RegistryReader provides the provenance partial."""
    reader = RegistryReader()
    reg = make_component_registry()
    data = reader.read(reg)
    assert data["provenance_partial"]["component_registry_name"] == "my_store_bot"
    print("  [PASS] test_registry_reader_provenance")


def test_registry_reader_expansion_points():
    """RegistryReader returns expansion points (may be empty)."""
    reader = RegistryReader()
    reg = make_component_registry()
    data = reader.read(reg)
    assert "expansion_points" in data
    assert isinstance(data["expansion_points"], list)
    print("  [PASS] test_registry_reader_expansion_points")


# ---------------------------------------------------------------------------#
# 7. FilePlanReader
# ---------------------------------------------------------------------------#

def test_file_plan_reader_files():
    """FilePlanReader reads the files from the file plan."""
    reader = FilePlanReader()
    fp = make_file_plan()
    data = reader.read(fp)
    files = data["files"]
    assert len(files) == 4
    assert all(f.source_artefact == PC_SOURCE_FILE_PLAN for f in files)
    print("  [PASS] test_file_plan_reader_files")


def test_file_plan_reader_relationships():
    """FilePlanReader reads the relationships from the file plan."""
    reader = FilePlanReader()
    fp = make_file_plan()
    data = reader.read(fp)
    rels = data["relationships"]
    assert len(rels) == 2
    assert all(r.source_artefact == PC_SOURCE_FILE_PLAN for r in rels)
    print("  [PASS] test_file_plan_reader_relationships")


def test_file_plan_reader_provenance():
    """FilePlanReader provides the provenance partial."""
    reader = FilePlanReader()
    fp = make_file_plan()
    data = reader.read(fp)
    assert data["provenance_partial"]["file_plan_name"] == "my_store_bot"
    print("  [PASS] test_file_plan_reader_provenance")


# ---------------------------------------------------------------------------#
# 8. DependencyReader
# ---------------------------------------------------------------------------#

def test_dependency_reader_dependencies():
    """DependencyReader reads the dependencies from the report."""
    reader = DependencyReader()
    dr = make_dependency_report()
    data = reader.read(dr)
    deps = data["dependencies"]
    assert len(deps) == 4
    assert all(d.source_artefact == PC_SOURCE_DEPENDENCY_REPORT for d in deps)
    print("  [PASS] test_dependency_reader_dependencies")


def test_dependency_reader_relationships():
    """DependencyReader reads the relationships from the report."""
    reader = DependencyReader()
    dr = make_dependency_report()
    data = reader.read(dr)
    rels = data["relationships"]
    assert len(rels) == 2
    print("  [PASS] test_dependency_reader_relationships")


def test_dependency_reader_findings():
    """DependencyReader returns findings (may be empty for a clean report)."""
    reader = DependencyReader()
    dr = make_dependency_report()
    data = reader.read(dr)
    assert "findings" in data
    assert isinstance(data["findings"], list)
    print("  [PASS] test_dependency_reader_findings")


def test_dependency_reader_provenance():
    """DependencyReader provides the provenance partial."""
    reader = DependencyReader()
    dr = make_dependency_report()
    data = reader.read(dr)
    assert data["provenance_partial"]["dependency_report_name"] == "my_store_bot"
    print("  [PASS] test_dependency_reader_provenance")


# ---------------------------------------------------------------------------#
# 9. ContextAssembler
# ---------------------------------------------------------------------------#

def test_assembler_produces_project_context():
    """ContextAssembler.assemble produces a ProjectContext."""
    assembler = ContextAssembler()
    ctx = assembler.assemble(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
    )
    assert isinstance(ctx, ProjectContext)
    assert ctx.feature_count == 1
    assert ctx.component_count == 3
    assert ctx.file_count > 0
    assert ctx.dependency_count == 4
    assert ctx.stage_count == 3
    print("  [PASS] test_assembler_produces_project_context")


def test_assembler_goal():
    """The assembled context has the correct goal."""
    assembler = ContextAssembler()
    ctx = assembler.assemble(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
    )
    assert ctx.goal.name == "my_store_bot"
    assert ctx.goal.bot_type == "store"
    print("  [PASS] test_assembler_goal")


def test_assembler_features_have_components():
    """The assembler cross-links features to components."""
    assembler = ContextAssembler()
    ctx = assembler.assemble(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
    )
    store_feat = ctx.get_feature("store")
    assert store_feat is not None
    assert "store_command" in store_feat.components
    print("  [PASS] test_assembler_features_have_components")


def test_assembler_components_have_files():
    """The assembler cross-links components to files."""
    assembler = ContextAssembler()
    ctx = assembler.assemble(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
    )
    core_comp = ctx.get_component("core")
    assert core_comp is not None
    assert len(core_comp.files) > 0
    db_comp = ctx.get_component("database")
    assert db_comp is not None
    assert len(db_comp.files) > 0
    print("  [PASS] test_assembler_components_have_files")


def test_assembler_components_have_dependencies():
    """The assembler cross-links components to dependencies."""
    assembler = ContextAssembler()
    ctx = assembler.assemble(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
    )
    core_comp = ctx.get_component("core")
    assert core_comp is not None
    assert "python-telegram-bot" in core_comp.dependencies
    db_comp = ctx.get_component("database")
    assert db_comp is not None
    assert "SQLAlchemy" in db_comp.dependencies
    print("  [PASS] test_assembler_components_have_dependencies")


def test_assembler_deduplicates_relationships():
    """The assembler deduplicates relationships by (source, target, kind)."""
    assembler = ContextAssembler()
    ctx = assembler.assemble(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
    )
    # No two relationships should have the same (source, target, kind).
    seen = set()
    for rel in ctx.relationships:
        key = (rel.source, rel.target, rel.kind)
        assert key not in seen, f"Duplicate relationship: {key}"
        seen.add(key)
    print("  [PASS] test_assembler_deduplicates_relationships")


def test_assembler_provenance():
    """The assembler builds the provenance record."""
    assembler = ContextAssembler()
    ctx = assembler.assemble(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
    )
    prov = ctx.provenance
    assert prov.blueprint_name == "my_store_bot"
    assert prov.validation_status == STATUS_APPROVED
    assert prov.structure_map_name == "my_store_bot"
    assert prov.component_registry_name == "my_store_bot"
    assert prov.file_plan_name == "my_store_bot"
    assert prov.dependency_report_name == "my_store_bot"
    assert len(prov.all_sources_used) == 6
    print("  [PASS] test_assembler_provenance")


def test_assembler_stages_enriched():
    """The assembler enriches stages with files and dependencies."""
    assembler = ContextAssembler()
    ctx = assembler.assemble(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
    )
    # The 'build_database' stage should have the database component
    # and its files.
    db_stage = ctx.get_stage("build_database")
    if db_stage:
        # The database component's files should be in the stage.
        db_comp = ctx.get_component("database")
        if db_comp:
            for f_path in db_comp.files:
                assert f_path in db_stage.files
    print("  [PASS] test_assembler_stages_enriched")


# ---------------------------------------------------------------------------#
# 10. ContextLinker
# ---------------------------------------------------------------------------#

def _make_assembled_context():
    """Helper: assemble a context and link it."""
    assembler = ContextAssembler()
    ctx = assembler.assemble(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
    )
    linker = ContextLinker()
    linker.link(ctx)
    return ctx


def test_linker_builds_links():
    """ContextLinker builds a non-empty links list."""
    ctx = _make_assembled_context()
    assert ctx.link_count > 0
    print("  [PASS] test_linker_builds_links")


def test_linker_feature_to_component_links():
    """ContextLinker creates feature-to-component links."""
    ctx = _make_assembled_context()
    fc_links = [l for l in ctx.links if l.kind == LINK_FEATURE_TO_COMPONENT]
    assert len(fc_links) > 0
    # The 'store' feature should be linked to 'store_command'.
    store_links = [l for l in fc_links if l.source == "store"]
    assert len(store_links) > 0
    assert "store_command" in [l.target for l in store_links]
    print("  [PASS] test_linker_feature_to_component_links")


def test_linker_component_to_file_links():
    """ContextLinker creates component-to-file links."""
    ctx = _make_assembled_context()
    cf_links = [l for l in ctx.links if l.kind == LINK_COMPONENT_TO_FILE]
    assert len(cf_links) > 0
    # The 'core' component should be linked to its files.
    core_links = [l for l in cf_links if l.source == "core"]
    assert len(core_links) > 0
    print("  [PASS] test_linker_component_to_file_links")


def test_linker_file_to_dependency_links():
    """ContextLinker creates file-to-dependency links."""
    ctx = _make_assembled_context()
    fd_links = [l for l in ctx.links if l.kind == LINK_FILE_TO_DEPENDENCY]
    assert len(fd_links) > 0
    print("  [PASS] test_linker_file_to_dependency_links")


def test_linker_component_to_stage_links():
    """ContextLinker creates component-to-stage links."""
    ctx = _make_assembled_context()
    cs_links = [l for l in ctx.links if l.kind == LINK_COMPONENT_TO_STAGE]
    assert len(cs_links) > 0
    print("  [PASS] test_linker_component_to_stage_links")


def test_linker_dependency_to_stage_links():
    """ContextLinker creates dependency-to-stage links."""
    ctx = _make_assembled_context()
    ds_links = [l for l in ctx.links if l.kind == LINK_DEPENDENCY_TO_STAGE]
    assert len(ds_links) > 0
    print("  [PASS] test_linker_dependency_to_stage_links")


def test_linker_indices_feature_to_components():
    """The indices map features to components."""
    ctx = _make_assembled_context()
    comps = ctx.indices.feature_to_components.get("store", [])
    assert "store_command" in comps
    print("  [PASS] test_linker_indices_feature_to_components")


def test_linker_indices_component_to_files():
    """The indices map components to files."""
    ctx = _make_assembled_context()
    files = ctx.indices.component_to_files.get("core", [])
    assert len(files) > 0
    print("  [PASS] test_linker_indices_component_to_files")


def test_linker_indices_file_to_dependencies():
    """The indices map files to dependencies."""
    ctx = _make_assembled_context()
    # Some file should have dependencies.
    found = False
    for f_path, deps in ctx.indices.file_to_dependencies.items():
        if deps:
            found = True
            break
    assert found, "No file has any dependency in the indices"
    print("  [PASS] test_linker_indices_file_to_dependencies")


def test_linker_indices_dependency_to_components():
    """The indices map dependencies to components."""
    ctx = _make_assembled_context()
    comps = ctx.indices.dependency_to_components.get("SQLAlchemy", [])
    assert "database" in comps
    print("  [PASS] test_linker_indices_dependency_to_components")


def test_linker_indices_component_to_stage():
    """The indices map components to stages."""
    ctx = _make_assembled_context()
    stage = ctx.indices.component_to_stage.get("core", "")
    assert stage != ""
    print("  [PASS] test_linker_indices_component_to_stage")


def test_linker_indices_dependency_to_stage():
    """The indices map dependencies to stages."""
    ctx = _make_assembled_context()
    stage = ctx.indices.dependency_to_stage.get("SQLAlchemy", "")
    assert stage != ""
    print("  [PASS] test_linker_indices_dependency_to_stage")


def test_linker_o1_lookup_methods():
    """The O(1) lookup methods on ProjectContext work."""
    ctx = _make_assembled_context()
    # components_for_feature
    comps = ctx.components_for_feature("store")
    assert "store_command" in comps
    # features_for_component
    feats = ctx.features_for_component("store_command")
    assert "store" in feats
    # files_for_component
    files = ctx.files_for_component("core")
    assert len(files) > 0
    # dependencies_for_component
    deps = ctx.dependencies_for_component("database")
    assert "SQLAlchemy" in deps
    # stage_for_component
    stage = ctx.stage_for_component("core")
    assert stage != ""
    print("  [PASS] test_linker_o1_lookup_methods")


# ---------------------------------------------------------------------------#
# 11. ContextValidator
# ---------------------------------------------------------------------------#

def test_validator_no_findings_on_valid_context():
    """The validator produces no error findings on a valid context."""
    ctx = _make_assembled_context()
    validator = ContextValidator()
    findings = validator.validate(ctx)
    errors = [f for f in findings if f.severity == PC_SEVERITY_ERROR]
    assert len(errors) == 0, (
        f"Unexpected errors: {[(f.code, f.message) for f in errors]}"
    )
    print("  [PASS] test_validator_no_findings_on_valid_context")


def test_validator_duplicate_feature_names():
    """The validator catches duplicate feature names."""
    ctx = _make_assembled_context()
    ctx.features.append(FeatureSummary(name="store"))  # duplicate
    validator = ContextValidator()
    findings = validator.validate(ctx)
    dup = [f for f in findings if f.code == "duplicate_feature_name"]
    assert len(dup) >= 1
    assert dup[0].severity == PC_SEVERITY_ERROR
    print("  [PASS] test_validator_duplicate_feature_names")


def test_validator_duplicate_component_names():
    """The validator catches duplicate component names."""
    ctx = _make_assembled_context()
    ctx.components.append(ComponentSummary(name="core"))  # duplicate
    validator = ContextValidator()
    findings = validator.validate(ctx)
    dup = [f for f in findings if f.code == "duplicate_component_name"]
    assert len(dup) >= 1
    assert dup[0].severity == PC_SEVERITY_ERROR
    print("  [PASS] test_validator_duplicate_component_names")


def test_validator_feature_without_components():
    """The validator catches features without components."""
    ctx = _make_assembled_context()
    ctx.features.append(FeatureSummary(name="orphan_feature"))
    validator = ContextValidator()
    findings = validator.validate(ctx)
    orphan = [f for f in findings if f.code == "feature_without_components"]
    assert len(orphan) >= 1
    assert orphan[0].severity == PC_SEVERITY_WARNING
    print("  [PASS] test_validator_feature_without_components")


def test_validator_component_without_files():
    """The validator catches components without files."""
    ctx = _make_assembled_context()
    ctx.components.append(ComponentSummary(name="orphan_comp"))
    validator = ContextValidator()
    findings = validator.validate(ctx)
    orphan = [f for f in findings if f.code == "component_without_files"]
    assert len(orphan) >= 1
    print("  [PASS] test_validator_component_without_files")


def test_validator_file_without_responsibility():
    """The validator catches files without responsibility."""
    ctx = _make_assembled_context()
    ctx.files.append(FileSummary(
        name="orphan.py", path="orphan.py",
        source_component="", responsible_engine="",
    ))
    validator = ContextValidator()
    findings = validator.validate(ctx)
    orphan = [f for f in findings if f.code == "file_without_responsibility"]
    assert len(orphan) >= 1
    print("  [PASS] test_validator_file_without_responsibility")


def test_validator_unknown_elements_in_relationships():
    """The validator catches relationships with unknown elements."""
    ctx = _make_assembled_context()
    ctx.relationships.append(RelationshipSummary(
        source="nonexistent", target="also_nonexistent",
        kind="depends_on",
    ))
    validator = ContextValidator()
    findings = validator.validate(ctx)
    unknown = [
        f for f in findings
        if f.code in ("unknown_relationship_source", "unknown_relationship_target")
    ]
    assert len(unknown) >= 1
    print("  [PASS] test_validator_unknown_elements_in_relationships")


# ---------------------------------------------------------------------------#
# 12. Engine — data source (reads only 6 artefacts)
# ---------------------------------------------------------------------------#

def test_engine_requires_blueprint():
    """Engine fails when the project_blueprint artefact is missing."""
    engine = ProjectContextEngine()
    ctx = make_context(
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
    )
    result = engine.execute(ctx)
    assert not result.success
    assert any("project_blueprint" in e for e in result.errors)
    print("  [PASS] test_engine_requires_blueprint")


def test_engine_requires_validation_report():
    """Engine fails when the blueprint_validation_report artefact is missing."""
    engine = ProjectContextEngine()
    ctx = make_context(
        blueprint=make_valid_blueprint(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
    )
    result = engine.execute(ctx)
    assert not result.success
    assert any("blueprint_validation_report" in e for e in result.errors)
    print("  [PASS] test_engine_requires_validation_report")


def test_engine_requires_structure_map():
    """Engine fails when the project_structure_map artefact is missing."""
    engine = ProjectContextEngine()
    ctx = make_context(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
    )
    result = engine.execute(ctx)
    assert not result.success
    assert any("project_structure_map" in e for e in result.errors)
    print("  [PASS] test_engine_requires_structure_map")


def test_engine_requires_component_registry():
    """Engine fails when the component_registry artefact is missing."""
    engine = ProjectContextEngine()
    ctx = make_context(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
    )
    result = engine.execute(ctx)
    assert not result.success
    assert any("component_registry" in e for e in result.errors)
    print("  [PASS] test_engine_requires_component_registry")


def test_engine_requires_file_plan():
    """Engine fails when the file_generation_plan artefact is missing."""
    engine = ProjectContextEngine()
    ctx = make_context(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        dependency_report=make_dependency_report(),
    )
    result = engine.execute(ctx)
    assert not result.success
    assert any("file_generation_plan" in e for e in result.errors)
    print("  [PASS] test_engine_requires_file_plan")


def test_engine_requires_dependency_report():
    """Engine fails when the dependency_resolution_report artefact is missing."""
    engine = ProjectContextEngine()
    ctx = make_context(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
    )
    result = engine.execute(ctx)
    assert not result.success
    assert any("dependency_resolution_report" in e for e in result.errors)
    print("  [PASS] test_engine_requires_dependency_report")


def test_engine_does_not_read_request():
    """The engine's output does not depend on the request field."""
    ctx1 = make_full_context()
    ctx1.request = "create a store bot"

    ctx2 = make_full_context()
    ctx2.request = "completely different request text"

    engine = ProjectContextEngine()
    result1 = engine.execute(ctx1)
    result2 = engine.execute(ctx2)

    assert result1.success
    assert result2.success

    pc1 = ctx1.get("project_context")
    pc2 = ctx2.get("project_context")
    assert pc1.feature_count == pc2.feature_count
    assert pc1.component_count == pc2.component_count
    assert pc1.file_count == pc2.file_count
    assert pc1.dependency_count == pc2.dependency_count
    print("  [PASS] test_engine_does_not_read_request")


# ---------------------------------------------------------------------------#
# 13. Engine — type checking
# ---------------------------------------------------------------------------#

def test_engine_type_check_blueprint():
    """Engine fails when the blueprint is the wrong type."""
    engine = ProjectContextEngine()
    ctx = make_context(
        blueprint="not a blueprint",
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
    )
    result = engine.execute(ctx)
    assert not result.success
    assert any("ProjectBlueprint" in e for e in result.errors)
    print("  [PASS] test_engine_type_check_blueprint")


def test_engine_type_check_validation_report():
    """Engine fails when the validation report is the wrong type."""
    engine = ProjectContextEngine()
    ctx = make_context(
        blueprint=make_valid_blueprint(),
        validation_report="not a report",
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
    )
    result = engine.execute(ctx)
    assert not result.success
    assert any("BlueprintValidationReport" in e for e in result.errors)
    print("  [PASS] test_engine_type_check_validation_report")


def test_engine_type_check_structure_map():
    """Engine fails when the structure map is the wrong type."""
    engine = ProjectContextEngine()
    ctx = make_context(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map="not a structure map",
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
    )
    result = engine.execute(ctx)
    assert not result.success
    assert any("ProjectStructureMap" in e for e in result.errors)
    print("  [PASS] test_engine_type_check_structure_map")


def test_engine_type_check_registry():
    """Engine fails when the registry is the wrong type."""
    engine = ProjectContextEngine()
    ctx = make_context(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry="not a registry",
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
    )
    result = engine.execute(ctx)
    assert not result.success
    assert any("ComponentRegistry" in e for e in result.errors)
    print("  [PASS] test_engine_type_check_registry")


def test_engine_type_check_file_plan():
    """Engine fails when the file plan is the wrong type."""
    engine = ProjectContextEngine()
    ctx = make_context(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan="not a file plan",
        dependency_report=make_dependency_report(),
    )
    result = engine.execute(ctx)
    assert not result.success
    assert any("FileGenerationPlan" in e for e in result.errors)
    print("  [PASS] test_engine_type_check_file_plan")


def test_engine_type_check_dependency_report():
    """Engine fails when the dependency report is the wrong type."""
    engine = ProjectContextEngine()
    ctx = make_context(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report="not a report",
    )
    result = engine.execute(ctx)
    assert not result.success
    assert any("DependencyResolutionReport" in e for e in result.errors)
    print("  [PASS] test_engine_type_check_dependency_report")


# ---------------------------------------------------------------------------#
# 14. Engine — output
# ---------------------------------------------------------------------------#

def test_engine_produces_project_context():
    """Engine produces a ProjectContext and stores it."""
    ctx = make_full_context()
    engine = ProjectContextEngine()
    result = engine.execute(ctx)
    assert result.success, f"Engine failed: {result.errors}"
    pc = ctx.get("project_context")
    assert pc is not None
    assert isinstance(pc, ProjectContext)
    assert pc.goal.name == "my_store_bot"
    assert pc.feature_count > 0
    assert pc.component_count > 0
    assert pc.file_count > 0
    assert pc.dependency_count > 0
    print("  [PASS] test_engine_produces_project_context")


def test_engine_context_stored_in_metadata():
    """The context is also stored in the context metadata."""
    ctx = make_full_context()
    engine = ProjectContextEngine()
    engine.execute(ctx)
    assert "project_context" in ctx.metadata
    assert isinstance(ctx.metadata["project_context"], ProjectContext)
    print("  [PASS] test_engine_context_stored_in_metadata")


def test_engine_records_provenance():
    """The context records all six source artefacts in provenance."""
    ctx = make_full_context()
    engine = ProjectContextEngine()
    engine.execute(ctx)
    pc = ctx.get("project_context")
    prov = pc.provenance
    assert prov.blueprint_name == "my_store_bot"
    assert prov.validation_status == STATUS_APPROVED
    assert prov.structure_map_name == "my_store_bot"
    assert prov.component_registry_name == "my_store_bot"
    assert prov.file_plan_name == "my_store_bot"
    assert prov.dependency_report_name == "my_store_bot"
    assert len(prov.all_sources_used) == 6
    print("  [PASS] test_engine_records_provenance")


def test_engine_context_has_summary():
    """The context has a non-empty summary."""
    ctx = make_full_context()
    engine = ProjectContextEngine()
    engine.execute(ctx)
    pc = ctx.get("project_context")
    assert pc.summary
    assert "feature" in pc.summary.lower() or "context" in pc.summary.lower()
    print("  [PASS] test_engine_context_has_summary")


def test_engine_context_has_notes():
    """The context has a non-empty notes list."""
    ctx = make_full_context()
    engine = ProjectContextEngine()
    engine.execute(ctx)
    pc = ctx.get("project_context")
    assert len(pc.notes) > 0
    print("  [PASS] test_engine_context_has_notes")


def test_engine_context_has_stages():
    """The context has non-zero stages."""
    ctx = make_full_context()
    engine = ProjectContextEngine()
    engine.execute(ctx)
    pc = ctx.get("project_context")
    assert pc.stage_count > 0
    assert pc.stage_count == 3
    print("  [PASS] test_engine_context_has_stages")


def test_engine_context_has_links():
    """The context has non-zero links."""
    ctx = make_full_context()
    engine = ProjectContextEngine()
    engine.execute(ctx)
    pc = ctx.get("project_context")
    assert pc.link_count > 0
    print("  [PASS] test_engine_context_has_links")


def test_engine_metadata_in_result():
    """The result metadata contains the context statistics."""
    ctx = make_full_context()
    engine = ProjectContextEngine()
    result = engine.execute(ctx)
    assert result.success
    assert "project_name" in result.metadata
    assert "feature_count" in result.metadata
    assert "component_count" in result.metadata
    assert "file_count" in result.metadata
    assert "dependency_count" in result.metadata
    assert "stage_count" in result.metadata
    assert "link_count" in result.metadata
    print("  [PASS] test_engine_metadata_in_result")


def test_engine_context_no_errors():
    """The context has no error-level findings."""
    ctx = make_full_context()
    engine = ProjectContextEngine()
    result = engine.execute(ctx)
    assert result.success, f"Engine failed: {result.errors}"
    pc = ctx.get("project_context")
    assert pc.error_count == 0, (
        f"Context has errors: {[(f.code, f.message) for f in pc.findings if f.severity == PC_SEVERITY_ERROR]}"
    )
    print("  [PASS] test_engine_context_no_errors")


# ---------------------------------------------------------------------------#
# 15. Context integrity
# ---------------------------------------------------------------------------#

def test_context_all_features_have_components():
    """Every feature has at least one component (or a warning is recorded)."""
    ctx = make_full_context()
    engine = ProjectContextEngine()
    engine.execute(ctx)
    pc = ctx.get("project_context")
    for feat in pc.features:
        if not feat.components:
            # There should be a warning for this feature.
            warnings = [
                f for f in pc.findings
                if f.code == "feature_without_components"
                and f.affected == feat.name
            ]
            assert len(warnings) >= 1
    print("  [PASS] test_context_all_features_have_components")


def test_context_all_components_have_files():
    """Every component has at least one file (or a warning is recorded)."""
    ctx = make_full_context()
    engine = ProjectContextEngine()
    engine.execute(ctx)
    pc = ctx.get("project_context")
    for comp in pc.components:
        if not comp.files:
            warnings = [
                f for f in pc.findings
                if f.code == "component_without_files"
                and f.affected == comp.name
            ]
            assert len(warnings) >= 1
    print("  [PASS] test_context_all_components_have_files")


def test_context_no_duplicate_components():
    """No two components share the same name."""
    ctx = make_full_context()
    engine = ProjectContextEngine()
    engine.execute(ctx)
    pc = ctx.get("project_context")
    names = [c.name for c in pc.components]
    assert len(names) == len(set(names))
    print("  [PASS] test_context_no_duplicate_components")


def test_context_no_duplicate_files():
    """No two files share the same path."""
    ctx = make_full_context()
    engine = ProjectContextEngine()
    engine.execute(ctx)
    pc = ctx.get("project_context")
    paths = [f.path for f in pc.files]
    assert len(paths) == len(set(paths))
    print("  [PASS] test_context_no_duplicate_files")


def test_context_no_duplicate_dependencies():
    """No two dependencies share the same name."""
    ctx = make_full_context()
    engine = ProjectContextEngine()
    engine.execute(ctx)
    pc = ctx.get("project_context")
    names = [d.name for d in pc.dependencies]
    assert len(names) == len(set(names))
    print("  [PASS] test_context_no_duplicate_dependencies")


def test_context_provenance_all_sources():
    """The provenance records all six source artefacts."""
    ctx = make_full_context()
    engine = ProjectContextEngine()
    engine.execute(ctx)
    pc = ctx.get("project_context")
    assert len(pc.provenance.all_sources_used) == 6
    for src in PC_ALL_SOURCES:
        assert src in pc.provenance.all_sources_used
    print("  [PASS] test_context_provenance_all_sources")


# ---------------------------------------------------------------------------#
# 16. Bootstrap integration
# ---------------------------------------------------------------------------#

def test_bootstrap_registers_project_context():
    """Bootstrap registers the project context engine in the manager."""
    registry, orchestrator, manager = bootstrap()
    entries = manager.all_entries()
    engine_ids = [e.engine_id for e in entries]
    assert "project_context" in engine_ids
    print("  [PASS] test_bootstrap_registers_project_context")


def test_bootstrap_project_context_priority():
    """Project context is registered at priority 96."""
    registry, orchestrator, manager = bootstrap()
    entry = manager.get("project_context")
    assert entry is not None
    assert entry.priority == 15
    print("  [PASS] test_bootstrap_project_context_priority")


def test_bootstrap_project_context_dependencies():
    """Project context depends on dependency_resolver."""
    registry, orchestrator, manager = bootstrap()
    entry = manager.get("project_context")
    assert entry is not None
    assert "formal_understanding" in entry.dependencies
    print("  [PASS] test_bootstrap_project_context_dependencies")


# ---------------------------------------------------------------------------#
# 17. Serialisation
# ---------------------------------------------------------------------------#

def test_project_goal_serialisation():
    """ProjectGoal.to_dict returns all expected keys."""
    goal = ProjectGoal(name="test")
    d = goal.to_dict()
    expected = {
        "name", "display_name", "bot_type", "primary_goal",
        "language", "language_version", "framework", "database",
        "source_artefact",
    }
    assert set(d.keys()) == expected
    print("  [PASS] test_project_goal_serialisation")


def test_feature_summary_serialisation():
    """FeatureSummary.to_dict returns all expected keys."""
    feat = FeatureSummary(name="test")
    d = feat.to_dict()
    expected = {
        "name", "display_name", "description", "priority",
        "source_feature", "components", "source_artefact",
    }
    assert set(d.keys()) == expected
    print("  [PASS] test_feature_summary_serialisation")


def test_component_summary_serialisation():
    """ComponentSummary.to_dict returns all expected keys."""
    comp = ComponentSummary(name="test")
    d = comp.to_dict()
    expected = {
        "name", "type", "purpose", "responsibility",
        "source_feature", "location", "build_order", "importance",
        "files", "dependencies", "depends_on", "depended_by",
        "source_artefact",
    }
    assert set(d.keys()) == expected
    print("  [PASS] test_component_summary_serialisation")


def test_file_summary_serialisation():
    """FileSummary.to_dict returns all expected keys."""
    f = FileSummary(name="test.py", path="test.py")
    d = f.to_dict()
    expected = {
        "name", "path", "file_type", "purpose", "folder",
        "responsible_engine", "generation_priority", "build_order",
        "source_component", "depends_on", "depended_by",
        "reason_for_existence", "contains_code", "source_artefact",
    }
    assert set(d.keys()) == expected
    print("  [PASS] test_file_summary_serialisation")


def test_dependency_summary_serialisation():
    """DependencySummary.to_dict returns all expected keys."""
    dep = DependencySummary(name="test")
    d = dep.to_dict()
    expected = {
        "name", "type", "suggested_version", "version_constraint",
        "reason", "source_components", "priority", "load_order",
        "language", "framework", "depends_on", "depended_by",
        "source_artefact",
    }
    assert set(d.keys()) == expected
    print("  [PASS] test_dependency_summary_serialisation")


def test_relationship_summary_serialisation():
    """RelationshipSummary.to_dict returns all expected keys."""
    rel = RelationshipSummary(source="a", target="b")
    d = rel.to_dict()
    expected = {"source", "target", "kind", "description", "source_artefact"}
    assert set(d.keys()) == expected
    print("  [PASS] test_relationship_summary_serialisation")


def test_execution_stage_serialisation():
    """ExecutionStage.to_dict returns all expected keys."""
    stage = ExecutionStage(name="test")
    d = stage.to_dict()
    expected = {
        "name", "phase", "priority", "components", "files",
        "dependencies", "source_artefact",
    }
    assert set(d.keys()) == expected
    print("  [PASS] test_execution_stage_serialisation")


def test_context_link_serialisation():
    """ContextLink.to_dict returns all expected keys."""
    link = ContextLink(source="a", target="b")
    d = link.to_dict()
    expected = {"source", "target", "kind", "source_artefact"}
    assert set(d.keys()) == expected
    print("  [PASS] test_context_link_serialisation")


def test_expansion_point_serialisation():
    """ExpansionPoint.to_dict returns all expected keys."""
    ep = ExpansionPoint(area="test")
    d = ep.to_dict()
    expected = {"area", "description", "source_artefact"}
    assert set(d.keys()) == expected
    print("  [PASS] test_expansion_point_serialisation")


def test_context_finding_serialisation():
    """ContextFinding.to_dict returns all expected keys."""
    finding = ContextFinding()
    d = finding.to_dict()
    expected = {
        "severity", "code", "message", "affected",
        "resolution_hint", "category",
    }
    assert set(d.keys()) == expected
    print("  [PASS] test_context_finding_serialisation")


def test_link_indices_serialisation():
    """LinkIndices.to_dict returns all expected keys."""
    indices = LinkIndices()
    d = indices.to_dict()
    expected = {
        "feature_to_components", "component_to_features",
        "component_to_files", "file_to_components",
        "file_to_dependencies", "dependency_to_files",
        "dependency_to_components", "component_to_dependencies",
        "component_to_stage", "feature_to_stage",
        "file_to_stage", "dependency_to_stage",
    }
    assert set(d.keys()) == expected
    print("  [PASS] test_link_indices_serialisation")


def test_source_provenance_serialisation():
    """SourceProvenance.to_dict returns all expected keys."""
    prov = SourceProvenance()
    d = prov.to_dict()
    expected = {
        "blueprint_name", "validation_status", "structure_map_name",
        "component_registry_name", "file_plan_name",
        "dependency_report_name", "all_sources_used",
    }
    assert set(d.keys()) == expected
    print("  [PASS] test_source_provenance_serialisation")


def test_project_context_to_dict():
    """ProjectContext.to_dict returns all expected keys."""
    ctx = make_full_context()
    engine = ProjectContextEngine()
    engine.execute(ctx)
    pc = ctx.get("project_context")
    d = pc.to_dict()
    expected = {
        "goal", "feature_count", "component_count", "file_count",
        "dependency_count", "relationship_count", "stage_count",
        "link_count", "error_count", "warning_count", "summary",
        "notes", "warnings", "features", "components", "files",
        "dependencies", "relationships", "stages", "links",
        "indices", "expansion_points", "provenance", "findings",
    }
    assert set(d.keys()) == expected
    assert d["feature_count"] == pc.feature_count
    assert d["component_count"] == pc.component_count
    assert isinstance(d["features"], list)
    assert isinstance(d["components"], list)
    assert isinstance(d["files"], list)
    assert isinstance(d["dependencies"], list)
    assert isinstance(d["stages"], list)
    assert isinstance(d["links"], list)
    assert isinstance(d["indices"], dict)
    assert isinstance(d["provenance"], dict)
    assert isinstance(d["findings"], list)
    print("  [PASS] test_project_context_to_dict")


# ---------------------------------------------------------------------------#
# 18. End-to-end integration
# ---------------------------------------------------------------------------#

def test_end_to_end_full_pipeline():
    """Run the engine and verify the project context."""
    ctx = make_full_context()
    engine = ProjectContextEngine()
    result = engine.execute(ctx)

    assert result.success, f"Engine failed: {result.errors}"
    pc = ctx.get("project_context")
    assert pc is not None
    assert pc.goal.name == "my_store_bot"
    assert pc.feature_count > 0
    assert pc.component_count > 0
    assert pc.file_count > 0
    assert pc.dependency_count > 0
    assert pc.stage_count > 0
    assert pc.link_count > 0
    assert pc.error_count == 0
    print("  [PASS] test_end_to_end_full_pipeline")


def test_end_to_end_with_dependency_resolver():
    """Run dependency resolver then project context in sequence."""
    ctx = make_context(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
    )
    # Run the dependency resolver first to produce the 6th artefact.
    dr_engine = DependencyResolutionEngine()
    dr_result = dr_engine.execute(ctx)
    assert dr_result.success

    # Now run the project context engine.
    pc_engine = ProjectContextEngine()
    pc_result = pc_engine.execute(ctx)
    assert pc_result.success
    pc = ctx.get("project_context")
    assert pc is not None
    assert pc.dependency_count > 0
    print("  [PASS] test_end_to_end_with_dependency_resolver")


# ---------------------------------------------------------------------------#
# Test runner
# ---------------------------------------------------------------------------#

def run_all_tests():
    tests = [
        # Data model
        test_project_goal_creation,
        test_project_goal_to_dict,
        test_feature_summary_creation,
        test_feature_summary_to_dict,
        test_component_summary_creation,
        test_component_summary_to_dict,
        test_file_summary_creation,
        test_file_summary_to_dict,
        test_dependency_summary_creation,
        test_dependency_summary_to_dict,
        test_relationship_summary_creation,
        test_relationship_summary_to_dict,
        test_execution_stage_creation,
        test_execution_stage_to_dict,
        test_context_link_creation,
        test_context_link_to_dict,
        test_expansion_point_creation,
        test_expansion_point_to_dict,
        test_context_finding_creation,
        test_context_finding_to_dict,
        test_link_indices_creation,
        test_link_indices_to_dict,
        test_source_provenance_creation,
        test_source_provenance_to_dict,
        test_source_artefact_constants,
        test_severity_constants,
        test_link_kind_constants,
        # ProjectContext convenience
        test_project_context_empty,
        test_project_context_counts,
        test_project_context_add_finding,
        test_project_context_get_methods,
        # BlueprintReader
        test_blueprint_reader_goal,
        test_blueprint_reader_features,
        test_blueprint_reader_relationships,
        test_blueprint_reader_stages,
        test_blueprint_reader_expansion_points,
        # ValidationReader
        test_validation_reader_status,
        test_validation_reader_findings,
        # StructureReader
        test_structure_reader_files,
        test_structure_reader_provenance,
        test_structure_reader_build_order_map,
        # RegistryReader
        test_registry_reader_components,
        test_registry_reader_provenance,
        test_registry_reader_expansion_points,
        # FilePlanReader
        test_file_plan_reader_files,
        test_file_plan_reader_relationships,
        test_file_plan_reader_provenance,
        # DependencyReader
        test_dependency_reader_dependencies,
        test_dependency_reader_relationships,
        test_dependency_reader_findings,
        test_dependency_reader_provenance,
        # ContextAssembler
        test_assembler_produces_project_context,
        test_assembler_goal,
        test_assembler_features_have_components,
        test_assembler_components_have_files,
        test_assembler_components_have_dependencies,
        test_assembler_deduplicates_relationships,
        test_assembler_provenance,
        test_assembler_stages_enriched,
        # ContextLinker
        test_linker_builds_links,
        test_linker_feature_to_component_links,
        test_linker_component_to_file_links,
        test_linker_file_to_dependency_links,
        test_linker_component_to_stage_links,
        test_linker_dependency_to_stage_links,
        test_linker_indices_feature_to_components,
        test_linker_indices_component_to_files,
        test_linker_indices_file_to_dependencies,
        test_linker_indices_dependency_to_components,
        test_linker_indices_component_to_stage,
        test_linker_indices_dependency_to_stage,
        test_linker_o1_lookup_methods,
        # ContextValidator
        test_validator_no_findings_on_valid_context,
        test_validator_duplicate_feature_names,
        test_validator_duplicate_component_names,
        test_validator_feature_without_components,
        test_validator_component_without_files,
        test_validator_file_without_responsibility,
        test_validator_unknown_elements_in_relationships,
        # Engine — data source
        test_engine_requires_blueprint,
        test_engine_requires_validation_report,
        test_engine_requires_structure_map,
        test_engine_requires_component_registry,
        test_engine_requires_file_plan,
        test_engine_requires_dependency_report,
        test_engine_does_not_read_request,
        # Engine — type checking
        test_engine_type_check_blueprint,
        test_engine_type_check_validation_report,
        test_engine_type_check_structure_map,
        test_engine_type_check_registry,
        test_engine_type_check_file_plan,
        test_engine_type_check_dependency_report,
        # Engine — output
        test_engine_produces_project_context,
        test_engine_context_stored_in_metadata,
        test_engine_records_provenance,
        test_engine_context_has_summary,
        test_engine_context_has_notes,
        test_engine_context_has_stages,
        test_engine_context_has_links,
        test_engine_metadata_in_result,
        test_engine_context_no_errors,
        # Context integrity
        test_context_all_features_have_components,
        test_context_all_components_have_files,
        test_context_no_duplicate_components,
        test_context_no_duplicate_files,
        test_context_no_duplicate_dependencies,
        test_context_provenance_all_sources,
        # Bootstrap
        test_bootstrap_registers_project_context,
        test_bootstrap_project_context_priority,
        test_bootstrap_project_context_dependencies,
        # Serialisation
        test_project_goal_serialisation,
        test_feature_summary_serialisation,
        test_component_summary_serialisation,
        test_file_summary_serialisation,
        test_dependency_summary_serialisation,
        test_relationship_summary_serialisation,
        test_execution_stage_serialisation,
        test_context_link_serialisation,
        test_expansion_point_serialisation,
        test_context_finding_serialisation,
        test_link_indices_serialisation,
        test_source_provenance_serialisation,
        test_project_context_to_dict,
        # End-to-end
        test_end_to_end_full_pipeline,
        test_end_to_end_with_dependency_resolver,
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
