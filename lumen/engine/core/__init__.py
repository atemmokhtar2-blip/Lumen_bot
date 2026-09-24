"""Core package — IR, results, errors (Cline path only)."""

from .result import GenerationResult, StageResult, Severity, ValidationReport
from .contracts import Component
from .errors import (
    EngineError, EngineExecutionError, BuilderError,
    ValidationError, PipelineError, ConfigurationError,
)
from .ir import BuildIR, EngineMode, IRStatus, AcceptanceCriterion
from .language_runtime import (
    LanguageRuntime, resolve_language, language_metadata, recipe_for,
    assert_language_allowed, enabled_languages, parse_language as parse_language_runtime,
)
from .project_kind import (
    ProjectKind, DeliverySurface, resolve_project_kind, delivery_surface,
    kind_metadata, label_ar, http_runtime_hints, runtime_contract,
    default_deliverables, acceptance_hints, seed_workspace,
)
from .ir_validate import validate_and_normalize_ir, check_project_against_ir

__all__ = [
    "GenerationResult", "StageResult", "Severity", "ValidationReport",
    "Component",
    "EngineError", "EngineExecutionError", "BuilderError",
    "ValidationError", "PipelineError", "ConfigurationError",
    "BuildIR", "EngineMode", "IRStatus", "AcceptanceCriterion",
    "LanguageRuntime", "resolve_language", "language_metadata", "recipe_for",
    "assert_language_allowed", "enabled_languages", "parse_language_runtime",
    "ProjectKind", "DeliverySurface", "resolve_project_kind", "delivery_surface", "kind_metadata", "label_ar", "http_runtime_hints",
    "runtime_contract", "default_deliverables", "acceptance_hints", "seed_workspace",
    "validate_and_normalize_ir", "check_project_against_ir",
]
