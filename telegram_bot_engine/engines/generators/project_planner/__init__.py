"""
Project Planning Engine package (Specification 004).

This package contains the planning brain of the Telegram Bot
Generation Engine.  Its sole function is to convert the
:class:`AnalysisReport` (produced by the Core Request Analyzer Engine)
into a professional :class:`ProjectBlueprint` that the rest of the
system relies on.

Public surface
--------------
* :class:`ProjectPlanningEngine` \\u2014 the engine itself.
* :class:`ProjectBlueprint` and all of its sub-dataclasses.
* :class:`FeatureUnit` and the priority constants.
* :class:`DependencyGraph` and :class:`DependencyNode`.
* :class:`ExecutionPlan`, :class:`ExecutionPhase`, :class:`PhaseStatus`,
  :class:`PhaseDefinition`, and the :data:`DEFAULT_PHASES` list.
* :class:`RiskDetector` and :class:`BlueprintValidator`.
"""

from __future__ import annotations

from .blueprint import (
    BlueprintRisk,
    BlueprintValidation,
    ComponentRelationship,
    ExpectedStructure,
    InternalComponent,
    ProjectBlueprint,
    ProjectIdentity,
    RequiredEngine,
    StructureEntry,
)
from .dependency_graph import DependencyGraph, DependencyNode
from .execution_plan import (
    DEFAULT_PHASES,
    ExecutionPhase,
    ExecutionPlan,
    PhaseDefinition,
    PhaseStatus,
)
from .feature_unit import (
    PRIORITY_CRITICAL,
    PRIORITY_DEFERRED,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_NORMAL,
    FeatureUnit,
)
from .planning_engine import ProjectPlanningEngine
from .risk_detection import RiskDetector
from .validation import BlueprintValidator

__all__ = [
    # Engine
    "ProjectPlanningEngine",
    # Blueprint data model
    "ProjectBlueprint",
    "ProjectIdentity",
    "ExpectedStructure",
    "StructureEntry",
    "InternalComponent",
    "ComponentRelationship",
    "RequiredEngine",
    "BlueprintRisk",
    "BlueprintValidation",
    # Feature breakdown
    "FeatureUnit",
    "PRIORITY_CRITICAL",
    "PRIORITY_HIGH",
    "PRIORITY_NORMAL",
    "PRIORITY_LOW",
    "PRIORITY_DEFERRED",
    # Dependency graph
    "DependencyGraph",
    "DependencyNode",
    # Execution plan
    "ExecutionPlan",
    "ExecutionPhase",
    "PhaseDefinition",
    "PhaseStatus",
    "DEFAULT_PHASES",
    # Risk & validation
    "RiskDetector",
    "BlueprintValidator",
]
