"""Core package — contracts and bootstrap."""

from .context import GenerationContext
from .result import GenerationResult, StageResult, Severity, ValidationReport
from .contracts import Engine, Builder, Validator, PipelineStage, Component
from .errors import (
    EngineError, EngineExecutionError, BuilderError,
    ValidationError, PipelineError, ConfigurationError,
)

# Lazy import to avoid circular dependency with registry / engines
def __getattr__(name: str):
    if name in ("bootstrap", "build_configuration"):
        from .bootstrap import bootstrap, build_configuration
        return {"bootstrap": bootstrap, "build_configuration": build_configuration}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "GenerationContext", "GenerationResult", "StageResult", "Severity",
    "ValidationReport", "Engine", "Builder", "Validator", "PipelineStage",
    "Component", "EngineError", "EngineExecutionError", "BuilderError",
    "ValidationError", "PipelineError", "ConfigurationError",
    "bootstrap", "build_configuration",
]
