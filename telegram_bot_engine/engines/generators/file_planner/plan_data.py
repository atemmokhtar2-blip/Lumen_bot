"""
File Generation Plan data model (Specification 008).

This module defines the :class:`FileGenerationPlan` — the complete,
authoritative plan for every file that the generated Telegram bot
project will contain **before** any file is created on disk.  It is the
single artefact produced by the
:class:`~telegram_bot_engine.engines.generators.file_planner.FileGenerationPlanningEngine`.

The plan is built from **four** read-only artefacts:

1. the ``project_blueprint`` (produced by the Project Planning Engine),
2. the ``blueprint_validation_report`` (produced by the Blueprint
   Validator Engine),
3. the ``project_structure_map`` (produced by the Structure Generation
   Engine),
4. the ``component_registry`` (produced by the Component Detection
   Engine).

The planning engine is **forbidden** from reading the user's request.

Design principles
-----------------
* **Every file is planned before it is created.**  No file is invented
  during code generation — they are all planned here.
* **Single Responsibility Principle per file.**  Each planned file
  carries a single, clear responsibility.
* **No files without a reason.**  Every file entry records *why* it
  exists (``reason_for_existence``).
* **No files without a component.**  Every file is linked to at least
  one detected component.
* **No files without a location.**  Every file belongs to a folder in
  the structure map.
* **Extensible.**  New files can be added to the plan without altering
  the existing structure or affecting existing files.
* **Generation order.**  The plan records the precise order in which
  files should be created, respecting dependencies, build order, and
  parallel-execution safety.

The plan is a plain data container — no logic lives here.  The planning
engine and its helpers populate it; downstream consumers (the code
generators, the manager, tests) read it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------#
# Generation-priority levels
# ---------------------------------------------------------------------------#
#
# The generation priority determines the broad phase in which a file is
# created.  These mirror the build-order constants from the structure
# map but are expressed at the file level.  Lower values are created
# first.

GENERATION_PRIORITY_INFRASTRUCTURE = 10
GENERATION_PRIORITY_CORE = 20
GENERATION_PRIORITY_DATABASE = 30
GENERATION_PRIORITY_FEATURES = 40
GENERATION_PRIORITY_WIRING = 50
GENERATION_PRIORITY_ENTRY = 60
GENERATION_PRIORITY_DOCS = 70
GENERATION_PRIORITY_TESTS = 80

ALL_GENERATION_PRIORITIES = (
    GENERATION_PRIORITY_INFRASTRUCTURE,
    GENERATION_PRIORITY_CORE,
    GENERATION_PRIORITY_DATABASE,
    GENERATION_PRIORITY_FEATURES,
    GENERATION_PRIORITY_WIRING,
    GENERATION_PRIORITY_ENTRY,
    GENERATION_PRIORITY_DOCS,
    GENERATION_PRIORITY_TESTS,
)


# ---------------------------------------------------------------------------#
# File-extension constants
# ---------------------------------------------------------------------------#
#
# The set of file extensions the planning engine recognises.  These
# determine the ``extension`` and ``file_type`` fields on each
# :class:`FilePlanEntry`.

EXTENSION_PYTHON = ".py"
EXTENSION_YAML = ".yaml"
EXTENSION_YML = ".yml"
EXTENSION_TOML = ".toml"
EXTENSION_JSON = ".json"
EXTENSION_ENV = ".env"
EXTENSION_SQL = ".sql"
EXTENSION_MARKDOWN = ".md"
EXTENSION_TEXT = ".txt"
EXTENSION_DOCKERFILE = ""
EXTENSION_SCRIPT = ".sh"

ALL_EXTENSIONS = (
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
)


# ---------------------------------------------------------------------------#
# File-type constants
# ---------------------------------------------------------------------------#
#
# The file type is a semantic classification of the file's role.  It is
# derived from the structure map's ``FILE_TYPE_*`` constants but is
# owned by the file planner so the plan is self-contained.

FILE_TYPE_PYTHON_MODULE = "python_module"
FILE_TYPE_PYTHON_PACKAGE = "python_package"
FILE_TYPE_CONFIG = "config"
FILE_TYPE_TEXT = "text"
FILE_TYPE_MARKDOWN = "markdown"
FILE_TYPE_YAML = "yaml"
FILE_TYPE_TOML = "toml"
FILE_TYPE_ENV = "env"
FILE_TYPE_JSON = "json"
FILE_TYPE_SQL = "sql"
FILE_TYPE_DOCKERFILE = "dockerfile"
FILE_TYPE_SCRIPT = "script"
FILE_TYPE_REQUIREMENTS = "requirements"

ALL_FILE_TYPES = (
    FILE_TYPE_PYTHON_MODULE,
    FILE_TYPE_PYTHON_PACKAGE,
    FILE_TYPE_CONFIG,
    FILE_TYPE_TEXT,
    FILE_TYPE_MARKDOWN,
    FILE_TYPE_YAML,
    FILE_TYPE_TOML,
    FILE_TYPE_ENV,
    FILE_TYPE_JSON,
    FILE_TYPE_SQL,
    FILE_TYPE_DOCKERFILE,
    FILE_TYPE_SCRIPT,
    FILE_TYPE_REQUIREMENTS,
)


# ---------------------------------------------------------------------------#
# A single planned file
# ---------------------------------------------------------------------------#

@dataclass
class FilePlanEntry:
    """A single file planned for generation.

    This is the unit of the File Generation Plan.  Each entry describes
    a file that the code generators must produce later — it is **not**
    the file itself, nor does it contain any code.

    Attributes:
        name: The file name (e.g. ``"main.py"``, ``"config.yaml"``).
        path: The full relative path from the project root
            (e.g. ``"my_bot/main.py"``).
        extension: The file extension (e.g. ``".py"``, ``".yaml"``).
            ``""`` for files without an extension (e.g. ``Dockerfile``).
        file_type: The file type (one of the ``FILE_TYPE_*`` constants).
        purpose: What this file is for — a single, clear
            responsibility.
        responsible_engine: The engine that will build this file
            later (e.g. ``"code_generator"``, ``"database_engine"``).
        generation_priority: The broad generation phase (one of the
            ``GENERATION_PRIORITY_*`` constants).  Lower values are
            generated first.
        folder: The folder path this file belongs to (must exist in
            the structure map).
        depends_on: The paths of other files this file depends on.
        depended_by: The paths of files that depend on this file.
        source_component: The detected component this file belongs to.
        build_order: The precise position in the generation sequence
            (lower first).  Assigned by the generation-order computer.
        reason_for_existence: A human-readable explanation of *why*
            this file exists.
        contains_code: ``True`` when this file will eventually contain
            executable code.
        scalable: ``True`` when additional files can be added to the
            same folder without restructuring.
    """

    name: str
    path: str
    extension: str = ""
    file_type: str = FILE_TYPE_TEXT
    purpose: str = ""
    responsible_engine: str = ""
    generation_priority: int = GENERATION_PRIORITY_CORE
    folder: str = ""
    depends_on: List[str] = field(default_factory=list)
    depended_by: List[str] = field(default_factory=list)
    source_component: str = ""
    build_order: int = 0
    reason_for_existence: str = ""
    contains_code: bool = False
    scalable: bool = True

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("FilePlanEntry requires a non-empty name.")
        if not self.path:
            raise ValueError("FilePlanEntry requires a non-empty path.")

    def add_dependency(self, path: str) -> None:
        """Record that this file depends on another file (by path)."""
        if path and path not in self.depends_on:
            self.depends_on.append(path)

    def add_dependent(self, path: str) -> None:
        """Record that another file depends on this file (by path)."""
        if path and path not in self.depended_by:
            self.depended_by.append(path)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "extension": self.extension,
            "file_type": self.file_type,
            "purpose": self.purpose,
            "responsible_engine": self.responsible_engine,
            "generation_priority": self.generation_priority,
            "folder": self.folder,
            "depends_on": list(self.depends_on),
            "depended_by": list(self.depended_by),
            "source_component": self.source_component,
            "build_order": self.build_order,
            "reason_for_existence": self.reason_for_existence,
            "contains_code": self.contains_code,
            "scalable": self.scalable,
        }


# ---------------------------------------------------------------------------#
# File relationship
# ---------------------------------------------------------------------------#

@dataclass
class FileRelationship:
    """A directed relationship between two planned files.

    Relationships are **recorded but not linked** — they describe which
    files depend on each other so that later engines can wire them up.
    No imports, symlinks, or physical links are created at this stage.

    Attributes:
        source: The source file path.
        target: The target file path.
        kind: The relationship kind (``"depends_on"``, ``"imports"``,
            ``"calls"``, ``"configures"``, ``"documents"``,
            ``"tested_by"``).
        description: A human-readable description.
    """

    source: str
    target: str
    kind: str = "depends_on"
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind,
            "description": self.description,
        }


# ---------------------------------------------------------------------------#
# Generation-order entry
# ---------------------------------------------------------------------------#

@dataclass
class FileGenerationOrderEntry:
    """A single entry in the file generation order sequence.

    The generation order tells later engines in which sequence the
    files should be created.  It is a topological sort of the file
    dependency graph, adjusted by generation priority.

    Attributes:
        position: The 0-based position in the generation sequence.
        file_path: The path of the file.
        file_name: The name of the file.
        responsible_engine: The engine that will build this file.
        source_component: The detected component this file belongs to.
    """

    position: int
    file_path: str
    file_name: str = ""
    responsible_engine: str = ""
    source_component: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "position": self.position,
            "file_path": self.file_path,
            "file_name": self.file_name,
            "responsible_engine": self.responsible_engine,
            "source_component": self.source_component,
        }


# ---------------------------------------------------------------------------#
# Plan finding (for the report)
# ---------------------------------------------------------------------------#

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"


@dataclass
class PlanFinding:
    """A single finding produced during file generation planning.

    Attributes:
        severity: ``"error"`` or ``"warning"``.
        code: A short, machine-readable code (e.g.
            ``"duplicate_file"``).
        message: A human-readable description.
        affected: The path of the affected file or the name of the
            affected component.
        resolution_hint: An optional suggestion on how to fix the
            issue.
    """

    severity: str = SEVERITY_WARNING
    code: str = ""
    message: str = ""
    affected: str = ""
    resolution_hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "affected": self.affected,
            "resolution_hint": self.resolution_hint,
        }


# ---------------------------------------------------------------------------#
# The full file generation plan
# ---------------------------------------------------------------------------#

@dataclass
class FileGenerationPlan:
    """The complete, authoritative plan for every file in the project.

    This is the **only** object the File Generation Planning Engine
    produces.  It is stored in the generation context as the
    ``file_generation_plan`` artefact.

    The plan is **read-only** for all downstream engines — no engine may
    modify it directly.  Any modification requires a dedicated engine.

    Attributes:
        project_name: The machine-friendly project name.
        root_path: The root path of the generated project.
        files: The list of :class:`FilePlanEntry` objects — the
            complete list of every file to be generated.
        relationships: The list of :class:`FileRelationship` objects
            describing the wiring between files.
        generation_order: The ordered list of
            :class:`FileGenerationOrderEntry` objects.
        source_blueprint: The name of the blueprint this plan was
            built from.
        validation_status: The approval status of the blueprint at the
            time the plan was built.
        source_structure_map: The name of the structure map this plan
            was built from.
        source_component_registry: The name of the component registry
            this plan was built from.
        findings: The list of :class:`PlanFinding` objects produced
            during planning (duplicates, naming conflicts, useless
            files, unlinked files).
        summary: A human-readable summary.
        notes: General notes about the plan.
        warnings: Warnings produced during planning.
    """

    project_name: str = ""
    root_path: str = ""
    files: List[FilePlanEntry] = field(default_factory=list)
    relationships: List[FileRelationship] = field(default_factory=list)
    generation_order: List[FileGenerationOrderEntry] = field(default_factory=list)
    source_blueprint: str = ""
    validation_status: str = ""
    source_structure_map: str = ""
    source_component_registry: str = ""
    findings: List[PlanFinding] = field(default_factory=list)
    summary: str = ""
    notes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # -- convenience -------------------------------------------------------#

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def is_empty(self) -> bool:
        return self.file_count == 0

    def file_paths(self) -> List[str]:
        return [f.path for f in self.files]

    def file_names(self) -> List[str]:
        return [f.name for f in self.files]

    def get_file(self, path: str) -> Optional[FilePlanEntry]:
        for f in self.files:
            if f.path == path:
                return f
        return None

    def has_file(self, path: str) -> bool:
        return self.get_file(path) is not None

    def files_for_component(self, component_name: str) -> List[FilePlanEntry]:
        return [f for f in self.files if f.source_component == component_name]

    def files_for_engine(self, engine_id: str) -> List[FilePlanEntry]:
        return [f for f in self.files if f.responsible_engine == engine_id]

    def add_finding(self, severity: str, code: str, message: str,
                    affected: str = "", resolution_hint: str = "") -> None:
        self.findings.append(PlanFinding(
            severity=severity, code=code, message=message,
            affected=affected, resolution_hint=resolution_hint,
        ))
        if severity == SEVERITY_WARNING:
            self.warnings.append(message)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_name": self.project_name,
            "root_path": self.root_path,
            "file_count": self.file_count,
            "source_blueprint": self.source_blueprint,
            "validation_status": self.validation_status,
            "source_structure_map": self.source_structure_map,
            "source_component_registry": self.source_component_registry,
            "summary": self.summary,
            "notes": list(self.notes),
            "warnings": list(self.warnings),
            "files": [f.to_dict() for f in self.files],
            "relationships": [r.to_dict() for r in self.relationships],
            "generation_order": [o.to_dict() for o in self.generation_order],
            "findings": [f.to_dict() for f in self.findings],
        }


__all__ = [
    # Generation-priority constants
    "GENERATION_PRIORITY_INFRASTRUCTURE",
    "GENERATION_PRIORITY_CORE",
    "GENERATION_PRIORITY_DATABASE",
    "GENERATION_PRIORITY_FEATURES",
    "GENERATION_PRIORITY_WIRING",
    "GENERATION_PRIORITY_ENTRY",
    "GENERATION_PRIORITY_DOCS",
    "GENERATION_PRIORITY_TESTS",
    "ALL_GENERATION_PRIORITIES",
    # Extension constants
    "EXTENSION_PYTHON",
    "EXTENSION_YAML",
    "EXTENSION_YML",
    "EXTENSION_TOML",
    "EXTENSION_JSON",
    "EXTENSION_ENV",
    "EXTENSION_SQL",
    "EXTENSION_MARKDOWN",
    "EXTENSION_TEXT",
    "EXTENSION_DOCKERFILE",
    "EXTENSION_SCRIPT",
    "ALL_EXTENSIONS",
    # File-type constants
    "FILE_TYPE_PYTHON_MODULE",
    "FILE_TYPE_PYTHON_PACKAGE",
    "FILE_TYPE_CONFIG",
    "FILE_TYPE_TEXT",
    "FILE_TYPE_MARKDOWN",
    "FILE_TYPE_YAML",
    "FILE_TYPE_TOML",
    "FILE_TYPE_ENV",
    "FILE_TYPE_JSON",
    "FILE_TYPE_SQL",
    "FILE_TYPE_DOCKERFILE",
    "FILE_TYPE_SCRIPT",
    "FILE_TYPE_REQUIREMENTS",
    "ALL_FILE_TYPES",
    # Data model
    "FilePlanEntry",
    "FileRelationship",
    "FileGenerationOrderEntry",
    "PlanFinding",
    "FileGenerationPlan",
    # Findings
    "SEVERITY_ERROR",
    "SEVERITY_WARNING",
    "SEVERITY_INFO",
]
