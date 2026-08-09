#!/usr/bin/env python3
"""
Comprehensive test suite for the Project Intelligence Graph Engine
(Specification 011).

These tests cover every aspect of the specification:

1. Data model integrity (GraphNode, GraphEdge, GraphFinding,
   GraphIndices, GraphProvenance, ProjectIntelligenceGraph, source
   constants, severity constants, node-type constants, edge-kind
   constants, category constants).
2. The GraphBuilder (converts seven artefacts into nodes and edges,
   deduplicates nodes by (type, name), deduplicates edges by
   (source_id, kind, target_id), builds provenance).
3. The GraphNavigator (builds all eleven O(1) look-up indices:
   node_by_id, nodes_by_type, node_by_name, node_id_by_type_and_name,
   edges_by_source, edges_by_target, out_edges, in_edges,
   out_edges_by_kind, in_edges_by_kind, edges_by_kind).
4. The CircularDetector (circular dependencies via DFS, broken
   references, unused components, orphan files, dead components).
5. The GraphValidator (duplicate node IDs, duplicate edge IDs, edges
   referencing non-existent nodes, unknown node types, unknown edge
   kinds, empty required fields, self-loops, project node existence,
   indices consistency).
6. The main engine reads ONLY the seven upstream artefacts
   (project_blueprint, blueprint_validation_report,
   project_structure_map, component_registry, file_generation_plan,
   dependency_resolution_report, project_context) and NOT the raw
   request.
7. The main engine fails when each of the seven artefacts is
   missing.
8. The main engine fails when the artefacts are the wrong type.
9. The engine produces a ProjectIntelligenceGraph artefact.
10. The engine stores the graph in both context.artefacts and
    context.metadata.
11. The graph records the source artefacts (provenance).
12. The graph has a summary, notes, and warnings.
13. The graph has O(1) look-up methods (get_node, get_node_by_name,
    get_node_by_type_and_name, nodes_of_type, outgoing, incoming,
    edges_from, edges_to, edges_of_kind, neighbours, reachable,
    shortest_path).
14. Bootstrap integration (engine registered at priority 97, depends
    on project_context).
15. Serialisation (to_dict) for all data model classes.
16. End-to-end pipeline (build graph from all seven artefacts,
    verify nodes, edges, indices, findings, provenance, navigation).
"""

import sys
import os

# Ensure the package is importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path

from telegram_bot_engine.core import build_configuration, bootstrap
from telegram_bot_engine.core.context import GenerationContext
from telegram_bot_engine.core.result import StageResult
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
    ALL_SOURCES as PC_ALL_SOURCES,
)
from telegram_bot_engine.engines.generators.intelligence_graph import (
    IntelligenceGraphEngine,
    ProjectIntelligenceGraph,
    GraphNode,
    GraphEdge,
    GraphFinding,
    GraphIndices,
    GraphProvenance,
    GraphBuilder,
    GraphNavigator,
    CircularDetector,
    GraphValidator,
    # Source-artefact constants
    SOURCE_BLUEPRINT,
    SOURCE_VALIDATION,
    SOURCE_STRUCTURE,
    SOURCE_COMPONENT_REGISTRY,
    SOURCE_FILE_PLAN,
    SOURCE_DEPENDENCY_REPORT,
    SOURCE_PROJECT_CONTEXT,
    ALL_SOURCES,
    # Severity constants
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    SEVERITY_INFO,
    ALL_SEVERITIES,
    # Node-type constants
    NODE_TYPE_PROJECT,
    NODE_TYPE_FOLDER,
    NODE_TYPE_FILE,
    NODE_TYPE_CLASS,
    NODE_TYPE_FUNCTION,
    NODE_TYPE_INTERFACE,
    NODE_TYPE_COMPONENT,
    NODE_TYPE_FEATURE,
    NODE_TYPE_DEPENDENCY,
    NODE_TYPE_LIBRARY,
    NODE_TYPE_DATABASE_TABLE,
    NODE_TYPE_ROUTE,
    NODE_TYPE_COMMAND,
    NODE_TYPE_CONFIGURATION,
    NODE_TYPE_ENVIRONMENT_VARIABLE,
    NODE_TYPE_SERVICE,
    NODE_TYPE_MIDDLEWARE,
    NODE_TYPE_REPOSITORY,
    NODE_TYPE_STAGE,
    ALL_NODE_TYPES,
    # Edge-kind constants
    EDGE_USES,
    EDGE_IMPORTS,
    EDGE_DEPENDS_ON,
    EDGE_CALLS,
    EDGE_CREATES,
    EDGE_READS,
    EDGE_WRITES,
    EDGE_EXTENDS,
    EDGE_IMPLEMENTS,
    EDGE_CONTAINS,
    EDGE_REFERENCES,
    EDGE_REQUIRED_BY,
    ALL_EDGE_KINDS,
    # Category constants
    CATEGORY_CIRCULAR_DEPENDENCY,
    CATEGORY_BROKEN_REFERENCE,
    CATEGORY_UNUSED_COMPONENT,
    CATEGORY_ORPHAN_FILE,
    CATEGORY_DEAD_COMPONENT,
    CATEGORY_CONSISTENCY,
    CATEGORY_STRUCTURE,
    ALL_CATEGORIES,
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
    project_context=None,
):
    """Build a generation context with the seven intelligence-graph
    artefacts.

    The request field is intentionally set to a string that the engine
    must NOT read.
    """
    ctx = GenerationContext(
        request="test request (must not be read by intelligence graph)",
        config=make_config(),
        work_dir=Path("/tmp/test_intelligence_graph"),
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
    if project_context is not None:
        ctx.set("project_context", project_context)
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


def make_project_context_artefact(name="my_store_bot"):
    """Run the Project Context Engine to produce the 7th artefact."""
    ctx = make_context(
        blueprint=make_valid_blueprint(name),
        validation_report=make_approved_report(name),
        structure_map=make_structure_map(name),
        registry=make_component_registry(name),
        file_plan=make_file_plan(name),
        dependency_report=make_dependency_report(name),
    )
    pc_engine = ProjectContextEngine()
    pc_result = pc_engine.execute(ctx)
    assert pc_result.success, f"ProjectContext failed: {pc_result.errors}"
    pc = ctx.get("project_context")
    assert pc is not None
    assert isinstance(pc, ProjectContext)
    return pc


def make_full_context(name="my_store_bot"):
    """Build a context with all seven artefacts set."""
    blueprint = make_valid_blueprint(name)
    report = make_approved_report(name)
    structure_map = make_structure_map(name)
    registry = make_component_registry(name)
    file_plan = make_file_plan(name)
    dependency_report = make_dependency_report(name)
    project_context = make_project_context_artefact(name)
    return make_context(
        blueprint=blueprint,
        validation_report=report,
        structure_map=structure_map,
        registry=registry,
        file_plan=file_plan,
        dependency_report=dependency_report,
        project_context=project_context,
    )

# ---------------------------------------------------------------------------#
# 1. Data model tests
# ---------------------------------------------------------------------------#

def test_graph_node_creation():
    """GraphNode can be created and has the right defaults."""
    node = GraphNode()
    assert node.node_id == ""
    assert node.type == NODE_TYPE_COMPONENT
    assert node.name == ""
    assert node.display_name == ""
    assert node.description == ""
    assert node.priority == 100
    assert node.owner_engine == ""
    assert node.source == SOURCE_BLUEPRINT
    assert node.metadata == {}
    assert node.neighbours == []
    print("  [PASS] test_graph_node_creation")


def test_graph_node_to_dict():
    """GraphNode.to_dict returns the right structure."""
    node = GraphNode(
        node_id="component:core",
        type=NODE_TYPE_COMPONENT,
        name="core",
        display_name="Core",
        description="Core bot logic",
        priority=10,
        owner_engine="component_detector",
        source=SOURCE_COMPONENT_REGISTRY,
        metadata={"importance": "critical"},
        neighbours=["file:src/core/handler.py"],
    )
    d = node.to_dict()
    assert d["node_id"] == "component:core"
    assert d["type"] == NODE_TYPE_COMPONENT
    assert d["name"] == "core"
    assert d["display_name"] == "Core"
    assert d["description"] == "Core bot logic"
    assert d["priority"] == 10
    assert d["owner_engine"] == "component_detector"
    assert d["source"] == SOURCE_COMPONENT_REGISTRY
    assert d["metadata"] == {"importance": "critical"}
    assert d["neighbours"] == ["file:src/core/handler.py"]
    print("  [PASS] test_graph_node_to_dict")


def test_graph_edge_creation():
    """GraphEdge can be created and has the right defaults."""
    edge = GraphEdge()
    assert edge.edge_id == ""
    assert edge.source_id == ""
    assert edge.target_id == ""
    assert edge.kind == EDGE_DEPENDS_ON
    assert edge.source == SOURCE_BLUEPRINT
    assert edge.description == ""
    print("  [PASS] test_graph_edge_creation")


def test_graph_edge_to_dict():
    """GraphEdge.to_dict returns the right structure."""
    edge = GraphEdge(
        edge_id="component:core--depends_on-->dependency:aiogram",
        source_id="component:core",
        target_id="dependency:aiogram",
        kind=EDGE_DEPENDS_ON,
        source=SOURCE_DEPENDENCY_REPORT,
        description="Core depends on aiogram",
    )
    d = edge.to_dict()
    assert d["edge_id"] == "component:core--depends_on-->dependency:aiogram"
    assert d["source_id"] == "component:core"
    assert d["target_id"] == "dependency:aiogram"
    assert d["kind"] == EDGE_DEPENDS_ON
    assert d["source"] == SOURCE_DEPENDENCY_REPORT
    assert d["description"] == "Core depends on aiogram"
    print("  [PASS] test_graph_edge_to_dict")


def test_graph_finding_creation():
    """GraphFinding can be created and has the right defaults."""
    f = GraphFinding()
    assert f.severity == SEVERITY_WARNING
    assert f.code == ""
    assert f.message == ""
    assert f.affected == ""
    assert f.category == CATEGORY_CONSISTENCY
    assert f.resolution_hint == ""
    assert f.cycle == []
    print("  [PASS] test_graph_finding_creation")


def test_graph_finding_to_dict():
    """GraphFinding.to_dict returns the right structure."""
    f = GraphFinding(
        severity=SEVERITY_ERROR,
        code="circular_dependency",
        message="A -> B -> A",
        affected="component:core",
        category=CATEGORY_CIRCULAR_DEPENDENCY,
        resolution_hint="Break the cycle",
        cycle=["component:core", "component:database", "component:core"],
    )
    d = f.to_dict()
    assert d["severity"] == SEVERITY_ERROR
    assert d["code"] == "circular_dependency"
    assert d["message"] == "A -> B -> A"
    assert d["affected"] == "component:core"
    assert d["category"] == CATEGORY_CIRCULAR_DEPENDENCY
    assert d["resolution_hint"] == "Break the cycle"
    assert d["cycle"] == ["component:core", "component:database", "component:core"]
    print("  [PASS] test_graph_finding_to_dict")


def test_graph_indices_creation():
    """GraphIndices can be created and has the right defaults."""
    indices = GraphIndices()
    assert indices.node_by_id == {}
    assert indices.nodes_by_type == {}
    assert indices.node_by_name == {}
    assert indices.node_id_by_type_and_name == {}
    assert indices.edges_by_source == {}
    assert indices.edges_by_target == {}
    assert indices.out_edges == {}
    assert indices.in_edges == {}
    assert indices.out_edges_by_kind == {}
    assert indices.in_edges_by_kind == {}
    assert indices.edges_by_kind == {}
    print("  [PASS] test_graph_indices_creation")


def test_graph_indices_to_dict():
    """GraphIndices.to_dict returns the right structure."""
    indices = GraphIndices()
    indices.node_by_id["component:core"] = GraphNode(
        node_id="component:core",
        type=NODE_TYPE_COMPONENT,
        name="core",
    )
    indices.nodes_by_type[NODE_TYPE_COMPONENT] = ["component:core"]
    indices.node_by_name["core"] = "component:core"
    d = indices.to_dict()
    assert d["node_count"] == 1
    assert NODE_TYPE_COMPONENT in d["nodes_by_type"]
    assert d["node_by_name"] == {"core": "component:core"}
    print("  [PASS] test_graph_indices_to_dict")


def test_graph_provenance_creation():
    """GraphProvenance can be created and has the right defaults."""
    prov = GraphProvenance()
    assert prov.project_name == ""
    assert prov.blueprint_name == ""
    assert prov.validation_status == ""
    assert prov.structure_map_name == ""
    assert prov.component_registry_name == ""
    assert prov.file_plan_name == ""
    assert prov.dependency_report_name == ""
    assert prov.project_context_name == ""
    assert prov.all_sources_used == []
    print("  [PASS] test_graph_provenance_creation")


def test_graph_provenance_to_dict():
    """GraphProvenance.to_dict returns the right structure."""
    prov = GraphProvenance(
        project_name="my_store_bot",
        blueprint_name="my_store_bot",
        validation_status=STATUS_APPROVED,
        structure_map_name="my_store_bot",
        component_registry_name="my_store_bot",
        file_plan_name="my_store_bot",
        dependency_report_name="my_store_bot",
        project_context_name="my_store_bot",
        all_sources_used=list(ALL_SOURCES),
    )
    d = prov.to_dict()
    assert d["project_name"] == "my_store_bot"
    assert d["blueprint_name"] == "my_store_bot"
    assert d["validation_status"] == STATUS_APPROVED
    assert d["structure_map_name"] == "my_store_bot"
    assert d["component_registry_name"] == "my_store_bot"
    assert d["file_plan_name"] == "my_store_bot"
    assert d["dependency_report_name"] == "my_store_bot"
    assert d["project_context_name"] == "my_store_bot"
    assert len(d["all_sources_used"]) == 7
    print("  [PASS] test_graph_provenance_to_dict")


def test_source_artefact_constants():
    """The source-artefact constants are the seven artefact IDs."""
    assert SOURCE_BLUEPRINT == "blueprint"
    assert SOURCE_VALIDATION == "validation"
    assert SOURCE_STRUCTURE == "structure"
    assert SOURCE_COMPONENT_REGISTRY == "component_registry"
    assert SOURCE_FILE_PLAN == "file_plan"
    assert SOURCE_DEPENDENCY_REPORT == "dependency_report"
    assert SOURCE_PROJECT_CONTEXT == "project_context"
    assert len(ALL_SOURCES) == 7
    assert SOURCE_PROJECT_CONTEXT in ALL_SOURCES
    print("  [PASS] test_source_artefact_constants")


def test_severity_constants():
    """The severity constants are error, warning, info."""
    assert SEVERITY_ERROR == "error"
    assert SEVERITY_WARNING == "warning"
    assert SEVERITY_INFO == "info"
    assert len(ALL_SEVERITIES) == 3
    print("  [PASS] test_severity_constants")


def test_node_type_constants():
    """There are exactly 19 node types."""
    assert len(ALL_NODE_TYPES) == 19
    assert NODE_TYPE_PROJECT in ALL_NODE_TYPES
    assert NODE_TYPE_FOLDER in ALL_NODE_TYPES
    assert NODE_TYPE_FILE in ALL_NODE_TYPES
    assert NODE_TYPE_CLASS in ALL_NODE_TYPES
    assert NODE_TYPE_FUNCTION in ALL_NODE_TYPES
    assert NODE_TYPE_INTERFACE in ALL_NODE_TYPES
    assert NODE_TYPE_COMPONENT in ALL_NODE_TYPES
    assert NODE_TYPE_FEATURE in ALL_NODE_TYPES
    assert NODE_TYPE_DEPENDENCY in ALL_NODE_TYPES
    assert NODE_TYPE_LIBRARY in ALL_NODE_TYPES
    assert NODE_TYPE_DATABASE_TABLE in ALL_NODE_TYPES
    assert NODE_TYPE_ROUTE in ALL_NODE_TYPES
    assert NODE_TYPE_COMMAND in ALL_NODE_TYPES
    assert NODE_TYPE_CONFIGURATION in ALL_NODE_TYPES
    assert NODE_TYPE_ENVIRONMENT_VARIABLE in ALL_NODE_TYPES
    assert NODE_TYPE_SERVICE in ALL_NODE_TYPES
    assert NODE_TYPE_MIDDLEWARE in ALL_NODE_TYPES
    assert NODE_TYPE_REPOSITORY in ALL_NODE_TYPES
    assert NODE_TYPE_STAGE in ALL_NODE_TYPES
    print("  [PASS] test_node_type_constants")


def test_edge_kind_constants():
    """There are exactly 12 edge kinds."""
    assert len(ALL_EDGE_KINDS) == 12
    assert EDGE_USES in ALL_EDGE_KINDS
    assert EDGE_IMPORTS in ALL_EDGE_KINDS
    assert EDGE_DEPENDS_ON in ALL_EDGE_KINDS
    assert EDGE_CALLS in ALL_EDGE_KINDS
    assert EDGE_CREATES in ALL_EDGE_KINDS
    assert EDGE_READS in ALL_EDGE_KINDS
    assert EDGE_WRITES in ALL_EDGE_KINDS
    assert EDGE_EXTENDS in ALL_EDGE_KINDS
    assert EDGE_IMPLEMENTS in ALL_EDGE_KINDS
    assert EDGE_CONTAINS in ALL_EDGE_KINDS
    assert EDGE_REFERENCES in ALL_EDGE_KINDS
    assert EDGE_REQUIRED_BY in ALL_EDGE_KINDS
    print("  [PASS] test_edge_kind_constants")


def test_category_constants():
    """The category constants are defined for all detection types."""
    assert len(ALL_CATEGORIES) == 7
    assert CATEGORY_CIRCULAR_DEPENDENCY in ALL_CATEGORIES
    assert CATEGORY_BROKEN_REFERENCE in ALL_CATEGORIES
    assert CATEGORY_UNUSED_COMPONENT in ALL_CATEGORIES
    assert CATEGORY_ORPHAN_FILE in ALL_CATEGORIES
    assert CATEGORY_DEAD_COMPONENT in ALL_CATEGORIES
    assert CATEGORY_CONSISTENCY in ALL_CATEGORIES
    assert CATEGORY_STRUCTURE in ALL_CATEGORIES
    print("  [PASS] test_category_constants")


# ---------------------------------------------------------------------------#
# 2. ProjectIntelligenceGraph convenience properties
# ---------------------------------------------------------------------------#

def test_graph_empty():
    """An empty graph has zero counts."""
    g = ProjectIntelligenceGraph()
    assert g.node_count == 0
    assert g.edge_count == 0
    assert g.finding_count == 0
    assert g.is_empty is True
    assert g.has_errors is False
    assert g.error_count == 0
    assert g.warning_count == 0
    print("  [PASS] test_graph_empty")


def test_graph_counts():
    """The convenience properties reflect the node/edge/finding counts."""
    g = ProjectIntelligenceGraph()
    g.nodes = [GraphNode(node_id="component:core", type=NODE_TYPE_COMPONENT, name="core")]
    g.edges = [GraphEdge(edge_id="e1", source_id="component:core", target_id="component:core", kind=EDGE_USES)]
    g.findings = [GraphFinding(severity=SEVERITY_WARNING, code="test", message="test")]
    assert g.node_count == 1
    assert g.edge_count == 1
    assert g.finding_count == 1
    assert g.is_empty is False
    assert g.warning_count == 1
    print("  [PASS] test_graph_counts")


def test_graph_has_errors():
    """has_errors is True when there are error-level findings."""
    g = ProjectIntelligenceGraph()
    g.findings = [
        GraphFinding(severity=SEVERITY_ERROR, code="err", message="err"),
        GraphFinding(severity=SEVERITY_WARNING, code="warn", message="warn"),
    ]
    assert g.has_errors is True
    assert g.error_count == 1
    assert g.warning_count == 1
    print("  [PASS] test_graph_has_errors")


def test_graph_add_finding():
    """add_finding appends to the findings list and warnings."""
    g = ProjectIntelligenceGraph()
    g.add_finding(
        severity=SEVERITY_ERROR,
        code="test_error",
        message="Test error",
        affected="component:core",
        category=CATEGORY_CIRCULAR_DEPENDENCY,
    )
    g.add_finding(
        severity=SEVERITY_WARNING,
        code="test_warning",
        message="Test warning",
    )
    assert g.finding_count == 2
    assert g.error_count == 1
    assert g.warning_count == 1
    assert "Test warning" in g.warnings
    print("  [PASS] test_graph_add_finding")


def test_graph_get_node_methods():
    """get_node, get_node_by_name, get_node_by_type_and_name work."""
    g = ProjectIntelligenceGraph()
    node = GraphNode(
        node_id="component:core",
        type=NODE_TYPE_COMPONENT,
        name="core",
        display_name="Core",
    )
    g.nodes = [node]
    g.indices.node_by_id["component:core"] = node
    g.indices.node_by_name["core"] = "component:core"
    g.indices.node_id_by_type_and_name[(NODE_TYPE_COMPONENT, "core")] = "component:core"
    g.indices.nodes_by_type[NODE_TYPE_COMPONENT] = ["component:core"]

    assert g.get_node("component:core") is node
    assert g.get_node("nonexistent") is None
    assert g.get_node_by_name("core") is node
    assert g.get_node_by_name("nonexistent") is None
    assert g.get_node_by_type_and_name(NODE_TYPE_COMPONENT, "core") is node
    assert g.get_node_by_type_and_name(NODE_TYPE_COMPONENT, "nonexistent") is None
    print("  [PASS] test_graph_get_node_methods")


def test_graph_nodes_of_type():
    """nodes_of_type and node_ids_of_type return the right nodes."""
    g = ProjectIntelligenceGraph()
    n1 = GraphNode(node_id="component:core", type=NODE_TYPE_COMPONENT, name="core")
    n2 = GraphNode(node_id="component:db", type=NODE_TYPE_COMPONENT, name="db")
    g.nodes = [n1, n2]
    g.indices.node_by_id["component:core"] = n1
    g.indices.node_by_id["component:db"] = n2
    g.indices.nodes_by_type[NODE_TYPE_COMPONENT] = ["component:core", "component:db"]
    g.indices.nodes_by_type[NODE_TYPE_FILE] = []

    nodes = g.nodes_of_type(NODE_TYPE_COMPONENT)
    assert len(nodes) == 2
    assert n1 in nodes
    assert n2 in nodes
    ids = g.node_ids_of_type(NODE_TYPE_COMPONENT)
    assert "component:core" in ids
    assert "component:db" in ids
    assert g.nodes_of_type(NODE_TYPE_FILE) == []
    print("  [PASS] test_graph_nodes_of_type")


def test_graph_outgoing_incoming():
    """outgoing and incoming return the right node IDs."""
    g = ProjectIntelligenceGraph()
    g.indices.out_edges["component:core"] = ["component:db", "dependency:aiogram"]
    g.indices.in_edges["component:core"] = ["feature:catalog"]
    assert g.outgoing("component:core") == ["component:db", "dependency:aiogram"]
    assert g.incoming("component:core") == ["feature:catalog"]
    assert g.outgoing("nonexistent") == []
    assert g.incoming("nonexistent") == []
    print("  [PASS] test_graph_outgoing_incoming")


def test_graph_outgoing_incoming_by_kind():
    """outgoing_by_kind and incoming_by_kind return the right node IDs."""
    g = ProjectIntelligenceGraph()
    g.indices.out_edges_by_kind[("component:core", EDGE_DEPENDS_ON)] = ["dependency:aiogram"]
    g.indices.in_edges_by_kind[("component:core", EDGE_USES)] = ["feature:catalog"]
    assert g.outgoing_by_kind("component:core", EDGE_DEPENDS_ON) == ["dependency:aiogram"]
    assert g.incoming_by_kind("component:core", EDGE_USES) == ["feature:catalog"]
    assert g.outgoing_by_kind("component:core", EDGE_CALLS) == []
    print("  [PASS] test_graph_outgoing_incoming_by_kind")


def test_graph_edges_from_to_of_kind():
    """edges_from, edges_to, edges_of_kind return the right edges."""
    g = ProjectIntelligenceGraph()
    e1 = GraphEdge(edge_id="e1", source_id="a", target_id="b", kind=EDGE_USES)
    e2 = GraphEdge(edge_id="e2", source_id="c", target_id="a", kind=EDGE_CONTAINS)
    g.edges = [e1, e2]
    g.indices.edges_by_source["a"] = [e1]
    g.indices.edges_by_target["a"] = [e2]
    g.indices.edges_by_kind[EDGE_USES] = [e1]
    g.indices.edges_by_kind[EDGE_CONTAINS] = [e2]

    assert g.edges_from("a") == [e1]
    assert g.edges_to("a") == [e2]
    assert g.edges_of_kind(EDGE_USES) == [e1]
    assert g.edges_of_kind(EDGE_CONTAINS) == [e2]
    print("  [PASS] test_graph_edges_from_to_of_kind")


def test_graph_neighbours():
    """neighbours returns all directly connected node IDs (both directions)."""
    g = ProjectIntelligenceGraph()
    g.indices.out_edges["a"] = ["b", "c"]
    g.indices.in_edges["a"] = ["d"]
    n = g.neighbours("a")
    assert set(n) == {"b", "c", "d"}
    assert len(n) == 3
    print("  [PASS] test_graph_neighbours")


def test_graph_reachable():
    """reachable returns all nodes within max_hops (BFS)."""
    g = ProjectIntelligenceGraph()
    g.indices.node_by_id["a"] = GraphNode(node_id="a")
    g.indices.node_by_id["b"] = GraphNode(node_id="b")
    g.indices.node_by_id["c"] = GraphNode(node_id="c")
    g.indices.out_edges["a"] = ["b"]
    g.indices.out_edges["b"] = ["c"]
    g.indices.out_edges["c"] = []
    result = g.reachable("a", max_hops=4)
    assert "a" in result
    assert "b" in result
    assert "c" in result
    print("  [PASS] test_graph_reachable")


def test_graph_shortest_path():
    """shortest_path returns the shortest path between two nodes."""
    g = ProjectIntelligenceGraph()
    for nid in ["a", "b", "c", "d"]:
        g.indices.node_by_id[nid] = GraphNode(node_id=nid)
    g.indices.out_edges["a"] = ["b"]
    g.indices.out_edges["b"] = ["c"]
    g.indices.out_edges["c"] = ["d"]
    path = g.shortest_path("a", "d")
    assert path == ["a", "b", "c", "d"]
    path = g.shortest_path("a", "a")
    assert path == ["a"]
    path = g.shortest_path("a", "nonexistent")
    assert path == []
    print("  [PASS] test_graph_shortest_path")


# ---------------------------------------------------------------------------#
# 3. GraphBuilder tests
# ---------------------------------------------------------------------------#

def test_builder_produces_graph():
    """GraphBuilder.build produces a ProjectIntelligenceGraph."""
    builder = GraphBuilder()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    assert isinstance(graph, ProjectIntelligenceGraph)
    assert graph.node_count > 0
    assert graph.edge_count > 0
    print("  [PASS] test_builder_produces_graph")


def test_builder_creates_project_node():
    """The builder creates a project node from the blueprint."""
    builder = GraphBuilder()
    graph = builder.build(
        blueprint=make_valid_blueprint("my_store_bot"),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    project_nodes = [n for n in graph.nodes if n.type == NODE_TYPE_PROJECT]
    assert len(project_nodes) == 1
    assert project_nodes[0].name == "my_store_bot"
    print("  [PASS] test_builder_creates_project_node")


def test_builder_creates_feature_nodes():
    """The builder creates feature nodes from the blueprint."""
    builder = GraphBuilder()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    feature_nodes = [n for n in graph.nodes if n.type == NODE_TYPE_FEATURE]
    assert len(feature_nodes) >= 1
    names = {n.name for n in feature_nodes}
    assert "store" in names
    print("  [PASS] test_builder_creates_feature_nodes")


def test_builder_creates_component_nodes():
    """The builder creates component nodes from the registry."""
    builder = GraphBuilder()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    component_nodes = [n for n in graph.nodes if n.type == NODE_TYPE_COMPONENT]
    assert len(component_nodes) >= 3
    names = {n.name for n in component_nodes}
    assert "core" in names
    assert "database" in names
    print("  [PASS] test_builder_creates_component_nodes")


def test_builder_creates_stage_nodes():
    """The builder creates stage nodes from the blueprint execution plan."""
    builder = GraphBuilder()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    stage_nodes = [n for n in graph.nodes if n.type == NODE_TYPE_STAGE]
    assert len(stage_nodes) >= 3
    print("  [PASS] test_builder_creates_stage_nodes")


def test_builder_creates_folder_nodes():
    """The builder creates folder nodes from the structure map."""
    builder = GraphBuilder()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    folder_nodes = [n for n in graph.nodes if n.type == NODE_TYPE_FOLDER]
    assert len(folder_nodes) >= 4
    print("  [PASS] test_builder_creates_folder_nodes")


def test_builder_creates_file_nodes():
    """The builder creates file nodes from the structure map and file plan."""
    builder = GraphBuilder()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    file_nodes = [n for n in graph.nodes if n.type == NODE_TYPE_FILE]
    assert len(file_nodes) >= 6
    print("  [PASS] test_builder_creates_file_nodes")


def test_builder_creates_dependency_nodes():
    """The builder creates dependency and library nodes from the
    dependency report."""
    builder = GraphBuilder()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    dep_nodes = [n for n in graph.nodes if n.type == NODE_TYPE_DEPENDENCY]
    lib_nodes = [n for n in graph.nodes if n.type == NODE_TYPE_LIBRARY]
    total = len(dep_nodes) + len(lib_nodes)
    assert total >= 4
    all_names = {n.name for n in dep_nodes} | {n.name for n in lib_nodes}
    assert "python-telegram-bot" in all_names
    assert "SQLAlchemy" in all_names
    print("  [PASS] test_builder_creates_dependency_nodes")


def test_builder_creates_route_nodes():
    """The builder creates route nodes from the blueprint features."""
    builder = GraphBuilder()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    route_nodes = [n for n in graph.nodes if n.type == NODE_TYPE_ROUTE]
    assert len(route_nodes) >= 1
    print("  [PASS] test_builder_creates_route_nodes")


def test_builder_creates_command_nodes():
    """The builder creates command nodes from the blueprint features."""
    builder = GraphBuilder()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    command_nodes = [n for n in graph.nodes if n.type == NODE_TYPE_COMMAND]
    assert len(command_nodes) >= 1
    print("  [PASS] test_builder_creates_command_nodes")


def test_builder_creates_configuration_nodes():
    """The builder creates configuration or environment variable nodes."""
    builder = GraphBuilder()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    config_nodes = [n for n in graph.nodes if n.type == NODE_TYPE_CONFIGURATION]
    env_nodes = [n for n in graph.nodes if n.type == NODE_TYPE_ENVIRONMENT_VARIABLE]
    assert len(config_nodes) + len(env_nodes) >= 1
    print("  [PASS] test_builder_creates_configuration_nodes")


def test_builder_creates_environment_variable_nodes():
    """The builder creates environment-variable nodes from the blueprint."""
    builder = GraphBuilder()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    env_nodes = [n for n in graph.nodes if n.type == NODE_TYPE_ENVIRONMENT_VARIABLE]
    assert len(env_nodes) >= 1
    print("  [PASS] test_builder_creates_environment_variable_nodes")


def test_builder_creates_edges():
    """The builder creates edges between nodes."""
    builder = GraphBuilder()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    assert graph.edge_count > 0
    # Check that at least some edges are EDGE_CONTAINS (project -> features)
    contains_edges = [e for e in graph.edges if e.kind == EDGE_CONTAINS]
    assert len(contains_edges) > 0
    print("  [PASS] test_builder_creates_edges")


def test_builder_node_dedup():
    """The builder deduplicates nodes by (type, name)."""
    builder = GraphBuilder()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    # No two nodes should have the same (type, name).
    seen = set()
    for node in graph.nodes:
        key = (node.type, node.name)
        assert key not in seen, f"Duplicate node: {key}"
        seen.add(key)
    print("  [PASS] test_builder_node_dedup")


def test_builder_edge_dedup():
    """The builder deduplicates edges by (source_id, kind, target_id)."""
    builder = GraphBuilder()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    # No two edges should have the same edge_id.
    edge_ids = [e.edge_id for e in graph.edges]
    assert len(edge_ids) == len(set(edge_ids)), "Duplicate edge IDs found"
    print("  [PASS] test_builder_edge_dedup")


def test_builder_provenance():
    """The builder builds provenance with all source artefacts."""
    builder = GraphBuilder()
    graph = builder.build(
        blueprint=make_valid_blueprint("my_store_bot"),
        validation_report=make_approved_report("my_store_bot"),
        structure_map=make_structure_map("my_store_bot"),
        registry=make_component_registry("my_store_bot"),
        file_plan=make_file_plan("my_store_bot"),
        dependency_report=make_dependency_report("my_store_bot"),
        project_context=make_project_context_artefact("my_store_bot"),
    )
    prov = graph.provenance
    assert prov.project_name == "my_store_bot"
    assert len(prov.all_sources_used) == 7
    print("  [PASS] test_builder_provenance")


def test_builder_node_ids_format():
    """Node IDs follow the 'type:name' format."""
    builder = GraphBuilder()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    for node in graph.nodes:
        assert ":" in node.node_id, f"Node ID '{node.node_id}' missing ':'"
        parts = node.node_id.split(":", 1)
        assert parts[0] == node.type, (
            f"Node ID type prefix '{parts[0]}' != type '{node.type}'"
        )
    print("  [PASS] test_builder_node_ids_format")


def test_builder_edge_ids_format():
    """Edge IDs follow the 'source--kind-->target' format."""
    builder = GraphBuilder()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    for edge in graph.edges:
        assert "-->" in edge.edge_id, f"Edge ID '{edge.edge_id}' missing '-->'"
    print("  [PASS] test_builder_edge_ids_format")


def test_builder_node_has_required_fields():
    """Every node has node_id, type, name, description, priority, source."""
    builder = GraphBuilder()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    for node in graph.nodes:
        assert node.node_id, f"Node has empty node_id"
        assert node.type, f"Node has empty type"
        assert node.name, f"Node has empty name"
        assert isinstance(node.priority, int)
        assert node.source in ALL_SOURCES
    print("  [PASS] test_builder_node_has_required_fields")


# ---------------------------------------------------------------------------#
# 4. GraphNavigator tests
# ---------------------------------------------------------------------------#

def test_navigator_builds_indices():
    """GraphNavigator builds the GraphIndices on the graph."""
    builder = GraphBuilder()
    navigator = GraphNavigator()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    navigator.navigate(graph)
    assert isinstance(graph.indices, GraphIndices)
    assert len(graph.indices.node_by_id) > 0
    print("  [PASS] test_navigator_builds_indices")


def test_navigator_node_by_id():
    """node_by_id has an entry for every node."""
    builder = GraphBuilder()
    navigator = GraphNavigator()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    navigator.navigate(graph)
    assert len(graph.indices.node_by_id) == graph.node_count
    for node in graph.nodes:
        assert node.node_id in graph.indices.node_by_id
    print("  [PASS] test_navigator_node_by_id")


def test_navigator_nodes_by_type():
    """nodes_by_type has a key for every known node type."""
    builder = GraphBuilder()
    navigator = GraphNavigator()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    navigator.navigate(graph)
    for nt in ALL_NODE_TYPES:
        assert nt in graph.indices.nodes_by_type, f"Missing type: {nt}"
    # The sum of all node IDs across types should equal the total node count.
    total = sum(len(v) for v in graph.indices.nodes_by_type.values())
    assert total == graph.node_count
    print("  [PASS] test_navigator_nodes_by_type")


def test_navigator_node_by_name():
    """node_by_name maps element names to node IDs."""
    builder = GraphBuilder()
    navigator = GraphNavigator()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    navigator.navigate(graph)
    assert len(graph.indices.node_by_name) > 0
    print("  [PASS] test_navigator_node_by_name")


def test_navigator_node_id_by_type_and_name():
    """node_id_by_type_and_name maps (type, name) pairs to node IDs."""
    builder = GraphBuilder()
    navigator = GraphNavigator()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    navigator.navigate(graph)
    for node in graph.nodes:
        key = (node.type, node.name)
        assert key in graph.indices.node_id_by_type_and_name
        assert graph.indices.node_id_by_type_and_name[key] == node.node_id
    print("  [PASS] test_navigator_node_id_by_type_and_name")


def test_navigator_edges_by_source():
    """edges_by_source maps source node IDs to their edges."""
    builder = GraphBuilder()
    navigator = GraphNavigator()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    navigator.navigate(graph)
    for edge in graph.edges:
        assert edge.source_id in graph.indices.edges_by_source
        assert edge in graph.indices.edges_by_source[edge.source_id]
    print("  [PASS] test_navigator_edges_by_source")


def test_navigator_edges_by_target():
    """edges_by_target maps target node IDs to their edges."""
    builder = GraphBuilder()
    navigator = GraphNavigator()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    navigator.navigate(graph)
    for edge in graph.edges:
        assert edge.target_id in graph.indices.edges_by_target
        assert edge in graph.indices.edges_by_target[edge.target_id]
    print("  [PASS] test_navigator_edges_by_target")


def test_navigator_out_edges():
    """out_edges maps source node IDs to target node IDs."""
    builder = GraphBuilder()
    navigator = GraphNavigator()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    navigator.navigate(graph)
    for edge in graph.edges:
        assert edge.target_id in graph.indices.out_edges.get(edge.source_id, [])
    print("  [PASS] test_navigator_out_edges")


def test_navigator_in_edges():
    """in_edges maps target node IDs to source node IDs."""
    builder = GraphBuilder()
    navigator = GraphNavigator()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    navigator.navigate(graph)
    for edge in graph.edges:
        assert edge.source_id in graph.indices.in_edges.get(edge.target_id, [])
    print("  [PASS] test_navigator_in_edges")


def test_navigator_out_edges_by_kind():
    """out_edges_by_kind maps (source_id, kind) to target node IDs."""
    builder = GraphBuilder()
    navigator = GraphNavigator()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    navigator.navigate(graph)
    for edge in graph.edges:
        key = (edge.source_id, edge.kind)
        assert key in graph.indices.out_edges_by_kind
        assert edge.target_id in graph.indices.out_edges_by_kind[key]
    print("  [PASS] test_navigator_out_edges_by_kind")


def test_navigator_in_edges_by_kind():
    """in_edges_by_kind maps (target_id, kind) to source node IDs."""
    builder = GraphBuilder()
    navigator = GraphNavigator()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    navigator.navigate(graph)
    for edge in graph.edges:
        key = (edge.target_id, edge.kind)
        assert key in graph.indices.in_edges_by_kind
        assert edge.source_id in graph.indices.in_edges_by_kind[key]
    print("  [PASS] test_navigator_in_edges_by_kind")


def test_navigator_edges_by_kind():
    """edges_by_kind maps edge kinds to their edges."""
    builder = GraphBuilder()
    navigator = GraphNavigator()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    navigator.navigate(graph)
    total = sum(len(v) for v in graph.indices.edges_by_kind.values())
    assert total == graph.edge_count
    print("  [PASS] test_navigator_edges_by_kind")


def test_navigator_returns_graph():
    """navigate returns the graph (not None)."""
    builder = GraphBuilder()
    navigator = GraphNavigator()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    result = navigator.navigate(graph)
    assert result is graph
    print("  [PASS] test_navigator_returns_graph")


# ---------------------------------------------------------------------------#
# 5. CircularDetector tests
# ---------------------------------------------------------------------------#

def test_detector_no_findings_on_clean_graph():
    """A clean graph with no cycles produces no circular-dependency findings."""
    builder = GraphBuilder()
    navigator = GraphNavigator()
    detector = CircularDetector()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    navigator.navigate(graph)
    findings = detector.detect(graph)
    cycle_findings = [
        f for f in findings if f.category == CATEGORY_CIRCULAR_DEPENDENCY
    ]
    assert len(cycle_findings) == 0, (
        f"Unexpected cycles: {[(f.code, f.message) for f in cycle_findings]}"
    )
    print("  [PASS] test_detector_no_findings_on_clean_graph")


def test_detector_detects_circular_dependency():
    """The detector finds a circular dependency when one exists."""
    graph = ProjectIntelligenceGraph()
    n1 = GraphNode(node_id="component:a", type=NODE_TYPE_COMPONENT, name="a")
    n2 = GraphNode(node_id="component:b", type=NODE_TYPE_COMPONENT, name="b")
    graph.nodes = [n1, n2]
    graph.edges = [
        GraphEdge(edge_id="e1", source_id="component:a", target_id="component:b", kind=EDGE_DEPENDS_ON),
        GraphEdge(edge_id="e2", source_id="component:b", target_id="component:a", kind=EDGE_DEPENDS_ON),
    ]
    navigator = GraphNavigator()
    navigator.navigate(graph)
    detector = CircularDetector()
    findings = detector.detect(graph)
    cycle_findings = [
        f for f in findings if f.category == CATEGORY_CIRCULAR_DEPENDENCY
    ]
    assert len(cycle_findings) >= 1, "No circular dependency detected"
    assert cycle_findings[0].severity == SEVERITY_ERROR
    assert len(cycle_findings[0].cycle) >= 3
    print("  [PASS] test_detector_detects_circular_dependency")


def test_detector_three_node_cycle():
    """The detector finds a three-node cycle."""
    graph = ProjectIntelligenceGraph()
    for nid in ["component:a", "component:b", "component:c"]:
        graph.nodes.append(GraphNode(node_id=nid, type=NODE_TYPE_COMPONENT, name=nid.split(":")[1]))
    graph.edges = [
        GraphEdge(edge_id="e1", source_id="component:a", target_id="component:b", kind=EDGE_DEPENDS_ON),
        GraphEdge(edge_id="e2", source_id="component:b", target_id="component:c", kind=EDGE_DEPENDS_ON),
        GraphEdge(edge_id="e3", source_id="component:c", target_id="component:a", kind=EDGE_DEPENDS_ON),
    ]
    navigator = GraphNavigator()
    navigator.navigate(graph)
    detector = CircularDetector()
    findings = detector.detect(graph)
    cycle_findings = [
        f for f in findings if f.category == CATEGORY_CIRCULAR_DEPENDENCY
    ]
    assert len(cycle_findings) == 1
    print("  [PASS] test_detector_three_node_cycle")


def test_detector_no_cycle_with_non_dependency_edges():
    """The detector does not report cycles on non-dependency edges."""
    graph = ProjectIntelligenceGraph()
    for nid in ["component:a", "component:b"]:
        graph.nodes.append(GraphNode(node_id=nid, type=NODE_TYPE_COMPONENT, name=nid.split(":")[1]))
    graph.edges = [
        GraphEdge(edge_id="e1", source_id="component:a", target_id="component:b", kind=EDGE_CONTAINS),
        GraphEdge(edge_id="e2", source_id="component:b", target_id="component:a", kind=EDGE_CONTAINS),
    ]
    navigator = GraphNavigator()
    navigator.navigate(graph)
    detector = CircularDetector()
    findings = detector.detect(graph)
    cycle_findings = [
        f for f in findings if f.category == CATEGORY_CIRCULAR_DEPENDENCY
    ]
    assert len(cycle_findings) == 0
    print("  [PASS] test_detector_no_cycle_with_non_dependency_edges")


def test_detector_broken_references():
    """The detector finds edges that reference non-existent nodes."""
    graph = ProjectIntelligenceGraph()
    n1 = GraphNode(node_id="component:a", type=NODE_TYPE_COMPONENT, name="a")
    graph.nodes = [n1]
    graph.edges = [
        GraphEdge(edge_id="e1", source_id="component:a", target_id="component:nonexistent", kind=EDGE_USES),
    ]
    navigator = GraphNavigator()
    navigator.navigate(graph)
    detector = CircularDetector()
    findings = detector.detect(graph)
    broken = [f for f in findings if f.category == CATEGORY_BROKEN_REFERENCE]
    assert len(broken) >= 1
    assert broken[0].severity == SEVERITY_ERROR
    print("  [PASS] test_detector_broken_references")


def test_detector_unused_components():
    """The detector finds components with no incoming edges."""
    graph = ProjectIntelligenceGraph()
    n1 = GraphNode(node_id="component:unused", type=NODE_TYPE_COMPONENT, name="unused")
    n2 = GraphNode(node_id="component:used", type=NODE_TYPE_COMPONENT, name="used")
    graph.nodes = [n1, n2]
    graph.edges = [
        GraphEdge(edge_id="e1", source_id="component:used", target_id="component:used", kind=EDGE_CONTAINS),
    ]
    navigator = GraphNavigator()
    navigator.navigate(graph)
    detector = CircularDetector()
    findings = detector.detect(graph)
    unused = [f for f in findings if f.category == CATEGORY_UNUSED_COMPONENT]
    unused_names = {f.affected for f in unused}
    assert "component:unused" in unused_names
    assert unused[0].severity == SEVERITY_WARNING
    print("  [PASS] test_detector_unused_components")


def test_detector_orphan_files():
    """The detector finds files with no incoming edges."""
    graph = ProjectIntelligenceGraph()
    n1 = GraphNode(node_id="file:orphan.py", type=NODE_TYPE_FILE, name="orphan.py")
    n2 = GraphNode(node_id="file:contained.py", type=NODE_TYPE_FILE, name="contained.py")
    n3 = GraphNode(node_id="folder:src", type=NODE_TYPE_FOLDER, name="src")
    graph.nodes = [n1, n2, n3]
    graph.edges = [
        GraphEdge(edge_id="e1", source_id="folder:src", target_id="file:contained.py", kind=EDGE_CONTAINS),
    ]
    navigator = GraphNavigator()
    navigator.navigate(graph)
    detector = CircularDetector()
    findings = detector.detect(graph)
    orphans = [f for f in findings if f.category == CATEGORY_ORPHAN_FILE]
    orphan_names = {f.affected for f in orphans}
    assert "file:orphan.py" in orphan_names
    assert orphans[0].severity == SEVERITY_WARNING
    print("  [PASS] test_detector_orphan_files")


def test_detector_dead_components():
    """The detector finds components with no outgoing edges."""
    graph = ProjectIntelligenceGraph()
    n1 = GraphNode(node_id="component:dead", type=NODE_TYPE_COMPONENT, name="dead")
    n2 = GraphNode(node_id="component:alive", type=NODE_TYPE_COMPONENT, name="alive")
    n3 = GraphNode(node_id="dependency:aiogram", type=NODE_TYPE_DEPENDENCY, name="aiogram")
    graph.nodes = [n1, n2, n3]
    graph.edges = [
        GraphEdge(edge_id="e1", source_id="component:alive", target_id="dependency:aiogram", kind=EDGE_DEPENDS_ON),
    ]
    navigator = GraphNavigator()
    navigator.navigate(graph)
    detector = CircularDetector()
    findings = detector.detect(graph)
    dead = [f for f in findings if f.category == CATEGORY_DEAD_COMPONENT]
    dead_names = {f.affected for f in dead}
    assert "component:dead" in dead_names
    assert "component:alive" not in dead_names
    assert dead[0].severity == SEVERITY_INFO
    print("  [PASS] test_detector_dead_components")


def test_detector_cycle_normalisation():
    """The same cycle detected from different starting points produces one finding."""
    graph = ProjectIntelligenceGraph()
    for nid in ["component:z", "component:a", "component:m"]:
        graph.nodes.append(GraphNode(node_id=nid, type=NODE_TYPE_COMPONENT, name=nid.split(":")[1]))
    graph.edges = [
        GraphEdge(edge_id="e1", source_id="component:z", target_id="component:a", kind=EDGE_DEPENDS_ON),
        GraphEdge(edge_id="e2", source_id="component:a", target_id="component:m", kind=EDGE_DEPENDS_ON),
        GraphEdge(edge_id="e3", source_id="component:m", target_id="component:z", kind=EDGE_DEPENDS_ON),
    ]
    navigator = GraphNavigator()
    navigator.navigate(graph)
    detector = CircularDetector()
    findings = detector.detect(graph)
    cycle_findings = [
        f for f in findings if f.category == CATEGORY_CIRCULAR_DEPENDENCY
    ]
    assert len(cycle_findings) == 1, (
        f"Expected 1 cycle finding, got {len(cycle_findings)}"
    )
    print("  [PASS] test_detector_cycle_normalisation")


# ---------------------------------------------------------------------------#
# 6. GraphValidator tests
# ---------------------------------------------------------------------------#

def test_validator_no_findings_on_clean_graph():
    """A clean, well-built graph has no error-level findings."""
    builder = GraphBuilder()
    navigator = GraphNavigator()
    validator = GraphValidator()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    navigator.navigate(graph)
    findings = validator.validate(graph)
    error_findings = [f for f in findings if f.severity == SEVERITY_ERROR]
    assert len(error_findings) == 0, (
        f"Validation errors: {[(f.code, f.message) for f in error_findings]}"
    )
    print("  [PASS] test_validator_no_findings_on_clean_graph")


def test_validator_duplicate_node_ids():
    """The validator detects duplicate node IDs."""
    graph = ProjectIntelligenceGraph()
    n1 = GraphNode(node_id="component:dup", type=NODE_TYPE_COMPONENT, name="dup")
    n2 = GraphNode(node_id="component:dup", type=NODE_TYPE_COMPONENT, name="dup")
    graph.nodes = [n1, n2]
    graph.edges = []
    navigator = GraphNavigator()
    navigator.navigate(graph)
    validator = GraphValidator()
    findings = validator.validate(graph)
    dup = [f for f in findings if f.code == "duplicate_node_id"]
    assert len(dup) >= 1
    assert dup[0].severity == SEVERITY_ERROR
    print("  [PASS] test_validator_duplicate_node_ids")


def test_validator_duplicate_edge_ids():
    """The validator detects duplicate edge IDs."""
    graph = ProjectIntelligenceGraph()
    n1 = GraphNode(node_id="component:a", type=NODE_TYPE_COMPONENT, name="a")
    n2 = GraphNode(node_id="component:b", type=NODE_TYPE_COMPONENT, name="b")
    graph.nodes = [n1, n2]
    graph.edges = [
        GraphEdge(edge_id="dup", source_id="component:a", target_id="component:b", kind=EDGE_USES),
        GraphEdge(edge_id="dup", source_id="component:a", target_id="component:b", kind=EDGE_USES),
    ]
    navigator = GraphNavigator()
    navigator.navigate(graph)
    validator = GraphValidator()
    findings = validator.validate(graph)
    dup = [f for f in findings if f.code == "duplicate_edge_id"]
    assert len(dup) >= 1
    print("  [PASS] test_validator_duplicate_edge_ids")


def test_validator_edge_source_not_found():
    """The validator detects edges with a missing source node."""
    graph = ProjectIntelligenceGraph()
    n1 = GraphNode(node_id="component:a", type=NODE_TYPE_COMPONENT, name="a")
    graph.nodes = [n1]
    graph.edges = [
        GraphEdge(edge_id="e1", source_id="component:nonexistent", target_id="component:a", kind=EDGE_USES),
    ]
    navigator = GraphNavigator()
    navigator.navigate(graph)
    validator = GraphValidator()
    findings = validator.validate(graph)
    not_found = [f for f in findings if f.code == "edge_source_not_found"]
    assert len(not_found) >= 1
    print("  [PASS] test_validator_edge_source_not_found")


def test_validator_edge_target_not_found():
    """The validator detects edges with a missing target node."""
    graph = ProjectIntelligenceGraph()
    n1 = GraphNode(node_id="component:a", type=NODE_TYPE_COMPONENT, name="a")
    graph.nodes = [n1]
    graph.edges = [
        GraphEdge(edge_id="e1", source_id="component:a", target_id="component:nonexistent", kind=EDGE_USES),
    ]
    navigator = GraphNavigator()
    navigator.navigate(graph)
    validator = GraphValidator()
    findings = validator.validate(graph)
    not_found = [f for f in findings if f.code == "edge_target_not_found"]
    assert len(not_found) >= 1
    print("  [PASS] test_validator_edge_target_not_found")


def test_validator_unknown_node_type():
    """The validator detects nodes with an unknown type."""
    graph = ProjectIntelligenceGraph()
    n1 = GraphNode(node_id="unknown:foo", type="unknown_type", name="foo")
    graph.nodes = [n1]
    graph.edges = []
    navigator = GraphNavigator()
    navigator.navigate(graph)
    validator = GraphValidator()
    findings = validator.validate(graph)
    unknown = [f for f in findings if f.code == "unknown_node_type"]
    assert len(unknown) >= 1
    print("  [PASS] test_validator_unknown_node_type")


def test_validator_unknown_edge_kind():
    """The validator detects edges with an unknown kind."""
    graph = ProjectIntelligenceGraph()
    n1 = GraphNode(node_id="component:a", type=NODE_TYPE_COMPONENT, name="a")
    n2 = GraphNode(node_id="component:b", type=NODE_TYPE_COMPONENT, name="b")
    graph.nodes = [n1, n2]
    graph.edges = [
        GraphEdge(edge_id="e1", source_id="component:a", target_id="component:b", kind="unknown_kind"),
    ]
    navigator = GraphNavigator()
    navigator.navigate(graph)
    validator = GraphValidator()
    findings = validator.validate(graph)
    unknown = [f for f in findings if f.code == "unknown_edge_kind"]
    assert len(unknown) >= 1
    print("  [PASS] test_validator_unknown_edge_kind")


def test_validator_empty_node_id():
    """The validator detects nodes with an empty node_id."""
    graph = ProjectIntelligenceGraph()
    n1 = GraphNode(node_id="", type=NODE_TYPE_COMPONENT, name="test")
    graph.nodes = [n1]
    graph.edges = []
    navigator = GraphNavigator()
    navigator.navigate(graph)
    validator = GraphValidator()
    findings = validator.validate(graph)
    empty = [f for f in findings if f.code == "empty_node_id"]
    assert len(empty) >= 1
    assert empty[0].severity == SEVERITY_ERROR
    print("  [PASS] test_validator_empty_node_id")


def test_validator_empty_node_name():
    """The validator detects nodes with an empty name."""
    graph = ProjectIntelligenceGraph()
    n1 = GraphNode(node_id="component:noname", type=NODE_TYPE_COMPONENT, name="")
    graph.nodes = [n1]
    graph.edges = []
    navigator = GraphNavigator()
    navigator.navigate(graph)
    validator = GraphValidator()
    findings = validator.validate(graph)
    empty = [f for f in findings if f.code == "empty_node_name"]
    assert len(empty) >= 1
    assert empty[0].severity == SEVERITY_WARNING
    print("  [PASS] test_validator_empty_node_name")


def test_validator_self_loop():
    """The validator detects self-loop edges."""
    graph = ProjectIntelligenceGraph()
    n1 = GraphNode(node_id="component:a", type=NODE_TYPE_COMPONENT, name="a")
    graph.nodes = [n1]
    graph.edges = [
        GraphEdge(edge_id="e1", source_id="component:a", target_id="component:a", kind=EDGE_USES),
    ]
    navigator = GraphNavigator()
    navigator.navigate(graph)
    validator = GraphValidator()
    findings = validator.validate(graph)
    loops = [f for f in findings if f.code == "self_loop"]
    assert len(loops) >= 1
    assert loops[0].severity == SEVERITY_WARNING
    print("  [PASS] test_validator_self_loop")


def test_validator_missing_project_node():
    """The validator warns when there is no project node."""
    graph = ProjectIntelligenceGraph()
    n1 = GraphNode(node_id="component:a", type=NODE_TYPE_COMPONENT, name="a")
    graph.nodes = [n1]
    graph.edges = []
    navigator = GraphNavigator()
    navigator.navigate(graph)
    validator = GraphValidator()
    findings = validator.validate(graph)
    missing = [f for f in findings if f.code == "missing_project_node"]
    assert len(missing) >= 1
    assert missing[0].severity == SEVERITY_WARNING
    print("  [PASS] test_validator_missing_project_node")


def test_validator_multiple_project_nodes():
    """The validator errors when there are multiple project nodes."""
    graph = ProjectIntelligenceGraph()
    n1 = GraphNode(node_id="project:a", type=NODE_TYPE_PROJECT, name="a")
    n2 = GraphNode(node_id="project:b", type=NODE_TYPE_PROJECT, name="b")
    graph.nodes = [n1, n2]
    graph.edges = []
    navigator = GraphNavigator()
    navigator.navigate(graph)
    validator = GraphValidator()
    findings = validator.validate(graph)
    multiple = [f for f in findings if f.code == "multiple_project_nodes"]
    assert len(multiple) >= 1
    assert multiple[0].severity == SEVERITY_ERROR
    print("  [PASS] test_validator_multiple_project_nodes")


def test_validator_indices_consistency():
    """The validator detects when the indices don't match the raw lists."""
    builder = GraphBuilder()
    navigator = GraphNavigator()
    graph = builder.build(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    navigator.navigate(graph)
    # Corrupt the indices by removing a node.
    graph.indices.node_by_id.pop(next(iter(graph.indices.node_by_id)))
    validator = GraphValidator()
    findings = validator.validate(graph)
    mismatch = [f for f in findings if f.code == "index_node_count_mismatch"]
    assert len(mismatch) >= 1
    print("  [PASS] test_validator_indices_consistency")


# ---------------------------------------------------------------------------#
# 7. Engine — data source requirements
# ---------------------------------------------------------------------------#

def test_engine_requires_blueprint():
    """Engine fails when the blueprint artefact is missing."""
    ctx = make_context(
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    engine = IntelligenceGraphEngine()
    result = engine.execute(ctx)
    assert not result.success
    assert any("project_blueprint" in e for e in result.errors)
    print("  [PASS] test_engine_requires_blueprint")


def test_engine_requires_validation_report():
    """Engine fails when the validation report artefact is missing."""
    ctx = make_context(
        blueprint=make_valid_blueprint(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    engine = IntelligenceGraphEngine()
    result = engine.execute(ctx)
    assert not result.success
    assert any("validation" in e.lower() for e in result.errors)
    print("  [PASS] test_engine_requires_validation_report")


def test_engine_requires_structure_map():
    """Engine fails when the structure map artefact is missing."""
    ctx = make_context(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    engine = IntelligenceGraphEngine()
    result = engine.execute(ctx)
    assert not result.success
    assert any("structure" in e.lower() for e in result.errors)
    print("  [PASS] test_engine_requires_structure_map")


def test_engine_requires_registry():
    """Engine fails when the component registry artefact is missing."""
    ctx = make_context(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    engine = IntelligenceGraphEngine()
    result = engine.execute(ctx)
    assert not result.success
    assert any("component_registry" in e for e in result.errors)
    print("  [PASS] test_engine_requires_registry")


def test_engine_requires_file_plan():
    """Engine fails when the file generation plan artefact is missing."""
    ctx = make_context(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        dependency_report=make_dependency_report(),
        project_context=make_project_context_artefact(),
    )
    engine = IntelligenceGraphEngine()
    result = engine.execute(ctx)
    assert not result.success
    assert any("file_generation_plan" in e for e in result.errors)
    print("  [PASS] test_engine_requires_file_plan")


def test_engine_requires_dependency_report():
    """Engine fails when the dependency resolution report artefact is missing."""
    ctx = make_context(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        project_context=make_project_context_artefact(),
    )
    engine = IntelligenceGraphEngine()
    result = engine.execute(ctx)
    assert not result.success
    assert any("dependency" in e.lower() for e in result.errors)
    print("  [PASS] test_engine_requires_dependency_report")


def test_engine_requires_project_context():
    """Engine fails when the project context artefact is missing."""
    ctx = make_context(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
        file_plan=make_file_plan(),
        dependency_report=make_dependency_report(),
    )
    engine = IntelligenceGraphEngine()
    result = engine.execute(ctx)
    assert not result.success
    assert any("project_context" in e for e in result.errors)
    print("  [PASS] test_engine_requires_project_context")


def test_engine_does_not_read_request():
    """The engine does not read the user's raw request."""
    ctx = make_full_context()
    # Set the request to a sentinel value that would cause failure
    # if the engine tried to read it.
    ctx.request = "THIS_SHOULD_NOT_BE_READ"
    engine = IntelligenceGraphEngine()
    result = engine.execute(ctx)
    assert result.success, f"Engine failed: {result.errors}"
    graph = ctx.get("intelligence_graph")
    assert graph is not None
    # The graph should not reference the raw request.
    assert graph.provenance.project_name != "THIS_SHOULD_NOT_BE_READ"
    print("  [PASS] test_engine_does_not_read_request")


# ---------------------------------------------------------------------------#
# 8. Engine — type checking
# ---------------------------------------------------------------------------#

def test_engine_type_check_blueprint():
    """Engine fails when the blueprint is the wrong type."""
    ctx = make_full_context()
    ctx.set("project_blueprint", "not a blueprint")
    engine = IntelligenceGraphEngine()
    result = engine.execute(ctx)
    assert not result.success
    assert any("ProjectBlueprint" in e for e in result.errors)
    print("  [PASS] test_engine_type_check_blueprint")


def test_engine_type_check_validation_report():
    """Engine fails when the validation report is the wrong type."""
    ctx = make_full_context()
    ctx.set("blueprint_validation_report", "not a report")
    engine = IntelligenceGraphEngine()
    result = engine.execute(ctx)
    assert not result.success
    assert any("BlueprintValidationReport" in e for e in result.errors)
    print("  [PASS] test_engine_type_check_validation_report")


def test_engine_type_check_structure_map():
    """Engine fails when the structure map is the wrong type."""
    ctx = make_full_context()
    ctx.set("project_structure_map", "not a structure map")
    engine = IntelligenceGraphEngine()
    result = engine.execute(ctx)
    assert not result.success
    assert any("ProjectStructureMap" in e for e in result.errors)
    print("  [PASS] test_engine_type_check_structure_map")


def test_engine_type_check_registry():
    """Engine fails when the component registry is the wrong type."""
    ctx = make_full_context()
    ctx.set("component_registry", "not a registry")
    engine = IntelligenceGraphEngine()
    result = engine.execute(ctx)
    assert not result.success
    assert any("ComponentRegistry" in e for e in result.errors)
    print("  [PASS] test_engine_type_check_registry")


def test_engine_type_check_file_plan():
    """Engine fails when the file plan is the wrong type."""
    ctx = make_full_context()
    ctx.set("file_generation_plan", "not a file plan")
    engine = IntelligenceGraphEngine()
    result = engine.execute(ctx)
    assert not result.success
    assert any("FileGenerationPlan" in e for e in result.errors)
    print("  [PASS] test_engine_type_check_file_plan")


def test_engine_type_check_dependency_report():
    """Engine fails when the dependency report is the wrong type."""
    ctx = make_full_context()
    ctx.set("dependency_resolution_report", "not a report")
    engine = IntelligenceGraphEngine()
    result = engine.execute(ctx)
    assert not result.success
    assert any("DependencyResolutionReport" in e for e in result.errors)
    print("  [PASS] test_engine_type_check_dependency_report")


def test_engine_type_check_project_context():
    """Engine fails when the project context is the wrong type."""
    ctx = make_full_context()
    ctx.set("project_context", "not a project context")
    engine = IntelligenceGraphEngine()
    result = engine.execute(ctx)
    assert not result.success
    assert any("ProjectContext" in e for e in result.errors)
    print("  [PASS] test_engine_type_check_project_context")


# ---------------------------------------------------------------------------#
# 9. Engine — output verification
# ---------------------------------------------------------------------------#

def test_engine_produces_graph():
    """Engine produces a ProjectIntelligenceGraph and stores it."""
    ctx = make_full_context()
    engine = IntelligenceGraphEngine()
    result = engine.execute(ctx)
    assert result.success, f"Engine failed: {result.errors}"
    graph = ctx.get("intelligence_graph")
    assert graph is not None
    assert isinstance(graph, ProjectIntelligenceGraph)
    assert graph.node_count > 0
    assert graph.edge_count > 0
    print("  [PASS] test_engine_produces_graph")


def test_engine_graph_stored_in_metadata():
    """The graph is also stored in the context metadata."""
    ctx = make_full_context()
    engine = IntelligenceGraphEngine()
    engine.execute(ctx)
    assert "intelligence_graph" in ctx.metadata
    assert isinstance(ctx.metadata["intelligence_graph"], ProjectIntelligenceGraph)
    print("  [PASS] test_engine_graph_stored_in_metadata")


def test_engine_records_provenance():
    """The graph records all seven source artefacts in provenance."""
    ctx = make_full_context()
    engine = IntelligenceGraphEngine()
    engine.execute(ctx)
    graph = ctx.get("intelligence_graph")
    prov = graph.provenance
    assert prov.project_name == "my_store_bot"
    assert len(prov.all_sources_used) == 7
    print("  [PASS] test_engine_records_provenance")


def test_engine_graph_has_summary():
    """The graph has a non-empty summary."""
    ctx = make_full_context()
    engine = IntelligenceGraphEngine()
    engine.execute(ctx)
    graph = ctx.get("intelligence_graph")
    assert graph.summary
    assert "node" in graph.summary.lower()
    print("  [PASS] test_engine_graph_has_summary")


def test_engine_graph_has_notes():
    """The graph has a non-empty notes list."""
    ctx = make_full_context()
    engine = IntelligenceGraphEngine()
    engine.execute(ctx)
    graph = ctx.get("intelligence_graph")
    assert len(graph.notes) > 0
    print("  [PASS] test_engine_graph_has_notes")


def test_engine_graph_has_indices():
    """The graph has O(1) lookup indices."""
    ctx = make_full_context()
    engine = IntelligenceGraphEngine()
    engine.execute(ctx)
    graph = ctx.get("intelligence_graph")
    assert isinstance(graph.indices, GraphIndices)
    assert len(graph.indices.node_by_id) > 0
    assert len(graph.indices.nodes_by_type) > 0
    print("  [PASS] test_engine_graph_has_indices")


def test_engine_graph_node_type_count():
    """The graph has multiple node types."""
    ctx = make_full_context()
    engine = IntelligenceGraphEngine()
    engine.execute(ctx)
    graph = ctx.get("intelligence_graph")
    assert graph.node_type_count >= 5
    print("  [PASS] test_engine_graph_node_type_count")


def test_engine_graph_edge_kind_count():
    """The graph has multiple edge kinds."""
    ctx = make_full_context()
    engine = IntelligenceGraphEngine()
    engine.execute(ctx)
    graph = ctx.get("intelligence_graph")
    assert graph.edge_kind_count >= 1
    print("  [PASS] test_engine_graph_edge_kind_count")


def test_engine_metadata_in_result():
    """The result metadata contains the graph statistics."""
    ctx = make_full_context()
    engine = IntelligenceGraphEngine()
    result = engine.execute(ctx)
    assert result.success
    assert "project_name" in result.metadata
    assert "node_count" in result.metadata
    assert "edge_count" in result.metadata
    assert "node_type_count" in result.metadata
    assert "edge_kind_count" in result.metadata
    assert "finding_count" in result.metadata
    print("  [PASS] test_engine_metadata_in_result")


def test_engine_graph_no_errors():
    """The graph has no error-level findings from detection or validation."""
    ctx = make_full_context()
    engine = IntelligenceGraphEngine()
    result = engine.execute(ctx)
    assert result.success, f"Engine failed: {result.errors}"
    graph = ctx.get("intelligence_graph")
    error_findings = [f for f in graph.findings if f.severity == SEVERITY_ERROR]
    assert len(error_findings) == 0, (
        f"Graph has errors: {[(f.code, f.message) for f in error_findings]}"
    )
    print("  [PASS] test_engine_graph_no_errors")


def test_engine_graph_has_project_node():
    """The graph has exactly one project node."""
    ctx = make_full_context()
    engine = IntelligenceGraphEngine()
    engine.execute(ctx)
    graph = ctx.get("intelligence_graph")
    project_nodes = graph.nodes_of_type(NODE_TYPE_PROJECT)
    assert len(project_nodes) == 1
    assert project_nodes[0].name == "my_store_bot"
    print("  [PASS] test_engine_graph_has_project_node")


def test_engine_graph_navigation_works():
    """The graph's O(1) look-up methods work after engine execution."""
    ctx = make_full_context()
    engine = IntelligenceGraphEngine()
    engine.execute(ctx)
    graph = ctx.get("intelligence_graph")
    # Get a project node and navigate from it.
    project_node = graph.nodes_of_type(NODE_TYPE_PROJECT)[0]
    out = graph.outgoing(project_node.node_id)
    assert len(out) > 0
    # Verify we can look up a node by name.
    node = graph.get_node_by_name("core")
    if node is not None:
        assert node.type == NODE_TYPE_COMPONENT
    print("  [PASS] test_engine_graph_navigation_works")


# ---------------------------------------------------------------------------#
# 10. Graph integrity
# ---------------------------------------------------------------------------#

def test_graph_all_node_types_known():
    """Every node in the graph has a known type."""
    ctx = make_full_context()
    engine = IntelligenceGraphEngine()
    engine.execute(ctx)
    graph = ctx.get("intelligence_graph")
    for node in graph.nodes:
        assert node.type in ALL_NODE_TYPES, (
            f"Unknown node type: {node.type}"
        )
    print("  [PASS] test_graph_all_node_types_known")


def test_graph_all_edge_kinds_known():
    """Every edge in the graph has a known kind."""
    ctx = make_full_context()
    engine = IntelligenceGraphEngine()
    engine.execute(ctx)
    graph = ctx.get("intelligence_graph")
    for edge in graph.edges:
        assert edge.kind in ALL_EDGE_KINDS, (
            f"Unknown edge kind: {edge.kind}"
        )
    print("  [PASS] test_graph_all_edge_kinds_known")


def test_graph_no_duplicate_node_ids():
    """No two nodes in the graph share the same node_id."""
    ctx = make_full_context()
    engine = IntelligenceGraphEngine()
    engine.execute(ctx)
    graph = ctx.get("intelligence_graph")
    node_ids = [n.node_id for n in graph.nodes]
    assert len(node_ids) == len(set(node_ids))
    print("  [PASS] test_graph_no_duplicate_node_ids")


def test_graph_no_duplicate_edge_ids():
    """No two edges in the graph share the same edge_id."""
    ctx = make_full_context()
    engine = IntelligenceGraphEngine()
    engine.execute(ctx)
    graph = ctx.get("intelligence_graph")
    edge_ids = [e.edge_id for e in graph.edges]
    assert len(edge_ids) == len(set(edge_ids))
    print("  [PASS] test_graph_no_duplicate_edge_ids")


def test_graph_provenance_all_sources():
    """The provenance records all seven source artefacts."""
    ctx = make_full_context()
    engine = IntelligenceGraphEngine()
    engine.execute(ctx)
    graph = ctx.get("intelligence_graph")
    prov = graph.provenance
    assert len(prov.all_sources_used) == 7
    for s in ALL_SOURCES:
        assert s in prov.all_sources_used, f"Missing source: {s}"
    print("  [PASS] test_graph_provenance_all_sources")


def test_graph_node_sources_valid():
    """Every node's source is one of the seven source constants."""
    ctx = make_full_context()
    engine = IntelligenceGraphEngine()
    engine.execute(ctx)
    graph = ctx.get("intelligence_graph")
    for node in graph.nodes:
        assert node.source in ALL_SOURCES, (
            f"Node {node.node_id} has invalid source: {node.source}"
        )
    print("  [PASS] test_graph_node_sources_valid")


# ---------------------------------------------------------------------------#
# 11. Bootstrap tests
# ---------------------------------------------------------------------------#

def test_bootstrap_registers_intelligence_graph():
    """The bootstrap registers the IntelligenceGraphEngine."""
    registry, orchestrator, manager = bootstrap()
    engine = registry.get_engine("intelligence_graph")
    assert engine is not None
    assert isinstance(engine, IntelligenceGraphEngine)
    print("  [PASS] test_bootstrap_registers_intelligence_graph")


def test_bootstrap_intelligence_graph_priority():
    """The intelligence_graph engine is registered at priority 97."""
    registry, orchestrator, manager = bootstrap()
    entry = manager.get("intelligence_graph")
    assert entry is not None
    assert entry.priority == 97
    print("  [PASS] test_bootstrap_intelligence_graph_priority")


def test_bootstrap_intelligence_graph_dependencies():
    """The intelligence_graph engine depends on project_context."""
    registry, orchestrator, manager = bootstrap()
    entry = manager.get("intelligence_graph")
    assert entry is not None
    assert "project_context" in entry.dependencies
    print("  [PASS] test_bootstrap_intelligence_graph_dependencies")


# ---------------------------------------------------------------------------#
# 12. Serialisation tests
# ---------------------------------------------------------------------------#

def test_graph_node_serialisation():
    """GraphNode round-trips through to_dict."""
    node = GraphNode(
        node_id="component:core",
        type=NODE_TYPE_COMPONENT,
        name="core",
        display_name="Core",
        description="Core bot logic",
        priority=10,
        owner_engine="component_detector",
        source=SOURCE_COMPONENT_REGISTRY,
        metadata={"key": "value"},
        neighbours=["file:src/core/handler.py"],
    )
    d = node.to_dict()
    assert d["node_id"] == "component:core"
    assert d["type"] == NODE_TYPE_COMPONENT
    assert d["name"] == "core"
    assert d["display_name"] == "Core"
    assert d["description"] == "Core bot logic"
    assert d["priority"] == 10
    assert d["owner_engine"] == "component_detector"
    assert d["source"] == SOURCE_COMPONENT_REGISTRY
    assert d["metadata"] == {"key": "value"}
    assert d["neighbours"] == ["file:src/core/handler.py"]
    print("  [PASS] test_graph_node_serialisation")


def test_graph_edge_serialisation():
    """GraphEdge round-trips through to_dict."""
    edge = GraphEdge(
        edge_id="component:core--depends_on-->dependency:aiogram",
        source_id="component:core",
        target_id="dependency:aiogram",
        kind=EDGE_DEPENDS_ON,
        source=SOURCE_DEPENDENCY_REPORT,
        description="Core depends on aiogram",
    )
    d = edge.to_dict()
    assert d["edge_id"] == "component:core--depends_on-->dependency:aiogram"
    assert d["source_id"] == "component:core"
    assert d["target_id"] == "dependency:aiogram"
    assert d["kind"] == EDGE_DEPENDS_ON
    assert d["source"] == SOURCE_DEPENDENCY_REPORT
    assert d["description"] == "Core depends on aiogram"
    print("  [PASS] test_graph_edge_serialisation")


def test_graph_finding_serialisation():
    """GraphFinding round-trips through to_dict."""
    f = GraphFinding(
        severity=SEVERITY_ERROR,
        code="circular_dependency",
        message="A -> B -> A",
        affected="component:a",
        category=CATEGORY_CIRCULAR_DEPENDENCY,
        resolution_hint="Break the cycle",
        cycle=["component:a", "component:b", "component:a"],
    )
    d = f.to_dict()
    assert d["severity"] == SEVERITY_ERROR
    assert d["code"] == "circular_dependency"
    assert d["message"] == "A -> B -> A"
    assert d["affected"] == "component:a"
    assert d["category"] == CATEGORY_CIRCULAR_DEPENDENCY
    assert d["resolution_hint"] == "Break the cycle"
    assert d["cycle"] == ["component:a", "component:b", "component:a"]
    print("  [PASS] test_graph_finding_serialisation")


def test_graph_indices_serialisation():
    """GraphIndices round-trips through to_dict."""
    indices = GraphIndices()
    indices.node_by_id["component:core"] = GraphNode(
        node_id="component:core", type=NODE_TYPE_COMPONENT, name="core",
    )
    indices.nodes_by_type[NODE_TYPE_COMPONENT] = ["component:core"]
    indices.nodes_by_type[NODE_TYPE_FILE] = []
    indices.node_by_name["core"] = "component:core"
    d = indices.to_dict()
    assert d["node_count"] == 1
    assert NODE_TYPE_COMPONENT in d["nodes_by_type"]
    print("  [PASS] test_graph_indices_serialisation")


def test_graph_provenance_serialisation():
    """GraphProvenance round-trips through to_dict."""
    prov = GraphProvenance(
        project_name="my_store_bot",
        blueprint_name="my_store_bot",
        validation_status=STATUS_APPROVED,
        structure_map_name="my_store_bot",
        component_registry_name="my_store_bot",
        file_plan_name="my_store_bot",
        dependency_report_name="my_store_bot",
        project_context_name="my_store_bot",
        all_sources_used=list(ALL_SOURCES),
    )
    d = prov.to_dict()
    assert d["project_name"] == "my_store_bot"
    assert d["blueprint_name"] == "my_store_bot"
    assert d["validation_status"] == STATUS_APPROVED
    assert d["structure_map_name"] == "my_store_bot"
    assert d["component_registry_name"] == "my_store_bot"
    assert d["file_plan_name"] == "my_store_bot"
    assert d["dependency_report_name"] == "my_store_bot"
    assert d["project_context_name"] == "my_store_bot"
    assert len(d["all_sources_used"]) == 7
    print("  [PASS] test_graph_provenance_serialisation")


def test_intelligence_graph_to_dict():
    """ProjectIntelligenceGraph.to_dict returns the full structure."""
    ctx = make_full_context()
    engine = IntelligenceGraphEngine()
    engine.execute(ctx)
    graph = ctx.get("intelligence_graph")
    d = graph.to_dict()
    assert d["node_count"] == graph.node_count
    assert d["edge_count"] == graph.edge_count
    assert d["finding_count"] == graph.finding_count
    assert d["node_type_count"] == graph.node_type_count
    assert d["edge_kind_count"] == graph.edge_kind_count
    assert len(d["nodes"]) == graph.node_count
    assert len(d["edges"]) == graph.edge_count
    assert "provenance" in d
    assert "indices" in d
    assert "summary" in d
    assert "notes" in d
    print("  [PASS] test_intelligence_graph_to_dict")


# ---------------------------------------------------------------------------#
# 13. End-to-end tests
# ---------------------------------------------------------------------------#

def test_end_to_end_full_pipeline():
    """Run the engine and verify the intelligence graph."""
    ctx = make_full_context()
    engine = IntelligenceGraphEngine()
    result = engine.execute(ctx)

    assert result.success, f"Engine failed: {result.errors}"
    graph = ctx.get("intelligence_graph")
    assert graph is not None
    assert isinstance(graph, ProjectIntelligenceGraph)
    assert graph.node_count > 0
    assert graph.edge_count > 0
    assert graph.node_type_count > 0
    assert len(graph.provenance.all_sources_used) == 7
    assert graph.summary
    assert len(graph.notes) > 0
    # No error-level findings.
    error_findings = [f for f in graph.findings if f.severity == SEVERITY_ERROR]
    assert len(error_findings) == 0
    print("  [PASS] test_end_to_end_full_pipeline")


def test_end_to_end_with_dependency_resolver():
    """Run dependency resolver, project context, then intelligence graph in sequence."""
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

    # Run the project context engine to produce the 7th artefact.
    pc_engine = ProjectContextEngine()
    pc_result = pc_engine.execute(ctx)
    assert pc_result.success

    # Now run the intelligence graph engine.
    ig_engine = IntelligenceGraphEngine()
    ig_result = ig_engine.execute(ctx)
    assert ig_result.success, f"Intelligence graph failed: {ig_result.errors}"
    graph = ctx.get("intelligence_graph")
    assert graph is not None
    assert graph.node_count > 0
    print("  [PASS] test_end_to_end_with_dependency_resolver")


def test_end_to_end_graph_navigation():
    """Navigate the graph from the project node to features and components."""
    ctx = make_full_context()
    engine = IntelligenceGraphEngine()
    engine.execute(ctx)
    graph = ctx.get("intelligence_graph")

    # Start from the project node.
    project_nodes = graph.nodes_of_type(NODE_TYPE_PROJECT)
    assert len(project_nodes) == 1
    project = project_nodes[0]

    # The project should have outgoing edges.
    out = graph.outgoing(project.node_id)
    assert len(out) > 0

    # The project should be able to reach other nodes.
    reachable = graph.reachable(project.node_id, max_hops=8)
    assert len(reachable) > 1

    # Look up a component by type and name.
    core = graph.get_node_by_type_and_name(NODE_TYPE_COMPONENT, "core")
    if core is not None:
        assert core.type == NODE_TYPE_COMPONENT
        assert core.name == "core"

    print("  [PASS] test_end_to_end_graph_navigation")


def test_end_to_end_all_node_types_present():
    """The graph built from a full context has multiple node types."""
    ctx = make_full_context()
    engine = IntelligenceGraphEngine()
    engine.execute(ctx)
    graph = ctx.get("intelligence_graph")

    # The graph should have nodes of several different types.
    types_present = set()
    for node in graph.nodes:
        types_present.add(node.type)
    assert NODE_TYPE_PROJECT in types_present
    assert NODE_TYPE_COMPONENT in types_present
    assert NODE_TYPE_FEATURE in types_present or NODE_TYPE_FILE in types_present
    print("  [PASS] test_end_to_end_all_node_types_present")


# ---------------------------------------------------------------------------#
# Test runner
# ---------------------------------------------------------------------------#

def run_all_tests():
    tests = [
        # Data model
        test_graph_node_creation,
        test_graph_node_to_dict,
        test_graph_edge_creation,
        test_graph_edge_to_dict,
        test_graph_finding_creation,
        test_graph_finding_to_dict,
        test_graph_indices_creation,
        test_graph_indices_to_dict,
        test_graph_provenance_creation,
        test_graph_provenance_to_dict,
        test_source_artefact_constants,
        test_severity_constants,
        test_node_type_constants,
        test_edge_kind_constants,
        test_category_constants,
        # ProjectIntelligenceGraph convenience
        test_graph_empty,
        test_graph_counts,
        test_graph_has_errors,
        test_graph_add_finding,
        test_graph_get_node_methods,
        test_graph_nodes_of_type,
        test_graph_outgoing_incoming,
        test_graph_outgoing_incoming_by_kind,
        test_graph_edges_from_to_of_kind,
        test_graph_neighbours,
        test_graph_reachable,
        test_graph_shortest_path,
        # GraphBuilder
        test_builder_produces_graph,
        test_builder_creates_project_node,
        test_builder_creates_feature_nodes,
        test_builder_creates_component_nodes,
        test_builder_creates_stage_nodes,
        test_builder_creates_folder_nodes,
        test_builder_creates_file_nodes,
        test_builder_creates_dependency_nodes,
        test_builder_creates_route_nodes,
        test_builder_creates_command_nodes,
        test_builder_creates_configuration_nodes,
        test_builder_creates_environment_variable_nodes,
        test_builder_creates_edges,
        test_builder_node_dedup,
        test_builder_edge_dedup,
        test_builder_provenance,
        test_builder_node_ids_format,
        test_builder_edge_ids_format,
        test_builder_node_has_required_fields,
        # GraphNavigator
        test_navigator_builds_indices,
        test_navigator_node_by_id,
        test_navigator_nodes_by_type,
        test_navigator_node_by_name,
        test_navigator_node_id_by_type_and_name,
        test_navigator_edges_by_source,
        test_navigator_edges_by_target,
        test_navigator_out_edges,
        test_navigator_in_edges,
        test_navigator_out_edges_by_kind,
        test_navigator_in_edges_by_kind,
        test_navigator_edges_by_kind,
        test_navigator_returns_graph,
        # CircularDetector
        test_detector_no_findings_on_clean_graph,
        test_detector_detects_circular_dependency,
        test_detector_three_node_cycle,
        test_detector_no_cycle_with_non_dependency_edges,
        test_detector_broken_references,
        test_detector_unused_components,
        test_detector_orphan_files,
        test_detector_dead_components,
        test_detector_cycle_normalisation,
        # GraphValidator
        test_validator_no_findings_on_clean_graph,
        test_validator_duplicate_node_ids,
        test_validator_duplicate_edge_ids,
        test_validator_edge_source_not_found,
        test_validator_edge_target_not_found,
        test_validator_unknown_node_type,
        test_validator_unknown_edge_kind,
        test_validator_empty_node_id,
        test_validator_empty_node_name,
        test_validator_self_loop,
        test_validator_missing_project_node,
        test_validator_multiple_project_nodes,
        test_validator_indices_consistency,
        # Engine — data source requirements
        test_engine_requires_blueprint,
        test_engine_requires_validation_report,
        test_engine_requires_structure_map,
        test_engine_requires_registry,
        test_engine_requires_file_plan,
        test_engine_requires_dependency_report,
        test_engine_requires_project_context,
        test_engine_does_not_read_request,
        # Engine — type checking
        test_engine_type_check_blueprint,
        test_engine_type_check_validation_report,
        test_engine_type_check_structure_map,
        test_engine_type_check_registry,
        test_engine_type_check_file_plan,
        test_engine_type_check_dependency_report,
        test_engine_type_check_project_context,
        # Engine — output verification
        test_engine_produces_graph,
        test_engine_graph_stored_in_metadata,
        test_engine_records_provenance,
        test_engine_graph_has_summary,
        test_engine_graph_has_notes,
        test_engine_graph_has_indices,
        test_engine_graph_node_type_count,
        test_engine_graph_edge_kind_count,
        test_engine_metadata_in_result,
        test_engine_graph_no_errors,
        test_engine_graph_has_project_node,
        test_engine_graph_navigation_works,
        # Graph integrity
        test_graph_all_node_types_known,
        test_graph_all_edge_kinds_known,
        test_graph_no_duplicate_node_ids,
        test_graph_no_duplicate_edge_ids,
        test_graph_provenance_all_sources,
        test_graph_node_sources_valid,
        # Bootstrap
        test_bootstrap_registers_intelligence_graph,
        test_bootstrap_intelligence_graph_priority,
        test_bootstrap_intelligence_graph_dependencies,
        # Serialisation
        test_graph_node_serialisation,
        test_graph_edge_serialisation,
        test_graph_finding_serialisation,
        test_graph_indices_serialisation,
        test_graph_provenance_serialisation,
        test_intelligence_graph_to_dict,
        # End-to-end
        test_end_to_end_full_pipeline,
        test_end_to_end_with_dependency_resolver,
        test_end_to_end_graph_navigation,
        test_end_to_end_all_node_types_present,
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
