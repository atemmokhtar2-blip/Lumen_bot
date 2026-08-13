"""
Project Structure Map — the data model for the output of the Project
Structure Generation Engine (Specification 006).

The :class:`ProjectStructureMap` is the **complete, authoritative** map
of every folder and every file that the generated Telegram bot project
will contain.  It is the first artefact that physically describes the
project on disk — but it does **not** contain any code, functions,
classes, or database definitions.

The structure map is built by the
:class:`StructureGenerationEngine` from the
:class:`~telegram_bot_engine.engines.generators.project_planner.blueprint.ProjectBlueprint`
and the
:class:`~telegram_bot_engine.engines.generators.blueprint_validator.validation_report.BlueprintValidationReport`.
It does **not** read the user's request.

Design principles
-----------------
* **Single responsibility per folder/file.**  Every folder entry and
  every file entry has exactly one purpose.
* **No large files, no merged functions.**  The structure map itself is
  a pure data container — no logic lives here.
* **Scalable.**  The map is built per-project needs: small projects get
  a lean structure, large projects are split into independent packages.
* **No code inside files at this stage.**  File entries describe *what*
  a file is for and *which engine* will build it later — not its
  contents.
* **Relationships, not links.**  Dependencies between files/folders are
  recorded as relationship entries for later engines to use; no actual
  imports or links are created.

The map is a plain data container with ``to_dict()`` methods for
serialisation, logging, and inspection by downstream engines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------#
# Build-order position constants
# ---------------------------------------------------------------------------#

BUILD_ORDER_INFRASTRUCTURE = 10
BUILD_ORDER_CORE = 20
BUILD_ORDER_DATABASE = 30
BUILD_ORDER_FEATURES = 40
BUILD_ORDER_WIRING = 50
BUILD_ORDER_ENTRY = 60
BUILD_ORDER_DOCS = 70
BUILD_ORDER_TESTS = 80


# ---------------------------------------------------------------------------#
# File-type constants
# ---------------------------------------------------------------------------#

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


# ---------------------------------------------------------------------------#
# Folder entry
# ---------------------------------------------------------------------------#

@dataclass
class FolderEntry:
    """A single folder in the project structure.

    Attributes:
        name: The folder name (e.g. ``"handlers"``, ``"models"``).
        path: The full relative path from the project root
            (e.g. ``"src/handlers"``).
        purpose: What this folder is for — a single, clear
            responsibility.
        parent: The parent folder path, or empty string for a
            top-level folder.
        subfolders: The names of the immediate subfolders.
        relationships: A list of :class:`StructureRelationship`
            objects describing how this folder relates to other
            folders or files.
        build_order: The position in the build sequence (lower first).
        reason: Why this folder exists (helps the validator detect
            empty or unnecessary folders).
        scalable: ``True`` when this folder can hold additional
            subfolders without restructuring.
    """

    name: str
    path: str
    purpose: str = ""
    parent: str = ""
    subfolders: List[str] = field(default_factory=list)
    relationships: List["StructureRelationship"] = field(default_factory=list)
    build_order: int = BUILD_ORDER_CORE
    reason: str = ""
    scalable: bool = True

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("FolderEntry requires a non-empty name.")
        if not self.path:
            raise ValueError("FolderEntry requires a non-empty path.")

    def add_relationship(self, target: str, kind: str,
                         description: str = "") -> None:
        """Record a relationship to another folder or file."""
        self.relationships.append(StructureRelationship(
            source=self.path,
            target=target,
            kind=kind,
            description=description,
        ))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "purpose": self.purpose,
            "parent": self.parent,
            "subfolders": list(self.subfolders),
            "relationships": [r.to_dict() for r in self.relationships],
            "build_order": self.build_order,
            "reason": self.reason,
            "scalable": self.scalable,
        }


# ---------------------------------------------------------------------------#
# File entry
# ---------------------------------------------------------------------------#

@dataclass
class FileEntry:
    """A single file in the project structure.

    Attributes:
        name: The file name (e.g. ``"main.py"``, ``"config.yaml"``).
        path: The full relative path from the project root
            (e.g. ``"src/main.py"``).
        file_type: The file type (one of the ``FILE_TYPE_*`` constants).
        purpose: What this file is for — a single, clear
            responsibility.
        folder: The folder path this file lives in (or empty string
            for a root-level file).
        building_engine: The engine that will build this file later
            (e.g. ``"code_generator"``, ``"database_engine"``).  Empty
            string when no specific engine is assigned yet.
        build_order: The position in the build sequence (lower first).
        relationships: A list of :class:`StructureRelationship`
            objects describing how this file relates to other files
            or folders.
        source_component: The internal component this file belongs to,
            if any.
        contains_code: ``True`` when this file will eventually contain
            executable code (as opposed to config, docs, etc.).
    """

    name: str
    path: str
    file_type: str = FILE_TYPE_TEXT
    purpose: str = ""
    folder: str = ""
    building_engine: str = ""
    build_order: int = BUILD_ORDER_CORE
    relationships: List["StructureRelationship"] = field(default_factory=list)
    source_component: str = ""
    contains_code: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("FileEntry requires a non-empty name.")
        if not self.path:
            raise ValueError("FileEntry requires a non-empty path.")

    def add_relationship(self, target: str, kind: str,
                         description: str = "") -> None:
        """Record a relationship to another file or folder."""
        self.relationships.append(StructureRelationship(
            source=self.path,
            target=target,
            kind=kind,
            description=description,
        ))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "file_type": self.file_type,
            "purpose": self.purpose,
            "folder": self.folder,
            "building_engine": self.building_engine,
            "build_order": self.build_order,
            "relationships": [r.to_dict() for r in self.relationships],
            "source_component": self.source_component,
            "contains_code": self.contains_code,
        }


# ---------------------------------------------------------------------------#
# Structure relationship
# ---------------------------------------------------------------------------#

@dataclass
class StructureRelationship:
    """A relationship between two entries in the structure map.

    Relationships are **recorded but not linked** — they describe which
    files or folders depend on each other so that later engines can wire
    them up.  No imports, symlinks, or physical links are created at
    this stage.

    Attributes:
        source: The source path (a folder or file path).
        target: The target path (a folder or file path).
        kind: The relationship kind (``"contains"``,
            ``"depends_on"``, ``"imports"``, ``"managed_by"``,
            ``"stored_in"``, ``"configures"``, ``"documents"``).
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
# Build order entry
# ---------------------------------------------------------------------------#

@dataclass
class BuildOrderEntry:
    """A single entry in the build order sequence.

    The build order tells later engines in which sequence the files
    and folders should be materialised.

    Attributes:
        position: The 0-based position in the build sequence.
        path: The path of the folder or file.
        kind: ``"folder"`` or ``"file"``.
        building_engine: The engine that will build this entry (for
            files only).
    """

    position: int
    path: str
    kind: str = "file"
    building_engine: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "position": self.position,
            "path": self.path,
            "kind": self.kind,
            "building_engine": self.building_engine,
        }


# ---------------------------------------------------------------------------#
# The full structure map
# ---------------------------------------------------------------------------#

@dataclass
class ProjectStructureMap:
    """The complete structure map for the generated Telegram bot project.

    This is the **only** object the Structure Generation Engine produces.
    It is stored in the generation context as the
    ``project_structure_map`` artefact.

    The map is **read-only** for all downstream engines — no engine may
    modify it directly.  Any modification requires a dedicated engine.

    Attributes:
        project_name: The machine-friendly project name (root
            package).
        root_path: The root path of the generated project (usually the
            project name).
        folders: The list of :class:`FolderEntry` objects.
        files: The list of :class:`FileEntry` objects.
        build_order: The ordered list of :class:`BuildOrderEntry`
            objects.
        source_blueprint: The name of the blueprint this map was built
            from.
        validation_status: The approval status of the blueprint at the
            time the map was built.
        component_to_folder: A mapping from internal component name to
            the folder that holds its files.
        summary: A human-readable summary.
        notes: General notes about the structure.
        warnings: Warnings produced during structure generation.
    """

    project_name: str = ""
    root_path: str = ""
    folders: List[FolderEntry] = field(default_factory=list)
    files: List[FileEntry] = field(default_factory=list)
    build_order: List[BuildOrderEntry] = field(default_factory=list)
    source_blueprint: str = ""
    validation_status: str = ""
    component_to_folder: Dict[str, str] = field(default_factory=dict)
    summary: str = ""
    notes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # -- convenience -------------------------------------------------------#

    @property
    def folder_count(self) -> int:
        return len(self.folders)

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def is_empty(self) -> bool:
        return self.folder_count == 0 and self.file_count == 0

    def folder_paths(self) -> List[str]:
        """Return all folder paths."""
        return [f.path for f in self.folders]

    def file_paths(self) -> List[str]:
        """Return all file paths."""
        return [f.path for f in self.files]

    def all_paths(self) -> List[str]:
        """Return every path (folders and files) in the map."""
        return self.folder_paths() + self.file_paths()

    def get_folder(self, path: str) -> Optional[FolderEntry]:
        for f in self.folders:
            if f.path == path:
                return f
        return None

    def get_file(self, path: str) -> Optional[FileEntry]:
        for f in self.files:
            if f.path == path:
                return f
        return None

    def files_in_folder(self, folder_path: str) -> List[FileEntry]:
        """Return all files that live directly in the given folder.

        A file is considered to live in a folder when either its
        ``folder`` attribute matches the path or the parent path
        derived from its ``path`` matches.
        """
        result: List[FileEntry] = []
        for f in self.files:
            if f.folder == folder_path:
                result.append(f)
            elif not f.folder and f.path:
                parent = "/".join(f.path.strip("/").split("/")[:-1])
                if parent == folder_path:
                    result.append(f)
        return result

    def subfolders_of(self, folder_path: str) -> List[FolderEntry]:
        """Return all folders whose parent is the given path."""
        return [f for f in self.folders if f.parent == folder_path]

    def files_for_engine(self, engine_id: str) -> List[FileEntry]:
        """Return all files assigned to a given building engine."""
        return [f for f in self.files if f.building_engine == engine_id]

    def files_for_component(self, component_name: str) -> List[FileEntry]:
        """Return all files belonging to a given internal component."""
        return [f for f in self.files if f.source_component == component_name]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_name": self.project_name,
            "root_path": self.root_path,
            "folder_count": self.folder_count,
            "file_count": self.file_count,
            "source_blueprint": self.source_blueprint,
            "validation_status": self.validation_status,
            "component_to_folder": dict(self.component_to_folder),
            "summary": self.summary,
            "notes": list(self.notes),
            "warnings": list(self.warnings),
            "folders": [f.to_dict() for f in self.folders],
            "files": [f.to_dict() for f in self.files],
            "build_order": [b.to_dict() for b in self.build_order],
        }


__all__ = [
    # Data model
    "ProjectStructureMap",
    "FolderEntry",
    "FileEntry",
    "StructureRelationship",
    "BuildOrderEntry",
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
    # Build-order constants
    "BUILD_ORDER_INFRASTRUCTURE",
    "BUILD_ORDER_CORE",
    "BUILD_ORDER_DATABASE",
    "BUILD_ORDER_FEATURES",
    "BUILD_ORDER_WIRING",
    "BUILD_ORDER_ENTRY",
    "BUILD_ORDER_DOCS",
    "BUILD_ORDER_TESTS",
]
