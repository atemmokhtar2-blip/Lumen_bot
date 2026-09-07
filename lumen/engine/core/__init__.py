"""Core package — IR, results, errors (Cline path only)."""

from .result import GenerationResult, StageResult, Severity, ValidationReport
from .contracts import Component
from .errors import (
    EngineError, EngineExecutionError, BuilderError,
    ValidationError, PipelineError, ConfigurationError,
)
from .ir import BuildIR, EngineMode, IRStatus, AcceptanceCriterion
from .ir_validate import validate_and_normalize_ir, check_project_against_ir

__all__ = [
    "GenerationResult", "StageResult", "Severity", "ValidationReport",
    "Component",
    "EngineError", "EngineExecutionError", "BuilderError",
    "ValidationError", "PipelineError", "ConfigurationError",
    "BuildIR", "EngineMode", "IRStatus", "AcceptanceCriterion",
    "validate_and_normalize_ir", "check_project_against_ir",
]
