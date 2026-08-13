"""
Blueprint Validation Report (Specification 005) — the data model for the
output of the Project Blueprint Validator Engine.

This module defines the structured report that the
:class:`BlueprintValidatorEngine` produces.  The report is the **only**
authoritative verdict on whether a :class:`ProjectBlueprint` may proceed
to the building phase.  No project is allowed to move to generation until
this report's ``status`` is ``APPROVED``.

The report aggregates six :class:`LayerResult` objects (one per
validation layer), a :class:`QualityScore` breakdown, a list of detected
conflicts, a list of missing-information items, and a final approval
status.

The report is a pure data container — no logic lives here.  The
validator engine and its layer helpers populate it; downstream
consumers (the pipeline, the manager, tests) read it.

Design notes
------------
* Every field has a sensible default so a fresh report starts empty and
  is filled incrementally.
* The ``to_dict`` methods mirror the rest of the engine's data classes
  for serialisation and logging.
* Severity levels match the rest of the engine (``"error"``,
  ``"warning"``, ``"info"``).
* The ``status`` field uses the two approval states mandated by the
  specification: ``"APPROVED"`` and ``"REJECTED"``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------#
# Severity and status constants
# ---------------------------------------------------------------------------#

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"

STATUS_APPROVED = "APPROVED"
STATUS_REJECTED = "REJECTED"

# Layer identifiers (stable, used for logging and reporting).
LAYER_1_BASIC_DATA = "layer_1_basic_data"
LAYER_2_FEATURES = "layer_2_features"
LAYER_3_RELATIONSHIPS = "layer_3_relationships"
LAYER_4_EXECUTION_PLAN = "layer_4_execution_plan"
LAYER_5_DEPENDENCIES = "layer_5_dependencies"
LAYER_6_BUILDABILITY = "layer_6_buildability"

ALL_LAYERS = (
    LAYER_1_BASIC_DATA,
    LAYER_2_FEATURES,
    LAYER_3_RELATIONSHIPS,
    LAYER_4_EXECUTION_PLAN,
    LAYER_5_DEPENDENCIES,
    LAYER_6_BUILDABILITY,
)


# ---------------------------------------------------------------------------#
# Individual finding (error / warning / info)
# ---------------------------------------------------------------------------#

@dataclass
class ValidationFinding:
    """A single finding produced by a validation layer.

    Attributes:
        layer: The layer identifier that produced this finding.
        severity: ``"error"`` or ``"warning"``.
        code: A short, machine-readable code (e.g. ``"missing_name"``).
        message: A human-readable description of the finding.
        affected: The name of the affected component / feature / phase.
        resolution_hint: An optional suggestion on how to fix the issue.
    """

    layer: str
    severity: str = SEVERITY_ERROR
    code: str = ""
    message: str = ""
    affected: str = ""
    resolution_hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "layer": self.layer,
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "affected": self.affected,
            "resolution_hint": self.resolution_hint,
        }


# ---------------------------------------------------------------------------#
# Layer result
# ---------------------------------------------------------------------------#

@dataclass
class LayerResult:
    """The outcome of a single validation layer.

    Attributes:
        layer_id: The stable layer identifier (one of the ``LAYER_*``
            constants).
        name: The human-readable layer name.
        passed: ``True`` when the layer found no errors.  Warnings do
            not cause a layer to fail.
        findings: The list of :class:`ValidationFinding` objects.
        duration_ms: The time the layer took to run, in milliseconds.
    """

    layer_id: str
    name: str
    passed: bool = True
    findings: List[ValidationFinding] = field(default_factory=list)
    duration_ms: float = 0.0

    @property
    def errors(self) -> List[ValidationFinding]:
        return [f for f in self.findings if f.severity == SEVERITY_ERROR]

    @property
    def warnings(self) -> List[ValidationFinding]:
        return [f for f in self.findings if f.severity == SEVERITY_WARNING]

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == SEVERITY_ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == SEVERITY_WARNING)

    def add_error(self, code: str, message: str,
                  affected: str = "",
                  resolution_hint: str = "") -> None:
        self.findings.append(ValidationFinding(
            layer=self.layer_id, severity=SEVERITY_ERROR, code=code,
            message=message, affected=affected,
            resolution_hint=resolution_hint,
        ))
        self.passed = False

    def add_warning(self, code: str, message: str,
                    affected: str = "",
                    resolution_hint: str = "") -> None:
        self.findings.append(ValidationFinding(
            layer=self.layer_id, severity=SEVERITY_WARNING, code=code,
            message=message, affected=affected,
            resolution_hint=resolution_hint,
        ))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "layer_id": self.layer_id,
            "name": self.name,
            "passed": self.passed,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "duration_ms": self.duration_ms,
            "findings": [f.to_dict() for f in self.findings],
        }


# ---------------------------------------------------------------------------#
# Quality score
# ---------------------------------------------------------------------------#

@dataclass
class QualityScore:
    """The quality breakdown for the blueprint.

    Each sub-score is a value in the range 0.0–1.0.  The
    :attr:`overall` score is a weighted average computed by the
    :class:`QualityScorer`.  The blueprint is not approved when the
    overall score is below the minimum threshold configured in the
    engine configuration.

    Attributes:
        structure_quality: How well the project structure is defined.
        dependency_quality: How well the dependency graph is formed.
        feature_quality: How well the features are described.
        planning_quality: How well the execution plan is constructed.
        overall: The weighted overall score (0.0–1.0).
        minimum_required: The minimum overall score required for
            approval.  Read from configuration.
        meets_minimum: ``True`` when ``overall >= minimum_required``.
    """

    structure_quality: float = 0.0
    dependency_quality: float = 0.0
    feature_quality: float = 0.0
    planning_quality: float = 0.0
    overall: float = 0.0
    minimum_required: float = 0.7
    meets_minimum: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "structure_quality": round(self.structure_quality, 4),
            "dependency_quality": round(self.dependency_quality, 4),
            "feature_quality": round(self.feature_quality, 4),
            "planning_quality": round(self.planning_quality, 4),
            "overall": round(self.overall, 4),
            "minimum_required": round(self.minimum_required, 4),
            "meets_minimum": self.meets_minimum,
        }


# ---------------------------------------------------------------------------#
# Conflict and missing-info entries
# ---------------------------------------------------------------------------#

@dataclass
class ConflictFinding:
    """A conflict detected in the blueprint.

    Attributes:
        kind: ``"incompatible_database"``, ``"unsupported_framework"``,
            ``"feature_depends_on_missing"``, ``"phase_depends_on_missing"``,
            or any other conflict kind.
        description: What the conflict is.
        severity: ``"error"`` or ``"warning"``.
        affected: The affected component / feature / phase.
        resolution_hint: An optional suggestion to resolve the conflict.
    """

    kind: str
    description: str
    severity: str = SEVERITY_ERROR
    affected: str = ""
    resolution_hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "description": self.description,
            "severity": self.severity,
            "affected": self.affected,
            "resolution_hint": self.resolution_hint,
        }


@dataclass
class MissingInformationFinding:
    """A piece of missing information that blocks approval.

    Attributes:
        field: The blueprint field that is missing.
        description: A description of what is missing.
        question: The question to ask the user to resolve the gap.
        required: Whether this information is required to proceed.
    """

    field: str
    description: str
    question: str = ""
    required: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "description": self.description,
            "question": self.question,
            "required": self.required,
        }


# ---------------------------------------------------------------------------#
# The full report
# ---------------------------------------------------------------------------#

@dataclass
class BlueprintValidationReport:
    """The complete validation report for a :class:`ProjectBlueprint`.

    This is the **only** object the blueprint validator engine produces.
    It is stored in the generation context as the
    ``blueprint_validation_report`` artefact.

    The report's :attr:`status` is the single source of truth for
    whether the blueprint may proceed to generation.  When ``status`` is
    ``REJECTED`` the report carries a detailed list of all the reasons.

    Attributes:
        status: ``"APPROVED"`` or ``"REJECTED"``.
        layers: A mapping of layer id → :class:`LayerResult`.
        quality: The :class:`QualityScore` breakdown.
        conflicts: The list of :class:`ConflictFinding` objects.
        missing_info: The list of :class:`MissingInformationFinding`
            objects.
        errors: The flat list of all error findings across all layers.
        warnings: The flat list of all warning findings across all
            layers.
        total_duration_ms: The total review duration in milliseconds.
        reviewed_at: The review timestamp (ISO-8601 string).
        blueprint_name: The name of the reviewed blueprint.
        summary: A human-readable summary of the verdict.
    """

    status: str = STATUS_REJECTED
    layers: Dict[str, LayerResult] = field(default_factory=dict)
    quality: QualityScore = field(default_factory=QualityScore)
    conflicts: List[ConflictFinding] = field(default_factory=list)
    missing_info: List[MissingInformationFinding] = field(default_factory=list)
    errors: List[ValidationFinding] = field(default_factory=list)
    warnings: List[ValidationFinding] = field(default_factory=list)
    total_duration_ms: float = 0.0
    reviewed_at: str = ""
    blueprint_name: str = ""
    summary: str = ""

    # -- convenience -------------------------------------------------------#

    @property
    def is_approved(self) -> bool:
        return self.status == STATUS_APPROVED

    @property
    def is_rejected(self) -> bool:
        return self.status == STATUS_REJECTED

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    @property
    def has_warnings(self) -> bool:
        return bool(self.warnings)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    @property
    def all_layers_passed(self) -> bool:
        return all(layer.passed for layer in self.layers.values())

    def add_layer(self, result: LayerResult) -> None:
        """Register a layer result and aggregate its findings."""
        self.layers[result.layer_id] = result
        for finding in result.findings:
            if finding.severity == SEVERITY_ERROR:
                self.errors.append(finding)
            elif finding.severity == SEVERITY_WARNING:
                self.warnings.append(finding)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "blueprint_name": self.blueprint_name,
            "is_approved": self.is_approved,
            "all_layers_passed": self.all_layers_passed,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "total_duration_ms": round(self.total_duration_ms, 2),
            "reviewed_at": self.reviewed_at,
            "summary": self.summary,
            "quality": self.quality.to_dict(),
            "layers": {
                lid: lr.to_dict() for lid, lr in self.layers.items()
            },
            "conflicts": [c.to_dict() for c in self.conflicts],
            "missing_info": [m.to_dict() for m in self.missing_info],
            "errors": [f.to_dict() for f in self.errors],
            "warnings": [f.to_dict() for f in self.warnings],
        }


__all__ = [
    # constants
    "SEVERITY_ERROR",
    "SEVERITY_WARNING",
    "SEVERITY_INFO",
    "STATUS_APPROVED",
    "STATUS_REJECTED",
    "LAYER_1_BASIC_DATA",
    "LAYER_2_FEATURES",
    "LAYER_3_RELATIONSHIPS",
    "LAYER_4_EXECUTION_PLAN",
    "LAYER_5_DEPENDENCIES",
    "LAYER_6_BUILDABILITY",
    "ALL_LAYERS",
    # data classes
    "ValidationFinding",
    "LayerResult",
    "QualityScore",
    "ConflictFinding",
    "MissingInformationFinding",
    "BlueprintValidationReport",
]
