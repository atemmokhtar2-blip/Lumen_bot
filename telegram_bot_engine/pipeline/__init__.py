"""
Pipeline package — the generation lifecycle.

The pipeline is the ordered path a request follows from the moment it
is received until the final project is produced.  Each stage runs only
after the previous stage has succeeded.  The orchestrator drives the
stages, collects results, and stops the pipeline on failure.
"""

from .base_stage import BaseStage
from .orchestrator import PipelineOrchestrator
from .stages import (
    ParseStage,
    ComposeBlueprintStage,
    ValidateBlueprintStage,
    GenerateStage,
    ValidateOutputStage,
    PackageStage,
)

__all__ = [
    "BaseStage",
    "PipelineOrchestrator",
    "ParseStage",
    "ComposeBlueprintStage",
    "ValidateBlueprintStage",
    "GenerateStage",
    "ValidateOutputStage",
    "PackageStage",
]
