"""
File Generation Planning Engine package (Specification 008).

This package contains the file generation planning engine — the engine
that plans **all** files the generated project will contain **before**
any file is created on disk.  The engine does **not** write code,
create files, or generate project files.  Its sole function is to
analyse the project's components and structure map and produce a
complete, validated file generation plan.

Public surface
--------------
* :class:`FileGenerationPlanningEngine` — the engine itself.
* :class:`FileGenerationPlan` and all of its sub-dataclasses
  (:class:`FilePlanEntry`, :class:`FileRelationship`,
  :class:`FileGenerationOrderEntry`, :class:`PlanFinding`).
* :class:`ComponentAnalyzer` — the component analysis helper.
* :class:`FileDeterminer` — the file determination helper.
* :class:`RelationshipResolver` — the relationship resolution helper.
* :class:`GenerationOrderComputer` — the generation order computer.
* :class:`ConflictDetector` — the conflict detection helper.
* :class:`PlanValidator` — the plan validation helper.
* Generation-priority, file-extension, and file-type constants.
"""

from __future__ import annotations

from .file_planning_engine import FileGenerationPlanningEngine
from .plan_data import (
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
    ALL_FILE_TYPES,
)
from .component_analyzer import (
    ComponentAnalyzer,
    ComponentFileAnalysis,
    ComponentAnalysisResult,
)
from .file_determiner import FileDeterminer
from .relationship_resolver import RelationshipResolver
from .generation_order_computer import GenerationOrderComputer
from .conflict_detector import ConflictDetector
from .plan_validator import PlanValidator

__all__ = [
    # Engine
    "FileGenerationPlanningEngine",
    # Data model
    "FileGenerationPlan",
    "FilePlanEntry",
    "FileRelationship",
    "FileGenerationOrderEntry",
    "PlanFinding",
    # Severity
    "SEVERITY_ERROR",
    "SEVERITY_WARNING",
    "SEVERITY_INFO",
    # Generation priorities
    "GENERATION_PRIORITY_INFRASTRUCTURE",
    "GENERATION_PRIORITY_CORE",
    "GENERATION_PRIORITY_DATABASE",
    "GENERATION_PRIORITY_FEATURES",
    "GENERATION_PRIORITY_WIRING",
    "GENERATION_PRIORITY_ENTRY",
    "GENERATION_PRIORITY_DOCS",
    "GENERATION_PRIORITY_TESTS",
    "ALL_GENERATION_PRIORITIES",
    # Extensions
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
    # File types
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
    # Helpers
    "ComponentAnalyzer",
    "ComponentFileAnalysis",
    "ComponentAnalysisResult",
    "FileDeterminer",
    "RelationshipResolver",
    "GenerationOrderComputer",
    "ConflictDetector",
    "PlanValidator",
]
