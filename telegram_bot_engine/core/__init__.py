"""Core package — contracts, context, state, artifacts."""

from .context import GenerationContext
from .result import GenerationResult, StageResult, Severity, ValidationReport
from .contracts import Engine, Builder, Validator, PipelineStage, Component
from .errors import (
    EngineError, EngineExecutionError, BuilderError,
    ValidationError, PipelineError, ConfigurationError,
)
from .artifact_store import ArtifactStore, ArtifactKey, ArtifactStoreError
from .metadata import RunMetadata
from .state import (
    ProjectState, RunState, DeploymentState, JobState,
    RunStatus, DeploymentStatus, JobStatus,
)
from .engine_role import EngineRole, PLANNING_OWNED_KEYS

__all__ = [
    "GenerationContext", "GenerationResult", "StageResult", "Severity",
    "ValidationReport", "Engine", "Builder", "Validator", "PipelineStage",
    "Component", "EngineError", "EngineExecutionError", "BuilderError",
    "ValidationError", "PipelineError", "ConfigurationError",
    "ArtifactStore", "ArtifactKey", "ArtifactStoreError", "RunMetadata",
    "ProjectState", "RunState", "DeploymentState", "JobState",
    "RunStatus", "DeploymentStatus", "JobStatus", "EngineRole",
    "PLANNING_OWNED_KEYS", "bootstrap", "build_configuration",
]


def __getattr__(name: str):
    if name in ("bootstrap", "build_configuration"):
        from .bootstrap import bootstrap, build_configuration
        return bootstrap if name == "bootstrap" else build_configuration
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
