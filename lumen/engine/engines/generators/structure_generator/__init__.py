"""
Project Structure Generation Engine package (Specification 006).

This package contains the structure generation engine — the first engine
that physically builds the project by creating the professional project
structure (folder/file map).  The engine does **not** write code,
functions, classes, or databases.  Its sole function is to create the
project structure.

Public surface
--------------
* :class:`StructureGenerationEngine` — the engine itself.
* :class:`ProjectStructureMap` and all of its sub-dataclasses
  (:class:`FolderEntry`, :class:`FileEntry`,
  :class:`StructureRelationship`, :class:`BuildOrderEntry`).
* :class:`NamingEngine` — the internal naming engine.
* :class:`FolderPlanner` — the folder planning helper.
* :class:`FilePlanner` — the file planning helper.
* :class:`StructureValidator` — the structure validation helper.
* :class:`StructureValidationReport` and :class:`StructureIssue`.
* File-type and build-order constants.
"""

from __future__ import annotations

from .structure_generation_engine import StructureGenerationEngine
from .structure_map import (
    ProjectStructureMap,
    FolderEntry,
    FileEntry,
    StructureRelationship,
    BuildOrderEntry,
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
    BUILD_ORDER_INFRASTRUCTURE,
    BUILD_ORDER_CORE,
    BUILD_ORDER_DATABASE,
    BUILD_ORDER_FEATURES,
    BUILD_ORDER_WIRING,
    BUILD_ORDER_ENTRY,
    BUILD_ORDER_DOCS,
    BUILD_ORDER_TESTS,
)
from .naming_engine import NamingEngine
from .folder_planner import FolderPlanner
from .file_planner import FilePlanner
from .structure_validator import (
    StructureValidator,
    StructureValidationReport,
    StructureIssue,
)

__all__ = [
    # Engine
    "StructureGenerationEngine",
    # Data model
    "ProjectStructureMap",
    "FolderEntry",
    "FileEntry",
    "StructureRelationship",
    "BuildOrderEntry",
    # Helpers
    "NamingEngine",
    "FolderPlanner",
    "FilePlanner",
    "StructureValidator",
    "StructureValidationReport",
    "StructureIssue",
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
