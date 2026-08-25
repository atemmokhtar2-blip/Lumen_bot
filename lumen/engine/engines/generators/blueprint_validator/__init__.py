"""
Blueprint Validator Engine package (Specification 005).

This package contains the blueprint validator engine — the gatekeeper
that validates a :class:`ProjectBlueprint` through six independent
layers, detects conflicts, computes a quality score, and produces an
APPROVED/REJECTED verdict.

Public surface
--------------
* :class:`BlueprintValidatorEngine` — the engine itself.
* :class:`BlueprintValidationReport` and all of its sub-dataclasses
  (:class:`ValidationFinding`, :class:`LayerResult`,
  :class:`QualityScore`, :class:`ConflictFinding`,
  :class:`MissingInformationFinding`).
* :class:`ConflictDetector` — the conflict detection helper.
* :class:`QualityScorer` — the quality scoring helper.
* The six validation layer classes.
"""

from __future__ import annotations

from .blueprint_validator_engine import BlueprintValidatorEngine
from .conflict_detector import (
    ConflictDetector,
    SUPPORTED_DATABASES,
    SUPPORTED_FRAMEWORKS,
)
from .quality_scorer import (
    QualityScorer,
    DEFAULT_WEIGHTS,
    DEFAULT_MINIMUM_REQUIRED,
)
from .validation_report import (
    ALL_LAYERS,
    BlueprintValidationReport,
    ConflictFinding,
    LayerResult,
    LAYER_1_BASIC_DATA,
    LAYER_2_FEATURES,
    LAYER_3_RELATIONSHIPS,
    LAYER_4_EXECUTION_PLAN,
    LAYER_5_DEPENDENCIES,
    LAYER_6_BUILDABILITY,
    MissingInformationFinding,
    QualityScore,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    STATUS_APPROVED,
    STATUS_REJECTED,
    ValidationFinding,
)
from .layers import (
    Layer1BasicData,
    Layer2Features,
    Layer3Relationships,
    Layer4ExecutionPlan,
    Layer5Dependencies,
    Layer6Buildability,
)

__all__ = [
    # Engine
    "BlueprintValidatorEngine",
    # Data model
    "BlueprintValidationReport",
    "ValidationFinding",
    "LayerResult",
    "QualityScore",
    "ConflictFinding",
    "MissingInformationFinding",
    # Constants
    "ALL_LAYERS",
    "LAYER_1_BASIC_DATA",
    "LAYER_2_FEATURES",
    "LAYER_3_RELATIONSHIPS",
    "LAYER_4_EXECUTION_PLAN",
    "LAYER_5_DEPENDENCIES",
    "LAYER_6_BUILDABILITY",
    "SEVERITY_ERROR",
    "SEVERITY_WARNING",
    "SEVERITY_INFO",
    "STATUS_APPROVED",
    "STATUS_REJECTED",
    # Helpers
    "ConflictDetector",
    "QualityScorer",
    "SUPPORTED_DATABASES",
    "SUPPORTED_FRAMEWORKS",
    "DEFAULT_WEIGHTS",
    "DEFAULT_MINIMUM_REQUIRED",
    # Layers
    "Layer1BasicData",
    "Layer2Features",
    "Layer3Relationships",
    "Layer4ExecutionPlan",
    "Layer5Dependencies",
    "Layer6Buildability",
]
