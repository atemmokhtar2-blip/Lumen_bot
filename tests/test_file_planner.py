#!/usr/bin/env python3
"""
Comprehensive test suite for the File Generation Planning Engine
(Specification 008).

These tests cover every aspect of the specification:

1. Data model integrity (FileGenerationPlan, FilePlanEntry,
   FileRelationship, FileGenerationOrderEntry, PlanFinding,
   generation-priority constants, extension constants, file-type
   constants).
2. The ComponentAnalyzer (analyse, group files, missing-file findings).
3. The FileDeterminer (determine files, assign metadata, extensions,
   file types, priorities, reason for existence).
4. The RelationshipResolver (component-based dependencies, package-init
   relationships, warnings).
5. The GenerationOrderComputer (topological sort, priority tie-breaking,
   build_order assignment).
6. The ConflictDetector (duplicates, naming conflicts, useless files,
   unlinked files, dangling dependencies, circular dependencies).
7. The PlanValidator (plan not empty, all components have files, all
   files have purpose, all files have engine, all files have folder,
   all files have component, all relationships valid, generation order
   valid).
8. The main engine reads ONLY the project_blueprint,
   blueprint_validation_report, project_structure_map, and
   component_registry artefacts (not the raw request).
9. The main engine produces a FileGenerationPlan artefact.
10. The main engine fails when each artefact is missing.
11. The main engine fails when the artefacts are the wrong type.
12. The generation order is topologically valid (no file before its
    dependencies).
13. No file is created on disk (the engine only plans).
14. Bootstrap integration (engine registered in registry and manager).
15. Config section exists.
16. Serialisation (to_dict) for all data model classes.
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
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    SEVERITY_INFO,
    GENERATION_PRIORITY_INFRASTRUCTURE,
    GENERATION_PRIORITY_CORE,
    GENERATION_PRIORITY_DATABASE,
    GENERATION_PRIORITY_FEATURES,
    GENERATION_PRIORITY_WIRING,
    GENERATION_PRIORITY_ENTRY,
    GENERATION_PRIORITY_DOCS,
    GENERATION_PRIORITY_TESTS,
    ALL_GENERATION_PRIORITIES,
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
    ALL_EXTENSIONS,
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
    ALL_FILE_TYPES,
    ComponentAnalyzer,
    ComponentFileAnalysis,
    ComponentAnalysisResult,
    FileDeterminer,
    RelationshipResolver,
    GenerationOrderComputer,
    ConflictDetector,
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
):
    """Build a generation context with the four file-planner artefacts.

    The request field is intentionally set to a string that the engine
    must NOT read.
    """
    ctx = GenerationContext(
        request="test request (must not be read by file planner)",
        config=make_config(),
        work_dir=Path("/tmp/test_file_planner"),
    )
    if blueprint is not None:
        ctx.set("project_blueprint", blueprint)
    if validation_report is not None:
        ctx.set("blueprint_validation_report", validation_report)
    if structure_map is not None:
        ctx.set("project_structure_map", structure_map)
    if registry is not None:
        ctx.set("component_registry", registry)
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
                engine_id="file_planner",
                name="File Planner",
                phase="plan_files",
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
    """Build a structure map with folders and files linked to components.

    The files use ``source_component`` values that match the component
    names in :func:`make_component_registry` so the planner can wire
    them up.
    """
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
        # Root package init.
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
        # Core component.
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
        # Database component.
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
        # Store / command handler component.
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
    structure map's ``source_component`` values.

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


def make_full_context(name="my_store_bot"):
    """Build a context with all four artefacts set."""
    blueprint = make_valid_blueprint(name)
    report = make_approved_report(name)
    structure_map = make_structure_map(name)
    registry = make_component_registry(name)
    return make_context(blueprint, report, structure_map, registry)


# ---------------------------------------------------------------------------#
# 1. Data model tests
# ---------------------------------------------------------------------------#

def test_file_plan_entry_creation():
    """FilePlanEntry can be created and serialised."""
    entry = FilePlanEntry(
        name="main.py",
        path="src/main.py",
        extension=EXTENSION_PYTHON,
        file_type=FP_FILE_TYPE_PYTHON_MODULE,
        purpose="Bot entry point.",
        responsible_engine="code_generator",
        generation_priority=GENERATION_PRIORITY_CORE,
        folder="src",
        source_component="core",
        reason_for_existence="File 'main.py' exists to start the bot.",
        contains_code=True,
    )
    assert entry.name == "main.py"
    assert entry.path == "src/main.py"
    assert entry.extension == EXTENSION_PYTHON
    assert entry.file_type == FP_FILE_TYPE_PYTHON_MODULE
    assert entry.responsible_engine == "code_generator"
    assert entry.generation_priority == GENERATION_PRIORITY_CORE
    assert entry.contains_code is True
    d = entry.to_dict()
    assert d["name"] == "main.py"
    assert d["path"] == "src/main.py"
    assert d["extension"] == EXTENSION_PYTHON
    assert d["file_type"] == FP_FILE_TYPE_PYTHON_MODULE
    assert d["responsible_engine"] == "code_generator"
    assert d["contains_code"] is True
    print("  [PASS] test_file_plan_entry_creation")


def test_file_plan_entry_requires_name():
    """FilePlanEntry raises ValueError without a name or path."""
    try:
        FilePlanEntry(name="", path="src/main.py")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    try:
        FilePlanEntry(name="main.py", path="")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    print("  [PASS] test_file_plan_entry_requires_name")


def test_file_plan_entry_add_dependency():
    """FilePlanEntry.add_dependency and add_dependent work correctly."""
    entry = FilePlanEntry(name="main.py", path="src/main.py")
    entry.add_dependency("src/config.py")
    entry.add_dependency("src/config.py")  # no duplicates
    assert entry.depends_on == ["src/config.py"]
    entry.add_dependent("src/bot.py")
    entry.add_dependent("src/bot.py")  # no duplicates
    assert entry.depended_by == ["src/bot.py"]
    entry.add_dependency("")  # empty string ignored
    assert entry.depends_on == ["src/config.py"]
    print("  [PASS] test_file_plan_entry_add_dependency")


def test_file_relationship():
    """FileRelationship can be created and serialised."""
    rel = FileRelationship(
        source="src/main.py",
        target="src/config.py",
        kind="depends_on",
        description="main.py depends on config.py",
    )
    assert rel.source == "src/main.py"
    assert rel.target == "src/config.py"
    assert rel.kind == "depends_on"
    d = rel.to_dict()
    assert d["source"] == "src/main.py"
    assert d["target"] == "src/config.py"
    assert d["kind"] == "depends_on"
    print("  [PASS] test_file_relationship")


def test_file_generation_order_entry():
    """FileGenerationOrderEntry can be created and serialised."""
    entry = FileGenerationOrderEntry(
        position=0,
        file_path="src/main.py",
        file_name="main.py",
        responsible_engine="code_generator",
        source_component="core",
    )
    assert entry.position == 0
    assert entry.file_path == "src/main.py"
    assert entry.file_name == "main.py"
    assert entry.responsible_engine == "code_generator"
    d = entry.to_dict()
    assert d["position"] == 0
    assert d["file_path"] == "src/main.py"
    assert d["file_name"] == "main.py"
    print("  [PASS] test_file_generation_order_entry")


def test_plan_finding():
    """PlanFinding can be created and serialised."""
    finding = PlanFinding(
        severity=SEVERITY_ERROR,
        code="duplicate_file",
        message="Duplicate file detected.",
        affected="src/main.py",
        resolution_hint="Rename the duplicate.",
    )
    assert finding.severity == SEVERITY_ERROR
    assert finding.code == "duplicate_file"
    d = finding.to_dict()
    assert d["severity"] == SEVERITY_ERROR
    assert d["code"] == "duplicate_file"
    assert d["affected"] == "src/main.py"
    print("  [PASS] test_plan_finding")


def test_file_generation_plan():
    """FileGenerationPlan can be created, queried, and serialised."""
    plan = FileGenerationPlan(
        project_name="test_bot",
        root_path="test_bot",
        files=[FilePlanEntry(name="main.py", path="test_bot/main.py")],
        relationships=[
            FileRelationship(
                source="test_bot/main.py",
                target="test_bot/config.py",
            ),
        ],
        generation_order=[
            FileGenerationOrderEntry(
                position=0, file_path="test_bot/main.py",
                file_name="main.py",
            ),
        ],
    )
    assert plan.project_name == "test_bot"
    assert plan.file_count == 1
    assert not plan.is_empty
    assert plan.file_paths() == ["test_bot/main.py"]
    assert plan.file_names() == ["main.py"]
    assert plan.has_file("test_bot/main.py")
    assert not plan.has_file("does/not/exist.py")
    f = plan.get_file("test_bot/main.py")
    assert f is not None
    assert f.name == "main.py"
    # files_for_component and files_for_engine.
    plan.files[0].source_component = "core"
    plan.files[0].responsible_engine = "code_generator"
    assert len(plan.files_for_component("core")) == 1
    assert len(plan.files_for_engine("code_generator")) == 1
    d = plan.to_dict()
    assert d["project_name"] == "test_bot"
    assert d["file_count"] == 1
    assert len(d["files"]) == 1
    assert len(d["relationships"]) == 1
    assert len(d["generation_order"]) == 1
    print("  [PASS] test_file_generation_plan")


def test_file_generation_plan_empty():
    """An empty FileGenerationPlan has the correct properties."""
    plan = FileGenerationPlan()
    assert plan.file_count == 0
    assert plan.is_empty
    assert plan.file_paths() == []
    assert plan.file_names() == []
    print("  [PASS] test_file_generation_plan_empty")


def test_file_generation_plan_add_finding():
    """FileGenerationPlan.add_finding records findings and warnings."""
    plan = FileGenerationPlan()
    plan.add_finding(
        SEVERITY_WARNING, "test_warning", "A warning message.",
    )
    assert len(plan.findings) == 1
    assert len(plan.warnings) == 1
    assert plan.warnings[0] == "A warning message."
    # Error findings do not add to warnings.
    plan.add_finding(
        SEVERITY_ERROR, "test_error", "An error message.",
    )
    assert len(plan.findings) == 2
    assert len(plan.warnings) == 1  # still only the warning
    print("  [PASS] test_file_generation_plan_add_finding")


def test_generation_priority_constants():
    """Generation priority constants are distinct and ordered."""
    assert GENERATION_PRIORITY_INFRASTRUCTURE < GENERATION_PRIORITY_CORE
    assert GENERATION_PRIORITY_CORE < GENERATION_PRIORITY_DATABASE
    assert GENERATION_PRIORITY_DATABASE < GENERATION_PRIORITY_FEATURES
    assert GENERATION_PRIORITY_FEATURES < GENERATION_PRIORITY_WIRING
    assert GENERATION_PRIORITY_WIRING < GENERATION_PRIORITY_ENTRY
    assert GENERATION_PRIORITY_ENTRY < GENERATION_PRIORITY_DOCS
    assert GENERATION_PRIORITY_DOCS < GENERATION_PRIORITY_TESTS
    assert len(ALL_GENERATION_PRIORITIES) == 8
    # All priorities are unique.
    assert len(set(ALL_GENERATION_PRIORITIES)) == 8
    print("  [PASS] test_generation_priority_constants")


def test_extension_constants():
    """Extension constants are defined."""
    assert EXTENSION_PYTHON == ".py"
    assert EXTENSION_YAML == ".yaml"
    assert EXTENSION_YML == ".yml"
    assert EXTENSION_TOML == ".toml"
    assert EXTENSION_JSON == ".json"
    assert EXTENSION_ENV == ".env"
    assert EXTENSION_SQL == ".sql"
    assert EXTENSION_MARKDOWN == ".md"
    assert EXTENSION_TEXT == ".txt"
    assert EXTENSION_DOCKERFILE == ""
    assert EXTENSION_SCRIPT == ".sh"
    assert len(ALL_EXTENSIONS) == 11
    print("  [PASS] test_extension_constants")


def test_file_type_constants():
    """File-type constants are defined and the file-planner owns them."""
    assert FP_FILE_TYPE_PYTHON_MODULE == "python_module"
    assert FP_FILE_TYPE_PYTHON_PACKAGE == "python_package"
    assert FILE_TYPE_CONFIG == "config"
    assert FP_FILE_TYPE_TEXT == "text"
    assert FP_FILE_TYPE_MARKDOWN == "markdown"
    assert FP_FILE_TYPE_YAML == "yaml"
    assert FILE_TYPE_TOML == "toml"
    assert FP_FILE_TYPE_ENV == "env"
    assert FP_FILE_TYPE_JSON == "json"
    assert FP_FILE_TYPE_SQL == "sql"
    assert FP_FILE_TYPE_DOCKERFILE == "dockerfile"
    assert FILE_TYPE_SCRIPT == "script"
    assert FILE_TYPE_REQUIREMENTS == "requirements"
    assert len(ALL_FILE_TYPES) == 13
    # All file types are unique.
    assert len(set(ALL_FILE_TYPES)) == 13
    print("  [PASS] test_file_type_constants")


# ---------------------------------------------------------------------------#
# 2. ComponentAnalyzer tests
# ---------------------------------------------------------------------------#

def test_component_analyzer_basic():
    """ComponentAnalyzer groups files by component."""
    analyzer = ComponentAnalyzer()
    registry = make_component_registry()
    structure_map = make_structure_map()
    result = analyzer.analyze(registry, structure_map)
    assert isinstance(result, ComponentAnalysisResult)
    assert result.component_count == 3
    assert "core" in result.component_names
    assert "database" in result.component_names
    assert "store_command" in result.component_names
    # The store_command component should have files.
    store_analysis = result.get("store_command")
    assert store_analysis.has_files
    assert len(store_analysis.files) >= 1
    print("  [PASS] test_component_analyzer_basic")


def test_component_analyzer_missing_files():
    """ComponentAnalyzer records components without files."""
    analyzer = ComponentAnalyzer()
    registry = ComponentRegistry(
        project_name="test",
        components=[
            DetectedComponent(name="orphan", type=COMPONENT_TYPE_UTILITY),
            DetectedComponent(
                name="core", type=COMPONENT_TYPE_SERVICE,
                source_blueprint_component="core",
            ),
        ],
    )
    # Structure map with a file for "core" but not for "orphan".
    structure_map = ProjectStructureMap(
        project_name="test",
        root_path="test",
        folders=[FolderEntry(name="test", path="test")],
        files=[
            FileEntry(
                name="core.py", path="test/core.py",
                source_component="core",
            ),
        ],
    )
    result = analyzer.analyze(registry, structure_map)
    assert "orphan" in result.components_without_files
    assert "core" not in result.components_without_files
    print("  [PASS] test_component_analyzer_missing_files")


def test_component_analyzer_findings_for_missing_files():
    """findings_for_missing_files produces warnings."""
    analyzer = ComponentAnalyzer()
    registry = ComponentRegistry(
        project_name="test",
        components=[
            DetectedComponent(name="orphan", type=COMPONENT_TYPE_UTILITY),
        ],
    )
    structure_map = ProjectStructureMap(
        project_name="test",
        root_path="test",
        folders=[],
        files=[],
    )
    result = analyzer.analyze(registry, structure_map)
    findings = analyzer.findings_for_missing_files(result)
    assert len(findings) == 1
    assert findings[0].severity == SEVERITY_WARNING
    assert findings[0].code == "component_without_files"
    assert findings[0].affected == "orphan"
    print("  [PASS] test_component_analyzer_findings_for_missing_files")


def test_component_analyzer_pure():
    """ComponentAnalyzer does not mutate the registry or structure map."""
    analyzer = ComponentAnalyzer()
    registry = make_component_registry()
    structure_map = make_structure_map()
    comp_count_before = registry.component_count
    file_count_before = len(structure_map.files)
    analyzer.analyze(registry, structure_map)
    assert registry.component_count == comp_count_before
    assert len(structure_map.files) == file_count_before
    print("  [PASS] test_component_analyzer_pure")


# ---------------------------------------------------------------------------#
# 3. FileDeterminer tests
# ---------------------------------------------------------------------------#

def test_file_determiner_basic():
    """FileDeterminer converts structure map files to plan entries."""
    analyzer = ComponentAnalyzer()
    determiner = FileDeterminer()
    registry = make_component_registry()
    structure_map = make_structure_map()
    analysis = analyzer.analyze(registry, structure_map)
    files = determiner.determine(analysis, structure_map)
    assert len(files) == len(structure_map.files)
    # Every entry should be a FilePlanEntry.
    for f in files:
        assert isinstance(f, FilePlanEntry)
        assert f.name
        assert f.path
        assert f.purpose
        assert f.reason_for_existence
    print("  [PASS] test_file_determiner_basic")


def test_file_determiner_extension_derivation():
    """FileDeterminer derives the correct extension."""
    analyzer = ComponentAnalyzer()
    determiner = FileDeterminer()
    registry = make_component_registry()
    structure_map = make_structure_map()
    analysis = analyzer.analyze(registry, structure_map)
    files = determiner.determine(analysis, structure_map)
    by_path = {f.path: f for f in files}
    # Python module.
    bot = by_path["my_store_bot/core/bot.py"]
    assert bot.extension == EXTENSION_PYTHON
    # Dockerfile has no extension.
    # (Add a Dockerfile to test this edge case.)
    structure_map.files.append(FileEntry(
        name="Dockerfile", path="my_store_bot/Dockerfile",
        file_type=FILE_TYPE_DOCKERFILE,
        purpose="Container image definition.",
        folder="my_store_bot",
        building_engine="code_generator",
        build_order=BUILD_ORDER_INFRASTRUCTURE,
        source_component="core",
    ))
    files2 = determiner.determine(
        analyzer.analyze(registry, structure_map), structure_map,
    )
    dockerfile = next(
        f for f in files2 if f.name == "Dockerfile"
    )
    assert dockerfile.extension == EXTENSION_DOCKERFILE
    print("  [PASS] test_file_determiner_extension_derivation")


def test_file_determiner_file_type_derivation():
    """FileDeterminer derives the correct file type."""
    analyzer = ComponentAnalyzer()
    determiner = FileDeterminer()
    registry = make_component_registry()
    structure_map = make_structure_map()
    analysis = analyzer.analyze(registry, structure_map)
    files = determiner.determine(analysis, structure_map)
    by_path = {f.path: f for f in files}
    # Python package init.
    root_init = by_path["my_store_bot/__init__.py"]
    assert root_init.file_type == FP_FILE_TYPE_PYTHON_PACKAGE
    # Python module.
    bot = by_path["my_store_bot/core/bot.py"]
    assert bot.file_type == FP_FILE_TYPE_PYTHON_MODULE
    print("  [PASS] test_file_determiner_file_type_derivation")


def test_file_determiner_priority_derivation():
    """FileDeterminer derives the correct generation priority."""
    analyzer = ComponentAnalyzer()
    determiner = FileDeterminer()
    registry = make_component_registry()
    structure_map = make_structure_map()
    analysis = analyzer.analyze(registry, structure_map)
    files = determiner.determine(analysis, structure_map)
    by_path = {f.path: f for f in files}
    # Infrastructure.
    root_init = by_path["my_store_bot/__init__.py"]
    assert root_init.generation_priority == GENERATION_PRIORITY_INFRASTRUCTURE
    # Core.
    bot = by_path["my_store_bot/core/bot.py"]
    assert bot.generation_priority == GENERATION_PRIORITY_CORE
    # Database.
    models = by_path["my_store_bot/database/models.py"]
    assert models.generation_priority == GENERATION_PRIORITY_DATABASE
    # Features.
    start = by_path["my_store_bot/handlers/start.py"]
    assert start.generation_priority == GENERATION_PRIORITY_FEATURES
    print("  [PASS] test_file_determiner_priority_derivation")


def test_file_determiner_source_component():
    """FileDeterminer assigns the correct source component."""
    analyzer = ComponentAnalyzer()
    determiner = FileDeterminer()
    registry = make_component_registry()
    structure_map = make_structure_map()
    analysis = analyzer.analyze(registry, structure_map)
    files = determiner.determine(analysis, structure_map)
    by_path = {f.path: f for f in files}
    bot = by_path["my_store_bot/core/bot.py"]
    assert bot.source_component == "core"
    models = by_path["my_store_bot/database/models.py"]
    assert models.source_component == "database"
    start = by_path["my_store_bot/handlers/start.py"]
    assert start.source_component == "store_command"
    print("  [PASS] test_file_determiner_source_component")


def test_file_determiner_reason_for_existence():
    """FileDeterminer assigns a reason for existence to every file."""
    analyzer = ComponentAnalyzer()
    determiner = FileDeterminer()
    registry = make_component_registry()
    structure_map = make_structure_map()
    analysis = analyzer.analyze(registry, structure_map)
    files = determiner.determine(analysis, structure_map)
    for f in files:
        assert f.reason_for_existence, (
            f"File '{f.path}' has no reason for existence."
        )
        # The reason should mention the file name.
        assert f.name in f.reason_for_existence
    print("  [PASS] test_file_determiner_reason_for_existence")


def test_file_determiner_responsible_engine():
    """FileDeterminer assigns the correct responsible engine."""
    analyzer = ComponentAnalyzer()
    determiner = FileDeterminer()
    registry = make_component_registry()
    structure_map = make_structure_map()
    analysis = analyzer.analyze(registry, structure_map)
    files = determiner.determine(analysis, structure_map)
    by_path = {f.path: f for f in files}
    bot = by_path["my_store_bot/core/bot.py"]
    assert bot.responsible_engine == "code_generator"
    models = by_path["my_store_bot/database/models.py"]
    assert models.responsible_engine == "database_engine"
    # A file with no building_engine defaults to code_generator.
    structure_map.files.append(FileEntry(
        name="util.py", path="my_store_bot/core/util.py",
        file_type=FILE_TYPE_PYTHON_MODULE,
        purpose="Utility functions.",
        folder="my_store_bot/core",
        building_engine="",
        build_order=BUILD_ORDER_CORE,
        source_component="core",
        contains_code=True,
    ))
    files2 = determiner.determine(
        analyzer.analyze(registry, structure_map), structure_map,
    )
    util = next(f for f in files2 if f.name == "util.py")
    assert util.responsible_engine == "code_generator"
    print("  [PASS] test_file_determiner_responsible_engine")


# ---------------------------------------------------------------------------#
# 4. RelationshipResolver tests
# ---------------------------------------------------------------------------#

def test_relationship_resolver_component_based():
    """RelationshipResolver derives file deps from the component graph."""
    analyzer = ComponentAnalyzer()
    determiner = FileDeterminer()
    resolver = RelationshipResolver()
    registry = make_component_registry()
    structure_map = make_structure_map()
    analysis = analyzer.analyze(registry, structure_map)
    files = determiner.determine(analysis, structure_map)
    relationships, warnings = resolver.resolve(files, registry)
    # store_command depends on database, so start.py should depend on
    # the database's first file.
    start = next(
        f for f in files if f.path == "my_store_bot/handlers/start.py"
    )
    db_init = "my_store_bot/database/__init__.py"
    assert db_init in start.depends_on, (
        f"start.py should depend on the database init file. "
        f"Got: {start.depends_on}"
    )
    # There should be at least one relationship involving start.py.
    start_rels = [
        r for r in relationships if r.source == "my_store_bot/handlers/start.py"
    ]
    assert len(start_rels) > 0
    assert any(r.kind == "depends_on" for r in start_rels)
    print("  [PASS] test_relationship_resolver_component_based")


def test_relationship_resolver_package_init():
    """RelationshipResolver wires package init files to their modules."""
    analyzer = ComponentAnalyzer()
    determiner = FileDeterminer()
    resolver = RelationshipResolver()
    registry = make_component_registry()
    structure_map = make_structure_map()
    analysis = analyzer.analyze(registry, structure_map)
    files = determiner.determine(analysis, structure_map)
    relationships, _ = resolver.resolve(files, registry)
    # bot.py should depend on core/__init__.py.
    bot = next(f for f in files if f.path == "my_store_bot/core/bot.py")
    core_init = "my_store_bot/core/__init__.py"
    assert core_init in bot.depends_on, (
        f"bot.py should depend on core/__init__.py. "
        f"Got: {bot.depends_on}"
    )
    # There should be an "imports" relationship from bot.py to the init.
    import_rels = [
        r for r in relationships
        if r.source == "my_store_bot/core/bot.py"
        and r.target == core_init
        and r.kind == "imports"
    ]
    assert len(import_rels) > 0
    print("  [PASS] test_relationship_resolver_package_init")


def test_relationship_resolver_no_self_dependency():
    """RelationshipResolver does not create self-dependencies."""
    analyzer = ComponentAnalyzer()
    determiner = FileDeterminer()
    resolver = RelationshipResolver()
    registry = make_component_registry()
    structure_map = make_structure_map()
    analysis = analyzer.analyze(registry, structure_map)
    files = determiner.determine(analysis, structure_map)
    relationships, _ = resolver.resolve(files, registry)
    # No relationship should have source == target.
    for r in relationships:
        assert r.source != r.target, (
            f"Self-dependency: {r.source} -> {r.target}"
        )
    print("  [PASS] test_relationship_resolver_no_self_dependency")


def test_relationship_resolver_dangling_warning():
    """RelationshipResolver warns when a dependency component has no files."""
    analyzer = ComponentAnalyzer()
    determiner = FileDeterminer()
    resolver = RelationshipResolver()
    # A component depends on a component that has no files.
    registry = ComponentRegistry(
        project_name="test",
        components=[
            DetectedComponent(
                name="handler", type=COMPONENT_TYPE_COMMAND,
                depends_on=["missing_component"],
            ),
            DetectedComponent(
                name="missing_component", type=COMPONENT_TYPE_UTILITY,
            ),
        ],
    )
    structure_map = ProjectStructureMap(
        project_name="test",
        root_path="test",
        folders=[FolderEntry(name="test", path="test")],
        files=[
            FileEntry(
                name="handler.py", path="test/handler.py",
                source_component="handler",
                contains_code=True,
            ),
        ],
    )
    analysis = analyzer.analyze(registry, structure_map)
    files = determiner.determine(analysis, structure_map)
    _, warnings = resolver.resolve(files, registry)
    assert len(warnings) > 0
    assert any("missing_component" in w for w in warnings)
    print("  [PASS] test_relationship_resolver_dangling_warning")


# ---------------------------------------------------------------------------#
# 5. GenerationOrderComputer tests
# ---------------------------------------------------------------------------#

def test_generation_order_computer_basic():
    """GenerationOrderComputer produces a valid generation order."""
    analyzer = ComponentAnalyzer()
    determiner = FileDeterminer()
    resolver = RelationshipResolver()
    computer = GenerationOrderComputer()
    registry = make_component_registry()
    structure_map = make_structure_map()
    analysis = analyzer.analyze(registry, structure_map)
    files = determiner.determine(analysis, structure_map)
    resolver.resolve(files, registry)
    order = computer.compute(files)
    assert len(order) == len(files)
    # Positions should be sequential (0, 1, 2, ...).
    for i, entry in enumerate(order):
        assert entry.position == i
    # Every file should have a build_order assigned.
    for f in files:
        assert f.build_order >= 0
    print("  [PASS] test_generation_order_computer_basic")


def test_generation_order_computer_topological_validity():
    """Generation order respects dependencies (no file before its deps)."""
    analyzer = ComponentAnalyzer()
    determiner = FileDeterminer()
    resolver = RelationshipResolver()
    computer = GenerationOrderComputer()
    registry = make_component_registry()
    structure_map = make_structure_map()
    analysis = analyzer.analyze(registry, structure_map)
    files = determiner.determine(analysis, structure_map)
    resolver.resolve(files, registry)
    order = computer.compute(files)
    # Build a position lookup.
    position_by_path = {o.file_path: o.position for o in order}
    # For every file, each dependency must come before it.
    for f in files:
        my_pos = position_by_path[f.path]
        for dep in f.depends_on:
            if dep in position_by_path:
                assert position_by_path[dep] < my_pos, (
                    f"File '{f.path}' (pos {my_pos}) appears before "
                    f"its dependency '{dep}' (pos {position_by_path[dep]})."
                )
    print("  [PASS] test_generation_order_computer_topological_validity")


def test_generation_order_computer_empty():
    """GenerationOrderComputer handles an empty file list."""
    computer = GenerationOrderComputer()
    order = computer.compute([])
    assert order == []
    print("  [PASS] test_generation_order_computer_empty")


def test_generation_order_computer_no_dependencies():
    """Files with no dependencies get level 0 (earliest positions)."""
    computer = GenerationOrderComputer()
    files = [
        FilePlanEntry(
            name="a.py", path="src/a.py",
            generation_priority=GENERATION_PRIORITY_CORE,
        ),
        FilePlanEntry(
            name="b.py", path="src/b.py",
            generation_priority=GENERATION_PRIORITY_CORE,
        ),
    ]
    order = computer.compute(files)
    assert len(order) == 2
    # Both should be at level 0, sorted by path.
    assert order[0].file_path == "src/a.py"
    assert order[1].file_path == "src/b.py"
    print("  [PASS] test_generation_order_computer_no_dependencies")


# ---------------------------------------------------------------------------#
# 6. ConflictDetector tests
# ---------------------------------------------------------------------------#

def test_conflict_detector_no_conflicts():
    """ConflictDetector finds no conflicts in a clean plan."""
    analyzer = ComponentAnalyzer()
    determiner = FileDeterminer()
    resolver = RelationshipResolver()
    detector = ConflictDetector()
    registry = make_component_registry()
    structure_map = make_structure_map()
    analysis = analyzer.analyze(registry, structure_map)
    files = determiner.determine(analysis, structure_map)
    relationships, _ = resolver.resolve(files, registry)
    findings = detector.detect(files, relationships)
    # There should be no error-severity findings.
    errors = [f for f in findings if f.severity == SEVERITY_ERROR]
    assert len(errors) == 0, (
        f"Unexpected errors in clean plan: "
        f"{[(f.code, f.message) for f in errors]}"
    )
    print("  [PASS] test_conflict_detector_no_conflicts")


def test_conflict_detector_duplicates():
    """ConflictDetector detects duplicate file paths."""
    detector = ConflictDetector()
    files = [
        FilePlanEntry(
            name="a.py", path="src/a.py",
            purpose="First copy.",
            reason_for_existence="Reason.",
            source_component="core",
        ),
        FilePlanEntry(
            name="a.py", path="src/a.py",
            purpose="Second copy.",
            reason_for_existence="Reason.",
            source_component="core",
        ),
    ]
    findings = detector.detect(files, [])
    dup_findings = [f for f in findings if f.code == "duplicate_file"]
    assert len(dup_findings) >= 1
    assert dup_findings[0].severity == SEVERITY_ERROR
    print("  [PASS] test_conflict_detector_duplicates")


def test_conflict_detector_useless_file():
    """ConflictDetector detects files without purpose."""
    detector = ConflictDetector()
    files = [
        FilePlanEntry(
            name="useless.py", path="src/useless.py",
            purpose="",
            reason_for_existence="",
            source_component="core",
        ),
    ]
    findings = detector.detect(files, [])
    useless = [f for f in findings if f.code == "file_without_purpose"]
    assert len(useless) >= 1
    assert useless[0].severity == SEVERITY_ERROR
    print("  [PASS] test_conflict_detector_useless_file")


def test_conflict_detector_unlinked_file():
    """ConflictDetector detects unlinked files."""
    detector = ConflictDetector()
    files = [
        FilePlanEntry(
            name="lone.py", path="src/lone.py",
            purpose="A standalone file.",
            reason_for_existence="Reason.",
            source_component="core",
        ),
    ]
    findings = detector.detect(files, [])
    unlinked = [f for f in findings if f.code == "unlinked_file"]
    assert len(unlinked) >= 1
    assert unlinked[0].severity == SEVERITY_WARNING
    print("  [PASS] test_conflict_detector_unlinked_file")


def test_conflict_detector_dangling_dependency():
    """ConflictDetector detects dangling dependencies."""
    detector = ConflictDetector()
    files = [
        FilePlanEntry(
            name="a.py", path="src/a.py",
            purpose="File A.",
            reason_for_existence="Reason.",
            source_component="core",
            depends_on=["src/nonexistent.py"],
        ),
    ]
    findings = detector.detect(files, [])
    dangling = [f for f in findings if f.code == "dangling_dependency"]
    assert len(dangling) >= 1
    assert dangling[0].severity == SEVERITY_ERROR
    print("  [PASS] test_conflict_detector_dangling_dependency")


def test_conflict_detector_circular_dependency():
    """ConflictDetector detects circular dependencies."""
    detector = ConflictDetector()
    files = [
        FilePlanEntry(
            name="a.py", path="src/a.py",
            purpose="File A.",
            reason_for_existence="Reason.",
            source_component="core",
            depends_on=["src/b.py"],
        ),
        FilePlanEntry(
            name="b.py", path="src/b.py",
            purpose="File B.",
            reason_for_existence="Reason.",
            source_component="core",
            depends_on=["src/a.py"],
        ),
    ]
    findings = detector.detect(files, [])
    circular = [f for f in findings if f.code == "circular_dependency"]
    assert len(circular) >= 1
    assert circular[0].severity == SEVERITY_ERROR
    print("  [PASS] test_conflict_detector_circular_dependency")


# ---------------------------------------------------------------------------#
# 7. PlanValidator tests
# ---------------------------------------------------------------------------#

def test_plan_validator_valid_plan():
    """PlanValidator finds no errors in a valid plan."""
    analyzer = ComponentAnalyzer()
    determiner = FileDeterminer()
    resolver = RelationshipResolver()
    computer = GenerationOrderComputer()
    validator = PlanValidator()
    registry = make_component_registry()
    structure_map = make_structure_map()
    analysis = analyzer.analyze(registry, structure_map)
    files = determiner.determine(analysis, structure_map)
    relationships, _ = resolver.resolve(files, registry)
    order = computer.compute(files)
    plan = FileGenerationPlan(
        project_name="my_store_bot",
        root_path="my_store_bot",
        files=files,
        relationships=relationships,
        generation_order=order,
    )
    findings = validator.validate(plan, registry, structure_map)
    errors = [f for f in findings if f.severity == SEVERITY_ERROR]
    assert len(errors) == 0, (
        f"Unexpected validation errors: "
        f"{[(f.code, f.message) for f in errors]}"
    )
    print("  [PASS] test_plan_validator_valid_plan")


def test_plan_validator_empty_plan():
    """PlanValidator detects an empty plan."""
    validator = PlanValidator()
    registry = ComponentRegistry(project_name="test")
    structure_map = ProjectStructureMap(project_name="test")
    plan = FileGenerationPlan()
    findings = validator.validate(plan, registry, structure_map)
    empty = [f for f in findings if f.code == "empty_plan"]
    assert len(empty) == 1
    assert empty[0].severity == SEVERITY_ERROR
    print("  [PASS] test_plan_validator_empty_plan")


def test_plan_validator_component_without_files():
    """PlanValidator detects components without files."""
    validator = PlanValidator()
    registry = ComponentRegistry(
        project_name="test",
        components=[
            DetectedComponent(name="orphan", type=COMPONENT_TYPE_UTILITY),
            DetectedComponent(
                name="core", type=COMPONENT_TYPE_SERVICE,
                source_blueprint_component="core",
            ),
        ],
    )
    structure_map = ProjectStructureMap(
        project_name="test",
        root_path="test",
        folders=[FolderEntry(name="test", path="test")],
        files=[
            FileEntry(
                name="core.py", path="test/core.py",
                source_component="core",
                purpose="Core.",
                building_engine="code_generator",
            ),
        ],
    )
    plan = FileGenerationPlan(
        project_name="test",
        files=[
            FilePlanEntry(
                name="core.py", path="test/core.py",
                purpose="Core.",
                responsible_engine="code_generator",
                source_component="core",
                reason_for_existence="Reason.",
            ),
        ],
    )
    findings = validator.validate(plan, registry, structure_map)
    orphan_findings = [
        f for f in findings if f.code == "component_without_files"
    ]
    assert any(f.affected == "orphan" for f in orphan_findings)
    print("  [PASS] test_plan_validator_component_without_files")


def test_plan_validator_file_without_purpose():
    """PlanValidator detects files without a purpose."""
    validator = PlanValidator()
    registry = ComponentRegistry(project_name="test")
    structure_map = ProjectStructureMap(
        project_name="test",
        folders=[FolderEntry(name="test", path="test")],
    )
    plan = FileGenerationPlan(
        project_name="test",
        files=[
            FilePlanEntry(
                name="nopurpose.py", path="test/nopurpose.py",
                purpose="",
                responsible_engine="code_generator",
                source_component="core",
                reason_for_existence="Reason.",
            ),
        ],
    )
    findings = validator.validate(plan, registry, structure_map)
    nopurpose = [f for f in findings if f.code == "file_without_purpose"]
    assert len(nopurpose) >= 1
    assert nopurpose[0].severity == SEVERITY_ERROR
    print("  [PASS] test_plan_validator_file_without_purpose")


def test_plan_validator_file_without_engine():
    """PlanValidator detects files without a responsible engine."""
    validator = PlanValidator()
    registry = ComponentRegistry(project_name="test")
    structure_map = ProjectStructureMap(
        project_name="test",
        folders=[FolderEntry(name="test", path="test")],
    )
    plan = FileGenerationPlan(
        project_name="test",
        files=[
            FilePlanEntry(
                name="noengine.py", path="test/noengine.py",
                purpose="A file.",
                responsible_engine="",
                source_component="core",
                reason_for_existence="Reason.",
            ),
        ],
    )
    findings = validator.validate(plan, registry, structure_map)
    noengine = [f for f in findings if f.code == "file_without_engine"]
    assert len(noengine) >= 1
    assert noengine[0].severity == SEVERITY_ERROR
    print("  [PASS] test_plan_validator_file_without_engine")


def test_plan_validator_invalid_relationship():
    """PlanValidator detects relationships with invalid sources/targets."""
    validator = PlanValidator()
    registry = ComponentRegistry(project_name="test")
    structure_map = ProjectStructureMap(
        project_name="test",
        folders=[FolderEntry(name="test", path="test")],
    )
    plan = FileGenerationPlan(
        project_name="test",
        files=[
            FilePlanEntry(
                name="a.py", path="test/a.py",
                purpose="File A.",
                responsible_engine="code_generator",
                source_component="core",
                reason_for_existence="Reason.",
            ),
        ],
        relationships=[
            FileRelationship(
                source="test/a.py",
                target="test/nonexistent.py",
            ),
        ],
    )
    findings = validator.validate(plan, registry, structure_map)
    invalid_target = [
        f for f in findings if f.code == "invalid_relationship_target"
    ]
    assert len(invalid_target) >= 1
    assert invalid_target[0].severity == SEVERITY_ERROR
    print("  [PASS] test_plan_validator_invalid_relationship")


def test_plan_validator_generation_order_covers_all_files():
    """PlanValidator detects files missing from the generation order."""
    validator = PlanValidator()
    registry = ComponentRegistry(project_name="test")
    structure_map = ProjectStructureMap(
        project_name="test",
        folders=[FolderEntry(name="test", path="test")],
    )
    plan = FileGenerationPlan(
        project_name="test",
        files=[
            FilePlanEntry(
                name="a.py", path="test/a.py",
                purpose="File A.",
                responsible_engine="code_generator",
                source_component="core",
                reason_for_existence="Reason.",
            ),
            FilePlanEntry(
                name="b.py", path="test/b.py",
                purpose="File B.",
                responsible_engine="code_generator",
                source_component="core",
                reason_for_existence="Reason.",
            ),
        ],
        # Only a.py is in the order — b.py is missing.
        generation_order=[
            FileGenerationOrderEntry(
                position=0, file_path="test/a.py",
                file_name="a.py",
                responsible_engine="code_generator",
            ),
        ],
    )
    findings = validator.validate(plan, registry, structure_map)
    not_in_order = [f for f in findings if f.code == "file_not_in_order"]
    assert any(f.affected == "test/b.py" for f in not_in_order)
    print("  [PASS] test_plan_validator_generation_order_covers_all_files")


def test_plan_validator_generation_order_topological():
    """PlanValidator detects invalid generation order."""
    validator = PlanValidator()
    registry = ComponentRegistry(project_name="test")
    structure_map = ProjectStructureMap(
        project_name="test",
        folders=[FolderEntry(name="test", path="test")],
    )
    plan = FileGenerationPlan(
        project_name="test",
        files=[
            FilePlanEntry(
                name="a.py", path="test/a.py",
                purpose="File A.",
                responsible_engine="code_generator",
                source_component="core",
                reason_for_existence="Reason.",
                depends_on=["test/b.py"],
            ),
            FilePlanEntry(
                name="b.py", path="test/b.py",
                purpose="File B.",
                responsible_engine="code_generator",
                source_component="core",
                reason_for_existence="Reason.",
            ),
        ],
        # a.py depends on b.py, but a.py comes first (invalid).
        generation_order=[
            FileGenerationOrderEntry(
                position=0, file_path="test/a.py",
                file_name="a.py",
            ),
            FileGenerationOrderEntry(
                position=1, file_path="test/b.py",
                file_name="b.py",
            ),
        ],
    )
    findings = validator.validate(plan, registry, structure_map)
    invalid_order = [f for f in findings if f.code == "invalid_generation_order"]
    assert len(invalid_order) >= 1
    assert invalid_order[0].severity == SEVERITY_ERROR
    print("  [PASS] test_plan_validator_generation_order_topological")


# ---------------------------------------------------------------------------#
# 8. Main engine — data source
# ---------------------------------------------------------------------------#

def test_engine_requires_blueprint():
    """Engine fails when the project_blueprint artefact is missing."""
    engine = FileGenerationPlanningEngine()
    ctx = make_context(
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
    )
    result = engine.execute(ctx)
    assert not result.success
    assert any("project_blueprint" in e for e in result.errors)
    print("  [PASS] test_engine_requires_blueprint")


def test_engine_requires_validation_report():
    """Engine fails when the blueprint_validation_report artefact is missing."""
    engine = FileGenerationPlanningEngine()
    ctx = make_context(
        blueprint=make_valid_blueprint(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
    )
    result = engine.execute(ctx)
    assert not result.success
    assert any("blueprint_validation_report" in e for e in result.errors)
    print("  [PASS] test_engine_requires_validation_report")


def test_engine_requires_structure_map():
    """Engine fails when the project_structure_map artefact is missing."""
    engine = FileGenerationPlanningEngine()
    ctx = make_context(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        registry=make_component_registry(),
    )
    result = engine.execute(ctx)
    assert not result.success
    assert any("project_structure_map" in e for e in result.errors)
    print("  [PASS] test_engine_requires_structure_map")


def test_engine_requires_component_registry():
    """Engine fails when the component_registry artefact is missing."""
    engine = FileGenerationPlanningEngine()
    ctx = make_context(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
    )
    result = engine.execute(ctx)
    assert not result.success
    assert any("component_registry" in e for e in result.errors)
    print("  [PASS] test_engine_requires_component_registry")


def test_engine_does_not_read_request():
    """The engine's output does not depend on the request field."""
    blueprint = make_valid_blueprint()
    report = make_approved_report()
    structure_map = make_structure_map()
    registry = make_component_registry()

    ctx1 = make_context(blueprint, report, structure_map, registry)
    ctx1.request = "create a store bot"

    ctx2 = make_context(blueprint, report, structure_map, registry)
    ctx2.request = "completely different request text"

    engine = FileGenerationPlanningEngine()
    result1 = engine.execute(ctx1)
    result2 = engine.execute(ctx2)

    assert result1.success
    assert result2.success

    plan1 = ctx1.get("file_generation_plan")
    plan2 = ctx2.get("file_generation_plan")
    # The plans should be identical (same artefacts).
    assert plan1.file_count == plan2.file_count
    assert plan1.file_paths() == plan2.file_paths()
    print("  [PASS] test_engine_does_not_read_request")


def test_engine_type_check_blueprint():
    """Engine fails when the blueprint is the wrong type."""
    engine = FileGenerationPlanningEngine()
    ctx = make_context(
        blueprint="not a blueprint",
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry=make_component_registry(),
    )
    result = engine.execute(ctx)
    assert not result.success
    assert any("ProjectBlueprint" in e for e in result.errors)
    print("  [PASS] test_engine_type_check_blueprint")


def test_engine_type_check_structure_map():
    """Engine fails when the structure map is the wrong type."""
    engine = FileGenerationPlanningEngine()
    ctx = make_context(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map="not a structure map",
        registry=make_component_registry(),
    )
    result = engine.execute(ctx)
    assert not result.success
    assert any("ProjectStructureMap" in e for e in result.errors)
    print("  [PASS] test_engine_type_check_structure_map")


def test_engine_type_check_registry():
    """Engine fails when the registry is the wrong type."""
    engine = FileGenerationPlanningEngine()
    ctx = make_context(
        blueprint=make_valid_blueprint(),
        validation_report=make_approved_report(),
        structure_map=make_structure_map(),
        registry="not a registry",
    )
    result = engine.execute(ctx)
    assert not result.success
    assert any("ComponentRegistry" in e for e in result.errors)
    print("  [PASS] test_engine_type_check_registry")


# ---------------------------------------------------------------------------#
# 9. Main engine — output
# ---------------------------------------------------------------------------#

def test_engine_produces_file_generation_plan():
    """Engine produces a FileGenerationPlan and stores it in the context."""
    ctx = make_full_context()
    engine = FileGenerationPlanningEngine()
    result = engine.execute(ctx)
    assert result.success
    plan = ctx.get("file_generation_plan")
    assert plan is not None
    assert isinstance(plan, FileGenerationPlan)
    assert plan.project_name == "my_store_bot"
    assert plan.file_count > 0
    print("  [PASS] test_engine_produces_file_generation_plan")


def test_engine_plan_stored_in_metadata():
    """The plan is also stored in the context metadata."""
    ctx = make_full_context()
    engine = FileGenerationPlanningEngine()
    engine.execute(ctx)
    assert "file_generation_plan" in ctx.metadata
    assert isinstance(
        ctx.metadata["file_generation_plan"], FileGenerationPlan,
    )
    print("  [PASS] test_engine_plan_stored_in_metadata")


def test_engine_records_source_artefacts():
    """The plan records the source blueprint, structure map, and registry."""
    ctx = make_full_context()
    engine = FileGenerationPlanningEngine()
    engine.execute(ctx)
    plan = ctx.get("file_generation_plan")
    assert plan.source_blueprint == "my_store_bot"
    assert plan.source_structure_map == "my_store_bot"
    assert plan.source_component_registry == "my_store_bot"
    assert plan.validation_status == STATUS_APPROVED
    print("  [PASS] test_engine_records_source_artefacts")


def test_engine_plan_has_summary():
    """The plan has a non-empty summary."""
    ctx = make_full_context()
    engine = FileGenerationPlanningEngine()
    engine.execute(ctx)
    plan = ctx.get("file_generation_plan")
    assert plan.summary
    assert "file" in plan.summary.lower()
    print("  [PASS] test_engine_plan_has_summary")


def test_engine_plan_has_notes():
    """The plan has notes about its provenance."""
    ctx = make_full_context()
    engine = FileGenerationPlanningEngine()
    engine.execute(ctx)
    plan = ctx.get("file_generation_plan")
    assert len(plan.notes) > 0
    # The notes should mention the source blueprint.
    assert any("blueprint" in n.lower() for n in plan.notes)
    print("  [PASS] test_engine_plan_has_notes")


# ---------------------------------------------------------------------------#
# 10. Plan integrity
# ---------------------------------------------------------------------------#

def test_plan_no_duplicate_paths():
    """The generated plan has no duplicate file paths."""
    ctx = make_full_context()
    engine = FileGenerationPlanningEngine()
    engine.execute(ctx)
    plan = ctx.get("file_generation_plan")
    paths = plan.file_paths()
    assert len(paths) == len(set(paths)), "Duplicate paths in plan."
    print("  [PASS] test_plan_no_duplicate_paths")


def test_plan_all_files_have_purpose():
    """Every file in the plan has a purpose."""
    ctx = make_full_context()
    engine = FileGenerationPlanningEngine()
    engine.execute(ctx)
    plan = ctx.get("file_generation_plan")
    for f in plan.files:
        assert f.purpose, f"File '{f.path}' has no purpose."
    print("  [PASS] test_plan_all_files_have_purpose")


def test_plan_all_files_have_reason():
    """Every file in the plan has a reason for existence."""
    ctx = make_full_context()
    engine = FileGenerationPlanningEngine()
    engine.execute(ctx)
    plan = ctx.get("file_generation_plan")
    for f in plan.files:
        assert f.reason_for_existence, (
            f"File '{f.path}' has no reason for existence."
        )
    print("  [PASS] test_plan_all_files_have_reason")


def test_plan_all_files_have_engine():
    """Every file in the plan has a responsible engine."""
    ctx = make_full_context()
    engine = FileGenerationPlanningEngine()
    engine.execute(ctx)
    plan = ctx.get("file_generation_plan")
    for f in plan.files:
        assert f.responsible_engine, (
            f"File '{f.path}' has no responsible engine."
        )
    print("  [PASS] test_plan_all_files_have_engine")


def test_plan_generation_order_covers_all():
    """The generation order covers every file exactly once."""
    ctx = make_full_context()
    engine = FileGenerationPlanningEngine()
    engine.execute(ctx)
    plan = ctx.get("file_generation_plan")
    all_paths = set(plan.file_paths())
    order_paths = [o.file_path for o in plan.generation_order]
    assert set(order_paths) == all_paths
    assert len(order_paths) == len(set(order_paths)), (
        "Duplicate entries in generation order."
    )
    print("  [PASS] test_plan_generation_order_covers_all")


def test_plan_generation_order_topologically_valid():
    """The generation order is topologically valid."""
    ctx = make_full_context()
    engine = FileGenerationPlanningEngine()
    engine.execute(ctx)
    plan = ctx.get("file_generation_plan")
    position_by_path = {
        o.file_path: o.position for o in plan.generation_order
    }
    for f in plan.files:
        my_pos = position_by_path[f.path]
        for dep in f.depends_on:
            if dep in position_by_path:
                assert position_by_path[dep] < my_pos, (
                    f"File '{f.path}' appears before dependency '{dep}'."
                )
    print("  [PASS] test_plan_generation_order_topologically_valid")


def test_plan_no_circular_dependencies():
    """The plan has no circular dependencies."""
    ctx = make_full_context()
    engine = FileGenerationPlanningEngine()
    result = engine.execute(ctx)
    plan = ctx.get("file_generation_plan")
    circular = [
        f for f in plan.findings if f.code == "circular_dependency"
    ]
    assert len(circular) == 0
    # The engine should succeed (no errors).
    assert result.success
    print("  [PASS] test_plan_no_circular_dependencies")


def test_plan_no_files_created_on_disk():
    """The engine does not create any files on disk."""
    import tempfile
    import shutil
    tmpdir = tempfile.mkdtemp(prefix="file_planner_test_")
    try:
        ctx = GenerationContext(
            request="test",
            config=make_config(),
            work_dir=Path(tmpdir),
        )
        ctx.set("project_blueprint", make_valid_blueprint())
        ctx.set("blueprint_validation_report", make_approved_report())
        ctx.set("project_structure_map", make_structure_map())
        ctx.set("component_registry", make_component_registry())
        engine = FileGenerationPlanningEngine()
        engine.execute(ctx)
        # No files should have been created in the work directory.
        # (Only the plan is produced — no file I/O.)
        created = []
        for root, dirs, filenames in os.walk(tmpdir):
            for fn in filenames:
                created.append(os.path.join(root, fn))
        assert len(created) == 0, (
            f"Engine created files on disk: {created}"
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    print("  [PASS] test_plan_no_files_created_on_disk")


# ---------------------------------------------------------------------------#
# 11. Bootstrap integration
# ---------------------------------------------------------------------------#

def test_bootstrap_registers_file_planner():
    """Bootstrap registers the file planner in the manager."""
    registry, orchestrator, manager = bootstrap()
    entries = manager.all_entries()
    engine_ids = [e.engine_id for e in entries]
    assert "file_planner" in engine_ids
    print("  [PASS] test_bootstrap_registers_file_planner")


def test_bootstrap_file_planner_priority():
    """File planner is registered at priority 95."""
    registry, orchestrator, manager = bootstrap()
    entry = manager.get("file_planner")
    assert entry is not None
    assert entry.priority == 95
    print("  [PASS] test_bootstrap_file_planner_priority")


def test_bootstrap_file_planner_dependencies():
    """File planner depends on structure_generator."""
    registry, orchestrator, manager = bootstrap()
    entry = manager.get("file_planner")
    assert entry is not None
    assert "structure_generator" in entry.dependencies
    print("  [PASS] test_bootstrap_file_planner_dependencies")


def test_bootstrap_file_planner_in_registry():
    """The file planner engine is in the component registry."""
    registry, _, _ = bootstrap()
    engine = registry.get_engine("file_planner")
    assert engine is not None
    assert engine.name == "file_planner"
    print("  [PASS] test_bootstrap_file_planner_in_registry")


def test_bootstrap_config_has_file_planner_section():
    """The default configuration has a file_planner section."""
    config = build_configuration()
    schema = config.schema
    section_names = [s.name for s in schema.sections]
    assert "file_planner" in section_names
    print("  [PASS] test_bootstrap_config_has_file_planner_section")


# ---------------------------------------------------------------------------#
# 12. Serialisation
# ---------------------------------------------------------------------------#

def test_file_plan_entry_to_dict():
    """FilePlanEntry.to_dict returns all fields."""
    entry = FilePlanEntry(
        name="main.py", path="src/main.py",
        extension=EXTENSION_PYTHON,
        file_type=FP_FILE_TYPE_PYTHON_MODULE,
        purpose="Entry point.",
        responsible_engine="code_generator",
        generation_priority=GENERATION_PRIORITY_CORE,
        folder="src",
        source_component="core",
        reason_for_existence="Reason.",
        contains_code=True,
        scalable=False,
    )
    d = entry.to_dict()
    expected_keys = {
        "name", "path", "extension", "file_type", "purpose",
        "responsible_engine", "generation_priority", "folder",
        "depends_on", "depended_by", "source_component",
        "build_order", "reason_for_existence", "contains_code",
        "scalable",
    }
    assert set(d.keys()) == expected_keys
    assert d["depends_on"] == []
    assert d["depended_by"] == []
    assert d["scalable"] is False
    print("  [PASS] test_file_plan_entry_to_dict")


def test_file_relationship_to_dict():
    """FileRelationship.to_dict returns all fields."""
    rel = FileRelationship(
        source="a.py", target="b.py",
        kind="imports", description="a imports b",
    )
    d = rel.to_dict()
    assert d["source"] == "a.py"
    assert d["target"] == "b.py"
    assert d["kind"] == "imports"
    assert d["description"] == "a imports b"
    print("  [PASS] test_file_relationship_to_dict")


def test_file_generation_order_entry_to_dict():
    """FileGenerationOrderEntry.to_dict returns all fields."""
    entry = FileGenerationOrderEntry(
        position=5, file_path="src/a.py",
        file_name="a.py",
        responsible_engine="code_generator",
        source_component="core",
    )
    d = entry.to_dict()
    assert d["position"] == 5
    assert d["file_path"] == "src/a.py"
    assert d["file_name"] == "a.py"
    assert d["responsible_engine"] == "code_generator"
    assert d["source_component"] == "core"
    print("  [PASS] test_file_generation_order_entry_to_dict")


def test_plan_finding_to_dict():
    """PlanFinding.to_dict returns all fields."""
    finding = PlanFinding(
        severity=SEVERITY_WARNING,
        code="test_code",
        message="A warning.",
        affected="src/a.py",
        resolution_hint="Fix it.",
    )
    d = finding.to_dict()
    assert d["severity"] == SEVERITY_WARNING
    assert d["code"] == "test_code"
    assert d["message"] == "A warning."
    assert d["affected"] == "src/a.py"
    assert d["resolution_hint"] == "Fix it."
    print("  [PASS] test_plan_finding_to_dict")


def test_file_generation_plan_to_dict():
    """FileGenerationPlan.to_dict returns all fields."""
    ctx = make_full_context()
    engine = FileGenerationPlanningEngine()
    engine.execute(ctx)
    plan = ctx.get("file_generation_plan")
    d = plan.to_dict()
    assert d["project_name"] == "my_store_bot"
    assert d["file_count"] == plan.file_count
    assert isinstance(d["files"], list)
    assert isinstance(d["relationships"], list)
    assert isinstance(d["generation_order"], list)
    assert isinstance(d["findings"], list)
    assert isinstance(d["notes"], list)
    assert isinstance(d["warnings"], list)
    # Each file dict should have all the keys.
    if d["files"]:
        file_d = d["files"][0]
        assert "name" in file_d
        assert "path" in file_d
        assert "purpose" in file_d
        assert "source_component" in file_d
    print("  [PASS] test_file_generation_plan_to_dict")


# ---------------------------------------------------------------------------#
# 13. End-to-end integration
# ---------------------------------------------------------------------------#

def test_end_to_end_full_pipeline():
    """Run the full pipeline up to the file planner and verify the plan."""
    # Build all four artefacts.
    blueprint = make_valid_blueprint()
    report = make_approved_report()
    structure_map = make_structure_map()
    registry = make_component_registry()

    ctx = make_context(blueprint, report, structure_map, registry)
    engine = FileGenerationPlanningEngine()
    result = engine.execute(ctx)

    assert result.success, (
        f"Engine failed: {result.errors}"
    )
    plan = ctx.get("file_generation_plan")
    assert plan is not None
    assert plan.file_count > 0
    assert len(plan.generation_order) == plan.file_count
    # The plan should record the source artefacts.
    assert plan.source_blueprint == "my_store_bot"
    assert plan.validation_status == STATUS_APPROVED
    print("  [PASS] test_end_to_end_full_pipeline")


def test_engine_metadata_in_result():
    """The engine result metadata contains the plan statistics."""
    ctx = make_full_context()
    engine = FileGenerationPlanningEngine()
    result = engine.execute(ctx)
    assert result.success
    assert "project_name" in result.metadata
    assert "file_count" in result.metadata
    assert "relationship_count" in result.metadata
    assert "generation_order_entries" in result.metadata
    assert result.metadata["project_name"] == "my_store_bot"
    assert result.metadata["file_count"] > 0
    print("  [PASS] test_engine_metadata_in_result")


# ---------------------------------------------------------------------------#
# Test runner
# ---------------------------------------------------------------------------#

def run_all_tests():
    tests = [
        # Data model
        test_file_plan_entry_creation,
        test_file_plan_entry_requires_name,
        test_file_plan_entry_add_dependency,
        test_file_relationship,
        test_file_generation_order_entry,
        test_plan_finding,
        test_file_generation_plan,
        test_file_generation_plan_empty,
        test_file_generation_plan_add_finding,
        test_generation_priority_constants,
        test_extension_constants,
        test_file_type_constants,
        # ComponentAnalyzer
        test_component_analyzer_basic,
        test_component_analyzer_missing_files,
        test_component_analyzer_findings_for_missing_files,
        test_component_analyzer_pure,
        # FileDeterminer
        test_file_determiner_basic,
        test_file_determiner_extension_derivation,
        test_file_determiner_file_type_derivation,
        test_file_determiner_priority_derivation,
        test_file_determiner_source_component,
        test_file_determiner_reason_for_existence,
        test_file_determiner_responsible_engine,
        # RelationshipResolver
        test_relationship_resolver_component_based,
        test_relationship_resolver_package_init,
        test_relationship_resolver_no_self_dependency,
        test_relationship_resolver_dangling_warning,
        # GenerationOrderComputer
        test_generation_order_computer_basic,
        test_generation_order_computer_topological_validity,
        test_generation_order_computer_empty,
        test_generation_order_computer_no_dependencies,
        # ConflictDetector
        test_conflict_detector_no_conflicts,
        test_conflict_detector_duplicates,
        test_conflict_detector_useless_file,
        test_conflict_detector_unlinked_file,
        test_conflict_detector_dangling_dependency,
        test_conflict_detector_circular_dependency,
        # PlanValidator
        test_plan_validator_valid_plan,
        test_plan_validator_empty_plan,
        test_plan_validator_component_without_files,
        test_plan_validator_file_without_purpose,
        test_plan_validator_file_without_engine,
        test_plan_validator_invalid_relationship,
        test_plan_validator_generation_order_covers_all_files,
        test_plan_validator_generation_order_topological,
        # Engine — data source
        test_engine_requires_blueprint,
        test_engine_requires_validation_report,
        test_engine_requires_structure_map,
        test_engine_requires_component_registry,
        test_engine_does_not_read_request,
        test_engine_type_check_blueprint,
        test_engine_type_check_structure_map,
        test_engine_type_check_registry,
        # Engine — output
        test_engine_produces_file_generation_plan,
        test_engine_plan_stored_in_metadata,
        test_engine_records_source_artefacts,
        test_engine_plan_has_summary,
        test_engine_plan_has_notes,
        # Plan integrity
        test_plan_no_duplicate_paths,
        test_plan_all_files_have_purpose,
        test_plan_all_files_have_reason,
        test_plan_all_files_have_engine,
        test_plan_generation_order_covers_all,
        test_plan_generation_order_topologically_valid,
        test_plan_no_circular_dependencies,
        test_plan_no_files_created_on_disk,
        # Bootstrap
        test_bootstrap_registers_file_planner,
        test_bootstrap_file_planner_priority,
        test_bootstrap_file_planner_dependencies,
        test_bootstrap_file_planner_in_registry,
        test_bootstrap_config_has_file_planner_section,
        # Serialisation
        test_file_plan_entry_to_dict,
        test_file_relationship_to_dict,
        test_file_generation_order_entry_to_dict,
        test_plan_finding_to_dict,
        test_file_generation_plan_to_dict,
        # End-to-end
        test_end_to_end_full_pipeline,
        test_engine_metadata_in_result,
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
