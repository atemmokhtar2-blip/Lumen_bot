#!/usr/bin/env python3
"""
Comprehensive test suite for the Project Structure Generation Engine
(Specification 006).

These tests cover every aspect of the specification:

1. Data model integrity (ProjectStructureMap, FolderEntry, FileEntry,
   StructureRelationship, BuildOrderEntry, file-type constants,
   build-order constants).
2. The naming engine (folder_name, file_name, python_module_name,
   package_name, root_package_name, path helpers, slugify).
3. The folder planner (root package, core, database, component folders,
   config, integrations, tests, docs, scalability, relationships,
   large project splitting).
4. The file planner (package inits, core files, database files,
   component files, integration files, test files, docs files,
   project-level files, relationships).
5. The structure validator (duplicate folders, duplicate files,
   conflicting names, empty folders, files without purpose,
   orphan folders, orphan files, component-to-folder, root package).
6. The main engine reads ONLY the project_blueprint and
   blueprint_validation_report (not the raw request or analysis
   report).
7. The main engine produces a ProjectStructureMap artefact.
8. The main engine fails when the blueprint is missing.
9. The main engine fails when the validation report is missing.
10. The structure map has no duplicate paths.
11. The structure map has no orphan folders or files.
12. The build order is correct (folders before files, sorted by
    build_order).
13. Bootstrap integration (engine registered in registry and manager).
"""

import sys
import os

# Ensure the package is importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path

from lumen.engine.core import build_configuration, bootstrap
from lumen.engine.core.context import GenerationContext
from lumen.engine.engines.generators.project_planner import (
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
from lumen.engine.engines.generators.blueprint_validator import (
    BlueprintValidationReport,
    QualityScore,
    STATUS_APPROVED,
    STATUS_REJECTED,
)
from lumen.engine.engines.generators.structure_generator import (
    BuildOrderEntry,
    FILE_TYPE_DOCKERFILE,
    FILE_TYPE_ENV,
    FILE_TYPE_MARKDOWN,
    FILE_TYPE_PYTHON_MODULE,
    FILE_TYPE_PYTHON_PACKAGE,
    FILE_TYPE_REQUIREMENTS,
    FILE_TYPE_TEXT,
    FILE_TYPE_TOML,
    FileEntry,
    FilePlanner,
    FolderEntry,
    FolderPlanner,
    NamingEngine,
    ProjectStructureMap,
    StructureGenerationEngine,
    StructureIssue,
    StructureRelationship,
    StructureValidationReport,
    StructureValidator,
    BUILD_ORDER_CORE,
    BUILD_ORDER_DATABASE,
    BUILD_ORDER_DOCS,
    BUILD_ORDER_FEATURES,
    BUILD_ORDER_INFRASTRUCTURE,
    BUILD_ORDER_TESTS,
)


# ---------------------------------------------------------------------------#
# Test helpers
# ---------------------------------------------------------------------------#

def make_config():
    return build_configuration()


def make_context(blueprint=None, validation_report=None):
    ctx = GenerationContext(
        request="test request (not read by structure engine)",
        config=make_config(),
        work_dir=Path("/tmp/test_structure"),
    )
    if blueprint is not None:
        ctx.set("project_blueprint", blueprint)
    if validation_report is not None:
        ctx.set("blueprint_validation_report", validation_report)
    return ctx


def make_valid_blueprint(
    name="my_store_bot",
    database="sqlite",
    components=None,
):
    """Build a valid, ready-to-use blueprint for testing."""
    if components is None:
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
            InternalComponent(
                name="admin_panel", display_name="Admin Panel",
                kind="feature", priority=PRIORITY_NORMAL,
                description="Admin panel",
            ),
            InternalComponent(
                name="payment_gateway", display_name="Payment Gateway",
                kind="integration", priority=PRIORITY_NORMAL,
                description="Payment integration",
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
            FeatureUnit(
                name="admin_panel", display_name="Admin Panel",
                build_priority=PRIORITY_NORMAL,
                phase="phase_5_code_generation",
                introduces_components=["admin_panel"],
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
                engine_id="structure_generator",
                name="Structure Generator",
                phase="create_structure",
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


# ---------------------------------------------------------------------------#
# 1. Data model tests
# ---------------------------------------------------------------------------#

def test_folder_entry_creation():
    """FolderEntry can be created and serialised."""
    folder = FolderEntry(
        name="handlers",
        path="src/handlers",
        purpose="Bot command handlers.",
        parent="src",
        build_order=BUILD_ORDER_FEATURES,
        reason="Contains handler modules.",
    )
    assert folder.name == "handlers"
    assert folder.path == "src/handlers"
    assert folder.parent == "src"
    d = folder.to_dict()
    assert d["name"] == "handlers"
    assert d["path"] == "src/handlers"
    assert d["build_order"] == BUILD_ORDER_FEATURES
    print("  [PASS] test_folder_entry_creation")


def test_folder_entry_requires_name():
    """FolderEntry raises ValueError without a name."""
    try:
        FolderEntry(name="", path="src")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    try:
        FolderEntry(name="handlers", path="")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    print("  [PASS] test_folder_entry_requires_name")


def test_file_entry_creation():
    """FileEntry can be created and serialised."""
    file = FileEntry(
        name="main.py",
        path="src/main.py",
        file_type=FILE_TYPE_PYTHON_MODULE,
        purpose="Bot entry point.",
        folder="src",
        building_engine="code_generator",
        build_order=BUILD_ORDER_CORE,
        contains_code=True,
    )
    assert file.name == "main.py"
    assert file.file_type == FILE_TYPE_PYTHON_MODULE
    assert file.contains_code is True
    d = file.to_dict()
    assert d["name"] == "main.py"
    assert d["file_type"] == FILE_TYPE_PYTHON_MODULE
    print("  [PASS] test_file_entry_creation")


def test_file_entry_requires_name():
    """FileEntry raises ValueError without a name or path."""
    try:
        FileEntry(name="", path="main.py")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    try:
        FileEntry(name="main.py", path="")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    print("  [PASS] test_file_entry_requires_name")


def test_structure_relationship():
    """StructureRelationship can be created and serialised."""
    rel = StructureRelationship(
        source="src/main.py",
        target="src/bot.py",
        kind="imports",
        description="main.py imports bot.py",
    )
    assert rel.source == "src/main.py"
    assert rel.kind == "imports"
    d = rel.to_dict()
    assert d["source"] == "src/main.py"
    print("  [PASS] test_structure_relationship")


def test_build_order_entry():
    """BuildOrderEntry can be created and serialised."""
    entry = BuildOrderEntry(
        position=0,
        path="src/",
        kind="folder",
        building_engine="directory_builder",
    )
    assert entry.position == 0
    assert entry.kind == "folder"
    d = entry.to_dict()
    assert d["position"] == 0
    print("  [PASS] test_build_order_entry")


def test_project_structure_map():
    """ProjectStructureMap can be created, queried, and serialised."""
    sm = ProjectStructureMap(
        project_name="test_bot",
        root_path="test_bot",
        folders=[FolderEntry(name="test_bot", path="test_bot")],
        files=[FileEntry(name="__init__.py", path="test_bot/__init__.py")],
    )
    assert sm.folder_count == 1
    assert sm.file_count == 1
    assert sm.is_empty is False
    assert sm.folder_paths() == ["test_bot"]
    assert sm.file_paths() == ["test_bot/__init__.py"]
    assert len(sm.all_paths()) == 2

    # Query helpers
    assert sm.get_folder("test_bot") is not None
    assert sm.get_folder("nonexistent") is None
    assert sm.get_file("test_bot/__init__.py") is not None
    assert sm.get_file("nonexistent") is None
    assert len(sm.files_in_folder("test_bot")) == 1
    assert len(sm.files_in_folder("nonexistent")) == 0

    # Serialisation
    d = sm.to_dict()
    assert d["project_name"] == "test_bot"
    assert d["folder_count"] == 1
    assert d["file_count"] == 1
    print("  [PASS] test_project_structure_map")


def test_project_structure_map_empty():
    """An empty ProjectStructureMap is detected."""
    sm = ProjectStructureMap()
    assert sm.is_empty is True
    assert sm.folder_count == 0
    assert sm.file_count == 0
    print("  [PASS] test_project_structure_map_empty")


# ---------------------------------------------------------------------------#
# 2. Naming engine tests
# ---------------------------------------------------------------------------#

def test_naming_folder_name():
    """NamingEngine.folder_name produces professional names."""
    assert NamingEngine.folder_name("handlers") == "handlers"
    assert NamingEngine.folder_name("Database") == "database"
    assert NamingEngine.folder_name("User Management") == "user_management"
    assert NamingEngine.folder_name("API Integration") == "api_integration"
    assert NamingEngine.folder_name("") == "misc"
    print("  [PASS] test_naming_folder_name")


def test_naming_file_name():
    """NamingEngine.file_name produces professional file names."""
    assert NamingEngine.file_name("main") == "main.py"
    assert NamingEngine.file_name("Database Config") == "database_config.py"
    assert NamingEngine.file_name("README", "md") == "README.md"
    assert NamingEngine.file_name("requirements", "txt") == "requirements.txt"
    print("  [PASS] test_naming_file_name")


def test_naming_python_module_name():
    """NamingEngine.python_module_name avoids reserved keywords."""
    assert NamingEngine.python_module_name("class") == "class_module"
    assert NamingEngine.python_module_name("import") == "import_module"
    assert NamingEngine.python_module_name("store") == "store"
    assert NamingEngine.python_module_name("User Model") == "user_model"
    print("  [PASS] test_naming_python_module_name")


def test_naming_package_name():
    """NamingEngine.package_name avoids reserved keywords."""
    assert NamingEngine.package_name("test") == "tests"
    assert NamingEngine.package_name("config") == "config"
    assert NamingEngine.package_name("class") == "class_pkg"
    print("  [PASS] test_naming_package_name")


def test_naming_root_package_name():
    """NamingEngine.root_package_name converts project names to slugs."""
    assert NamingEngine.root_package_name("My Store Bot") == "my_store_bot"
    assert NamingEngine.root_package_name("AI Assistant") == "ai_assistant"
    assert NamingEngine.root_package_name("") == "telegram_bot"
    print("  [PASS] test_naming_root_package_name")


def test_naming_join_path():
    """NamingEngine.join_path joins parts correctly."""
    assert NamingEngine.join_path("src", "handlers") == "src/handlers"
    assert NamingEngine.join_path("src/", "/handlers") == "src/handlers"
    assert NamingEngine.join_path("", "src", "", "main.py") == "src/main.py"
    print("  [PASS] test_naming_join_path")


def test_naming_parent_path():
    """NamingEngine.parent_path returns the parent path."""
    assert NamingEngine.parent_path("src/handlers/commands") == "src/handlers"
    assert NamingEngine.parent_path("main.py") == ""
    assert NamingEngine.parent_path("src") == ""
    print("  [PASS] test_naming_parent_path")


def test_naming_base_name():
    """NamingEngine.base_name returns the last path component."""
    assert NamingEngine.base_name("src/handlers/commands") == "commands"
    assert NamingEngine.base_name("src/main.py") == "main.py"
    assert NamingEngine.base_name("main.py") == "main.py"
    print("  [PASS] test_naming_base_name")


# ---------------------------------------------------------------------------#
# 3. Folder planner tests
# ---------------------------------------------------------------------------#

def test_folder_planner_basic():
    """FolderPlanner produces a folder map with root, core, config, tests, docs."""
    blueprint = make_valid_blueprint()
    planner = FolderPlanner()
    folders = planner.plan(blueprint, "my_store_bot")

    paths = [f.path for f in folders]
    assert "my_store_bot" in paths
    assert "my_store_bot/core" in paths
    assert "my_store_bot/config" in paths
    assert "my_store_bot/tests" in paths
    assert "my_store_bot/docs" in paths
    print("  [PASS] test_folder_planner_basic")


def test_folder_planner_database_folder():
    """FolderPlanner creates database and migrations folders when database is present."""
    blueprint = make_valid_blueprint(database="sqlite")
    planner = FolderPlanner()
    folders = planner.plan(blueprint, "my_store_bot")

    paths = [f.path for f in folders]
    assert "my_store_bot/database" in paths
    assert "my_store_bot/database/migrations" in paths
    print("  [PASS] test_folder_planner_database_folder")


def test_folder_planner_no_database_folder():
    """FolderPlanner does not create database folders when no database."""
    blueprint = make_valid_blueprint(database="")
    planner = FolderPlanner()
    folders = planner.plan(blueprint, "my_store_bot")

    paths = [f.path for f in folders]
    assert "my_store_bot/database" not in paths
    print("  [PASS] test_folder_planner_no_database_folder")


def test_folder_planner_component_folders():
    """FolderPlanner creates folders for feature components."""
    blueprint = make_valid_blueprint()
    planner = FolderPlanner()
    folders = planner.plan(blueprint, "my_store_bot")

    paths = [f.path for f in folders]
    assert "my_store_bot/store" in paths
    assert "my_store_bot/admin_panel" in paths
    # Infrastructure and integration components don't get their own folders
    assert "my_store_bot/core" in paths  # core folder, but from the core folder
    print("  [PASS] test_folder_planner_component_folders")


def test_folder_planner_integration_folder():
    """FolderPlanner creates an integrations folder when integrations exist."""
    blueprint = make_valid_blueprint()
    planner = FolderPlanner()
    folders = planner.plan(blueprint, "my_store_bot")

    paths = [f.path for f in folders]
    assert "my_store_bot/integrations" in paths
    print("  [PASS] test_folder_planner_integration_folder")


def test_folder_planner_no_duplicate_folders():
    """FolderPlanner does not produce duplicate folder paths."""
    blueprint = make_valid_blueprint()
    planner = FolderPlanner()
    folders = planner.plan(blueprint, "my_store_bot")

    paths = [f.path for f in folders]
    assert len(paths) == len(set(paths)), "Duplicate folder paths found"
    print("  [PASS] test_folder_planner_no_duplicate_folders")


def test_folder_planner_relationships():
    """FolderPlanner records parent-child relationships."""
    blueprint = make_valid_blueprint()
    planner = FolderPlanner()
    folders = planner.plan(blueprint, "my_store_bot")

    # The root folder should have subfolders.
    root = next(f for f in folders if f.path == "my_store_bot")
    assert len(root.subfolders) > 0
    # At least one folder should have a child_of relationship.
    has_relationship = any(
        f.relationships for f in folders
    )
    assert has_relationship, "No folder relationships recorded"
    print("  [PASS] test_folder_planner_relationships")


def test_folder_planner_large_project():
    """FolderPlanner splits components into components/ for large projects."""
    # Create a blueprint with many components (>= 8)
    components = [
        InternalComponent(
            name=f"feature_{i}", display_name=f"Feature {i}",
            kind="feature", priority=PRIORITY_NORMAL,
            description=f"Feature {i} component.",
        )
        for i in range(10)
    ]
    blueprint = make_valid_blueprint(components=components)
    planner = FolderPlanner()
    folders = planner.plan(blueprint, "my_large_bot")

    paths = [f.path for f in folders]
    # Large projects should have a components/ folder.
    assert "my_large_bot/components" in paths or any(
        "components" in p for p in paths
    )
    print("  [PASS] test_folder_planner_large_project")


# ---------------------------------------------------------------------------#
# 4. File planner tests
# ---------------------------------------------------------------------------#

def test_file_planner_basic():
    """FilePlanner produces files with correct types."""
    blueprint = make_valid_blueprint()
    folders = FolderPlanner().plan(blueprint, "my_store_bot")
    component_to_folder = {}
    for f in folders:
        pass
    planner = FilePlanner()
    files = planner.plan(
        blueprint, folders, "my_store_bot", {},
    )

    paths = [f.path for f in files]
    assert "my_store_bot/__init__.py" in paths
    assert "my_store_bot/core/__init__.py" in paths
    assert "my_store_bot/core/main.py" in paths
    assert "my_store_bot/core/bot.py" in paths
    print("  [PASS] test_file_planner_basic")


def test_file_planner_database_files():
    """FilePlanner creates database files when database is present."""
    blueprint = make_valid_blueprint(database="sqlite")
    folders = FolderPlanner().plan(blueprint, "my_store_bot")
    planner = FilePlanner()
    files = planner.plan(
        blueprint, folders, "my_store_bot", {},
    )

    paths = [f.path for f in files]
    assert "my_store_bot/database/__init__.py" in paths
    assert "my_store_bot/database/connection.py" in paths
    assert "my_store_bot/database/models.py" in paths
    assert "my_store_bot/database/schema.py" in paths
    assert "my_store_bot/database/migrations/__init__.py" in paths
    assert "my_store_bot/database/migrations/initial_migration.py" in paths
    print("  [PASS] test_file_planner_database_files")


def test_file_planner_no_database_files_without_database():
    """FilePlanner does not create database files when no database."""
    blueprint = make_valid_blueprint(database="")
    folders = FolderPlanner().plan(blueprint, "my_store_bot")
    planner = FilePlanner()
    files = planner.plan(
        blueprint, folders, "my_store_bot", {},
    )

    paths = [f.path for f in files]
    assert not any("database" in p for p in paths)
    print("  [PASS] test_file_planner_no_database_files_without_database")


def test_file_planner_project_level_files():
    """FilePlanner creates project-level files (README, requirements, etc.)."""
    blueprint = make_valid_blueprint()
    folders = FolderPlanner().plan(blueprint, "my_store_bot")
    planner = FilePlanner()
    files = planner.plan(
        blueprint, folders, "my_store_bot", {},
    )

    paths = [f.path for f in files]
    assert "README.md" in paths
    assert "requirements.txt" in paths
    assert "pyproject.toml" in paths
    assert "Dockerfile" in paths
    assert ".gitignore" in paths
    assert ".dockerignore" in paths
    print("  [PASS] test_file_planner_project_level_files")


def test_file_planner_no_duplicate_files():
    """FilePlanner does not produce duplicate file paths."""
    blueprint = make_valid_blueprint()
    folders = FolderPlanner().plan(blueprint, "my_store_bot")
    planner = FilePlanner()
    files = planner.plan(
        blueprint, folders, "my_store_bot", {},
    )

    paths = [f.path for f in files]
    assert len(paths) == len(set(paths)), "Duplicate file paths found"
    print("  [PASS] test_file_planner_no_duplicate_files")


def test_file_planner_all_files_have_purpose():
    """Every file produced by FilePlanner has a purpose."""
    blueprint = make_valid_blueprint()
    folders = FolderPlanner().plan(blueprint, "my_store_bot")
    planner = FilePlanner()
    files = planner.plan(
        blueprint, folders, "my_store_bot", {},
    )

    for file in files:
        assert file.purpose, f"File {file.path} has no purpose"
    print("  [PASS] test_file_planner_all_files_have_purpose")


def test_file_planner_file_types():
    """FilePlanner assigns correct file types."""
    blueprint = make_valid_blueprint()
    folders = FolderPlanner().plan(blueprint, "my_store_bot")
    planner = FilePlanner()
    files = planner.plan(
        blueprint, folders, "my_store_bot", {},
    )

    for file in files:
        if file.name.endswith(".py"):
            assert file.file_type in (
                FILE_TYPE_PYTHON_MODULE, FILE_TYPE_PYTHON_PACKAGE,
            ), f"File {file.path} has wrong type: {file.file_type}"
        elif file.name == "README.md":
            assert file.file_type == FILE_TYPE_MARKDOWN
        elif file.name == "requirements.txt":
            assert file.file_type == FILE_TYPE_REQUIREMENTS
        elif file.name == "Dockerfile":
            assert file.file_type == FILE_TYPE_DOCKERFILE
        elif file.name == "pyproject.toml":
            assert file.file_type == FILE_TYPE_TOML
    print("  [PASS] test_file_planner_file_types")


def test_file_planner_relationships():
    """FilePlanner records stored_in relationships."""
    blueprint = make_valid_blueprint()
    folders = FolderPlanner().plan(blueprint, "my_store_bot")
    planner = FilePlanner()
    files = planner.plan(
        blueprint, folders, "my_store_bot", {},
    )

    # At least some files should have relationships.
    has_rel = any(f.relationships for f in files)
    assert has_rel, "No file relationships recorded"
    print("  [PASS] test_file_planner_relationships")


# ---------------------------------------------------------------------------#
# 5. Structure validator tests
# ---------------------------------------------------------------------------#

def test_validator_valid_structure():
    """Validator returns valid for a correct structure map."""
    blueprint = make_valid_blueprint()
    engine = StructureGenerationEngine()
    ctx = make_context(blueprint, make_approved_report())
    result = engine.execute(ctx)
    assert result.success

    sm = ctx.get("project_structure_map")
    validator = StructureValidator()
    report = validator.validate(sm)
    assert report.valid, f"Validation failed: {[i.message for i in report.issues if i.severity == 'error']}"
    print("  [PASS] test_validator_valid_structure")


def test_validator_duplicate_folders():
    """Validator detects duplicate folder paths."""
    sm = ProjectStructureMap(
        project_name="test",
        root_path="test",
        folders=[
            FolderEntry(name="test", path="test"),
            FolderEntry(name="test", path="test"),
        ],
        files=[],
    )
    validator = StructureValidator()
    report = validator.validate(sm)
    assert not report.valid
    assert any(i.code == "duplicate_folder" for i in report.issues)
    print("  [PASS] test_validator_duplicate_folders")


def test_validator_duplicate_files():
    """Validator detects duplicate file paths."""
    sm = ProjectStructureMap(
        project_name="test",
        root_path="test",
        folders=[FolderEntry(name="test", path="test")],
        files=[
            FileEntry(name="main.py", path="test/main.py",
                       purpose="test"),
            FileEntry(name="main.py", path="test/main.py",
                       purpose="test"),
        ],
    )
    validator = StructureValidator()
    report = validator.validate(sm)
    assert not report.valid
    assert any(i.code == "duplicate_file" for i in report.issues)
    print("  [PASS] test_validator_duplicate_files")


def test_validator_conflicting_names():
    """Validator detects when a folder and file share the same path."""
    sm = ProjectStructureMap(
        project_name="test",
        root_path="test",
        folders=[FolderEntry(name="main", path="test/main")],
        files=[FileEntry(name="main", path="test/main",
                          purpose="conflict")],
    )
    validator = StructureValidator()
    report = validator.validate(sm)
    assert not report.valid
    assert any(i.code == "conflicting_name" for i in report.issues)
    print("  [PASS] test_validator_conflicting_names")


def test_validator_files_without_purpose():
    """Validator detects files without a purpose."""
    sm = ProjectStructureMap(
        project_name="test",
        root_path="test",
        folders=[FolderEntry(name="test", path="test")],
        files=[FileEntry(name="main.py", path="test/main.py",
                          purpose="")],
    )
    validator = StructureValidator()
    report = validator.validate(sm)
    assert not report.valid
    assert any(i.code == "file_without_purpose" for i in report.issues)
    print("  [PASS] test_validator_files_without_purpose")


def test_validator_orphan_folder():
    """Validator detects folders with nonexistent parents."""
    sm = ProjectStructureMap(
        project_name="test",
        root_path="test",
        folders=[FolderEntry(
            name="sub", path="test/sub",
            parent="nonexistent",
        )],
        files=[],
    )
    validator = StructureValidator()
    report = validator.validate(sm)
    assert not report.valid
    assert any(i.code == "orphan_folder" for i in report.issues)
    print("  [PASS] test_validator_orphan_folder")


def test_validator_orphan_file():
    """Validator detects files in nonexistent folders."""
    sm = ProjectStructureMap(
        project_name="test",
        root_path="test",
        folders=[FolderEntry(name="test", path="test")],
        files=[FileEntry(
            name="main.py", path="nonexistent/main.py",
            folder="nonexistent", purpose="test",
        )],
    )
    validator = StructureValidator()
    report = validator.validate(sm)
    assert not report.valid
    assert any(i.code == "orphan_file" for i in report.issues)
    print("  [PASS] test_validator_orphan_file")


def test_validator_missing_root_folder():
    """Validator detects missing root folder."""
    sm = ProjectStructureMap(
        project_name="test",
        root_path="test",
        folders=[FolderEntry(name="other", path="other")],
        files=[],
    )
    validator = StructureValidator()
    report = validator.validate(sm)
    assert not report.valid
    assert any(i.code == "missing_root_folder" for i in report.issues)
    print("  [PASS] test_validator_missing_root_folder")


def test_validator_missing_project_name():
    """Validator detects missing project name."""
    sm = ProjectStructureMap(
        project_name="",
        root_path="",
        folders=[],
        files=[],
    )
    validator = StructureValidator()
    report = validator.validate(sm)
    assert not report.valid
    assert any(i.code == "missing_project_name" for i in report.issues)
    print("  [PASS] test_validator_missing_project_name")


def test_validator_report_serialisation():
    """StructureValidationReport serialises correctly."""
    report = StructureValidationReport()
    report.add_error("test_code", "test error", "test/path")
    report.add_warning("warn_code", "test warning")
    d = report.to_dict()
    assert d["valid"] is False
    assert d["error_count"] == 1
    assert d["warning_count"] == 1
    assert len(d["issues"]) == 2
    print("  [PASS] test_validator_report_serialisation")


# ---------------------------------------------------------------------------#
# 6. Engine — data source restrictions
# ---------------------------------------------------------------------------#

def test_engine_requires_blueprint():
    """Engine fails when the project_blueprint artefact is missing."""
    engine = StructureGenerationEngine()
    ctx = make_context()  # no blueprint
    result = engine.execute(ctx)
    assert not result.success
    assert any("project_blueprint" in e for e in result.errors)
    print("  [PASS] test_engine_requires_blueprint")


def test_engine_requires_validation_report():
    """Engine fails when the blueprint_validation_report artefact is missing."""
    engine = StructureGenerationEngine()
    ctx = make_context(blueprint=make_valid_blueprint())
    # No validation report set
    result = engine.execute(ctx)
    assert not result.success
    assert any("blueprint_validation_report" in e for e in result.errors)
    print("  [PASS] test_engine_requires_validation_report")


def test_engine_does_not_read_request():
    """The engine's output does not depend on the request field."""
    blueprint = make_valid_blueprint()
    report = make_approved_report()

    ctx1 = make_context(blueprint, report)
    ctx1.request = "create a store bot"

    ctx2 = make_context(blueprint, report)
    ctx2.request = "completely different request text"

    engine = StructureGenerationEngine()
    result1 = engine.execute(ctx1)
    result2 = engine.execute(ctx2)

    assert result1.success
    assert result2.success

    sm1 = ctx1.get("project_structure_map")
    sm2 = ctx2.get("project_structure_map")
    # The structure maps should be identical (same blueprint, same report).
    assert sm1.folder_count == sm2.folder_count
    assert sm1.file_count == sm2.file_count
    assert sm1.folder_paths() == sm2.folder_paths()
    assert sm1.file_paths() == sm2.file_paths()
    print("  [PASS] test_engine_does_not_read_request")


# ---------------------------------------------------------------------------#
# 7. Engine — output
# ---------------------------------------------------------------------------#

def test_engine_produces_structure_map():
    """Engine produces a ProjectStructureMap and stores it in the context."""
    blueprint = make_valid_blueprint()
    report = make_approved_report()
    ctx = make_context(blueprint, report)

    engine = StructureGenerationEngine()
    result = engine.execute(ctx)

    assert result.success
    sm = ctx.get("project_structure_map")
    assert sm is not None
    assert isinstance(sm, ProjectStructureMap)
    assert sm.project_name == "my_store_bot"
    assert sm.root_path == "my_store_bot"
    assert sm.folder_count > 0
    assert sm.file_count > 0
    print("  [PASS] test_engine_produces_structure_map")


def test_engine_validation_status_recorded():
    """Engine records the validation status in the structure map."""
    blueprint = make_valid_blueprint()
    report = make_approved_report()
    ctx = make_context(blueprint, report)

    engine = StructureGenerationEngine()
    engine.execute(ctx)

    sm = ctx.get("project_structure_map")
    assert sm.validation_status == STATUS_APPROVED
    assert sm.source_blueprint == "my_store_bot"
    print("  [PASS] test_engine_validation_status_recorded")


# ---------------------------------------------------------------------------#
# 8. Structure map integrity
# ---------------------------------------------------------------------------#

def test_no_duplicate_paths():
    """The structure map has no duplicate folder or file paths."""
    blueprint = make_valid_blueprint()
    report = make_approved_report()
    ctx = make_context(blueprint, report)

    engine = StructureGenerationEngine()
    engine.execute(ctx)

    sm = ctx.get("project_structure_map")
    folder_paths = sm.folder_paths()
    file_paths = sm.file_paths()

    assert len(folder_paths) == len(set(folder_paths))
    assert len(file_paths) == len(set(file_paths))
    # No folder and file share the same path.
    assert not (set(folder_paths) & set(file_paths))
    print("  [PASS] test_no_duplicate_paths")


def test_no_orphan_folders():
    """Every folder's parent exists in the folder map."""
    blueprint = make_valid_blueprint()
    report = make_approved_report()
    ctx = make_context(blueprint, report)

    engine = StructureGenerationEngine()
    engine.execute(ctx)

    sm = ctx.get("project_structure_map")
    folder_paths = set(sm.folder_paths())
    for folder in sm.folders:
        if folder.parent:
            assert folder.parent in folder_paths, (
                f"Folder {folder.path} has orphan parent {folder.parent}"
            )
    print("  [PASS] test_no_orphan_folders")


def test_no_orphan_files():
    """Every file's folder exists in the folder map."""
    blueprint = make_valid_blueprint()
    report = make_approved_report()
    ctx = make_context(blueprint, report)

    engine = StructureGenerationEngine()
    engine.execute(ctx)

    sm = ctx.get("project_structure_map")
    folder_paths = set(sm.folder_paths())
    for file in sm.files:
        if file.folder:
            assert file.folder in folder_paths, (
                f"File {file.path} has orphan folder {file.folder}"
            )
    print("  [PASS] test_no_orphan_files")


def test_no_files_without_purpose():
    """Every file in the structure map has a purpose."""
    blueprint = make_valid_blueprint()
    report = make_approved_report()
    ctx = make_context(blueprint, report)

    engine = StructureGenerationEngine()
    engine.execute(ctx)

    sm = ctx.get("project_structure_map")
    for file in sm.files:
        assert file.purpose, f"File {file.path} has no purpose"
    print("  [PASS] test_no_files_without_purpose")


def test_all_files_have_file_type():
    """Every file has a non-empty file type."""
    blueprint = make_valid_blueprint()
    report = make_approved_report()
    ctx = make_context(blueprint, report)

    engine = StructureGenerationEngine()
    engine.execute(ctx)

    sm = ctx.get("project_structure_map")
    for file in sm.files:
        assert file.file_type, f"File {file.path} has no file type"
    print("  [PASS] test_all_files_have_file_type")


def test_all_files_have_building_engine():
    """Every file has a building engine assigned."""
    blueprint = make_valid_blueprint()
    report = make_approved_report()
    ctx = make_context(blueprint, report)

    engine = StructureGenerationEngine()
    engine.execute(ctx)

    sm = ctx.get("project_structure_map")
    for file in sm.files:
        assert file.building_engine, f"File {file.path} has no building engine"
    print("  [PASS] test_all_files_have_building_engine")


# ---------------------------------------------------------------------------#
# 9. Build order tests
# ---------------------------------------------------------------------------#

def test_build_order_folders_before_files():
    """Build order lists all folders before any file."""
    blueprint = make_valid_blueprint()
    report = make_approved_report()
    ctx = make_context(blueprint, report)

    engine = StructureGenerationEngine()
    engine.execute(ctx)

    sm = ctx.get("project_structure_map")
    folder_positions = [
        b.position for b in sm.build_order if b.kind == "folder"
    ]
    file_positions = [
        b.position for b in sm.build_order if b.kind == "file"
    ]

    assert max(folder_positions) < min(file_positions), (
        "Folders should be built before files"
    )
    print("  [PASS] test_build_order_folders_before_files")


def test_build_order_positions_sequential():
    """Build order positions are sequential (0, 1, 2, ...)."""
    blueprint = make_valid_blueprint()
    report = make_approved_report()
    ctx = make_context(blueprint, report)

    engine = StructureGenerationEngine()
    engine.execute(ctx)

    sm = ctx.get("project_structure_map")
    positions = [b.position for b in sm.build_order]
    assert positions == list(range(len(positions))), (
        "Positions should be sequential"
    )
    print("  [PASS] test_build_order_positions_sequential")


def test_build_order_all_paths_covered():
    """Build order covers every folder and file path."""
    blueprint = make_valid_blueprint()
    report = make_approved_report()
    ctx = make_context(blueprint, report)

    engine = StructureGenerationEngine()
    engine.execute(ctx)

    sm = ctx.get("project_structure_map")
    build_order_paths = {b.path for b in sm.build_order}
    all_paths = set(sm.all_paths())
    assert build_order_paths == all_paths, (
        "Build order should cover all paths"
    )
    print("  [PASS] test_build_order_all_paths_covered")


# ---------------------------------------------------------------------------#
# 10. Bootstrap integration
# ---------------------------------------------------------------------------#

def test_bootstrap_registers_structure_generator():
    """Bootstrap registers the structure generator in the manager."""
    registry, orchestrator, manager = bootstrap()
    entries = manager.all_entries()
    engine_ids = [e.engine_id for e in entries]
    assert "structure_generator" in engine_ids
    print("  [PASS] test_bootstrap_registers_structure_generator")


def test_bootstrap_structure_generator_priority():
    """Structure generator is registered at priority 90."""
    registry, orchestrator, manager = bootstrap()
    entry = manager.get("structure_generator")
    assert entry is not None
    assert entry.priority == 90
    print("  [PASS] test_bootstrap_structure_generator_priority")


def test_bootstrap_structure_generator_dependencies():
    """Structure generator depends on project_structure_planning."""
    registry, orchestrator, manager = bootstrap()
    entry = manager.get("structure_generator")
    assert entry is not None
    assert "project_structure_planning" in entry.dependencies
    print("  [PASS] test_bootstrap_structure_generator_dependencies")


def test_bootstrap_config_has_structure_generator_section():
    """The default configuration has a structure_generator section."""
    config = build_configuration()
    schema = config.schema
    section_names = [s.name for s in schema.sections]
    assert "structure_generator" in section_names
    print("  [PASS] test_bootstrap_config_has_structure_generator_section")


# ---------------------------------------------------------------------------#
# 11. Serialisation tests
# ---------------------------------------------------------------------------#

def test_structure_map_to_dict():
    """ProjectStructureMap.to_dict() produces a valid dict."""
    blueprint = make_valid_blueprint()
    report = make_approved_report()
    ctx = make_context(blueprint, report)

    engine = StructureGenerationEngine()
    engine.execute(ctx)

    sm = ctx.get("project_structure_map")
    d = sm.to_dict()
    assert "project_name" in d
    assert "folders" in d
    assert "files" in d
    assert "build_order" in d
    assert isinstance(d["folders"], list)
    assert isinstance(d["files"], list)
    assert isinstance(d["build_order"], list)
    print("  [PASS] test_structure_map_to_dict")


# ---------------------------------------------------------------------------#
# Main
# ---------------------------------------------------------------------------#

def run_all_tests():
    """Run all tests and report results."""
    tests = [
        # Data model
        test_folder_entry_creation,
        test_folder_entry_requires_name,
        test_file_entry_creation,
        test_file_entry_requires_name,
        test_structure_relationship,
        test_build_order_entry,
        test_project_structure_map,
        test_project_structure_map_empty,
        # Naming engine
        test_naming_folder_name,
        test_naming_file_name,
        test_naming_python_module_name,
        test_naming_package_name,
        test_naming_root_package_name,
        test_naming_join_path,
        test_naming_parent_path,
        test_naming_base_name,
        # Folder planner
        test_folder_planner_basic,
        test_folder_planner_database_folder,
        test_folder_planner_no_database_folder,
        test_folder_planner_component_folders,
        test_folder_planner_integration_folder,
        test_folder_planner_no_duplicate_folders,
        test_folder_planner_relationships,
        test_folder_planner_large_project,
        # File planner
        test_file_planner_basic,
        test_file_planner_database_files,
        test_file_planner_no_database_files_without_database,
        test_file_planner_project_level_files,
        test_file_planner_no_duplicate_files,
        test_file_planner_all_files_have_purpose,
        test_file_planner_file_types,
        test_file_planner_relationships,
        # Validator
        test_validator_valid_structure,
        test_validator_duplicate_folders,
        test_validator_duplicate_files,
        test_validator_conflicting_names,
        test_validator_files_without_purpose,
        test_validator_orphan_folder,
        test_validator_orphan_file,
        test_validator_missing_root_folder,
        test_validator_missing_project_name,
        test_validator_report_serialisation,
        # Engine — data source
        test_engine_requires_blueprint,
        test_engine_requires_validation_report,
        test_engine_does_not_read_request,
        # Engine — output
        test_engine_produces_structure_map,
        test_engine_validation_status_recorded,
        # Structure map integrity
        test_no_duplicate_paths,
        test_no_orphan_folders,
        test_no_orphan_files,
        test_no_files_without_purpose,
        test_all_files_have_file_type,
        test_all_files_have_building_engine,
        # Build order
        test_build_order_folders_before_files,
        test_build_order_positions_sequential,
        test_build_order_all_paths_covered,
        # Bootstrap
        test_bootstrap_registers_structure_generator,
        test_bootstrap_structure_generator_priority,
        test_bootstrap_structure_generator_dependencies,
        test_bootstrap_config_has_structure_generator_section,
        # Serialisation
        test_structure_map_to_dict,
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
