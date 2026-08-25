"""
Project Structure Blueprint data model (Specification 020).

This module defines the :class:`ProjectStructureBlueprint` -- the
complete, authoritative output of the
:class:`~lumen.engine.engines.generators.project_structure_planning.ProjectStructurePlanningEngine`.

The Project Structure Planning Engine is responsible for designing the
complete project layout **before any file is created**.  It does **not**
write code or create files on disk.  Its sole function is to produce the
*Project Structure Blueprint* -- the official map that downstream engines
will use to materialise the project.

Data sources
------------
The engine reads **five** data sources:

1. **Execution Plan** -- the ``execution_plan`` artefact produced by the
   :class:`~lumen.engine.engines.generators.execution_planning.ExecutionPlanningEngine`.
2. **Architecture Decision Report** -- the
   ``architecture_decision_report`` artefact.
3. **Technology Selection Report** -- the
   ``technology_selection_report`` artefact.
4. **Normalized Requirement Model** -- the
   ``requirement_normalization_report`` artefact.
5. **Project Capability Report** -- the
   ``project_capability_report`` artefact.

Responsibilities
-----------------
* Analyse the project type and scale.
* Design the optimal folder hierarchy.
* Enumerate every required file with full metadata.
* Map modules to folders and files to modules.
* Build the inter-file dependency graph (imports / exports / interfaces).
* Ensure the structure is scalable for future modules.
* Validate the structure (no duplicates, no unused folders, no name
  collisions, no circular structure).
* Produce the *Project Structure Blueprint* with a readiness verdict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------#
# Source constants
# ---------------------------------------------------------------------------#

SOURCE_EXECUTION_PLAN = "execution_plan"
SOURCE_ARCHITECTURE_DECISION = "architecture_decision_report"
SOURCE_TECHNOLOGY_SELECTION = "technology_selection_report"
SOURCE_NORMALIZED_REQUIREMENTS = "requirement_normalization_report"
SOURCE_PROJECT_CAPABILITY = "project_capability_report"

ALL_SOURCES = (
    SOURCE_EXECUTION_PLAN,
    SOURCE_ARCHITECTURE_DECISION,
    SOURCE_TECHNOLOGY_SELECTION,
    SOURCE_NORMALIZED_REQUIREMENTS,
    SOURCE_PROJECT_CAPABILITY,
)


# ---------------------------------------------------------------------------#
# Folder / file type constants
# ---------------------------------------------------------------------------#

FOLDER_ROOT = "root"
FOLDER_CORE = "core"
FOLDER_MODULES = "modules"
FOLDER_HANDLERS = "handlers"
FOLDER_SERVICES = "services"
FOLDER_DATABASE = "database"
FOLDER_UTILS = "utils"
FOLDER_CONFIGS = "configs"
FOLDER_TESTS = "tests"
FOLDER_ASSETS = "assets"
FOLDER_LOGS = "logs"
FOLDER_DOCS = "docs"
FOLDER_SCRIPTS = "scripts"
FOLDER_MIDDLEWARE = "middleware"
FOLDER_API = "api"
FOLDER_MODELS = "models"
FOLDER_REPOSITORIES = "repositories"

ALL_STANDARD_FOLDERS = (
    FOLDER_ROOT,
    FOLDER_CORE,
    FOLDER_MODULES,
    FOLDER_HANDLERS,
    FOLDER_SERVICES,
    FOLDER_DATABASE,
    FOLDER_UTILS,
    FOLDER_CONFIGS,
    FOLDER_TESTS,
    FOLDER_ASSETS,
    FOLDER_LOGS,
    FOLDER_DOCS,
    FOLDER_SCRIPTS,
    FOLDER_MIDDLEWARE,
    FOLDER_API,
    FOLDER_MODELS,
    FOLDER_REPOSITORIES,
)

FILE_TYPE_PYTHON = "python"
FILE_TYPE_CONFIG = "config"
FILE_TYPE_TEST = "test"
FILE_TYPE_DOC = "documentation"
FILE_TYPE_SCRIPT = "script"
FILE_TYPE_ASSET = "asset"
FILE_TYPE_DATA = "data"
FILE_TYPE_INIT = "init"
FILE_TYPE_OTHER = "other"

ALL_FILE_TYPES = (
    FILE_TYPE_PYTHON,
    FILE_TYPE_CONFIG,
    FILE_TYPE_TEST,
    FILE_TYPE_DOC,
    FILE_TYPE_SCRIPT,
    FILE_TYPE_ASSET,
    FILE_TYPE_DATA,
    FILE_TYPE_INIT,
    FILE_TYPE_OTHER,
)


# ---------------------------------------------------------------------------#
# Severity / conflict / quality constants
# ---------------------------------------------------------------------------#

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

ALL_SEVERITIES = (
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    SEVERITY_LOW,
)

CONFLICT_DUPLICATE_FILE = "duplicate_file"
CONFLICT_DUPLICATE_FOLDER = "duplicate_folder"
CONFLICT_UNUSED_FOLDER = "unused_folder"
CONFLICT_NAME_COLLISION = "name_collision"
CONFLICT_CIRCULAR_STRUCTURE = "circular_structure"
CONFLICT_MISSING_REQUIRED = "missing_required_item"
CONFLICT_ORPHAN_FILE = "orphan_file"

ALL_CONFLICT_TYPES = (
    CONFLICT_DUPLICATE_FILE,
    CONFLICT_DUPLICATE_FOLDER,
    CONFLICT_UNUSED_FOLDER,
    CONFLICT_NAME_COLLISION,
    CONFLICT_CIRCULAR_STRUCTURE,
    CONFLICT_MISSING_REQUIRED,
    CONFLICT_ORPHAN_FILE,
)

RULE_NO_CRITICAL_CONFLICTS = "no_critical_conflicts"
RULE_NO_DUPLICATES = "no_duplicates"
RULE_NO_UNUSED_FOLDERS = "no_unused_folders"
RULE_NO_NAME_COLLISIONS = "no_name_collisions"
RULE_NO_CIRCULAR_STRUCTURE = "no_circular_structure"
RULE_STRUCTURE_COMPLETE = "structure_complete"
RULE_SUFFICIENT_CONFIDENCE = "sufficient_confidence"

ALL_QUALITY_RULES = (
    RULE_NO_CRITICAL_CONFLICTS,
    RULE_NO_DUPLICATES,
    RULE_NO_UNUSED_FOLDERS,
    RULE_NO_NAME_COLLISIONS,
    RULE_NO_CIRCULAR_STRUCTURE,
    RULE_STRUCTURE_COMPLETE,
    RULE_SUFFICIENT_CONFIDENCE,
)


# ---------------------------------------------------------------------------#
# Cache / confidence / verdict constants
# ---------------------------------------------------------------------------#

CACHE_HIT = "hit"
CACHE_MISS = "miss"
CACHE_STALE = "stale"
CACHE_DISABLED = "disabled"

ALL_CACHE_STATUSES = (CACHE_HIT, CACHE_MISS, CACHE_STALE, CACHE_DISABLED)

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"

ALL_CONFIDENCE_LEVELS = (CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW)

CONFIDENCE_HIGH_THRESHOLD = 0.85
CONFIDENCE_MEDIUM_THRESHOLD = 0.60

VERDICT_READY = "ready"
VERDICT_READY_WITH_WARNINGS = "ready_with_warnings"
VERDICT_NOT_READY = "not_ready"

ALL_VERDICTS = (VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY)


# ---------------------------------------------------------------------------#
# Data classes
# ---------------------------------------------------------------------------#

@dataclass
class FolderNode:
    """A node in the project folder tree.

    Attributes:
        folder_id: Unique identifier.
        name: Folder name (last path segment).
        path: Full relative path from project root.
        purpose: Why this folder exists.
        parent_id: folder_id of the parent (None for root).
        children: List of child folder_ids.
        is_standard: Whether it is one of the canonical folders.
        tags: Classification tags.
    """

    folder_id: str
    name: str
    path: str
    purpose: str = ""
    parent_id: Optional[str] = None
    children: List[str] = field(default_factory=list)
    is_standard: bool = True
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "folder_id": self.folder_id,
            "name": self.name,
            "path": self.path,
            "purpose": self.purpose,
            "parent_id": self.parent_id,
            "children": list(self.children),
            "is_standard": self.is_standard,
            "tags": list(self.tags),
        }


@dataclass
class FileDescriptor:
    """Full metadata for a single planned file.

    Attributes:
        file_id: Unique identifier.
        name: File name including extension.
        path: Full relative path from project root.
        purpose: Short description of the file's role.
        responsibility: Detailed responsibility statement.
        file_type: One of ALL_FILE_TYPES.
        module_id: The module this file belongs to (if any).
        folder_id: The folder that contains this file.
        depends_on: List of file_ids this file depends on.
        exports: Symbols / interfaces this file exports.
        is_required: Whether the file is mandatory.
        tags: Classification tags.
        metadata: Arbitrary extra information.
    """

    file_id: str
    name: str
    path: str
    purpose: str = ""
    responsibility: str = ""
    file_type: str = FILE_TYPE_PYTHON
    module_id: str = ""
    folder_id: str = ""
    depends_on: List[str] = field(default_factory=list)
    exports: List[str] = field(default_factory=list)
    is_required: bool = True
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_id": self.file_id,
            "name": self.name,
            "path": self.path,
            "purpose": self.purpose,
            "responsibility": self.responsibility,
            "file_type": self.file_type,
            "module_id": self.module_id,
            "folder_id": self.folder_id,
            "depends_on": list(self.depends_on),
            "exports": list(self.exports),
            "is_required": self.is_required,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
        }


@dataclass
class ModuleMapping:
    """Maps a logical module to its physical location and files.

    Attributes:
        module_id: Unique identifier.
        name: Human-readable module name.
        folder_path: Path of the primary folder for this module.
        file_ids: Files that belong to this module.
        description: Purpose of the module.
        depends_on_modules: Other module_ids this module needs.
    """

    module_id: str
    name: str
    folder_path: str = ""
    file_ids: List[str] = field(default_factory=list)
    description: str = ""
    depends_on_modules: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module_id": self.module_id,
            "name": self.name,
            "folder_path": self.folder_path,
            "file_ids": list(self.file_ids),
            "description": self.description,
            "depends_on_modules": list(self.depends_on_modules),
        }


@dataclass
class FileDependency:
    """A directed dependency between two files.

    Attributes:
        from_file_id: The file that is imported / required.
        to_file_id: The file that performs the import.
        dependency_kind: import / interface / shared / data.
        reason: Why the dependency exists.
    """

    from_file_id: str
    to_file_id: str
    dependency_kind: str = "import"
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_file_id": self.from_file_id,
            "to_file_id": self.to_file_id,
            "dependency_kind": self.dependency_kind,
            "reason": self.reason,
        }


@dataclass
class StructureConflict:
    """A detected structural problem.

    Attributes:
        conflict_id: Unique identifier.
        conflict_type: One of ALL_CONFLICT_TYPES.
        severity: critical / high / medium / low.
        message: Human-readable description.
        affected_paths: Paths involved.
        resolution_hint: Suggested fix.
    """

    conflict_id: str
    conflict_type: str
    severity: str = SEVERITY_HIGH
    message: str = ""
    affected_paths: List[str] = field(default_factory=list)
    resolution_hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "conflict_type": self.conflict_type,
            "severity": self.severity,
            "message": self.message,
            "affected_paths": list(self.affected_paths),
            "resolution_hint": self.resolution_hint,
        }


@dataclass
class StructureFinding:
    """A quality / validation finding.

    Attributes:
        severity: critical / high / medium / low.
        code: Machine-readable code.
        message: Human-readable message.
        affected: What is affected.
        resolution_hint: How to resolve.
        category: quality / structure / dependency.
    """

    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "quality"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "affected": self.affected,
            "resolution_hint": self.resolution_hint,
            "category": self.category,
        }


@dataclass
class CacheInfo:
    """Cache metadata for the structure blueprint."""

    status: str = CACHE_MISS
    key: str = ""
    created_at: str = ""
    hits: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "key": self.key,
            "created_at": self.created_at,
            "hits": self.hits,
        }


@dataclass
class StructureProvenance:
    """Provenance information for the generated blueprint."""

    engine_name: str = "project_structure_planning"
    engine_version: str = "1.0.0"
    sources_used: List[str] = field(default_factory=list)
    sources_missing: List[str] = field(default_factory=list)
    generated_at: str = ""
    confidence: float = 0.0
    confidence_level: str = CONFIDENCE_LOW

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_name": self.engine_name,
            "engine_version": self.engine_version,
            "sources_used": list(self.sources_used),
            "sources_missing": list(self.sources_missing),
            "generated_at": self.generated_at,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level,
        }


@dataclass
class ProjectStructureBlueprint:
    """The complete, authoritative Project Structure Blueprint.

    This is the sole output of the Project Structure Planning Engine.
    Downstream engines treat it as the single source of truth for the
    physical layout of the generated project.

    Attributes:
        blueprint_id: Unique identifier.
        root_name: Suggested project root folder name.
        folders: All FolderNode objects.
        files: All FileDescriptor objects.
        modules: All ModuleMapping objects.
        dependencies: All FileDependency edges.
        conflicts: Detected structural conflicts.
        findings: Quality / validation findings.
        folder_tree: Nested dict representation of the folder hierarchy
            (convenient for consumers that prefer a tree view).
        readiness_status: Overall readiness.
        verdict: Final verdict after quality gate.
        cache_info: Cache metadata.
        provenance: Provenance and confidence.
        metadata: Arbitrary extra information.
        is_empty: True when the blueprint contains no useful content.
    """

    blueprint_id: str = ""
    root_name: str = "telegram_bot"
    folders: List[FolderNode] = field(default_factory=list)
    files: List[FileDescriptor] = field(default_factory=list)
    modules: List[ModuleMapping] = field(default_factory=list)
    dependencies: List[FileDependency] = field(default_factory=list)
    conflicts: List[StructureConflict] = field(default_factory=list)
    findings: List[StructureFinding] = field(default_factory=list)
    folder_tree: Dict[str, Any] = field(default_factory=dict)
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: StructureProvenance = field(default_factory=StructureProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "blueprint_id": self.blueprint_id,
            "root_name": self.root_name,
            "folders": [f.to_dict() for f in self.folders],
            "files": [f.to_dict() for f in self.files],
            "modules": [m.to_dict() for m in self.modules],
            "dependencies": [d.to_dict() for d in self.dependencies],
            "conflicts": [c.to_dict() for c in self.conflicts],
            "findings": [f.to_dict() for f in self.findings],
            "folder_tree": dict(self.folder_tree),
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    # Source constants
    "SOURCE_EXECUTION_PLAN",
    "SOURCE_ARCHITECTURE_DECISION",
    "SOURCE_TECHNOLOGY_SELECTION",
    "SOURCE_NORMALIZED_REQUIREMENTS",
    "SOURCE_PROJECT_CAPABILITY",
    "ALL_SOURCES",
    # Folder / file type constants
    "FOLDER_ROOT",
    "FOLDER_CORE",
    "FOLDER_MODULES",
    "FOLDER_HANDLERS",
    "FOLDER_SERVICES",
    "FOLDER_DATABASE",
    "FOLDER_UTILS",
    "FOLDER_CONFIGS",
    "FOLDER_TESTS",
    "FOLDER_ASSETS",
    "FOLDER_LOGS",
    "FOLDER_DOCS",
    "FOLDER_SCRIPTS",
    "FOLDER_MIDDLEWARE",
    "FOLDER_API",
    "FOLDER_MODELS",
    "FOLDER_REPOSITORIES",
    "ALL_STANDARD_FOLDERS",
    "FILE_TYPE_PYTHON",
    "FILE_TYPE_CONFIG",
    "FILE_TYPE_TEST",
    "FILE_TYPE_DOC",
    "FILE_TYPE_SCRIPT",
    "FILE_TYPE_ASSET",
    "FILE_TYPE_DATA",
    "FILE_TYPE_INIT",
    "FILE_TYPE_OTHER",
    "ALL_FILE_TYPES",
    # Severity / conflict / quality
    "SEVERITY_CRITICAL",
    "SEVERITY_HIGH",
    "SEVERITY_MEDIUM",
    "SEVERITY_LOW",
    "ALL_SEVERITIES",
    "CONFLICT_DUPLICATE_FILE",
    "CONFLICT_DUPLICATE_FOLDER",
    "CONFLICT_UNUSED_FOLDER",
    "CONFLICT_NAME_COLLISION",
    "CONFLICT_CIRCULAR_STRUCTURE",
    "CONFLICT_MISSING_REQUIRED",
    "CONFLICT_ORPHAN_FILE",
    "ALL_CONFLICT_TYPES",
    "RULE_NO_CRITICAL_CONFLICTS",
    "RULE_NO_DUPLICATES",
    "RULE_NO_UNUSED_FOLDERS",
    "RULE_NO_NAME_COLLISIONS",
    "RULE_NO_CIRCULAR_STRUCTURE",
    "RULE_STRUCTURE_COMPLETE",
    "RULE_SUFFICIENT_CONFIDENCE",
    "ALL_QUALITY_RULES",
    # Cache / confidence / verdict
    "CACHE_HIT",
    "CACHE_MISS",
    "CACHE_STALE",
    "CACHE_DISABLED",
    "ALL_CACHE_STATUSES",
    "CONFIDENCE_HIGH",
    "CONFIDENCE_MEDIUM",
    "CONFIDENCE_LOW",
    "ALL_CONFIDENCE_LEVELS",
    "CONFIDENCE_HIGH_THRESHOLD",
    "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY",
    "VERDICT_READY_WITH_WARNINGS",
    "VERDICT_NOT_READY",
    "ALL_VERDICTS",
    # Data classes
    "FolderNode",
    "FileDescriptor",
    "ModuleMapping",
    "FileDependency",
    "StructureConflict",
    "StructureFinding",
    "CacheInfo",
    "StructureProvenance",
    "ProjectStructureBlueprint",
]
