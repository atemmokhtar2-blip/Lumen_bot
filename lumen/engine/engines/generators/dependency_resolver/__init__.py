"""
Dependency Resolution Engine package (Specification 009).

This package contains the dependency resolution engine — the engine
that builds the complete, authoritative dependency map for the generated
project **before** any code is written or any file is created on disk.
The engine does **not** write code, create files, install libraries, or
add dependencies.  Its sole function is to analyse the project's
components and structure and produce a complete, validated dependency
resolution report.

Public surface
--------------
* :class:`DependencyResolutionEngine` — the engine itself.
* :class:`DependencyResolutionReport` and all of its sub-dataclasses
  (:class:`DependencyEntry`, :class:`DependencyRelationship`,
  :class:`DependencyOrderEntry`, :class:`ResolutionFinding`).
* :class:`ComponentAnalyzer` — the component analysis helper.
* :class:`LibraryDeterminer` — the library determination helper.
* :class:`DependencyGraphBuilder` — the dependency graph builder.
* :class:`CompatibilityChecker` — the compatibility checker.
* :class:`ConflictDetector` — the conflict detection helper.
* :class:`DependencyOptimizer` — the optimization helper.
* :class:`SecurityChecker` — the security checking helper.
* :class:`PlanValidator` — the plan validation helper.
* Dependency-type, dependency-priority, source, reputation, trust,
  stability, and severity constants.
"""

from __future__ import annotations

from .dependency_resolution_engine import DependencyResolutionEngine
from .report_data import (
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
)
from .component_analyzer import (
    ComponentAnalyzer,
    ComponentDependencyAnalysis,
    ComponentAnalysisResult,
)
from .library_determiner import LibraryDeterminer
from .dependency_graph_builder import DependencyGraphBuilder
from .compatibility_checker import CompatibilityChecker
from .conflict_detector import ConflictDetector
from .optimizer import DependencyOptimizer
from .security_checker import SecurityChecker
from .plan_validator import PlanValidator

__all__ = [
    # Engine
    "DependencyResolutionEngine",
    # Data model
    "DependencyResolutionReport",
    "DependencyEntry",
    "DependencyRelationship",
    "DependencyOrderEntry",
    "ResolutionFinding",
    # Severity
    "SEVERITY_ERROR",
    "SEVERITY_WARNING",
    "SEVERITY_INFO",
    # Dependency types
    "DEPENDENCY_TYPE_LIBRARY",
    "DEPENDENCY_TYPE_FRAMEWORK",
    "DEPENDENCY_TYPE_TOOL",
    "DEPENDENCY_TYPE_RUNTIME",
    "DEPENDENCY_TYPE_DEV",
    "DEPENDENCY_TYPE_TEST",
    "DEPENDENCY_TYPE_BUILD",
    "ALL_DEPENDENCY_TYPES",
    # Dependency priorities
    "DEPENDENCY_PRIORITY_INFRASTRUCTURE",
    "DEPENDENCY_PRIORITY_CORE",
    "DEPENDENCY_PRIORITY_DATABASE",
    "DEPENDENCY_PRIORITY_FEATURES",
    "DEPENDENCY_PRIORITY_WIRING",
    "DEPENDENCY_PRIORITY_ENTRY",
    "DEPENDENCY_PRIORITY_TESTS",
    "DEPENDENCY_PRIORITY_DEV",
    "ALL_DEPENDENCY_PRIORITIES",
    # Sources
    "SOURCE_BLUEPRINT",
    "SOURCE_COMPONENT",
    "SOURCE_FILE_PLAN",
    "SOURCE_FRAMEWORK",
    "SOURCE_INFERENCE",
    "ALL_SOURCES",
    # Reputations
    "REPUTATION_GOOD",
    "REPUTATION_NEUTRAL",
    "REPUTATION_BAD",
    "REPUTATION_UNKNOWN",
    "ALL_REPUTATIONS",
    # Trust levels
    "TRUST_OFFICIAL",
    "TRUST_COMMUNITY",
    "TRUST_UNTRUSTED",
    "TRUST_UNKNOWN",
    "ALL_TRUST_LEVELS",
    # Stabilities
    "STABILITY_STABLE",
    "STABILITY_BETA",
    "STABILITY_UNSTABLE",
    "STABILITY_ABANDONED",
    "STABILITY_UNKNOWN",
    "ALL_STABILITIES",
    # Helpers
    "ComponentAnalyzer",
    "ComponentDependencyAnalysis",
    "ComponentAnalysisResult",
    "LibraryDeterminer",
    "DependencyGraphBuilder",
    "CompatibilityChecker",
    "ConflictDetector",
    "DependencyOptimizer",
    "SecurityChecker",
    "PlanValidator",
]
