"""
Component Detection Engine package (Specification 007).

This package contains the component detection engine — the engine that
detects **all** software components the generated project will need
**before** code generation begins.  The engine does **not** write code,
create files, or generate project files.  Its sole function is to
detect, classify, validate, and order every software component.

Public surface
--------------
* :class:`ComponentDetectionEngine` — the engine itself.
* :class:`ComponentRegistry` and all of its sub-dataclasses
  (:class:`DetectedComponent`, :class:`ComponentDependencyEdge`,
  :class:`ComponentBuildOrderEntry`, :class:`DetectionFinding`).
* :class:`TypeDetector` — the component-type classification helper.
* :class:`RelationAnalyzer` — the dependency-graph builder.
* :class:`DuplicateDetector` — the duplicate-component merger.
* :class:`ResponsibilityValidator` — the SRP validator.
* :class:`ScalabilityChecker` — the scalability/reusability checker.
* :class:`CompatibilityChecker` — the compatibility checker.
* :class:`QualityRulesValidator` — the quality-rules validator.
* :class:`BuildOrderComputer` — the build-order computer.
* Component-type and importance-level constants.
"""

from __future__ import annotations

from .detection_engine import ComponentDetectionEngine
from .registry import (
    ComponentRegistry,
    DetectedComponent,
    ComponentDependencyEdge,
    ComponentBuildOrderEntry,
    DetectionFinding,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    SEVERITY_INFO,
    IMPORTANCE_CRITICAL,
    IMPORTANCE_HIGH,
    IMPORTANCE_NORMAL,
    IMPORTANCE_LOW,
    ALL_IMPORTANCE_LEVELS,
    COMPONENT_TYPE_COMMAND,
    COMPONENT_TYPE_HANDLER,
    COMPONENT_TYPE_ROUTER,
    COMPONENT_TYPE_SERVICE,
    COMPONENT_TYPE_MANAGER,
    COMPONENT_TYPE_MIDDLEWARE,
    COMPONENT_TYPE_FILTER,
    COMPONENT_TYPE_DECORATOR,
    COMPONENT_TYPE_UTILITY,
    COMPONENT_TYPE_CONFIGURATION,
    COMPONENT_TYPE_ENVIRONMENT,
    COMPONENT_TYPE_DATABASE_MODEL,
    COMPONENT_TYPE_REPOSITORY,
    COMPONENT_TYPE_VALIDATOR,
    COMPONENT_TYPE_KEYBOARD_BUILDER,
    COMPONENT_TYPE_MESSAGE_BUILDER,
    COMPONENT_TYPE_CALLBACK_HANDLER,
    COMPONENT_TYPE_API_CLIENT,
    COMPONENT_TYPE_SCHEDULER,
    COMPONENT_TYPE_BACKGROUND_TASK,
    COMPONENT_TYPE_CACHE_LAYER,
    COMPONENT_TYPE_LOCALIZATION,
    COMPONENT_TYPE_LOGGING_SYSTEM,
    COMPONENT_TYPE_PLUGIN,
    COMPONENT_TYPE_EXTENSION,
    COMPONENT_TYPE_APPLICATION,
    COMPONENT_TYPE_SESSION,
    ALL_COMPONENT_TYPES,
)
from .type_detector import TypeDetector
from .relation_analyzer import RelationAnalyzer
from .duplicate_detector import DuplicateDetector
from .responsibility_validator import ResponsibilityValidator
from .scalability_checker import ScalabilityChecker
from .compatibility_checker import CompatibilityChecker
from .quality_validator import QualityRulesValidator
from .build_order_computer import BuildOrderComputer

__all__ = [
    # Engine
    "ComponentDetectionEngine",
    # Data model
    "ComponentRegistry",
    "DetectedComponent",
    "ComponentDependencyEdge",
    "ComponentBuildOrderEntry",
    "DetectionFinding",
    # Severity
    "SEVERITY_ERROR",
    "SEVERITY_WARNING",
    "SEVERITY_INFO",
    # Importance
    "IMPORTANCE_CRITICAL",
    "IMPORTANCE_HIGH",
    "IMPORTANCE_NORMAL",
    "IMPORTANCE_LOW",
    "ALL_IMPORTANCE_LEVELS",
    # Component types
    "COMPONENT_TYPE_COMMAND",
    "COMPONENT_TYPE_HANDLER",
    "COMPONENT_TYPE_ROUTER",
    "COMPONENT_TYPE_SERVICE",
    "COMPONENT_TYPE_MANAGER",
    "COMPONENT_TYPE_MIDDLEWARE",
    "COMPONENT_TYPE_FILTER",
    "COMPONENT_TYPE_DECORATOR",
    "COMPONENT_TYPE_UTILITY",
    "COMPONENT_TYPE_CONFIGURATION",
    "COMPONENT_TYPE_ENVIRONMENT",
    "COMPONENT_TYPE_DATABASE_MODEL",
    "COMPONENT_TYPE_REPOSITORY",
    "COMPONENT_TYPE_VALIDATOR",
    "COMPONENT_TYPE_KEYBOARD_BUILDER",
    "COMPONENT_TYPE_MESSAGE_BUILDER",
    "COMPONENT_TYPE_CALLBACK_HANDLER",
    "COMPONENT_TYPE_API_CLIENT",
    "COMPONENT_TYPE_SCHEDULER",
    "COMPONENT_TYPE_BACKGROUND_TASK",
    "COMPONENT_TYPE_CACHE_LAYER",
    "COMPONENT_TYPE_LOCALIZATION",
    "COMPONENT_TYPE_LOGGING_SYSTEM",
    "COMPONENT_TYPE_PLUGIN",
    "COMPONENT_TYPE_EXTENSION",
    "COMPONENT_TYPE_APPLICATION",
    "COMPONENT_TYPE_SESSION",
    "ALL_COMPONENT_TYPES",
    # Helpers
    "TypeDetector",
    "RelationAnalyzer",
    "DuplicateDetector",
    "ResponsibilityValidator",
    "ScalabilityChecker",
    "CompatibilityChecker",
    "QualityRulesValidator",
    "BuildOrderComputer",
]
