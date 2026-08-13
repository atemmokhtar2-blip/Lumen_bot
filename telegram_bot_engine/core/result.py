"""
Result and report types shared across the engine.

These data classes carry information *out* of engines, builders, and
validators so that the pipeline can decide what to do next.  They are
deliberately plain data containers — no business logic lives here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class Severity(Enum):
    """Severity of a validation or generation issue."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class StageResult:
    """Outcome of a single pipeline stage execution.

    Attributes:
        stage_name: Name of the stage that produced the result.
        success: ``True`` when the stage completed without errors.
        outputs: Artefacts produced by the stage (files, data, etc.).
        errors: List of error messages.
        warnings: List of warning messages.
        metadata: Extra information for diagnostics.
    """

    stage_name: str
    success: bool
    outputs: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, stage_name: str, outputs: Optional[Dict[str, Any]] = None,
           metadata: Optional[Dict[str, Any]] = None,
           warnings: Optional[List[str]] = None) -> "StageResult":
        return cls(
            stage_name=stage_name,
            success=True,
            outputs=outputs or {},
            metadata=metadata or {},
            warnings=warnings or [],
        )

    @classmethod
    def failed(cls, stage_name: str, errors: List[str],
               outputs: Optional[Dict[str, Any]] = None,
               warnings: Optional[List[str]] = None,
               metadata: Optional[Dict[str, Any]] = None) -> "StageResult":
        return cls(
            stage_name=stage_name,
            success=False,
            outputs=outputs or {},
            errors=errors,
            warnings=warnings or [],
            metadata=metadata or {},
        )


@dataclass
class ValidationReport:
    """Structured report produced by a validator.

    A validator never raises on warnings — it records them here so the
    pipeline can decide whether to continue.  When errors are present
    the pipeline is expected to stop.
    """

    validator_name: str
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    info: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """``True`` when there are no errors."""
        return len(self.errors) == 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def add_info(self, message: str) -> None:
        self.info.append(message)

    def merge(self, other: "ValidationReport") -> "ValidationReport":
        """Return a new report combining this report with *other*."""
        merged = ValidationReport(
            validator_name=f"{self.validator_name}+{other.validator_name}",
            errors=[*self.errors, *other.errors],
            warnings=[*self.warnings, *other.warnings],
            info=[*self.info, *other.info],
        )
        return merged


@dataclass
class GenerationResult:
    """Final outcome of a complete generation run.

    This is what the orchestrator returns to the caller after the whole
    pipeline has finished.
    """

    success: bool
    project_path: Optional[str] = None
    stages: List[StageResult] = field(default_factory=list)
    validation_reports: List[ValidationReport] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors) or any(not s.success for s in self.stages)


__all__ = [
    "Severity",
    "StageResult",
    "ValidationReport",
    "GenerationResult",
]
